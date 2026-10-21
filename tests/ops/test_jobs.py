import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.ops.jobs as jobs
from app.config import AUSTIN
from app.ops.alerts import Alerts
from app.ops.gate import ResetGate
from app.ops.metrics import RESET_FAILED, live_numbers
from app.ops.store import OpsStore
from app.web.main import create_app

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
SECRET = "test-only-secret"


class Clock:
    def __init__(self, when: datetime):
        self.now = when

    def __call__(self):
        return self.now


class Webhook:
    """A fake alert webhook: records each post."""

    def __init__(self):
        self.posts = []

    def __call__(self, url, payload, timeout):
        self.posts.append((url, payload, timeout))


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 20, 14, 0, tzinfo=AUSTIN))


@pytest.fixture
def store(tmp_path, clock):
    return OpsStore(tmp_path / "ops.sqlite", clock=clock)


@pytest.fixture
def sched(tmp_path):
    copy = tmp_path / "scheduling.sqlite"
    shutil.copy(SEED, copy)
    return copy


@pytest.fixture
def webhook():
    return Webhook()


@pytest.fixture
def alerts(store, webhook, clock):
    return Alerts(store, url="https://alerts.example/hook", post=webhook, clock=clock)


def dump(path: Path) -> dict:
    db = sqlite3.connect(path)
    try:
        tables = [r[0] for r in db.execute("select name from sqlite_master where type = 'table' "
                                           "and name != 'agent_confirmations' order by name")]
        return {t: sorted(db.execute(f"select * from {t}").fetchall(), key=repr) for t in tables}
    finally:
        db.close()


def book_on(path: Path) -> int:
    """A booking change as the agent makes it: a slot marked booked, an appointment row and its confirmation."""
    db = sqlite3.connect(path)
    with db:
        db.executescript((ROOT / "app" / "scheduling" / "confirmations.sql").read_text())
        slot = db.execute("select slot_id from appointment_slots where status = 'open' limit 1").fetchone()[0]
        db.execute("update appointment_slots set status = 'booked' where slot_id = ?", (slot,))
        columns = [r[1] for r in db.execute("pragma table_info(appointments)")]
        row = dict(zip(columns, db.execute("select * from appointments limit 1").fetchone()))
        row.update(appointment_id=999_999, slot_id=slot)
        db.execute(f"insert into appointments ({', '.join(row)}) values ({', '.join('?' * len(row))})",
                   tuple(row.values()))
        db.execute("insert into agent_confirmations values ('MHC-TEST1', '{}', '2026-10-20T14:00:00')")
        db.execute("delete from appointments where appointment_id = (select min(appointment_id) from appointments)")
    db.close()
    return slot


def confirmations(path: Path) -> int:
    db = sqlite3.connect(path)
    try:
        return db.execute("select count(*) from agent_confirmations").fetchone()[0]
    finally:
        db.close()


def slot_status(path: Path, slot_id: int) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("select status from appointment_slots where slot_id = ?", (slot_id,)).fetchone()[0]
    finally:
        db.close()


# -- Reset ---------------------------------------------------------------------------------------------------------
def test_the_nightly_reset_restores_the_seed_empties_confirmations_and_leaves_operations_alone(sched, store):
    store.open_conversation("v1", "c1")
    store.log_message("c1", "caller", "book me a plumber")
    before_ops = store.read("select count(*) as n from messages")[0]["n"]
    book_on(sched)
    assert dump(sched) != dump(SEED)

    assert jobs.nightly_reset(sched, SEED, store) == "ok"

    assert dump(sched) == dump(SEED)
    assert confirmations(sched) == 0
    runs = store.job_runs("nightly reset")
    assert [r["result"] for r in runs] == ["ok"] and runs[0]["finished_at"]
    assert store.read("select count(*) as n from messages")[0]["n"] == before_ops


def test_a_second_reset_while_one_is_running_returns_already_running(sched, store):
    gate = ResetGate()
    results = []
    with gate.shared():  # a message in progress: the first reset waits for it
        first = threading.Thread(target=lambda: results.append(jobs.nightly_reset(sched, SEED, store, gate=gate)))
        first.start()
        time.sleep(0.1)
        assert jobs.nightly_reset(sched, SEED, store, gate=gate) == "already running"
    first.join(5)
    assert results == ["ok"]


def test_the_next_reset_is_the_next_3_am_in_austin():
    assert jobs.next_reset_time(datetime(2026, 10, 20, 22, 0, tzinfo=AUSTIN)) == datetime(2026, 10, 21, 3, 0,
                                                                                          tzinfo=AUSTIN)
    assert jobs.next_reset_time(datetime(2026, 10, 20, 2, 0, tzinfo=AUSTIN)) == datetime(2026, 10, 20, 3, 0,
                                                                                         tzinfo=AUSTIN)
    assert jobs.next_reset_time(datetime(2026, 10, 20, 3, 0, tzinfo=AUSTIN)) == datetime(2026, 10, 21, 3, 0,
                                                                                         tzinfo=AUSTIN)


# -- Gate ----------------------------------------------------------------------------------------------------------
def test_a_message_that_starts_during_the_reset_waits_and_then_sees_the_restored_data(sched):
    gate = ResetGate()
    slot = book_on(sched)
    seen = []

    def message():
        with gate.shared():
            seen.append(slot_status(sched, slot))

    with gate.exclusive():
        reader = threading.Thread(target=message)
        reader.start()
        time.sleep(0.1)
        assert seen == []  # still waiting for the reset
        jobs.restore(sched, SEED)
    reader.join(5)
    assert seen == [slot_status(SEED, slot)] and seen != ["booked"]


def test_the_reset_waits_for_messages_in_progress(sched, store):
    gate = ResetGate()
    done = []
    with gate.shared():
        resetter = threading.Thread(target=lambda: done.append(jobs.nightly_reset(sched, SEED, store, gate=gate)))
        resetter.start()
        time.sleep(0.1)
        assert done == []
    resetter.join(5)
    assert done == ["ok"]


def test_startup_runs_a_reset_only_if_the_last_success_is_before_the_most_recent_3_am(sched, store, clock):
    clock.now = datetime(2026, 10, 20, 10, 0, tzinfo=AUSTIN)
    assert jobs.reset_if_missed(sched, SEED, store, clock=clock) == "ok"  # never run before
    clock.now = datetime(2026, 10, 20, 11, 0, tzinfo=AUSTIN)
    assert jobs.reset_if_missed(sched, SEED, store, clock=clock) is None  # this morning's counts
    clock.now = datetime(2026, 10, 21, 4, 0, tzinfo=AUSTIN)
    assert jobs.reset_if_missed(sched, SEED, store, clock=clock) == "ok"  # missed 03:00 on the 21st


def test_a_reset_failing_twice_records_failed_alerts_once_and_shows_in_the_live_numbers(sched, store, alerts,
                                                                                       webhook, clock, monkeypatch):
    calls = []

    def broken(*args):
        calls.append(args)
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(jobs, "restore", broken)
    assert jobs.nightly_reset(sched, SEED, store, alerts=alerts) == "failed"
    assert len(calls) == 2
    run = store.job_runs("nightly reset")[-1]
    assert run["result"] == "failed" and run["finished_at"] is None
    assert [p[1]["kind"] for p in webhook.posts] == ["reset"]
    assert [a["kind"] for a in store.alerts()] == ["reset"]
    assert live_numbers(store, clock().date())["nightly_reset"] == RESET_FAILED


def test_a_reset_that_succeeds_on_retry_is_recorded_as_retried(sched, store, monkeypatch):
    real, calls = jobs.restore, []

    def flaky(*args):
        calls.append(args)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        real(*args)

    monkeypatch.setattr(jobs, "restore", flaky)
    assert jobs.nightly_reset(sched, SEED, store) == "retried"
    assert live_numbers(store, datetime(2026, 10, 20).date())["nightly_reset"] is None


# -- Alerts --------------------------------------------------------------------------------------------------------
def errors(store, n):
    for i in range(n):
        store.log_event("error", f"failure {i}", "c1")


def messages(store, n):
    store.open_conversation("v1", "c1")
    for i in range(n):
        store.log_message("c1", "caller", f"message {i}")


def test_three_errors_in_ten_minutes_send_an_error_alert_and_two_do_not(store, alerts, webhook):
    errors(store, 2)
    alerts.check_errors()
    assert webhook.posts == []
    errors(store, 1)
    alerts.check_errors()
    alerts.check_errors()  # still the same burst: one alert
    assert [p[1]["kind"] for p in webhook.posts] == ["errors"]
    assert webhook.posts[0][0] == "https://alerts.example/hook" and webhook.posts[0][2] == 5


def test_errors_older_than_ten_minutes_do_not_count(store, alerts, webhook, clock):
    errors(store, 2)
    clock.now += timedelta(minutes=11)
    errors(store, 1)
    alerts.check_errors()
    assert webhook.posts == []


def test_three_errors_in_twelve_messages_over_ten_minutes_send_one_alert(store, alerts, webhook, clock):
    for i in range(12):
        messages(store, 1)
        if i % 4 == 0:
            errors(store, 1)
        alerts.check_errors()
        clock.now += timedelta(seconds=50)
    assert [p[1]["kind"] for p in webhook.posts] == ["errors"]


def test_a_failed_database_write_sends_a_write_failure_alert(store, alerts, webhook):
    alerts.watch(store)
    store._db.close()  # every later write fails
    with pytest.raises(sqlite3.ProgrammingError):
        store.log_event("error", "anything")
    assert [p[1]["kind"] for p in webhook.posts] == ["write failure"]


def test_a_webhook_that_fails_never_raises(store, clock):
    def down(url, payload, timeout):
        raise OSError("connection refused")

    Alerts(store, url="https://alerts.example/hook", post=down, clock=clock).send("errors", "three errors")
    assert [a["kind"] for a in store.alerts()] == ["errors"]


# -- Purge ---------------------------------------------------------------------------------------------------------
def old_conversation(store, clock, conversation_id, flagged=False):
    store.open_conversation("v1", conversation_id)
    caller = store.log_message(conversation_id, "caller", "hello")
    agent = store.log_message(conversation_id, "agent", "hi there")
    store.log_sentence(agent, "hi there")
    store.log_receipt(agent, "clear", "knowledge", [], [], None, "answered")
    store.log_model_call(agent, "write", "claude-sonnet-5-5", "test", {}, 10, 5, 100, 30)
    store.log_event("error", "old error", conversation_id)
    if flagged:
        store.add_flag(agent, "wrong price")
    return caller, agent


def test_the_purge_deletes_a_31_day_old_conversation_with_everything_it_logged_but_keeps_flagged_ones(store,
                                                                                                    clock):
    now = clock.now
    clock.now = now - timedelta(days=31)
    old_conversation(store, clock, "old")
    old_conversation(store, clock, "kept", flagged=True)
    clock.now = now - timedelta(days=29)
    old_conversation(store, clock, "recent")
    clock.now = now

    jobs.purge(store, older_than_days=30, clock=clock)

    remaining = {r["conversation_id"] for r in store.read("select conversation_id from conversations")}
    assert remaining == {"kept", "recent"}
    for table in ("messages", "events"):
        assert {r["conversation_id"] for r in store.read(f"select conversation_id from {table}")} == remaining
    left = {r["message_id"] for r in store.read("select message_id from messages")}
    for table in ("sentences", "receipts", "model_calls"):
        assert {r["message_id"] for r in store.read(f"select message_id from {table}")} <= left
    assert store.read("select count(*) as n from model_calls")[0]["n"] == 2
    assert [r["result"] for r in store.job_runs("log purge")] == ["ok"]


def test_the_purge_keeps_tickets_for_staff_but_detaches_them(store, clock):
    now = clock.now
    clock.now = now - timedelta(days=31)
    old_conversation(store, clock, "old")
    ticket = store.create_ticket("old", "Linda", "a plumber", "nothing", "none", "calm", "handoff")
    clock.now = now
    jobs.purge(store, older_than_days=30, clock=clock)
    assert [(t["ticket_id"], t["conversation_id"]) for t in store.tickets()] == [(ticket, None)]


# -- Health --------------------------------------------------------------------------------------------------------
class SilentEngine:
    def handle(self, turn):
        return iter(())


def test_health_is_200_when_both_databases_open_and_503_when_the_scheduling_file_is_missing(sched, store):
    client = TestClient(create_app(SilentEngine(), store, cookie_secret=SECRET, scheduling_db=sched))
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"ok": True}
    sched.unlink()
    response = client.get("/health")
    assert response.status_code == 503 and response.json()["ok"] is False


def test_messages_hold_the_gate_shared_so_they_wait_for_a_reset(store):
    from app.core.types import DoneEvent, SentenceEvent
    gate, started = ResetGate(), []

    class Engine:
        def handle(self, turn):
            started.append(turn.text)
            yield SentenceEvent("hi")
            yield DoneEvent(route="knowledge", ticket=None, outcome="answered")

    client = TestClient(create_app(Engine(), store, cookie_secret=SECRET, gate=gate), base_url="https://testserver")
    with gate.exclusive():
        client.post("/api/message", json={"conversation_id": "c-gate", "message_id": "m1", "text": "hello"})
        time.sleep(0.2)
        assert started == []
    assert "hi" in client.get("/api/stream/m1").text and started == ["hello"]
