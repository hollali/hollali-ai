from __future__ import annotations

import sys
import threading
import time
from queue import Queue

import config
from commands import process_command
from log import logger
from speech import call, rec_audio, talk

END_CONVERSATION = ("stop listening", "that's all", "never mind", "go to sleep", "shut up")

# ---------------------------------------------------------------------------
# TUI / Text mode
# ---------------------------------------------------------------------------

_tui_mode = False
_command_queue: Queue[str] = Queue()
_exit_event = threading.Event()


def tui_input_loop() -> None:
    while not _exit_event.is_set():
        try:
            line = input(">>> ").strip()
            if line:
                _command_queue.put(line)
        except (EOFError, KeyboardInterrupt):
            _exit_event.set()
            break


# ---------------------------------------------------------------------------
# Audio input loop (runs in background thread)
# ---------------------------------------------------------------------------

def audio_input_loop() -> None:
    while not _exit_event.is_set():
        try:
            text = rec_audio()
            if text:
                _command_queue.put(text)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Conversation handler
# ---------------------------------------------------------------------------

def _handle_conversation(text: str) -> bool:
    text_lower = text.lower()

    if any(w in text_lower for w in END_CONVERSATION):
        talk("Going back to idle. Say 'Hollali' when you need me.")
        return False

    if any(w in text_lower for w in ("exit", "quit")):
        talk("Goodbye!")
        _exit_event.set()
        return False

    if config.TUI_MODE:
        print(f"\nHollali: ", end="", flush=True)

    response = process_command(text)
    if response:
        talk(response)

    return True


def conversation_loop() -> None:
    talk("Hollali here. I'm listening.")

    while not _exit_event.is_set():
        text = _get_input(timeout=config.CONVERSATION_TIMEOUT)
        if _exit_event.is_set():
            break
        if text is None:
            talk("Going back to idle. Say 'Hollali' when you need me.")
            break
        if not _handle_conversation(text):
            break


# ---------------------------------------------------------------------------
# Input gathering (shared between TUI and audio)
# ---------------------------------------------------------------------------

def _get_input(timeout: float | None = None) -> str | None:
    try:
        return _command_queue.get(timeout=timeout) if timeout else _command_queue.get()
    except __import__("queue").Empty:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _tui_mode

    if "--text" in sys.argv or "-t" in sys.argv:
        config.TUI_MODE = True
        print("Hollali TEXT mode. Type your commands. Type 'exit' to quit.")
    else:
        config.TUI_MODE = False
        talk("Hollali is ready. Say 'Hollali' to start.")

    listener = threading.Thread(target=audio_input_loop, daemon=True)
    listener.start()

    if config.TUI_MODE:
        tui = threading.Thread(target=tui_input_loop, daemon=True)
        tui.start()

    while not _exit_event.is_set():
        try:
            text = _get_input()
            if not text or _exit_event.is_set():
                continue

            if config.TUI_MODE:
                conversation_loop()
                continue

            if not call(text):
                continue

            conversation_loop()

        except SystemExit:
            _exit_event.set()
            sys.exit(0)
        except KeyboardInterrupt:
            talk("Goodbye!")
            _exit_event.set()
            sys.exit(0)
        except Exception as e:
            logger.error("Main loop error", exc_info=True)
            if not config.TUI_MODE:
                talk("I don't know that")


if __name__ == "__main__":
    main()
