"""Turning what a caller says about when into a date and a window, read against the fixed "now" (R12, R50)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
          "december"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SPOKEN_WINDOWS = {("8", "12"): "08:00-12:00", ("12", "4"): "12:00-16:00", ("1", "5"): "13:00-17:00", ("4", "7"): "16:00-19:00"}


@dataclass(frozen=True)
class DateRequest:
    date: date | None = None   # None: as soon as possible
    part: str | None = None    # morning or afternoon
    window: str | None = None  # an exact window


def _calendar_date(said: str, today: date) -> date | None:
    """"October 22", "Oct 22", "22 October", "the 22nd" (this month, or next if passed) and "10/22"."""
    month_names = "|".join(m[:3] + rf"(?:{m[3:]})?" for m in MONTHS)
    named = re.search(rf"\b({month_names})\.? (\d{{1,2}})(?:st|nd|rd|th)?\b", said) or \
        re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({month_names})\b", said)
    if named:
        first, second = named.groups()
        month_word, day_text = (first, second) if not first.isdigit() else (second, first)
        month = next(n for n, m in enumerate(MONTHS, 1) if month_word.startswith(m[:3]))
        return _future(today, month, int(day_text))
    slashed = re.search(r"\b(\d{1,2})/(\d{1,2})\b", said)
    if slashed:
        return _future(today, int(slashed.group(1)), int(slashed.group(2)))
    ordinal = re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", said)
    if ordinal:
        day_number = int(ordinal.group(1))
        candidate = _future(today, today.month, day_number)
        if candidate and candidate < today:
            candidate = _future(today, today.month % 12 + 1, day_number)
        return candidate
    return None


def _future(today: date, month: int, day_number: int) -> date | None:
    """That month and day this year, or next year if it has passed; None if no such date."""
    try:
        candidate = date(today.year, month, day_number)
    except ValueError:
        return None
    if candidate < today and month != today.month:
        candidate = candidate.replace(year=today.year + 1)
    return candidate


def parse_request(text: str, now: datetime) -> DateRequest | None:
    said = text.lower()
    today = now.date()
    day = None
    if re.search(r"\btoday\b", said):
        day = today
    elif re.search(r"\btomorrow\b", said):
        day = today + timedelta(days=1)
    elif (calendar := _calendar_date(said, today)) is not None:
        day = calendar
    else:
        match = re.search(rf"\b(this |next )?({'|'.join(WEEKDAYS)})\b", said)
        if match:
            ahead = (WEEKDAYS.index(match.group(2)) - today.weekday()) % 7
            if ahead == 0 and match.group(1) == "next ":
                ahead = 7
            day = today + timedelta(days=ahead)
    spoken = re.search(r"\b(8|12|1|4) ?(?:to|-|–) ?(12|4|5|7)\b", said)
    window = SPOKEN_WINDOWS.get(spoken.groups()) if spoken else None
    if window is None and re.search(r"\bevening\b|\bafter work\b", said):
        window = "16:00-19:00"  # the only evening window
    part = None
    if window is None:
        part = "morning" if re.search(r"\bmorning\b|\bfirst thing\b", said) else "afternoon" if "afternoon" in said else None
    soon = re.search(r"\bas soon as possible\b|\bsoonest\b|\basap\b", said)
    if day is None and window is None and part is None and not soon:
        return None
    return DateRequest(day, part, window)
