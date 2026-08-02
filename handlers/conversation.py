from __future__ import annotations

import utils


def handle_hello(text: str) -> str:
    return utils.say_hello(text)


def handle_about(text: str) -> str:
    if "who are you" in text or "define yourself" in text:
        return (
            " Hello, I am Hollali. Your personal voice assistant. "
            "I am here to make your life easier. "
            "You can command me to perform various tasks such as "
            "asking questions or opening applications etcetera."
        )
    if "made you" in text or "created you" in text:
        return " I was created by Deon Cardoza"
    if "your name" in text:
        return " My name is Hollali"
    if "who am i" in text:
        return " You must probably be a human"
    if "why do you exist" in text or "why did you come to this word" in text:
        return " It is a secret"
    if "how are you" in text:
        return " I am awesome, Thank you\nHow are you?"
    if "fine" in text or "good" in text:
        return " It's good to know that your fine"
    return ""
