from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from pathlib import Path

import config
import utils
from speech import rec_audio, talk, talk_async


def handle_speak(text: str) -> str:
    words = text.lower().split()
    if words and words[0] in ("say", "speak", "talk") and len(words) > 1:
        phrase = text[len(words[0]) :].strip()
        if phrase:
            talk_async(phrase)
            return "\u2713"  # stop handler chain, no visible text
    return ""


def handle_sleep(text: str) -> str:
    if "don't listen" not in text and "stop listening" not in text and "do not listen" not in text:
        return ""
    talk("For how many seconds do you want me to sleep?")
    try:
        raw = rec_audio(timeout=10)
        a = int(raw.strip()) if raw else 0
    except (ValueError, TypeError, AttributeError):
        return " I didn't understand the number."
    if a <= 0:
        return " I need a positive number of seconds."
    time.sleep(a)
    return f" {a} seconds completed. Now you can ask me anything"


def handle_change_background(text: str) -> str:
    if "change background" in text or "change wallpaper" in text:
        utils.change_background(text)
        return ""
    return ""


def handle_exit(text: str) -> None:
    if any(w in text for w in ("exit", "quit")):
        talk("Goodbye!")
        raise SystemExit(0)


def handle_play_music(text: str) -> str:
    if "play music" not in text and "play song" not in text:
        return ""

    music_dir = Path(config.MUSIC_DIR)
    if not music_dir.exists():
        return " Music directory not found"

    songs = [f for f in music_dir.iterdir() if f.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a")]
    if not songs:
        return " No music files found in Music directory"

    talk("Here you go with music")
    choice = random.choice(songs)

    if sys.platform == "win32":
        os.startfile(str(choice))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(choice)])
    else:
        subprocess.Popen(["xdg-open", str(choice)])

    return " Playing music"
