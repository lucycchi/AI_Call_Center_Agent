"""Fixes from the Codex review of Milestone 7 (docs/MILESTONE7_REVIEW.md), each named by its finding."""

import sqlite3

from app.ops.masking import mask
from tests.flows.scripted import request
from tests.flows.test_conversations import chat, clear  # noqa: F401  (the fixture)


def actions(chat):
    return chat["store"].account_actions()


def tier(chat, customer="MHC-10001"):
    return sqlite3.connect(chat["db"]).execute("select membership_tier from customers where customer_id = ?",
                                               (customer,)).fetchone()[0]


def upgrade_read_back(chat):
    chat["routes_add"]("upgrade me to plus", clear(request("upgrade me to plus", "account", "action")))
    chat["say"]("I'm Linda Foster, MHC-10001, please upgrade me to Plus")


# -- an emergency leaves a previous action armed (I1) ---------------------------------------------------------------

def test_an_emergency_drops_a_waiting_action(chat):
    upgrade_read_back(chat)
    chat["say"]("I smell gas")
    chat["say"]("yes")
    assert tier(chat) == "standard" and actions(chat) == []


# -- committed actions can finish silently (I2) ---------------------------------------------------------------------

def test_a_done_action_is_confirmed_in_fixed_text_even_if_the_writer_says_something_blocked(chat):
    upgrade_read_back(chat)
    chat["writer_says"](lambda facts: ["You're on the waitlist for an earlier slot."])  # a blocked promise
    reply, done = chat["say"]("yes")
    assert tier(chat) == "plus" and "Done" in reply and "upgraded" in reply and "waitlist" not in reply


# -- payment-data masking is bypassable (S1) ------------------------------------------------------------------------

def test_dotted_card_numbers_and_bank_numbers_are_masked():
    assert "4111" not in mask("card 4111.1111.1111.1111 please")
    assert "123456789012" not in mask("my account is 123456789012 and routing 021000021")
    assert "021000021" not in mask("routing 021000021")
    assert mask("call 512-555-0101 about INV-204411, MHC-10001") == "call [phone] about INV-204411, MHC-10001"


def test_a_typed_bank_number_gets_the_security_reply(chat):
    upgrade_read_back(chat)
    reply, _ = chat["say"]("just take it from my bank, account 123456789012")
    assert "123456789012" not in reply and "secure" in reply.lower()


# -- membership change and action record half-committed (D1) --------------------------------------------------------

def test_a_failed_action_record_rolls_back_the_membership_change(chat, monkeypatch):
    upgrade_read_back(chat)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(chat["store"], "record_action", broken)
    chat["say"]("yes")
    assert tier(chat) == "standard"


# -- auto-renew state is write-only and survives the reset (I4) -----------------------------------------------------

def test_the_membership_lookup_says_auto_renew_is_off_after_it_was_turned_off(chat):
    chat["routes_add"]("turn off auto-renew", clear(request("turn off auto-renew", "account", "action")))
    chat["routes_add"]("when does my membership renew", clear(request("when does my membership renew", "account",
                                                                       "membership")))
    chat["say"]("I'm Grace Okafor, MHC-10003, please turn off auto-renew")
    chat["say"]("yes")
    reply, _ = chat["say"]("when does my membership renew?")
    assert "auto-renew is off" in reply.lower() and "renews" not in reply.lower()


def test_the_nightly_reset_clears_the_auto_renew_table(tmp_path):
    import shutil
    from app.ops.jobs import restore
    seed = tmp_path / "seed.sqlite"
    shutil.copy(SEED, seed)
    live = tmp_path / "live.sqlite"
    shutil.copy(SEED, live)
    db = sqlite3.connect(live)
    db.execute("create table membership_settings (customer_id text primary key, auto_renew integer not null, "
               "changed_at text not null, conversation_id text)")
    db.execute("insert into membership_settings values ('MHC-10003', 0, 'x', null)")
    db.commit()
    db.close()
    restore(live, seed)
    db = sqlite3.connect(live)
    assert not db.execute("select 1 from sqlite_master where name = 'membership_settings'").fetchone()


# -- payment links recorded as already expired (I5) -----------------------------------------------------------------

def test_a_link_expires_24_hours_after_it_is_recorded(chat):
    from datetime import datetime, timedelta
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    chat["say"]("yes")
    [sent] = actions(chat)
    made, expires = datetime.fromisoformat(sent["created_at"]), datetime.fromisoformat(sent["expires_at"])
    assert expires - made == timedelta(hours=24)


# -- action records escape the 30-day purge (S2) --------------------------------------------------------------------

def test_the_purge_removes_a_purged_conversations_action_records(chat):
    chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link")
    chat["say"]("yes")
    assert actions(chat)
    chat["store"].purge_before("9999-01-01")
    assert actions(chat) == []


# -- ticket "wants" is not the whole interaction (I6) ---------------------------------------------------------------

def test_a_problem_given_with_an_account_number_is_kept_in_the_ticket(chat):
    from app.core.pipeline import _caller_words, _only_identity
    assert not _only_identity("MHC-10001 sink is backed up")
    assert _only_identity("Linda Foster, MHC-10001")
    assert _only_identity("Sure, it's Kim Murphy, 512-494-3705.")
    early = ["My kitchen sink is backing up into the dishwasher"] + ["Can you hear me okay?"] * 30
    assert "kitchen sink" in _caller_words(early, "Monday please")


# -- different account actions collapse into one (I3) ---------------------------------------------------------------

def test_two_actions_in_one_message_are_both_offered(chat):
    chat["routes_add"]("payment link and set up autopay", clear(request("send me a payment link", "account", "action"),
                                                                request("set up autopay", "account", "action")))
    reply, _ = chat["say"]("I'm Omar Patel, MHC-10002, send me a payment link and set up autopay")
    assert "payment link" in reply.lower()
    reply, _ = chat["say"]("yes")
    assert [a["kind"] for a in actions(chat)] == ["payment link"] and "autopay" in reply.lower()
    chat["say"]("yes")
    assert [a["kind"] for a in actions(chat)] == ["payment link", "autopay link"]


SEED = __import__("pathlib").Path(__file__).resolve().parents[2] / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
