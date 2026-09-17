"""Opening-hours helpers: never schedule a stop before it opens.

OSM hours arrive as an opaque ``opening_hours`` dict (``{"raw": ...}``) or a
test-friendly structured mapping. Anything unparseable is treated as unknown
and the caller falls back to the default window while flagging the activity
``hours_unverified``.
"""

import re
from datetime import date

from app import config

_OPEN_CLOSE_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")

_WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def parse_clock_time_to_minutes(clock_time: str) -> int:
    """Convert "HH:MM" to minutes since midnight."""
    hours, minutes = clock_time.strip().split(":")
    return int(hours) * 60 + int(minutes)


def parse_opening_window_for_date(place: dict, visit_date: date | None) -> tuple[int, int] | None:
    """Return (open_minutes, close_minutes) for the visit date, or None if unknown.

    Understands, in order: a structured per-weekday mapping, a "daily" entry,
    then the first HH:MM-HH:MM range inside a raw OSM string.
    """
    opening_hours = place.get("opening_hours") or {}
    if not isinstance(opening_hours, dict) or not opening_hours:
        return None

    weekday_name: str | None = None
    if visit_date is not None:
        weekday_name = _WEEKDAY_KEYS[visit_date.weekday()]

    candidates: list = []
    if weekday_name is not None and opening_hours.get(weekday_name):
        candidates.append(opening_hours[weekday_name])
    if opening_hours.get("daily"):
        candidates.append(opening_hours["daily"])
    if opening_hours.get("raw"):
        candidates.append(opening_hours["raw"])

    for candidate in candidates:
        window = _parse_window_candidate(candidate)
        if window is not None:
            return window
    return None


def _parse_window_candidate(candidate) -> tuple[int, int] | None:
    if isinstance(candidate, (list, tuple)):
        for entry in candidate:
            window = _parse_window_candidate(entry)
            if window is not None:
                return window
        return None
    if not isinstance(candidate, str):
        return None
    match = _OPEN_CLOSE_PATTERN.search(candidate)
    if not match:
        return None
    open_minutes = int(match.group(1)) * 60 + int(match.group(2))
    close_minutes = int(match.group(3)) * 60 + int(match.group(4))
    if close_minutes <= open_minutes:
        return None
    return (open_minutes, close_minutes)


def calculate_earliest_start_minutes(place: dict, visit_date: date | None) -> int | None:
    """Published opening time in minutes, or None when hours are unknown."""
    window = parse_opening_window_for_date(place, visit_date)
    if window is None:
        return None
    return window[0]


def calculate_latest_end_minutes(place: dict, visit_date: date | None) -> int | None:
    """Published closing time in minutes, or None when hours are unknown."""
    window = parse_opening_window_for_date(place, visit_date)
    if window is None:
        return None
    return window[1]


def default_opening_window() -> tuple[int, int]:
    """Assumed 09:00-21:00 window used only with hours_unverified flagged."""
    return (config.DEFAULT_OPEN_HOUR * 60, config.DEFAULT_CLOSE_HOUR * 60)
