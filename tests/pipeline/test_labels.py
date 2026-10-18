import csv
import json

import pytest

from pipeline.agreement import agreement, write_agreement
from pipeline.categories import CATEGORIES, REASONS
from pipeline.label_codex import CodexLabelError, label_with_codex
from pipeline.label_fable import label_blind_third
from pipeline.label_haiku import label_with_haiku
from pipeline.sheet import write_author_sheet
from pipeline.transcripts import Call


def call(call_id, text):
    return Call(call_id, "2026-07-01T10:00", "Tasha", 60, [text], ["Sure, let me look that up."])


class FakeHaiku:
    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def label(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return self.answer


def test_categories_cover_the_reasons_from_the_data_review():
    for reason in ["new booking", "billing", "membership", "warranty", "existing appointment",
                   "complaint or manager", "replacement estimate", "safety emergency", "hiring",
                   "commercial", "wrong number"]:
        assert reason in REASONS
    assert ("billing", "current balance") in CATEGORIES


def test_haiku_label_is_stored_per_call():
    fake = FakeHaiku({"reason": "billing", "sub_reason": "current balance"})
    labels = label_with_haiku([call("C1", "What's my current balance?")], fake)
    assert labels["C1"] == ("billing", "current balance")


def test_haiku_label_outside_the_frozen_list_is_rejected():
    fake = FakeHaiku({"reason": "pizza", "sub_reason": "order"})
    with pytest.raises(ValueError, match="C1"):
        label_with_haiku([call("C1", "Can I order a pizza?")], fake)


def test_agreement_is_the_share_of_matching_labels():
    assert agreement({"t1": "billing", "t2": "membership"}, {"t1": "billing", "t2": "warranty"}) == 0.5


def test_codex_labels_every_template_once_without_seeing_haiku_labels():
    seen = []

    def runner(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"reason": "billing", "sub_reason": "current balance", "model": "gpt-frontier"})

    samples = {"T1": call("C1", "What's my current balance?"), "T2": call("C2", "Balance please")}
    labels = label_with_codex(samples, runner, haiku_labels={"C1": ("billing", "current balance")})
    assert set(labels) == {"T1", "T2"}
    assert len(seen) == 2
    assert all("Haiku" not in p and "suggested label" not in p.lower() for p in seen)
    assert labels["T1"] == ("billing", "current balance", "gpt-frontier")


def test_codex_invalid_json_names_the_template():
    with pytest.raises(CodexLabelError, match="T9"):
        label_with_codex({"T9": call("C9", "hello")}, lambda prompt: "not json", haiku_labels={})


def test_author_sheet_has_a_third_of_templates_and_no_ai_labels(tmp_path):
    templates = {f"T{i}": call(f"C{i}", f"request {i}") for i in range(30)}
    path = tmp_path / "sheet.csv"
    write_author_sheet(templates, path, seed=17)
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 10
    assert set(rows[0]) == {"template_id", "sample_call_id", "caller_request", "your_reason", "your_sub_reason"}
    again = tmp_path / "again.csv"
    write_author_sheet(templates, again, seed=17)
    assert path.read_text() == again.read_text()


def test_agreement_file_is_provisional_until_fable_labels_exist(tmp_path):
    out = tmp_path / "agreement.json"
    write_agreement(out, codex={"T1": "billing", "T2": "membership"}, haiku_by_template={"T1": "billing", "T2": "billing"},
                    fable=None)
    result = json.loads(out.read_text())
    assert result["status"] == "provisional"
    assert result["fable_vs_codex"] is None
    assert result["codex_vs_haiku"] == 0.5


def test_agreement_file_reports_fable_against_codex_on_the_blind_third(tmp_path):
    out = tmp_path / "agreement.json"
    write_agreement(out, codex={"T1": "billing", "T2": "membership", "T3": "warranty"},
                    haiku_by_template={"T1": "billing", "T2": "membership", "T3": "warranty"},
                    fable={"T1": "billing", "T3": "membership"})
    result = json.loads(out.read_text())
    assert result["status"] == "final"
    assert result["fable_vs_codex"] == 0.5
    assert result["fable_labels"] == 2


def test_fable_labels_only_the_blind_third_without_other_models_labels():
    fake = FakeHaiku({"reason": "warranty", "sub_reason": "claim"})
    samples = {"T1": call("C1", "My unit stopped working"), "T2": call("C2", "Balance please")}
    labels = label_blind_third(samples, ["T1"], fake)
    assert labels == {"T1": ("warranty", "claim")}
    assert len(fake.prompts) == 1
    assert "Haiku" not in fake.prompts[0] and "Codex" not in fake.prompts[0]


def test_codex_output_file_check_accepts_a_complete_valid_file(tmp_path):
    from pipeline.label_codex import validate_codex_file

    expected = {"T1": "C1", "T2": "C2"}
    good = tmp_path / "good.csv"
    good.write_text("template_id,sample_call_id,reason,sub_reason,model\n"
                    "T1,C1,billing,current balance,gpt-6.1-sol\nT2,C2,warranty,claim,gpt-6.1-sol\n")
    assert validate_codex_file(good, expected) == []


def test_codex_output_file_check_lists_every_problem(tmp_path):
    from pipeline.label_codex import validate_codex_file

    expected = {"T1": "C1", "T2": "C2", "T3": "C3"}
    bad = tmp_path / "bad.csv"
    bad.write_text("template_id,sample_call_id,reason,sub_reason,model\n"
                   "T1,C9,billing,current balance,gpt-6.1-sol\nT2,C2,pizza,order,\n")
    problems = validate_codex_file(bad, expected)
    assert any("T1" in p and "sample" in p for p in problems)
    assert any("T2" in p and "category" in p for p in problems)
    assert any("T2" in p and "model" in p for p in problems)
    assert any("T3" in p and "missing" in p for p in problems)


def test_haiku_label_per_template_is_the_majority_of_its_calls():
    from pipeline.agreement import majority_by_template

    templates = {"C1": "T1", "C2": "T1", "C3": "T1", "C4": "T2"}
    haiku = {"C1": "billing", "C2": "billing", "C3": "membership", "C4": "warranty"}
    assert majority_by_template(templates, haiku) == {"T1": "billing", "T2": "warranty"}


def test_agreement_is_final_only_when_every_blind_template_has_a_fable_label(tmp_path):
    out = tmp_path / "agreement.json"
    write_agreement(out, codex={"T1": "billing", "T2": "warranty"}, haiku_by_template={"T1": "billing", "T2": "warranty"},
                    fable={"T1": "billing"}, blind_ids=["T1", "T2"])
    result = json.loads(out.read_text())
    assert result["status"] == "provisional"
    assert result["fable_missing"] == ["T2"]
