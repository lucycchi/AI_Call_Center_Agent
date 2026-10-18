import shutil
import sqlite3
from pathlib import Path

import pytest

from app.config import SETTINGS
from app.core.engine import Engine
from app.core.model_log import RecordingClient
from app.core.pipeline import AgentPipeline
from app.core.types import DoneEvent, SentenceEvent, Turn
from app.knowledge.index import Chunk
from app.knowledge.search import ScoredChunk
from app.ops.store import OpsStore
from app.replies.writer import write
from app.routing.router import route
from app.safety.replies import fixed_reply
from tests.flows.scripted import ScriptedClient, request

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"


def clear(*requests):
    return {"clear": True, "requests": list(requests)}


ROUTES = {
    "my balance": clear(request("what's my balance", "account", "balance")),
    "payment link": clear(request("send me a payment link", "account", "action")),
    "book": clear(request("I want to book a repair", "scheduling", "book", "hvac_repair")),
    "same thing again": clear(request("you fixed my blower and it's doing the same thing again", "scheduling", "book",
                                      "hvac_repair")),
    "move my appointment": clear(request("move my appointment", "scheduling", "reschedule")),
    "cancel my appointment": clear(request("cancel my appointment", "scheduling", "cancel")),
    "tune-up cost": clear(request("how much is a tune-up", "knowledge")),
}
TUNE_UP = Chunk("services__service_catalog#3", "services/service_catalog.md", "Maintenance tune-up", "2026-02-10",
                "$129 for non-members (one system). Included for Comfort Club members.", 22, 25)


class FakeSearcher:
    def search(self, question, mode="combined", k=5):
        return [ScoredChunk(TUNE_UP, 0.72, 4.0)]


@pytest.fixture
def chat(tmp_path):
    db = tmp_path / "scheduling.sqlite"
    shutil.copy(SEED, db)
    store = OpsStore(tmp_path / "ops.sqlite")
    client = RecordingClient(ScriptedClient(dict(ROUTES)), sdk_version="anthropic test")
    pipeline = AgentPipeline(store=store, scheduling_db=db, seed_db=SEED, searcher=FakeSearcher(),
                             route_fn=lambda text, history: route(text, history, client),
                             writer=lambda reply_type, facts, history: write(reply_type, facts, history, client),
                             threshold=0.4)
    engine = Engine(pipeline)

    def say(text, conversation="c1"):
        events = list(engine.handle(Turn(conversation, "v1", f"m{len(store.tickets())}{text[:8]}", text)))
        return " ".join(e.text for e in events if isinstance(e, SentenceEvent)), events[-1]
    return {"say": say, "store": store, "db": db}


def count(db, sql, *args):
    return sqlite3.connect(db).execute(sql, args).fetchone()[0]


def test_two_failed_identity_attempts_hand_off_and_a_new_customer_is_handed_off_to_be_set_up(chat):
    chat["say"]("what's my balance")
    chat["say"]("Linda Foster, MHC-99999")
    _, done = chat["say"]("Linda Foster, MHC-99999")
    assert done.outcome == "handed_off" and chat["store"].tickets()[-1]["reason_tag"] == "not identified"
    chat["say"]("what's my balance", conversation="c2")
    _, done = chat["say"]("I'm new, Sam Lee, 12 Main St, Austin", conversation="c2")
    assert done.outcome == "handed_off" and chat["store"].tickets()[-1]["reason_tag"] == "new customer"


def test_omar_hears_his_balance_and_a_silent_billing_review_opens(chat):
    reply, done = chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    for part in ("$478.00", "1 November", "Diagnostic visit $89.00", "Contactor replacement $245.00", "After-hours dispatch $144.00"):
        assert part in reply, part
    assert done.ticket is None and "Ticket #" not in reply
    [review] = chat["store"].tickets()
    assert (review["reason_tag"], review["priority"], review["conversation_id"]) == ("billing review", 0, None)


def test_a_payment_link_request_is_an_action_gap_handoff(chat):
    _, done = chat["say"]("I'm Omar Patel, MHC-10002. Send me a payment link")
    assert done.outcome == "handed_off" and chat["store"].tickets()[-1]["reason_tag"] == "action gap"


def test_a_manor_caller_is_told_the_area_is_served_and_handed_off(chat):
    sqlite3.connect(chat["db"]).execute(
        "insert into customers values ('MHC-00042','Pat Kim','512-555-0142',null,'5 Elm Way','Manor','78653','none',null,"
        "'Trane','2021-01-01')").connection.commit()
    reply, done = chat["say"]("I'm Pat Kim, MHC-00042, I want to book a repair")
    assert "Manor is in our service area" in reply and done.outcome == "declined" and done.ticket


def test_a_booking_changes_nothing_until_a_clear_yes(chat):
    before = count(chat["db"], "select count(*) from appointments")
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    assert "2026-10-19, 08:00-12:00" in reply
    reply, _ = chat["say"]("yes")
    assert "Read back" in reply and "hvac repair" in reply and "2026-10-19, 08:00-12:00" in reply
    reply, _ = chat["say"]("maybe")
    assert "clear yes" in reply and count(chat["db"], "select count(*) from appointments") == before
    chat["say"]("yes")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_a_repeat_repair_claim_is_booked_normally_with_a_warranty_review_ticket(chat):
    chat["say"]("I'm Linda Foster, MHC-10001. You fixed my blower and it's doing the same thing again, Monday morning")
    chat["say"]("yes")
    reply, done = chat["say"]("yes")
    assert "no diagnostic fee if the technician confirms" in reply
    appointment = int(done.db_actions[0].rsplit(" ", 1)[1])
    assert count(chat["db"], "select is_warranty_visit from appointments where appointment_id = ?", appointment) == 0
    review = chat["store"].tickets()[-1]
    assert (review["reason_tag"], review["appointment_id"], review["priority"]) == ("warranty review", appointment, 0)


def test_a_caller_with_two_appointments_is_asked_which_one(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    chat["say"]("yes")
    chat["say"]("yes")
    reply, _ = chat["say"]("can you move my appointment")
    assert "which appointment" in reply.lower() and "2026-10-19" in reply and "2026-10-22" in reply


def test_a_double_yes_cancels_once(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, cancel my appointment")
    chat["say"]("yes")
    _, done = chat["say"]("yes")
    assert count(chat["db"], "select count(*) from appointments where status = 'cancelled' and customer_id = 'MHC-10001'") == 1
    assert count(chat["db"], "select status = 'open' from appointment_slots where slot_id = 159") == 1


def test_urgent_and_danger_replies(chat):
    reply, done = chat["say"]("No heat and it's freezing")
    assert reply.startswith(fixed_reply("urgent", "no heat")[0]) and done.ticket
    assert chat["store"].tickets()[-1]["priority"] == 2
    reply, _ = chat["say"]("I smell gas", conversation="c2")
    for line in fixed_reply("danger"):
        assert line in reply


def test_a_booking_conversation_is_fully_logged(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, phone 512-555-0101, I want to book a repair Monday morning")
    chat["say"]("yes")
    chat["say"]("yes")
    store = chat["store"]
    messages = store._rows("select * from messages order by message_id")
    assert all("512-555-0101" not in m["text_masked"] for m in messages) and any("[phone]" in m["text_masked"] for m in messages)
    agent = [m for m in messages if m["role"] == "agent"]
    assert all(m["full_reply_ms"] is not None and m["first_sentence_ms"] is not None for m in agent)
    assert all(m["cost_microdollars"] > 0 for m in agent)
    receipts = store._rows("select * from receipts")
    assert receipts and all(r["route"] for r in receipts)
    assert any("booked appointment" in (r["db_action"] or "") for r in receipts)
    calls = store._rows("select * from model_calls")
    assert {c["purpose"] for c in calls} == {"route", "write"}
    assert all(c["model_id"] in (SETTINGS.router_model, SETTINGS.writer_model) and c["settings"] and c["microdollars"] > 0
               for c in calls)


def test_a_knowledge_answer_logs_its_passages(chat):
    chat["say"]("how much is a tune-up cost")
    [receipt] = chat["store"]._rows("select * from receipts")
    assert "services/service_catalog.md" in receipt["passages"]
