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
    "two questions": clear(request("what's my balance", "account", "balance"), request("when is my appointment", "scheduling", "confirm")),
    "my membership": clear(request("what's my membership", "account", "membership")),
    "autopay": clear(request("set up autopay on my plan", "account", "balance")),
    "cancel my other": clear(request("cancel my other appointment", "scheduling", "cancel")),
    "earlier": {"clear": False, "requests": [request("anything earlier?", "handoff", "other")]},
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

    scripted = client.messages._client

    sent = [0]

    def say(text, conversation="c1"):
        sent[0] += 1
        events = list(engine.handle(Turn(conversation, "v1", f"m{sent[0]}", text)))
        return " ".join(e.text for e in events if isinstance(e, SentenceEvent)), events[-1]
    return {"say": say, "store": store, "db": db, "engine": engine,
            "routes_add": lambda key, value: scripted.routes.update({key: value})}


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


# Milestone 3 gate fixes.

def book_to_read_back(chat, when="Monday morning"):
    chat["say"](f"I'm Linda Foster, MHC-10001, I want to book a repair {when}")
    return chat["say"]("yes")


@pytest.mark.parametrize("hedge", ["ok wait, is there a fee?", "sure, but can it be Tuesday instead?", "yeah no, not that one",
                                   "yes?"])
def test_only_a_plain_yes_books(chat, hedge):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    reply, _ = chat["say"](hedge)
    assert count(chat["db"], "select count(*) from appointments") == before
    reply, _ = chat["say"]("Yes, please book it.")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


@pytest.mark.parametrize("plain", ["Book it.", "Um, yes.", "Yeah, that works.", "Take it.", "Perfect."])
def test_plain_confirmations_from_the_transcripts_book(chat, plain):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"](plain)
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_the_tuesday_one_picks_tuesday_and_never_reads_one_as_first():
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-20", "window": "12:00-16:00"},
               {"slot_date": "2026-10-20", "window": "13:00-17:00"}]
    assert _pick("I'll take the Tuesday one", choices, SETTINGS.now) == choices[1]
    assert _pick("the one on Tuesday", choices, SETTINGS.now) == choices[1]
    assert _pick("Tuesday 1 to 5", choices, SETTINGS.now) == choices[2]
    assert _pick("the second one", choices, SETTINGS.now) == choices[1]
    assert _pick("hmm", choices, SETTINGS.now) is None


def test_a_calendar_date_during_an_offer_offers_that_date(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("how about October 22 in the morning")
    assert "2026-10-22" in reply


def test_a_reschedule_to_a_named_date_offers_that_date(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, can you move my appointment")
    reply, _ = chat["say"]("the 28th please")
    assert "2026-10-28" in reply


def test_every_waiting_request_is_answered_once_the_caller_is_identified(chat):
    reply, _ = chat["say"]("two questions: what's my balance and when is my appointment")
    assert reply.count("account number") == 1
    reply, _ = chat["say"]("Linda Foster MHC-10001")
    assert "no open invoices" in reply.lower() and "2026-10-22" in reply
    reply, done = chat["say"]("and what's my membership")
    assert "Standard" in reply and "2026-10-22" not in reply


def test_a_capacity_decline_names_the_service_and_closes_the_flow(chat):
    chat["routes_add"]("plumber", clear(request("I want to book a plumber for my sink", "scheduling", "book", "plumbing")))
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a plumber for my sink")
    assert "plumbing" in reply and "hvac" not in reply.lower() and done.outcome == "declined"
    reply, _ = chat["say"]("how much is a tune-up cost")
    assert "$129" in reply


def test_a_failed_cancel_is_reported_plainly(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, cancel my appointment")
    sqlite3.connect(chat["db"]).execute("update appointments set status = 'cancelled' where appointment_id = 159").connection.commit()
    reply, _ = chat["say"]("yes")
    assert "Cancelled" not in reply and "nothing was changed" in reply


def test_an_unavailable_operations_database_still_answers_with_a_plain_message(chat, caplog):
    import logging
    store = chat["store"]
    store._db.close()
    with caplog.at_level(logging.ERROR):
        reply, done = chat["say"]("what does the membership include")
    assert "phone our office" in reply and done.outcome == "error"
    assert "turn failed" in caplog.text


def test_a_committed_booking_is_confirmed_even_if_logging_the_reply_fails(chat, monkeypatch):
    book_to_read_back(chat)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(chat["store"], "log_sentence", broken)
    reply, done = chat["say"]("yes")
    assert "Marta Kowalski" in reply and any("booked appointment" in a for a in done.db_actions)


def test_a_booking_is_not_committed_once_the_message_deadline_has_passed(chat, monkeypatch):
    import app.flows.scheduling as scheduling
    book_to_read_back(chat)
    before = count(chat["db"], "select count(*) from appointments")
    monkeypatch.setattr(scheduling, "_deadline_passed", lambda: True)
    reply, done = chat["say"]("yes")
    assert count(chat["db"], "select count(*) from appointments") == before and done.outcome == "handed_off"


def test_the_emergency_advice_comes_before_the_ticket(chat, monkeypatch):
    order = []
    original = chat["store"].create_ticket
    monkeypatch.setattr(chat["store"], "log_sentence", lambda m, t: order.append("sentence"))
    monkeypatch.setattr(chat["store"], "create_ticket", lambda *a, **k: order.append("ticket") or original(*a, **k))
    chat["say"]("I smell gas")
    assert order.index("sentence") < order.index("ticket")


def test_an_idle_conversation_mid_flow_is_abandoned_and_the_caller_can_end_a_chat(chat):
    store = chat["store"]
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    store._write("update conversations set last_message_at = '2000-01-01T00:00:00' where conversation_id = 'c1'")
    chat["say"]("how much is a tune-up cost", conversation="c2")
    assert store.conversation("c1")["status"] == "abandoned"
    reply, done = chat["say"]("No, that's it. Thanks.", conversation="c2")
    assert done.outcome == "ended" and store.conversation("c2")["status"] == "closed"


def test_the_dispute_ticket_carries_the_fee_mismatch_and_the_lookup(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    chat["store"]  # the silent review exists; now the caller disputes
    chat["routes_add"]("that fee is wrong", clear(request("that after-hours fee is wrong", "handoff", "dispute")))
    chat["say"]("that fee is wrong")
    dispute = [t for t in chat["store"].tickets() if t["reason_tag"] == "dispute"][0]
    assert "after-hours dispatch 144.00 vs schedule 149.00" in dispute["constraints"]
    assert "invoice" in dispute["tried"]


def test_receipts_keep_dated_passages_excluded_documents_and_the_route_label(chat):
    chat["say"]("how much is a tune-up cost")
    [receipt] = chat["store"]._rows("select * from receipts")
    assert "2026-02-10" in receipt["passages"] and receipt["route"] == "knowledge, clear"
    assert receipt["excluded"] is not None


def test_another_visitor_cannot_continue_a_conversation(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    events = list(chat["engine"].handle(Turn("c1", "someone-else", "mx", "yes")))
    assert events[-1].outcome == "forbidden" and count(chat["db"], "select count(*) from appointments where customer_id='MHC-10001'") == 1


def test_an_action_request_misrouted_as_an_account_question_is_still_handed_off(chat):
    _, done = chat["say"]("I'm Linda Foster, MHC-10001, set up autopay on my plan")
    assert chat["store"].tickets()[-1]["reason_tag"] == "action gap"


def test_a_caller_wanting_earlier_than_the_earliest_slot_gets_an_earlier_slot_ticket(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair")
    reply, done = chat["say"]("anything earlier?")
    assert chat["store"].tickets()[-1]["reason_tag"] == "earlier slot"


def test_switching_to_cancelling_another_appointment_mid_booking_is_a_new_topic(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("actually, cancel my other appointment instead")
    assert "cancelling" in reply and "2026-10-22" in reply


def test_the_identity_prompt_does_not_count_ages_or_system_counts_as_addresses(chat):
    from app.flows.identify import has_identifier
    assert not has_identifier("my unit is 15 years old way past warranty")
    assert not has_identifier("I have 2 systems at my place")
    assert has_identifier("4412 Oak Hollow Dr")


def test_a_question_during_a_reschedule_offer_keeps_the_offer_and_states_the_fee(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, can you move my appointment")
    reply, _ = chat["say"]("the 28th please")
    assert "2026-10-28" in reply and "no late fee" in reply.lower()
    reply, _ = chat["say"]("ok wait, is there a fee?")
    assert "2026-10-28" in reply and "2026-10-19" not in reply


def test_a_goodbye_ends_the_chat_even_mid_flow(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, done = chat["say"]("No, that's it. Thanks.")
    assert done.outcome == "ended" and chat["store"].conversation("c1")["status"] == "closed"
