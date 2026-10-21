"""Spending budgets and the reviewer link (R61, R85, D30, D34). No model is ever called: spend is reported through the
model-call sink exactly as the RecordingClient reports it, with made-up microdollars."""

import json
import logging
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AUSTIN, SETTINGS, real_now
from app.core.model_log import SINK
from app.core.pipeline import LIMIT
from app.core.types import DoneEvent, SentenceEvent
from app.ops.spend import Spend
from app.ops.store import OpsStore
from app.safety.replies import fixed_reply
from app.web.main import create_app
from eval.budget import RunBudget
from tests.core.test_engine import say, world  # noqa: F401  (the fixture)
from tests.flows.test_conversations import chat  # noqa: F401  (the fixture)

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "rv-" + "7f3c9a1e5b2d4f60a8c1e3b5d7f9a2c4"
SECRET = "test-only-secret"
DOLLAR = 1_000_000


class Clock:
    def __init__(self, when: datetime):
        self.now = when

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    return OpsStore(tmp_path / "ops.sqlite")


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 20, 14, 0, tzinfo=AUSTIN))


@pytest.fixture
def spend(store, clock):
    return Spend(store, clock=clock)


def spent(spend, visitor, dollars):
    spend.record(visitor, round(dollars * DOLLAR))


# -- Public visitors and the site cap ----------------------------------------------------------------------------

def test_a_public_visitor_at_39_cents_is_allowed_and_at_41_cents_is_refused(spend):
    spent(spend, "v1", 0.39)
    assert spend.allow("v1")
    spent(spend, "v1", 0.02)
    assert not spend.allow("v1") and spend.refusal("v1") == "visitor daily budget"
    assert spend.allow("v2")  # another visitor has their own budget


def test_an_over_budget_visitor_gets_a_plain_handoff_without_routing_but_still_gets_safety_replies(world, store, clock):
    spend = Spend(store, clock=clock)
    spent(spend, "v1", 0.41)
    engine, _ = world["build"](guard=spend.refusal)
    sentences, done = say(engine, "what does the membership include")
    assert sentences == [LIMIT] and done.outcome == "limit" and world["router"].calls == []
    sentences, done = say(engine, "I smell gas")  # safety runs before the spending guard (R34)
    assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger")
    sentences, done = say(engine, "what does the membership include", conversation="c2", visitor="v2")
    assert done.outcome != "limit"


def test_with_the_site_at_10_dollars_a_public_visitor_is_refused_but_a_reviewer_under_3_dollars_is_allowed(spend, store):
    for n in range(25):
        spent(spend, f"public-{n}", 0.40)  # $10.00 of public traffic
    assert not spend.allow("newcomer") and spend.refusal("newcomer") == "site daily budget"
    store.make_reviewer("rev")
    assert spend.allow("rev")
    spent(spend, "rev", 2.99)
    assert spend.allow("rev")
    spent(spend, "rev", 0.01)
    assert not spend.allow("rev") and spend.refusal("rev") == "reviewer reserve"


def test_reviewer_spend_draws_on_the_reserve_and_not_on_the_public_pools(spend, store):
    store.make_reviewer("rev")
    spent(spend, "rev", 2.50)
    assert spend.totals("rev") == {"visitor": 2.50, "public": 0.0, "reviewer": 2.50, "site": 0.0}
    assert spend.allow("v1")
    assert {row["pool"] for row in store.spend_rows()} == {"reviewer"}


# -- The $5 alert and the Austin day ------------------------------------------------------------------------------

def test_crossing_5_dollars_site_wide_records_exactly_one_spend_alert_per_day(spend, store, clock):
    for n in range(12):
        spent(spend, f"v{n}", 0.40)  # $4.80
    assert store.alerts("spend") == []
    spent(spend, "v12", 0.40)  # crosses $5.00
    spent(spend, "v13", 0.40)
    spent(spend, "v14", 0.40)
    [alert] = store.alerts("spend")
    assert "passed $5.00" in alert["detail"] and "2026-10-20" in alert["detail"]
    assert Spend(store, clock=clock).totals()["site"] > 5  # a restart does not alert again
    spent(Spend(store, clock=clock), "v15", 0.40)
    assert len(store.alerts("spend")) == 1
    clock.now = datetime(2026, 10, 21, 0, 1, tzinfo=AUSTIN)
    for n in range(13):
        spent(spend, f"w{n}", 0.40)
    assert len(store.alerts("spend")) == 2


def test_reviewer_spend_counts_toward_the_alert(spend, store):
    store.make_reviewer("rev")
    spent(spend, "rev", 2.90)
    spent(spend, "v1", 0.30)
    spent(spend, "v2", 0.30)
    for n in range(6):
        spent(spend, f"x{n}", 0.30)
    assert len(store.alerts("spend")) == 1


def test_days_roll_over_at_austin_midnight(spend, clock):
    clock.now = datetime(2026, 10, 21, 4, 59, tzinfo=timezone.utc)  # 23:59 in Austin on the 20th
    spent(spend, "v1", 0.41)
    assert not spend.allow("v1")
    clock.now = datetime(2026, 10, 21, 5, 1, tzinfo=timezone.utc)  # 00:01 in Austin on the 21st
    assert spend.allow("v1") and spend.totals("v1")["visitor"] == 0


def test_the_day_is_real_time_not_the_fixed_test_now(store):
    spend = Spend(store)
    assert spend.clock is real_now
    spent(spend, "v1", 0.10)
    [row] = store.spend_rows()
    assert row["day"] == real_now().date().isoformat()
    assert spend.day() != SETTINGS.now.date().isoformat() or real_now().date() == SETTINGS.now.date()


def test_a_failing_spend_write_never_breaks_the_reply(spend, monkeypatch, caplog):
    def broken(*args):
        raise RuntimeError("disk full")
    monkeypatch.setattr(spend.store, "add_spend", broken)
    spend.record("v1", 1000)  # does not raise
    assert "spend" in caplog.text


# -- The web layer records each turn's model calls against the visitor --------------------------------------------

class SpendingEngine:
    """Reports two model calls through the sink, as the RecordingClient does, then replies."""

    def __init__(self, store, microdollars=3100):
        self.store, self.microdollars, self.sinks = store, microdollars, []

    def handle(self, turn):
        self.store.log_message(turn.conversation_id, "caller", turn.text, turn.message_id)
        agent = self.store.log_message(turn.conversation_id, "agent", "")
        sink = SINK.get()
        self.sinks.append(sink)
        sink("route", "claude-haiku-5-5", "sdk", {}, 400, 60, 5, 100)
        sink("write", "claude-sonnet-5-5", "sdk", {}, 900, 120, 9, self.microdollars)
        self.store.log_sentence(agent, "Done.")
        yield SentenceEvent("Done.")
        yield DoneEvent("knowledge", None)


def client_for(app):
    return TestClient(app, base_url="https://testserver")


def send(client, text="hello"):
    message_id = uuid.uuid4().hex
    response = client.post("/api/message", json={"conversation_id": "c-" + uuid.uuid4().hex[:8],
                                                  "message_id": message_id, "text": text})
    assert response.status_code == 202
    return client.get(f"/api/stream/{message_id}").text


def test_each_turns_model_calls_are_recorded_against_the_visitor_in_the_background_thread(store, spend):
    engine = SpendingEngine(store)
    app = create_app(engine, store, cookie_secret=SECRET, spend=spend)
    with client_for(app) as client:
        send(client)
        send(client)
        visitor = [r for r in store.spend_rows()][0]["visitor_id"]
    assert spend.totals(visitor)["visitor"] == pytest.approx(2 * 3200 / DOLLAR)
    assert {row["pool"] for row in store.spend_rows()} == {"public"}
    assert SINK.get() is None  # the request thread's sink is untouched


def test_the_reply_thread_does_not_keep_the_visitor_sink_after_the_turn(store, spend):
    engine = SpendingEngine(store)
    app = create_app(engine, store, cookie_secret=SECRET, spend=spend, workers=1)
    with client_for(app) as client:
        send(client)
    seen = app.state.executor.submit(SINK.get).result()
    assert seen is None


# -- The evaluation harness never touches the live pools ----------------------------------------------------------

def test_an_eval_run_with_its_own_sink_does_not_touch_the_live_pools(chat):
    store = chat["store"]
    live = Spend(store)
    budget = RunBudget(cap_usd=8.0)
    token = SINK.set(budget.record)  # as eval/harness.py does for every attempt
    try:
        chat["say"]("how much is a tune-up")
    finally:
        SINK.reset(token)
    assert budget.spent_usd > 0  # the scripted calls were counted against the run (the evaluation key's budget)
    assert store.spend_rows() == [] and live.totals("v1") == {"visitor": 0, "public": 0, "reviewer": 0, "site": 0}


def test_the_same_turn_under_the_web_recorder_does_count(chat):
    store = chat["store"]
    live = Spend(store)
    token = SINK.set(live.recorder("v1"))
    try:
        chat["say"]("how much is a tune-up")
    finally:
        SINK.reset(token)
    assert live.totals("v1")["visitor"] > 0


# -- The reviewer link ---------------------------------------------------------------------------------------------

def reviewer_app(store, token=TOKEN, spend=None):
    return create_app(SpendingEngine(store), store, cookie_secret=SECRET, spend=spend, reviewer_token=token)


def visitor_of(client):
    from app.web.visitor import COOKIE, VisitorCookie
    return VisitorCookie(SECRET).read(client.cookies.get(COOKIE))


def test_the_correct_token_starts_a_reviewer_session_once(store, spend, caplog):
    caplog.set_level(logging.DEBUG)
    with client_for(reviewer_app(store, spend=spend)) as client:
        response = client.post("/api/reviewer", json={"token": TOKEN})
        assert response.status_code == 200 and TOKEN not in response.text
        visitor = visitor_of(client)
        assert visitor and store.visitor_kind(visitor) == "reviewer" and spend.is_reviewer(visitor)
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 404  # second use
    with client_for(reviewer_app(store)) as other:
        assert other.post("/api/reviewer", json={"token": TOKEN}).status_code == 404
        assert store.visitor_kind(visitor_of(other)) != "reviewer"
    assert TOKEN not in caplog.text
    assert all(TOKEN not in str(record.args) for record in caplog.records)


def test_a_used_token_stays_used_after_a_restart(tmp_path):
    with client_for(reviewer_app(OpsStore(tmp_path / "ops.sqlite"))) as client:
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 200
    restarted = OpsStore(tmp_path / "ops.sqlite")
    with client_for(reviewer_app(restarted)) as client:
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 404
    raw = (tmp_path / "ops.sqlite").read_bytes() + b"".join(p.read_bytes() for p in tmp_path.glob("ops.sqlite-*"))
    assert TOKEN.encode() not in raw  # only a hash of the token is stored


@pytest.mark.parametrize("body", [{"token": "rv-wrong-token-0000000000000000"}, {"token": TOKEN[:-1]}, {"token": ""},
                                  {}, {"token": 12}, "not json", {"token": TOKEN + "x"}])
def test_a_wrong_or_malformed_token_returns_404_and_is_not_logged(store, caplog, body):
    caplog.set_level(logging.DEBUG)
    with client_for(reviewer_app(store)) as client:
        if isinstance(body, str):
            response = client.post("/api/reviewer", content=body, headers={"content-type": "application/json"})
        else:
            response = client.post("/api/reviewer", json=body)
        assert response.status_code == 404
        assert store.visitor_kind(visitor_of(client)) != "reviewer"
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 200  # the real one still works
    assert TOKEN not in caplog.text and "rv-wrong" not in caplog.text


def test_without_a_configured_token_the_reviewer_link_is_off(store):
    for token in (None, "", "short"):
        with client_for(reviewer_app(store, token=token)) as client:
            assert client.post("/api/reviewer", json={"token": token or ""}).status_code == 404
            assert client.post("/api/reviewer", json={"token": "short"}).status_code == 404


def test_a_reviewer_session_spends_from_the_reserve_while_the_site_is_full(store, spend):
    for n in range(25):
        spent(spend, f"public-{n}", 0.40)
    with client_for(reviewer_app(store, spend=spend)) as client:
        visitor = visitor_of(client) or (client.get("/") and visitor_of(client))
        assert not spend.allow(visitor)
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 200
        assert spend.allow(visitor_of(client))
        send(client)
    assert spend.totals(visitor_of(client))["reviewer"] == pytest.approx(3200 / DOLLAR)


def test_the_reviewer_token_comes_from_the_environment_and_env_example_has_only_a_placeholder(monkeypatch):
    from app.web.reviewer import TOKEN_VARIABLE, token_from_environment
    monkeypatch.setenv(TOKEN_VARIABLE, TOKEN)
    assert token_from_environment() == TOKEN
    monkeypatch.delenv(TOKEN_VARIABLE)
    assert token_from_environment() is None
    lines = [line for line in (ROOT / ".env.example").read_text().splitlines() if line.startswith(f"{TOKEN_VARIABLE}=")]
    assert lines == [f"{TOKEN_VARIABLE}="]


# -- reviewer.js ---------------------------------------------------------------------------------------------------

def test_the_chat_page_loads_reviewer_js(store):
    with client_for(reviewer_app(store)) as client:
        assert 'src="/static/reviewer.js"' in client.get("/").text
        assert client.get("/static/reviewer.js").status_code == 200


HARNESS = """
const calls = {fetch: [], replace: []};
global.window = global;
global.location = {hash: process.argv[2], pathname: "/", search: "?q=1", href: "https://app.test/?q=1" + process.argv[2]};
global.history = {state: null, replaceState: (s, t, url) => { calls.replace.push(url); location.hash = ""; }};
global.document = {title: "Chat"};
global.fetch = (url, options) => { calls.fetch.push({url, options, hashAtFetch: location.hash});
  return Promise.resolve({ok: true, status: 200}); };
const source = require("fs").readFileSync(process.argv[1], "utf8");
eval(source);  // runs only the repository's own page script, in a throwaway node process
eval(source);  // the page script running again (a second load of the same address) must not post again
setTimeout(() => console.log(JSON.stringify(calls)), 10);
"""


def run_reviewer_js(fragment: str) -> dict:
    out = subprocess.run(["node", "-e", HARNESS, str(ROOT / "app/web/static/reviewer.js"), fragment],
                         capture_output=True, text=True, check=True, timeout=10).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page script")
def test_reviewer_js_posts_the_fragment_once_and_clears_it_from_the_address():
    calls = run_reviewer_js(f"#r={TOKEN}")
    [call] = calls["fetch"]
    assert call["url"] == "/api/reviewer" and call["options"]["method"] == "POST"
    assert json.loads(call["options"]["body"]) == {"token": TOKEN}
    assert call["hashAtFetch"] == ""  # cleared before the request is even sent
    assert calls["replace"] == ["/?q=1"]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page script")
def test_reviewer_js_does_nothing_without_a_reviewer_fragment():
    for fragment in ("", "#", "#other=1"):
        assert run_reviewer_js(fragment) == {"fetch": [], "replace": []}


# -- One link per reviewer (D50) -----------------------------------------------------------------------------------

OTHER = "rv-second-reviewer-token-abcdef123456"


def test_each_reviewer_gets_their_own_one_time_link(store, spend):
    app = reviewer_app(store, token=f"{TOKEN}, {OTHER}", spend=spend)
    with client_for(app) as first, client_for(app) as second:
        assert first.post("/api/reviewer", json={"token": TOKEN}).status_code == 200
        assert second.post("/api/reviewer", json={"token": OTHER}).status_code == 200  # the other link still works
        assert spend.is_reviewer(visitor_of(first)) and spend.is_reviewer(visitor_of(second))
    with client_for(app) as third:
        assert third.post("/api/reviewer", json={"token": TOKEN}).status_code == 404  # each is used once
        assert third.post("/api/reviewer", json={"token": OTHER}).status_code == 404


def test_a_too_short_token_in_the_list_is_dropped_but_the_others_work(store):
    with client_for(reviewer_app(store, token=f"short,{TOKEN}")) as client:
        assert client.post("/api/reviewer", json={"token": "short"}).status_code == 404
        assert client.post("/api/reviewer", json={"token": TOKEN}).status_code == 200


def test_a_zero_public_budget_refuses_every_public_message_but_not_a_reviewer(store):
    # Reviewer-only mode (D50): PER_VISITOR_DAILY_USD=0 on Fly; nothing is spent before the refusal.
    zero = Spend(store, per_visitor_usd=0.0)
    assert not zero.allow("a-public-visitor")
    store.make_reviewer("a-reviewer")
    assert zero.allow("a-reviewer")
