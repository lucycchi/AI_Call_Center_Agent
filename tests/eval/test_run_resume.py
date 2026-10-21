"""Resuming the grading of a run whose conversations were saved but whose grading crashed: the saved first attempts
are graded, never run again; each failed case gets its one retry; the summary is written as a full run writes it.

Everything is fake (agent, caller, Codex, database checks); nothing reaches a model, Codex or the held-out set."""

import json
from collections import Counter

import pytest

import eval.grade_conversations as grading
from tests.eval.test_grader import FakeRunner
from tests.eval.test_run_safety import SETTINGS, Caller, _cases, _lines
from tests.eval.test_scoring import Recorder


class CountingCaller(Caller):
    """Counts each conversation the simulator starts, per case and attempt (the first line of each conversation)."""

    def __init__(self, started):
        super().__init__()
        self.started = started

    def next(self, case, conversation, timeout=None):
        if not conversation:
            self.started[case["case_id"]] += 1
        return super().next(case, conversation, timeout)


def _crash_in_grading(monkeypatch, on="c2"):
    """The final run's crash: database_checks raised part way through the first grading batch, after it had already
    written its checks into the earlier attempts' grades."""
    real = grading.database_checks

    def crashing(case, attempt):
        if case["case_id"] == on:
            raise UnboundLocalError("cannot access local variable 'missed_only'")
        return real(case, attempt)
    monkeypatch.setattr(grading, "database_checks", crashing)
    return real


def _first_run_that_crashes(tmp_path, monkeypatch, started, engine):
    from eval.run import run_graded
    real = _crash_in_grading(monkeypatch)
    with pytest.raises(UnboundLocalError):
        run_graded(_cases(), "t", out=tmp_path, factory=engine, simulator_factory=lambda: CountingCaller(started),
                   runner=FakeRunner(), model="gpt-5.6-sol", settings=SETTINGS)
    monkeypatch.setattr(grading, "database_checks", real)


def _resume(tmp_path, started, engine, runner, cases=None):
    from eval.run import resume_graded
    return resume_graded(cases or _cases(), tmp_path, factory=engine, simulator_factory=lambda: CountingCaller(started),
                         runner=runner, model="gpt-5.6-sol")


def _fails(*ids):
    return lambda i: {"correct": i not in ids}


def test_resume_grades_the_saved_first_attempts_and_retries_only_failed_cases_once(tmp_path, monkeypatch):
    started, engine = Counter(), Recorder()
    _first_run_that_crashes(tmp_path, monkeypatch, started, engine)
    assert started == Counter({"c0": 1, "c1": 1, "c2": 1, "c3": 1}) and len(engine.paths) == 4
    saved = {a["case_id"]: a for a in _lines(tmp_path / "ungraded-first.jsonl")}
    assert json.loads((tmp_path / "summary.json").read_text())["extra"]["failed"].startswith("UnboundLocalError")

    runner = FakeRunner(_fails("c1|1", "c3|1"))
    attempts, summary = _resume(tmp_path, started, engine, runner)

    # no first attempt ran again; c1 and c3 got exactly one retry each
    assert started == Counter({"c0": 1, "c1": 2, "c2": 1, "c3": 2})
    assert [p.name for p in engine.paths[4:]] == ["c1-2.sqlite", "c3-2.sqlite"]
    firsts = {a.case_id: a for a in attempts if a.attempt == 1}
    for cid, a in firsts.items():  # the saved conversations come back exactly as they were saved
        for key in ("db_path", "conversation", "done_events", "tickets", "stopped", "models", "cost_usd",
                    "conversation_id", "seconds", "first_route", "handed_off"):
            assert getattr(a, key) == saved[cid][key], (cid, key)
    assert {cid: a.all_correct for cid, a in firsts.items()} == {"c0": True, "c1": False, "c2": True, "c3": False}

    lines = _lines(tmp_path / "attempts.jsonl")
    assert sorted((a["case_id"], a["attempt"]) for a in lines) == \
        [("c0", 1), ("c1", 1), ("c1", 2), ("c2", 1), ("c3", 1), ("c3", 2)]
    assert all(a["graded"] and a["settings"] == SETTINGS for a in lines)
    verdicts = [v["id"] for v in _lines(tmp_path / "verdicts.jsonl")]
    assert sorted(verdicts) == ["c0|1", "c1|1", "c1|2", "c2|1", "c3|1", "c3|2"]
    written = json.loads((tmp_path / "summary.json").read_text())
    assert written == summary.to_json() and "failed" not in written["extra"] and written["extra"]["ungraded"] == []
    assert written["extra"]["settings"] == SETTINGS and written["extra"]["resumed"] is True
    assert written["extra"]["spent_usd"] == pytest.approx(sum(a.cost_usd for a in attempts), abs=1e-4)
    assert sum(a.cost_usd for a in attempts) > 0


def test_resume_refuses_when_a_case_has_no_saved_first_attempt(tmp_path, monkeypatch):
    started, engine = Counter(), Recorder()
    _first_run_that_crashes(tmp_path, monkeypatch, started, engine)
    before = (tmp_path / "attempts.jsonl").read_text()
    runner = FakeRunner()
    more = _cases(5)
    with pytest.raises(SystemExit, match="no saved first attempt.*c4"):
        _resume(tmp_path, started, engine, runner, cases=more)
    assert runner.prompts == [] and sum(started.values()) == 4 and len(engine.paths) == 4
    assert (tmp_path / "attempts.jsonl").read_text() == before


def test_resume_refuses_an_empty_folder(tmp_path):
    with pytest.raises(SystemExit, match="no saved first attempt"):
        _resume(tmp_path, Counter(), Recorder(), FakeRunner())


def test_resume_refuses_a_case_saved_twice_or_already_graded_twice(tmp_path, monkeypatch):
    started, engine = Counter(), Recorder()
    _first_run_that_crashes(tmp_path, monkeypatch, started, engine)
    path = tmp_path / "ungraded-first.jsonl"
    original = path.read_text()
    path.write_text(original + original.splitlines()[0] + "\n")
    runner = FakeRunner()
    with pytest.raises(SystemExit, match="saved more than once.*c0"):
        _resume(tmp_path, started, engine, runner)
    path.write_text(original)
    (tmp_path / "verdicts.jsonl").write_text(json.dumps({"id": "c1|1"}) + "\n" + json.dumps({"id": "c1|1"}) + "\n")
    with pytest.raises(SystemExit, match="graded twice.*c1\\|1"):
        _resume(tmp_path, started, engine, runner)
    assert runner.prompts == [] and sum(started.values()) == 4


def test_resume_keeps_grades_already_given_and_does_not_grade_them_again(tmp_path):
    """Codex failed during the retries: the first attempts were graded and the retries ran; resume grades only the
    retries, and runs nothing."""
    from eval.run import run_graded
    from tests.eval.test_run_safety import FailsOnRetries
    started, engine = Counter(), Recorder()
    with pytest.raises(RuntimeError, match="Codex is down"):
        run_graded(_cases(), "t", out=tmp_path, factory=engine, simulator_factory=lambda: CountingCaller(started),
                   runner=FailsOnRetries(), model="gpt-5.6-sol", settings=SETTINGS)
    assert sum(started.values()) == 8
    runner = FakeRunner()
    attempts, summary = _resume(tmp_path, started, engine, runner)
    assert sum(started.values()) == 8 and len(engine.paths) == 8
    graded_ids = [i["id"] for p in runner.prompts for i in json.loads(p[p.index("ITEMS:") + 6:])]
    assert sorted(graded_ids) == [f"c{k}|2" for k in range(4)]
    assert all(a.all_correct is (a.attempt == 2) for a in attempts)
    assert len(_lines(tmp_path / "verdicts.jsonl")) == 8 and all(a["graded"] for a in _lines(tmp_path / "attempts.jsonl"))


def test_a_normal_run_still_refuses_a_folder_holding_saved_attempts(tmp_path, monkeypatch):
    from eval.run import run_graded
    started, engine = Counter(), Recorder()
    _first_run_that_crashes(tmp_path, monkeypatch, started, engine)
    with pytest.raises(SystemExit, match="already holds attempts"):
        run_graded(_cases(), "t", out=tmp_path, factory=engine, simulator_factory=lambda: CountingCaller(started),
                   runner=FakeRunner(), model="gpt-5.6-sol", settings=SETTINGS)
    assert sum(started.values()) == 4
