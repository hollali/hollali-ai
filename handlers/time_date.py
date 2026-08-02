from __future__ import annotations

import datetime

import utils


def handle_date(text: str) -> str:
    if not any(w in text for w in ("date", "day", "month", "today")):
        return ""
    return " " + utils.today_date()


def handle_time(text: str) -> str:
    if "time" not in text.lower():
        return ""
    now = datetime.datetime.now()
    meridiem = "p.m" if now.hour >= 12 else "a.m"
    hour = now.hour - 12 if now.hour >= 12 else now.hour
    if hour == 0:
        hour = 12
    minute = f"{now.minute:02d}"
    return f" It is {hour}:{minute} {meridiem}."
