from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import config
import database
import utils
from log import logger
from speech import rec_audio, talk


def handle_email(text: str) -> str:
    has_email_keyword = any(kw in text for kw in ("email", "gmail", "mail"))
    is_computer = "computer" in text

    if not has_email_keyword:
        return ""

    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        return " Email credentials not configured. Please set GMAIL_USER and GMAIL_APP_PASSWORD in .env"

    try:
        talk("What should I say?")
        content = rec_audio(timeout=15)
        if not content:
            return " I didn't catch that."

        if is_computer:
            to = config.GMAIL_USER
        else:
            talk("Whom should I send it to?")
            to = rec_audio(timeout=15)
            if not to:
                return " I didn't catch the recipient."

        utils.send_email(to, content)
        return " Email has been sent!"
    except Exception:
        logger.error("Email send failed", exc_info=True)
        return " I am not able to send this email"


def handle_make_note(text: str) -> str:
    if "make a note" not in text:
        return ""
    talk("What would you like me to write down?")
    note_text = rec_audio(timeout=15)
    if note_text:
        utils.note(note_text)
        database.save_note(title="", content=note_text)
        return " I have made a note of that."
    return " I didn't catch that."


def handle_send_message(text: str) -> str:
    if "send message" not in text:
        return ""

    if not all(
        [config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN, config.TWILIO_FROM_NUMBER, config.TWILIO_TO_NUMBER]
    ):
        return " Twilio credentials not configured. Please set them in .env"

    from twilio.rest import Client

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    talk("What should I send?")
    body = rec_audio(timeout=15)
    if not body:
        return " I didn't catch that."

    message = client.messages.create(
        body=body,
        from_=config.TWILIO_FROM_NUMBER,
        to=config.TWILIO_TO_NUMBER,
    )
    logger.debug(f"Twilio message SID: {message.sid}")
    return " Message sent successfully"


def handle_google_calendar(text: str) -> str:
    if "calendar" not in text.lower():
        return ""

    try:
        service = _get_calendar_service()
        _calendar_events(10, service)
    except Exception:
        logger.error("Google Calendar error", exc_info=True)
        return " Could not connect to Google Calendar. Please check your credentials and connection."
    return ""


def _get_calendar_service() -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

    token_path = Path.home() / ".hollali" / "token.json"
    legacy_token_path = Path.home() / ".hollali" / "token.pickle"
    creds = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_path.read_text()))
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read token.json: {e}")

    if creds is None and legacy_token_path.exists():
        # One-time migration from the insecure pickle format.
        try:
            import pickle

            with legacy_token_path.open("rb") as token:
                creds = pickle.load(token)
            token_path.write_text(creds.to_json())
            legacy_token_path.unlink()
            logger.info("Migrated Google Calendar token from pickle to token.json")
        except Exception as e:
            logger.error(f"Failed to migrate legacy pickle token: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_path = Path(config.GOOGLE_CALENDAR_CREDENTIALS_PATH)
            if not creds_path.exists():
                raise FileNotFoundError(f"Credentials file not found: {creds_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _calendar_events(num: int, service: Any) -> None:

    talk("Hey there! Good Day. Hope you are doing fine. These are the events to do today")
    now = datetime.datetime.utcnow().isoformat() + "Z"
    logger.debug(f"Getting the upcoming {num} events")
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
