from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import threading
import uuid
import webbrowser
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

import config
import database
import llm
import plugin_loader
import speech
from commands import process_command_stream
from log import logger


def _load_token() -> str:
    return os.environ.get("HOLLALI_API_TOKEN") or secrets.token_urlsafe(32)


API_TOKEN = _load_token()
API_HOST = "127.0.0.1"
API_PORT = int(os.environ.get("HOLLALI_API_PORT", "8765"))
FRONTEND_DIST = Path(__file__).resolve().parent / "static"
OPEN_BROWSER = False
MAX_MESSAGE_LENGTH = 20_000
ALLOWED_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    f"http://localhost:{API_PORT}",
    f"http://127.0.0.1:{API_PORT}",
]


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SettingsUpdate(BaseModel):
    theme: str | None = None
    stt_engine: str | None = None
    tts_engine: str | None = None
    conversation_timeout: int | None = Field(default=None, ge=3, le=60)
    llm_model: str | None = Field(default=None, min_length=1, max_length=120)
    wake_listening: bool | None = None


class VoiceAction(BaseModel):
    action: str = Field(max_length=20)


class EventHub:
    def __init__(self) -> None:
        self._clients: dict[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._clients[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.pop(queue, None)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients.items())
        for queue, loop in clients:
            if loop.is_running():
                loop.call_soon_threadsafe(_offer_event, queue, event)


def _offer_event(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    if queue.full():
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(event)


events = EventHub()


def _new_manager(session_id: str) -> llm.ConversationManager:
    manager = llm.ConversationManager()
    manager._session_id = session_id
    manager._initialized = True
    for message in database.load_conversation(session_id, limit=llm.MAX_HISTORY * 2):
        manager._history.append(message)
    return manager


class VoiceService:
    """Background listener that remains alive independently of the browser window."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._conversation_active = False
        self._active_request_cancel: threading.Event | None = None
        self._state = "idle"
        self._transcript = ""
        self._response_text = ""
        self._last_error = ""
        self._wake_enabled = True
        self._voice_conversation_id: str | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "wake_word": config.WAKE_WORD,
                "wake_listener_active": bool(self._thread and self._thread.is_alive() and self._state != "error"),
                "wake_engine": config.WAKE_ENGINE,
                "stt_engine": config.STT_ENGINE,
                "transcript": self._transcript,
                "response": self._response_text,
                "error": self._last_error,
            }

    def _set_state(self, state: str, **fields: Any) -> None:
        with self._lock:
            self._state = state
            event = {"type": "voice_state", **self.snapshot(), **fields}
        events.publish(event)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._last_error = ""
            self._thread = threading.Thread(target=self._run, name="hollali-voice", daemon=True)
            self._thread.start()

    def set_listening(self, active: bool) -> None:
        with self._lock:
            self._conversation_active = active
            if not active:
                self._voice_conversation_id = None
                if self._active_request_cancel:
                    self._active_request_cancel.set()
        self._set_state("listening" if active else "idle")
        self.start()

    def set_wake_enabled(self, enabled: bool) -> None:
        self._wake_enabled = enabled

    @property
    def wake_enabled(self) -> bool:
        return self._wake_enabled

    def interrupt(self) -> None:
        with self._lock:
            if self._active_request_cancel:
                self._active_request_cancel.set()
        speech.stop_speaking()
        self._set_state("interrupted")

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._conversation_active = False
            if self._active_request_cancel:
                self._active_request_cancel.set()
        speech.stop_speaking()
        self._set_state("idle")

    def _emit_level(self, level: float) -> None:
        events.publish({"type": "audio_level", "level": max(0.0, min(1.0, level))})

    def _on_partial(self, text: str) -> None:
        with self._lock:
            self._transcript = text
        events.publish({"type": "transcription", "text": text, "final": False})

    def _run(self) -> None:
        from constants import END_CONVERSATION
        from wake import listen_for_wake, wake_listener_active

        while not self._stop.is_set():
            try:
                with self._lock:
                    active = self._conversation_active
                if active:
                    self._set_state("listening")
                    text = speech.rec_audio(
                        timeout=config.CONVERSATION_TIMEOUT,
                        partial_cb=self._on_partial,
                        level_cb=self._emit_level,
                    )
                    if not text:
                        self.set_listening(False)
                        continue
                elif self._wake_enabled and wake_listener_active():
                    self._set_state("idle")
                    text = listen_for_wake(level_cb=self._emit_level, stop_event=self._stop)
                else:
                    if not self._wake_enabled:
                        if self._stop.wait(1.5):
                            break
                        continue
                    self._set_state("idle")
                    text = speech.rec_audio(timeout=2, level_cb=self._emit_level)

                if self._stop.is_set() or not text:
                    continue
                with self._lock:
                    active = self._conversation_active
                if not active and not speech.call(text):
                    continue
                if not active:
                    self.set_listening(True)
                    events.publish({"type": "wake_word_detected", "word": config.WAKE_WORD})
                    self._set_state("responding")
                    speech.talk("Hollali here. I'm listening.")
                    self._set_state("listening")
                    continue

                events.publish({"type": "transcription", "text": text, "final": True})
                with self._lock:
                    self._transcript = ""
                if any(phrase in text.lower() for phrase in END_CONVERSATION):
                    self.set_listening(False)
                    continue

                conversation_id = self._voice_conversation_id
                if conversation_id is None:
                    conversation_id = str(uuid.uuid4())
                    with self._lock:
                        self._voice_conversation_id = conversation_id
                database.create_conversation(conversation_id, text[:60] or "Voice conversation")
                manager = _new_manager(conversation_id)
                database.save_conversation(conversation_id, "user", text)
                with self._lock:
                    self._response_text = ""
                    cancel_event = threading.Event()
                    self._active_request_cancel = cancel_event
                self._set_state("processing", conversation_id=conversation_id)
                response = ""
                try:
                    for kind, chunk in process_command_stream(
                        text,
                        chat_manager=manager,
                        cancel_event=cancel_event,
                        check_exit=False,
                    ):
                        if kind == "chunk":
                            response += chunk
                            with self._lock:
                                self._response_text += chunk
                            if self._state != "responding":
                                self._set_state("responding", conversation_id=conversation_id)
                            events.publish(
                                {"type": "voice_response_chunk", "conversation_id": conversation_id, "text": chunk}
                            )
                finally:
                    with self._lock:
                        self._active_request_cancel = None
                if cancel_event.is_set():
                    self._set_state("listening" if self._conversation_active else "idle")
                    continue
                response = response.strip()
                if not response:
                    response = "I couldn't produce a response. Check the local model connection and try again."
                self._set_state("responding", conversation_id=conversation_id)
                database.save_conversation(conversation_id, "assistant", response)
                events.publish(
                    {
                        "type": "voice_response",
                        "conversation_id": conversation_id,
                        "text": response,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                self._set_state("speaking", conversation_id=conversation_id)
                speech.talk(response)
                with self._lock:
                    active = self._conversation_active
                self._set_state("listening" if active else "idle")
            except Exception as exc:
                logger.warning("Voice listener error: %s", exc, exc_info=True)
                with self._lock:
                    self._last_error = str(exc)
                self._set_state("error", error=str(exc))
                if self._stop.wait(1):
                    break
                self._set_state("idle")


voice = VoiceService()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    config.load_persisted_settings()
    llm.LLM_MODEL = config.LLM_MODEL
    voice.set_wake_enabled(database.get_preference("wake_listening", "true") != "false")
    plugin_loader.list_loaded()
    voice.start()
    if OPEN_BROWSER and FRONTEND_DIST.is_dir():
        webbrowser.open(f"http://{API_HOST}:{API_PORT}/")
    try:
        yield
    finally:
        voice.stop()
        database.close_connections()


app = FastAPI(title="Hollali Local API", version="1.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def restrict_local_requests(request, call_next):
    if request.url.hostname not in {"127.0.0.1", "localhost"}:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403, content={"detail": "Local requests only"})
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
    return await call_next(request)


def require_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias="hollali_session"),
) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    valid_header = scheme.lower() == "bearer" and secrets.compare_digest(token, API_TOKEN)
    valid_cookie = secrets.compare_digest(session_cookie or "", API_TOKEN)
    if not (valid_header or valid_cookie):
        raise HTTPException(status_code=401, detail="Authentication required")


Auth = Depends(require_token)


@app.get("/api/session")
def browser_session(response: Response) -> dict[str, bool]:
    response.set_cookie(
        "hollali_session",
        API_TOKEN,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
        max_age=60 * 60 * 24,
    )
    return {"authenticated": True}


@app.get("/api/health")
def health(_: None = Auth) -> dict[str, Any]:
    return {
        "backend": "online",
        "ollama": llm.check_available(timeout=1.5),
        "model": config.LLM_MODEL,
        "voice": voice.snapshot(),
    }


@app.get("/api/conversations")
def conversations(search: str = Query(default="", max_length=120), _: None = Auth) -> list[dict[str, Any]]:
    return database.list_conversations(search=search, limit=100)


@app.post("/api/conversations", status_code=201)
def create_conversation(body: CreateConversationRequest, _: None = Auth) -> dict[str, str]:
    session_id = str(uuid.uuid4())
    database.create_conversation(session_id, body.title.strip() or "New conversation")
    return {"id": session_id, "title": body.title.strip() or "New conversation"}


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, _: None = Auth) -> list[dict[str, str]]:
    if not database.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return database.load_conversation_entries(conversation_id, limit=200)


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: RenameConversationRequest, _: None = Auth) -> dict[str, str]:
    if not database.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    database.rename_conversation(conversation_id, body.title.strip())
    return {"id": conversation_id, "title": body.title.strip()}


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, _: None = Auth) -> None:
    database.delete_conversation(conversation_id)


@app.post("/api/chat/stream")
def chat_stream(body: ChatRequest, _: None = Auth) -> StreamingResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if text.lower() in {"exit", "quit"}:
        raise HTTPException(status_code=422, detail="Use the application Quit action to exit Hollali")

    conversation_id = body.conversation_id or str(uuid.uuid4())
    if not database.conversation_exists(conversation_id):
        database.create_conversation(conversation_id, text[:60] or "New conversation")
    cancel_event = threading.Event()
    request_id = str(body.request_id)
    _active_requests[request_id] = cancel_event

    def stream() -> Generator[bytes, None, None]:
        manager = _new_manager(conversation_id)
        database.save_conversation(conversation_id, "user", text)
        yield (
            json.dumps({"type": "start", "conversation_id": conversation_id, "request_id": request_id}) + "\n"
        ).encode()
        reply = ""
        try:
            for kind, content in process_command_stream(
                text,
                chat_manager=manager,
                cancel_event=cancel_event,
                check_exit=False,
            ):
                if cancel_event.is_set():
                    yield (json.dumps({"type": "cancelled"}) + "\n").encode()
                    return
                if kind == "chunk" and content:
                    reply += content
                    yield (json.dumps({"type": "chunk", "text": content}) + "\n").encode()
                elif kind == "done":
                    if not reply:
                        reply = content
            if cancel_event.is_set():
                if reply.strip():
                    database.save_conversation(conversation_id, "assistant", reply.strip())
                yield (json.dumps({"type": "cancelled"}) + "\n").encode()
                return
            if reply.strip():
                database.save_conversation(conversation_id, "assistant", reply.strip())
            yield (json.dumps({"type": "done", "text": reply.strip()}) + "\n").encode()
        except Exception as exc:
            logger.error("Chat stream failed: %s", exc, exc_info=True)
            yield (
                json.dumps({"type": "error", "message": "Hollali could not complete that request."}) + "\n"
            ).encode()
        finally:
            cancel_event.set()
            _active_requests.pop(request_id, None)

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})


_active_requests: dict[str, threading.Event] = {}


@app.post("/api/chat/{request_id}/cancel", status_code=202)
def cancel_chat(request_id: str, _: None = Auth) -> dict[str, bool]:
    event = _active_requests.get(request_id)
    if event is None:
        return {"cancelled": False}
    event.set()
    return {"cancelled": True}


@app.get("/api/settings")
def get_settings(_: None = Auth) -> dict[str, Any]:
    return {
        "theme": database.get_preference("theme", "dark"),
        "stt_engine": config.STT_ENGINE,
        "tts_engine": config.TTS_ENGINE,
        "conversation_timeout": config.CONVERSATION_TIMEOUT,
        "llm_model": config.LLM_MODEL,
        "wake_word": config.WAKE_WORD,
        "wake_engine": config.WAKE_ENGINE,
        "wake_listening": voice.wake_enabled,
    }


@app.patch("/api/settings")
def update_settings(body: SettingsUpdate, _: None = Auth) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    if "theme" in changes and changes["theme"] not in {"dark", "light"}:
        raise HTTPException(status_code=422, detail="Theme must be dark or light")
    if "stt_engine" in changes and changes["stt_engine"] not in {"google", "vosk"}:
        raise HTTPException(status_code=422, detail="Unsupported speech recognition engine")
    if "tts_engine" in changes and changes["tts_engine"] not in {"piper", "espeak", "pyttsx3"}:
        raise HTTPException(status_code=422, detail="Unsupported text-to-speech engine")
    if "llm_model" in changes:
        models = _ollama_models()
        if changes["llm_model"] not in {item["name"] for item in models}:
            raise HTTPException(status_code=422, detail="Select a model installed in Ollama")
    if "theme" in changes:
        database.set_preference("theme", changes["theme"])
    if "stt_engine" in changes:
        config.STT_ENGINE = changes["stt_engine"]
        database.set_preference("stt_engine", config.STT_ENGINE)
    if "tts_engine" in changes:
        config.TTS_ENGINE = changes["tts_engine"]
        database.set_preference("tts_engine", config.TTS_ENGINE)
    if "conversation_timeout" in changes:
        config.CONVERSATION_TIMEOUT = changes["conversation_timeout"]
        database.set_preference("conversation_timeout", str(config.CONVERSATION_TIMEOUT))
    if "llm_model" in changes:
        config.LLM_MODEL = changes["llm_model"]
        llm.LLM_MODEL = changes["llm_model"]
        database.set_preference("llm_model", config.LLM_MODEL)
    if "wake_listening" in changes:
        voice.set_wake_enabled(changes["wake_listening"])
        database.set_preference("wake_listening", "true" if changes["wake_listening"] else "false")
    return get_settings()


def _ollama_models() -> list[dict[str, Any]]:
    tags_url = config.LLM_API_URL.rsplit("/", 1)[0] + "/tags"
    try:
        response = requests.get(tags_url, timeout=2)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Ollama is unavailable") from exc
    return [
        {"name": item.get("name", ""), "size": item.get("size", 0), "modified_at": item.get("modified_at", "")}
        for item in data.get("models", [])
        if item.get("name")
    ]


@app.get("/api/models")
def models(_: None = Auth) -> dict[str, Any]:
    return {"current": config.LLM_MODEL, "models": _ollama_models()}


@app.get("/api/plugins")
def plugins(_: None = Auth) -> list[dict[str, Any]]:
    return [
        {"name": item["name"], "available": True, "management_supported": False}
        for item in plugin_loader.list_loaded()
    ]


@app.post("/api/voice")
def voice_action(body: VoiceAction, _: None = Auth) -> dict[str, Any]:
    if body.action == "start":
        voice.set_listening(True)
    elif body.action == "stop":
        voice.set_listening(False)
    elif body.action == "interrupt":
        speech.stop_speaking()
        voice.set_listening(True)
    elif body.action == "stop-speaking":
        speech.stop_speaking()
    else:
        raise HTTPException(status_code=422, detail="Supported voice actions: start, stop, interrupt, stop-speaking")
    return voice.snapshot()


@app.websocket("/api/events")
async def event_socket(websocket: WebSocket, token: str = Query(default="")) -> None:
    token = token or websocket.cookies.get("hollali_session", "")
    if not secrets.compare_digest(token, API_TOKEN):
        await websocket.close(code=4401, reason="Authentication required")
        return
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=4403, reason="Origin not allowed")
        return
    await websocket.accept()
    queue = events.subscribe()
    await websocket.send_json({"type": "voice_state", **voice.snapshot()})
    try:
        while True:
            event_task = asyncio.create_task(queue.get())
            receive_task = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait({event_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if event_task in done:
                await websocket.send_json(event_task.result())
            if receive_task in done:
                try:
                    message = json.loads(receive_task.result())
                except (ValueError, TypeError):
                    continue
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(queue)


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def frontend_not_built() -> str:
        return "<h1>Hollali web frontend is not built</h1><p>Run npm --prefix frontend run build.</p>"


def main() -> None:
    global OPEN_BROWSER
    if API_HOST not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Hollali API must bind to loopback")
    OPEN_BROWSER = True
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
