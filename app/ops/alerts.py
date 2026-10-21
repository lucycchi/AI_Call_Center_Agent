"""Alerts to the author (R76): one HTTP post to ALERT_WEBHOOK_URL per alert, with a 5-second timeout, plus a row in
the alerts table. Alerts fire on 3 or more errors in 10 minutes (or over 20 percent of at least 10 caller messages),
any failed operations write, a failed nightly reset and daily spend passing $5 (app/ops/spend.py). Sending never
raises: an alert must not break the reply or the job that raised it."""

import json
import logging
import os
import threading
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta

from app.config import SETTINGS, real_now

log = logging.getLogger("meridian.alerts")
WINDOW = timedelta(minutes=10)
ERROR_COUNT = 3
ERROR_SHARE, MIN_MESSAGES = 0.20, 10


def post_json(url: str, payload: dict, timeout: float) -> None:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout):
        pass


class Alerts:
    def __init__(self, store, url: str | None = None, post: Callable = post_json,
                 clock: Callable[[], datetime] = real_now, timeout_s: float = SETTINGS.webhook_timeout_s):
        self.store, self.url, self.post, self.clock, self.timeout_s = store, url, post, clock, timeout_s
        self._sending = threading.local()  # a failed write while recording an alert must not alert again
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls, store) -> "Alerts":
        return cls(store, url=os.environ.get("ALERT_WEBHOOK_URL") or None)

    def send(self, kind: str, detail: str) -> None:
        if getattr(self._sending, "on", False):
            return
        self._sending.on = True
        try:
            log.warning("alert (%s): %s", kind, detail)
            try:
                self.store.log_alert(kind, detail)
            except Exception as error:
                log.error("alert not recorded: %s", error)
            if self.url:
                try:
                    self.post(self.url, {"kind": kind, "detail": detail}, self.timeout_s)
                except Exception as error:
                    log.error("alert webhook failed: %s", error)
        finally:
            self._sending.on = False

    def watch(self, store) -> None:
        """Every failed write to this operations store sends a write-failure alert."""
        store.on_write_failure = lambda error: self.send("write failure", f"operations write failed: {error}")

    def check_errors(self) -> None:
        """Called after each message: one error alert per burst, at most one every ten minutes."""
        try:
            with self._lock:
                now = self.clock()
                since = (now - WINDOW).isoformat(timespec="seconds")
                count = self.store.read("select count(*) as n from events where kind = 'error' and created_at >= ?",
                                        (since,))[0]["n"]
                sent = self.store.read("select count(*) as n from messages where role = 'caller' and created_at >= ?",
                                       (since,))[0]["n"]
                burst = count >= ERROR_COUNT or (sent >= MIN_MESSAGES and count / sent > ERROR_SHARE)
                if not burst or self.store.read("select 1 from alerts where kind = 'errors' and sent_at >= ?",
                                                (since,)):
                    return
                self.send("errors", f"{count} errors in {sent} messages over the last 10 minutes")
        except Exception as error:
            log.error("error check failed: %s", error)
