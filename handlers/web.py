from __future__ import annotations

import webbrowser

import utils


def handle_open(text: str) -> str:
    if "open" not in text.lower():
        return ""

    text_lower = text.lower()

    SITES: dict[str, str] = {
        "youtube": "https://youtube.com/",
        "google": "https://google.com/",
        "stackoverflow": "https://stackoverflow.com/",
    }

    for name, url in SITES.items():
        if name in text_lower:
            webbrowser.open(url)
            return f" Opening {name.title()}"

    result = utils.open_application(text_lower)
    if result:
        return f" Opening {result.title()}"
    return " Application not available"


def handle_youtube_search(text: str) -> str:
    if "youtube" not in text.lower():
        return ""
    ind = text.lower().split().index("youtube")
    search = text.split()[ind + 1 :]
    webbrowser.open("http://www.youtube.com/results?search_query=" + "+".join(search))
    return f" Opening {' '.join(search)} on youtube"


def handle_google_search(text: str) -> str:
    text_lower = text.lower()
    for keyword in ("search", "google"):
        if keyword in text_lower:
            ind = text_lower.split().index(keyword)
            search = text.split()[ind + 1 :]
            webbrowser.open("https://www.google.com/search?q=" + "+".join(search))
            return f" Searching {' '.join(search)} on google"
    return ""
