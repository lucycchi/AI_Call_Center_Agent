"""The chat page, message requests, sentence stream and visitor cookie (Task 21), with a fake engine: no model is
ever called. The fake engine writes to the operations store exactly as the real pipeline does (the caller message
with its request id, an agent message, and each released sentence), so replay is tested against the same records."""

import csv
import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AUSTIN
from app.core.state import ConversationState
from app.core.types import DoneEvent, SentenceEvent, Turn
from app.ops.store import OpsStore
from app.core.language import other_language
from app.handoff.flow import ERROR_MESSAGE
from app.handoff.flow import _message as handoff_message
from app.web.main import create_app
from app.web.visitor import VisitorCookie

SECRET = "test-only-secret"


class FakeEngine:
    """Replies "You said: <text>." unless a reply function is given; records every turn it is handed."""

    def __init__(self, store, reply=None):
        self.store, self.turns = store, []
        self.reply = reply or (lambda turn: ([f"You said: {turn.text[:40]}."], DoneEvent("knowledge", None)))

    def handle(self, turn: Turn):
        self.turns.append(turn)
        self.store.log_message(turn.conversation_id, "caller", turn.text, turn.message_id)
        agent = self.store.log_message(turn.conversation_id, "agent", "")
        sentences, done = self.reply(turn)
        for sentence in sentences:
            self.store.log_sentence(agent, sentence)
            yield SentenceEvent(sentence)
        self.store.log_agent_message(agent, " ".join(sentences))
        yield done


@pytest.fixture
def store(tmp_path):
    return OpsStore(tmp_path / "ops.sqlite")


def client_for(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")  # the cookie is Secure, so it is only sent over https


def make(store, engine=None, **options):
    engine = engine or FakeEngine(store)
    app = create_app(engine, store, cookie_secret=SECRET, **options)
    return app, engine, client_for(app)


def new_id() -> str:
    return uuid.uuid4().hex


def post(client, conversation_id, text, message_id=None, headers=None):
    return client.post("/api/message", json={"conversation_id": conversation_id, "message_id": message_id or new_id(),
                                              "text": text}, headers=headers or {})


def stream(client, message_id) -> list[tuple[str, dict]]:
    response = client.get(f"/api/stream/{message_id}")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def say(client, conversation_id, text, headers=None):
    """Send one message and read its whole stream: (sentences, done)."""
    message_id = new_id()
    assert post(client, conversation_id, text, message_id, headers).status_code == 202
    events = stream(client, message_id)
    assert events[-1][0] == "done" and all(kind == "sentence" for kind, _ in events[:-1])
    return [data["text"] for _, data in events[:-1]], events[-1][1]


# -- Cookie and ownership ----------------------------------------------------------------------------------------

def test_first_request_sets_a_signed_http_only_secure_lax_cookie_for_seven_days(store):
    _, _, client = make(store)
    response = post(client, "c1", "hello")
    assert response.status_code == 202
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("meridian_visitor=")
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    assert "Max-Age=604800" in cookie
    assert "set-cookie" not in post(client, "c1", "again").headers  # the same visitor: no new cookie


def test_a_tampered_cookie_is_replaced_with_a_new_visitor(store):
    app, engine, client = make(store)
    say(client, "c1", "hello")
    first, signed = engine.turns[-1].visitor_id, client.cookies["meridian_visitor"]
    forger = client_for(app)
    for forged in (signed[:-2] + "xx", first):  # an altered signature, and the bare visitor id
        message_id = new_id()
        response = post(forger, "c1", "let me in", message_id, headers={"cookie": f"meridian_visitor={forged}"})
        assert response.status_code == 404  # treated as a new visitor, who does not own c1
        assert response.headers["set-cookie"].startswith("meridian_visitor=")
    assert [turn.visitor_id for turn in engine.turns] == [first]


def test_posting_to_another_visitors_conversation_returns_404(store):
    app, engine, alice = make(store)
    bob = client_for(app)
    say(alice, "shared", "my booking")
    assert post(bob, "shared", "let me in").status_code == 404
    assert [turn.text for turn in engine.turns] == ["my booking"]  # the engine never saw bob's message


def test_another_visitors_stream_returns_404(store):
    app, _, alice = make(store)
    bob = client_for(app)
    message_id = new_id()
    post(alice, "c1", "hello", message_id)
    stream(alice, message_id)
    assert bob.get(f"/api/stream/{message_id}").status_code == 404


def test_the_message_reaches_the_engine_as_a_turn_for_this_visitor(store):
    _, engine, client = make(store)
    sentences, done = say(client, "c1", "What does the tune-up cost?")
    turn = engine.turns[0]
    assert (turn.conversation_id, turn.text) == ("c1", "What does the tune-up cost?")
    assert sentences == ["You said: What does the tune-up cost?."]
    assert done["route"] == "knowledge"


# -- Limits ------------------------------------------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 20, 9, 0, tzinfo=AUSTIN)

    def __call__(self):
        return self.now


def limited(sentences, done) -> bool:
    return done["outcome"] == "limit" and "phone our office" in sentences[0]


def test_the_21st_message_within_10_minutes_gets_a_plain_handoff(store):
    clock = Clock()
    _, engine, client = make(store, clock=clock)
    for _ in range(20):
        assert not limited(*say(client, "c1", "hello"))
        clock.now += timedelta(seconds=20)
    sentences, done = say(client, "c1", "one more")
    assert limited(sentences, done) and len(engine.turns) == 20  # the engine never saw it
    clock.now += timedelta(minutes=10)
    assert not limited(*say(client, "c1", "later"))


def test_the_101st_message_in_a_day_gets_a_plain_handoff(store):
    clock = Clock()
    _, engine, client = make(store, clock=clock)
    for _ in range(100):
        assert not limited(*say(client, "c1", "hello"))
        clock.now += timedelta(minutes=1)  # never more than 10 in any 10 minutes
    assert limited(*say(client, "c1", "one more"))
    assert len(engine.turns) == 100


def test_the_61st_site_wide_message_in_a_minute_gets_a_plain_handoff(store):
    clock = Clock()
    app, engine, _ = make(store, clock=clock)
    for n in range(60):
        assert not limited(*say(client_for(app), f"c{n}", "hello", {"Fly-Client-IP": f"10.0.0.{n}"}))
    assert limited(*say(client_for(app), "c60", "hello", {"Fly-Client-IP": "10.0.1.1"}))
    clock.now += timedelta(minutes=1)
    assert not limited(*say(client_for(app), "c61", "hello", {"Fly-Client-IP": "10.0.1.2"}))


def test_a_visitor_who_clears_their_cookie_is_still_limited_by_the_fly_client_address(store):
    app, _, client = make(store, clock=Clock())
    address = {"Fly-Client-IP": "203.0.113.7"}
    for _ in range(20):
        assert not limited(*say(client, "c1", "hello", address))
    fresh = client_for(app)  # no cookie: a new visitor id, the same address
    assert limited(*say(fresh, "c2", "hello", address))
    assert not limited(*say(client_for(app), "c3", "hello", {"Fly-Client-IP": "203.0.113.8"}))


# -- Stream ------------------------------------------------------------------------------------------------------

def restarted(store, engine=None):
    """A new app on the same operations store, as after a restart: nothing is kept in memory."""
    return make(store, engine)


def as_visitor(app, visitor_id: str) -> TestClient:
    client = client_for(app)
    client.headers["cookie"] = f"meridian_visitor={VisitorCookie(SECRET).sign(visitor_id)}"
    return client


def test_posting_the_same_message_id_twice_produces_one_reply(store):
    _, engine, client = make(store)
    message_id = new_id()
    assert post(client, "c1", "hello", message_id).status_code == 202
    assert post(client, "c1", "hello", message_id).status_code == 202
    events = stream(client, message_id)
    assert [kind for kind, _ in events] == ["sentence", "done"]
    assert len(engine.turns) == 1


def test_the_same_message_id_after_a_restart_is_not_processed_again(store):
    _, engine, client = make(store)
    message_id = new_id()
    post(client, "c1", "hello", message_id)
    first = stream(client, message_id)
    app, engine_after, _ = restarted(store)
    again = as_visitor(app, engine.turns[0].visitor_id)
    assert post(again, "c1", "hello", message_id).status_code == 202
    assert engine_after.turns == [] and stream(again, message_id) == first


def test_a_stream_opened_after_the_reply_finished_replays_the_saved_sentences_and_the_done_event(store):
    reply = lambda turn: (["First sentence.", "Second sentence."], DoneEvent("knowledge", None))  # noqa: E731
    _, engine, client = make(store, FakeEngine(store, reply))
    message_id = new_id()
    post(client, "c1", "hello", message_id)
    first = stream(client, message_id)
    assert [data.get("text") for _, data in first] == ["First sentence.", "Second sentence.", None]
    assert stream(client, message_id) == first  # a reconnect in the same process
    app, _, _ = restarted(store)
    assert stream(as_visitor(app, engine.turns[0].visitor_id), message_id) == first  # and after a restart


def test_a_stream_opened_while_the_reply_is_running_gets_saved_then_live_sentences(store):
    gate = threading.Event()

    class SlowEngine(FakeEngine):
        def handle(self, turn):
            self.store.log_message(turn.conversation_id, "caller", turn.text, turn.message_id)
            agent = self.store.log_message(turn.conversation_id, "agent", "")
            self.store.log_sentence(agent, "Let me check.")
            yield SentenceEvent("Let me check.")
            gate.wait(5)
            self.store.log_sentence(agent, "Your visit is on Monday.")
            yield SentenceEvent("Your visit is on Monday.")
            yield DoneEvent("scheduling", None)

    _, _, client = make(store, SlowEngine(store))
    message_id = new_id()
    post(client, "c1", "when is my visit", message_id)
    threading.Timer(0.3, gate.set).start()  # released while the stream is open
    events = stream(client, message_id)
    assert [data.get("text") for _, data in events] == ["Let me check.", "Your visit is on Monday.", None]


def test_a_message_left_unfinished_by_a_restart_streams_a_handoff_message(store):
    # The process stopped part-way: the caller message and one released sentence were saved, no done event.
    ConversationState.load(store, "c1", "visitor-1")
    store.log_message("c1", "caller", "book me a visit", "m-unfinished")
    store.log_sentence(store.log_message("c1", "agent", ""), "Let me find a time.")
    app, engine, _ = restarted(store)
    client = as_visitor(app, "visitor-1")
    events = stream(client, "m-unfinished")
    assert [data.get("text") for _, data in events] == ["Let me find a time.", ERROR_MESSAGE, None]
    assert events[-1][1]["outcome"] == "incomplete"
    assert stream(client, "m-unfinished") == events and engine.turns == []


def test_an_unknown_message_id_returns_404(store):
    _, _, client = make(store)
    assert client.get("/api/stream/nothing-here").status_code == 404


def test_a_reply_that_never_finishes_ends_its_stream_with_a_handoff(store):
    gate = threading.Event()

    class StuckEngine(FakeEngine):
        def handle(self, turn):
            gate.wait(5)
            yield DoneEvent("knowledge", None)

    _, _, client = make(store, StuckEngine(store), stream_timeout_s=0.2)
    message_id = new_id()
    post(client, "c1", "hello", message_id)
    events = stream(client, message_id)
    gate.set()
    assert [data.get("text") for _, data in events] == [ERROR_MESSAGE, None]
    assert events[-1][1]["outcome"] == "incomplete"


# -- Page --------------------------------------------------------------------------------------------------------

SEEDED = Path(__file__).resolve().parents[2] / "call_data" / "scheduling_db" / "customers.csv"


def page(store) -> str:
    _, _, client = make(store)
    response = client.get("/")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    assert response.headers["set-cookie"].startswith("meridian_visitor=")  # the first request sets the cookie
    return response.text


def test_the_greeting_says_what_the_assistant_can_do(store):
    greeting = re.search(r'<p class="greeting">(.*?)</p>', page(store), re.S).group(1)
    for promise in ("fees, memberships and warranties", "look up your account", "book or change an appointment"):
        assert promise in greeting


def test_the_four_test_customers_appear_with_one_fact_each_and_are_labelled_synthetic(store):
    html = page(store)
    card = re.search(r'<section class="test-customers"[^>]*>(.*?)</section>', html, re.S).group(1)
    assert "synthetic" in card.lower()
    seeded = {row["name"]: row["customer_id"] for row in csv.DictReader(SEEDED.open())}
    customers = re.findall(r'<li class="customer">(.*?)</li>', card, re.S)
    names = [re.search(r'<strong>(.*?)</strong>', item).group(1) for item in customers]
    assert names == ["Linda Foster", "Omar Patel", "Grace Okafor", "Daniel Reyes"]
    for name, item in zip(names, customers):
        assert seeded[name] in item  # the account number from the seeded scheduling database
        assert len(re.findall(r'class="fact"', item)) == 1


def test_four_to_six_suggested_question_buttons_only_fill_the_text_box(store):
    html = page(store)
    buttons = re.findall(r'<button type="button" class="suggestion" data-question="([^"]+)">', html)
    assert 4 <= len(buttons) <= 6
    assert re.search(r'<textarea id="message"', html) and 'src="/static/chat.js"' in html
    _, _, client = make(store)
    script = client.get("/static/chat.js").text
    handler = script.split("// Suggested questions: fill the text box only.")[1].split("// End of suggested questions.")[0]
    assert "box.value = button.dataset.question" in handler
    assert "send(" not in handler and "fetch(" not in handler and "submit" not in handler


# -- Receipts ----------------------------------------------------------------------------------------------------

def done_for(store, done: DoneEvent) -> dict:
    _, _, client = make(store, FakeEngine(store, lambda turn: (["Done."], done)))
    return say(client, new_id(), "go ahead")[1]


@pytest.mark.parametrize("action, proof", [
    ("booked appointment 201", "customer verified · eligibility checked · booked in one transaction"),
    ("rescheduled appointment 159", "customer verified · eligibility checked · rescheduled in one transaction"),
    ("cancelled appointment 159", "customer verified · cancelled in one transaction"),
])
def test_after_a_booking_change_the_done_event_carries_its_proof_receipt(store, action, proof):
    done = done_for(store, DoneEvent("scheduling", None, outcome="answered", db_actions=[action]))
    assert done["proof"] == proof


def test_after_a_handoff_the_done_event_says_which_ticket_was_created(store):
    done = done_for(store, DoneEvent("handoff", 12, outcome="handed_off"))
    assert (done["proof"], done["ticket"]) == ("ticket #12 created", 12)


def test_a_booking_with_a_ticket_carries_both_receipts(store):
    done = done_for(store, DoneEvent("scheduling", 7, db_actions=["booked appointment 201"]))
    assert done["proof"] == "customer verified · eligibility checked · booked in one transaction · ticket #7 created"


def test_a_plain_answer_or_a_lookup_has_no_proof_receipt(store):
    assert done_for(store, DoneEvent("knowledge", None))["proof"] is None
    assert done_for(store, DoneEvent("account", None, db_actions=["invoice lookup MHC-10002"]))["proof"] is None


# -- Review Focus 4: empty, very long and other-language messages -------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_an_empty_message_gets_a_request_for_more_without_calling_the_engine(store, text):
    _, engine, client = make(store)
    sentences, done = say(client, "c1", text)
    assert sentences == ["Could you tell me a bit more?"] and engine.turns == []
    assert done["proof"] is None


def test_a_2500_character_message_is_cut_to_2000_before_the_engine_and_the_reply_says_so(store):
    _, engine, client = make(store)
    text = "My furnace makes a rattling noise. " * 72  # 2,520 characters
    sentences, _ = say(client, "c1", text[:2500])
    assert engine.turns[0].text == text[:2000]
    assert "shortened" in sentences[0] and "2,000 characters" in sentences[0]
    assert sentences[1:] == [f"You said: {text[:40]}."]


def test_a_spanish_message_reaches_the_engine_unchanged_and_its_handoff_is_streamed(store):
    def reply(turn):  # as the real pipeline: another language is handed off with an English note (D47)
        assert other_language(turn.text)
        return [handoff_message(31, "other language", identified=False)], DoneEvent("handoff", 31, outcome="handed_off")

    _, engine, client = make(store, FakeEngine(store, reply))
    spanish = "¿Pueden enviar un técnico mañana? Mi aire acondicionado no funciona."
    sentences, done = say(client, "c1", spanish)
    assert engine.turns[0].text == spanish
    assert sentences[0].startswith("I can only help in English, so I've passed this to our team: Ticket #31.")
    assert done["proof"] == "ticket #31 created"


# -- Review Focus 5: tabs and reloads ----------------------------------------------------------------------------

def history(client, conversation_id):
    response = client.get(f"/api/conversation/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_two_tabs_with_one_cookie_keep_separate_histories(store):
    _, engine, client = make(store)
    say(client, "tab-a", "What does the tune-up cost?")
    say(client, "tab-b", "Is my system under warranty?")
    say(client, "tab-a", "And for members?")
    assert len({turn.visitor_id for turn in engine.turns}) == 1
    assert [m["text"] for m in history(client, "tab-a")["messages"]] == [
        "What does the tune-up cost?", "You said: What does the tune-up cost?.", "And for members?",
        "You said: And for members?."]
    assert [m["role"] for m in history(client, "tab-b")["messages"]] == ["caller", "agent"]


def test_reloading_with_the_same_conversation_id_returns_its_history_and_active_booking_step(store):
    def reply(turn):  # the scheduling flow has offered times and waits for a choice
        state = ConversationState.load(store, turn.conversation_id, turn.visitor_id)
        state.customer_id, state.active_flow, state.flow = "MHC-10001", "scheduling", {"step": "offer"}
        state.save(store)
        return ["I have Monday 8am to 12pm or Tuesday 1pm to 5pm. Which works?"], DoneEvent("scheduling", None)

    app, _, client = make(store, FakeEngine(store, reply))
    say(client, "c1", "Book a tune-up, Linda Foster MHC-10001")
    reloaded = client_for(app)
    reloaded.headers["cookie"] = f"meridian_visitor={client.cookies['meridian_visitor']}"
    saved = history(reloaded, "c1")
    assert [m["role"] for m in saved["messages"]] == ["caller", "agent"]
    assert saved["messages"][1]["text"].startswith("I have Monday")
    assert (saved["active_flow"], saved["step"]) == ("scheduling", "offer")
    assert saved["step_label"] == "Booking in progress: choosing a time"


def test_another_visitors_or_an_unknown_conversation_history_returns_404(store):
    app, _, alice = make(store)
    say(alice, "c1", "hello")
    assert client_for(app).get("/api/conversation/c1").status_code == 404
    assert alice.get("/api/conversation/never-used").status_code == 404

