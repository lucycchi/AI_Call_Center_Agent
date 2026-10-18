"""Handoffs, messages after a handoff, and turning failures into handoffs (R57, R58, R59).

Handoff messages are fixed text written in code, so the ticket number and what happens next are always exact."""

import logging
import time

from app.core.deadline import DeadlinePassed
from app.flows.protocol import FlowResult

log = logging.getLogger("meridian.handoff")
OFFICE_HOURS = "Monday to Friday 7am to 7pm, or Saturday 8am to 4pm"
ERROR_MESSAGE = "I couldn't finish that just now, so I'm passing it to a team member to follow up."
NO_TICKET_MESSAGE = ("I'm sorry, I couldn't record your request just now. Please phone our office "
                     f"({OFFICE_HOURS}) and they can help you directly.")


def _message(ticket_id: int, reason_tag: str) -> str:
    if reason_tag in ("emergency", "burning smell"):
        return (f"This is flagged as an emergency for our team: Ticket #{ticket_id}. They will contact you as a "
                f"priority. You can keep asking me other questions here.")
    return (f"I've passed this to our team: Ticket #{ticket_id}. Someone will contact you within one business day. "
            f"You can keep asking me other questions here.")


def hand_off(state: dict, reason_tag: str, constraints: str) -> FlowResult:
    """Open a ticket with the five fields a staff member needs, and tell the caller its number."""
    store = state["store"]
    try:
        ticket_id = store.create_ticket(state.get("conversation_id"), state.get("who") or "caller not identified",
                                        state.get("wants") or "not stated", state.get("tried") or "nothing yet",
                                        constraints or "none", state.get("mood") or "calm", reason_tag,
                                        state.get("appointment_id"))
    except Exception as error:  # the operations database is unavailable
        log.error("ticket could not be saved for conversation %s (%s): %s", state.get("conversation_id"), reason_tag, error)
        try:
            store.log_event("write failure", f"ticket not saved: {reason_tag}: {error}", state.get("conversation_id"))
        except Exception:
            log.error("event could not be recorded either")
        return FlowResult([NO_TICKET_MESSAGE], "handoff", handoff_reason=reason_tag)
    state["ticket_id"] = ticket_id
    return FlowResult([_message(ticket_id, reason_tag)], "handoff", handoff_reason=reason_tag)


def add_to_open_ticket(state: dict, message_id: int) -> None:
    """After a handoff the chat stays open; later caller messages are added to the open ticket (R58)."""
    if state.get("ticket_id"):
        state["store"].append_to_ticket(state["ticket_id"], message_id)


def safe(step, on_error=None) -> FlowResult:
    """Run one flow step; any model, search or database error, or passing the message deadline, becomes a handoff.
    The step runs in this thread and checks the deadline itself, so nothing carries on after the handoff."""
    try:
        return step()
    except DeadlinePassed as error:
        detail = f"message deadline passed: {error}"
    except Exception as error:
        detail = f"flow step failed: {type(error).__name__}: {error}"
    log.error(detail)
    if on_error:
        on_error(detail)
    return FlowResult([ERROR_MESSAGE], "handoff", handoff_reason="error")


def confirm_booking(state: dict, booked, slot_date: str, window: str, service_type: str) -> FlowResult:
    """The booking has committed, so the caller is told even if logging it fails."""
    from datetime import date
    facts = [f"Booked: your {service_type.replace('_', ' ').replace('hvac', 'HVAC')} visit on {date.fromisoformat(slot_date):%A} {slot_date}, "
             f"{window}, with {booked.technician}."]
    for attempt in (1, 2):  # the booking has committed; retry the log write once
        try:
            state["store"].log_event("booking", f"appointment {booked.appointment_id} booked", state.get("conversation_id"))
            break
        except Exception as error:
            if attempt == 2:
                log.error("appointment %s booked but not logged: %s", booked.appointment_id, error)
            else:
                time.sleep(0.05)
    return FlowResult(facts, "confirmation", db_actions=[f"booked appointment {booked.appointment_id}"])
