from __future__ import annotations

import json
import time
import urllib.parse
import webbrowser

import pyjokes
import requests
import wikipedia

import config
import utils
from log import logger
from speech import talk_async

_http = requests.Session()


def handle_wikipedia(text: str) -> str:
    person = utils.wiki_person(text)
    if not person:
        words = text.lower().split()
        if "wikipedia" in words:
            # Try the words after "wikipedia" as search term
            ind = words.index("wikipedia")
            after = text.split()[ind + 1 :]
            if after:
                person = " ".join(after)
    if person:
        try:
            wiki = wikipedia.summary(person, sentences=2, auto_suggest=False)
            return " " + wiki
        except wikipedia.exceptions.DisambiguationError:
            return f" There are multiple results for {person}. Please be more specific."
        except wikipedia.exceptions.PageError:
            return f" I could not find information about {person}."
    return ""


def handle_where_is(text: str) -> str:
    words = text.lower().split()
    if "where" not in words or "is" not in words:
        return ""
    ind = words.index("is")
    location = " ".join(text.split()[ind + 1 :])
    url = "https://www.google.com/maps/place/" + urllib.parse.quote(location)
    webbrowser.open(url)
    return f" This is where {location} is."


def handle_weather(text: str) -> str:
    if "weather" not in text.lower():
        return ""

    if not config.WEATHER_API_KEY:
        return " Weather API key not configured. Please set WEATHER_API_KEY in .env"

    words = text.lower().split()
    if "in" in words:
        ind = words.index("in")
        location = urllib.parse.quote(" ".join(text.split()[ind + 1 :]))
    else:
        # Try last word as city name
        location = urllib.parse.quote(words[-1])
    url = f"https://api.openweathermap.org/data/2.5/weather?appid={config.WEATHER_API_KEY}&q={location}"

    try:
        js = _http.get(url, timeout=10).json()
    except requests.RequestException:
        return " Could not fetch weather data. Please check your connection."

    if isinstance(js.get("cod"), str) and js["cod"] == "404":
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


def handle_joke(text: str) -> str:
    if "joke" in text.lower():
        return " " + pyjokes.get_joke()
    return ""


def handle_news(text: str) -> str:
    if "news" not in text:
        return ""

    if not config.NEWS_API_KEY:
        return " News API key not configured. Please set NEWS_API_KEY in .env"

    url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={config.NEWS_API_KEY}"

    try:
        response = _http.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return " Please check your connection"

    news = json.loads(response.text)

    for article in news.get("articles", []):
        title = article.get("title", "")
        description = article.get("description", "")
        if title:
            talk_async(str(title))
        if description:
            talk_async(str(description))
        time.sleep(2)

    return " News headlines delivered."


def handle_calculate(text: str) -> str:
    if "calculate" not in text:
        return ""

    if not config.WOLFRAM_APP_ID:
        return " WolframAlpha API key not configured. Please set WOLFRAM_APP_ID in .env"

    import wolframalpha

    client = wolframalpha.Client(config.WOLFRAM_APP_ID)
    ind = text.lower().split().index("calculate")
    query = " ".join(text.split()[ind + 1 :])
    try:
        res = client.query(query)
        answer = next(res.results).text
        return f" The answer is {answer}"
    except Exception:
        logger.error("WolframAlpha query failed", exc_info=True)
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
    query = " ".join(text.split()[ind + 1 :])
    try:
        res = client.query(query)
        answer = next(res.results).text
        return f" {answer}"
    except Exception:
        logger.error("WolframAlpha query failed", exc_info=True)
        return " I could not find that."
