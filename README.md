# Hollali — Local AI Web Assistant

Hollali is a local-first AI assistant with a browser-based React interface and a Python backend. The web app replaces the former desktop UI. Python remains responsible for Ollama, command routing, speech, wake-word detection, system controls, plugins, and SQLite persistence.

## Features

- **Browser chat** — streamed assistant replies, Markdown and code highlighting, search, persistent history, rename and delete
- **Voice workspace** — real microphone input, live transcription/audio events where supported, wake-word status, interrupt, and speech playback
- **Installable web app (PWA)** — works as a desktop/mobile app; installs from the browser and opens offline
- **Local model support** — uses Ollama and lists models actually installed on the configured endpoint
- **Settings** — theme, model, speech engines, listening timeout, and background wake listening, stored in the existing SQLite database
- **System controls** — volume, brightness, screenshot, and screen lock through existing Python handlers
- **Plugins and integrations** — existing Python plugin contract and optional weather, calendar, Gmail, and SMS integrations
- **Dark and light themes**
- **Terminal modes** — text and voice CLI remain available

Google speech recognition and optional integrations may contact their configured providers. Vosk and Ollama can run locally.

## Requirements

- Python 3.11+
- Node.js 22.12+ and npm (for building the frontend)
- Ollama and at least one installed model
- `portaudio-devel`, Python development headers, and PyAudio for Google STT; Vosk is an offline alternative
- Piper TTS (recommended) or `espeak-ng`

## Quick start

Fedora system dependencies:

```bash
sudo dnf install -y portaudio-devel python3-devel espeak-ng
```

From the project checkout:

```bash
python -m pip install -e ".[web,dev]"
npm ci --prefix frontend
cp .env.example .env
# Configure optional API keys and Ollama settings in .env
npm run build --prefix frontend
hollali-web
```

`hollali-web` starts the Python services on `127.0.0.1:8765` and opens the web app in your browser. The Python service owns the wake-word listener for as long as it is running, including when the browser is closed. Stop the service with `Ctrl+C`.

Conversation history, settings, and notes continue to use `~/.hollali/hollali.db`. The title metadata table is additive; existing conversation records are preserved.

## Frontend development

Run the backend and Vite separately:

```bash
# Terminal 1 — API, voice listener, and existing Python services
hollali-web

# Terminal 2 — React development server
npm --prefix frontend run dev
```

Open `http://127.0.0.1:1420`. Vite’s origin is explicitly allowed for local development. Set `VITE_HOLLALI_API_URL` in `frontend/.env.local` only if the API uses a non-default loopback port.

For a standalone frontend build, run `npm run build --prefix frontend`; the Python service serves `frontend/dist` from `/`. No conversation data or microphone audio is served to a remote host.

## Terminal use

Voice mode:

```bash
hollali
```

Say **“Hollali”**, then speak naturally. The default silence timeout is 8 seconds. Say “stop listening” or “that’s all” to return to idle.

Text mode:

```bash
hollali --text
```

## Wake word and speech

The default `WAKE_ENGINE=stt` detects the configured wake phrase from recognition results. `WAKE_ENGINE=openwakeword` can use a custom ONNX model placed in `~/.hollali/wakeword`; otherwise Hollali falls back to STT detection. Run `python -m wake` to inspect a trained model’s live scores.

The web app exposes a **Background listening** toggle (Settings → Voice). When disabled, the Python service stops sampling the microphone while idle and only records during an active voice session. For a fully offline wake path, prefer `WAKE_ENGINE=openwakeword`, or `STT_ENGINE=vosk` so recognition stays on-device.

Configure speech in `.env` or `~/.hollali/.env`:

| Variable | Default | Description |
|---|---|---|
| `STT_ENGINE` | `google` | `google` or offline `vosk` |
| `TTS_ENGINE` | `piper` | `piper`, `espeak`, or `pyttsx3` |
| `WAKE_WORD` | `hollali` | Activation word |
| `WAKE_ENGINE` | `stt` | `stt` or `openwakeword` |
| `CONVERSATION_TIMEOUT` | `8` | Listening timeout in seconds |

## Web API and local security

The React app and Python service communicate over HTTP and WebSockets. The backend binds to loopback only, validates `Host` and browser origins, and issues an `HttpOnly`, `SameSite=Strict` session cookie. JavaScript does not receive the API secret. Chat responses use newline-delimited JSON; `/api/events` carries live voice and transcription events.

| Operation | Endpoint |
|---|---|
| Browser session | `GET /api/session` |
| Stream or cancel chat | `POST /api/chat/stream`, `POST /api/chat/{request_id}/cancel` |
| List, search, load, rename, delete conversations | `/api/conversations` and `/api/conversations/{id}` |
| Read and update supported settings | `GET/PATCH /api/settings` |
| Ollama health and installed models | `GET /api/health`, `GET /api/models` |
| List loaded plugins | `GET /api/plugins` |
| Start, stop, or interrupt voice | `POST /api/voice` |
| Voice-state and audio events | `WS /api/events` |

Plugin enable/disable and per-plugin configuration are not offered because the existing plugin loader does not support those operations. The interface reports discovered plugins without presenting unsupported controls.

## Installable web app (PWA)

The frontend ships a web app manifest, app icons, and a service worker (`frontend/public/`). Open Hollali in a Chromium browser and choose **Install app** in the sidebar (or the browser’s install prompt) to run it in its own window. The service worker only caches the app shell and hashed assets and never intercepts `/api/*`; chat streaming and voice events always reach the live local service. Offline you can still open the app and browse cached conversations, but chatting requires the backend, which is always on the same machine.

## Architecture

```text
frontend/src/          React + TypeScript, Vite, Tailwind, Lucide
backend/api/app.py     FastAPI web/API server and background voice service
main.py                Existing terminal text/voice entry point
commands.py            Existing command routing and streamed LLM interface
llm.py                 Ollama integration and conversation manager
speech.py, wake.py     Speech engines and wake-word lifecycle
database.py            Existing SQLite storage plus additive conversation titles
handlers/, plugins/    Existing Python capabilities and plugin contract
system_control.py      Existing Linux system controls
```

## Configuration and integrations

Copy `.env.example` to `.env` for a source checkout or use `~/.hollali/.env` for a user-level configuration. Ollama is local by default. Optional keys configure OpenWeatherMap, NewsAPI, WolframAlpha, Gmail, Twilio, and Google Calendar. Features requiring those services may use their external network APIs.

## Tests and checks

```bash
python -m pytest tests/ -q
ruff check .
ruff format --check .
npm ci --prefix frontend
npm run build --prefix frontend
```

## Troubleshooting

- **PyAudio build fails:** install PortAudio and Python development headers, or select `STT_ENGINE=vosk`.
- **Ollama is offline:** start `ollama serve` and pull a model, for example `ollama pull qwen:latest`.
- **The web root says the frontend is not built:** run `npm run build --prefix frontend`, then restart `hollali-web`.
- **Voice input is unavailable:** check the configured speech engine and Linux microphone access; Vosk can run offline.

## License

MIT
