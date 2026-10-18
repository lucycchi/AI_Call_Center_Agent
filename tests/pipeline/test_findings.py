import sqlite3
from pathlib import Path

import pytest

from pipeline.capacity import capacity_by_zone, zone_mismatches
from pipeline.findings import HANDLING, human_baseline, rank_reasons, write_findings
from pipeline.staff_checks import staff_policy_errors
from pipeline.transcripts import Call

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"


def make(call_id, seconds, customer, agent):
    return Call(call_id, "2026-07-01T10:00", "Tasha", seconds, customer, agent)


def test_rank_reasons_by_calls_with_minutes_and_running_total():
    calls = [make("A", 120, ["book"], []), make("B", 60, ["book"], []), make("C", 90, ["bill"], [])]
    labels = {"A": "new booking", "B": "new booking", "C": "billing"}
    rows = rank_reasons(calls, labels)
    assert [r.reason for r in rows] == ["new booking", "billing"]
    assert rows[0].calls == 2 and rows[0].share == pytest.approx(0.667, abs=0.001)
    assert rows[0].minutes == 3.0 and rows[0].running_total == pytest.approx(0.667, abs=0.001)
    assert rows[1].running_total == 1.0


@pytest.mark.parametrize("customer, agent, expected", [
    (["My AC is out"], ["I can add you to the waitlist for cancellations."], "offered a waitlist"),
    (["I smell something burning from the vents"], ["You're booked. The diagnostic fee is $89."], "booked a burning smell as a normal visit"),
    (["I want a manager"], ["I'm going to escalate this to our service manager. She'll call you back today."], "promised a manager callback today"),
    (["I have a tech coming tomorrow but something came up. Can I move it?"], ["I can do Friday 8 to 12.", "Moved."], "moved a next-day appointment without the $49 fee"),
    (["I got an invoice"], ["It's the diagnostic fee plus the contactor replacement."], "explained an invoice as the diagnostic fee plus the repair"),
    (["Okay. Let's schedule it then."], ["Anything else today?"], "dropped a booking the caller asked for"),
    (["I want a full refund"], ["Refund requests go to our billing supervisor. You'll hear back within two business days."], "promised a refund callback in two business days"),
])
def test_each_staff_policy_error_pattern_is_recognised(customer, agent, expected):
    assert staff_policy_errors([make("X", 60, customer, agent)])[expected] == 1


def test_human_baseline_counts_resolved_calls_and_action_dependence():
    calls = [make("A", 60, ["balance?"], ["You have an open balance of $245."]),
             make("B", 60, ["pay"], ["I can text you a secure payment link."]),
             make("C", 60, ["refund"], ["Refund requests go to our billing supervisor."]),
             make("D", 60, ["Okay. Let's schedule it then."], ["Anything else today?"])]
    baseline = human_baseline(calls)
    assert baseline["resolved_on_call"] == 3
    assert baseline["resolved_without_account_actions"] == 2
    assert baseline["dropped_bookings"] == 1


def test_capacity_on_the_real_database_shows_the_gaps():
    db = sqlite3.connect(DB)
    capacity = capacity_by_zone(db)
    assert capacity["north"]["plumbing"] == 0
    assert capacity["central"]["estimate"] == 0
    assert capacity["north"]["customers"] == 108


def test_zone_mismatches_lists_seeded_appointments_outside_the_customers_zone():
    mismatches = zone_mismatches(sqlite3.connect(DB))
    assert mismatches
    assert all(m["slot_zone"] != m["customer_zone"] for m in mismatches)


def test_every_top_three_sub_reason_has_a_handling_route():
    for sub in ["hvac repair", "plumbing", "tune-up", "burning smell", "current balance", "pay an invoice",
                "what an invoice is for", "charged twice", "quote dispute", "refund", "what it includes or price",
                "renewal date", "autopay", "cancel", "upgrade", "member discount on a new system"]:
        assert HANDLING[sub] in {"documents", "lookups", "booking", "handoff"}


def test_findings_document_has_the_required_parts(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out)
    text = out.read_text()
    assert "| Rank | Call reason | Calls | Share | Staff minutes | Running total | Handled or handed off | Reason |" in text
    for heading in ["## Method", "## Observed top three", "## Agent scope", "## Human baseline",
                    "## Executive findings", "### Staff policy errors", "### Capacity imbalance by zone",
                    "### Documentation gaps", "## Seeded appointments outside the customer's zone", "## Glossary"]:
        assert heading in text
    assert "templated" in text
    assert "no human labeled" in text.lower()


def test_offering_a_slot_without_confirming_it_is_a_dropped_booking():
    call = make("X", 60, ["Yeah, add it and book the visit.", "Book it."], ["Done. I have tomorrow 12 to 4.", "Anything else?"])
    assert staff_policy_errors([call])["dropped a booking the caller asked for"] == 1


def test_emailing_an_invoice_copy_is_not_an_account_action():
    calls = [make("A", 60, ["What is this invoice for?"], ["It's the diagnostic fee plus the drain line clearing.",
                                                            "Absolutely, sending that to the email on file now."])]
    assert human_baseline(calls)["resolved_without_account_actions"] == 1
