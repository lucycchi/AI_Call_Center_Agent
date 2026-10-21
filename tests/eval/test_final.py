"""The final held-out run (R23), tested on a fake project folder with fake runners: nothing here touches the real
held-out cases, the agent or Codex (D46)."""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import pytest

import eval.final as final
from eval.freeze import freeze_agent
from eval.scoring import Summary
from eval.split import freeze_hash

HELD = [f"H{i:02d}" for i in range(40)]


def fake_summary(**overrides) -> Summary:
    values = dict(containment=0.6, containment_without_redirects=0.55, scope_ceiling=0.9, adjusted_ceiling=0.8,
                  action_gap=0.1, wrong_confident=1, knowledge_accuracy=0.9, routing_accuracy=0.95,
                  handoff_correct_safety_and_booking=1.0, handoff_correct_other=0.8, booking_correct=0.9,
                  lookup_correct=1.0, clean_declines=2, flaky=[], interval_low=0.5, interval_high=0.7, scenarios=40,
                  weighted_calls=400)
    values.update(overrides)
    return Summary(**values)


@dataclass
class Attempt:
    case_id: str
    attempt: int
    all_correct: bool | None
    grades: dict = field(default_factory=dict)


class FakeRunner:
    """Stands in for eval.run.run_graded: records what it was asked to run and writes the run's summary.json."""

    def __init__(self, correct=lambda case_id, call: True):
        self.calls, self.correct = [], correct

    def __call__(self, cases, name, *, out):
        self.calls.append(([c["case_id"] for c in cases], out))
        out.mkdir(parents=True, exist_ok=True)
        (out / "attempts.jsonl").write_text("")
        summary = fake_summary(scenarios=len(cases))
        (out / "summary.json").write_text(json.dumps(summary.to_json()))
        call = len(self.calls)
        return [Attempt(c["case_id"], 1, self.correct(c["case_id"], call)) for c in cases], summary


SECTION_FILES = {
    "retrieval": ("data/results/retrieval/summary.json", {"coverage": 0.9, "combined": {"hit_at_5": 0.92},
                                                          "settings": {"top": 5}}),
    "answers": ("data/results/retrieval/answer_scores.json", {"combined": {"correct": 0.88}}),
    "adversarial": ("data/results/adversarial/summary.json", {"pass_rate": 1.0, "failures": []}),
    "grader_agreement": ("data/results/grader_check.json", {"agreement": 0.93, "graded": 30}),
    "label_agreement": ("data/label_agreement.json", {"codex_vs_haiku": 0.9, "fable_vs_codex": 0.88}),
}


def write(root: Path, rel: str, data) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


@pytest.fixture
def root(tmp_path):
    """A fake project: an agent file, a web file, 40 held-out cases, and the two freeze records."""
    write(tmp_path, "app/core/engine.py", "AGENT = 1\n")
    write(tmp_path, "app/web/main.py", "WEB = 1\n")
    cases = [write(tmp_path, f"data/testset/{cid}.json", {"case_id": cid, "calls_weight": 10}) for cid in HELD]
    write(tmp_path, "data/testset/W01.json", {"case_id": "W01", "calls_weight": 10})
    write(tmp_path, "data/split.json", {"working": ["W01"], "held_out": HELD, "held_out_hash": freeze_hash(cases)})
    write(tmp_path, "data/agent_freeze.json", {"hash": freeze_agent(tmp_path)})
    return tmp_path


def with_sections(root: Path) -> Path:
    for rel, data in SECTION_FILES.values():
        write(root, rel, data)
    return root


# -- The freeze checks ---------------------------------------------------------------------------------------------
def test_run_final_runs_every_held_out_case_into_the_final_folder(root):
    runner = FakeRunner()
    final.run_final(runner, root=with_sections(root), confirmed=True)
    ids, out = runner.calls[0]
    assert ids == HELD and out == root / "data" / "results" / "final"


def test_run_final_refuses_when_a_held_out_case_changed(root):
    write(root, "data/testset/H03.json", {"case_id": "H03", "calls_weight": 11})
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="held-out cases differ"):
        final.run_final(runner, root=root, confirmed=True)
    assert runner.calls == []


def test_run_final_refuses_when_the_agent_changed(root):
    write(root, "app/core/engine.py", "AGENT = 2\n")
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="freeze record"):
        final.run_final(runner, root=root, confirmed=True)
    assert runner.calls == []


def test_changes_to_the_web_code_do_not_stop_the_final_run(root):
    write(root, "app/web/main.py", "WEB = 2\n")
    runner = FakeRunner()
    final.run_final(runner, root=with_sections(root), confirmed=True)
    assert len(runner.calls) == 1


def test_run_final_needs_explicit_confirmation_before_touching_the_held_out_set(root):
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="confirm"):
        final.run_final(runner, root=with_sections(root), confirmed=False)
    assert runner.calls == []


def test_run_final_never_replaces_an_earlier_final_run(root):
    write(root, "data/results/final/attempts.jsonl", "")
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="already holds attempts"):
        final.run_final(runner, root=with_sections(root), confirmed=True)
    assert runner.calls == []


# -- The final summary ---------------------------------------------------------------------------------------------
def test_the_final_summary_has_every_summary_field_and_every_section(root):
    summary = final.run_final(FakeRunner(), root=with_sections(root), confirmed=True)
    saved = json.loads((root / "data" / "results" / "final" / "summary.json").read_text())
    assert saved == summary
    for f in fields(Summary):
        assert f.name in saved
    for section in final.SECTIONS:
        assert isinstance(saved[section], dict) and saved[section]
    assert saved["adversarial"]["pass_rate"] == 1.0 and saved["label_agreement"]["fable_vs_codex"] == 0.88
    assert "settings" not in saved["retrieval"]  # run settings stay out of the Results tab's sections
    assert saved["held_out_hash"] == json.loads((root / "data" / "split.json").read_text())["held_out_hash"]
    assert saved["agent_hash"] == json.loads((root / "data" / "agent_freeze.json").read_text())["hash"]


@pytest.mark.parametrize("missing", list(SECTION_FILES))
def test_the_summary_fails_validation_when_a_section_is_missing(root, missing):
    with_sections(root)
    (root / SECTION_FILES[missing][0]).unlink()
    with pytest.raises(final.IncompleteSummary, match=missing):
        final.run_final(FakeRunner(), root=root, confirmed=True)
    out = root / "data" / "results" / "final"
    assert not (out / "summary.json").exists()  # the Results tab keeps saying the final results are not yet run
    assert json.loads((out / "run_summary.json").read_text())["scenarios"] == len(HELD)  # the run itself is kept


def test_the_summary_can_be_finished_later_once_the_missing_section_exists(root):
    with_sections(root)
    (root / SECTION_FILES["grader_agreement"][0]).unlink()
    with pytest.raises(final.IncompleteSummary):
        final.run_final(FakeRunner(), root=root, confirmed=True)
    write(root, *SECTION_FILES["grader_agreement"])
    summary = final.finish_summary(root)
    assert summary["grader_agreement"]["agreement"] == 0.93
    assert (root / "data" / "results" / "final" / "summary.json").exists()


def test_validation_names_a_missing_summary_field():
    complete = {f.name: None for f in fields(Summary)} | {s: {"x": 1} for s in final.SECTIONS}
    final.validate(complete)
    del complete["routing_accuracy"]
    with pytest.raises(final.IncompleteSummary, match="routing_accuracy"):
        final.validate(complete)


# -- Consistency ---------------------------------------------------------------------------------------------------
def test_consistency_runs_30_held_out_cases_three_times_with_seed_3_and_reports_the_share_correct_on_all_three(root):
    flaky = set(HELD[:6])
    runner = FakeRunner(correct=lambda case_id, call: not (case_id in flaky and call == 3))
    result = final.run_consistency(runner, root=root, confirmed=True)
    asked = [ids for ids, _ in runner.calls]
    assert len(asked) == 3 and all(ids == asked[0] for ids in asked) and len(asked[0]) == 30
    assert set(asked[0]) <= set(HELD)
    assert asked[0] == final.consistency_cases(HELD)  # the same 30 each time it is asked: seed 3
    assert [out.name for _, out in runner.calls] == ["run1", "run2", "run3"]
    expected = sum(1 for cid in asked[0] if cid not in flaky) / 30
    assert result["cases"] == 30 and result["runs"] == 3 and result["seed"] == 3
    assert result["correct_all_three"] == pytest.approx(expected)
    saved = json.loads((root / "data" / "results" / "final" / "consistency" / "summary.json").read_text())
    assert saved == result


def test_consistency_has_the_same_freeze_checks(root):
    write(root, "app/core/engine.py", "AGENT = 2\n")
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="freeze record"):
        final.run_consistency(runner, root=root, confirmed=True)
    assert runner.calls == []


# -- Resuming a run whose grading crashed --------------------------------------------------------------------------
FINAL = Path("data/results/final")


class FakeResumer:
    """Stands in for eval.run.resume_graded: records what it was asked to resume and writes the run's summary.json."""

    def __init__(self, correct=lambda case_id: True):
        self.calls, self.correct = [], correct

    def __call__(self, cases, out):
        self.calls.append(([c["case_id"] for c in cases], out))
        summary = fake_summary(scenarios=len(cases))
        (out / "summary.json").write_text(json.dumps(summary.to_json()))
        return [Attempt(c["case_id"], 1, self.correct(c["case_id"])) for c in cases], summary


class Crashes(FakeRunner):
    """A run whose grading crashed: its attempts were saved and run_graded wrote a partial summary, then raised."""

    def __call__(self, cases, name, *, out):
        super().__call__(cases, name, out=out)
        (out / "ungraded-first.jsonl").write_text("{}\n")
        (out / "summary.json").write_text(json.dumps(fake_summary(extra={"failed": "UnboundLocalError: x",
                                                                         "partial": True}).to_json()))
        raise UnboundLocalError("x")


def crashed_final(root: Path) -> Path:
    with pytest.raises(UnboundLocalError):
        final.run_final(Crashes(), root=root, confirmed=True)
    return root / FINAL


def test_a_crashed_final_run_leaves_no_summary_the_results_tab_could_read(root):
    out = crashed_final(with_sections(root))
    assert not (out / "summary.json").exists()
    assert json.loads((out / "run_summary.json").read_text())["extra"]["partial"] is True


def test_resume_final_grades_the_saved_run_and_writes_the_validated_summary(root):
    out = crashed_final(with_sections(root))
    resumer = FakeResumer()
    summary = final.resume_final(resumer, root=root, confirmed=True)
    assert resumer.calls == [(HELD, out)]
    saved = json.loads((out / "summary.json").read_text())
    assert saved == summary and saved["adversarial"]["pass_rate"] == 1.0
    assert saved["agent_hash"] == json.loads((root / "data" / "agent_freeze.json").read_text())["hash"]
    run_summary = json.loads((out / "run_summary.json").read_text())
    assert run_summary["scenarios"] == len(HELD) and "partial" not in run_summary["extra"]


def test_resume_final_replaces_a_partial_summary_left_in_the_folder(root):
    out = crashed_final(with_sections(root))
    (out / "summary.json").write_text(json.dumps({"extra": {"partial": True}}))  # as an older run_graded left it
    final.resume_final(FakeResumer(), root=root, confirmed=True)
    final.validate(json.loads((out / "summary.json").read_text()))


@pytest.mark.parametrize("change", ["agent", "held_out"])
def test_resume_final_refuses_when_a_hash_does_not_match(root, change):
    crashed_final(with_sections(root))
    if change == "agent":
        write(root, "app/core/engine.py", "AGENT = 2\n")
    else:
        write(root, "data/testset/H03.json", {"case_id": "H03", "calls_weight": 11})
    resumer = FakeResumer()
    with pytest.raises(SystemExit, match="freeze record" if change == "agent" else "held-out cases differ"):
        final.resume_final(resumer, root=root, confirmed=True)
    assert resumer.calls == []


def test_resume_final_needs_confirmation_and_a_saved_run(root):
    resumer = FakeResumer()
    with pytest.raises(SystemExit, match="nothing to resume"):
        final.resume_final(resumer, root=with_sections(root), confirmed=True)
    crashed_final(root)
    with pytest.raises(SystemExit, match="confirm"):
        final.resume_final(resumer, root=root, confirmed=False)
    assert resumer.calls == []


def test_resume_final_refuses_a_finished_final_run(root):
    final.run_final(FakeRunner(), root=with_sections(root), confirmed=True)
    resumer = FakeResumer()
    with pytest.raises(SystemExit, match="already finished"):
        final.resume_final(resumer, root=root, confirmed=True)
    assert resumer.calls == []


def test_the_run_command_still_refuses_after_a_crashed_final_run(root):
    crashed_final(with_sections(root))
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="already holds attempts"):
        final.run_final(runner, root=root, confirmed=True)
    assert runner.calls == []


def crashed_consistency(root: Path, crash_on: int) -> Path:
    """Consistency runs that crashed while grading run crash_on (its conversations saved)."""
    class CrashesOn(FakeRunner):
        def __call__(self, cases, name, *, out):
            attempts, summary = super().__call__(cases, name, out=out)
            (out / "attempts.jsonl").write_text("".join(json.dumps({"case_id": a.case_id, "attempt": 1,
                                                                    "all_correct": a.all_correct}) + "\n" for a in attempts))
            if len(self.calls) == crash_on:
                (out / "summary.json").write_text(json.dumps(fake_summary(extra={"failed": "x", "partial": True}).to_json()))
                raise UnboundLocalError("x")
            return attempts, summary
    flaky = set(HELD[:6])
    with pytest.raises(UnboundLocalError):
        final.run_consistency(CrashesOn(correct=lambda cid, call: cid not in flaky), root=root, confirmed=True)
    return root / FINAL / "consistency"


def test_consistency_resume_grades_run1_then_runs_runs_2_and_3(root):
    folder = crashed_consistency(root, crash_on=1)
    runner, resumer = FakeRunner(), FakeResumer()
    result = final.resume_consistency(runner, resumer, root=root, confirmed=True)
    chosen = final.consistency_cases(HELD)
    assert resumer.calls == [(chosen, folder / "run1")]
    assert [(ids, out.name) for ids, out in runner.calls] == [(chosen, "run2"), (chosen, "run3")]
    assert result["correct_all_three"] == 1.0
    assert json.loads((folder / "summary.json").read_text()) == result


def test_consistency_resume_reads_finished_runs_and_resumes_the_one_that_crashed(root):
    folder = crashed_consistency(root, crash_on=2)
    runner, resumer = FakeRunner(), FakeResumer()
    result = final.resume_consistency(runner, resumer, root=root, confirmed=True)
    assert [out.name for _, out in resumer.calls] == ["run2"] and [out.name for _, out in runner.calls] == ["run3"]
    chosen = final.consistency_cases(HELD)
    expected = sum(1 for cid in chosen if cid not in set(HELD[:6])) / 30  # run1's saved firsts are counted
    assert result["correct_all_three"] == pytest.approx(expected)
    assert json.loads((folder / "summary.json").read_text()) == result


def test_consistency_resume_has_the_same_freeze_checks_and_needs_a_saved_run(root):
    runner, resumer = FakeRunner(), FakeResumer()
    with pytest.raises(SystemExit, match="nothing to resume"):
        final.resume_consistency(runner, resumer, root=root, confirmed=True)
    crashed_consistency(root, crash_on=1)
    write(root, "app/core/engine.py", "AGENT = 2\n")
    with pytest.raises(SystemExit, match="freeze record"):
        final.resume_consistency(runner, resumer, root=root, confirmed=True)
    assert runner.calls == [] and resumer.calls == []


def test_resume_final_refuses_a_run_that_finished_but_lacks_a_section(root):
    with_sections(root)
    (root / SECTION_FILES["adversarial"][0]).unlink()
    with pytest.raises(final.IncompleteSummary):
        final.run_final(FakeRunner(), root=root, confirmed=True)
    resumer = FakeResumer()
    with pytest.raises(SystemExit, match="already finished"):
        final.resume_final(resumer, root=root, confirmed=True)
    assert resumer.calls == []
