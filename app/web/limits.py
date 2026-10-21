"""Message limits (R62): 20 messages per 10 minutes and 100 per day for each visitor, counted both by the visitor
cookie and by the client address Fly.io supplies (so clearing the cookie does not reset them), and 60 messages a
minute across the site. Kept in memory: the app runs one worker process, and operations use real time.

Safety comes first (R34): the web layer counts each message here when it arrives, and a message over a limit is
answered with the limit message only when the safety check finds nothing in it. One that reports a danger still goes
to the agent with its limit set in TURN_LIMIT, and the agent's guard (turn_guard, asked after its safety check, as
the spending caps are) refuses everything but the safety reply."""

import contextvars
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
                 site_per_minute: int = SETTINGS.site_messages_per_minute, safety_per_day: int = 3):
        self.clock, self.per_10_min, self.per_day, self.site_per_minute = clock, per_10_min, per_day, site_per_minute
        # Over the limits, an emergency still reaches the agent (safety first), but only a few a day per visitor and
        # per address open a ticket, so an over-limit visitor cannot flood staff with priority tickets. There is no
        # site-wide stop: a flood could use one up and leave a real caller without a ticket (security review).
        self.safety_per_day = safety_per_day
        self._safety_day, self._safety = None, {}
        self._lock = threading.Lock()
        self._recent: dict[str, deque] = {}  # key -> message times in the last 10 minutes
        self._day, self._today = None, {}  # key -> messages today
        self._site: deque = deque()

    def allow_safety(self, visitor_id: str, address: str | None) -> bool:
        """An over-limit emergency may reach the agent and open a ticket: a few a day per visitor and per address.
        Counts it when allowed."""
        now = self.clock()
        keys = [f"visitor:{visitor_id}"] + ([f"address:{address}"] if address else [])
        with self._lock:
            if self._safety_day != now.date():
                self._safety_day, self._safety = now.date(), {}
            if any(self._safety.get(k, 0) >= self.safety_per_day for k in keys):
                return False
            for key in keys:
                self._safety[key] = self._safety.get(key, 0) + 1
            return True

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


# The limit this reply thread's message hit, or None; set by the web layer around each turn.
TURN_LIMIT: contextvars.ContextVar[str | None] = contextvars.ContextVar("turn_limit", default=None)


def turn_guard(spend=None):
    """The agent pipeline's guard: the message limit this turn hit, or else the spending cap that refuses it."""
    def guard(visitor_id: str) -> str | None:
        return TURN_LIMIT.get() or (spend.refusal(visitor_id) if spend is not None else None)
    return guard
