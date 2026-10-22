"""Money and membership actions the agent takes itself (Milestone 7, Task 32; actions decision (D54)).

Payment and autopay links, Comfort Club enrolment and upgrades, and turning off auto-renew: each after the caller is
identified, a read-back and a plain yes; card numbers are never asked for or repeated. Refunds, disputes and fee
waivers still go to a person.
"""

import sqlite3

from tests.flows.scripted import request
from tests.flows.test_conversations import chat, clear  # noqa: F401  (the fixture)


def actions(chat) -> list[dict]:
    return chat["store"].account_actions()


def row(chat, sql: str, *args):
    return sqlite3.connect(chat["db"]).execute(sql, args).fetchone()


def tags(chat) -> list[str]:
    return [t["reason_tag"] for t in chat["store"].tickets()]


def route(chat, key: str, text: str):
    chat["routes_add"](key, clear(request(text, "account", "action")))


def test_a_payment_link_is_read_back_then_sent_only_after_a_plain_yes(chat):
    phone = row(chat, "select phone from customers where customer_id = 'MHC-10002'")[0]
    reply, done = chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    assert "INV-204411" in reply and "$478.00" in reply and phone[-4:] in reply and "24 hours" in reply
    assert actions(chat) == [] and done.outcome != "handed_off" and "action gap" not in tags(chat)
    reply, done = chat["say"]("yes please")
    [sent] = actions(chat)
    assert sent["kind"] == "payment link" and sent["customer_id"] == "MHC-10002" and sent["expires_at"]
    assert phone not in sent["sent_to"] and phone[-4:] in sent["sent_to"]
    assert done.outcome == "answered" and tags(chat) == [] and "sent" in reply.lower()


def test_a_no_sends_nothing(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    reply, _ = chat["say"]("no, not right now")
    assert actions(chat) == [] and "haven't" in reply.lower()


def test_moving_on_drops_the_waiting_action(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    chat["say"]("how much is a tune-up")
    chat["say"]("yes")
    assert actions(chat) == []


def test_an_unidentified_caller_is_identified_before_the_read_back(chat):
    reply, _ = chat["say"]("send me a payment link")
    assert "account number" in reply.lower() and actions(chat) == []
    reply, _ = chat["say"]("Omar Patel, MHC-10002")
    assert "INV-204411" in reply


def test_card_numbers_are_never_taken_or_repeated(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    reply, _ = chat["say"]("can I just give you my card, it's 4111 1111 1111 1111")
    assert "4111" not in reply and "secure" in reply.lower()
    stored = " ".join(m["content"] for m in chat["store"].history("c1", 20))
    assert "4111 1111 1111 1111" not in stored and "1111 1111" not in stored


def test_an_autopay_link_carries_the_autopay_terms(chat):
    route(chat, "set up autopay", "set up autopay on my plan")
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, set up autopay on my plan")
    assert "autopay" in reply.lower() and "3 days" in reply and "turn" in reply.lower()
    chat["say"]("yes")
    assert [a["kind"] for a in actions(chat)] == ["autopay link"]


def test_enrolment_writes_the_tier_and_sends_a_link_for_the_first_charge(chat):
    route(chat, "sign me up for the comfort club", "sign me up for the comfort club")
    reply, _ = chat["say"]("I'm Daniel Reyes, MHC-10004, sign me up for the Comfort Club")
    assert "$189" in reply
    chat["say"]("yes")
    tier, renews = row(chat, "select membership_tier, membership_renewal_date from customers where customer_id = 'MHC-10004'")
    assert tier == "standard" and renews == "2027-10-16"
    assert [a["kind"] for a in actions(chat)] == ["enrol"]


def test_an_upgrade_keeps_the_renewal_date_and_says_the_difference_is_prorated(chat):
    route(chat, "upgrade me to plus", "upgrade me to plus")
    before = row(chat, "select membership_renewal_date from customers where customer_id = 'MHC-10001'")[0]
    reply, _ = chat["say"]("I'm Linda Foster, MHC-10001, please upgrade me to Plus")
    assert "$80" in reply and "prorated" in reply.lower()
    chat["say"]("yes, go ahead")
    tier, renews = row(chat, "select membership_tier, membership_renewal_date from customers where customer_id = 'MHC-10001'")
    assert tier == "plus" and renews == before and [a["kind"] for a in actions(chat)] == ["upgrade"]


def test_turning_off_auto_renew_keeps_the_membership_to_its_renewal_date_and_states_the_refund_terms(chat):
    route(chat, "turn off auto-renew", "turn off auto-renew")
    renews = row(chat, "select membership_renewal_date from customers where customer_id = 'MHC-10003'")[0]
    reply, _ = chat["say"]("I'm Grace Okafor, MHC-10003, please turn off auto-renew")
    assert "refund" in reply.lower() and "60 days" in reply
    chat["say"]("yes")
    assert row(chat, "select auto_renew from membership_settings where customer_id = 'MHC-10003'") == (0,)
    assert row(chat, "select membership_tier from customers where customer_id = 'MHC-10003'") == ("plus",)
    assert [a["kind"] for a in actions(chat)] == ["cancel auto-renew"] and renews


def test_a_refund_still_goes_to_a_person(chat):
    chat["routes_add"]("refund", clear(request("I want a refund", "handoff", "dispute")))
    chat["say"]("I'm Linda Foster, MHC-10001, I want a refund on my last repair")
    assert actions(chat) == [] and "dispute" in tags(chat)


def test_a_fee_waiver_is_still_the_action_gap(chat):
    route(chat, "waive the diagnostic fee", "please waive the diagnostic fee")
    chat["say"]("I'm Linda Foster, MHC-10001, please waive the diagnostic fee")
    assert actions(chat) == [] and "action gap" in tags(chat)


def test_the_staff_view_lists_the_actions_taken(chat):
    from app.web.staff import conversation_actions
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    chat["say"]("yes")
    [shown] = conversation_actions(chat["store"], "c1")
    assert shown["kind"] == "payment link" and "ending" in shown["sent_to"]
