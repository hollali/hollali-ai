from __future__ import annotations

import os
import sys

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

GOOGLE_CALENDAR_CREDENTIALS_PATH = _getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", "credentials.json")
CHROME_DRIVER_PATH = _getenv("CHROME_DRIVER_PATH")

LLM_ENABLED = _getenv("LLM_ENABLED", "true").lower() == "true"
LLM_MODEL = _getenv("LLM_MODEL", "qwen:latest")
LLM_API_URL = _getenv("LLM_API_URL", "http://localhost:11434/api/generate")

CONVERSATION_TIMEOUT = int(_getenv("CONVERSATION_TIMEOUT", "8"))

STT_ENGINE = _getenv("STT_ENGINE", "google")  # google or vosk
VOSK_MODEL_PATH = _getenv("VOSK_MODEL_PATH", "")

TTS_ENGINE = _getenv("TTS_ENGINE", "pyttsx3")  # pyttsx3 or espeak
TUI_MODE = False  # set via --text flag at runtime
