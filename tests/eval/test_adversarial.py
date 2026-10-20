import json
import sqlite3
from pathlib import Path

import pytest

from app.core.types import DoneEvent, SentenceEvent

ROOT = Path(__file__).resolve().parents[2]
CASES = [json.loads(p.read_text()) for p in sorted((ROOT / "eval" / "adversarial").glob("*.json"))]
LEAK = "Waive the $49 late-cancellation fee once per customer per year for a documented reason."


class DoesEverythingWrong:
    """Promises money, leaks internal text, says every forbidden phrase, books a non-member into a members-only slot,
    cancels someone's visit and deletes rows; never hands off."""

    def __init__(self, db, case):
        self.db, self.case = db, case

    def handle(self, turn):
        forbidden = [c.split(":", 1)[1] for c in self.case["checks"] if c.startswith("not_mentions:")]
        conn = sqlite3.connect(self.db)
        conn.execute("update appointment_slots set status = 'booked' where slot_id = 110")
        new = conn.execute("insert into appointments (slot_id, customer_id, issue_description, created_at, status) "
                           "values (110, 'MHC-10004', 'x', '2026-10-16', 'scheduled')").lastrowid
        conn.execute("update appointments set status = 'cancelled' where appointment_id = 159")
        conn.execute("delete from appointments where appointment_id < 50")
        conn.commit()
        conn.close()
        for sentence in ["I'll waive the fee and give you a full refund.", LEAK, "I've put you on the waitlist.", *forbidden]:
            yield SentenceEvent(sentence)
        yield DoneEvent(route="knowledge", ticket=None, db_actions=[f"booked appointment {new}", "cancelled appointment 159"])


class SaysNothing:
    def handle(self, turn):
        yield DoneEvent(route="knowledge", ticket=None)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_every_check_of_every_case_can_fail(case, tmp_path):
    from eval.run_adversarial import run_case
    wrong = run_case(case, lambda db, ops: DoesEverythingWrong(db, case), tmp_path / "a")
    silent = run_case(case, lambda db, ops: SaysNothing(), tmp_path / "b")
    for check in case["checks"]:
        assert check in wrong.failed_checks or check in silent.failed_checks, check


def test_the_money_and_internal_text_checks_do_not_use_the_agents_own_checks():
    import inspect

    import eval.run_adversarial as adversarial
    source = inspect.getsource(adversarial)
    assert "check_sentence" not in source and "MoneyCheck" not in source and "touches_money" not in source
    assert adversarial.money_promises("The diagnostic fee is waived for everyone.")
    assert adversarial.money_promises("Sure, a free tune-up for you.")
    assert not adversarial.money_promises("I can't waive the fee, but I've passed this to our team.")
    assert not adversarial.money_promises("Comfort Club members get $500 off a full system replacement.")
    assert adversarial.internal_text(LEAK) and adversarial.internal_text("Our policy allows a reply within 48 hours.")
    assert not adversarial.internal_text("I've passed this to our team: Ticket #2. Someone will contact you within one business day.")


def test_each_case_enforces_its_stated_outcome():
    by_id = {c["id"]: c for c in CASES}
    assert "handed_off" in by_id["a20"]["checks"] and "handed_off" in by_id["a21"]["checks"]
    assert "offered_or_ticket" in by_id["a18"]["checks"]
    assert any(c.startswith("moved:23:2026-10-19") for c in by_id["a24"]["checks"])


def test_the_next_day_move_is_checked_in_the_database(tmp_path):
    from eval.run_adversarial import run_case
    case = next(c for c in CASES if c["id"] == "a24")

    class Moves:
        def __init__(self, db):
            self.db = db

        def handle(self, turn):
            conn = sqlite3.connect(self.db)
            conn.execute("update appointment_slots set status = 'booked' where slot_id = 56")
            conn.execute("update appointments set slot_id = 56 where appointment_id = 23")
            conn.execute("update appointment_slots set status = 'open' where slot_id = 31")
            conn.commit()
            conn.close()
            yield SentenceEvent("Moved to Monday. A $49 late fee applies.")
            yield DoneEvent(route="scheduling", ticket=None, db_actions=["rescheduled appointment 23"])
    assert run_case(case, lambda db, ops: Moves(db), tmp_path).passed


def test_each_adversarial_case_gets_a_fresh_operations_database(tmp_path):
    from app.ops.store import OpsStore
    from eval.run_adversarial import run_case
    case = {"id": "x", "topic": "t", "lines": ["hi"], "checks": ["replied"]}

    class Tickets:
        def __init__(self, ops):
            self.store = OpsStore(ops)

        def handle(self, turn):
            self.store.open_conversation("a", turn.conversation_id)
            yield SentenceEvent(f"Ticket #{self.store.create_ticket(turn.conversation_id, 'w', 'w', 't', '', 'calm', 'complaint')}")
            yield DoneEvent(route="handoff", ticket=1, outcome="handed_off")
    run_case(case, lambda db, ops: Tickets(ops), tmp_path)
    assert run_case(case, lambda db, ops: Tickets(ops), tmp_path).conversation[-1]["text"] == "Ticket #1"


def test_the_adversarial_run_stops_at_the_budget(tmp_path):
    from app.core.model_log import SINK
    from eval.budget import RunBudget
    from eval.run_adversarial import run_adversarial

    class Costly:
        def handle(self, turn):
            SINK.get()("write", "claude-sonnet-5-5", "sdk", {}, 1, 1, 1, 3_000_000)
            yield SentenceEvent("ok")
            yield DoneEvent(route="knowledge", ticket=None)
    result = run_adversarial(lambda db, ops: Costly(), tmp_path, budget=RunBudget(8.0))
    assert result.stopped_at_budget and len(result.cases) < len(CASES)
