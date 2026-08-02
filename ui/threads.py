from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6 import QtCore

import config
from commands import process_command, process_command_stream
from constants import END_CONVERSATION
from speech import call, is_speaking, rec_audio, talk, talk_async
from wake import listen_for_wake, wake_listener_active

AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/hollali-autostart.desktop")


def _resolve_desktop_script() -> str:
    root = Path(__file__).resolve().parent.parent
    script = root / "hollali-desktop"
    if script.exists() and os.access(str(script), os.X_OK):
        return str(script)
    return "hollali-desktop"


class TextCommandThread(QtCore.QThread):
    finished = QtCore.Signal(str)
    partial = QtCore.Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        for event_type, *args in process_command_stream(self.text):
            if self.isInterruptionRequested():
                return
            if event_type == "chunk":
                self.partial.emit(args[0])
            elif event_type == "done":
                self.finished.emit(args[0] if args else "")
                return


class EngineThread(QtCore.QThread):
    partial_text = QtCore.Signal(str)
    response_ready = QtCore.Signal(str)
    wake_word_detected = QtCore.Signal()
    status_changed = QtCore.Signal(str)
    error_occurred = QtCore.Signal(str)
    audio_level = QtCore.Signal(float)
    thinking_started = QtCore.Signal()
    thinking_ended = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._in_conversation = False
        self._lock = threading.Lock()

    def run(self):
        self._enabled = True
        with self._lock:
            self._in_conversation = False
        while self._enabled:
            try:
                with self._lock:
                    in_conv = self._in_conversation
                if in_conv:
                    text = rec_audio(
                        timeout=config.CONVERSATION_TIMEOUT,
                        partial_cb=lambda t: self.partial_text.emit(t),
                        level_cb=lambda level: self.audio_level.emit(level),
                    )
                elif wake_listener_active():
                    text = listen_for_wake(
                        level_cb=lambda level: self.audio_level.emit(level),
                    )
                else:
                    text = rec_audio(
                        level_cb=lambda level: self.audio_level.emit(level),
                    )
            except Exception as e:
                self.error_occurred.emit(str(e))
                continue

            if not text:
                continue

            if is_speaking() and not call(text):
                continue

            with self._lock:
                in_conv = self._in_conversation
            if in_conv:
                if any(w in text.lower() for w in END_CONVERSATION):
                    self.status_changed.emit("idle")
                    with self._lock:
                        self._in_conversation = False
                    talk_async("Going back to idle. Say 'Hollali' when you need me.")
                    continue

                if any(w in text.lower() for w in ("exit", "quit")):
                    talk_async("Goodbye!")
                    self._enabled = False
                    break

                self.thinking_started.emit()
                response = process_command(text)
                self.thinking_ended.emit()
                if response:
                    talk_async(response)
                    self.response_ready.emit(response)
                continue

            if call(text):
                self.wake_word_detected.emit()
                with self._lock:
                    self._in_conversation = True
                self.status_changed.emit("conversation")
                talk("Hollali here. I'm listening.")
                continue

    def set_conversation(self, active: bool) -> None:
        with self._lock:
            self._in_conversation = active

    def is_conversation(self) -> bool:
        with self._lock:
            return self._in_conversation

    def stop(self):
        self._enabled = False
