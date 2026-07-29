# Hollali — Voice Assistant

A modular, offline-capable voice assistant with both **terminal** and **desktop GUI** interfaces. Hollali supports local LLM integration (Ollama), system controls, plugins, conversation memory, and multiple speech I/O engines.

## Features

- **Wake-word activation** — say "Hollali" to start a conversation
- **Continuous conversation** — listens with configurable silence timeout (default 8s)
- **Local LLM** — Ollama integration (`qwen:latest` or any installed model) for natural language understanding and chat
- **Dual interfaces** — terminal/text mode (`--text`) or full desktop GUI
- **Desktop GUI** — system tray icon, main chat window, compact overlay mode
- **Speech-to-text** — Google STT (online) or Vosk (offline, auto-downloads small model)
- **Text-to-speech** — pyttsx3 or espeak-ng
- **System controls** — volume (pulseaudio), screen lock, screenshot, brightness
- **Plugin system** — drop `.py` files into `plugins/` directory with `name`, `keywords`, and `handle(text)`
- **Conversation memory** — last 5 exchanges per session, persisted in SQLite across restarts
- **WolframAlpha**, weather, news, Wikipedia, email (Gmail), SMS (Twilio), Google Calendar, notes
- **Live STT preview** — partial recognition results shown in GUI
- **Audio waveform** — animated level meter in the desktop window
- **Conversation history** — browse past sessions from the SQLite database
- **Theme support** — dark/light toggle, persisted
- **Auto-start** — optional launch at login via settings

## Requirements

- **Python** 3.11+
- **Ollama** — for local LLM (install separately from [ollama.ai](https://ollama.ai))
- **PyAudio** — for Google STT (`portaudio-devel` + `pyaudio` pip package)
- **espeak-ng** — for TTS (optional, install via system package manager)

## Installation

```bash
# Clone or navigate to the project directory
cd /home/hollali/Projects/hollali-ai

# Install system dependencies (Fedora)
sudo dnf install -y portaudio-devel espeak-ng

# Install Python packages
pip install --user --break-system-packages \
  python-dotenv SpeechRecognition pyttsx3 pyjokes wikipedia \
  wolframalpha twilio requests google-api-python-client \
  google-auth-oauthlib google-auth vosk sounddevice pydub \
  numpy PySide6 pyaudio

# Or use requirements.txt
pip install --user --break-system-packages -r requirements.txt

# Set up your .env file
cp .env.example .env
nano .env   # add your API keys (see Configuration section)
```

> **Note:** `--break-system-packages` may be needed on systems using PEP 668 (externally managed Python). Use a virtual environment if preferred.

## Usage

### Desktop GUI (recommended)

```bash
python3 desktop.py
```

Launches the system tray icon, main chat window, and optional overlay. Minimize to tray instead of quitting. Access all features via toolbar or tray menu.

### Terminal / Text mode

```bash
python3 main.py --text
```

Type commands directly. Type `exit` to quit.

### Terminal / Voice mode

```bash
python3 main.py
```

Say **"Hollali"** to activate. Then speak your command. The assistant listens continuously with an 8-second silence timeout per utterance.

### Wake-word flow

1. **Idle** — listens for the wake word "Hollali" on repeat
2. **Conversation** — after wake word, listens with 8s timeout. Say "stop listening", "that's all", "never mind", or "go to sleep" to return to idle
3. **Exit** — say "exit" or "quit" to terminate

## Configuration

All configuration is via `.env` file (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `STT_ENGINE` | `google` | Speech-to-text engine: `google` or `vosk` |
| `TTS_ENGINE` | `espeak` | Text-to-speech engine: `pyttsx3` or `espeak` |
| `LLM_ENABLED` | `true` | Enable local LLM for natural conversation |
| `LLM_MODEL` | `qwen:latest` | Ollama model name |
| `LLM_API_URL` | `http://localhost:11434/api/generate` | Ollama API endpoint |
| `CONVERSATION_TIMEOUT` | `8` | Seconds of silence before ending conversation |

### API keys (optional — feature-specific)

| Variable | Service | Required For |
|---|---|---|
| `WEATHER_API_KEY` | OpenWeatherMap | Weather queries |
| `NEWS_API_KEY` | NewsAPI | News headlines |
| `WOLFRAM_APP_ID` | WolframAlpha | What-is / calculation queries |
| `GMAIL_USER` | Gmail | Email sending |
| `GMAIL_APP_PASSWORD` | Gmail (app password) | Email sending |
| `TWILIO_ACCOUNT_SID` | Twilio | SMS messaging |
| `TWILIO_AUTH_TOKEN` | Twilio | SMS messaging |
| `TWILIO_FROM_NUMBER` | Twilio | SMS messaging |
| `TWILIO_TO_NUMBER` | Twilio | SMS messaging |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | Google Calendar | Calendar integration |
| `CHROME_DRIVER_PATH` | Selenium | Pizza ordering (deprecated) |

### Switching STT/TTS at runtime

In the desktop GUI, open **Settings** (toolbar or tray menu) and select the desired engine. In terminal mode, edit `.env` and restart.

## Desktop GUI Features

### System Tray

- Microphone icon in the system tray
- **Left-click** — toggle main window visibility
- **Right-click menu** — Show Window, Start/Stop Listening, Show Overlay, Quit
- Desktop notification when listening starts

### Main Window

- **Toolbar** — Start/Stop mic, Overlay, History, **Quick Actions**, Theme, Settings
- **Quick Actions** — one-click buttons for common commands:
  Weather, News, Joke, Time, Date, Volume Up/Down, Screenshot, Lock
- **Chat area** — colored messages (blue=you, green=Hollali), scrollable
- **Waveform** — 24-bar animated audio level meter
- **Partial text** — live STT recognition preview (italic, fades after 3s)
- **Text input** — type commands with `Ctrl+Enter` or click Send
- **History panel** — browse past conversation sessions from SQLite

### Overlay Mode

- Compact, frameless, always-on-top widget (420×90)
- Shows listening status, last response, and live partial STT
- Draggable (grab and move), auto-positions at top-right of screen
- Close with ✕ button or `Escape` key

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Q` | Quit application |
| `Ctrl+M` | Toggle microphone listening |
| `Ctrl+,` | Open settings |
| `Ctrl+Enter` | Send typed command |
| `Escape` | Minimize window / hide overlay |

### Settings Dialog

- STT engine (google / vosk)
- TTS engine (pyttsx3 / espeak)
- Conversation timeout (3-60 sec)
- Theme (dark / light)
- Auto-start at login toggle

## Commands

All commands work in both terminal and desktop modes. Voice commands route through the LLM for natural language understanding. Built-in keyword handlers (run before LLM for instant response):

| Category | Keywords |
|---|---|
| **System** | "volume [0-100]", "brightness [0-100]", "screenshot", "lock" |
| **Greetings** | "hello", "hi", "hey", "how are you", "what's your name" |
| **Time/Date** | "what time is it", "what is the date" |
| **Weather** | "weather in [city]" |
| **News** | "latest news", "news headlines" |
| **Jokes** | "tell me a joke" |
| **Wikipedia** | "who is [person]" |
| **WolframAlpha** | "what is [query]", "calculate [expression]" |
| **Email** | "send email to [name]" |
| **Notes** | "make a note", "take a note" |
| **SMS** | "send message to [name]" |
| **Google Calendar** | "what's on my calendar" |
| **Open** | "open [app name]" |
| **Search** | "search YouTube for [query]", "search Google for [query]" |
| **Music** | "play some music" |
| **Change background** | "change my wallpaper", "change background" |
| **Pizza** | "order pizza" (deprecated — website changed) |

If no keyword matches, the LLM handles the request as a conversational query.

## Plugin System

Create a `.py` file in the `plugins/` directory with a class that exposes `name`, `keywords`, and `handle(text)`:

```python
class Example:
    name = "Example"
    keywords = ["test plugin"]
    def handle(self, text: str) -> str | None:
        return "This is an example plugin. It works!"
```

Plugins are auto-discovered at startup and matched before other handlers.

## Architecture

```
main.py           CLI entry point (text + voice modes)
desktop.py        GUI entry point (PySide6 — tray, window, overlay)
config.py         .env-based configuration
speech.py         STT (Google/Vosk) + TTS (pyttsx3/espeak)
commands.py       All command handlers + LLM routing
llm.py            Ollama LLM integration, conversation memory
database.py       SQLite persistence (conversations, notes, preferences)
utils.py          Cross-platform helpers (date, email, notes, apps)
system_control.py System commands (volume, brightness, screenshot, lock)
plugin_loader.py  Auto-discovers and loads plugins
plugins/          Drop-in plugin directory
```

```
                        ┌──────────────┐
                        │  main.py /   │
                        │  desktop.py  │
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    │   commands.py        │
                    │   (dispatches to     │
                    │    handlers / LLM)   │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────┴─────┐       ┌─────┴─────┐       ┌──────┴──────┐
    │ speech.py │       │  llm.py   │       │  plugins /  │
    │ STT + TTS │       │  Ollama   │       │  system_ctl │
    └───────────┘       └───────────┘       └─────────────┘
          │
    ┌─────┴─────┐
    │ config.py │
    │ database  │
    │ utils.py  │
    └───────────┘
```

## Troubleshooting

**"Could not find PyAudio"** — Install `portaudio-devel` (system) + `pyaudio` (pip), or switch to Vosk STT (`STT_ENGINE=vosk` in `.env`).

**"ModuleNotFoundError: No module named 'dotenv'"** — Install `python-dotenv`: `pip install python-dotenv`.

**No microphone / audio input** — Check PulseAudio/ALSA: `pactl info`, `arecord -l`. The app falls back to Vosk if PyAudio is unavailable.

**espeak-ng not found** — Install it: `sudo dnf install espeak-ng` (Fedora) or `sudo apt install espeak-ng` (Debian/Ubuntu).

**LLM not responding** — Ensure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull qwen:latest`).

**Brightness control not working** — Only works with ACPI/Intel backlight (`/sys/class/backlight/intel_backlight`). NVIDIA GPU backlights are typically read-only.

**Screenshot not working** — Requires a running X display server. Fails in headless/SSH sessions.

**Desktop app tray icon not visible** — On GNOME/Wayland, install `libappindicator-gtk3` or use the `gnome-shell-extension-appindicator` extension.

## License

MIT
