from __future__ import annotations

import datetime
import json
import re
import threading
from typing import Literal

import requests

import config
import database
from log import logger

LLM_API_URL = config.LLM_API_URL
LLM_MODEL = config.LLM_MODEL
MAX_HISTORY = 20
LLM_NUM_CTX = 8192

_SESSION_ID: str | None = None


def _get_session_id() -> str:
    global _SESSION_ID
    if _SESSION_ID is None:
        _SESSION_ID = datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")
    return _SESSION_ID

TOOL_DESCRIPTIONS: dict[str, str] = {
    "handle_hello": "Greet the user",
    "handle_date": "Get today's date",
    "handle_time": "Get the current time",
    "handle_weather": "Check weather for a location",
    "handle_wikipedia": "Search Wikipedia",
    "handle_what_is": "Look up a concept online",
    "handle_where_is": "Show a location on Maps",
    "handle_google_search": "Search the web",
    "handle_youtube_search": "Search YouTube",
    "handle_calculate": "Do math calculations",
    "handle_joke": "Tell a joke",
    "handle_news": "Get news headlines",
    "handle_open": "Open an app, file, or website",
    "handle_play_music": "Play music",
    "handle_make_note": "Create a note",
    "handle_email": "Send an email",
    "handle_send_message": "Send a message",
    "handle_system": "Volume, screenshot, lock screen",
    "handle_change_background": "Change wallpaper",
    "handle_google_calendar": "Check calendar events",
    "handle_sleep": "Set a timer",
    "handle_pizza": "Order pizza",
    "handle_exit": "Quit the app",
    "handle_plugins": "Plugin commands",
}

TOOL_NAMES = list(TOOL_DESCRIPTIONS.keys())


def _build_tool_system_prompt() -> str:
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    tools_short = ", ".join(TOOL_NAMES)

    caps = "\n".join(f"- {desc}" for desc in TOOL_DESCRIPTIONS.values())

    return f"""You are Hollali, a voice assistant. Today is {date_str}.

Capabilities:
{caps}

Output JSON only: {{"tool":"handler_name"}} for actions, {{"chat":"reply"}} for chatting.

Examples:
"hello" -> {{"tool":"handle_hello"}}
"tell me a joke" -> {{"tool":"handle_joke"}}
"what's the weather in London" -> {{"tool":"handle_weather"}}
"set volume to 50%" -> {{"tool":"handle_system"}}
"what can you do" -> {{"chat":"I can check the weather, search the web, set timers, and more!"}}"""


def _build_chat_system_prompt() -> str:
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")

    caps = "\n".join(f"- {desc}" for desc in TOOL_DESCRIPTIONS.values())

    return f"""You are Hollali, an intelligent voice assistant. Today is {date_str}.

Capabilities:
{caps}

Answer the user's question clearly and completely. Be concise but thorough — if the question is complex, take your time and explain well. Use natural, conversational language."""

_history: list[dict] = []
_history_lock = threading.Lock()
_initialized = False
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def _init():
    global _initialized
    if _initialized:
        return
    _initialized = True
    database.init_db()
    prev_session = database.get_last_session_id()
    if prev_session:
        prev_msgs = database.load_conversation(prev_session, limit=MAX_HISTORY * 2)
        with _history_lock:
            for msg in reversed(prev_msgs):
                role = "user" if msg["role"] == "user" else "assistant"
                _history.append({"role": role, "content": msg["content"]})
            if _history:
                logger.info(f"Loaded {len(_history)} messages from last session ({prev_session})")


def _save(role: str, content: str) -> None:
    database.save_conversation(_get_session_id(), role, content)


def query(user_input: str) -> tuple[Literal["tool", "chat"], str]:
    _init()

    messages = [{"role": "system", "content": _build_tool_system_prompt()}]
    with _history_lock:
        messages.extend(_history)
    messages.append({"role": "user", "content": user_input})

    try:
        resp = _get_session().post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0.2},
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        return "chat", ""

    _save("user", user_input)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{[^{}]*\}', raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _save("assistant", raw)
                return "chat", raw
        else:
            _save("assistant", raw)
            return "chat", raw

    if "tool" in data and data["tool"] in TOOL_NAMES:
        with _history_lock:
            _history.append({"role": "user", "content": user_input})
            if len(_history) > MAX_HISTORY * 2:
                _history[:] = _history[-(MAX_HISTORY * 2):]
        _save("assistant", f"[tool: {data['tool']}]")
        return "tool", data["tool"]

    if "chat" in data:
        reply = str(data["chat"]).strip()
        with _history_lock:
            _history.append({"role": "user", "content": user_input})
            _history.append({"role": "assistant", "content": reply})
            if len(_history) > MAX_HISTORY * 2:
                _history[:] = _history[-(MAX_HISTORY * 2):]
        _save("assistant", reply)
        return "chat", reply

    _save("assistant", raw.strip())
    return "chat", raw.strip()


def query_stream(user_input: str):
    """Yields ("chunk", text) for each token, then ("done", intent_type, payload)."""
    _init()

    messages = [{"role": "system", "content": _build_tool_system_prompt()}]
    with _history_lock:
        messages.extend(_history)
    messages.append({"role": "user", "content": user_input})

    full_content = ""
    try:
        resp = _get_session().post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": True,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0.2},
            },
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in data:
                logger.error(f"Ollama error: {data['error']}")
                yield ("chunk", f"[Error: {data['error']}]")
                continue
            if "message" in data and "content" in data["message"]:
                chunk = data["message"]["content"]
                if chunk:
                    full_content += chunk
                    yield ("chunk", chunk)
            if data.get("done"):
                break
        if not full_content.strip():
            logger.warning("LLM returned empty response")
            yield ("done", "chat", "")
            return
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        yield ("chunk", "[LLM query failed — check Ollama is running]")
        yield ("done", "chat", "I had trouble connecting. Is Ollama running?")
        return

    _save("user", user_input)
    raw = full_content.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{[^{}]*\}', raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _save("assistant", raw)
                yield ("done", "chat", raw)
                return
        else:
            _save("assistant", raw)
            yield ("done", "chat", raw)
            return

    if "tool" in data and data["tool"] in TOOL_NAMES:
        with _history_lock:
            _history.append({"role": "user", "content": user_input})
            if len(_history) > MAX_HISTORY * 2:
                _history[:] = _history[-(MAX_HISTORY * 2):]
        _save("assistant", f"[tool: {data['tool']}]")
        yield ("done", "tool", data["tool"])
        return

    if "chat" in data:
        reply = str(data["chat"]).strip()
        with _history_lock:
            _history.append({"role": "user", "content": user_input})
            _history.append({"role": "assistant", "content": reply})
            if len(_history) > MAX_HISTORY * 2:
                _history[:] = _history[-(MAX_HISTORY * 2):]
        _save("assistant", reply)
        yield ("done", "chat", reply)
        return

    _save("assistant", raw)
    yield ("done", "chat", raw)


def query_chat(user_input: str) -> str:
    """Plain-text LLM chat, no JSON parsing. Returns the response string."""
    _init()

    messages = [{"role": "system", "content": _build_chat_system_prompt()}]
    with _history_lock:
        messages.extend(_history)
    messages.append({"role": "user", "content": user_input})

    try:
        resp = _get_session().post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0.7},
            },
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        return ""

    _save("user", user_input)
    if reply:
        with _history_lock:
            _history.append({"role": "user", "content": user_input})
            _history.append({"role": "assistant", "content": reply})
            if len(_history) > MAX_HISTORY * 2:
                _history[:] = _history[-(MAX_HISTORY * 2):]
        _save("assistant", reply)
    return reply


def query_chat_stream(user_input: str):
    """Streaming plain-text LLM chat. Yields ("chunk", text) then ("done", text)."""
    _init()

    messages = [{"role": "system", "content": _build_chat_system_prompt()}]
    with _history_lock:
        messages.extend(_history)
    messages.append({"role": "user", "content": user_input})

    full_content = ""
    try:
        resp = _get_session().post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": True,
                "options": {"num_ctx": LLM_NUM_CTX, "temperature": 0.7},
            },
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in data:
                logger.error(f"Ollama error: {data['error']}")
                continue
            if "message" in data and "content" in data["message"]:
                chunk = data["message"]["content"]
                if chunk:
                    full_content += chunk
                    yield ("chunk", chunk)
            if data.get("done"):
                break
        if not full_content.strip():
            logger.warning("LLM returned empty response")
            yield ("done", "")
            return
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        yield ("chunk", "[LLM error — is Ollama running?]")
        yield ("done", "")
        return

    _save("user", user_input)
    reply = full_content.strip()
    with _history_lock:
        _history.append({"role": "user", "content": user_input})
        _history.append({"role": "assistant", "content": reply})
        if len(_history) > MAX_HISTORY * 2:
            _history[:] = _history[-(MAX_HISTORY * 2):]
    _save("assistant", reply)
    yield ("done", reply)
