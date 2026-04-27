"""
Google Calendar sync with upsert logic.
Event identity is stored as an extendedProperty so it survives any
external edits to the event title or time.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from core.models import Shift

logger = logging.getLogger(__name__)

# extendedProperty key used for stable identification
_ID_KEY = "dienstplan_sync_id"


def list_calendars(creds: Credentials) -> list[dict]:
    """Return [{id, summary}, …] for all writable calendars."""
    service = build("calendar", "v3", credentials=creds)
    result = service.calendarList().list().execute()
    calendars = []
    for item in result.get("items", []):
        if item.get("accessRole") in ("owner", "writer"):
            calendars.append({"id": item["id"], "summary": item.get("summary", item["id"])})
    return calendars


def sync_shifts(
    creds: Credentials,
    calendar_id: str,
    shifts: list[Shift],
    log: Callable[[str], None],
) -> dict[str, int]:
    """
    Upsert all shifts into the given Google Calendar.
    Returns {"created": n, "updated": n, "skipped": n}.
    """
    service = build("calendar", "v3", credentials=creds)
    stats = {"created": 0, "updated": 0, "skipped": 0}

    for i, shift in enumerate(shifts):
        try:
            _upsert_shift(service, calendar_id, shift, log, stats)
        except HttpError as e:
            # 429 = quota exceeded – back off and retry once
            if e.resp.status == 429:
                log(f"Google API Rate-Limit – warte 10 s…", "WARN")
                time.sleep(10)
                try:
                    _upsert_shift(service, calendar_id, shift, log, stats)
                    continue
                except HttpError:
                    pass
            log(f"[Fehler] {shift}: {e}", "ERROR")
            logger.error("HttpError bei %s: %s", shift, e)
        # Throttle: max ~6 writes/sec to stay within Google free quota
        if i % 5 == 4:
            time.sleep(0.2)

    log(
        f"Sync abgeschlossen – Neu: {stats['created']}, "
        f"Aktualisiert: {stats['updated']}, Unverändert: {stats['skipped']}"
    )
    return stats


def _upsert_shift(service, calendar_id: str, shift: Shift, log, stats: dict) -> None:
    shift_id = shift.event_id
    existing = _find_event(service, calendar_id, shift_id)

    body = _build_event_body(shift)

    if existing:
        if _event_unchanged(existing, body):
            stats["skipped"] += 1
            return
        service.events().update(
            calendarId=calendar_id,
            eventId=existing["id"],
            body=body,
        ).execute()
        stats["updated"] += 1
        log(f"Aktualisiert: {shift}")
    else:
        service.events().insert(calendarId=calendar_id, body=body).execute()
        stats["created"] += 1
        log(f"Erstellt: {shift}")


def _find_event(service, calendar_id: str, shift_id: str) -> Optional[dict]:
    """Search by extendedProperty for existing event."""
    result = service.events().list(
        calendarId=calendar_id,
        privateExtendedProperty=f"{_ID_KEY}={shift_id}",
        maxResults=1,
        singleEvents=True,
    ).execute()
    items = result.get("items", [])
    return items[0] if items else None


_TZ = ZoneInfo("Europe/Berlin")


def _build_event_body(shift: Shift) -> dict:
    start_dt = datetime.fromisoformat(f"{shift.date}T{shift.start}:00").replace(tzinfo=_TZ)
    end_dt = datetime.fromisoformat(f"{shift.date}T{shift.end}:00").replace(tzinfo=_TZ)

    # Handle overnight shifts
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return {
        "summary": shift.summary,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Berlin"},
        "extendedProperties": {
            "private": {_ID_KEY: shift.event_id}
        },
        "reminders": {"useDefault": False},
    }


def _event_unchanged(existing: dict, new_body: dict) -> bool:
    """Normalize both timestamps to UTC before comparing to avoid tz-offset mismatches."""
    try:
        def _to_utc(dt_str: str) -> datetime:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_TZ)
            return dt.astimezone(timezone.utc)

        return (
            existing.get("summary") == new_body.get("summary")
            and _to_utc(existing["start"]["dateTime"]) == _to_utc(new_body["start"]["dateTime"])
            and _to_utc(existing["end"]["dateTime"]) == _to_utc(new_body["end"]["dateTime"])
        )
    except (KeyError, TypeError, ValueError):
        return False
