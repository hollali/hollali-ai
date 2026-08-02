from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

import llm
from llm import ConversationManager


@pytest.fixture
def manager() -> ConversationManager:
    m = ConversationManager()
    m._session_id = "test_session"
    return m


class TestCheckAvailable:
    @patch("requests.get")
    def test_available(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        assert llm.check_available() is True
        mock_get.assert_called_once()

    @patch("requests.get", side_effect=requests.ConnectionError)
    def test_unavailable(self, mock_get):
        assert llm.check_available() is False


class TestPostRetry:
    def test_retries_then_succeeds(self, manager):
        session = MagicMock()
        ok = MagicMock(status_code=200)
        session.post.side_effect = [requests.ConnectionError("down"), ok]
        with patch.object(manager, "_get_session", return_value=session):
            with patch("llm.time.sleep") as mock_sleep:
                resp = manager._post([], stream=False, temperature=0.7)
        assert session.post.call_count == 2
        assert resp == ok
        mock_sleep.assert_called_once_with(0.5)

    def test_raises_after_max_retries(self, manager):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError("down")
        with patch.object(manager, "_get_session", return_value=session):
            with patch("llm.time.sleep"):
                with pytest.raises(requests.RequestException):
                    manager._post([], stream=False, temperature=0.7)
        assert session.post.call_count == llm.MAX_RETRIES

    def test_retries_on_http_500(self, manager):
        session = MagicMock()
        fail = MagicMock(status_code=500)
        ok = MagicMock(status_code=200)
        session.post.side_effect = [fail, ok]
        with patch.object(manager, "_get_session", return_value=session):
            with patch("llm.time.sleep"):
                resp = manager._post([], stream=False, temperature=0.7)
        assert resp == ok


class TestBuildMessages:
    def test_includes_system_and_history(self, manager):
        with patch.object(manager, "_init"):
            manager._history.append({"role": "user", "content": "hi"})
            messages = manager._build_messages("hello", "SYSTEM")
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "user"]
        assert messages[0]["content"] == "SYSTEM"
        assert messages[-1]["content"] == "hello"


class TestQueryChat:
    def test_query_chat_success(self, manager):
        reply = "Hi there!"
        session = MagicMock()
        session.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": reply}},
        )
        with patch.object(manager, "_get_session", return_value=session):
            with patch.object(manager, "_save") as mock_save:
                result = manager.query_chat("hello")
        assert result == reply
        assert mock_save.call_count == 2  # user + assistant persisted

    def test_query_chat_failure_returns_empty(self, manager):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError("down")
        with patch.object(manager, "_get_session", return_value=session):
            with patch("llm.time.sleep"):
                result = manager.query_chat("hello")
        assert result == ""


class TestQueryChatStream:
    def test_stream_yields_chunks_then_done(self, manager):
        lines = [
            b'{"message":{"content":"Hello"}}',
            b'{"message":{"content":" world"}}',
            b'{"done":true}',
        ]
        resp = MagicMock(status_code=200)
        resp.iter_lines.return_value = lines
        session = MagicMock()
        session.post.return_value = resp
        with patch.object(manager, "_get_session", return_value=session):
            with patch.object(manager, "_save"):
                events = list(manager.query_chat_stream("hi"))
        assert events == [("chunk", "Hello"), ("chunk", " world"), ("done", "Hello world")]

    def test_stream_error_yields_error_chunks(self, manager):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError("down")
        with patch.object(manager, "_get_session", return_value=session):
            with patch("llm.time.sleep"):
                events = list(manager.query_chat_stream("hi"))
        assert events[0][0] == "chunk"
        assert events[1][0] == "done"
        assert events[1][1] == ""
