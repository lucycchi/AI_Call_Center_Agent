import logging
import sqlite3
import time

import pytest

from app.flows.protocol import FlowResult
from app.handoff.flow import add_to_open_ticket, confirm_booking, hand_off, safe
from app.ops.store import OpsStore
from app.scheduling.transactions import BookingResult


@pytest.fixture
def state(tmp_path):
    store = OpsStore(tmp_path / "ops.sqlite")
    store.open_conversation("v1", "c1")
    return {"store": store, "conversation_id": "c1", "who": "Omar Patel, MHC-10002",
            "wants": "The tech quoted me $89 and the invoice says $149.", "tried": "read the invoice lines",
            "mood": "frustrated"}


def test_a_handoff_opens_a_ticket_with_all_five_fields_and_tells_the_caller(state):
    result = hand_off(state, "dispute", "disputed fee $149")
    [ticket] = state["store"].tickets()
    for field in ("who", "wants", "tried", "constraints", "mood"):
        assert ticket[field], field
    assert "invoice says $149" in ticket["wants"]
    assert result.reply_type == "handoff" and result.handoff_reason == "dispute"
    assert "Ticket #1" in result.facts[0] and "within one business day" in result.facts[0]


def test_missing_ticket_fields_are_filled_plainly(state):
    for key in ("who", "tried", "mood"):
        state.pop(key)
    hand_off(state, "complaint", "")
    [ticket] = state["store"].tickets()
    assert ticket["who"] and ticket["tried"] and ticket["mood"] and ticket["constraints"]


def test_an_emergency_handoff_says_it_was_flagged(state):
    result = hand_off(state, "emergency", "gas smell")
    assert "flagged as an emergency" in result.facts[0]


def test_later_messages_are_added_to_the_open_ticket_and_the_chat_stays_open(state):
    hand_off(state, "dispute", "")
    store = state["store"]
    later = store.log_message("c1", "caller", "Also it was a Tuesday.")
    add_to_open_ticket(state, later)
    assert store.ticket_messages(state["ticket_id"]) == ["Also it was a Tuesday."]
    assert store._rows("select status from conversations where conversation_id = 'c1'")[0]["status"] == "open"


@pytest.mark.parametrize("error", [RuntimeError("voyage down"), sqlite3.OperationalError("database is locked")])
def test_search_and_database_errors_become_a_handoff(error):
    def step():
        raise error
    result = safe(step)
    assert result.reply_type == "handoff" and result.handoff_reason == "error"
    assert "team member" in result.facts[0]


def test_a_step_that_finds_the_deadline_passed_becomes_a_handoff_without_its_change():
    from app.core import deadline
    changes, errors = [], []

    def step():
        deadline.check()
        changes.append("committed")
        return FlowResult(["done"], "confirmation")
    token = deadline.start(0.01)
    try:
        time.sleep(0.02)
        result = safe(step, on_error=errors.append)
    finally:
        deadline.DEADLINE.reset(token)
    assert result.handoff_reason == "error" and changes == [] and "deadline" in errors[0]


def test_a_step_inside_the_deadline_passes_through():
    assert safe(lambda: FlowResult(["ok"], "policy answer")).facts == ["ok"]


class BrokenStore:
    def __init__(self):
        self.events = []

    def create_ticket(self, *args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    def log_event(self, kind, detail, conversation_id=None):
        self.events.append((kind, detail))


def test_when_no_ticket_can_be_saved_the_caller_is_asked_to_phone_and_the_failure_is_logged(state, caplog):
    state["store"] = BrokenStore()
    with caplog.at_level(logging.ERROR):
        result = hand_off(state, "dispute", "")
    assert "phone our office" in result.facts[0]
    assert "ticket could not be saved" in caplog.text
    assert state["store"].events and state["store"].events[0][0] == "write failure"


class LoggingFails:
    def log_event(self, *args, **kwargs):
        raise sqlite3.OperationalError("disk full")


def test_a_committed_booking_is_confirmed_even_if_logging_fails(state, caplog):
    state["store"] = LoggingFails()
    booked = BookingResult("booked", 160, "Marta Kowalski", False, False)
    with caplog.at_level(logging.ERROR):
        result = confirm_booking(state, booked, "2026-10-19", "08:00-12:00", "hvac_repair")
    assert result.reply_type == "confirmation" and "Marta Kowalski" in " ".join(result.facts)
    assert "appointment 160" in caplog.text
