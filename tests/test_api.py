from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from backend.api import app as api_module


@pytest.fixture
def api_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(database, "DB_PATH", Path(tmp) / "hollali.db")
        database._local.conn = None
        monkeypatch.setattr(api_module, "API_TOKEN", "test-local-token")
        monkeypatch.setattr(api_module.voice, "start", lambda: None)
        with TestClient(api_module.app, base_url="http://127.0.0.1") as client:
            yield client
        database.close_connections()


def auth_headers():
    return {"Authorization": "Bearer test-local-token"}


def test_private_routes_require_a_bearer_token(api_client):
    response = api_client.get("/api/conversations")
    assert response.status_code == 401


def test_browser_session_issues_httponly_cookie_for_api_access(api_client):
    response = api_client.get("/api/session", headers={"Origin": "http://127.0.0.1:1420"})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert response.headers["access-control-allow-credentials"] == "true"
    assert api_client.get("/api/conversations").status_code == 200


def test_web_root_serves_the_built_frontend(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    if api_module.FRONTEND_DIST.is_dir():
        assert '<div id="root"></div>' in response.text
    else:
        assert "frontend is not built" in response.text


def test_conversation_metadata_and_messages_are_persisted(api_client):
    created = api_client.post("/api/conversations", json={"title": "Scratch chat"}, headers=auth_headers())
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert api_client.get("/api/conversations", headers=auth_headers()).json()[0]["title"] == "Scratch chat"

    renamed = api_client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "Renamed chat"}, headers=auth_headers()
    )
    assert renamed.status_code == 200
    database.save_conversation(conversation_id, "user", "A persisted request")
    rows = api_client.get(f"/api/conversations/{conversation_id}/messages", headers=auth_headers()).json()
    assert rows[0]["content"] == "A persisted request"
    assert rows[0]["role"] == "user"

    deleted = api_client.delete(f"/api/conversations/{conversation_id}", headers=auth_headers())
    assert deleted.status_code == 204
    assert api_client.get(f"/api/conversations/{conversation_id}/messages", headers=auth_headers()).status_code == 404


def test_chat_stream_routes_through_existing_command_stream(api_client, monkeypatch):
    def fake_stream(_text, **_kwargs):
        yield "chunk", "Hello"
        yield "chunk", " there"
        yield "done", "Hello there"

    monkeypatch.setattr(api_module, "process_command_stream", fake_stream)
    response = api_client.post(
        "/api/chat/stream",
        json={"text": "hello", "request_id": "00000000-0000-4000-8000-000000000001"},
        headers=auth_headers(),
    )
    records = [__import__("json").loads(line) for line in response.text.splitlines()]
    assert records[0]["type"] == "start"
    assert [record["text"] for record in records if record["type"] == "chunk"] == ["Hello", " there"]
    conversation_id = records[0]["conversation_id"]
    stored = database.load_conversation(conversation_id)
    assert [message["role"] for message in stored] == ["user", "assistant"]
    assert stored[-1]["content"] == "Hello there"


def test_settings_validate_engines_and_persist_theme(api_client):
    response = api_client.patch("/api/settings", json={"theme": "light"}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["theme"] == "light"
    invalid = api_client.patch("/api/settings", json={"stt_engine": "arbitrary"}, headers=auth_headers())
    assert invalid.status_code == 422
    mixed = api_client.patch(
        "/api/settings", json={"theme": "dark", "stt_engine": "arbitrary"}, headers=auth_headers()
    )
    assert mixed.status_code == 422
    assert api_client.get("/api/settings", headers=auth_headers()).json()["theme"] == "light"


def test_api_rejects_non_local_origin(api_client):
    response = api_client.get("/api/health", headers={**auth_headers(), "Origin": "https://attacker.example"})
    assert response.status_code == 403


def test_settings_toggle_background_listening(api_client):
    assert api_client.get("/api/settings", headers=auth_headers()).json()["wake_listening"] is True
    response = api_client.patch("/api/settings", json={"wake_listening": False}, headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["wake_listening"] is False
    assert api_module.voice.wake_enabled is False
    api_module.voice.set_wake_enabled(True)


def test_event_socket_sends_real_voice_lifecycle_snapshot(api_client):
    session = api_client.get("/api/session").cookies["hollali_session"]
    with api_client.websocket_connect(
        "/api/events",
        headers={"Origin": "http://127.0.0.1:8765", "Cookie": f"hollali_session={session}"},
    ) as socket:
        state = socket.receive_json()
    assert state["type"] == "voice_state"
    assert state["state"] == "idle"
    assert state["wake_word"] == api_module.config.WAKE_WORD
