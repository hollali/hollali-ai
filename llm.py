from __future__ import annotations

import datetime
import json
import threading
import time
from collections import deque
from collections.abc import Generator
from typing import Literal

import requests

import config
import database
from log import logger

LLM_API_URL = config.LLM_API_URL
LLM_MODEL = config.LLM_MODEL
MAX_HISTORY = 20
LLM_NUM_CTX = 8192
MAX_RETRIES = 3
RETRY_BACKOFF = [0.5, 1.5, 3.0]

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
    "handle_exit": "Quit the app",
    "handle_plugins": "Plugin commands",
}


def _build_chat_system_prompt() -> str:
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    caps = "\n".join(f"- {desc}" for desc in TOOL_DESCRIPTIONS.values())

    return f"""You are Hollali, an intelligent voice assistant. Today is {date_str}.

Capabilities:
{caps}

Answer the user's question clearly and completely. Be concise but thorough — if the question is complex, take your time and explain well. Use natural, conversational language."""


class ConversationManager:
    def __init__(self) -> None:
        self._history: deque[dict[str, str]] = deque(maxlen=MAX_HISTORY * 2)
        self._lock = threading.Lock()
        self._initialized = False
        self._session: requests.Session | None = None
        self._session_id: str | None = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _get_session_id(self) -> str:
        if self._session_id is None:
            self._session_id = datetime.datetime.now().strftime("session_%Y%m%d_%H%M%S")
        return self._session_id

    def _init(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        database.init_db()
        prev_session = database.get_last_session_id()
        if prev_session:
            prev_msgs = database.load_conversation(prev_session, limit=MAX_HISTORY * 2)
            with self._lock:
                for msg in reversed(prev_msgs):
                    self._history.append({"role": msg["role"], "content": msg["content"]})
                if self._history:
                    logger.info(f"Loaded {len(self._history)} messages from last session ({prev_session})")

    def _save(self, role: str, content: str) -> None:
        database.save_conversation(self._get_session_id(), role, content)

    def _build_messages(self, user_input: str, system_prompt: str) -> list[dict[str, str]]:
        self._init()
        messages = [{"role": "system", "content": system_prompt}]
        with self._lock:
            messages.extend(self._history)
        messages.append({"role": "user", "content": user_input})
        return messages

    def _post(self, messages: list[dict], stream: bool, temperature: float) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._get_session().post(
                    LLM_API_URL,
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "stream": stream,
                        "options": {"num_ctx": LLM_NUM_CTX, "temperature": temperature},
                    },
                    stream=stream,
                    timeout=120,
                )
                if resp.status_code < 500:
                    return resp
                logger.warning(f"Ollama returned HTTP {resp.status_code} (attempt {attempt + 1}/{MAX_RETRIES})")
                last_error = requests.HTTPError(f"HTTP {resp.status_code}")
            except (requests.ConnectionError, requests.Timeout, requests.RequestException) as e:
                logger.warning(f"Ollama request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[attempt])
        raise requests.RequestException(f"Ollama unreachable after {MAX_RETRIES} attempts") from last_error

    def _iter_stream(self, resp: requests.Response) -> Generator[str, None, None]:
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
                    yield chunk
            if data.get("done"):
                break

    def _append_both(self, user_input: str, reply: str) -> None:
        with self._lock:
            self._history.append({"role": "user", "content": user_input})
            self._history.append({"role": "assistant", "content": reply})
        self._save("user", user_input)
        self._save("assistant", reply)

    def query_chat(self, user_input: str) -> str:
        messages = self._build_messages(user_input, _build_chat_system_prompt())
        try:
            resp = self._post(messages, stream=False, temperature=0.7)
            resp.raise_for_status()
            reply = resp.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            return ""

        if reply:
            self._append_both(user_input, reply)
        return reply

    def query_chat_stream(self, user_input: str) -> Generator[tuple[Literal["chunk", "done"], str], None, None]:
        messages = self._build_messages(user_input, _build_chat_system_prompt())
        full_content = ""
        try:
            resp = self._post(messages, stream=True, temperature=0.7)
            resp.raise_for_status()
            for chunk in self._iter_stream(resp):
                full_content += chunk
                yield ("chunk", chunk)
        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            yield ("chunk", "[LLM error — is Ollama running?]")
            yield ("done", "")
            return

        if full_content.strip():
            self._append_both(user_input, full_content.strip())
        yield ("done", full_content.strip())


manager = ConversationManager()


def query_chat(user_input: str) -> str:
    return manager.query_chat(user_input)


def query_chat_stream(user_input: str) -> Generator[tuple[Literal["chunk", "done"], str], None, None]:
    yield from manager.query_chat_stream(user_input)


def check_available(timeout: float = 3.0) -> bool:
    """Return True if the Ollama server responds within `timeout` seconds."""
    try:
        resp = requests.get(LLM_API_URL.rsplit("/", 1)[0] + "/tags", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False
