"""
Generates a RFC-5545-compliant .ics file from a list of Shift objects.
The file can be opened directly in Apple Calendar (or any iCal-compatible app).
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Callable

from core.models import Shift


def generate_ical(
    shifts: List[Shift],
    output_path: Path,
    log: Callable[[str, str], None] | None = None,
) -> None:
    def _log(msg: str, level: str = "INFO") -> None:
        if log:
            log(msg, level)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DienstplanSync//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for shift in shifts:
        start_dt = _parse_dt(shift.date, shift.start)
        end_dt = _parse_dt(shift.date, shift.end)

        # Handle overnight shifts (e.g. 22:00–06:00)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        uid = f"{shift.event_id}@dienstplansync"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;TZID=Europe/Berlin:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=Europe/Berlin:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{shift.summary}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    # RFC 5545 mandates CRLF line endings
    output_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    _log(f"iCal-Datei erstellt: {output_path}", "OK")


def _parse_dt(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
