from __future__ import annotations

from queue import Queue
from unittest.mock import patch

import main


class TestGetInput:
    def test_returns_queued_text(self):
        q = Queue()
        q.put("hello")
        with patch("main._command_queue", q):
            result = main._get_input()
        assert result == "hello"

    def test_timeout_returns_none(self):
        q = Queue()
        with patch("main._command_queue", q):
            result = main._get_input(timeout=0.01)
        assert result is None

    def test_returns_none_when_exit_set(self):
        q = Queue()
        main._exit_event.set()
        try:
            with patch("main._command_queue", q):
                result = main._get_input(timeout=None)
            assert result is None
        finally:
            main._exit_event.clear()


class TestHandleConversation:
    def test_end_conversation_returns_false(self):
        main._exit_event.clear()
        with patch("main.talk") as mock_talk:
            result = main._handle_conversation("stop listening")
        assert result is False
        mock_talk.assert_called_once()

    def test_exit_keyword_returns_false_and_sets_exit(self):
        main._exit_event.clear()
        with patch("main.talk"):
            result = main._handle_conversation("quit")
        assert result is False
        assert main._exit_event.is_set()
        main._exit_event.clear()

    def test_responds_and_returns_true(self):
        main._exit_event.clear()
        with (
            patch("main.talk") as mock_talk,
            patch("main.process_command", return_value="42") as mock_process,
            patch("config.TUI_MODE", False),
        ):
            result = main._handle_conversation("what is 2+2")
        assert result is True
        mock_process.assert_called_once_with("what is 2+2")
        mock_talk.assert_called_once_with("42")
