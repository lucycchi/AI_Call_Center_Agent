import json
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from app.config import SETTINGS
from app.core.engine import Engine
from app.core.pipeline import AgentPipeline
from app.core.types import DoneEvent, SentenceEvent, Turn
from app.knowledge.index import Chunk
from app.knowledge.search import ScoredChunk
from app.ops.store import OpsStore
from app.routing.router import Request, RouteResult, route
from app.safety.replies import fixed_reply

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
MEMBERSHIP = Chunk("membership__comfort_club_overview#1", "membership/comfort_club_overview.md", "Plans", "2026-01-01",
                   "Comfort Club (Standard): $189 per year; two tune-ups, priority scheduling, 15% off repairs.", 6, 26)


class FakeRouter:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, text, history):
        self.calls.append(text)
        for key, result in self.routes.items():
            if key in text.lower():
                return result
        return RouteResult("knowledge", True, [Request(text, "knowledge")])


class FakeSearcher:
    def search(self, question, mode="combined", k=5):
        return [ScoredChunk(MEMBERSHIP, 0.7, 2.0)]


def echo_writer(reply_type, facts, history):
    yield from facts


class Clock:
    def __init__(self):
        self.now = SETTINGS.now

    def __call__(self):
        return self.now


def book_route(service="hvac_repair"):
    return lambda text: RouteResult("scheduling", True, [Request(text, "scheduling", "book", service)])


ROUTES = {
    "need a repair": RouteResult("scheduling", True, [Request("I need a repair", "scheduling", "book", "hvac_repair")]),
    "yes": RouteResult("handoff", False, [Request("yes", "handoff", "other")]),
    "membership include": RouteResult("knowledge", True, [Request("what does the membership include", "knowledge")]),
    "balance": RouteResult("account", True, [Request("what's my balance", "account", "balance"),
                                             Request("I want a refund", "handoff", "dispute")]),
    "manager": RouteResult("handoff", True, [Request("have a manager call me back", "handoff", "complaint")]),
    "hiring": RouteResult("redirect", True, [Request("are you hiring", "redirect", "hiring")]),
}


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "scheduling.sqlite"
    shutil.copy(SEED, db)
    clock = Clock()
    router = FakeRouter(dict(ROUTES))

    def build(guard=lambda visitor: None):
        pipeline = AgentPipeline(store=OpsStore(tmp_path / "ops.sqlite", clock=clock), scheduling_db=db, seed_db=SEED,
                                 searcher=FakeSearcher(), route_fn=router, writer=echo_writer, threshold=0.4,
                                 guard=guard, now=SETTINGS.now, clock=clock)
        return Engine(pipeline), pipeline
    engine, pipeline = build()
    return {"engine": engine, "pipeline": pipeline, "router": router, "db": db, "clock": clock, "build": build,
            "ops": tmp_path / "ops.sqlite"}


def say(engine, text, conversation="c1", visitor="v1"):
    events = list(engine.handle(Turn(conversation, visitor, f"m-{abs(hash(text))}", text)))
    assert isinstance(events[-1], DoneEvent) and sum(isinstance(e, DoneEvent) for e in events) == 1
    return [e.text for e in events if isinstance(e, SentenceEvent)], events[-1]


def appointments(db):
    return sqlite3.connect(db).execute("select count(*) from appointments").fetchone()[0]


def test_danger_gets_the_fixed_reply_and_a_priority_ticket_without_calling_the_router(world):
    sentences, done = say(world["engine"], "I smell gas near my furnace")
    assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger")
    assert done.ticket and done.outcome == "safety"
    assert world["pipeline"].store.tickets()[0]["priority"] == 2
    assert world["router"].calls == []


def test_an_over_budget_visitor_reporting_gas_still_gets_the_safety_reply(world):
    engine, _ = world["build"](guard=lambda visitor: "over budget")
    sentences, done = say(engine, "I smell gas")
    assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger")
    sentences, done = say(engine, "what does the membership include")
    assert done.outcome == "limit" and world["router"].calls == []


def test_yes_stays_in_the_booking_flow_and_a_clear_new_topic_is_answered_with_an_offer_to_return(world):
    engine = world["engine"]
    sentences, done = say(engine, "I'm Linda Foster, MHC-10001. I need a repair Monday morning")
    assert done.route == "scheduling" and any("2026-10-19" in s and "08:00-12:00" in s for s in sentences)
    sentences, done = say(engine, "actually what does the membership include")
    assert any("$189" in s for s in sentences) and any("return to the booking" in s for s in sentences)
    sentences, done = say(engine, "yes")
    assert done.route == "scheduling" and done.ticket is None and any("read back" in s.lower() for s in sentences)
    before = appointments(world["db"])
    sentences, done = say(engine, "yes")
    assert appointments(world["db"]) == before + 1 and any("Marta Kowalski" in s for s in sentences)
    assert any("booked appointment" in action for action in done.db_actions)


def test_gas_during_a_booking_read_back_gives_the_safety_reply_and_books_nothing(world):
    engine = world["engine"]
    say(engine, "I'm Linda Foster, MHC-10001. I need a repair Monday morning")
    say(engine, "yes")
    before = appointments(world["db"])
    sentences, done = say(engine, "yes book it, also I can smell gas now")
    assert sentences[:len(fixed_reply("danger"))] == fixed_reply("danger") and done.outcome == "safety"
    assert appointments(world["db"]) == before


def test_a_balance_and_a_refund_answers_one_and_hands_off_the_other(world):
    sentences, done = say(world["engine"], "I'm Omar Patel, MHC-10002. What's my balance, and I want a refund")
    assert any("$478.00" in s for s in sentences)
    tickets = world["pipeline"].store.tickets()
    disputes = [t for t in tickets if t["reason_tag"] == "dispute"]
    assert len(disputes) == 1 and done.ticket == disputes[0]["ticket_id"]
    # Omar's $144 after-hours line also opens a silent billing review, with no conversation.
    reviews = [t for t in tickets if t["reason_tag"] == "billing review"]
    assert len(reviews) == 1 and reviews[0]["conversation_id"] is None


def test_routes_follow_the_handled_reason_list(world):
    _, done = say(world["engine"], "have a manager call me back", conversation="c2")
    assert done.outcome == "handed_off" and done.ticket
    sentences, done = say(world["engine"], "are you hiring", conversation="c3")
    assert done.outcome == "redirect" and done.ticket is None and any("careers" in s for s in sentences)


def test_a_caller_named_without_an_identifier_is_asked_and_handed_off_after_two_failures(world):
    engine = world["engine"]
    world["router"].routes = {"my balance": RouteResult("account", True, [Request("what's my balance", "account", "balance")]),
                              **world["router"].routes}
    sentences, done = say(engine, "what's my balance", conversation="c4")
    assert any("account number" in s for s in sentences) and done.ticket is None
    say(engine, "Linda Foster, MHC-99999", conversation="c4")
    _, done = say(engine, "Linda Foster, MHC-88888", conversation="c4")
    assert done.outcome == "handed_off" and done.ticket


def test_conversation_state_survives_a_new_engine(world):
    say(world["engine"], "I'm Linda Foster, MHC-10001. I need a repair Monday morning")
    engine, _ = world["build"]()
    sentences, done = say(engine, "yes")
    assert done.route == "scheduling" and any("read back" in s.lower() for s in sentences)


def test_a_conversation_idle_for_30_minutes_is_closed(world):
    say(world["engine"], "what does the membership include")
    world["clock"].now = world["clock"].now + timedelta(minutes=31)
    say(world["engine"], "what does the membership include", conversation="other")
    store = world["pipeline"].store
    assert store._rows("select status from conversations where conversation_id = 'c1'")[0]["status"] == "closed"


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.messages, self.calls = payload, stop_reason, self, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = type("Block", (), {"type": "text", "text": json.dumps(self.payload)})()
        return type("Response", (), {"content": [block], "stop_reason": self.stop_reason})()


def test_the_router_reads_haiku_structured_output():
    client = FakeClient({"clear": True, "requests": [{"text": "what's my balance", "route": "account", "detail": "balance",
                                                     "service_type": "none"}]})
    result = route("what's my balance", [], client)
    assert (result.route, result.clear, result.requests[0].detail) == ("account", True, "balance")
    assert client.calls[0]["model"] == "claude-haiku-5-5"
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_a_refused_or_broken_route_is_an_unclear_handoff():
    assert route("x", [], FakeClient({}, stop_reason="refusal")).route == "handoff"
    assert route("x", [], FakeClient({"nonsense": 1})).clear is False


def test_a_message_naming_a_different_customer_switches_the_account(world):
    engine = world["engine"]
    world["router"].routes = {"my balance": RouteResult("account", True, [Request("what's my balance", "account", "balance")]),
                              **world["router"].routes}
    say(engine, "I'm Linda Foster, MHC-10001. I need a repair Monday morning", conversation="c5")
    sentences, done = say(engine, "What's my balance? I'm Omar Patel, MHC-10002", conversation="c5")
    assert "invoice lookup MHC-10002" in done.db_actions and any("$478.00" in s for s in sentences)
