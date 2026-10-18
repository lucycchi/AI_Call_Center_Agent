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


def _section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    return rest[: rest.index("\n## ")] if "\n## " in rest else rest


def test_findings_are_written_provisionally_when_fable_labels_are_missing(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out, agreement={"codex_vs_haiku": 0.9, "fable_vs_codex": None, "fable_vs_codex_sub_reason": None,
                                   "fable_labels": 0, "status": "provisional", "fable_missing": ["T1"]})
    text = out.read_text()
    assert "provisional" in text.lower()
    assert "Perfect agreement" not in text


def test_agreement_wording_follows_the_numbers(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out, agreement={"codex_vs_haiku": 0.96, "fable_vs_codex": 0.94, "fable_vs_codex_sub_reason": 0.88,
                                   "fable_labels": 17, "status": "final", "fable_missing": []})
    method = _section(out.read_text(), "## Method")
    assert "96%" in method and "94%" in method and "88%" in method
    assert "Perfect agreement" not in method


def test_ranking_table_shows_the_top_five_and_the_rest_separately(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out)
    text = out.read_text()
    top = [line for line in _section(text, "## Top call reasons").splitlines() if line.startswith("| ") and line[2].isdigit()]
    assert len(top) == 5
    assert "## Other call reasons" in text


def test_each_handed_off_sub_reason_says_why(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out)
    scope = _section(out.read_text(), "## Agent scope")
    burning = next(line for line in scope.splitlines() if "burning smell" in line)
    assert "safety" in burning
    refund = next(line for line in scope.splitlines() if "| refund |" in line)
    assert "authority" in refund


def test_baseline_states_what_it_counts_and_the_figure_without_dropped_bookings(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out)
    baseline = _section(out.read_text(), "## Human baseline")
    assert "waitlist" in baseline
    assert "82%" in baseline


def test_exactly_three_executive_findings_and_members_today_wording(tmp_path):
    out = tmp_path / "FINDINGS.md"
    write_findings(out)
    text = out.read_text()
    executive = _section(text, "## Executive findings")
    assert executive.count("\n### ") == 3
    assert "members today" in executive
    mismatch_rows = [line for line in _section(text, "## Seeded appointments outside the customer's zone").splitlines()
                     if line.startswith("| ") and line[2].isdigit()]
    assert mismatch_rows
