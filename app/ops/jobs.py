"""Background jobs (R74, D31): the nightly reset of the scheduling tables at 03:00 Austin time and the daily log purge.

The reset takes the reset gate exclusively, replaces every provided table from the read-only seed copy in one
transaction, empties agent_confirmations and records the run in the operations database, which it never touches
otherwise. A failed reset is retried once, then the author is alerted and the Staff view shows it. If the app starts
and the last successful reset is before the most recent 03:00, the reset runs at once. Jobs use real time."""

import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, time, timedelta
from pathlib import Path

from app.config import AUSTIN, real_now

log = logging.getLogger("meridian.jobs")
RESET, PURGE = "nightly reset", "log purge"
RESET_AT = time(3, 0)
CONFIRMATIONS = (Path(__file__).resolve().parents[1] / "scheduling" / "confirmations.sql").read_text()
_running = threading.Lock()


def restore(sched_db: Path, seed_db: Path) -> None:
    """Every table in the seed copy, restored row for row in one transaction; agent_confirmations recreated empty."""
    db = sqlite3.connect(f"file:{Path(sched_db).resolve()}", uri=True, isolation_level=None)
    try:
        db.executescript(CONFIRMATIONS)
        db.execute("attach database ? as seed", (f"file:{Path(seed_db).resolve()}?mode=ro",))
        tables = [r[0] for r in db.execute("select name from seed.sqlite_master where type = 'table' "
                                           "and name not like 'sqlite_%'")]
        db.execute("begin immediate")
        try:
            for table in tables:
                db.execute(f'delete from main."{table}"')
                db.execute(f'insert into main."{table}" select * from seed."{table}"')
            db.execute("delete from main.agent_confirmations")
            # Auto-renew settings live only in the live copy (D54); the reset clears them (review finding I4).
            db.execute("drop table if exists main.membership_settings")
            db.execute("commit")
        except BaseException:
            db.execute("rollback")
            raise
    finally:
        db.close()


def nightly_reset(sched_db: Path, seed_db: Path, store, gate=None, alerts=None) -> str:
    """"ok", "retried" (succeeded on the second try), "failed" or "already running"."""
    if not _running.acquire(blocking=False):
        return "already running"
    try:
        run_id = store.start_job(RESET)
        result = "failed"
        for attempt in (1, 2):
            try:
                if gate is None:
                    restore(sched_db, seed_db)
                else:
                    with gate.exclusive():
                        restore(sched_db, seed_db)
                result = "ok" if attempt == 1 else "retried"
                break
            except Exception as error:
                log.error("nightly reset attempt %d failed: %s", attempt, error)
                last_error = error
        store.finish_job(run_id, result)
        if result == "failed" and alerts:
            alerts.send("reset", f"nightly reset failed twice: {last_error}")
        return result
    finally:
        _running.release()


def next_reset_time(now: datetime) -> datetime:
    """The next 03:00 Austin time strictly after now."""
    local = now.astimezone(AUSTIN)
    today = datetime.combine(local.date(), RESET_AT, tzinfo=AUSTIN)
    return today if local < today else datetime.combine(local.date() + timedelta(days=1), RESET_AT, tzinfo=AUSTIN)


def last_reset_time(now: datetime) -> datetime:
    """The most recent 03:00 Austin time at or before now."""
    local = now.astimezone(AUSTIN)
    today = datetime.combine(local.date(), RESET_AT, tzinfo=AUSTIN)
    return today if local >= today else datetime.combine(local.date() - timedelta(days=1), RESET_AT, tzinfo=AUSTIN)


def reset_if_missed(sched_db: Path, seed_db: Path, store, gate=None, alerts=None,
                    clock: Callable[[], datetime] = real_now) -> str | None:
    """At startup: run the reset if the last success started before the most recent 03:00; None if not needed."""
    done = [datetime.fromisoformat(r["started_at"]) for r in store.job_runs(RESET) if r["result"] in ("ok", "retried")]
    if done and max(done) >= last_reset_time(clock()):
        return None
    return nightly_reset(sched_db, seed_db, store, gate=gate, alerts=alerts)


def purge(store, older_than_days: int = 30, clock: Callable[[], datetime] = real_now) -> int:
    """Delete conversations older than the cutoff (flagged ones are kept); returns how many went."""
    run_id = store.start_job(PURGE)
    try:
        removed = store.purge_before((clock() - timedelta(days=older_than_days)).isoformat(timespec="seconds"))
    except Exception:
        store.finish_job(run_id, "failed")
        raise
    store.finish_job(run_id, "ok")
    return removed


class Scheduler:
    """A daemon thread that runs the reset at each 03:00 Austin time, then the purge."""

    def __init__(self, sched_db: Path, seed_db: Path, store, gate, alerts=None,
                 clock: Callable[[], datetime] = real_now):
        self.sched_db, self.seed_db, self.store, self.gate, self.alerts, self.clock = (
            sched_db, seed_db, store, gate, alerts, clock)
        self._stop = threading.Event()

    def start(self) -> "Scheduler":
        reset_if_missed(self.sched_db, self.seed_db, self.store, self.gate, self.alerts, self.clock)
        threading.Thread(target=self._loop, name="nightly-jobs", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(max(1.0, (next_reset_time(self.clock()) - self.clock()).total_seconds())):
            try:
                nightly_reset(self.sched_db, self.seed_db, self.store, self.gate, self.alerts)
                purge(self.store, clock=self.clock)
            except Exception as error:
                log.exception("nightly jobs failed: %s", error)
                if self.alerts:
                    self.alerts.send("reset", f"nightly jobs failed: {error}")
