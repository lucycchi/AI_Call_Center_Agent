"""Grader batches are saved as they finish, and the API fallback grader keeps the conversation run's own cap.

Every run here is fully stubbed: the agent, the simulated caller, the grading runner, the grader model and the
settings are passed in, so nothing reaches a model, Codex or the held-out set."""

import json

import pytest

from eval.grader import grade
from tests.eval.test_grader import FakeRunner, item


class FailsOnSecondBatch(FakeRunner):
    def __call__(self, prompt):
        if self.prompts:
            self.prompts.append(prompt)
            raise RuntimeError("Codex fell over on batch two")
        return super().__call__(prompt)


def test_each_batch_is_handed_over_as_it_finishes_so_a_later_failure_keeps_it():
    kept = []
    with pytest.raises(RuntimeError, match="batch two"):
        grade([item(n) for n in range(25)], FailsOnSecondBatch(), model="m", on_batch=kept.append)
    assert [len(batch) for batch in kept] == [20]
    assert [v.id for v in kept[0]] == [f"i{n}" for n in range(20)] and all(v.model == "m" for v in kept[0])


def _run(tmp_path, runner, n=25, **kwargs):
    from eval.run import run_graded
    from tests.eval.test_run_safety import Caller, SETTINGS, _cases
    from tests.eval.test_scoring import Recorder
    return run_graded(_cases(n), "t", out=tmp_path, factory=Recorder(), simulator_factory=lambda: Caller(),
                      runner=runner, model="gpt-5.6-sol", settings=SETTINGS, **kwargs)


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_grader_failure_in_batch_two_keeps_batch_ones_verdicts_and_grades(tmp_path):
    with pytest.raises(RuntimeError, match="batch two"):
        _run(tmp_path, FailsOnSecondBatch())
    verdicts = _lines(tmp_path / "verdicts.jsonl")
    assert [v["id"] for v in verdicts] == [f"c{k}|1" for k in range(20)]
    saved = _lines(tmp_path / "attempts.jsonl")
    assert len(saved) == 25
    graded = [a for a in saved if a["graded"]]
    assert [a["case_id"] for a in graded] == [f"c{k}" for k in range(20)]
    assert all(a["all_correct"] is True and a["grades"]["grader_model"] == "gpt-5.6-sol" for a in graded)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["extra"]["ungraded"] == [f"c{k}|1" for k in range(20, 25)]


# -- the API fallback grader ----------------------------------------------------------------------------------

class FakeOpenAI:
    """Reports usage at the most the call could have cost: its input estimate and every output token allowed."""

    def __init__(self):
        self.responses, self.calls, self.kwargs = self, 0, []

    def create(self, **kwargs):
        from eval.grader import input_token_estimate
        self.calls += 1
        self.kwargs.append(kwargs)
        usage = type("Usage", (), {"input_tokens": input_token_estimate(kwargs["input"]),
                                   "output_tokens": kwargs["max_output_tokens"]})()
        return type("Response", (), {"output_text": "[]", "usage": usage})()


def test_the_api_grader_refuses_a_call_that_could_cross_the_cap(monkeypatch):
    from eval.budget import BudgetExceeded, RunBudget
    from eval.grader import api_runner
    monkeypatch.setenv("GRADER_MODEL", "some-model")
    monkeypatch.setenv("GRADER_PRICES_PER_MILLION", "3,10")
    monkeypatch.setenv("GRADER_MAX_OUTPUT_TOKENS", "100000")  # $1 of output at most per call
    budget, client = RunBudget(8.0), FakeOpenAI()
    calls = 0
    with pytest.raises(BudgetExceeded):
        for _ in range(20):
            api_runner("P" * 30_000, budget=budget, client=client)
            calls += 1
    assert client.calls == calls and calls >= 6
    assert budget.spent_usd <= budget.cap_usd  # never overshoots
    assert all(k["max_output_tokens"] == 100_000 for k in client.kwargs)
    nearly = RunBudget(8.0)
    nearly.spent_usd = 7.5
    with pytest.raises(BudgetExceeded):
        api_runner("P", budget=nearly, client=client)  # $1 of output could cross the cap, so it is not made
    assert client.calls == calls


def test_the_api_grader_uses_the_budget_runner_for_is_given(monkeypatch):
    import eval.grader as grader
    from eval.budget import RunBudget
    seen = []
    monkeypatch.setattr(grader, "api_runner", lambda prompt, budget=None, client=None: seen.append(budget) or "[]")
    monkeypatch.setenv("GRADER_BACKEND", "api")
    budget = RunBudget(8.0)
    runner = grader.runner_for(budget)
    assert runner.__name__ == "api_runner" and runner("PROMPT") == "[]" and seen == [budget]


def test_the_conversation_run_gives_the_grader_its_own_budget(tmp_path, monkeypatch):
    import eval.grader as grader
    given = []

    def fake_runner_for(budget=None):
        given.append(budget)
        return FakeRunner()
    monkeypatch.setattr(grader, "runner_for", fake_runner_for)
    _run(tmp_path, None, n=2)
    [budget] = given
    assert budget is not None and budget.spent_usd > 0  # the budget the conversations were charged to
