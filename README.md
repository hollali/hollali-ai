# Hollali — Voice Assistant

A modular, offline-capable voice assistant with a modern **desktop GUI** (PySide6) and **terminal** interface. Hollali integrates local LLM inference via Ollama, system controls, a plugin system, conversation memory, and multiple speech I/O engines. The desktop UI is inspired by ChatGPT and Claude — clean chat bubbles, streaming responses, dark/light themes, and a collapsible side navigation panel.

## Features

- **Wake-word activation** — say "Hollali" to start a conversation, then speak naturally
- **Continuous conversation** — configurable silence timeout (default 8s); say "stop listening" or "that's all" to return to idle
- **Local LLM** — Ollama integration for natural language understanding, tool dispatch, and chat (any installed model)
- **Dual interfaces** — full desktop GUI (recommended) or terminal text/voice mode
- **Desktop GUI** — system tray icon, main chat window with side navigation, compact overlay widget
- **Speech-to-text** — Google STT (online) or Vosk (offline, auto-downloads small model on first use)
- **Text-to-speech** — Piper TTS (default), espeak-ng, or pyttsx3
- **System controls** — volume (PulseAudio), screen lock, screenshot (ImageMagick), brightness (ACPI backlight)
- **Plugin system** — drop `.py` files into `plugins/` for custom capabilities
- **Conversation memory** — last 20 exchanges per session, persisted in SQLite across restarts
- **Tool dispatch** — LLM intelligently routes requests to built-in handlers (weather, news, email, calendar, etc.)
- **Streaming responses** — LLM output appears incrementally as it's generated
- **Dark/light themes** — toggle persisted to SQLite
- **76 automated tests** — covering commands, database, speech, plugins, system control, utils, and config
- **Structured logging** — file + console via `log.py`

## Requirements

- **Python** 3.11+
- **Ollama** — for local LLM ([ollama.ai](https://ollama.ai))
- **PyAudio** — for Google STT (`portaudio-devel` + `pyaudio` pip package)
- **Piper TTS** — default speech engine
- **espeak-ng** — optional fallback TTS

## Quick Start

```bash
# Install system dependencies (Fedora example)
sudo dnf install -y portaudio-devel espeak-ng

# Install Python packages
pip install -r requirements.txt
# or editable install
pip install -e .

# Install Piper TTS
mkdir -p ~/.local/bin
# Download piper_linux_x86_64.tar.gz from https://github.com/rhasspy/piper/releases
tar xzf piper_linux_x86_64.tar.gz -C ~/.local/bin/
mkdir -p ~/.local/share/piper-tts/voices
# Download en_US-lessac-medium.onnx + .json from
#   https://huggingface.co/rhasspy/piper-voices
# and place both in ~/.local/share/piper-tts/voices/

# Configure environment
cp .env.example .env
# Edit .env with your API keys (optional — only needed for specific features)

# Launch desktop app
hollali-desktop
```

## Usage

### Desktop GUI (recommended)

```bash
hollali-desktop    # or python3 desktop.py
```

Launches a system tray icon and the main chat window. The interface is divided into:

- **Side navigation** (collapsible with `Ctrl+B`) — new chat, conversation history, theme toggle, settings
- **Chat area** — streaming AI responses, user messages, thinking indicator, waveform visualizer
- **Input bar** — type your message or click the mic button for voice input

Minimize to tray instead of quitting — click the tray icon to restore.

### Terminal / Voice mode

```bash
hollali            # or python3 main.py
```

Say **"Hollali"** to activate, then speak your command. The assistant listens continuously with an 8-second silence timeout.

### Terminal / Text mode

```bash
hollali --text     # or python3 main.py --text
```

Type commands directly. Type `exit` to quit.

### Wake-word flow

1. **Idle** — listens for "Hollali" on repeat  
2. **Conversation** — after wake word, listens with timeout; say "stop listening", "that's all", or "never mind" to return to idle  
3. **Exit** — say "exit" or "quit", or press `Ctrl+C`

## Desktop GUI Deep Dive

### Main Window

| Element | Description |
|---|---|
| **Chat bubbles** | User messages right-aligned with surface background; AI responses left-aligned with accent border. Hover to reveal Copy button |
| **Streaming text** | AI responses appear token-by-token as the LLM generates them |
| **Thinking indicator** | Animated dots while the LLM processes |
| **Cancel button** | Stops an in-flight response |
| **Mic button** | Custom-painted toggle — green when active |
| **Send button** | Appears when text is entered; `Enter` to send |
| **Waveform** | 20-bar animated audio level meter |
| **Partial text** | Live STT recognition preview (italic, auto-fades after 3s) |
| **Welcome screen** | Suggestion chips (Weather, News, Joke, Time, Date) |
| **Toast notifications** | Fade-in/fade-out messages for events (theme change, new chat, errors) |

### Side Navigation

- **New Chat** — clears the conversation
- **History list** — last 30 sessions, click to reload
- **Theme toggle** — switches dark/light mode
- **Settings** — STT/TTS engine, timeout, theme, auto-start

### Overlay Mode

A compact, frameless always-on-top widget showing listening status, last response, and live partial STT. Draggable, auto-positions at top-right of screen. Close with ✕ or `Escape`.

### System Tray

- Microphone icon
- **Left-click** — toggle main window visibility
- **Right-click menu** — Show Window, Start/Stop Listening, Show Overlay, Quit

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+M` | Toggle microphone |
| `Ctrl+,` | Settings |
| `Ctrl+B` | Toggle sidebar |
| `Enter` | Send message |
| `Shift+Enter` | New line in input |
| `Escape` | Minimize window / close overlay |

## Configuration

All configuration via `.env` (copy from `.env.example`):

### Core

| Variable | Default | Description |
|---|---|---|
| `STT_ENGINE` | `google` | `google` or `vosk` |
| `TTS_ENGINE` | `piper` | `piper`, `espeak`, or `pyttsx3` |
| `LLM_ENABLED` | `true` | Enable local LLM |
| `LLM_MODEL` | `qwen:latest` | Ollama model name |
| `LLM_API_URL` | `http://localhost:11434/api/chat` | Ollama endpoint |
| `CONVERSATION_TIMEOUT` | `8` | Silence timeout (seconds) |

### API Keys (optional — feature-specific)

| Variable | Service | Required For |
|---|---|---|
| `WEATHER_API_KEY` | OpenWeatherMap | Weather |
| `NEWS_API_KEY` | NewsAPI | News headlines |
| `WOLFRAM_APP_ID` | WolframAlpha | What-is / calculate |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Gmail | Email sending |
| `TWILIO_*` | Twilio | SMS messaging |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | Google Calendar | Calendar events |

### File paths

| Variable | Default | Description |
|---|---|---|
| `PIPER_BIN_PATH` | `~/.local/bin/piper` | Piper binary |
| `PIPER_VOICE_PATH` | `~/.local/share/piper-tts/voices/en_US-lessac-medium.onnx` | Voice model |
| `NOTES_DIR` | `~/Documents/notes/` | Note storage |
| `WALLPAPER_DIR` | `~/Pictures/wallpapers/` | Wallpaper images |
| `MUSIC_DIR` | `~/Music/` | Music files |

Settings changed via the GUI are persisted to SQLite and take precedence over `.env` defaults.

## Commands

Built-in keyword handlers run before the LLM for instant response. If no keyword matches, the LLM handles the query conversationally.

| Category | Triggers |
|---|---|
| **System** | "volume 50", "brightness 75", "screenshot", "lock" |
| **Greetings** | "hello", "hi", "how are you", "what's your name" |
| **Time/Date** | "what time is it", "what's the date" |
| **Weather** | "weather in London" or "weather Paris" |
| **News** | "latest news", "news headlines" |
| **Jokes** | "tell me a joke" |
| **Wikipedia** | "who is Albert Einstein" or "search wikipedia for Python" |
| **WolframAlpha** | "what is the speed of light", "calculate 2+2" |
| **Email** | "send email to John" (prompts for content and recipient) |
| **Notes** | "make a note" (prompts for content) |
| **SMS** | "send message" (prompts for content) |
| **Calendar** | "what's on my calendar" |
| **Open** | "open YouTube", "open Google" |
| **Search** | "search YouTube for cats", "search Google for weather" |
| **Music** | "play some music" (random file from `MUSIC_DIR`) |
| **Wallpaper** | "change my wallpaper" |
| **Sleep** | "stop listening for 10 seconds" |

## Plugin System

Drop a `.py` file into `plugins/` with a class exposing `name`, `keywords`, and `handle(text)`:

```python
class Example:
    name = "Example"
    keywords = ["test plugin"]
    def handle(self, text: str) -> str | None:
        return "This is an example plugin. It works!"
```

Plugins are auto-discovered at startup and matched before built-in keyword handlers.

## Architecture

```
# Entry points
main.py           CLI entry point (text + voice modes)
desktop.py        GUI entry point (PySide6)

# Core
config.py         .env-based configuration
constants.py      Shared constants (end-conversation phrases)
log.py            Structured logging (file + console)
database.py       SQLite persistence (conversations, notes, preferences)

# Speech I/O
speech.py         STT (Google/Vosk) + TTS (Piper/espeak/pyttsx3)

# Intelligence
llm.py            Ollama integration, conversation manager, tool dispatch
commands.py       Built-in command handlers + LLM routing
system_control.py System commands (volume, brightness, screenshot, lock)

# Extensibility
plugin_loader.py  Auto-discovers and loads plugins
plugins/          Drop-in plugin directory

# Utilities
utils.py          Cross-platform helpers (date, email, notes, apps)

# Desktop UI (PySide6)
ui/
├── main_window.py     Main chat window, layout, signal wiring
├── tray.py            System tray icon and menu
├── navigation.py      Side navigation panel
├── widgets.py         ChatBubble, ChatView, WelcomeWidget, MicButton,
│                      ThinkingIndicator, ToastWidget, WaveformWidget
├── overlay.py         Compact overlay widget
├── dialogs.py         Settings dialog
├── threads.py         Background QThreads (audio engine, text command)
└── theming.py         Dark/light palette + Qt stylesheet generation

# Tests
tests/
├── test_commands.py       28 tests
├── test_database.py       12 tests
├── test_config.py          5 tests
├── test_plugin_loader.py   5 tests
├── test_speech.py          6 tests
├── test_system_control.py  7 tests
└── test_utils.py           8 tests
```

### Data flow (desktop GUI)

```
EngineThread (QThread)           TextCommandThread (QThread)
    │                                   │
    ├─ rec_audio() → STT                ├─ process_command_stream()
    │       │                           │       │
    │       ├─ partial_text ─────┐      │       ├─ chunk → MainWindow
    │       ├─ audio_level ──┐   │      │       └─ done  → MainWindow
    │       └─ final text   ──┼───┤      │
    │                         │   │      │
    ├─ call() → wake word?    │   │      │
    ├─ process_command() ─────┘   │      │
    │       │                     │      │
    │       ├─ talk_async() ──────┘      │
    │       └─ response_ready ────┐      │
    │                              │      │
    └─ status_changed ──────────┐ │      │
                                │ │      │
MainWindow (Qt main thread) ◄──┘─┘──────┘
    │
    ├─ ChatView (QScrollArea)
    ├─ ChatBubble updates
    ├─ ThinkingIndicator start/stop
    ├─ WaveformWidget.set_level()
    └─ ToastWidget.show_message()
```

## Troubleshooting

**PyAudio not found** — Install `portaudio-devel` + `pyaudio`, or switch to Vosk (`STT_ENGINE=vosk` in `.env`).

**LLM not responding** — Ensure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull qwen:latest`).

**Desktop tray icon not visible** — On GNOME/Wayland, install `libappindicator-gtk3` or the `gnome-shell-extension-appindicator` extension.

**Brightness not working** — Requires ACPI/Intel backlight (`/sys/class/backlight/intel_backlight`). May need `video` group membership.

**Screenshot not working** — Requires a running X display server with ImageMagick's `import` command installed.

## Contributing

```bash
# Run tests
python -m pytest tests/

# Check code style
ruff check .
```

## License

MIT
