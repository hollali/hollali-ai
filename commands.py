from __future__ import annotations

import datetime
import json
import os
import pickle
import random
import sys
import time
import webbrowser
from pathlib import Path

import config
import database
import llm
import plugin_loader
import pyjokes
import requests
import system_control
import utils
import wikipedia
from speech import talk, rec_audio


def handle_hello(text: str) -> str:
    return utils.say_hello(text)


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


def handle_wikipedia(text: str) -> str:
    person = utils.wiki_person(text)
    if person:
        try:
            wiki = wikipedia.summary(person, sentences=2)
            return " " + wiki
        except wikipedia.exceptions.DisambiguationError as e:
            return f" There are multiple results for {person}. Please be more specific."
        except wikipedia.exceptions.PageError:
            return f" I could not find information about {person}."
    return ""


def handle_where_is(text: str) -> str:
    words = text.lower().split()
    if "where" not in words or "is" not in words:
        return ""
    ind = words.index("is")
    location = text.split()[ind + 1:]
    url = "https://www.google.com/maps/place/" + "".join(location)
    webbrowser.open(url)
    return f" This is where {''.join(location)} is."


def handle_weather(text: str) -> str:
    if "weather" not in text.lower():
        return ""

    if not config.WEATHER_API_KEY:
        return " Weather API key not configured. Please set WEATHER_API_KEY in .env"

    if "in" not in text.lower().split():
        return ""
    ind = text.lower().split().index("in")
    location = "".join(text.split()[ind + 1:])
    url = f"http://api.openweathermap.org/data/2.5/weather?appid={config.WEATHER_API_KEY}&q={location}"

    try:
        js = requests.get(url).json()
    except Exception:
        return " Could not fetch weather data. Please check your connection."

    if js.get("cod") == "404":
        return " City Not Found"

    weather = js["main"]
    temperature = weather["temp"] - 273.15
    humidity = weather["humidity"]
    desc = js["weather"][0]["description"]
    return (
        f" The temperature in Celsius is {temperature:.1f}, "
        f"the humidity is {humidity}%, "
        f"and the weather description is {desc}."
    )


def handle_about(text: str) -> str:
    if "who are you" in text or "define yourself" in text:
        return (" Hello, I am Hollali. Your personal voice assistant. "
                "I am here to make your life easier. "
                "You can command me to perform various tasks such as "
                "asking questions or opening applications etcetera.")
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


def handle_sleep(text: str) -> str:
    if "don't listen" in text or "stop listening" in text or "do not listen" in text:
        talk("for how many seconds do you want me to sleep")
        try:
            a = int(rec_audio())
        except (ValueError, TypeError):
            return " I didn't understand the number."
        time.sleep(a)
        return f" {a} seconds completed. Now you can ask me anything"
    return ""


def handle_change_background(text: str) -> str:
    if "change background" in text or "change wallpaper" in text:
        utils.change_background(text)
        return ""
    return ""


def handle_exit(text: str) -> None:
    if any(w in text for w in ("exit", "quit")):
        talk("Goodbye!")
        raise SystemExit(0)


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
    search = text.split()[ind + 1:]
    webbrowser.open("http://www.youtube.com/results?search_query=" + "+".join(search))
    return f" Opening {' '.join(search)} on youtube"


def handle_google_search(text: str) -> str:
    text_lower = text.lower()
    for keyword in ("search", "google"):
        if keyword in text_lower:
            ind = text_lower.split().index(keyword)
            search = text.split()[ind + 1:]
            webbrowser.open("https://www.google.com/search?q=" + "+".join(search))
            return f" Searching {' '.join(search)} on google"
    return ""


def handle_play_music(text: str) -> str:
    if "play music" not in text and "play song" not in text:
        return ""

    music_dir = Path.home() / "Music"
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
        import subprocess
        subprocess.Popen(["open", str(choice)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(choice)])

    return " Playing music"


def handle_joke(text: str) -> str:
    if "joke" in text.lower():
        return " " + pyjokes.get_joke()
    return ""


def handle_email(text: str) -> str:
    has_email_keyword = any(kw in text for kw in ("email", "gmail", "mail"))
    is_computer = "computer" in text

    if not has_email_keyword:
        return ""

    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        return " Email credentials not configured. Please set GMAIL_USER and GMAIL_APP_PASSWORD in .env"

    try:
        talk("What should I say?")
        content = rec_audio()
        if not content:
            return " I didn't catch that."

        if is_computer:
            to = config.GMAIL_USER
        else:
            talk("Whom should I send it to?")
            to = input("Enter To Address: ").strip()

        utils.send_email(to, content)
        return " Email has been sent!"
    except Exception as e:
        print(e)
        return " I am not able to send this email"


def handle_make_note(text: str) -> str:
    if "make a note" not in text:
        return ""
    talk("What would you like me to write down?")
    note_text = rec_audio()
    if note_text:
        utils.note(note_text)
        database.save_note(title="", content=note_text)
        return " I have made a note of that."
    return " I didn't catch that."


def handle_news(text: str) -> str:
    if "news" not in text:
        return ""

    if not config.NEWS_API_KEY:
        return " News API key not configured. Please set NEWS_API_KEY in .env"

    url = f"http://newsapi.org/v2/top-headlines?country=in&apiKey={config.NEWS_API_KEY}"

    try:
        response = requests.get(url)
        response.raise_for_status()
    except Exception:
        return " Please check your connection"

    news = json.loads(response.text)

    for article in news.get("articles", []):
        title = article.get("title", "")
        description = article.get("description", "")
        if title:
            talk(str(title))
        if description:
            talk(str(description))
        time.sleep(2)

    return ""


def handle_send_message(text: str) -> str:
    if "send message" not in text:
        return ""

    if not all([config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN, config.TWILIO_FROM_NUMBER, config.TWILIO_TO_NUMBER]):
        return " Twilio credentials not configured. Please set them in .env"

    from twilio.rest import Client

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    talk("What should I send?")
    body = rec_audio()
    if not body:
        return " I didn't catch that."

    message = client.messages.create(
        body=body,
        from_=config.TWILIO_FROM_NUMBER,
        to=config.TWILIO_TO_NUMBER,
    )
    print(message.sid)
    return " Message sent successfully"


def handle_calculate(text: str) -> str:
    if "calculate" not in text:
        return ""

    if not config.WOLFRAM_APP_ID:
        return " WolframAlpha API key not configured. Please set WOLFRAM_APP_ID in .env"

    import wolframalpha

    client = wolframalpha.Client(config.WOLFRAM_APP_ID)
    ind = text.lower().split().index("calculate")
    query = " ".join(text.split()[ind + 1:])
    try:
        res = client.query(query)
        answer = next(res.results).text
        return f" The answer is {answer}"
    except Exception as e:
        print(e)
        return " I could not calculate that."


def handle_what_is(text: str) -> str:
    has_what = "what is" in text.lower() or "who is" in text.lower()
    if not has_what:
        return ""

    if not config.WOLFRAM_APP_ID:
        return " WolframAlpha API key not configured. Please set WOLFRAM_APP_ID in .env"

    import wolframalpha

    client = wolframalpha.Client(config.WOLFRAM_APP_ID)
    ind = text.lower().split().index("is")
    query = " ".join(text.split()[ind + 1:])
    try:
        res = client.query(query)
        answer = next(res.results).text
        return f" {answer}"
    except Exception as e:
        print(e)
        return " I could not find that."


def handle_google_calendar(text: str) -> str:
    if "calendar" not in text.lower():
        return ""

    try:
        service = _get_calendar_service()
        _calendar_events(10, service)
    except Exception as e:
        print(e)
        return " Could not connect to Google Calendar. Please check your credentials and connection."
    return ""


def _get_calendar_service():
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
    creds = None

    token_path = Path("token.pickle")
    if token_path.exists():
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_path = Path(config.GOOGLE_CALENDAR_CREDENTIALS_PATH)
            if not creds_path.exists():
                raise FileNotFoundError(f"Credentials file not found: {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)


def _calendar_events(num: int, service) -> None:
    from googleapiclient.discovery import Resource

    talk("Hey there! Good Day. Hope you are doing fine. These are the events to do today")
    now = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"Getting the upcoming {num} events")
    events_result = (
        service.events()
        .list(calendarId="primary", timeMin=now, maxResults=num, singleEvents=True, orderBy="startTime")
        .execute()
    )
    events = events_result.get("items", [])

    if not events:
        talk("No upcoming events found.")

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        events_today = event["summary"]
        start_time = str(start.split("T")[1].split("-")[0])
        if int(start_time.split(":")[0]) < 12:
            start_time = start_time + "am"
        else:
            start_time = str(int(start_time.split(":")[0]) - 12) + "pm"
        talk(f"{events_today} at {start_time}")


def handle_pizza(text: str) -> str:
    if "pizza" not in text and "order" not in text:
        return ""
    _pizza_order()
    return ""


def _pizza_order() -> None:
    if not config.CHROME_DRIVER_PATH:
        talk("ChromeDriver path not configured. Please set CHROME_DRIVER_PATH in .env")
        return

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = webdriver.ChromeOptions()
    if config.CHROME_DRIVER_PATH:
        service = webdriver.chrome.service.Service(config.CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.maximize_window()
    talk("Opening Dominos")
    driver.get("https://www.dominos.co.in/")
    time.sleep(2)

    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "ORDER ONLINE NOW"))
        ).click()
    except Exception:
        talk("Could not find the order button on Dominos website.")
        driver.quit()
        return

    time.sleep(2)
    talk("Finding your location")

    talk("Please enter your location manually since location detection has changed.")
    talk("Pizza ordering via voice is currently unavailable due to website changes.")
    driver.quit()


_plugin_handlers: list[dict] = []


def _load_plugins() -> None:
    global _plugin_handlers
    _plugin_handlers = plugin_loader.discover()


def _handle_plugins(text: str) -> str:
    result = plugin_loader.match(text)
    return result or ""


# Load plugins on import
_load_plugins()


COMMAND_HANDLERS: dict[str, dict] = {
    "handle_exit": {"fn": handle_exit, "early": True},
    "handle_hello": {"fn": lambda t: handle_hello(t) or handle_about(t), "early": False},
    "handle_date": {"fn": handle_date, "early": False},
    "handle_time": {"fn": handle_time, "early": False},
    "handle_wikipedia": {"fn": handle_wikipedia, "early": False},
    "handle_where_is": {"fn": handle_where_is, "early": False},
    "handle_weather": {"fn": handle_weather, "early": False},
    "handle_sleep": {"fn": handle_sleep, "early": False},
    "handle_change_background": {"fn": handle_change_background, "early": False},
    "handle_open": {"fn": handle_open, "early": False},
    "handle_youtube_search": {"fn": handle_youtube_search, "early": False},
    "handle_google_search": {"fn": handle_google_search, "early": False},
    "handle_play_music": {"fn": handle_play_music, "early": False},
    "handle_joke": {"fn": handle_joke, "early": False},
    "handle_email": {"fn": handle_email, "early": False},
    "handle_make_note": {"fn": handle_make_note, "early": False},
    "handle_news": {"fn": handle_news, "early": False},
    "handle_send_message": {"fn": handle_send_message, "early": False},
    "handle_calculate": {"fn": handle_calculate, "early": False},
    "handle_what_is": {"fn": handle_what_is, "early": False},
    "handle_google_calendar": {"fn": handle_google_calendar, "early": False},
    "handle_pizza": {"fn": handle_pizza, "early": False},
    "handle_system": {"fn": system_control.handle_system_command, "early": False},
    "handle_plugins": {"fn": _handle_plugins, "early": False},
}


def _run_handlers(text: str, handler_names: list[str]) -> list[str]:
    responses = []
    for name in handler_names:
        entry = COMMAND_HANDLERS.get(name)
        if not entry:
            continue
        try:
            result = entry["fn"](text)
            if result is None:
                continue
            if isinstance(result, str) and result.strip():
                responses.append(result)
                break
        except SystemExit:
            raise
        except Exception as e:
            print(f"Handler {name} error: {e}")
    return responses


def process_command(text: str) -> str:
    responses = _run_handlers(text, ["handle_exit"])

    # Keyword-matched handlers run before LLM (system control, plugins)
    kw_result = _run_handlers(text, ["handle_system", "handle_plugins"])
    if kw_result:
        return " ".join(kw_result).strip()

    if config.LLM_ENABLED:
        intent, payload = llm.query(text)

        if intent == "tool" and payload in COMMAND_HANDLERS:
            if payload not in ("handle_exit", "handle_system", "handle_plugins"):
                responses.extend(_run_handlers(text, [payload]))
            return " ".join(responses).strip()
        if intent == "chat" and payload:
            return payload

    # Fallback: all keyword handlers
    all_handlers = [k for k in COMMAND_HANDLERS if k not in ("handle_exit", "handle_system", "handle_plugins")]
    responses = _run_handlers(text, all_handlers)

    result = " ".join(responses).strip()
    if not result and config.LLM_ENABLED:
        _, payload = llm.query(text)
        return payload

    return result
