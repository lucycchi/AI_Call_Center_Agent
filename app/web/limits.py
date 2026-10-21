"""Message limits (R62): 20 messages per 10 minutes and 100 per day for each visitor, counted both by the visitor
cookie and by the client address Fly.io supplies (so clearing the cookie does not reset them), and 60 messages a
minute across the site. Kept in memory: the app runs one worker process, and operations use real time."""

import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta

from app.config import SETTINGS, real_now
from app.handoff.flow import OFFICE_HOURS

LIMIT_MESSAGE = ("You've sent a lot of messages in a short time, so I can't reply to more right now. Please try again "
                 f"later, or phone our office ({OFFICE_HOURS}) and a team member can help you directly.")
TEN_MINUTES, ONE_MINUTE = timedelta(minutes=10), timedelta(minutes=1)


class Limits:
    def __init__(self, clock: Callable[[], datetime] = real_now, per_10_min: int = SETTINGS.visitor_messages_per_10_min,
                 per_day: int = SETTINGS.visitor_messages_per_day,
                 site_per_minute: int = SETTINGS.site_messages_per_minute):
        self.clock, self.per_10_min, self.per_day, self.site_per_minute = clock, per_10_min, per_day, site_per_minute
        self._lock = threading.Lock()
        self._recent: dict[str, deque] = {}  # key -> message times in the last 10 minutes
        self._day, self._today = None, {}  # key -> messages today
        self._site: deque = deque()

    def allow(self, visitor_id: str, address: str | None) -> str | None:
        """Count the message and return None, or return which limit it hit (and do not count it)."""
        now = self.clock()
        keys = [f"visitor:{visitor_id}"] + ([f"address:{address}"] if address else [])
        with self._lock:
            if self._day != now.date():
                self._day, self._today = now.date(), {}
            while self._site and self._site[0] <= now - ONE_MINUTE:
                self._site.popleft()
            recent = {key: self._trim(key, now) for key in keys}
            if len(self._site) >= self.site_per_minute:
                return "site per minute"
            if any(len(times) >= self.per_10_min for times in recent.values()):
                return "visitor per 10 minutes"
            if any(self._today.get(key, 0) >= self.per_day for key in keys):
                return "visitor per day"
            self._site.append(now)
            for key in keys:
                recent[key].append(now)
                self._today[key] = self._today.get(key, 0) + 1
            return None

    def _trim(self, key: str, now: datetime) -> deque:
        times = self._recent.setdefault(key, deque())
        while times and times[0] <= now - TEN_MINUTES:
            times.popleft()
        return times
