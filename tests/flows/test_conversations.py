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
                             threshold=0.4, money_check=lambda s, p: True)
    engine = Engine(pipeline)

    scripted = client.messages._client

    sent = [0]

    def say(text, conversation="c1"):
        sent[0] += 1
        events = list(engine.handle(Turn(conversation, "v1", f"m{sent[0]}", text)))
        return " ".join(e.text for e in events if isinstance(e, SentenceEvent)), events[-1]
    return {"say": say, "store": store, "db": db, "engine": engine,
            "routes_add": lambda key, value: scripted.routes.update({key: value}),
            "writer_says": lambda rewrite: setattr(scripted, "rewrite", rewrite)}


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
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
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
    store._write("update messages set created_at = '2000-01-01T00:00:00' where conversation_id = 'c1'")
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


# Review of the milestone 3 fixes.

def test_a_safety_message_after_a_goodbye_still_gets_the_safety_reply(chat):
    chat["say"]("No, that's it. Thanks.")
    reply, done = chat["say"]("actually wait, I smell gas now")
    assert fixed_reply("danger")[0] in reply and done.ticket and done.outcome == "safety"


def test_ok_all_set_at_a_read_back_does_not_end_the_chat(chat):
    book_to_read_back(chat)
    _, done = chat["say"]("Ok, all set")
    assert done.outcome != "ended"


def test_a_yes_naming_another_day_does_not_confirm(chat):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"]("Yes, Tuesday works")
    assert count(chat["db"], "select count(*) from appointments") == before


def test_picking_by_number(chat):
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-19", "window": "12:00-16:00"},
               {"slot_date": "2026-10-19", "window": "13:00-17:00"}]
    for text, index in (("2", 1), ("two please", 1), ("I'll take the 2nd one", 1), ("the 1st one please", 0),
                        ("the 3rd option", 2), ("number 3", 2)):
        assert _pick(text, choices, SETTINGS.now) == choices[index], text
    assert _pick("November 2", choices, SETTINGS.now) is None


def test_a_booking_is_confirmed_in_code_even_when_the_writer_then_fails(chat, monkeypatch):
    import app.replies.writer as writer_module
    book_to_read_back(chat)
    monkeypatch.setattr(writer_module, "split_sentences", lambda chunks: (_ for _ in ()).throw(RuntimeError("writer down")))
    reply, done = chat["say"]("yes")
    assert "Booked" in reply and "Marta Kowalski" in reply


def test_a_booking_is_confirmed_even_when_the_warranty_review_ticket_fails(chat, monkeypatch):
    chat["say"]("I'm Linda Foster, MHC-10001. You fixed my blower and it's doing the same thing again, Monday morning")
    chat["say"]("yes")
    original = chat["store"].create_ticket

    def failing(*args, **kwargs):
        if "warranty review" in (*args, *kwargs.values()):
            raise sqlite3.OperationalError("disk full")
        return original(*args, **kwargs)
    monkeypatch.setattr(chat["store"], "create_ticket", failing)
    reply, _ = chat["say"]("yes")
    assert "Booked" in reply


def test_a_failed_billing_review_is_tried_again_next_time(chat, monkeypatch):
    calls = []
    original = chat["store"].create_ticket

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise sqlite3.OperationalError("locked")
        return original(*args, **kwargs)
    monkeypatch.setattr(chat["store"], "create_ticket", flaky)
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    chat["say"]("what's my balance again")
    assert [t["reason_tag"] for t in chat["store"].tickets()].count("billing review") == 1


def test_a_failed_state_save_gives_the_phone_the_office_message(chat, monkeypatch):
    def broken(*args):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(chat["store"], "save_state", broken)
    reply, done = chat["say"]("how much is a tune-up cost")
    assert "phone our office" in reply and done.outcome == "error"


def test_billing_notes_stay_on_billing_tickets_and_one_earlier_slot_ticket_per_conversation(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    chat["say"]("I smell gas")
    emergency = chat["store"].tickets()[-1]
    assert emergency["reason_tag"] == "emergency" and "fee differs" not in emergency["constraints"]
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair", conversation="c2")
    chat["say"]("anything earlier?", conversation="c2")
    chat["say"]("anything earlier?", conversation="c2")
    assert [t["reason_tag"] for t in chat["store"].tickets()].count("earlier slot") == 1


def test_receipts_use_the_plain_labels(chat):
    chat["say"]("how much is a tune-up cost")
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?", conversation="c2")
    chat["say"]("I'm Omar Patel, MHC-10002. Send me a payment link", conversation="c3")
    labels = [r["outcome_label"] for r in chat["store"]._rows("select outcome_label from receipts order by message_id")]
    assert labels == ["supported by documents", "supported by account records", "handoff required"]


@pytest.mark.parametrize("text", ["no, cancel my other appointment instead", "yes, and cancel my other appointment"])
def test_a_yes_or_no_before_a_new_scheduling_action_still_switches(chat, text):
    chat["routes_add"]("cancel my other", clear(request("cancel my other appointment", "scheduling", "cancel")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"](text)
    assert "cancelling" in reply


def test_the_action_backstop_covers_misrouted_knowledge_and_scheduling_requests(chat):
    chat["routes_add"]("autopay set", clear(request("set up autopay for my membership", "knowledge")))
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. autopay set up please")
    assert chat["store"].tickets()[-1]["reason_tag"] == "action gap"
    chat["routes_add"]("pay by card", clear(request("can I pay by card over the phone", "knowledge")))
    _, done = chat["say"]("can I pay by card over the phone?", conversation="c2")
    assert done.outcome == "answered"


def test_the_writer_is_stopped_at_the_message_deadline(tmp_path):
    import time

    from app.core.types import Turn as T
    db = tmp_path / "s.sqlite"
    shutil.copy(SEED, db)

    def slow_writer(reply_type, facts, history):
        for n in range(5):
            yield f"Sentence {n}."
            time.sleep(0.1)
    pipeline = AgentPipeline(store=OpsStore(tmp_path / "ops.sqlite"), scheduling_db=db, seed_db=SEED, searcher=FakeSearcher(),
                             route_fn=lambda text, history: route(text, history, RecordingClient(ScriptedClient(dict(ROUTES)), "x")),
                             writer=slow_writer, threshold=0.4, deadline_s=0.15,
                             money_check=lambda s, p: True)
    events = list(Engine(pipeline).handle(T("c1", "v1", "m1", "how much is a tune-up cost")))
    texts = [e.text for e in events if isinstance(e, SentenceEvent)]
    assert "Sentence 4." not in texts and events[-1].outcome == "handed_off"




# Second review of the fixes.

def test_a_named_day_narrows_the_choices_before_an_ordinal():
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-20", "window": "08:00-12:00"},
               {"slot_date": "2026-10-21", "window": "12:00-16:00"}]
    assert _pick("first thing in the morning on Tuesday please", choices, SETTINGS.now) == choices[1]
    assert _pick("Wednesday the 21st, not the first one", choices, SETTINGS.now) == choices[2]
    assert _pick("the second one", choices, SETTINGS.now) == choices[1]


def test_a_yes_restating_the_read_back_books_and_one_naming_another_window_does_not(chat):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"]("yes, 12 to 4 works")
    assert count(chat["db"], "select count(*) from appointments") == before
    chat["say"]("Yes, Monday morning is fine")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_yes_please_confirm_it_at_a_read_back_books(chat):
    chat["routes_add"]("please confirm it", clear(request("yes, please confirm it", "scheduling", "confirm")))
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"]("Yes, please confirm it")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_a_failed_warranty_review_ticket_is_retried_on_the_next_message(chat, monkeypatch):
    chat["say"]("I'm Linda Foster, MHC-10001. You fixed my blower and it's doing the same thing again, Monday morning")
    chat["say"]("yes")
    original = chat["store"].create_ticket
    failed = [False]

    def flaky(*args, **kwargs):
        if "warranty review" in (*args, *kwargs.values()) and not failed[0]:
            failed[0] = True
            raise sqlite3.OperationalError("disk full")
        return original(*args, **kwargs)
    monkeypatch.setattr(chat["store"], "create_ticket", flaky)
    chat["say"]("yes")
    assert not [t for t in chat["store"].tickets() if t["reason_tag"] == "warranty review"]
    chat["say"]("thanks")
    assert [t for t in chat["store"].tickets() if t["reason_tag"] == "warranty review"]


def test_a_receipt_that_cannot_be_saved_twice_gives_the_phone_the_office_message(chat, monkeypatch):
    def broken(*args):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(chat["store"], "log_receipt", broken)
    reply, done = chat["say"]("how much is a tune-up cost")
    assert "phone our office" in reply


def test_membership_action_tickets_do_not_carry_invoice_notes(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    chat["routes_add"]("cancel my membership", clear(request("cancel my membership", "account", "action")))
    chat["say"]("please cancel my membership")
    ticket = chat["store"].tickets()[-1]
    assert ticket["reason_tag"] == "action gap" and "fee differs" not in ticket["constraints"]


def test_fixed_sentences_read_naturally(chat):
    from app.handoff.flow import confirm_booking
    from app.scheduling.transactions import BookingResult
    result = confirm_booking({"store": chat["store"]}, BookingResult("booked", 7, "Marta Kowalski", False, False),
                             "2026-10-19", "08:00-12:00", "hvac_repair")
    assert result.facts[0] == "Booked: your HVAC repair visit on Monday, October 19, 8am to 12pm, with Marta Kowalski."
    chat["say"]("I'm Linda Foster, MHC-10001, cancel my appointment")
    sqlite3.connect(chat["db"]).execute("update appointments set status = 'cancelled' where appointment_id = 159").connection.commit()
    reply, _ = chat["say"]("yes")
    assert "Would you like me to check your appointments again?" in reply and "Offer to" not in reply


@pytest.mark.parametrize("text", ["No, I'm good, thanks", "nope, i'm good"])
def test_im_good_ends_the_chat(chat, text):
    _, done = chat["say"](text)
    assert done.outcome == "ended"


def test_a_yes_to_an_offer_routed_as_confirm_picks_the_slot(chat):
    chat["routes_add"]("tuesday morning is fine", clear(request("yes, Tuesday morning is fine", "scheduling", "confirm")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair first thing in the morning on Tuesday please")
    reply, _ = chat["say"]("Yes, Tuesday morning is fine")
    assert "Read back" in reply and "Tuesday" in reply


# Third review of the fixes.

@pytest.mark.parametrize("text, window, expected", [
    ("yes, 12-4 works", "08:00-12:00", False), ("Yes, Monday at 1 works", "08:00-12:00", False),
    ("yes, 8-12 is fine", "08:00-12:00", True), ("yes, 12–4 works", "12:00-16:00", True),
    ("Yes, noon to four works", "08:00-12:00", False)])
def test_a_yes_naming_a_time_in_any_form_must_match_the_read_back(text, window, expected):
    from app.flows.scheduling import confirms
    assert confirms(text, "2026-10-19", window, SETTINGS.now) is expected


def test_okay_im_good_at_a_read_back_does_not_end_the_chat_but_a_curly_im_good_does_after(chat):
    book_to_read_back(chat)
    _, done = chat["say"]("Okay, I'm good")
    assert done.outcome != "ended"
    _, done = chat["say"]("I’m good, thanks", conversation="c2")
    assert done.outcome == "ended"


def test_may_i_have_the_2nd_one_picks_slot_two():
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-19", "window": "12:00-16:00"}]
    assert _pick("May I have the 2nd one?", choices, SETTINGS.now) == choices[1]


def test_a_failed_warranty_review_is_kept_in_a_fallback_file_and_saved_on_restart(tmp_path, monkeypatch):
    store = OpsStore(tmp_path / "ops.sqlite")
    original = store.create_ticket

    def failing(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(store, "create_ticket", failing)
    store.create_ticket_or_keep(conversation_id=None, who="Linda Foster, MHC-10001", wants="repeat repair claim",
                                tried="booked appointment 160", constraints="warranty not verifiable", mood="",
                                reason_tag="warranty review", appointment_id=160)
    assert store.tickets() == []
    monkeypatch.setattr(store, "create_ticket", original)
    restarted = OpsStore(tmp_path / "ops.sqlite")
    assert [t["reason_tag"] for t in restarted.tickets()] == ["warranty review"]


def test_tags_are_remembered_only_when_the_ticket_was_saved(chat, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("locked")
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair")
    monkeypatch.setattr(chat["store"], "create_ticket", broken)
    chat["say"]("anything earlier?")
    monkeypatch.undo()
    chat["say"]("anything earlier?")
    assert [t["reason_tag"] for t in chat["store"].tickets()].count("earlier slot") == 1


def test_a_message_with_almost_no_time_left_stops_before_a_model_call():
    from app.core import deadline
    token = deadline.start(0.001)
    try:
        import time
        time.sleep(0.002)
        with pytest.raises(deadline.DeadlinePassed):
            deadline.per_attempt()
    finally:
        deadline.DEADLINE.reset(token)


def test_a_cancel_request_routed_as_a_redirect_is_still_an_action_gap(chat):
    chat["routes_add"]("cancel my membership now", clear(request("cancel my membership now", "redirect", "wrong number")))
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. cancel my membership now")
    assert chat["store"].tickets()[-1]["reason_tag"] == "action gap"


# Found by the first harness run.

def test_messages_after_a_handoff_are_added_to_the_open_ticket_not_new_tickets(chat):
    chat["routes_add"]("not what i agreed", clear(request("the invoice is not what I agreed to", "handoff", "dispute")))
    chat["routes_add"]("robert", clear(request("it's Robert Chen", "handoff", "dispute")))
    chat["routes_add"]("fine", clear(request("Fine.", "handoff", "dispute")))
    chat["say"]("The tech quoted me $89 and the invoice says $149. That's not what I agreed to.")
    reply, done = chat["say"]("Um, sure, it's Robert Chen, 512-311-4666.")
    assert "Ticket #1" in reply and "added" in reply
    chat["say"]("Fine.")
    tickets = chat["store"].tickets()
    assert len(tickets) == 1 and len(chat["store"].ticket_messages(1)) == 2
    reply, done = chat["say"]("I smell gas")
    assert len(chat["store"].tickets()) == 2 and chat["store"].tickets()[-1]["priority"] == 2


def test_an_unavailable_requested_day_is_said_plainly_in_the_offer(chat):
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair tomorrow, 12 to 4")
    assert "Saturday, October 17, 12pm to 4pm is not available" in reply


def test_the_writer_knows_today():
    from tests.replies.test_checks import FakeClient
    client = FakeClient(["Ok."])
    list(__import__("app.replies.writer", fromlist=["write"]).write("policy answer", ["fact"], [], client))
    assert "Friday 16 October 2026" in client.calls[0]["system"]


def test_the_router_is_told_that_asking_whether_something_can_be_done_is_a_question():
    from app.routing.router import RULES
    assert "whether or how" in RULES


def test_clock_times_pick_and_confirm_the_right_window(chat):
    from app.flows.scheduling import _pick, confirms
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-19", "window": "12:00-16:00"}]
    assert _pick("Monday 12:00 PM to 4:00 PM is fine, thanks.", choices, SETTINGS.now) == choices[1]
    assert confirms("Yes, 12:00 PM to 4:00 PM is right.", "2026-10-19", "12:00-16:00", SETTINGS.now) is True
    assert confirms("Yes, 12:00 PM to 4:00 PM is right.", "2026-10-19", "08:00-12:00", SETTINGS.now) is False


def test_booking_the_same_service_again_that_day_moves_the_first_visit(chat):
    book_to_read_back(chat)
    chat["say"]("yes")
    chat["routes_add"]("afternoon instead", clear(request("book Monday afternoon instead", "scheduling", "book", "hvac_repair")))
    reply, _ = chat["say"]("Can you book Monday afternoon instead, 12 to 4")
    reply, _ = chat["say"]("yes")
    assert "moving" in reply.lower()
    chat["say"]("yes")
    rows = sqlite3.connect(chat["db"]).execute(
        "select s.window from appointments a join appointment_slots s using (slot_id) where a.customer_id = 'MHC-10001' "
        "and a.status = 'scheduled' and s.slot_date = '2026-10-19'").fetchall()
    assert rows == [("12:00-16:00",)]


def test_a_caller_who_identifies_in_a_knowledge_question_is_not_asked_again(chat):
    chat["say"]("I'm Linda Foster, MHC-10001. How much is a tune-up cost?")
    reply, _ = chat["say"]("I want to book a repair Monday morning")
    assert "account number" not in reply and "2026-10-19" in reply


# Found by the rehearsal.

def test_a_duplicate_request_is_never_queued_twice(chat):
    chat["routes_add"]("can i move it", clear(request("I have a tech coming", "scheduling", "reschedule"),
                                               request("can I move it", "scheduling", "reschedule")))
    chat["say"]("I'm Linda Foster, MHC-10001. Something came up, can I move it?")
    reply, _ = chat["say"]("next Tuesday morning")
    reply, _ = chat["say"]("yes")
    reply, _ = chat["say"]("yes")
    assert "Moved" in reply and "offer" not in reply.lower()


def test_an_unidentified_handoff_asks_for_details_and_the_ticket_gets_them(chat):
    chat["routes_add"]("talk to a manager", clear(request("I want to talk to a manager", "handoff", "complaint")))
    reply, _ = chat["say"]("I want to talk to a manager.")
    assert "name" in reply and "account number" in reply
    chat["say"]("Sure, it's Linda Foster, 512-555-0101. Please call me today.")
    ticket = chat["store"].tickets()[-1]
    assert ticket["who"] == "Linda Foster, MHC-10001"


def test_an_account_number_and_a_name_in_separate_messages_identify_the_caller(chat):
    chat["say"]("what's my balance")
    chat["say"]("Yeah, it's MHC-10002.")
    reply, _ = chat["say"]("Um, Omar Patel.")
    assert "$478.00" in reply


def test_the_grader_sees_messages_added_to_a_ticket(tmp_path):
    from eval.grade_conversations import default_tickets
    from eval.harness import Attempt
    db = tmp_path / "c-1.sqlite"
    db.write_bytes(b"")
    store = OpsStore(tmp_path / "c-1-ops.sqlite")
    store.open_conversation("v", "c")
    ticket = store.create_ticket("c", "x", "manager", "", "", "", "complaint")
    store.append_to_ticket(ticket, store.log_message("c", "caller", "call me today, not next week"))
    [seen] = default_tickets(Attempt("c", db_path=str(db)))
    assert seen["later_messages"] == ["call me today, not next week"]


def test_the_router_is_told_another_business_name_is_a_wrong_number():
    from app.routing.router import RULES
    assert "a different business" in RULES


def test_a_message_that_only_gives_details_is_answered_not_handed_off(chat):
    reply, done = chat["say"]("Linda Foster, 4412 Oak Hollow Dr, Round Rock.")
    assert done.ticket is None and "found your account" in reply


def test_a_warranty_claim_routed_to_booking_also_gets_the_coverage_answer(chat):
    chat["routes_add"]("warranty claim", clear(request("I need to file a warranty claim", "scheduling", "book", "hvac_repair")))
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001. I need to file a warranty claim, the unit stopped working.")
    assert "$129" in reply or "Maintenance tune-up" in reply or "source" in reply.lower()  # the knowledge facts came too
    assert "2026-10-" in reply  # and the booking offer


def test_the_router_treats_questions_about_my_own_membership_as_account_questions():
    from app.routing.router import RULES
    assert "when their own membership renews or charges" in RULES


# Found by the quick test run.

def test_filler_lines_never_open_a_ticket_and_repeat_an_open_offer(chat):
    for line in ("Hold on, my dog is barking.", "Can you hear me okay?", "Sorry, I'm driving, one sec."):
        _, done = chat["say"](line, conversation="f1")
        assert done.ticket is None
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning", conversation="f2")
    reply, done = chat["say"]("Sorry, you cut out for a second there. Could you repeat that?", conversation="f2")
    assert "2026-10-19" in reply and "Read back" not in reply and done.ticket is None


def test_for_a_second_is_not_the_second_slot():
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-21", "window": "08:00-12:00"}]
    assert _pick("Sorry, you cut out for a second there. Could you repeat that?", choices, SETTINGS.now) is None
    assert _pick("the second one", choices, SETTINGS.now) == choices[1] and _pick("second please", choices, SETTINGS.now) == choices[1]


def test_anything_earlier_at_a_read_back_offers_earlier_slots(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Thursday 8 to 12")
    chat["say"]("the first one")
    reply, _ = chat["say"]("Um, can you do anything earlier?")
    assert "2026-10-19" in reply


def test_rebooking_moves_only_a_visit_booked_in_this_chat(chat):
    sqlite3.connect(chat["db"]).execute(
        "update appointment_slots set status='booked' where slot_id=42").connection.commit()
    sqlite3.connect(chat["db"]).execute("insert into appointments (slot_id, customer_id, issue_description, created_at, status) "
                                        "values (42, 'MHC-10001', 'seeded', '2026-10-10', 'scheduled')").connection.commit()
    book_to_read_back(chat)
    reply, _ = chat["say"]("yes")
    assert "Booked" in reply and "Moved" not in reply


def test_later_ticket_notes_are_confirmed_without_repeating_the_promise(chat):
    chat["routes_add"]("talk to a manager", clear(request("I want to talk to a manager", "handoff", "complaint")))
    chat["say"]("I'm Linda Foster, MHC-10001. I want to talk to a manager.")
    reply, _ = chat["say"]("I need someone to call me today.")
    assert "added" in reply and "Ticket #1" in reply
    reply2, _ = chat["say"]("Please make sure it's today.")
    assert reply2 != reply or "within one business day" not in reply2


def test_the_final_price_line_is_only_for_repair_and_service_prices():
    from app.flows.knowledge import answer
    from app.knowledge.index import Chunk
    from app.knowledge.search import ScoredChunk

    class Only:
        def __init__(self, document):
            self.document = document

        def search(self, question, mode="combined", k=5):
            return [ScoredChunk(Chunk("x#1", self.document, "Plans", "", "$189 a year", 1, 2), 0.7, 2)]
    assert "final price" not in " ".join(answer("how much is the plan", Only("membership/comfort_club_overview.md"), 0.25).facts)
    assert "final price" in " ".join(answer("how much is drain clearing", Only("services/service_catalog.md"), 0.25).facts)


def test_facts_that_do_not_answer_the_question_are_said_then_handed_off_with_a_ticket(chat):
    from app.replies.checks import NOT_IN_DOCUMENTS
    chat["writer_says"](lambda facts: facts + [NOT_IN_DOCUMENTS])
    reply, done = chat["say"]("how much is a tune-up cost")
    assert "$129 for non-members" in reply and NOT_IN_DOCUMENTS not in reply and "NOT IN" not in reply
    assert reply.index("$129") < reply.index("Ticket #") and done.outcome == "handed_off"
    assert chat["store"].tickets()[-1]["reason_tag"] == "not enough evidence"


def test_a_reply_that_is_only_the_marker_is_a_handoff_alone(chat):
    from app.replies.checks import NOT_IN_DOCUMENTS
    chat["writer_says"](lambda facts: [NOT_IN_DOCUMENTS])
    reply, done = chat["say"]("how much is a tune-up cost")
    assert "$129" not in reply and "NOT IN" not in reply and "Ticket #" in reply and done.outcome == "handed_off"
    assert chat["store"].tickets()[-1]["reason_tag"] == "not enough evidence"


def test_the_writer_is_told_to_answer_completely():
    from app.replies.writer import RULES
    assert "every fact" in RULES and "two to four" not in RULES


def test_the_grader_sees_the_passages_the_agent_retrieved(tmp_path):
    from eval.grade_conversations import retrieved_passages
    from eval.harness import Attempt
    store = OpsStore(tmp_path / "c-1-ops.sqlite")
    store.open_conversation("v", "c")
    message = store.log_message("c", "agent", "x")
    store.log_receipt(message, "clear", "knowledge, clear", ["membership/comfort_club_overview.md (2026-01-01), Cancellation"], [],
                      None, "supported by documents")
    (tmp_path / "c-1.sqlite").write_bytes(b"")
    passages = retrieved_passages(Attempt("c", db_path=str(tmp_path / "c-1.sqlite")))
    assert any("cancel auto-renewal" in p for p in passages)


@pytest.mark.parametrize("text", ["Okay good to know.", "Hm. Okay.", "Yeah, I think so, it's whatever was there when we moved in."])
def test_a_calm_message_asking_nothing_gets_anything_else_not_a_ticket(chat, text):
    reply, done = chat["say"](text)
    assert done.ticket is None and "anything else" in reply


def test_an_angry_or_questioning_unclear_message_is_still_handed_off(chat):
    _, done = chat["say"]("I've called three times and nobody has called me back. This is ridiculous!!")
    assert done.ticket


@pytest.mark.parametrize("text", ["Oh, sorry about that, I think that's all I needed anyway. No, that's everything.",
                                  "Great, that's all I needed, thanks"])
def test_a_goodbye_anywhere_in_the_message_ends_the_chat(chat, text):
    _, done = chat["say"](text)
    assert done.outcome == "ended"


def test_the_grader_is_given_the_customers_existing_appointments(tmp_path):
    from eval.grade_conversations import _account_facts
    import shutil
    db = tmp_path / "c.sqlite"
    shutil.copy(SEED, db)
    facts = _account_facts({"caller_card": {"customer_id": "MHC-10001"}, "fixtures": []}, str(db))
    assert any(a["slot_date"] == "2026-10-22" for a in facts["scheduled_appointments_at_start"])


def test_a_written_promise_of_a_follow_up_becomes_a_real_ticket():
    from app.replies.checks import CheckedStream
    stream = CheckedStream(iter(["Your visit is booked.", "A team member will follow up about access to the unit."]),
                           money_check=lambda s, p: True)
    assert list(stream) == ["Your visit is booked."] and stream.blocked_rule == "follow_up_promise"
    offer = CheckedStream(iter(["If you'd like, I can pass your question to a team member."]), money_check=lambda s, p: True)
    assert list(offer) == ["If you'd like, I can pass your question to a team member."]


def test_an_unclear_complaint_keeps_the_routers_reason(chat):
    chat["routes_add"]("nobody has called me back", {"clear": False, "requests": [request("nobody called back", "handoff", "complaint")]})
    _, done = chat["say"]("I've called three times and nobody has called me back. I'm done.")
    assert chat["store"].tickets()[-1]["reason_tag"] == "complaint"


def test_the_writer_never_guesses_and_the_rubric_grades_to_the_question():
    from app.replies.writer import RULES
    assert "Never guess" in RULES
    rubric = (ROOT / "eval" / "grader_prompt.md").read_text()
    assert "the question did not ask about" in rubric


def test_yes_please_book_it_at_a_booking_read_back_books_even_if_routed_as_another_action(chat):
    chat["routes_add"]("go ahead and book it", clear(request("yes, go ahead and book it", "scheduling", "confirm")))
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"]("Yes, please go ahead and book it.")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_a_savings_question_gets_the_no_estimate_instruction():
    from app.flows.knowledge import answer
    from app.knowledge.index import Chunk
    from app.knowledge.search import ScoredChunk

    class Plans:
        def search(self, question, mode="combined", k=5):
            return [ScoredChunk(Chunk("m#1", "membership/comfort_club_overview.md", "Plans", "", "$189 a year", 1, 2), 0.7, 2)]
    facts = " ".join(answer("would joining the maintenance plan save me money on this?", Plans(), 0.25).facts)
    assert "Do not estimate" in facts and "team member confirms" in facts


def test_the_writer_states_member_benefits_as_member_benefits():
    from app.replies.writer import RULES
    assert "as member benefits" in RULES


def test_add_it_after_a_membership_discussion_hands_off_the_enrolment(chat):
    chat["routes_add"]("save me money", clear(request("I want someone out", "scheduling", "book", "hvac_repair"),
                                              request("would joining the maintenance plan save me money", "knowledge")))
    chat["routes_add"]("add it and book", clear(request("add it and book the visit", "scheduling", "book", "hvac_repair")))
    chat["say"]("I'm Linda Foster, MHC-10001. My AC is blowing warm, I want someone out, and would joining the maintenance plan save me money on this?")
    chat["say"]("Yeah, add it and book the visit.")
    assert any(t["reason_tag"] == "action gap" for t in chat["store"].tickets())


# Milestone 4 gate fixes.

@pytest.mark.parametrize("text, key, value", [
    ("My AC cut out and won't turn back on", "won't turn back on",
     clear(request("my AC cut out and won't turn back on", "scheduling", "book", "hvac_repair"))),
    ("Can you hear me? I need to cancel my appointment", None, None),
    ("Hold on, reschedule it.", "reschedule it", clear(request("reschedule it", "scheduling", "reschedule")))])
def test_a_filler_phrase_with_a_request_in_it_is_still_handled(chat, text, key, value):
    if key:
        chat["routes_add"](key, value)
    reply, _ = chat["say"](text)
    assert "take your time" not in reply and "account number" in reply


@pytest.mark.parametrize("text, key, value", [
    ("That's it, I want to speak to a manager about your technician", "speak to a manager",
     clear(request("I want to speak to a manager about your technician", "handoff", "complaint"))),
    ("Nothing else has worked, my heater is broken, book a repair", None, None)])
def test_a_goodbye_phrase_with_a_request_in_it_does_not_end_the_chat(chat, text, key, value):
    if key:
        chat["routes_add"](key, value)
    reply, done = chat["say"](text)
    assert done.outcome != "ended" and "Have a great day" not in reply
    assert done.ticket or "account number" in reply


def test_an_unclear_request_for_a_person_is_handed_off(chat):
    chat["routes_add"]("real person", {"clear": False, "requests": [request("let me talk to a real person", "handoff", "person")]})
    reply, done = chat["say"]("Just let me talk to a real person")
    assert done.ticket and "Ticket #" in reply
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001. Just let me talk to a real person", conversation="c2")
    assert done.ticket and "found your account" not in reply


def test_a_second_handoff_reason_adds_its_tag_and_invoice_notes_to_the_open_ticket(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    chat["say"]("Send me a payment link")
    [action] = [t for t in chat["store"].tickets() if t["reason_tag"] == "action gap"]
    chat["routes_add"]("after-hours fee", clear(request("I dispute the after-hours fee", "handoff", "dispute")))
    reply, done = chat["say"]("I dispute the after-hours fee")
    assert f"Ticket #{action['ticket_id']}" in reply and len(chat["store"].tickets()) == 2
    assert "dispute" in chat["store"].ticket_tags(action["ticket_id"])
    ticket = next(t for t in chat["store"].tickets() if t["ticket_id"] == action["ticket_id"])
    assert "after-hours dispatch 144.00 vs schedule 149.00" in ticket["constraints"]


def test_an_action_request_after_a_handoff_adds_the_action_gap_tag(chat):
    chat["routes_add"]("talk to a manager", clear(request("I want to talk to a manager", "handoff", "complaint")))
    chat["say"]("I'm Linda Foster, MHC-10001. I want to talk to a manager.")
    chat["say"]("Also send me a payment link")
    assert chat["store"].ticket_tags(1) == ["complaint", "action gap"] and len(chat["store"].tickets()) == 1


@pytest.mark.parametrize("text, index", [("I'll take the first", 0), ("let's do the second", 1), ("the first works for me", 0),
                                         ("Second, please", 1), ("give me the third", 2)])
def test_ordinal_words_pick_a_slot(text, index):
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-20", "window": "12:00-16:00"},
               {"slot_date": "2026-10-21", "window": "13:00-17:00"}]
    assert _pick(text, choices, SETTINGS.now) == choices[index]
    assert _pick("first thing in the morning", choices, SETTINGS.now) == choices[0]
    assert _pick("wait a second, which ones?", choices, SETTINGS.now) is None


@pytest.mark.parametrize("text", ["Yes please, sooner is better", "yes, the earlier the better"])
def test_a_yes_saying_sooner_is_better_at_a_read_back_books(chat, text):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"](text)
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_a_yes_saying_sooner_is_better_at_a_reschedule_read_back_moves_it(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, can you move my appointment")
    chat["say"]("the 28th please")
    chat["say"]("the first one")
    reply, _ = chat["say"]("yes, the earlier the better")
    assert "Moved" in reply


def test_a_message_in_another_language_gets_an_english_note_and_a_handoff(chat):
    # Languages other than English are a non-goal; the caller still gets a person (D47).
    chat["routes_add"]("aire acondicionado", {"clear": True, "requests": [
        request("Hola, mi aire acondicionado no enfría. ¿Pueden venir mañana?", "handoff", "other language")]})
    reply, done = chat["say"]("Hola, mi aire acondicionado no enfría. ¿Pueden venir mañana?")
    assert reply.startswith("I can only help in English") and "Ticket #" in reply
    assert [t["reason_tag"] for t in chat["store"].tickets()] == ["other language"]


def test_the_router_offers_an_other_language_detail():
    from app.routing.router import DETAILS, RULES
    assert "other language" in DETAILS and "not written in English" in RULES


def test_another_language_is_handed_off_even_when_the_router_misses_it(chat):
    chat["routes_add"]("aire acondicionado", clear(request("¿Pueden venir mañana?", "scheduling", "book", "hvac_repair")))
    reply, done = chat["say"]("Hola, mi aire acondicionado no enfría. ¿Pueden venir mañana?")
    assert reply.startswith("I can only help in English") and done.ticket


def test_nonsense_is_handed_off_not_answered_with_anything_else(chat):
    chat["routes_add"]("asdf", {"clear": False, "requests": [request("asdf qwer zxcv", "handoff", "other")]})
    reply, done = chat["say"]("asdf qwer zxcv ;;; 12345")
    assert done.ticket and "anything else" not in reply


@pytest.mark.parametrize("text, foreign", [
    ("Hola, mi aire acondicionado no enfría. ¿Pueden venir mañana?", True),
    ("Mon climatiseur ne marche pas, pouvez-vous venir demain?", True), ("Привет, мой кондиционер сломан", True),
    ("asdf qwer zxcv ;;; 12345", False), ("okay, good to know", False),
    ("I'm José García, MHC-10003, can you book a tune-up?", False), ("Linda Foster", False), ("hmm", False),
    ("Can I get a café-style schedule? My AC is broken", False)])
def test_another_language_is_spotted_only_on_strong_signs(text, foreign):
    from app.core.language import other_language
    assert other_language(text) is foreign


@pytest.mark.parametrize("text", ["Linda Foster, 4412 Oak Hollow Dr, Round Rock.", "Omar Patel 512-555-0142",
                                  "Nadia Lee at 77 Pecan Street, Pflugerville", "I'd better hear from someone soon.",
                                  "linda.foster@example.com", "michael chen, 9648 oak hollow dr round rock",
                                  "Compressor rattling, thermostat blinking", "Thermostat display blinking constantly",
                                  "Kitchen faucet drips constantly overnight", "Compressor making weird rattling noises",
                                  "José García", "Zoë Smith", "linda foster mhc-10001", "gas smell", "pilot light",
                                  "drain clogged", "either works", "earliest available", "renewal date", "sounds perfect",
                                  "account number 48213", "¿linda.foster@example.com?", "Que pasa, MHC-10001 para mi"])
def test_english_names_addresses_and_short_phrases_are_not_another_language(text):
    from app.core.language import other_language
    assert other_language(text) is False


def test_no_working_set_caller_line_is_taken_for_another_language():
    import json
    from app.core.language import other_language
    lines = json.loads((Path(__file__).parent / "caller_lines.json").read_text())
    assert len(lines) == 467 and [line for line in lines if other_language(line)] == []


def test_french_is_handed_off_with_an_english_note(chat):
    reply, done = chat["say"]("Mon climatiseur ne marche pas, pouvez-vous venir demain?")
    assert reply.startswith("I can only help in English") and done.ticket


@pytest.mark.parametrize("text", ["linda.foster@example.com", "michael chen, 9648 oak hollow dr round rock"])
def test_details_given_at_an_identity_prompt_are_not_handed_off(chat, text):
    chat["say"]("I want to book a repair")
    reply, done = chat["say"](text)
    assert not done.ticket and "only help in English" not in reply and not chat["store"].tickets()


def test_a_name_and_account_number_in_lower_case_find_the_account(chat):
    reply, done = chat["say"]("linda foster mhc-10001")
    assert "Thanks, Linda, I've found your account" in reply and not done.ticket


@pytest.mark.parametrize("text", ["pilot light", "drain clogged", "either works", "earliest available", "renewal date",
                                  "sounds perfect", "account number 48213", "Compressor rattling, thermostat blinking",
                                  "Kitchen faucet drips constantly overnight"])
def test_short_english_phrases_go_to_normal_routing(chat, text):
    chat["routes_add"](text.lower(), clear(request(text, "knowledge")))
    reply, done = chat["say"](text)
    assert not done.ticket and "only help in English" not in reply and "$129" in reply


def test_a_short_unclear_english_phrase_gets_anything_else_but_gibberish_a_handoff(chat):
    reply, done = chat["say"]("Um, Jordan Rivera.")
    assert "anything else" in reply and not done.ticket
    reply, done = chat["say"]("asdf qwer zxcv ;;; 12345", conversation="c2")
    assert done.ticket and "anything else" not in reply and "only help in English" not in reply


def test_picking_a_slot_in_a_reschedule_is_not_taken_for_a_new_booking(chat):
    # The router may label "the first one" a booking; without a booking verb the reschedule carries on (a24).
    chat["routes_add"]("move my appointment", clear(request("move my appointment tomorrow to Monday", "scheduling", "reschedule")))
    chat["say"]("I'm Nadia Lee, MHC-36446. Can you move my appointment tomorrow to Monday?")
    chat["routes_add"]("the first one", clear(request("the first one", "scheduling", "book", "hvac_repair")))
    reply, _ = chat["say"]("the first one")
    assert "moving the hvac repair visit to monday" in reply.lower()


def test_identifying_with_a_calm_question_finds_the_account(chat):
    reply, done = chat["say"]("Hi, this is Linda Foster, MHC-10001. Can you help me?")
    assert reply == "Thanks, Linda, I've found your account. What can I help you with?" and not done.ticket
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001. This is ridiculous, can you help me?", conversation="c2")
    assert done.ticket and "found your account" not in reply


@pytest.mark.parametrize("text", [
    "Nope, that covers it. Thanks for your help!", "No, that's everything. Thanks for confirming!",
    "That's all I need, thank you so much.", "Great, thank you. That covers it for me.",
    "Okay, that's fine. Nope, that covers it for me.", "Thanks, that's all I need", "ok that's it for me, thanks",
    "cheers", "take care", "thanks a bunch", "appreciate it", "have a good day", "Thanks, appreciate it. Take care!",
    # Working-set lines that ended the chat before the goodbye fix (ace46b0) and must still end it.
    "Okay good to know. I think that's everything for now.",
    "Okay, thanks for confirming. That covers it for me.",
    "Sorry, I'm on your website chat, so I don't think it's the wrong number. That's all I needed, thank you so much.",
    "Sorry, this is chat, not a phone call, and you just confirmed my Thursday appointment. No, that's everything, thanks.",
    "Thanks, that's all I needed. I'll hold off on the Wednesday one for now.",
    "Yes, I can hear you fine, thanks. That's everything I needed.",
    "Yes, I can see your messages fine. That's all I needed, thanks."])
def test_a_closing_line_ends_the_chat(chat, text):
    reply, done = chat["say"](text)
    assert done.outcome == "ended" and "Have a great day" in reply


@pytest.mark.parametrize("text", ["That's all, I'm confused", "I'm confused, you just confirmed my appointment. That's everything I needed, thanks.",
                                  "Sorry, that last message confused me. That's everything I needed."])
def test_a_confused_caller_is_not_closed_out(chat, text):
    reply, done = chat["say"](text)
    assert done.outcome != "ended"


@pytest.mark.parametrize("text", ["Hold on, my dog is barking a bit. Give me one second.", "sorry, hang on a sec"])
def test_a_line_that_asks_nothing_gets_the_filler_reply(chat, text):
    reply, done = chat["say"](text)
    assert reply == "No problem, take your time." and not done.ticket


def test_a_new_scheduling_action_without_its_verb_switches_mid_booking(chat):
    chat["routes_add"]("thursday visit anymore", clear(request("I don't need the Thursday visit anymore", "scheduling", "cancel")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("Actually, I don't need the Thursday visit anymore")
    assert "cancelling" in reply and "2026-10-22" in reply


def test_asking_about_an_existing_appointment_mid_booking_switches(chat):
    chat["routes_add"]("existing appointment", clear(request("when is my existing appointment", "scheduling", "confirm")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("Before that, when is my existing appointment?")
    assert "Scheduled appointment" in reply and "2026-10-22" in reply


def test_asking_for_a_booking_mid_cancel_switches(chat):
    chat["routes_add"]("tune-up instead", clear(request("schedule a tune-up instead", "scheduling", "book", "hvac_tune_up")))
    chat["say"]("I'm Linda Foster, MHC-10001, cancel my appointment")
    reply, _ = chat["say"]("wait, schedule a tune-up instead")
    assert "Offer these slots" in reply and "tune-up" in reply.lower() and "cancelling" not in reply


@pytest.mark.parametrize("text, index", [
    ("The first option is too early; what's later?", None), ("The second doesn't work", None), ("not the first one", None),
    ("the second time it broke", None), ("the third week of november", None), ("for a second", None),
    ("wait a second", None), ("First off, the second slot please", 1), ("second thoughts, the third", 2),
    ("I'll take the first, not the second", 0), ("the first one", 0), ("the 2nd one doesn't work", None)])
def test_a_turned_down_or_unrelated_ordinal_picks_no_slot(text, index):
    from app.flows.scheduling import _pick
    choices = [{"slot_date": "2026-10-19", "window": "08:00-12:00"}, {"slot_date": "2026-10-20", "window": "12:00-16:00"},
               {"slot_date": "2026-10-21", "window": "13:00-17:00"}]
    assert _pick(text, choices, SETTINGS.now) == (None if index is None else choices[index])


@pytest.mark.parametrize("text", ["Yes, sooner if possible", "Sure, if there's anything sooner I'd take it",
                                  "yes but anything earlier?"])
def test_a_yes_that_asks_for_anything_sooner_looks_for_earlier_slots(chat, text):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    reply, _ = chat["say"](text)
    assert count(chat["db"], "select count(*) from appointments") == before
    assert "earliest" in reply


def test_a_yes_that_asks_for_anything_sooner_at_a_reschedule_read_back_does_not_move_it(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, can you move my appointment")
    chat["say"]("the 28th please")
    chat["say"]("the first one")
    reply, _ = chat["say"]("Yes, sooner if possible")
    assert "Moved" not in reply and "earliest" in reply


@pytest.mark.parametrize("text, detail", [("That's fine, yes please go ahead and book it.", "confirm"),
                                          ("That's fine, yes please go ahead and book it.", "book"),
                                          ("That's fine.", "confirm"), ("Yes, book it", "confirm")])
def test_a_yes_at_a_read_back_books_whatever_action_the_router_names(chat, text, detail):
    # The quick run (T9bb3779a): the router labelled the caller's yes a confirm request, which switched flows.
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["routes_add"](text.split(",")[0].lower().rstrip("."), clear(request(text, "scheduling", detail, "hvac_repair")))
    reply, _ = chat["say"](text)
    assert count(chat["db"], "select count(*) from appointments") == before + 1, reply


def test_the_writer_gives_every_member_benefit_when_asked_whether_a_plan_saves_money():
    # Quick run (T9e29febc): the savings answer dropped the included tune-ups, which the reference counts as savings.
    from app.replies.writer import RULES
    assert "save them money" in RULES and "services it includes" in RULES
    # ...but never whether it would (or would likely) save money, which the facts cannot say (a guess fails).
    assert "never say whether it would save them money" in RULES


def test_the_marker_in_a_booking_or_account_reply_is_dropped_without_a_handoff(chat):
    # Quick run: the writer added the marker to identity prompts, account answers and slot offers.
    from app.replies.checks import NOT_IN_DOCUMENTS
    chat["writer_says"](lambda facts: [NOT_IN_DOCUMENTS] + facts)
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    assert "NOT IN" not in reply and "08:00-12:00" in reply and "Ticket #" not in reply
    assert not [t for t in chat["store"].tickets() if t["reason_tag"] == "not enough evidence"]


def test_the_writer_keeps_the_marker_to_questions_the_documents_should_answer():
    from app.replies.writer import RULES
    assert "never for booking, scheduling or account" in RULES


# Review of the milestone 4 last round.

@pytest.mark.parametrize("text", ["Alright, let me think about it", "That's fine, I'll call you back later", "fine I guess",
                                  "all right, I'll sleep on it", "That's fine, appreciate it", "Alright",
                                  "ok let me check my calendar"])
def test_a_hedged_or_deferring_yes_at_a_read_back_does_not_book(chat, text):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"](text)
    assert count(chat["db"], "select count(*) from appointments") == before


@pytest.mark.parametrize("text", ["That's fine, yes please go ahead and book it.", "That's fine, please go ahead and book it.",
                                  "That's fine.", "Yes, book it", "yes", "sure",
                                  "perfect", "sounds good", "Yes please, sooner is better", "Yes, that's it"])
def test_a_clear_yes_at_a_read_back_books(chat, text):
    before = count(chat["db"], "select count(*) from appointments")
    book_to_read_back(chat)
    chat["say"](text)
    assert count(chat["db"], "select count(*) from appointments") == before + 1


@pytest.mark.parametrize("marker", ["[Not in documents]", "NOT IN DOCUMENTS", "[NOT_IN_DOCUMENTS]", "[NOT IN"])
def test_a_variant_of_the_marker_is_never_shown_and_hands_off(chat, marker):
    chat["writer_says"](lambda facts: facts + [marker])
    reply, done = chat["say"]("how much is a tune-up cost")
    assert "$129" in reply and "NOT" not in reply.upper().replace("NOTE", "") and done.outcome == "handed_off"
    assert chat["store"].tickets()[-1]["reason_tag"] == "not enough evidence"


def test_a_writer_reply_with_no_sentence_on_a_booking_turn_is_handed_off_not_left_empty(chat):
    from app.replies.checks import NOT_IN_DOCUMENTS
    chat["writer_says"](lambda facts: [NOT_IN_DOCUMENTS])
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    # The same handoff as a writer that fails: the error ticket and its message.
    assert reply.startswith("I've passed this to our team: Ticket #") and done.ticket and done.outcome == "handed_off"
    assert chat["store"].tickets()[-1]["reason_tag"] == "error" and "NOT IN" not in reply


@pytest.mark.parametrize("pick_route", [None, request("Let's go with the first one", "account", "action"),
                                        request("Let's go with the first one", "handoff", "other")])
def test_a_slot_pick_with_a_ticket_open_goes_to_the_booking_not_the_ticket(chat, pick_route):
    # Quick runs (T9e29febc): with an action-gap ticket open, the caller's pick became "I've added that to Ticket #1".
    pick = "Let's go with the first one, 8:00 AM to 12:00 PM on Monday."
    if pick_route:
        chat["routes_add"]("go with the first one", clear(pick_route))
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
    assert done.ticket
    reply, _ = chat["say"]("I want to book a repair Monday")
    assert "1) Monday 2026-10-19, 08:00-12:00" in reply
    before = count(chat["db"], "select count(*) from appointments")
    reply, _ = chat["say"](pick)
    assert "Read back" in reply and "Ticket #" not in reply
    reply, _ = chat["say"]("yes")
    assert "Booked" in reply and count(chat["db"], "select count(*) from appointments") == before + 1


@pytest.mark.parametrize("text", ["Tuesday doesn't work, what about Thursday?", "Not Monday, how about Wednesday morning?"])
def test_another_day_at_a_booking_offer_stays_in_the_booking_without_another_actions_verb(chat, text):
    from app.core.state import ConversationState
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    chat["routes_add"](text.lower()[:12], clear(request(text, "scheduling", "reschedule")))
    reply, _ = chat["say"](text)
    assert ConversationState.load(chat["store"], "c1", "v1").flow["kind"] == "book" and "late fee" not in reply


def test_a_pick_with_a_separate_action_request_reads_back_and_hands_off_the_action(chat):
    text = "Yeah, add the membership and book the visit. The Monday 8:00 to 12:00 slot works."
    chat["routes_add"]("add the membership", clear(request("add the membership", "account", "action"),
                                                   request("book the visit Monday 8:00 to 12:00", "scheduling", "book")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, done = chat["say"](text)
    assert "Read back" in reply and "Ticket #" in reply and chat["store"].tickets()[-1]["reason_tag"] == "action gap"


@pytest.mark.parametrize("text", ["Hi, I'm Linda Foster, MHC-10001", "Linda Foster, MHC-10001. I have a question",
                                  "Hello, this is Linda Foster MHC-10001, I need some help"])
def test_identifying_with_a_general_request_for_help_finds_the_account(chat, text):
    reply, done = chat["say"](text)
    assert reply == "Thanks, Linda, I've found your account. What can I help you with?" and not done.ticket


def test_identifying_with_an_unclear_question_is_handed_off(chat):
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001. Why does my bill show a charge I don't recognize?")
    assert "found your account" not in reply and done.ticket and chat["store"].tickets()[-1]["reason_tag"] == "unclear"


@pytest.mark.parametrize("text", ["Perfect, appreciate it", "That's fine, take care", "Cool, cheers"])
def test_a_pleasantry_at_an_open_offer_or_read_back_goes_to_the_flow(chat, text):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    _, done = chat["say"](text)
    assert done.outcome != "ended"
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning", conversation="c2")
    chat["say"]("yes", conversation="c2")
    _, done = chat["say"](text, conversation="c2")
    assert done.outcome != "ended"


@pytest.mark.parametrize("text", ["No, that's it. Thanks.", "Nothing else, bye", "Okay, that covers it", "That's all, thanks"])
def test_a_goodbye_at_an_open_offer_or_read_back_ends_the_chat(chat, text):
    book_to_read_back(chat)
    _, done = chat["say"](text)
    assert done.outcome == "ended"


def test_a_reply_restating_the_open_tickets_promise_is_released_not_blocked(chat):
    # Quick run: "...under Ticket #1, and someone will contact you within one business day." was blocked as a promise.
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
    assert done.ticket == 1
    restated = "Your earlier request is already with our team under Ticket #1, and someone will contact you within one business day"
    chat["writer_says"](lambda facts: facts + [restated])
    reply, done = chat["say"]("how much is a tune-up cost")
    assert restated in reply and "added that to Ticket" not in reply and done.outcome == "answered"


PLAN = Chunk("membership__comfort_club_overview#1", "membership/comfort_club_overview.md", "Plans", "2026-01-01",
             "Comfort Club members get 15 percent off all repairs.", 1, 2)


class PlanSearcher:
    """Finds the plan only when the question (or the context sent with it) names the plan."""
    def search(self, question, mode="combined", k=5):
        if "plan" in question.lower():
            return [ScoredChunk(PLAN, 0.7, 3.0)]
        return [ScoredChunk(TUNE_UP, 0.1, 0.5)]


@pytest.mark.parametrize("label", ["knowledge", "handoff, clear", "handoff, unclear"])
@pytest.mark.parametrize("question", ["So it pays for itself basically?", "So it pays for itself basically."])
def test_a_follow_up_question_with_a_ticket_and_an_offer_open_is_answered_not_added_to_the_ticket(chat, label, question):
    # Quick run (T9e29febc): with a ticket and a booking offer open, "So it pays for itself basically?" got only
    # "I've added that to Ticket #1; our team will contact you within one business day."
    chat["engine"]._pipeline.searcher = PlanSearcher()
    chat["routes_add"]("maintenance plan", clear(request("does the maintenance plan save me money", "knowledge")))
    routed = {"knowledge": clear(request(question, "knowledge")),
              "handoff, clear": clear(request(question, "handoff", "other")),
              "handoff, unclear": {"clear": False, "requests": [request(question, "handoff", "other")]}}[label]
    chat["routes_add"]("pays for itself", routed)
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
    assert done.ticket == 1
    reply, _ = chat["say"]("Would the maintenance plan save me money?")
    assert "15 percent" in reply
    reply, _ = chat["say"]("I want to book a repair Monday")
    assert "1) Monday 2026-10-19, 08:00-12:00" in reply
    reply, done = chat["say"](question)
    assert "15 percent" in reply and "added that to Ticket" not in reply, reply
    assert len(chat["store"].tickets()) == 1


def test_an_unclear_message_with_a_ticket_open_is_still_added_to_it(chat):
    chat["engine"]._pipeline.searcher = PlanSearcher()
    _, done = chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
    chat["say"]("I want to book a repair Monday")
    text = "Why is everything so complicated with you people?"  # nothing the documents answer, even with context
    chat["routes_add"]("so complicated", clear(request(text, "handoff", "other")))
    reply, done = chat["say"](text)
    assert "added that to Ticket #1" in reply and len(chat["store"].tickets()) == 1


def test_an_unclear_question_the_documents_do_not_answer_at_an_open_offer_still_goes_to_the_offer(chat):
    chat["engine"]._pipeline.searcher = PlanSearcher()
    chat["say"]("I'm Linda Foster, MHC-10001. Send me a payment link")
    chat["say"]("I want to book a repair Monday")
    reply, _ = chat["say"]("Why is everything so complicated with you people?")  # unclear by default in the script
    assert "1) Monday 2026-10-19, 08:00-12:00" in reply and len(chat["store"].tickets()) == 1


MIXED = "I'm Linda Foster, MHC-10001. How much is a tune-up and book a repair Monday morning"


def _mixed_routes(chat):
    chat["routes_add"]("tune-up and book", clear(request("how much is a tune-up", "knowledge"),
                                                  request("book a repair Monday morning", "scheduling", "book", "hvac_repair")))


def test_a_marker_against_the_booking_part_of_a_mixed_turn_opens_no_ticket(chat):
    # Step 5 handed off "not enough evidence" whenever a knowledge answer was in the turn, even with the marker
    # written against the booking part.
    from app.replies.checks import NOT_IN_DOCUMENTS
    _mixed_routes(chat)
    chat["writer_says"](lambda facts: facts + [NOT_IN_DOCUMENTS] if any("08:00-12:00" in f for f in facts) else facts)
    reply, done = chat["say"](MIXED)
    assert "$129 for non-members" in reply and "08:00-12:00" in reply and "NOT IN" not in reply
    assert "Ticket #" not in reply and not chat["store"].tickets() and done.outcome == "answered"


def test_a_marker_against_the_knowledge_part_of_a_mixed_turn_still_hands_off(chat):
    from app.replies.checks import NOT_IN_DOCUMENTS
    _mixed_routes(chat)
    chat["writer_says"](lambda facts: facts + [NOT_IN_DOCUMENTS] if any("$129" in f for f in facts) else facts)
    reply, done = chat["say"](MIXED)
    assert "$129 for non-members" in reply and "08:00-12:00" in reply and "NOT IN" not in reply
    assert chat["store"].tickets()[-1]["reason_tag"] == "not enough evidence" and done.outcome == "handed_off"


def test_a_slot_pick_after_a_can_you_hear_me_question_still_books(chat):
    # Quick run (T9e29febc retry): "Can you hear me okay? I'd like the first one, Monday 8:00 AM to 12:00 PM." at an
    # offer went to the router and was lost; the filler question does not stop the pick.
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    chat["routes_add"]("hear me okay", {"clear": True, "requests": [request("Can you hear me okay?", "redirect", "wrong number")]})
    reply, _ = chat["say"]("Can you hear me okay? I'd like the first one, Monday 8:00 AM to 12:00 PM.")
    assert "wrong number" not in reply.lower() and "08:00-12:00" in reply


def test_the_second_part_of_a_mixed_reply_sees_what_the_first_part_said(chat):
    # The booking part of a mixed turn said it had no benefit details right after the knowledge part listed them.
    seen = []
    chat["writer_says"](lambda facts: facts)
    original = chat["engine"]._pipeline.writer
    def writer(reply_type, facts, history):
        seen.append([m["content"] for m in history])
        return original(reply_type, facts, history)
    chat["engine"]._pipeline.writer = writer
    chat["routes_add"]("tune-up and book", clear(request("how much is a tune-up", "knowledge"),
                                                   request("book a tune-up", "scheduling", "book", "hvac_tune_up")))
    chat["say"]("I'm Linda Foster, MHC-10001. How much is a tune-up and book a tune-up and book")
    assert len(seen) == 2 and any("$129" in m for m in seen[1])


# -- the service address on file (quick run 20261021-031409: T70425efa, T9bb3779a, T9f56ade3) ----------------------
ON_FILE = "service address on your account"
PRIVATE = "For privacy, I don't read street addresses aloud."


def _says_address_on_file(reply):
    return ON_FILE in reply and PRIVATE in reply and "4412" not in reply and "oak hollow" not in reply.lower()


@pytest.mark.parametrize("routed", [None, clear(request("Can you confirm the address on file?", "account", "none"))])
def test_confirming_the_address_as_a_first_question_gets_the_fixed_answer_without_the_street(chat, routed):
    # The router may call it an account question (an invoice lookup followed) or leave it unclear (a ticket followed).
    if routed:
        chat["routes_add"]("address on file", routed)
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001. Can you confirm the address on file?")
    assert _says_address_on_file(reply) and "team member can update it" in reply
    assert not done.ticket and not chat["store"].tickets() and "invoice" not in reply.lower()


def test_asking_about_the_address_at_an_offer_keeps_the_booking_open(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    chat["routes_add"]("address you have", clear(request("Is the visit at the address you have?", "scheduling", "confirm")))
    reply, done = chat["say"]("Is the visit at the address you have for me?")
    assert _says_address_on_file(reply) and "2026-10-19, 08:00-12:00" in reply and not done.ticket
    before = count(chat["db"], "select count(*) from appointments")
    reply, _ = chat["say"]("yes")
    assert "Read back" in reply
    reply, _ = chat["say"]("Can you confirm my address before I say yes?")
    assert _says_address_on_file(reply) and "clear yes" in reply.lower()
    chat["say"]("yes")
    assert count(chat["db"], "select count(*) from appointments") == before + 1


def test_a_slot_pick_that_also_mentions_the_address_books_and_answers_the_address(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("Yes, Monday morning works. Same address as before, 4412 Oak Hollow Dr in Round Rock.")
    assert "Read back" in reply and _says_address_on_file(reply) and not chat["store"].tickets()


@pytest.mark.parametrize("text", [
    "Thanks. I think the address on file is right, it's whatever was there when we moved in.",
    "Thanks! Is this visit at the same address on file, 4412 Oak Hollow Dr in Round Rock?",
    "Okay, can you note 4412 Oak Hollow Dr, Round Rock as the service address for the Monday visit?"])
def test_asking_about_the_address_after_booking_gets_the_fixed_answer(chat, text):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    chat["say"]("yes")
    chat["say"]("yes")
    chat["routes_add"]("address", clear(request(text, "scheduling", "confirm")))
    reply, done = chat["say"](text)
    assert _says_address_on_file(reply) and "your visit" in reply.lower()
    assert not done.ticket and not chat["store"].tickets() and "which" not in reply.lower()


@pytest.mark.parametrize("text", ["We moved last month, my address is 77 Pecan Street, Austin now.",
                                  "Can you note 12 Elm Way, Austin as the service address for the visit?",
                                  "My address has changed, can you update it?"])
def test_a_changed_address_opens_an_address_change_ticket_without_reading_any_street(chat, text):
    chat["say"]("I'm Linda Foster, MHC-10001.")
    reply, done = chat["say"](text)
    assert done.ticket and chat["store"].tickets()[-1]["reason_tag"] == "address change"
    assert PRIVATE in reply and "4412" not in reply and "77 Pecan" not in reply and "12 Elm" not in reply
    assert "Ticket #" in reply


@pytest.mark.parametrize("text", ["Linda Foster, 4412 Oak Hollow Dr, Round Rock",
                                  "Linda Foster, the service address is 4412 Oak Hollow Dr, Round Rock."])
def test_identity_messages_with_an_address_are_not_address_questions(chat, text):
    if "service address" not in text:
        reply, done = chat["say"](text)
        assert reply == "Thanks, Linda, I've found your account. What can I help you with?" and not done.ticket
    chat["say"]("I want to book a repair", conversation="c2")
    reply, done = chat["say"](text, conversation="c2")
    assert "08:00-12:00" in reply and ON_FILE not in reply and not done.ticket


def test_the_working_set_caller_lines_that_count_as_address_messages():
    import json
    from app.flows.account import about_address
    lines = json.loads((Path(__file__).parent / "caller_lines.json").read_text())
    # Identified earlier in the conversation: questions, notes and statements about the address all count.
    # All 18 ask about, note or restate the address after the caller was identified (checked against their runs).
    found = [line for line in lines if about_address(line, identified_before=True)]
    assert len(found) == 18 and all("address" in line for line in found), found
    # At the identity prompt, giving the address is how the caller identifies themselves: only questions count.
    at_prompt = [line for line in lines if about_address(line, identified_before=False)]
    assert len(at_prompt) == 11 and not any(line.startswith(("Sure, the address is", "The service address is"))
                                            for line in at_prompt)
    assert not about_address("Can you confirm that the visit is moved to Monday afternoon?", identified_before=True)


def test_the_system_lookup_says_how_long_ago_it_was_installed(chat):
    chat["routes_add"]("what system", clear(request("what system do I have", "account", "system")))
    reply, _ = chat["say"]("I'm Grace Garcia, MHC-95149. What system do I have?")
    assert "installed 2026-07-12, about 3 months ago" in reply
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001. What system do I have?", conversation="c2")
    assert "installed 2023-05-14, about 3 years and 5 months ago" in reply


def test_a_writer_sentence_that_reads_the_street_on_file_is_withheld(chat):
    chat["writer_says"](lambda facts: ["Your address on file is 901 Brookside Court."] + facts)
    reply, _ = chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    assert "$478.00" in reply and "Brookside" not in reply
    chat["writer_says"](lambda facts: ["Your address on file is 4412 Oak Hollow Drive."] + facts)
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, what's my balance?", conversation="c2")
    assert "Oak Hollow" not in reply and "no open invoices" in reply


@pytest.mark.parametrize("text", ["What day is it today?", "what time is it", "What's today's date?", "Sorry, what's the date today?",
                                  "what day of the week is it?", "Is today a weekday?", "is it Friday today?"])
def test_a_date_or_time_question_gets_the_fixed_demo_date_not_a_ticket(chat, text):
    reply, done = chat["say"](text)
    assert reply == "For this demo, today is Friday 16 October 2026, and the time is 9:00 a.m. in Austin."
    assert done.outcome == "answered" and not chat["store"].tickets()


def test_a_date_question_with_another_request_is_routed_as_usual(chat):
    reply, _ = chat["say"]("What day is it today? And how much is a tune-up?")
    assert not reply.startswith("For this demo")


def test_the_writer_is_told_the_date_is_the_demo_date():
    from app.replies.writer import RULES
    assert "Friday 16 October 2026" in RULES and "For this demo, today is" in RULES


# Post-measurement safety fix: after a safety reply the conversation is never booked (SPEC anti-goal, R36, R37).
def _appointments(chat):
    return count(chat["db"], "select count(*) from appointments")


def test_a_booking_after_a_burning_smell_is_not_booked_and_goes_to_the_emergency_ticket(chat):
    before = _appointments(chat)
    chat["say"]("I'm Linda Foster, MHC-10001. There's a burning smell from my furnace")
    [emergency] = chat["store"].tickets()
    assert emergency["reason_tag"] == "burning smell"
    reply, done = chat["say"]("yes, book me the first slot")
    assert reply == (f"Because of the safety issue you reported, I won't book a regular visit. Our team will arrange the "
                     f"visit as a priority through your emergency ticket, Ticket #{emergency['ticket_id']}, and I've "
                     f"added your message to it.")
    assert _appointments(chat) == before and not done.db_actions
    assert "yes, book me the first slot" in chat["store"].ticket_messages(emergency["ticket_id"])
    assert len(chat["store"].tickets()) == 1
    # Still refused on a later turn: the flag is kept for the whole conversation.
    reply, _ = chat["say"]("I want to book a repair Monday morning")
    assert reply.startswith("Because of the safety issue") and _appointments(chat) == before
    reply, _ = chat["say"]("move my appointment")
    assert reply.startswith("Because of the safety issue") and _appointments(chat) == before


def test_a_gas_report_mid_booking_abandons_the_booking_and_a_yes_at_the_read_back_books_nothing(chat):
    before = _appointments(chat)
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    reply, _ = chat["say"]("yes")
    assert "Read back" in reply
    chat["say"]("wait, I smell gas")
    emergency = chat["store"].tickets()[-1]
    assert emergency["reason_tag"] == "emergency"
    reply, done = chat["say"]("yes")
    assert reply.startswith("Because of the safety issue") and f"Ticket #{emergency['ticket_id']}" in reply
    assert _appointments(chat) == before and not done.db_actions
    assert "yes" in chat["store"].ticket_messages(emergency["ticket_id"])


def test_a_knowledge_question_after_a_burning_smell_is_answered_normally(chat):
    chat["say"]("There's a burning smell coming from the vents")
    reply, done = chat["say"]("how much is a tune-up cost?")
    assert "$129" in reply and "Because of the safety issue" not in reply


def test_an_account_question_after_a_safety_report_is_answered_normally(chat):
    chat["say"]("I'm Linda Foster, MHC-10001. No heat and it's freezing")
    reply, _ = chat["say"]("what's my balance")
    assert "Because of the safety issue" not in reply and "no open invoices" in reply


def test_a_caller_who_identifies_with_an_emergency_is_not_asked_again(chat):
    # Live check: "I'm Linda Foster, MHC-10001. There's a burning smell coming from my furnace." got a ticket that
    # still asked for the name and account number.
    reply, done = chat["say"]("I'm Linda Foster, MHC-10001. There's a burning smell coming from my furnace.")
    assert "Ticket #" in reply and "please tell me your name" not in reply
    ticket = chat["store"].tickets()[-1]
    assert "Linda Foster" in ticket["who"] and "MHC-10001" in ticket["who"]


def test_a_caller_who_reports_an_emergency_without_details_is_still_asked(chat):
    reply, _ = chat["say"]("There's a burning smell coming from my furnace.")
    assert "please tell me your name" in reply


# Milestone 5 review: a yes with the caller's details after a safety reply identifies them and names them on the ticket.
def test_a_yes_with_details_after_a_safety_reply_identifies_the_caller_on_the_emergency_ticket(chat):
    before = _appointments(chat)
    chat["say"]("I smell gas in the house")
    emergency = chat["store"].tickets()[-1]
    assert "Linda Foster" not in (emergency["who"] or "")
    reply, done = chat["say"]("Sure, Linda Foster, MHC-10001")
    assert reply == (f"Because of the safety issue you reported, I won't book a regular visit. Our team will arrange the "
                     f"visit as a priority through your emergency ticket, Ticket #{emergency['ticket_id']}, and I've "
                     f"added your message to it.")
    ticket = next(t for t in chat["store"].tickets() if t["ticket_id"] == emergency["ticket_id"])
    assert "Linda Foster" in ticket["who"] and "MHC-10001" in ticket["who"]
    assert _appointments(chat) == before and not done.db_actions
    reply, _ = chat["say"]("what's my balance")
    assert "please tell me your name" not in reply and "no open invoices" in reply


# Milestone 5 review: at an open booking offer or read-back, "what time?" or "what day?" asks about the offer.
@pytest.mark.parametrize("text", ["Sorry, what time?", "what day?"])
def test_a_time_question_at_an_open_offer_goes_to_the_booking_not_the_demo_date(chat, text):
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair Monday morning")
    assert "Monday" in reply
    reply, done = chat["say"](text)
    assert not reply.startswith("For this demo") and done.route == "scheduling"


@pytest.mark.parametrize("text", ["Sorry, what time?", "what day?"])
def test_a_time_question_with_no_offer_open_gets_the_demo_date(chat, text):
    reply, _ = chat["say"](text)
    assert reply.startswith("For this demo, today is Friday 16 October 2026")
