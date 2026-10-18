"""Booking, cancelling, rescheduling and confirming, one step per caller message (R49 to R55, R84).

Every change is read back with a confirmation id and needs a clear yes; the transaction itself repeats the
eligibility check, so a slot taken in between is offered again rather than double-booked."""

import re
import uuid
from dataclasses import asdict
from datetime import date

from app.flows.protocol import FlowResult
from app.handoff.flow import confirm_booking
from app.scheduling import transactions as tx
from app.scheduling.dates import parse_request
from app.scheduling.eligibility import SERVICE_NAMES, Slot, offer

YES = re.compile(r"^\W*(yes|yeah|yep|yup|sure|ok|okay|correct|that works|sounds good|book it|do it|please do|perfect|go ahead)\b", re.I)
NO = re.compile(r"^\W*(no|nope|neither|none of)\b", re.I)
ORDINALS = [r"\b(first|1st|one|1)\b", r"\b(second|2nd|two|2)\b", r"\b(third|3rd|three|3)\b"]
# Warranty claims the database cannot verify are booked as normal visits for staff review (R53).
REPEAT_REPAIR = re.compile(r"\b(same thing|same problem|again|came back|repeat repair|you fixed)\b", re.I)
MEMBER_INSTALL = re.compile(r"\bmember when (it was|you|we)\b.*\binstall|\b5-year\b", re.I)
NO_FEE_IF_COVERED = "There is no diagnostic fee if the technician confirms the repair is covered by the warranty."
SERVICE_WORDS = [(r"\btune-?up|maintenance\b", "hvac_tune_up"), (r"\breplac\w*|new system|estimate\b", "estimate"),
                 (r"\bsink|drain|toilet|water heater|pipe|plumb\w*", "plumbing")]


def guess_service(text: str) -> str:
    return next((service for pattern, service in SERVICE_WORDS if re.search(pattern, text, re.I)), "hvac_repair")


def _when(slot_date: str, window: str) -> str:
    return f"{date.fromisoformat(slot_date):%A} {slot_date}, {window}"


def _offer_facts(slots: list[dict], lead: str = "Offer these slots and ask which one suits:") -> list[str]:
    return [lead] + [f"{n}) {_when(s['slot_date'], s['window'])} ({SERVICE_NAMES[s['service_type']]})"
                     for n, s in enumerate(slots, 1)]


def _pick(text: str, choices: list[dict], now, key_date="slot_date") -> dict | None:
    if len(choices) == 1 and YES.search(text):
        return choices[0]
    for index, pattern in enumerate(ORDINALS[:len(choices)]):
        if re.search(pattern, text, re.I):
            return choices[index]
    wanted = parse_request(text, now)
    if wanted:
        for choice in choices:
            if (wanted.date is None or choice[key_date] == wanted.date.isoformat()) and \
                    (wanted.window is None or choice["window"] == wanted.window) and \
                    (wanted.part is None or (choice["window"] == "08:00-12:00") == (wanted.part == "morning")):
                return choice
    return None


def _read_back(flow: dict, what: str, fee_cents: int = 0) -> FlowResult:
    flow["confirmation_id"] = uuid.uuid4().hex
    flow["step"] = "readback"
    fee = " A $49 late fee applies because this is within 24 hours of the window." if fee_cents else ""
    return FlowResult([f"Read back: {what}.{fee} Ask the caller for a clear yes before going ahead."], "read-back")


def _make_offer(db, customer, flow: dict, text: str, now, lead: str | None = None) -> FlowResult:
    result = offer(db, customer, flow["service"], parse_request(text, now), now)
    if result.decline_reason:
        flow.clear()
        return FlowResult([result.decline_reason, customer.city, SERVICE_NAMES[flow.get("service", "hvac_repair")]],
                          "decline", handoff_reason="decline")
    flow["offered"] = [asdict(s) for s in result.slots]
    flow["step"] = "offer"
    return FlowResult(_offer_facts(flow["offered"], lead or "Offer these slots and ask which one suits:"), "booking offer")


def step(db, seed_db, customer, state, text: str, now, store) -> FlowResult:
    if state.flow["kind"] == "book":
        return _book(db, customer, state, text, now, store)
    return _existing(db, seed_db, customer, state, text, now)


def _book(db, customer, state, text, now, store) -> FlowResult:
    flow = state.flow
    if flow.get("step") in (None, "start"):
        flow.setdefault("service", guess_service(text))
        flow.setdefault("issue", text)
        claim = "repeat repair" if REPEAT_REPAIR.search(text) else "member installation" if MEMBER_INSTALL.search(text) else None
        if claim:
            flow["claim"] = claim
        return _make_offer(db, customer, flow, text, now)
    if flow["step"] == "offer":
        chosen = _pick(text, flow["offered"], now)
        if chosen is None:
            if parse_request(text, now):
                return _make_offer(db, customer, flow, text, now)
            return FlowResult(_offer_facts(flow["offered"], "Ask which of these slots suits, or what other time works:"),
                              "booking offer")
        flow["chosen"] = chosen
        return _read_back(flow, f"{SERVICE_NAMES[chosen['service_type']]} on {_when(chosen['slot_date'], chosen['window'])}")
    # Read-back: book only on a clear yes.
    if YES.search(text):
        chosen = flow["chosen"]
        booked = tx.book(db, customer, chosen["slot_id"], flow.get("issue", ""), flow["confirmation_id"], now,
                         claim=flow.get("claim"))
        if booked.status == "taken":
            flow["step"] = "start"
            return _make_offer(db, customer, flow, "", now, "That slot was just taken. Offer these instead:")
        state.tried.append(f"booked appointment {booked.appointment_id}")
        claim = flow.get("claim")
        state.flow, state.active_flow = {}, None
        confirmed = confirm_booking({"store": store, "conversation_id": state.conversation_id}, booked,
                                    chosen["slot_date"], chosen["window"], chosen["service_type"])
        if booked.warranty_review:
            store.create_ticket(None, f"{customer.name}, {customer.customer_id}", f"{claim} claim: {flow.get('issue', '')}",
                                f"booked appointment {booked.appointment_id} as a normal visit", "warranty not verifiable "
                                "from the database", "", "warranty review", booked.appointment_id)
            return FlowResult(confirmed.facts + [NO_FEE_IF_COVERED], "confirmation", db_actions=confirmed.db_actions)
        return confirmed
    if NO.search(text):
        flow["step"] = "offer"
        return FlowResult(_offer_facts(flow["offered"], "No change made. Ask which slot suits instead:"), "booking offer")
    return FlowResult(["Ask the caller for a clear yes or no to the booking read back."], "read-back")


def _existing(db, seed_db, customer, state, text, now) -> FlowResult:
    flow = state.flow
    kind = flow["kind"]
    if flow.get("step") in (None, "start"):
        appointments = [asdict(a) for a in tx.scheduled_appointments(db, customer.customer_id)]
        if not appointments:
            state.flow, state.active_flow = {}, None
            return FlowResult(["There are no scheduled appointments on this account."], "account answer")
        if len(appointments) > 1:
            flow["appointments"], flow["step"] = appointments, "which"
            return FlowResult(["Ask which appointment the caller means:"] +
                              [f"{n}) {_when(a['slot_date'], a['window'])} ({SERVICE_NAMES[a['service_type']]})"
                               for n, a in enumerate(appointments, 1)], "account answer")
        flow["appointment"] = appointments[0]
        return _about(db, customer, state, text, now)
    if flow["step"] == "which":
        chosen = _pick(text, flow["appointments"], now)
        if chosen is None:
            return FlowResult(["Ask which appointment the caller means, by its date."], "account answer")
        flow["appointment"] = chosen
        return _about(db, customer, state, text, now)
    if flow["step"] in ("new_date", "offer"):
        if flow["step"] == "offer" and (chosen := _pick(text, flow["offered"], now)):
            flow["chosen"] = chosen
            fee = tx.late_fee_preview(db, flow["appointment"]["appointment_id"], now)
            return _read_back(flow, f"moving the {SERVICE_NAMES[chosen['service_type']]} visit to "
                                    f"{_when(chosen['slot_date'], chosen['window'])}", fee)
        if parse_request(text, now) or flow["step"] == "offer":
            return _make_offer(db, customer, flow, text, now)
        return FlowResult(["Ask what day and time the caller would like instead."], "booking offer")
    # Read-back for a cancel or reschedule.
    appointment = flow["appointment"]
    if YES.search(text):
        if kind == "cancel":
            result = tx.cancel(db, customer, appointment["appointment_id"], flow["confirmation_id"], now, seed_db)
            what = f"Cancelled the {_when(appointment['slot_date'], appointment['window'])} visit"
        else:
            chosen = flow["chosen"]
            result = tx.reschedule(db, customer, appointment["appointment_id"], chosen["slot_id"], flow["confirmation_id"],
                                   now, seed_db)
            what = f"Moved the visit to {_when(chosen['slot_date'], chosen['window'])}"
        if result.status == "taken":
            flow["step"] = "new_date"
            return _make_offer(db, customer, flow, "", now, "That slot was just taken. Offer these instead:")
        if result.status != "not found":
            state.tried.append(f"{result.status} appointment {appointment['appointment_id']}")
        state.flow, state.active_flow = {}, None
        fee = " A $49 late fee applies." if result.late_fee_cents else ""
        return FlowResult([f"{what}.{fee}"], "confirmation", db_actions=[f"{result.status} appointment {appointment['appointment_id']}"])
    if NO.search(text):
        state.flow, state.active_flow = {}, None
        return FlowResult(["No change made to the appointment."], "confirmation")
    return FlowResult(["Ask the caller for a clear yes or no to the change read back."], "read-back")


def _about(db, customer, state, text, now) -> FlowResult:
    flow = state.flow
    appointment = flow["appointment"]
    summary = (f"{SERVICE_NAMES[appointment['service_type']]} on {_when(appointment['slot_date'], appointment['window'])}, "
               f"with {appointment['technician']}")
    if flow["kind"] == "confirm":
        state.flow, state.active_flow = {}, None
        return FlowResult([f"Scheduled appointment: {summary}."], "account answer",
                          db_actions=[f"appointment lookup {customer.customer_id}"])
    if flow["kind"] == "cancel":
        return _read_back(flow, f"cancelling the {summary}", tx.late_fee_preview(db, appointment["appointment_id"], now))
    flow["service"] = appointment["service_type"]
    flow["step"] = "new_date"
    return _existing(db, None, customer, state, text, now)
