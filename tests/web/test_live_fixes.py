"""Milestone 5 review fixes in the web layer (live-only, after the measurement, D51): safety before the message limits,
fallback replies that open a ticket, a timed-out turn that never acts later, an accepted message that survives a
restart, and no rows for refused or blank messages. No model is ever called."""

import threading
import time
from datetime import datetime

import pytest

from app.config import AUSTIN
from app.core.types import DoneEvent
from app.handoff.flow import ERROR_MESSAGE
from app.ops.gate import ResetGate
from app.ops.store import OpsStore
from app.safety.replies import fixed_reply
from app.web.limits import LIMIT_MESSAGE, TURN_LIMIT, Limits, turn_guard
from tests.core.test_engine import world  # noqa: F401  (the fixture)
from tests.web.test_chat import FakeEngine, as_visitor, client_for, make, new_id, post, restarted, say, stream


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 20, 9, 0, tzinfo=AUSTIN)

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    return OpsStore(tmp_path / "ops.sqlite")


def count(store, table: str) -> int:
    return store.read(f"select count(*) as n from {table}")[0]["n"]


def error_tickets(store) -> list[dict]:
    return [t for t in store.tickets() if t["reason_tag"] == "error"]


# -- Safety runs before the message limits (item 1) ---------------------------------------------------------------

def test_a_rate_limited_caller_reporting_gas_still_gets_the_safety_reply_and_a_priority_ticket(world):
    engine, pipeline = world["build"](guard=turn_guard())
    app_store = pipeline.store
    _, _, client = make(app_store, engine, limits=Limits(Clock(), per_10_min=2, per_day=100, site_per_minute=60))
    for _ in range(2):
        assert say(client, "c1", "what does the membership include")[1]["outcome"] != "limit"
    sentences, done = say(client, "c1", "what does the membership include")
    assert sentences == [LIMIT_MESSAGE] and done["outcome"] == "limit"
    sentences, done = say(client, "c1", "I smell gas")  # over the limit, but safety comes first
    assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger")
    assert done["outcome"] == "safety" and done["ticket"]
    assert [t["priority"] for t in app_store.tickets() if t["ticket_id"] == done["ticket"]] == [2]


def test_the_composed_guard_refuses_for_either_the_message_limit_or_the_spend_caps():
    class Spend:
        def refusal(self, visitor):
            return "visitor daily budget" if visitor == "spent" else None

    guard = turn_guard(Spend())
    assert guard("v1") is None and guard("spent") == "visitor daily budget"
    token = TURN_LIMIT.set("visitor per 10 minutes")
    try:
        assert guard("v1") == "visitor per 10 minutes"
    finally:
        TURN_LIMIT.reset(token)
    assert guard("v1") is None


def test_build_app_composes_the_limit_and_spend_guard():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "app" / "web" / "main.py").read_text()
    assert "guard=turn_guard(spend)" in source and "guard=spend.refusal" not in source


# -- Fallback replies open an error ticket (item 2) ----------------------------------------------------------------

def test_a_stream_that_gives_up_opens_one_error_ticket_with_the_callers_message(store):
    release = threading.Event()

    class StuckEngine(FakeEngine):
        def handle(self, turn):
            release.wait(5)
            yield DoneEvent("knowledge", None)

    app, _, client = make(store, StuckEngine(store), stream_timeout_s=0.2)
    message_id = new_id()
    post(client, "c1", "my furnace is rattling", message_id)
    events = stream(client, message_id)
    assert [data.get("text") for _, data in events] == [ERROR_MESSAGE, None]
    [ticket] = error_tickets(store)
    assert events[-1][1]["ticket"] == ticket["ticket_id"] and ticket["conversation_id"] == "c1"
    assert "my furnace is rattling" in ticket["wants"]
    assert stream(client, message_id) == events  # a reconnect replays it; no second ticket
    release.set()
    app.state.executor.shutdown(wait=True)
    assert len(error_tickets(store)) == 1


def test_a_reply_left_unfinished_by_a_restart_opens_one_error_ticket(store):
    from app.core.state import ConversationState
    ConversationState.load(store, "c1", "visitor-1")
    store.log_message("c1", "caller", "book me a visit", "m-unfinished")
    store.log_sentence(store.log_message("c1", "agent", ""), "Let me find a time.")
    app, _, _ = restarted(store)
    client = as_visitor(app, "visitor-1")
    events = stream(client, "m-unfinished")
    [ticket] = error_tickets(store)
    assert events[-1][1]["ticket"] == ticket["ticket_id"] and "book me a visit" in ticket["wants"]
    assert events[-1][1]["proof"] == f"ticket #{ticket['ticket_id']} created"
    assert stream(client, "m-unfinished") == events and len(error_tickets(store)) == 1


def test_an_engine_that_raises_gets_the_error_reply_and_one_error_ticket(store):
    class BrokenEngine(FakeEngine):
        def handle(self, turn):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    _, _, client = make(store, BrokenEngine(store))
    sentences, done = say(client, "c1", "what does the membership include")
    assert sentences == [ERROR_MESSAGE] and done["outcome"] == "error"
    [ticket] = error_tickets(store)
    assert done["ticket"] == ticket["ticket_id"] and "membership" in ticket["wants"]


# -- A timed-out turn never acts later (item 3) --------------------------------------------------------------------

def test_a_turn_stuck_behind_the_reset_gate_past_the_stream_timeout_never_runs_after_the_gate_opens(store):
    gate = ResetGate()
    app, engine, client = make(store, gate=gate, stream_timeout_s=0.2)
    held, release = threading.Event(), threading.Event()

    def reset():
        with gate.exclusive():
            held.set()
            release.wait(5)
    threading.Thread(target=reset, daemon=True).start()
    held.wait(5)
    message_id = new_id()
    post(client, "c1", "book me for Monday", message_id)
    events = stream(client, message_id)
    assert [data.get("text") for _, data in events] == [ERROR_MESSAGE, None]
    release.set()
    app.state.executor.shutdown(wait=True)
    assert engine.turns == []  # never booked, never answered after the caller was told it was passed on
    assert len(error_tickets(store)) == 1


def test_a_turn_with_too_little_time_left_for_its_deadline_does_not_start(store):
    lock_held = threading.Event()

    class SlowFirst(FakeEngine):
        def handle(self, turn):
            if not self.turns:
                self.turns.append(turn)
                lock_held.set()
                time.sleep(0.7)  # holds the conversation lock
                yield DoneEvent("knowledge", None)
                return
            yield from super().handle(turn)

    engine = SlowFirst(store)
    app, _, client = make(store, engine, stream_timeout_s=1.0, engine_deadline_s=0.5)
    post(client, "c1", "first")
    lock_held.wait(5)
    second = new_id()
    post(client, "c1", "second", second)  # waits about 0.7 s: 0.3 s is left, less than the 0.5 s deadline
    app.state.executor.shutdown(wait=True)
    assert [turn.text for turn in engine.turns] == ["first"]
    events = stream(client, second)
    assert [data.get("text") for _, data in events] == [ERROR_MESSAGE, None] and events[-1][1]["ticket"]


# -- An accepted message survives a restart (item 4) ---------------------------------------------------------------

def test_a_message_accepted_but_not_yet_worked_on_is_replayed_as_a_handoff_with_a_ticket_after_a_restart(store):
    app, engine, client = make(store)
    app.state.executor.submit = lambda *args, **kwargs: None  # the process stops before the worker starts
    message_id = new_id()
    assert post(client, "c1", "please send someone Tuesday", message_id).status_code == 202
    rows = store.read("select * from messages where request_id = ?", (message_id,))
    assert len(rows) == 1 and rows[0]["role"] == "caller"
    app2, engine2, _ = restarted(store)
    visitor = store.read("select visitor_id from conversations where conversation_id = 'c1'")[0]["visitor_id"]
    again = as_visitor(app2, visitor)
    events = stream(again, message_id)
    assert [data.get("text") for _, data in events] == [ERROR_MESSAGE, None]
    [ticket] = error_tickets(store)
    assert events[-1][1]["ticket"] == ticket["ticket_id"] and "please send someone Tuesday" in ticket["wants"]
    assert post(again, "c1", "please send someone Tuesday", message_id).status_code == 202
    assert engine2.turns == [] and stream(again, message_id) == events


def test_the_accepted_message_is_not_logged_twice_when_the_engine_logs_it(store):
    _, _, client = make(store)
    say(client, "c1", "what does the membership include")
    rows = store.read("select role, text_masked from messages where conversation_id = 'c1' order by message_id")
    assert [(r["role"], r["text_masked"]) for r in rows] == [
        ("caller", "what does the membership include"), ("agent", "You said: what does the membership include.")]


def test_an_accepted_message_waiting_behind_another_does_not_claim_the_others_reply_on_restart(store):
    # B is accepted while A is still running; after a restart B must not replay A's sentences.
    from app.core.state import ConversationState
    ConversationState.load(store, "c1", "visitor-1")
    store.accept_message("c1", "m-a", "first")
    store.accept_message("c1", "m-b", "second")
    store.log_message("c1", "caller", "first", "m-a")
    agent = store.log_message("c1", "agent", "")
    store.log_sentence(agent, "Answer to the first.")
    assert store.request_reply("visitor-1", "m-a")["agent_message_id"] == agent
    assert store.request_reply("visitor-1", "m-b")["agent_message_id"] is None


# -- No rows for refused or blank messages (item 7) ----------------------------------------------------------------

def test_with_limits_at_2_a_hundred_posts_write_only_what_the_two_processed_messages_need(store):
    app, engine, client = make(store, limits=Limits(Clock(), per_10_min=2, per_day=100, site_per_minute=60))
    for n in range(100):
        post(client, f"c{n % 3}", "what does the membership include")
    for n in range(5):
        post(client, "c-blank", "   ")
    app.state.executor.shutdown(wait=True)
    assert len(engine.turns) == 2
    assert count(store, "conversations") == len({t.conversation_id for t in engine.turns})
    assert count(store, "messages") == 4  # two caller messages and two replies
    assert store.read("select count(*) as n from events where kind != 'accepted' and kind != 'reply end'")[0]["n"] == 0
    assert count(store, "events") <= 4


def test_a_post_to_another_visitors_conversation_is_still_refused_without_opening_rows(store):
    app, _, alice = make(store)
    say(alice, "shared", "hello")
    before = count(store, "messages")
    assert post(client_for(app), "shared", "let me in").status_code == 404
    assert count(store, "messages") == before


def test_a_blank_message_still_streams_a_request_for_more(store):
    _, engine, client = make(store)
    sentences, done = say(client, "c1", "  ")
    assert sentences == ["Could you tell me a bit more?"] and engine.turns == []
    assert count(store, "conversations") == 0 and count(store, "events") == 0


def test_over_the_limit_only_a_few_emergencies_a_day_open_tickets_and_the_rest_still_get_the_advice(world):
    # Security review: safety-first pass-throughs must not let an over-limit visitor flood staff with priority tickets.
    engine, pipeline = world["build"](guard=turn_guard())
    app_store = pipeline.store
    limits = Limits(Clock(), per_10_min=1, per_day=100, site_per_minute=60, safety_per_day=2)
    _, _, client = make(app_store, engine, limits=limits)
    say(client, "c1", "what does the membership include")
    tickets = []
    for n in range(5):
        sentences, done = say(client, f"g{n}", "I smell gas")
        assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger")  # the advice every time
        tickets.append(done["ticket"])
    assert sum(1 for t in tickets if t) == 2 and len(app_store.tickets()) == 2
    assert count(app_store, "conversations") <= 3  # the advice past the allowance writes nothing


def test_the_safety_allowance_is_per_visitor_and_network_block_then_overflows_site_wide():
    # Security reviews: an over-limit visitor cannot flood staff (per visitor and per network block, so rotating
    # addresses in one /24 or /64 does not help), and past a site-wide ceiling reports are merged, never dropped.
    limits = Limits(Clock(), per_10_min=1, per_day=100, site_per_minute=60, safety_per_day=1, safety_site_per_day=3)
    assert limits.allow_safety("v1", "10.0.0.1") == "ticket"
    assert limits.allow_safety("v1", "10.9.9.9") == "advice"  # same visitor
    assert limits.allow_safety("v2", "10.0.0.77") == "advice"  # same /24
    assert limits.allow_safety("v3", "2001:db8:1:1::5") == "ticket"
    assert limits.allow_safety("v4", "2001:db8:1:1::abcd") == "advice"  # same /64
    assert limits.allow_safety("v5", "172.16.0.1") == "ticket"
    assert limits.allow_safety("v6", "192.168.5.1") == "overflow"  # site-wide ceiling reached: merged, not dropped



def test_past_the_ceiling_emergencies_join_one_overflow_ticket_and_alert_once(world):
    engine, pipeline = world["build"](guard=turn_guard())
    app_store = pipeline.store
    sent = []

    class Alerts:
        def send(self, kind, detail):
            sent.append(kind)

        def check_errors(self):
            pass
    limits = Limits(Clock(), per_10_min=1, per_day=100, site_per_minute=60, safety_per_day=5, safety_site_per_day=1)
    _, _, client = make(app_store, engine, limits=limits, alerts=Alerts())
    say(client, "c0", "what does the membership include")
    first = say(client, "g0", "I smell gas")[1]
    assert first["ticket"]
    for n in range(1, 4):
        sentences, done = say(client, f"g{n}", "I smell gas")
        assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger") and done["ticket"]
    overflow = [t for t in app_store.tickets() if t["ticket_id"] != first["ticket"]]
    assert len(overflow) == 1 and overflow[0]["priority"] == 2  # one merged emergency ticket for the rest
    assert sent.count("safety overflow") == 1

