import csv
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from eval.build_cases import build_cases, caller_card, expected_outcome
from eval.fixtures import apply_fixtures
from eval.split import freeze_hash, split_templates, write_split_counts

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"


def rows():
    return list(csv.DictReader((ROOT / "data" / "templates.csv").open()))


def codex():
    return {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}


def test_no_template_or_family_is_on_both_sides_and_split_is_repeatable():
    split = split_templates(rows(), codex(), seed=20261016)
    assert not set(split.working) & set(split.held_out)
    family = {r["template_id"]: r["family"] for r in rows()}
    assert not {family[t] for t in split.working} & {family[t] for t in split.held_out}
    again = split_templates(rows(), codex(), seed=20261016)
    assert again == split


def test_every_reason_with_two_or_more_families_is_on_both_sides():
    split = split_templates(rows(), codex(), seed=20261016)
    family = {r["template_id"]: r["family"] for r in rows()}
    families_by_reason = {}
    for template, (reason, _) in codex().items():
        families_by_reason.setdefault(reason, set()).add(family[template])
    sides = {"working": set(split.working), "held_out": set(split.held_out)}
    for reason, fams in families_by_reason.items():
        if len(fams) >= 2:
            for side, templates in sides.items():
                assert any(codex()[t][0] == reason for t in templates), (reason, side)


def test_split_counts_file_adds_up_to_420_calls(tmp_path):
    split = split_templates(rows(), codex(), seed=20261016)
    out = tmp_path / "counts.csv"
    write_split_counts(rows(), codex(), split, out)
    table = list(csv.DictReader(out.open()))
    assert sum(int(r["corpus_calls"]) for r in table) == 420
    assert sum(int(r["working_calls"]) + int(r["held_out_calls"]) for r in table) == 420
    assert {"reason", "corpus_templates", "working_templates", "held_out_templates"} <= set(table[0])


def test_freeze_hash_changes_when_a_case_changes(tmp_path):
    case = tmp_path / "T1.json"
    case.write_text('{"a": 1}')
    first = freeze_hash([case])
    case.write_text('{"a": 2}')
    assert freeze_hash([case]) != first


def test_caller_card_matches_zone_tier_and_brand_from_the_database():
    db = sqlite3.connect(SEED)
    card = caller_card(db, zone="north", tier="standard", brand="Trane", install_after=None, install_before=None)
    assert card["zone"] == "north" and card["membership_tier"] == "standard" and card["system_brand"] == "Trane"
    assert not card["synthetic"]


def test_caller_card_is_synthetic_when_no_customer_matches():
    db = sqlite3.connect(SEED)
    card = caller_card(db, zone="south", tier="plus", brand="Trane", install_after="2026-10-01", install_before=None)
    assert card["synthetic"] is True
    assert card["customer_id"].startswith("MHC-9")


def test_billing_fixture_goes_into_a_copy_never_the_original(tmp_path):
    before = SEED.stat().st_mtime
    copy = tmp_path / "copy.sqlite"
    shutil.copy(SEED, copy)
    apply_fixtures(copy, [{"table": "invoices", "row": {"invoice_id": "INV-999001", "customer_id": "MHC-10002",
                                                      "appointment_id": None, "issued_date": "2026-10-01",
                                                      "due_date": "2026-10-31", "amount_cents": 24500,
                                                      "balance_cents": 24500, "line_items": "[]"}}])
    assert sqlite3.connect(copy).execute("select count(*) from invoices where invoice_id='INV-999001'").fetchone()[0] == 1
    assert sqlite3.connect(SEED).execute("select count(*) from invoices where invoice_id='INV-999001'").fetchone()[0] == 0
    assert SEED.stat().st_mtime == before


@pytest.mark.parametrize("reason, sub, zone, expected", [
    ("billing", "quote dispute", "north", ("handed_off", "dispute")),
    ("billing", "charged twice", "north", ("contained", None)),
    ("billing", "current balance", "south", ("contained", None)),
    ("billing", "pay an invoice", "south", ("handed_off", "action gap")),
    ("existing appointment", "technician late", "north", ("handed_off", "late technician")),
    ("new booking", "plumbing", "north", ("clean_decline", "no plumbing capacity in north zone")),
    ("new booking", "plumbing", "south", ("contained", None)),
    ("new booking", "burning smell", "north", ("handed_off", "burning smell")),
    ("replacement estimate", "replacement estimate", "central", ("clean_decline", "no estimate capacity in central zone")),
    ("safety emergency", "gas, carbon monoxide or sparks", "north", ("handed_off", "emergency")),
    ("hiring", "hiring", "north", ("redirect", None)),
    ("membership", "autopay", "north", ("handed_off", "action gap")),
    ("membership", "renewal date", "north", ("contained", None)),
])
def test_expected_outcomes_follow_the_handled_reason_list(reason, sub, zone, expected):
    assert expected_outcome(reason, sub, zone) == expected


def test_built_cases_cover_every_template_and_knowledge_cases_have_evidence(tmp_path):
    cases = build_cases(tmp_path, seed=20261016)
    assert len(cases) == len({r["template_id"] for r in rows()})
    for case in cases:
        saved = json.loads((tmp_path / f"{case['case_id']}.json").read_text())
        assert saved["caller_card"]["customer_id"]
        if saved["needs_documents"]:
            assert saved["evidence_spans"], case["case_id"]
            for span in saved["evidence_spans"]:
                assert (ROOT / "data" / "kb_text" / span["file"]).exists()
                assert span["start_line"] <= span["end_line"]
            assert saved["reference_answer"]


def test_building_twice_gives_identical_cases(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    build_cases(first, seed=20261016)
    build_cases(second, seed=20261016)
    assert freeze_hash(list(first.glob("*.json"))) == freeze_hash(list(second.glob("*.json")))


def _built(tmp_path):
    build_cases(tmp_path, seed=20261016)
    return [json.loads(p.read_text()) for p in sorted(tmp_path.glob("*.json"))]


def test_every_existing_appointment_case_plants_the_appointment_in_the_callers_zone(tmp_path):
    for case in _built(tmp_path):
        if case["sub_reason"] in ("reschedule", "confirm", "cancel appointment", "technician late"):
            appointment = next((f for f in case["fixtures"] if f["table"] == "appointments"), None)
            slot = next((f for f in case["fixtures"] if f["table"] == "appointment_slots"), None)
            assert appointment and slot, case["case_id"]
            assert appointment["row"]["slot_id"] == slot["row"]["slot_id"]
            assert slot["row"]["zone"] == case["caller_card"]["zone"], case["case_id"]
            assert sqlite3.connect(SEED).execute("select count(*) from appointment_slots where slot_id = ?",
                                                 (slot["row"]["slot_id"],)).fetchone()[0] == 0


def test_a_synthetic_caller_is_planted_as_a_customer_fixture(tmp_path):
    for case in _built(tmp_path):
        if case["caller_card"]["synthetic"]:
            planted = [f for f in case["fixtures"] if f["table"] == "customers"]
            assert planted and planted[0]["row"]["customer_id"] == case["caller_card"]["customer_id"]


def test_joining_the_membership_during_a_booking_call_is_an_action_gap_handoff(tmp_path):
    two_things = next(c for c in _built(tmp_path) if "Two things" in " ".join(c["caller_script"]))
    assert two_things["expected_outcome"] == "handed_off"
    assert two_things["expected_handoff_reason"] == "action gap"
