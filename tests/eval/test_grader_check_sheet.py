"""A grade in the grader-check sheet stays only with the exact item it was given for, and starting a new sheet
archives the hidden verdicts and the result tables with the old sheet. Only local files in tmp_path are touched."""

import json

import pytest

from tests.eval.test_grader import _check_files


def _grade_everything(check, csvmod):
    rows = list(csvmod.DictReader(check.SHEET.open()))
    for row in rows:
        row["fable_correct (yes or no)"] = "yes"
    with check.SHEET.open("w", newline="") as handle:
        writer = csvmod.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _change_answers(check, change):
    path = check.RESULTS / "answers_to_grade.jsonl"
    answers = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps(change(a)) + "\n" for a in answers))


@pytest.mark.parametrize("change", [
    lambda a: {**a, "passages": ["[faq/customer_faq.md, Fees, 2026-03-02] Diagnostic fee: $99."]},
    lambda a: {**a, "question": "a different question"},
    lambda a: {**a, "reference_answer": "a different reference"},
], ids=["passages", "question", "reference answer"])
def test_a_grade_is_kept_only_for_the_same_question_reference_answer_and_passages(tmp_path, monkeypatch, change):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    _grade_everything(check, csvmod)
    check.write_sheet()  # nothing changed: the grades stay
    assert all(r["fable_correct (yes or no)"] == "yes" for r in csvmod.DictReader(check.SHEET.open()))
    _change_answers(check, change)
    with pytest.raises(SystemExit):
        check.write_sheet()
    assert all(r["fable_correct (yes or no)"] == "yes" for r in csvmod.DictReader(check.SHEET.open()))


def test_a_graded_sheet_without_fingerprints_is_not_carried_over(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    rows = _grade_everything(check, csvmod)
    with check.SHEET.open("w", newline="") as handle:  # a sheet written before rows carried a fingerprint
        columns = [c for c in rows[0] if c != "fingerprint"]
        writer = csvmod.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(SystemExit):
        check.write_sheet()


def test_a_new_sheet_archives_the_hidden_verdicts_and_the_result_tables_with_the_old_sheet(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    _grade_everything(check, csvmod)
    hidden = check.HIDDEN.read_text()
    for name in ("grader_check.json", "grader_check_claude.json", "grader_check_fable.json"):
        (check.OUT / name).write_text(json.dumps({"table": name}))
    check.write_sheet(new=True)
    archive = tmp_path / "grader_check_archive"
    [sheet] = list(archive.glob("*.csv"))
    number = sheet.stem
    assert (archive / f"{number}-{check.HIDDEN.name}").read_text() == hidden
    for name in ("grader_check.json", "grader_check_claude.json", "grader_check_fable.json"):
        assert json.loads((archive / f"{number}-{name}").read_text()) == {"table": name}
