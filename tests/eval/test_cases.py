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
    assert card["customer_id"].startswith("MHC-0")


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


def test_a_synthetic_caller_is_planted_as_a_customer_fixture(tmp_path):
    for case in _built(tmp_path):
        if case["caller_card"]["synthetic"]:
            planted = [f for f in case["fixtures"] if f["table"] == "customers"]
            assert planted and planted[0]["row"]["customer_id"] == case["caller_card"]["customer_id"]


def test_joining_the_membership_during_a_booking_call_is_an_action_gap_handoff(tmp_path):
    two_things = next(c for c in _built(tmp_path) if "Two things" in " ".join(c["caller_script"]))
    assert two_things["expected_outcome"] == "handed_off"
    assert two_things["expected_handoff_reason"] == "action gap"


# Milestone 2 gate fixes.

def _seed_ids(table, column):
    return {r[0] for r in sqlite3.connect(SEED).execute(f"select {column} from {table}")}


def test_caller_scripts_use_the_caller_cards_identity_not_the_transcripts(tmp_path):
    import re
    for case in _built(tmp_path):
        card, script = case["caller_card"], " ".join(case["caller_script"])
        assert set(re.findall(r"MHC-\d+", script)) <= {card["customer_id"]}, case["case_id"]
        assert set(re.findall(r"\b\d{3}-\d{3}-\d{4}\b", script)) <= {card["phone"]}, case["case_id"]
    t = next(c for c in _built(tmp_path) if c["case_id"] == "T1b970162")
    assert "Robert Martinez" not in " ".join(t["caller_script"])
    assert t["caller_card"]["name"] in t["caller_script"][2]


def test_identity_lines_are_rewritten_with_the_card():
    from eval.build_cases import use_card
    card = {"customer_id": "MHC-55555", "name": "Ana Cruz", "phone": "512-111-2222",
            "service_address": "9 Elm Way", "city": "Kyle"}
    lines = ["Yeah, it's MHC-25306.", "Um, david Foster.", "Sure, it's Maria Murphy, 512-318-7661.",
             "Tom Murphy, 1077 Maple St, Pflugerville.", "It's 4682 Maple St, Leander.", "Book it.", "Got it. Thanks."]
    assert use_card(lines, card) == ["Yeah, it's MHC-55555.", "Um, Ana Cruz.", "Sure, it's Ana Cruz, 512-111-2222.",
                                     "Ana Cruz, 9 Elm Way, Kyle.", "It's 9 Elm Way, Kyle.", "Book it.", "Got it. Thanks."]


def test_billing_fixtures_plant_the_invoice_the_caller_describes(tmp_path):
    import re
    for case in _built(tmp_path):
        if case["reason"] != "billing":
            continue
        invoice = next(f["row"] for f in case["fixtures"] if f["table"] == "invoices")
        named = re.findall(r"INV-\d{6}", " ".join(case["caller_script"]))
        if named:
            assert invoice["invoice_id"] == named[0], case["case_id"]
        assert invoice["invoice_id"] not in _seed_ids("invoices", "invoice_id")
    dispute = next(c for c in _built(tmp_path) if c["case_id"] == "T4ecda9c7")
    assert next(f["row"] for f in dispute["fixtures"] if f["table"] == "invoices")["amount_cents"] == 14900


def test_a_case_with_two_requests_expects_both_parts(tmp_path):
    cases = {c["case_id"]: c for c in _built(tmp_path)}
    booking = cases["T9e29febc"]
    parts = {r["request"]: r["expected_outcome"] for r in booking["requests"]}
    assert parts["hvac repair"] == "contained" and parts["join the Comfort Club"] == "handed_off"
    assert booking["needs_documents"] and booking["reference_answer"]
    invoice = cases["Tb9afdda4"]
    assert [r["expected_outcome"] for r in invoice["requests"]] == ["contained", "handed_off"]
    assert invoice["expected_outcome"] == "handed_off" and invoice["expected_handoff_reason"] == "action gap"
    for case in cases.values():
        assert case["requests"] and case["requests"][0]["request"] == case["sub_reason"]


def test_saying_you_are_a_member_is_not_a_request_to_join():
    from eval.build_cases import extra_requests
    assert extra_requests("new booking", ["I'm a Comfort Club member and my AC is out."]) == []
    assert [r["request"] for r in extra_requests("new booking", ["Is the maintenance plan worth it?", "Yeah, add it."])] \
        == ["join the Comfort Club"]


def test_any_stated_system_age_sets_the_install_year():
    from eval.build_cases import _requirements
    assert _requirements("replacement estimate", "My system is 18 years old")["install_after"] == "2008-01-01"
    need = _requirements("claim", "only three years old")
    assert (need["install_after"], need["install_before"]) == ("2023-01-01", "2023-12-31")


def test_existing_appointments_fall_on_an_offered_window_without_double_booking_a_technician(tmp_path):
    from datetime import date
    db = sqlite3.connect(SEED)
    offered = {(date.fromisoformat(d).weekday(), w) for d, w in db.execute("select distinct slot_date, window from appointment_slots")}
    for case in _built(tmp_path):
        if case["sub_reason"] not in ("reschedule", "confirm", "cancel appointment", "technician late"):
            continue
        appointment = case["appointment"]
        assert appointment["zone"] == case["caller_card"]["zone"], case["case_id"]
        assert (date.fromisoformat(appointment["slot_date"]).weekday(), appointment["window"]) in offered
        if appointment["source"] == "planted":
            busy = db.execute("select count(*) from appointment_slots where slot_date = ? and tech_id = ? and window = ?",
                              (appointment["slot_date"], appointment["tech_id"], appointment["window"])).fetchone()[0]
            assert busy == 0, case["case_id"]


def test_synthetic_customer_ids_are_outside_the_real_range(tmp_path):
    db = sqlite3.connect(SEED)
    card = caller_card(db, zone="south", tier="plus", brand="Trane", install_after="2026-10-01", install_before=None)
    assert card["customer_id"].startswith("MHC-0")
    assert card["customer_id"] not in _seed_ids("customers", "customer_id")


def test_the_card_says_whether_its_zone_came_from_the_transcript(tmp_path):
    for case in _built(tmp_path):
        assert case["caller_card"]["zone_source"] in ("transcript", "drawn")


def test_fixtures_refuse_the_live_database_and_never_overwrite(tmp_path, monkeypatch):
    import dataclasses

    import eval.fixtures as fixtures
    live = tmp_path / "live.sqlite"
    shutil.copy(SEED, live)
    monkeypatch.setattr(fixtures, "SETTINGS", dataclasses.replace(fixtures.SETTINGS, scheduling_db_path=live))
    with pytest.raises(ValueError):
        apply_fixtures(live, [])
    copy = tmp_path / "copy.sqlite"
    shutil.copy(SEED, copy)
    real = sqlite3.connect(SEED).execute("select customer_id from customers limit 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        apply_fixtures(copy, [{"table": "customers", "row": {"customer_id": real, "name": "X", "phone": "1",
                                                            "service_address": "a", "city": "Kyle", "zip": "78640"}}])


def test_evidence_spans_are_the_answering_lines_not_the_chunkers_sections(monkeypatch):
    import eval.build_cases as build
    monkeypatch.setattr(build, "chunk_document", lambda *_: (_ for _ in ()).throw(AssertionError("uses the chunker")), raising=False)
    [span] = build._spans([("membership__comfort_club_overview.md", "Plans", ("$500 off any full system replacement",))])
    assert span["start_line"] == span["end_line"] == 25
    lines = (ROOT / "data" / "kb_text" / "faq__customer_faq.md").read_text().splitlines()
    [span] = build._spans([("faq__customer_faq.md", "Payment", ("Card numbers",))])
    assert "Card numbers" in lines[span["start_line"] - 1]
