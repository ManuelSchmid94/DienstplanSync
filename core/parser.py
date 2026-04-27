"""
PDF parser for OSK Dienstplan Timeoffice "Ausführlicher Stundennachweis".

The PDF is image-based (no extractable text). Strategy:
  1. Render at 300 DPI via pdf2image (needs poppler)
  2. Crop to the shift-info column only (removes day-number and statistics columns
     whose table borders corrupt OCR of the first shift per day)
  3. Run Tesseract OCR (German) on the cleaned strip
  4. Parse the resulting text line by line with a day-tracking state machine
"""
import re
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image

from core.models import Shift

logger = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Time range: "08:00 - 12:00" or "08:00 – 12:00"
_TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})")

# Free day: "0: 00:00 - 00:00" or "OSK: 00:00" or "0:00:00"
# Character class includes ] (close-bracket) since OCR renders cell borders as |__]0:…
_FREE_RE = re.compile(r"(?:^|[|_\[\]\s])0\s*[:\.]?\s*00:00\s*[-–]\s*00:00|OSK\s*:\s*00:00", re.IGNORECASE)

# Weekday at start of line (possibly after some noise characters)
_WD_RE = re.compile(r"^\s*[|_\[\(\s]{0,5}(Mo|Di|Mi|Do|Fr|Sa|So)\b", re.IGNORECASE)

# Ist (hours) value at the end of a line: "7,70" or "10,00" or "6,75"
_IST_RE = re.compile(r"\b(\d{1,2}[,.]?\d{0,2})\s*[|,]?\s*$")

# Document generation date in header: "26.04.2026"
_DOC_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

_WEEKDAY_NAMES = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}

# Known shift type → standard start time (ground truth from Dienstplan)
_TYPE_START_LOOKUP: dict[str, str] = {
    "FTD": "08:00",
    "PA":  "08:00",
    "S":   "13:30",
    "STD": "16:00",
    "F":   "06:15",
}


# ── Public entry point ─────────────────────────────────────────────────────────

def parse_pdf(pdf_path: Path, year_hint: Optional[int] = None) -> list[Shift]:
    img = _render(pdf_path)
    year, month = _detect_period(img, year_hint)
    if not year or not month:
        logger.warning("Konnte Zeitraum nicht bestimmen – keine Schichten.")
        return []

    logger.info("Zeitraum erkannt: %d-%02d", year, month)

    text = _ocr_shift_column(img)
    logger.debug("OCR-Text (erste 300 Z.):\n%s", text[:300])

    shifts = _parse(text, year, month)
    shifts = _merge_sub_shifts(shifts)
    shifts = _apply_start_lookup(shifts)
    shifts.sort(key=lambda s: (s.date, s.start))
    logger.info("Geparste Schichten: %d", len(shifts))
    return shifts


# ── Rendering ─────────────────────────────────────────────────────────────────

def _render(pdf_path: Path) -> Image.Image:
    import sys, os
    from pdf2image import convert_from_path
    kwargs: dict = {}
    if getattr(sys, "frozen", False):
        kwargs["poppler_path"] = os.path.join(sys._MEIPASS, "bin")
    images = convert_from_path(str(pdf_path), dpi=300, **kwargs)
    return images[0]


# ── Period detection ───────────────────────────────────────────────────────────

def _detect_period(img: Image.Image, year_hint: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """
    Find year+month for the schedule.
    Primary: read the header area OCR and look for dates.
    Fallback: document generation date → next month.
    """
    w, h = img.size
    header = img.crop((0, 0, w, int(h * 0.12)))
    header_text = pytesseract.image_to_string(header, lang="deu", config="--psm 6")

    # Look for "Zeitraum: 01.05.2026" or any "DD.MM.YYYY" with a later YYYY-MM-DD
    dates = _DOC_DATE_RE.findall(header_text)
    # dates is list of (day, month, year) tuples
    if dates:
        # Try to find the schedule period: prefer the LATEST date that isn't the gen date
        # Usually we see the gen date once and the period start once
        parsed = [(int(y), int(m)) for d, m, y in dates]
        # If multiple: the period is typically the one with year that matches year_hint
        # or the largest year-month tuple
        parsed_sorted = sorted(set(parsed))
        if len(parsed_sorted) >= 2:
            # Use the second-latest as the schedule month
            return parsed_sorted[-1]
        if len(parsed_sorted) == 1:
            ym = parsed_sorted[0]
            # This might be just the gen date; compute next month
            return _next_month(*ym)

    # Fallback: year_hint with no month → can't determine
    logger.warning("Keine Datumsangabe in Header – verwende Dokumentdatum → nächsten Monat.")
    if dates:
        day, month, year = int(dates[0][0]), int(dates[0][1]), int(dates[0][2])
        return _next_month(year, month)

    if year_hint:
        return year_hint, None
    return None, None


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


# ── OCR ───────────────────────────────────────────────────────────────────────

def _ocr_shift_column(img: Image.Image) -> str:
    """
    Crop to the shift-info column (strip left day-number column and right
    statistics columns), then OCR. This removes table borders that corrupt
    OCR of the first shift line in each row.
    """
    w, h = img.size
    # At 300 DPI on an A4 page: left strip ~200px covers "Tage"+"gA" columns.
    # Right strip ~900px covers the statistics/hours columns.
    left = 200
    right = w - 900
    top = int(h * 0.10)    # skip logo/header
    bottom = int(h * 0.80) # skip footer legend

    strip = img.crop((left, top, right, bottom))
    text = pytesseract.image_to_string(strip, lang="deu", config="--psm 6")
    return text


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse(text: str, year: int, month: int) -> list[Shift]:
    n_days = _days_in_month(year, month)
    lines = text.splitlines()

    # State
    current_day = 0          # 1-based day of month, 0 = before first day
    current_shifts: list[Shift] = []
    result: list[Shift] = []

    def commit():
        result.extend(current_shifts)

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        is_free = bool(_FREE_RE.search(line))
        tr = _TIME_RANGE_RE.search(line)
        wd_m = _WD_RE.match(line)
        wd = wd_m.group(1).lower() if wd_m else None

        # ── Detect new day boundary ────────────────────────────────────────────
        new_day_detected = False
        new_day_num: Optional[int] = None

        if is_free:
            new_day_detected = True
            if wd:
                new_day_num = _resolve_day(year, month, wd, current_day)
            else:
                new_day_num = current_day + 1

        elif wd and tr:
            new_day_detected = True
            new_day_num = _resolve_day(year, month, wd, current_day)

        elif wd and not tr:
            # Weekday without time range → noise or header label (e.g. column header)
            # Treat as a day boundary only if current_day < n_days
            if current_day > 0 and current_day < n_days:
                new_day_detected = True
                new_day_num = _resolve_day(year, month, wd, current_day)

        elif tr and not wd:
            # Check if it has an Ist value → likely a new day first shift with garbled weekday
            ist_m = _IST_RE.search(line)
            if ist_m and current_day > 0:
                # Check if the number looks like hours (1-24)
                try:
                    val = float(ist_m.group(1).replace(",", "."))
                    if 0.5 <= val <= 24:
                        new_day_detected = True
                        new_day_num = current_day + 1
                except ValueError:
                    pass

        elif not tr and current_day > 0:
            # No time range, no weekday: might be a garbled day-start line
            # (contains noise characters, short, not a continuation shift)
            noise_chars = len(re.findall(r'[|_\[\]\\]', line))
            alpha_chars = len(re.findall(r'[A-Za-zÄÖÜäöüß]', line))
            is_noise_line = noise_chars >= 1 or (alpha_chars < 5 and len(line) < 30)
            if is_noise_line and not _is_footer(line):
                new_day_detected = True
                new_day_num = current_day + 1

        # ── Commit previous day and advance ────────────────────────────────────
        if new_day_detected and new_day_num is not None:
            # When a weekday jump skips a day (gap > 1) and the current day holds
            # shifts of the same type as the upcoming shift, those shifts belong to
            # the day immediately before the new weekday-confirmed day, not to the
            # noise-advanced current_day (which is often an invisible free day).
            gap = new_day_num - current_day
            if not is_free and tr and gap > 1 and current_shifts:
                new_type = _extract_type(line)
                if new_type:
                    same_type = [s for s in current_shifts if s.type == new_type]
                    other = [s for s in current_shifts if s.type != new_type]
                    if same_type:
                        prev_day = min(new_day_num - 1, n_days)
                        prev_date = f"{year:04d}-{month:02d}-{prev_day:02d}"
                        result.extend(other)
                        result.extend(
                            Shift(date=prev_date, start=s.start, end=s.end, type=s.type)
                            for s in same_type
                        )
                        logger.debug(
                            "Weekday jump %d→%d: moved %d %s shift(s) to day %d",
                            current_day, new_day_num, len(same_type), new_type, prev_day,
                        )
                        current_shifts = []
                    else:
                        commit()
                        current_shifts = []
                else:
                    commit()
                    current_shifts = []
            else:
                commit()
                current_shifts = []

            current_day = min(new_day_num, n_days)

            if not is_free and tr:
                start, end = _norm(tr.group(1)), _norm(tr.group(2))
                if not (start == "00:00" and end == "00:00"):
                    date_str = f"{year:04d}-{month:02d}-{current_day:02d}"
                    shift_type = _extract_type(line)
                    current_shifts.append(Shift(date=date_str, start=start, end=end, type=shift_type))

        elif tr and current_day > 0:
            # Continuation shift.
            # Detect OCR artifact: the PDF sometimes re-renders a previous day's
            # shift row text into the current day. Symptoms:
            #   - current day already has shifts (current_shifts non-empty)
            #   - the incoming type is NOT yet represented in current_shifts
            #     (it's not a legitimate second sub-row of the same shift type)
            #   - the (start, end, type) exactly matches the last committed shift
            start, end = _norm(tr.group(1)), _norm(tr.group(2))
            if not (start == "00:00" and end == "00:00"):
                date_str = f"{year:04d}-{month:02d}-{current_day:02d}"
                shift_type = _extract_type(line)
                type_already_on_day = any(s.type == shift_type for s in current_shifts)
                is_dup = (
                    bool(current_shifts)           # day already has shifts
                    and not type_already_on_day    # but not of this type yet
                    and bool(result)
                    and result[-1].start == start
                    and result[-1].end == end
                    and result[-1].type == shift_type
                )
                if is_dup:
                    logger.debug("Skipping OCR duplicate: %s %s-%s [%s]", date_str, start, end, shift_type)
                else:
                    current_shifts.append(Shift(date=date_str, start=start, end=end, type=shift_type))

    commit()

    # Deduplicate (same date + start)
    seen: set[str] = set()
    unique: list[Shift] = []
    for s in result:
        key = s.event_id
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_day(year: int, month: int, wd_str: str, after_day: int) -> int:
    """Find the first day in the month >= after_day+1 that matches the weekday."""
    target_wd = _WEEKDAY_NAMES.get(wd_str.lower())
    if target_wd is None:
        return after_day + 1
    for day in range(after_day + 1, 32):
        try:
            if date(year, month, day).weekday() == target_wd:
                return day
        except ValueError:
            break
    return after_day + 1


def _extract_type(line: str) -> Optional[str]:
    """Extract shift type code from a line like 'S: 13:30 - 17:00 ...'"""
    m = re.search(r"\b([A-Z][A-Z0-9]{0,4}):\s*\d{1,2}:\d{2}", line)
    if m:
        code = m.group(1)
        if code not in ("EK",):  # filter false positives
            return code
    return None


def _norm(t: str) -> str:
    h, m = t.split(":")
    return f"{int(h):02d}:{int(m):02d}"


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, 12, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _is_footer(line: str) -> bool:
    return any(kw in line for kw in ("Summe", "Tage>", "TIMEOFFICE", "Mitarbeiter", "Anspruch", "Ampel"))


def _merge_sub_shifts(shifts: list[Shift]) -> list[Shift]:
    """
    Merge consecutive same-type sub-shifts on the same day into one event.
    The PDF renders each shift as two sub-rows (before/after break); both
    represent a single calendar event. Take earliest start, latest end.
    """
    if not shifts:
        return shifts

    shifts = sorted(shifts, key=lambda s: (s.date, s.start))
    merged: list[Shift] = []
    i = 0
    while i < len(shifts):
        cur = shifts[i]
        j = i + 1
        while (
            j < len(shifts)
            and shifts[j].date == cur.date
            and shifts[j].type == cur.type
            and cur.type is not None
        ):
            cur = Shift(
                date=cur.date,
                start=min(cur.start, shifts[j].start),
                end=max(cur.end, shifts[j].end),
                type=cur.type,
            )
            j += 1
        merged.append(cur)
        i = j
    return merged


def _apply_start_lookup(shifts: list[Shift]) -> list[Shift]:
    """
    When OCR misses the first sub-row of a known shift type, the captured
    start time belongs to the second sub-row (after-break). Replace it with
    the known standard start time so the calendar event covers the full span.
    """
    result: list[Shift] = []
    for s in shifts:
        expected = _TYPE_START_LOOKUP.get(s.type) if s.type else None
        if expected and s.start != expected:
            logger.debug(
                "Lookup: %s %s → Startzeit %s→%s", s.date, s.type, s.start, expected
            )
            s = Shift(date=s.date, start=expected, end=s.end, type=s.type)
        result.append(s)
    return result
