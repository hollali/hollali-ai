from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import database


@pytest.fixture(autouse=True)
def _temp_db():
    database._local.conn = None
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = Path(f.name)
    with patch("database.DB_PATH", tmp_path):
        database.init_db()
        yield
    tmp_path.unlink(missing_ok=True)


class TestDatabase:
    def test_init_db_creates_tables(self):
        conn = database._get_conn()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        names = [r["name"] for r in tables]
        assert "conversations" in names
        assert "notes" in names
        assert "preferences" in names

    def test_save_and_load_conversation(self):
        database.save_conversation("sess1", "user", "hello")
        database.save_conversation("sess1", "assistant", "hi there")
        rows = database.load_conversation("sess1", limit=10)
        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[0]["content"] == "hello"
        assert rows[1]["role"] == "assistant"
        assert rows[1]["content"] == "hi there"

    def test_load_conversation_respects_limit(self):
        for i in range(5):
            database.save_conversation("sess2", "user", f"msg{i}")
        rows = database.load_conversation("sess2", limit=3)
        assert len(rows) == 3

    def test_save_and_list_notes(self):
        id1 = database.save_note("Title1", "Content1")
        id2 = database.save_note("Title2", "Content2")
        assert isinstance(id1, int)
        assert isinstance(id2, int)
        notes = database.list_notes(limit=10)
        assert len(notes) >= 2

    def test_list_notes_returns_dicts(self):
        database.save_note("Test", "Body")
        notes = database.list_notes()
        assert isinstance(notes, list)
        assert "id" in notes[0]
        assert "title" in notes[0]
        assert "content" in notes[0]
        assert "created_at" in notes[0]

    def test_get_preference_default(self):
        val = database.get_preference("nonexistent", "default_val")
        assert val == "default_val"

    def test_set_and_get_preference(self):
        database.set_preference("stt_engine", "vosk")
        val = database.get_preference("stt_engine")
        assert val == "vosk"

    def test_get_last_session_id_returns_none_when_empty(self):
        sid = database.get_last_session_id()
        assert sid is None

    def test_get_last_session_id(self):
        database.save_conversation("sess_last", "user", "test")
        sid = database.get_last_session_id()
        assert sid == "sess_last"

    def test_delete_conversation(self):
        database.save_conversation("del_sess", "user", "test")
        database.delete_conversation("del_sess")
        rows = database.load_conversation("del_sess")
        assert len(rows) == 0

    def test_clear_all_conversations(self):
        database.save_conversation("c1", "user", "a")
        database.save_conversation("c2", "user", "b")
        database.clear_all_conversations()
        assert database.get_last_session_id() is None
