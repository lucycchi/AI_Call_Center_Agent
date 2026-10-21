import re
import sqlite3
from pathlib import Path

import pytest

from app.ops.masking import mask
from app.ops.store import OpsStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    ops = OpsStore(tmp_path / "ops.sqlite")
    ops.open_conversation("v1", "c1")
    ops.open_conversation("v2", "c2")
    return ops


def test_masking_keeps_names_and_account_numbers():
    assert mask("call me at 512-555-0101 or omar.patel@example.com, 901 Brookside Ct") == "call me at [phone] or [email], [street]"
    assert mask("Omar Patel, MHC-10002, INV-204411 for $478.00") == "Omar Patel, MHC-10002, INV-204411 for $478.00"
    assert mask("(512) 555 0101 and 4412 oak hollow drive, Round Rock") == "[phone] and [street], Round Rock"


def test_messages_are_stored_masked(store):
    message = store.log_message("c1", "caller", "my number is 512-555-0101")
    assert store.message_text(message) == "my number is [phone]"


def test_tickets_count_up_with_priority_by_reason(store):
    first = store.create_ticket("c1", "Omar Patel", "help", "lookup", "", "calm", "emergency")
    second = store.create_ticket("c1", "Omar Patel", "help", "lookup", "", "calm", "billing review")
    third = store.create_ticket(None, "Omar Patel", "fee check", "none", "after-hours 144 vs 149", "", "billing review")
    assert (first, second, third) == (1, 2, 3)
    assert [t["priority"] for t in store.tickets()] == [2, 0, 0]
    assert store.create_ticket("c1", "x", "y", "z", "", "", "burning smell") and store.tickets()[-1]["priority"] == 2
    assert store.create_ticket("c1", "x", "y", "z", "", "", "dispute") and store.tickets()[-1]["priority"] == 1


def test_ticket_text_is_masked(store):
    ticket = store.create_ticket("c1", "Omar Patel, 512-555-0102", "wants a call at 901 Brookside Ct", "", "", "", "dispute")
    row = next(t for t in store.tickets() if t["ticket_id"] == ticket)
    assert row["who"] == "Omar Patel, [phone]" and row["wants"] == "wants a call at [street]"


def test_a_visitor_never_sees_another_visitors_tickets(store):
    mine = store.create_ticket("c1", "a", "b", "c", "", "", "dispute")
    store.create_ticket("c2", "d", "e", "f", "", "", "dispute")
    assert [t["ticket_id"] for t in store.tickets_for_visitor("v1")] == [mine]


def test_messages_after_a_handoff_are_appended_to_the_ticket(store):
    ticket = store.create_ticket("c1", "a", "b", "c", "", "", "dispute")
    later = store.log_message("c1", "caller", "also it was a Tuesday")
    store.append_to_ticket(ticket, later)
    assert store.ticket_messages(ticket) == ["also it was a Tuesday"]


def test_sentences_replay_in_order(store):
    message = store.log_message("c1", "agent", "")
    for text in ("First.", "Second.", "Third."):
        store.log_sentence(message, text)
    assert store.sentences(message) == ["First.", "Second.", "Third."]


def test_receipts_model_calls_and_events_are_logged(store):
    message = store.log_message("c1", "agent", "Your balance is $478.00.")
    store.log_receipt(message, "clear", "account question, clear", [], [], "invoice lookup MHC-10002", "supported")
    store.log_model_call(message, "write", "claude-sonnet-5-5", "anthropic 1.15.0", {"effort": "low"}, 2100, 85, 1650, 3100)
    store.log_event("blocked sentence", "promised a waiver", "c1")
    assert store.receipt(message)["db_action"] == "invoice lookup MHC-10002"


def test_every_table_in_the_architecture_exists_in_write_ahead_logging_mode(tmp_path):
    OpsStore(tmp_path / "new.sqlite")
    db = sqlite3.connect(tmp_path / "new.sqlite")
    assert db.execute("pragma journal_mode").fetchone()[0] == "wal"
    tables = {r[0] for r in db.execute("select name from sqlite_master where type = 'table'")}
    section = (ROOT / "docs" / "ARCHITECTURE.md").read_text().split("### 4.2 Operations database")[1].split("## 5.")[0]
    documented = {name.lower() for name in re.findall(r"^    ([A-Z_]+) \{", section, re.M)}
    assert documented and documented <= tables, documented - tables


def test_every_seeded_customer_address_is_masked_and_streets_with_old_or_the_too():
    from app.flows.identify import has_identifier
    seed = sqlite3.connect(ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite")
    addresses = [r[0] for r in seed.execute("select service_address from customers")]
    addresses += ["1200 Old Mill Rd", "8 Old Manor Rd", "310 Old Bee Caves Rd", "4500 The Lakes Blvd"]
    for address in addresses:
        assert mask(f"I live at {address}, Austin") == "I live at [street], Austin", address
        assert has_identifier(address), address


def test_the_idle_sweep_never_closes_a_conversation_with_a_recent_message(store):
    store.log_message("c1", "caller", "hello")
    store._write("update conversations set last_message_at = '2000-01-01T00:00:00' where conversation_id = 'c1'")
    store.close_idle()
    assert store.conversation("c1")["status"] == "open"


def test_a_later_reason_adds_its_tag_and_new_constraints_once(store):
    ticket = store.create_ticket("c1", "Omar Patel", "payment link", "none", "none", "calm", "action gap")
    store.add_reason(ticket, "dispute", "fee differs from schedule: after-hours 144 vs 149")
    store.add_reason(ticket, "dispute", "fee differs from schedule: after-hours 144 vs 149")
    store.add_reason(ticket, "action gap", "")
    assert store.ticket_tags(ticket) == ["action gap", "dispute"]
    assert store.tickets()[0]["constraints"] == "fee differs from schedule: after-hours 144 vs 149"


def _failing_tickets(ops, monkeypatch):
    def failing(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(ops, "create_ticket", failing)


def test_a_ticket_kept_in_the_backup_file_is_masked_there(store, tmp_path, monkeypatch):
    # Final review (F2): the backup file held the caller's phone number and street in plain text.
    _failing_tickets(store, monkeypatch)
    store.create_ticket_or_keep(conversation_id="c1", who="Linda Foster, 512-555-0101", wants="warranty claim: leak at "
                                "901 Brookside Ct", tried="booked", constraints="", mood="", reason_tag="warranty review")
    kept = (tmp_path / "ops.pending.jsonl").read_text()
    assert "555-0101" not in kept and "Brookside" not in kept and "[phone]" in kept and "Linda Foster" in kept


def test_a_ticket_kept_while_another_thread_retries_is_not_lost(store, tmp_path, monkeypatch):
    # Final review (F7): a ticket appended after a retry read the file was erased when the retry rewrote it.
    import threading
    _failing_tickets(store, monkeypatch)
    store.create_ticket_or_keep(conversation_id=None, who="first", wants="a", tried="", constraints="", mood="",
                                reason_tag="warranty review")
    monkeypatch.undo()
    original, entered, release = store.create_ticket, threading.Event(), threading.Event()

    def slow(**ticket):
        entered.set()
        release.wait(2)
        return original(**ticket)
    monkeypatch.setattr(store, "create_ticket", slow)
    retry = threading.Thread(target=store.retry_pending)
    retry.start()
    entered.wait(2)

    def keep():
        store.create_ticket_or_keep(conversation_id=None, who="second", wants="b", tried="", constraints="", mood="",
                                    reason_tag="warranty review")
    monkeypatch.setattr(store, "create_ticket", lambda **t: (_ for _ in ()).throw(sqlite3.OperationalError("busy")))
    keeper = threading.Thread(target=keep)
    keeper.start()
    keeper.join(0.3)
    monkeypatch.setattr(store, "create_ticket", original)
    release.set()
    retry.join(5)
    keeper.join(5)
    store.retry_pending()
    assert sorted(t["who"] for t in store.tickets()) == ["first", "second"]


def test_an_accepted_message_and_its_text_are_saved_together(store, monkeypatch):
    # Final review (F1): the empty placeholder was committed before the text, so a failed second write lost the text
    # and a retry of the same message was ignored.
    class FailingDb:  # the database refuses the accepted event, inside whatever transaction writes it
        def __init__(self, db):
            self.db = db

        def execute(self, sql, params=()):
            if "'accepted'" in sql:
                raise sqlite3.OperationalError("disk full")
            return self.db.execute(sql, params)
    monkeypatch.setattr(store, "_db", FailingDb(store._db))
    with pytest.raises(sqlite3.OperationalError):
        store.accept_message("c1", "m1", "please send someone Tuesday")
    monkeypatch.undo()
    assert store.request_reply("v1", "m1") is None  # nothing half-saved, so a retry is accepted again
    store.accept_message("c1", "m1", "please send someone Tuesday")
    assert store.accepted_text("c1", "m1") == "please send someone Tuesday"
