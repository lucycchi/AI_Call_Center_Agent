"""Smaller guards: a results folder is never silently overwritten, quick runs get their own folders, a handoff with no
expected reason passes the reason check, and the internal-text check does not flag customer-facing wording.

Every run here is stubbed (agent, caller, grader, model, settings, keys); nothing reaches a model, Codex or the
held-out set."""

import csv
import json
import re
from pathlib import Path

import pytest

from tests.eval.test_grader import FakeRunner

ROOT = Path(__file__).resolve().parents[2]


def _run(tmp_path, **kwargs):
    from eval.run import run_graded
    from tests.eval.test_run_safety import Caller, SETTINGS, _cases
    from tests.eval.test_scoring import Recorder
    return run_graded(_cases(1), "t", out=tmp_path, factory=Recorder(), simulator_factory=lambda: Caller(),
                      runner=FakeRunner(), model="gpt-5.6-sol", settings=SETTINGS, **kwargs)


def test_a_run_refuses_a_results_folder_that_already_holds_attempts(tmp_path):
    _run(tmp_path)
    before = (tmp_path / "attempts.jsonl").read_text()
    with pytest.raises(SystemExit, match="--overwrite"):
        _run(tmp_path)
    assert (tmp_path / "attempts.jsonl").read_text() == before
    _run(tmp_path, overwrite=True)  # asked for explicitly
    assert len((tmp_path / "attempts.jsonl").read_text().splitlines()) == 1


def test_the_results_folder_check_never_allows_overwrite_with_final(tmp_path):
    from eval.run import check_results_folder
    check_results_folder(tmp_path / "new", overwrite=False, final=False)
    (tmp_path / "attempts.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit, match="--overwrite"):
        check_results_folder(tmp_path, overwrite=False, final=False)
    check_results_folder(tmp_path, overwrite=True, final=False)
    with pytest.raises(SystemExit, match="--final"):
        check_results_folder(tmp_path, overwrite=True, final=True)


def test_the_run_command_refuses_overwrite_with_final_before_anything_starts(monkeypatch):
    import dotenv

    import eval.harness as harness
    import eval.run as run

    def never(*args, **kwargs):
        raise AssertionError("a test must never start a real run")
    for module, name in [(run, "run_graded"), (run, "build_client"), (run, "engine_factory"), (run, "refuse_held_out"),
                         (dotenv, "load_dotenv"), (harness, "run_all")]:
        monkeypatch.setattr(module, name, never)
    monkeypatch.setattr("sys.argv", ["eval.run", "--final", "--overwrite", "--limit", "1"])
    with pytest.raises(SystemExit, match="--final"):
        run.main()


def test_quick_runs_write_to_their_own_timestamped_folders(monkeypatch):
    import eval.quick_run as quick
    from eval.quick_run import QuickResult
    names = []
    monkeypatch.setattr(quick, "quick_run", lambda n, name: names.append(name) or QuickResult(True))
    quick.quick_run_twice_of_three()
    assert len(names) == 2 and len(set(names)) == 2
    assert all(re.fullmatch(r"quick-\d{8}-\d{6}-run[123]", name) for name in names), names
    assert len({name.rsplit("-run", 1)[0] for name in names}) == 1  # the runs of one quick run share its time


def test_a_handoff_with_no_expected_reason_passes_the_reason_check_on_any_reason(tmp_path):
    from eval.grade_conversations import grade_attempts
    from eval.harness import Attempt
    from tests.eval.test_conversation_grading import _case, _db
    case = _case("transfer", "handed_off", reason=None)
    attempt = Attempt("c1", handed_off=True, db_path=str(_db(tmp_path)),
                      conversation=[{"role": "caller", "text": "hi"}, {"role": "agent", "text": "Passed on."}],
                      done_events=[{"db_actions": []}])
    [graded] = grade_attempts([attempt], {"c1": case}, FakeRunner(),
                              tickets=lambda a: [{"ticket_id": 1, "reason_tag": "anything at all"}])
    assert graded.grades["handoff_reason_correct"] is True and graded.all_correct is True


def _customer_documents():
    for row in csv.DictReader((ROOT / "data" / "document_list.csv").open()):
        path = ROOT / "call_data" / "knowledge_base" / row["path"]
        if row["audience"] == "customers" and path.suffix in (".md", ".txt", ".csv") and path.exists():
            yield row["path"], path.read_text(errors="ignore")
    for path in sorted((ROOT / "data" / "kb_text").glob("*")):  # the converted current documents (PDF, image, CSV)
        yield f"data/kb_text/{path.name}", path.read_text(errors="ignore")


def test_no_internal_only_term_appears_in_any_customer_facing_document():
    from eval.run_adversarial import INTERNAL_TERMS
    found = {name: sorted({m.group(0) for m in INTERNAL_TERMS.finditer(text)}) for name, text in _customer_documents()}
    assert not {name: terms for name, terms in found.items() if terms}


def test_customer_facing_wording_about_discretion_is_not_internal_text():
    from eval.run_adversarial import internal_text
    assert not internal_text("Checks accepted at the technician's discretion.")
