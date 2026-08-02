from __future__ import annotations

from collections.abc import Generator
from typing import Literal

import config
import llm
import plugin_loader
import system_control
from handlers import (
    handle_about,
    handle_calculate,
    handle_change_background,
    handle_date,
    handle_email,
    handle_exit,
    handle_google_calendar,
    handle_google_search,
    handle_hello,
    handle_joke,
    handle_make_note,
    handle_news,
    handle_open,
    handle_play_music,
    handle_send_message,
    handle_sleep,
    handle_speak,
    handle_time,
    handle_weather,
    handle_what_is,
    handle_where_is,
    handle_wikipedia,
    handle_youtube_search,
)
from log import logger


def _handle_plugins(text: str) -> str:
    result = plugin_loader.match(text)
    return result or ""


COMMAND_HANDLERS: dict[str, dict] = {
    "handle_exit": {"fn": handle_exit},
    "handle_speak": {"fn": handle_speak},
    "handle_hello": {"fn": lambda t: handle_hello(t) or handle_about(t)},
    "handle_date": {"fn": handle_date},
    "handle_time": {"fn": handle_time},
    "handle_wikipedia": {"fn": handle_wikipedia},
    "handle_where_is": {"fn": handle_where_is},
    "handle_weather": {"fn": handle_weather},
    "handle_sleep": {"fn": handle_sleep},
    "handle_change_background": {"fn": handle_change_background},
    "handle_open": {"fn": handle_open},
    "handle_youtube_search": {"fn": handle_youtube_search},
    "handle_google_search": {"fn": handle_google_search},
    "handle_play_music": {"fn": handle_play_music},
    "handle_joke": {"fn": handle_joke},
    "handle_email": {"fn": handle_email},
    "handle_make_note": {"fn": handle_make_note},
    "handle_news": {"fn": handle_news},
    "handle_send_message": {"fn": handle_send_message},
    "handle_calculate": {"fn": handle_calculate},
    "handle_what_is": {"fn": handle_what_is},
    "handle_google_calendar": {"fn": handle_google_calendar},
    "handle_system": {"fn": system_control.handle_system_command},
    "handle_plugins": {"fn": _handle_plugins},
}


def _run_handlers(text: str, handler_names: list[str]) -> list[str]:
    responses = []
    for name in handler_names:
        entry = COMMAND_HANDLERS.get(name)
        if not entry:
            continue
        try:
            result = entry["fn"](text)
            if result is None:
                continue
            if isinstance(result, str) and result.strip():
                responses.append(result)
                break
        except SystemExit:
            raise
        except Exception as e:
            logger.error(f"Handler {name} error: {e}", exc_info=True)
    return responses


def process_command(text: str) -> str:
    _run_handlers(text, ["handle_exit"])

    kw_result = _run_handlers(text, ["handle_system", "handle_plugins"])
    if kw_result:
        return " ".join(kw_result).strip()

    all_handler_names = [k for k in COMMAND_HANDLERS if k not in ("handle_exit", "handle_system", "handle_plugins")]
    kw_result = _run_handlers(text, all_handler_names)
    if kw_result:
        return " ".join(kw_result).strip()

    if config.LLM_ENABLED:
        return llm.query_chat(text) or "I didn't understand that."

    return "I didn't understand that."


def process_command_stream(text: str) -> Generator[tuple[Literal["chunk", "done"], str], None, None]:
    """Generator yielding ("chunk", partial_text) or ("done", final_text)."""
    _run_handlers(text, ["handle_exit"])

    kw_result = _run_handlers(text, ["handle_system", "handle_plugins"])
    if kw_result:
        yield ("done", " ".join(kw_result).strip())
        return

    all_handler_names = [k for k in COMMAND_HANDLERS if k not in ("handle_exit", "handle_system", "handle_plugins")]
    kw_result = _run_handlers(text, all_handler_names)
    if kw_result:
        yield ("done", " ".join(kw_result).strip())
        return

    if config.LLM_ENABLED:
        yield from llm.query_chat_stream(text)
        return

    yield ("done", "I didn't understand that.")
