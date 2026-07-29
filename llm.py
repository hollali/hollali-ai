from __future__ import annotations

import datetime
import json
import re
from typing import Literal

import requests

import config
import database

LLM_API_URL = config.LLM_API_URL
LLM_MODEL = config.LLM_MODEL
MAX_HISTORY = 5

SESSION_ID = datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")

TOOL_NAMES = [
    "handle_date",
    "handle_time",
    "handle_wikipedia",
    "handle_where_is",
    "handle_weather",
    "handle_open",
    "handle_youtube_search",
    "handle_google_search",
    "handle_play_music",
    "handle_joke",
    "handle_email",
    "handle_make_note",
    "handle_news",
    "handle_send_message",
    "handle_calculate",
    "handle_what_is",
    "handle_google_calendar",
    "handle_pizza",
    "handle_change_background",
    "handle_sleep",
    "handle_exit",
    "handle_hello",
    "handle_system",
    "handle_plugins",
]

SYSTEM_PROMPT = f"""You are Hollali, a helpful voice assistant. You remember prior context.

Classify the user's intent and respond with ONLY valid JSON, no other text.

Valid tools: {", ".join(TOOL_NAMES)}

Rules:
- If the user wants to use one of the tools, respond: {{"tool": "tool_name"}}
- If the user is just chatting, responding conversationally, or the intent is unclear, respond: {{"chat": "your short response"}}
- Use handle_what_is for factual questions (what is X, who is Y, how many Z, etc.)
- Use handle_hello for greetings (hi, hello, hey, etc.)
- Use handle_joke for joke requests
- Use handle_weather for weather questions
- Use handle_play_music for playing music or songs
- Use handle_date/time for date/time questions
- Use handle_system for volume, brightness, screenshot, lock screen
- Use handle_plugins for custom plugin commands

Examples:
User: hello
{{"tool": "handle_hello"}}

User: what is the capital of France?
{{"tool": "handle_what_is"}}

User: tell me a joke
{{"tool": "handle_joke"}}

User: that's interesting, tell me more
{{"chat": "Glad you think so! What would you like to know?"}}

User: play some music
{{"tool": "handle_play_music"}}

User: I'm feeling bored
{{"chat": "I can tell you a joke, play music, or share the news. What sounds good?"}}

User: set volume to 50 percent
{{"tool": "handle_system"}}

User: take a screenshot
{{"tool": "handle_system"}}

User: lock my screen
{{"tool": "handle_system"}}"""

_history: list[str] = []

database.init_db()
prev_session = database.get_last_session_id()
if prev_session:
    prev_msgs = database.load_conversation(prev_session, limit=MAX_HISTORY * 2)
    for msg in prev_msgs:
        label = "User" if msg["role"] == "user" else "Hollali"
        _history.append(f"{label}: {msg['content']}")
    if _history:
        print(f"Loaded {len(_history)} messages from last session ({prev_session})")


def _build_prompt(user_input: str) -> str:
    parts = [SYSTEM_PROMPT, ""]
    for h in _history:
        parts.append(h)
    parts.append(f"User: {user_input}")
    return "\n".join(parts)


def _save(role: str, content: str) -> None:
    database.save_conversation(SESSION_ID, role, content)


def query(user_input: str) -> tuple[Literal["tool", "chat"], str]:
    global _history

    try:
        resp = requests.post(
            LLM_API_URL,
            json={
                "model": LLM_MODEL,
                "prompt": _build_prompt(user_input),
                "stream": False,
                "options": {"num_ctx": 2048, "temperature": 0.1},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except Exception as e:
        print(f"LLM error: {e}")
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
        _history.append(f"User: {user_input}")
        if len(_history) > MAX_HISTORY * 2:
            _history = _history[-(MAX_HISTORY * 2):]
        _save("assistant", f"[tool: {data['tool']}]")
        return "tool", data["tool"]

    if "chat" in data:
        reply = str(data["chat"]).strip()
        _history.append(f"User: {user_input}")
        _history.append(f"Hollali: {reply}")
        if len(_history) > MAX_HISTORY * 2:
            _history = _history[-(MAX_HISTORY * 2):]
        _save("assistant", reply)
        return "chat", reply

    _save("assistant", raw.strip())
    return "chat", raw.strip()
