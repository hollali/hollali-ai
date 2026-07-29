from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from speech import talk


def set_volume(percent: int) -> bool:
    percent = max(0, min(100, percent))
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
            capture_output=True, text=True, check=True,
        )
        return True
    except Exception:
        return False


def get_volume() -> int:
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True,
        )
        for part in result.stdout.split():
            if part.endswith("%"):
                return int(part.rstrip("%"))
    except Exception:
        pass
    return -1


def set_brightness(percent: int) -> bool:
    percent = max(0, min(100, percent))
    backlight_dirs = list(Path("/sys/class/backlight").iterdir()) if Path("/sys/class/backlight").exists() else []
    if not backlight_dirs:
        return False

    try:
        max_raw = int((backlight_dirs[0] / "max_brightness").read_text().strip())
        value = max(1, int(max_raw * percent / 100))
        (backlight_dirs[0] / "brightness").write_text(str(value))
        return True
    except Exception:
        return False


def screenshot() -> Path | None:
    output = Path.home() / "Pictures" / f"screenshot_{__import__('datetime').datetime.now():%Y%m%d_%H%M%S}.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["import", "-window", "root", str(output)],
            capture_output=True, text=True, check=True,
        )
        return output
    except Exception:
        return None


def lock_screen() -> bool:
    for cmd in ["gnome-screensaver-command", "xdg-screensaver", "loginctl"]:
        try:
            if cmd == "loginctl":
                subprocess.run(["loginctl", "lock-session"], capture_output=True, check=True)
            else:
                subprocess.run([cmd, "lock"], capture_output=True, check=True)
            return True
        except Exception:
            continue
    return False


def handle_system_command(text: str) -> str:
    text_lower = text.lower()

    if "volume" in text_lower:
        if "max" in text_lower or "full" in text_lower or "100" in text_lower:
            set_volume(100)
            return " Volume set to maximum."
        if "mute" in text_lower or "off" in text_lower:
            set_volume(0)
            return " Volume muted."
        for word in text_lower.split():
            if word.isdigit():
                pct = int(word)
                if 0 <= pct <= 100:
                    set_volume(pct)
                    return f" Volume set to {pct} percent."
        current = get_volume()
        return f" Current volume is {current} percent." if current >= 0 else ""

    if "brightness" in text_lower:
        for word in text_lower.split():
            if word.isdigit():
                pct = int(word)
                if 0 <= pct <= 100:
                    if set_brightness(pct):
                        return f" Brightness set to {pct} percent."
                    return " Could not change brightness."
        return ""

    if "screenshot" in text_lower or "screen shot" in text_lower or "take a picture" in text_lower:
        path = screenshot()
        if path:
            return f" Screenshot saved to {path.name}."
        return " Could not take screenshot."

    if "lock" in text_lower and ("screen" in text_lower or "computer" in text_lower):
        if lock_screen():
            return " Screen locked."
        return " Could not lock screen."

    return ""
