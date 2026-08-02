from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _getenv(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"

GMAIL_USER = _getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = _getenv("GMAIL_APP_PASSWORD")

WEATHER_API_KEY = _getenv("WEATHER_API_KEY")
NEWS_API_KEY = _getenv("NEWS_API_KEY")
WOLFRAM_APP_ID = _getenv("WOLFRAM_APP_ID")

TWILIO_ACCOUNT_SID = _getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = _getenv("TWILIO_FROM_NUMBER")
TWILIO_TO_NUMBER = _getenv("TWILIO_TO_NUMBER")

_raw_calendar_creds = _getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", "")
GOOGLE_CALENDAR_CREDENTIALS_PATH = (
    _raw_calendar_creds
    if _raw_calendar_creds and Path(_raw_calendar_creds).is_absolute()
    else str(Path.home() / ".hollali" / (_raw_calendar_creds or "credentials.json"))
)

LLM_ENABLED = _getenv("LLM_ENABLED", "true").lower() == "true"
LLM_MODEL = _getenv("LLM_MODEL", "qwen:latest")
LLM_API_URL = _getenv("LLM_API_URL", "http://localhost:11434/api/chat")

CONVERSATION_TIMEOUT = int(_getenv("CONVERSATION_TIMEOUT", "8"))

STT_ENGINE = _getenv("STT_ENGINE", "google")
VOSK_MODEL_PATH = _getenv("VOSK_MODEL_PATH", "")

WAKE_WORD = _getenv("WAKE_WORD", "hollali")
WAKE_ENGINE = _getenv("WAKE_ENGINE", "stt")
OPENWAKEWORD_MODEL_DIR = _getenv("OPENWAKEWORD_MODEL_DIR", str(Path.home() / ".hollali" / "wakeword"))

TTS_ENGINE = _getenv("TTS_ENGINE", "piper")

PIPER_BIN_PATH = _getenv("PIPER_BIN_PATH", str(Path.home() / ".local" / "bin" / "piper"))
PIPER_VOICE_PATH = _getenv(
    "PIPER_VOICE_PATH", str(Path.home() / ".local" / "share" / "piper-tts" / "voices" / "en_US-lessac-medium.onnx")
)
NOTES_DIR = _getenv("NOTES_DIR", str(Path.home() / "Documents" / "AssistantNotes"))
WALLPAPER_DIR = _getenv("WALLPAPER_DIR", str(Path.home() / "Pictures" / "Wallpapers"))
MUSIC_DIR = _getenv("MUSIC_DIR", str(Path.home() / "Music"))

TUI_MODE = False


def load_persisted_settings() -> None:
    try:
        from database import get_preference  # late import to avoid circular

        global STT_ENGINE, TTS_ENGINE, CONVERSATION_TIMEOUT
        stt = get_preference("stt_engine")
        tts = get_preference("tts_engine")
        timeout = get_preference("conversation_timeout")
        if stt:
            STT_ENGINE = stt
        if tts:
            TTS_ENGINE = tts
        if timeout:
            try:
                CONVERSATION_TIMEOUT = int(timeout)
            except ValueError:
                pass
    except Exception as e:
        import logging

        logging.getLogger("hollali").warning(f"Failed to load persisted settings: {e}")
