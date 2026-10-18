"""Booking, cancelling, rescheduling and confirming, one step per caller message (R49 to R55, R84).

Every change is read back with a confirmation id and needs a clear yes; the transaction itself repeats the
eligibility check, so a slot taken in between is offered again rather than double-booked."""

import logging
import re
import uuid
from dataclasses import asdict
from datetime import date

from app.core import deadline
from app.flows.protocol import FlowResult
from app.handoff.flow import confirm_booking
from app.scheduling import transactions as tx
from app.scheduling.dates import parse_request
from app.scheduling.eligibility import SERVICE_NAMES, Slot, offer, spoken_when

# Only a plain yes confirms a change (R52); anything hedged gets the read-back again.
AFFIRMATIVE = re.compile(r"^\W*(?:(?:um|uh|oh)\W+)?(yes|yeah|yep|yup|sure|ok|okay|correct|that works|sounds good|book it|"
                         r"do it|please do|perfect|go ahead|take it|works|let'?s do (?:it|that)|do that|great)\b", re.I)
HEDGE = re.compile(r"\?|\b(but|wait|actually|instead|hold on|not|no|nope|hmm|maybe|unless|first|which|what|how)\b", re.I)
# A yes that names a day or time is about a different slot, not this read-back ("Yes, Tuesday works").
NAMES_A_TIME = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|morning|afternoon|"
                          r"evening|next week|january|february|march|april|june|july|august|september|october|november|"
                          r"december|\d{1,2}(st|nd|rd|th)|\d{1,2}(:\d\d)? ?(am|pm)|\d{1,2} to \d{1,2})\b", re.I)
log = logging.getLogger("meridian.scheduling")
NO = re.compile(r"^\W*(no|nope|neither|none of)\b", re.I)
EARLIER = re.compile(r"\b(earlier|sooner|anything before|any earlier)\b", re.I)
# Ordinal words only: a bare "one" or "1" is too often part of a date or window ("the Tuesday one", "1 to 5").
ORDINALS = [r"\b(first|1st|option (?:1|one)|number (?:1|one)|#1)\b", r"\b(second|2nd|option (?:2|two)|number (?:2|two)|#2)\b",
            r"\b(third|3rd|option (?:3|three)|number (?:3|three)|#3)\b"]


class _PlainYes:
    def search(self, text: str) -> bool:
        rest = AFFIRMATIVE.sub("", text, count=1)
        return bool(AFFIRMATIVE.search(text)) and not HEDGE.search(rest) and not NAMES_A_TIME.search(rest)


def confirms(text: str, slot_date: str, window: str, now) -> bool:
    """A clear yes to this read-back: no hedge, and any day or time it names is the one read back (R52)."""
    if not AFFIRMATIVE.search(text) or HEDGE.search(AFFIRMATIVE.sub("", text, count=1)):
        return False
    if not NAMES_A_TIME.search(AFFIRMATIVE.sub("", text, count=1)):
        return True
    wanted = parse_request(text, now)
    if wanted is None:
        return False
    return (wanted.date is None or wanted.date.isoformat() == slot_date) and \
        (wanted.window is None or wanted.window == window) and \
        (wanted.part is None or (window == "08:00-12:00") == (wanted.part == "morning"))


YES = _PlainYes()
_deadline_passed = deadline.passed  # replaced in tests
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


NUMBERS = {"1": 0, "one": 0, "first": 0, "1st": 0, "2": 1, "two": 1, "second": 1, "2nd": 1, "3": 2, "three": 2,
           "third": 2, "3rd": 2}
BARE_NUMBER = re.compile(r"^\W*(?:option |number |#|the )?(1|2|3|one|two|three)(?: one| please| thanks| option)*\W*$", re.I)
NTH_ONE = re.compile(r"\b(first|second|third|1st|2nd|3rd)\b(?! of\b)(?:\s+(?:one|option|slot|choice|time|window))?", re.I)
NTH_WITH_NOUN = re.compile(r"\b(1st|2nd|3rd)\s+(?:one|option|slot|choice|time|window)\b", re.I)


def _numbered(text: str, choices: list[dict]) -> dict | None:
    """"2", "two please", "the 2nd one", "the third option": a slot by its number in the offer."""
    match = BARE_NUMBER.match(text) or NTH_WITH_NOUN.search(text)
    if not match:
        word = NTH_ONE.search(text)
        match = word if word and word.group(1).isalpha() else None
    if match:
        index = NUMBERS[match.group(1).lower()]
        return choices[index] if index < len(choices) else None
    return None


def _pick(text: str, choices: list[dict], now, key_date="slot_date") -> dict | None:
    """A named day or date narrows the choices first ("the Tuesday one", "first thing on Tuesday"); then a slot
    number or ordinal picks among them; then the window or part of day."""
    if len(choices) == 1 and YES.search(text):
        return choices[0]
    names_a_day = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|january|february|"
                            r"march|april|may|june|july|august|september|october|november|december|\d{1,2}/\d{1,2})\b", text, re.I)
    if NTH_WITH_NOUN.search(text) and not names_a_day:  # "the 2nd one" is a slot, not 2 November
        return _numbered(text, choices)
    wanted = parse_request(text, now)
    if wanted and wanted.date:
        pool = [c for c in choices if c[key_date] == wanted.date.isoformat()]
        if len(pool) > 1:
            numbered = _numbered(text, pool)
            if numbered:
                return numbered
        choices = pool
    else:
        numbered = _numbered(text, choices)
        if numbered:
            return numbered
    if wanted and (wanted.date or wanted.window or wanted.part):
        for choice in choices:
            if (wanted.date is None or choice[key_date] == wanted.date.isoformat()) and \
                    (wanted.window is None or choice["window"] == wanted.window) and \
                    (wanted.part is None or (choice["window"] == "08:00-12:00") == (wanted.part == "morning")):
                return choice
        return None
    for index, pattern in enumerate(ORDINALS[:len(choices)]):
        if re.search(pattern, text, re.I):
            return choices[index]
    return None


def _read_back(flow: dict, what: str, fee_cents: int = 0) -> FlowResult:
    flow["confirmation_id"] = uuid.uuid4().hex
    flow["step"] = "readback"
    fee = " A $49 late fee applies because this is within 24 hours of the window." if fee_cents else ""
    return FlowResult([f"Read back: {what}.{fee} Ask the caller for a clear yes before going ahead."], "read-back")


def _make_offer(db, customer, flow: dict, text: str, now, lead: str | None = None) -> FlowResult:
    requested = parse_request(text, now)
    if requested and requested.date and requested.date < now.date():
        requested, lead = None, f"{requested.date:%B} {requested.date.day} has already passed. Offer the soonest slots instead:"
    result = offer(db, customer, flow["service"], requested, now)
    if result.decline_reason:
        service = SERVICE_NAMES[flow["service"]]
        flow.clear()
        return FlowResult([result.decline_reason, customer.city, service], "decline", handoff_reason="decline")
    flow["offered"] = [asdict(s) for s in result.slots]
    flow["step"] = "offer"
    return FlowResult(_offer_facts(flow["offered"], lead or "Offer these slots and ask which one suits:"), "booking offer")


def _with_fee(db, flow: dict, now, result: FlowResult) -> FlowResult:
    """A reschedule offer says whether moving the appointment carries the late fee."""
    if result.reply_type != "booking offer":
        return result
    fee = tx.late_fee_preview(db, flow["appointment"]["appointment_id"], now)
    note = ("A $49 late fee applies because the current appointment is within 24 hours." if fee
            else "There is no late fee for moving this appointment, as it is more than 24 hours away.")
    return FlowResult(result.facts + [note], result.reply_type, db_actions=result.db_actions)


def _earlier(db, customer, flow: dict, now) -> FlowResult:
    """Offer anything earlier than what was offered; if there is nothing, a ticket marked "wants an earlier slot" (R44)."""
    soonest = offer(db, customer, flow["service"], None, now)
    offered = {(s["slot_date"], s["window"]) for s in flow.get("offered", [])}
    earliest_offered = min(offered) if offered else None
    sooner = [s for s in soonest.slots if earliest_offered is None or (s.slot_date, s.window) < earliest_offered]
    if sooner:
        flow["offered"] = [asdict(s) for s in sooner]
        flow["step"] = "offer"
        return FlowResult(_offer_facts(flow["offered"], "These are the earliest open slots; ask which one suits:"),
                          "booking offer")
    return FlowResult(["The slots offered are the earliest available; the caller can still take one of them."],
                      "booking offer", handoff_reason="earlier slot")


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
        if chosen is None and EARLIER.search(text):
            return _earlier(db, customer, flow, now)
        if chosen is None:
            if parse_request(text, now):
                return _make_offer(db, customer, flow, text, now)
            return FlowResult(_offer_facts(flow["offered"], "Ask which of these slots suits, or what other time works:"),
                              "booking offer")
        flow["chosen"] = chosen
        return _read_back(flow, f"{SERVICE_NAMES[chosen['service_type']]} on {_when(chosen['slot_date'], chosen['window'])}")
    # Read-back: book only on a clear yes.
    if confirms(text, flow["chosen"]["slot_date"], flow["chosen"]["window"], now):
        chosen = flow["chosen"]
        if _deadline_passed():
            raise deadline.DeadlinePassed("not booking after the message deadline")
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
            try:  # the booking has committed; a failed review ticket must not hide it
                store.create_ticket(None, f"{customer.name}, {customer.customer_id}", f"{claim} claim: {flow.get('issue', '')}",
                                    f"booked appointment {booked.appointment_id} as a normal visit",
                                    "warranty not verifiable from the database", "", "warranty review", booked.appointment_id)
            except Exception as error:
                log.error("warranty review for appointment %s not saved, kept to retry: %s", booked.appointment_id, error)
                state.pending_tickets.append({"conversation_id": None, "who": f"{customer.name}, {customer.customer_id}",
                                              "wants": f"{claim} claim: {flow.get('issue', '')}",
                                              "tried": f"booked appointment {booked.appointment_id} as a normal visit",
                                              "constraints": "warranty not verifiable from the database", "mood": "",
                                              "reason_tag": "warranty review", "appointment_id": booked.appointment_id})
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
        if parse_request(text, now):
            return _with_fee(db, flow, now, _make_offer(db, customer, flow, text, now))
        if EARLIER.search(text):
            return _earlier(db, customer, flow, now)
        if flow["step"] == "offer":
            return _with_fee(db, flow, now, FlowResult(_offer_facts(flow["offered"], "Ask which of these slots suits, or what "
                                                                    "other time works:"), "booking offer"))
        return FlowResult(["Ask what day and time the caller would like instead."], "booking offer")
    # Read-back for a cancel or reschedule.
    appointment = flow["appointment"]
    target = flow.get("chosen") or appointment
    if confirms(text, target["slot_date"], target["window"], now):
        if _deadline_passed():
            raise deadline.DeadlinePassed("not changing an appointment after the message deadline")
        if kind == "cancel":
            result = tx.cancel(db, customer, appointment["appointment_id"], flow["confirmation_id"], now, seed_db)
            what = f"Cancelled: your visit on {spoken_when(appointment['slot_date'], appointment['window'])}"
        else:
            chosen = flow["chosen"]
            result = tx.reschedule(db, customer, appointment["appointment_id"], chosen["slot_id"], flow["confirmation_id"],
                                   now, seed_db)
            what = f"Moved: your visit is now on {spoken_when(chosen['slot_date'], chosen['window'])}"
        if result.status == "taken":
            flow["step"] = "new_date"
            return _make_offer(db, customer, flow, "", now, "That slot was just taken. Offer these instead:")
        state.flow, state.active_flow = {}, None
        if result.status == "not found":
            return FlowResult(["That appointment had already changed, so nothing was changed. Would you like me to check "
                               "your appointments again?"], "confirmation",
                              db_actions=[f"no change to appointment {appointment['appointment_id']}"])
        state.tried.append(f"{result.status} appointment {appointment['appointment_id']}")
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
