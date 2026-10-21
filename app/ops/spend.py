"""Spending budgets (R61, D30): live AI spend, recorded per model call and summed per pool and Austin day.

Pools: "public" (each ordinary visitor about $0.40 a day), "site" (all public traffic together, $10 a day) and
"reviewer" (visitors who used the reviewer link, a $3-a-day reserve that public traffic cannot touch). Days roll
over at Austin midnight in real time (real_now), never the fixed customer-facing "now". Crossing $5.00 of live spend
in a day records one spend alert for that day. Only the web layer reports to it (through the model-call sink), so
the evaluation harness, which sets its own run-budget sink, never touches these pools.

The agent's pipeline asks refusal(visitor) after its safety check, so an over-budget visitor reporting gas still gets
the safety reply; a refusal becomes the pipeline's plain limit handoff. Within a turn, each model call is checked
again before it is made (Recorder.before), so a turn that crosses the cap makes no further calls."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from app.config import AUSTIN, SETTINGS, real_now

log = logging.getLogger("meridian.spend")
DOLLAR = 1_000_000


class Spend:
    def __init__(self, store, clock: Callable[[], datetime] = real_now,
                 per_visitor_usd: float = SETTINGS.per_visitor_daily_usd, site_usd: float = SETTINGS.site_daily_usd,
                 reviewer_usd: float = SETTINGS.reviewer_daily_usd, alert_usd: float = SETTINGS.spend_alert_usd,
                 notify: Callable[[str], None] | None = None):
        self.store, self.clock, self.notify = store, clock, notify
        self.per_visitor, self.site = round(per_visitor_usd * DOLLAR), round(site_usd * DOLLAR)
        self.reviewer, self.alert = round(reviewer_usd * DOLLAR), round(alert_usd * DOLLAR)
        self._lock = threading.Lock()

    def day(self) -> str:
        """Today's Austin calendar day in real time."""
        return self.clock().astimezone(AUSTIN).date().isoformat()

    def is_reviewer(self, visitor_id: str) -> bool:
        return self.store.visitor_kind(visitor_id) == "reviewer"

    def refusal(self, visitor_id: str) -> str | None:
        """Which budget refuses this visitor's next message, or None. Fails closed if the store cannot be read."""
        try:
            day = self.day()
            if self.is_reviewer(visitor_id):
                return "reviewer reserve" if self.store.spend_microdollars(day, "reviewer") >= self.reviewer else None
            if self.store.spend_microdollars(day, "public", visitor_id) >= self.per_visitor:
                return "visitor daily budget"
            if self.store.spend_microdollars(day, "public") >= self.site:
                return "site daily budget"
            return None
        except Exception as error:
            log.error("spend check failed, refusing the message: %s", error)
            return "spend unavailable"

    def allow(self, visitor_id: str) -> bool:
        return self.refusal(visitor_id) is None

    def record(self, visitor_id: str, microdollars: int) -> None:
        """Count one model call. Never raises: it runs inside the agent's model call."""
        try:
            with self._lock:
                day = self.day()
                before = self.store.spend_microdollars(day)
                pool = "reviewer" if self.is_reviewer(visitor_id) else "public"
                self.store.add_spend(visitor_id, pool, day, int(microdollars))
                if before < self.alert <= before + microdollars:
                    self._alert_once(day)
        except Exception as error:
            log.error("spend record failed: %s", error)

    def _alert_once(self, day: str) -> None:
        detail = f"daily spend passed ${self.alert / DOLLAR:.2f} on {day}"
        if any(alert["detail"] == detail for alert in self.store.alerts("spend")):
            return
        self.store.log_alert("spend", detail)
        log.warning(detail)
        if self.notify:
            self.notify(detail)

    def recorder(self, visitor_id: str) -> "Recorder":
        """A model-call sink (app.core.model_log.SINK) that counts each call against this visitor, with a before()
        check the web layer sets as the pre-call check (app.core.model_log.PRE_CALL)."""
        return Recorder(self, visitor_id)

    def totals(self, visitor_id: str | None = None) -> dict:
        """Today's spend in dollars: this visitor's, all public traffic (the site pool) and the reviewer reserve."""
        day = self.day()
        public = self.store.spend_microdollars(day, "public") / DOLLAR
        return {"visitor": self.store.spend_microdollars(day, None, visitor_id) / DOLLAR if visitor_id else 0,
                "public": public, "reviewer": self.store.spend_microdollars(day, "reviewer") / DOLLAR, "site": public}


class Recorder:
    """One visitor's model-call sink for one turn."""

    def __init__(self, spend: Spend, visitor_id: str):
        self.spend, self.visitor_id = spend, visitor_id

    def __call__(self, purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars):
        self.spend.record(self.visitor_id, microdollars)

    def before(self) -> None:
        """Raise CallRefused if this visitor's budget is already spent; the call is then never made."""
        from app.core.model_log import CallRefused
        reason = self.spend.refusal(self.visitor_id)
        if reason:
            raise CallRefused(reason)
