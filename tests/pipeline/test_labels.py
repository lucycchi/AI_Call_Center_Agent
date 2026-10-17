import csv
import json

import pytest

from pipeline.agreement import agreement, write_agreement
from pipeline.categories import CATEGORIES, REASONS
from pipeline.label_codex import CodexLabelError, label_with_codex
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


def test_agreement_file_is_provisional_until_the_author_returns_the_sheet(tmp_path):
    out = tmp_path / "agreement.json"
    write_agreement(out, codex={"T1": "billing", "T2": "membership"}, haiku_by_template={"T1": "billing", "T2": "billing"},
                    author=None)
    result = json.loads(out.read_text())
    assert result["status"] == "provisional"
    assert result["author_vs_codex"] is None
    assert result["codex_vs_haiku"] == 0.5
