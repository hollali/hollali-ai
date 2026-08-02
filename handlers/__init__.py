"""Built-in command handlers, grouped by concern.

Each submodule exposes ``handle_*`` callables that return an optional response
string ("" means "no match"). The registry and routing live in ``commands.py``.
"""

from handlers.conversation import handle_about, handle_hello
from handlers.knowledge import (
    handle_calculate,
    handle_joke,
    handle_news,
    handle_weather,
    handle_what_is,
    handle_where_is,
    handle_wikipedia,
)
from handlers.productivity import (
    handle_email,
    handle_google_calendar,
    handle_make_note,
    handle_send_message,
)
from handlers.system import (
    handle_change_background,
    handle_exit,
    handle_play_music,
    handle_sleep,
    handle_speak,
)
from handlers.time_date import handle_date, handle_time
from handlers.web import handle_google_search, handle_open, handle_youtube_search

__all__ = [
    "handle_about",
    "handle_calculate",
    "handle_change_background",
    "handle_date",
    "handle_email",
    "handle_exit",
    "handle_google_calendar",
    "handle_google_search",
    "handle_hello",
    "handle_joke",
    "handle_make_note",
    "handle_news",
    "handle_open",
    "handle_play_music",
    "handle_send_message",
    "handle_sleep",
    "handle_speak",
    "handle_time",
    "handle_weather",
    "handle_what_is",
    "handle_where_is",
    "handle_wikipedia",
    "handle_youtube_search",
]
