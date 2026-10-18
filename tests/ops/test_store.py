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
