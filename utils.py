from __future__ import annotations

import datetime
import os
import random
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path

import calendar
import config
import pyjokes
import requests
from speech import talk


def today_date() -> str:
    now = datetime.datetime.now()
    weekday = calendar.day_name[now.weekday()]
    month = now.strftime("%B")
    day = now.day

    if 11 <= day <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"Today is {weekday}, {month} the {day}{suffix}."


def say_hello(text: str) -> str:
    GREETINGS = {"hi", "hey", "hola", "greetings", "wassup", "hello"}
    RESPONSES = ["howdy", "whats good", "hello", "hey there"]

    for word in text.split():
        if word.lower() in GREETINGS:
            return random.choice(RESPONSES) + "."

    return ""


def wiki_person(text: str) -> str | None:
    words = text.split()
    for i in range(len(words) - 3):
        if words[i].lower() == "who" and words[i + 1].lower() == "is":
            return " ".join(words[i + 2 : i + 4])
    return None


def send_email(to: str, content: str) -> None:
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        talk("Email credentials not configured. Please set GMAIL_USER and GMAIL_APP_PASSWORD in .env")
        return

    msg = MIMEText(content)
    msg["Subject"] = "Message from Hollali"
    msg["From"] = config.GMAIL_USER
    msg["To"] = to

    server = smtplib.SMTP("smtp.gmail.com", 587)
    try:
        server.ehlo()
        server.starttls()
        server.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.GMAIL_USER, [to], msg.as_string())
    finally:
        server.close()


def note(text: str) -> None:
    date = datetime.datetime.now()
    file_name = str(date).replace(":", "-") + "-note.txt"
    notes_dir = Path.home() / "Documents" / "AssistantNotes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    file_path = notes_dir / file_name

    with open(file_path, "w") as f:
        f.write(text)

    if sys.platform == "win32":
        os.startfile(file_path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(file_path)])
    else:
        subprocess.Popen(["xdg-open", str(file_path)])

    talk(f"Note saved to {file_path}")


def _change_bg_linux(image_path: str) -> bool:
    try:
        uri = Path(image_path).resolve().as_uri()
        result = subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def change_background(text: str) -> None:
    img_dir = Path.home() / "Pictures" / "Wallpapers"
    if not img_dir.exists():
        talk(f"Wallpaper directory not found at {img_dir}")
        return

    images = [f for f in img_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")]
    if not images:
        talk("No images found in wallpaper directory")
        return

    choice = random.choice(images)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.SystemParametersInfoW(20, 0, str(choice), 0)
        talk("Background changed successfully")
    elif sys.platform == "linux":
        if _change_bg_linux(str(choice)):
            talk("Background changed successfully")
        else:
            talk("Could not change background. Try installing feh or check your desktop environment.")
    else:
        talk("Background change is not supported on this platform")


def _which(cmd: str) -> str:
    return subprocess.run(["which", cmd], capture_output=True, text=True).stdout.strip()


def open_application(app_name: str) -> str | None:
    APP_MAP: dict[str, list[str]] = {
        "chrome": ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "firefox"],
        "word": ["libreoffice --writer"],
        "excel": ["libreoffice --calc"],
        "vs code": ["code"],
    }

    for key, cmds in APP_MAP.items():
        if key in app_name:
            for cmd in cmds:
                binary = cmd.split()[0]
                if sys.platform == "win32":
                    os.startfile(cmd)
                    return key
                if _which(binary):
                    subprocess.Popen(cmd.split())
                    return key
            talk(f"Could not find {key} on this system.")

    return None
