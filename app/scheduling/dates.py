"""Turning what a caller says about when into a date and a window, read against the fixed "now" (R12, R50)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SPOKEN_WINDOWS = {("8", "12"): "08:00-12:00", ("12", "4"): "12:00-16:00", ("1", "5"): "13:00-17:00", ("4", "7"): "16:00-19:00"}


@dataclass(frozen=True)
class DateRequest:
    date: date | None = None   # None: as soon as possible
    part: str | None = None    # morning or afternoon
    window: str | None = None  # an exact window


def parse_request(text: str, now: datetime) -> DateRequest | None:
    said = text.lower()
    today = now.date()
    day = None
    if re.search(r"\btoday\b", said):
        day = today
    elif re.search(r"\btomorrow\b", said):
        day = today + timedelta(days=1)
    else:
        match = re.search(rf"\b(this |next )?({'|'.join(WEEKDAYS)})\b", said)
        if match:
            ahead = (WEEKDAYS.index(match.group(2)) - today.weekday()) % 7
            if ahead == 0 and match.group(1) == "next ":
                ahead = 7
            day = today + timedelta(days=ahead)
    spoken = re.search(r"\b(8|12|1|4) to (12|4|5|7)\b", said)
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
