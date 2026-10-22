"""A handoff carries the whole interaction (Milestone 7, Task 30).

Seen in the held-out run: four tickets were not actionable because each dropped the caller's problem (the backed-up
sink, the blower, the upgrade). The problem had been said in an earlier message, but the ticket's "wants" held only
the message that triggered the handoff, and only messages sent after the handoff were linked to the ticket.
"""

import sqlite3

from tests.flows.scripted import request
from tests.flows.test_conversations import chat, clear  # noqa: F401  (the fixture)


def _sink(chat):
    chat["routes_add"]("plumber", clear(request("I want to book a plumber for my sink", "scheduling", "book", "plumbing")))
    chat["say"]("I need a plumber, my kitchen sink is backing up into the dishwasher")
    return chat["say"]("Linda Foster, MHC-10001")  # north zone: no plumbing slots, so a clean decline with a ticket


def test_the_ticket_says_the_problem_given_before_the_handoff(chat):
    _, done = _sink(chat)
    [ticket] = chat["store"].tickets()
    assert done.ticket == ticket["ticket_id"]
    assert "kitchen sink is backing up" in ticket["wants"]


def test_the_ticket_holds_the_whole_conversation_so_far_both_sides(chat):
    _sink(chat)
    [ticket] = chat["store"].tickets()
    conversation = chat["store"].ticket_conversation(ticket["ticket_id"])
    roles = [m["role"] for m in conversation]
    texts = " ".join(m["text"] for m in conversation)
    assert roles[:2] == ["caller", "agent"] and "agent" in roles[2:]
    assert "kitchen sink is backing up" in texts and "Linda Foster" in texts


def test_messages_after_the_handoff_still_join_the_ticket(chat):
    _sink(chat)
    chat["say"]("Also, the water smells a bit")
    [ticket] = chat["store"].tickets()
    texts = [m["text"] for m in chat["store"].ticket_conversation(ticket["ticket_id"])]
    assert texts.count("Also, the water smells a bit") == 1


def test_the_staff_view_shows_the_whole_conversation_on_the_ticket(chat):
    from app.web.staff import ticket_view
    _sink(chat)
    [row] = chat["store"].tickets()
    view = ticket_view(chat["store"], row)
    assert any("kitchen sink" in m["text"] and m["role"] == "caller" for m in view["conversation"])


# -- between the agent's own flows ----------------------------------------------------------------------------------

def test_a_caller_identified_for_a_lookup_is_not_asked_again_to_book(chat):
    chat["say"]("I'm Linda Foster, MHC-10001, what's my balance?")
    reply, _ = chat["say"]("ok, I want to book a repair")
    assert "account number" not in reply.lower() and "your name" not in reply.lower()


def test_the_problem_said_in_a_question_carries_into_the_booking(chat):
    chat["routes_add"]("blowing warm air", clear(request("my AC is blowing warm air, what does a visit cost",
                                                         "knowledge", "fees")))
    chat["say"]("My AC is blowing warm air. What does a repair visit cost?")
    chat["say"]("I'm Linda Foster, MHC-10001, I want to book a repair")
    for _ in range(3):  # pick the first slot and confirm the read-back
        reply, done = chat["say"]("the first one")
        if "confirm" in reply.lower() or "correct" in reply.lower():
            reply, done = chat["say"]("yes")
            break
    db = sqlite3.connect(chat["db"])
    issues = [row[0] for row in db.execute("select issue_description from appointments where customer_id = 'MHC-10001' "
                                           "order by appointment_id desc limit 1")]
    assert issues and "blowing warm air" in issues[0]
