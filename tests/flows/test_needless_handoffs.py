"""Needless handoffs found on the working set (Milestone 7, Task 31, run m7-working-1).

Each test names the working-set case it came from. None comes from the fresh test set, which is never looked at.
"""

from tests.flows.scripted import request
from tests.flows.test_conversations import chat, clear  # noqa: F401  (the fixture)


def tags(chat) -> list[str]:
    return [t["reason_tag"] for t in chat["store"].tickets()]


# -- an earlier slot (T391b9f20, T70425efa, Tf0d9c2f5) ---------------------------------------------------------------

def test_asking_for_earlier_when_the_earliest_are_offered_gets_told_so_without_a_ticket(chat):
    # The agent said "those three are the earliest slots" and opened a ticket in the same turn, then booked the visit:
    # a finished call counted as a handoff. R44 is met by offering the earliest eligible slots.
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair")
    reply, done = chat["say"]("anything earlier?")
    assert "earliest" in reply.lower() and "earlier slot" not in tags(chat) and done.outcome != "handed_off"


def test_asking_again_after_being_told_opens_the_earlier_slot_ticket(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair")
    chat["say"]("anything earlier?")
    chat["say"]("anything earlier?")
    assert tags(chat).count("earlier slot") == 1


# -- thinking it over (Tbaf67f84) ------------------------------------------------------------------------------------

def test_thinking_it_over_is_a_pause_not_a_wrong_number_or_a_ticket(chat):
    chat["say"]("how much is a tune-up")
    reply, done = chat["say"]("Okay, let me think about it.")
    assert "wrong number" not in reply.lower() and done.route != "redirect" and tags(chat) == []
    assert "take your time" in reply.lower() or "anything else" in reply.lower()


def test_saying_the_last_reply_was_a_mistake_gets_an_apology_not_a_complaint_ticket(chat):
    chat["say"]("how much is a tune-up")
    reply, done = chat["say"]("Sorry, that last reply seems like a mistake. I'm just thinking it over.")
    assert "sorry" in reply.lower() and tags(chat) == [] and done.outcome != "handed_off"


def test_a_real_complaint_after_a_mistake_still_goes_to_a_person(chat):
    chat["routes_add"]("speak to a manager", clear(request("I want to speak to a manager", "handoff", "complaint")))
    chat["say"]("how much is a tune-up")
    chat["say"]("that reply was a mistake, I want to speak to a manager")
    assert "complaint" in tags(chat)


# -- registration on the caller's own system (Tf7d382d9) ---------------------------------------------------------------

def test_a_registration_question_about_my_unit_is_answered_from_the_documents_too(chat):
    # The system lookup alone said only the install date; the warranty policy says Meridian registers every unit.
    chat["routes_add"]("register my new unit", clear(request("did you register my new unit with the manufacturer",
                                                             "account", "system")))
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, did you register my new unit with the manufacturer?")
    assert "installed" in reply.lower() and "$129" in reply  # the lookup, and the documents (the fake search's passage)


# -- an emailed invoice copy (Tb9afdda4) -----------------------------------------------------------------------------

def test_asking_for_an_emailed_invoice_copy_is_handed_off_not_dropped(chat):
    # The agent said it could not email and moved on: the request was dropped. No document says how copies are sent.
    chat["say"]("I'm Omar Patel, MHC-10002, what's my balance?")
    reply, done = chat["say"]("Oh okay. Can you email me an itemized copy?")
    assert "action gap" in tags(chat) and done.ticket  # an account action staff take (Tb9afdda4 expects this tag)
