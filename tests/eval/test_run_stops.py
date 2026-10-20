"""How a test conversation stops: at the time or turn limit (which fails the quick run), on a call that timed out at
the 60-second cap, and at the budget (which ends the attempt rather than becoming a handoff inside the agent).

Every agent, caller, model client and grader here is a stand-in; nothing reaches a model, Codex or the held-out set."""

import json

import httpx
import pytest

from app.core.model_log import SINK
from app.core.types import DoneEvent, SentenceEvent
from eval.budget import RunBudget
from eval.harness import Attempt, run_case
from tests.eval.test_scoring import Recorder, ScriptedCaller, case


# -- the quick run ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("stop", ["time limit", "turn limit"])
def test_an_attempt_stopped_at_the_time_or_turn_limit_fails_the_quick_run_outright(stop):
    from eval.quick_run import judge
    cases = {c: {"case_id": c, "sub_reason": "hvac repair", "needs_documents": False, "calls_weight": 1} for c in ("a", "b")}
    result = judge([Attempt("a", all_correct=True), Attempt("b", all_correct=True, stopped=stop)], cases)
    assert not result.passed and result.hard and any(stop in r for r in result.reasons)


# -- a call that times out at the cap -------------------------------------------------------------------------

def _timeout():
    import anthropic
    return anthropic.APITimeoutError(request=httpx.Request("POST", "https://example.invalid/v1/messages"))


def test_a_simulator_call_that_times_out_at_the_cap_is_a_time_limit_stop(tmp_path):
    now = [0.0]

    class TimesOut(ScriptedCaller):
        def next(self, case, conversation, timeout=None):
            if conversation:
                now[0] += timeout  # the call ran out the time it was given, which was the time left
                raise _timeout()
            now[0] += 10
            return "hello"
    result = run_case(case("t", 1), Recorder(), TimesOut([]), RunBudget(8.0), tmp_path, clock=lambda: now[0])
    assert result.stopped == "time limit" and result.error is None


def test_an_agent_call_that_times_out_at_the_cap_is_a_time_limit_stop(tmp_path):
    now = [0.0]

    class Slow:
        def handle(self, turn):
            now[0] = 60.0
            raise _timeout()
            yield
    result = run_case(case("t", 1), lambda db, ops: Slow(), ScriptedCaller(["hi"]), RunBudget(8.0), tmp_path,
                      clock=lambda: now[0])
    assert result.stopped == "time limit"


def test_a_timeout_well_inside_the_cap_is_still_an_error(tmp_path):
    now = [0.0]

    class Early(ScriptedCaller):
        def next(self, case, conversation, timeout=None):
            now[0] += 5
            raise _timeout()
    result = run_case(case("t", 1), Recorder(), Early([]), RunBudget(8.0), tmp_path, clock=lambda: now[0])
    assert result.stopped == "error" and "Timeout" in result.error


class FakeAnthropic:
    """Records the retry setting each call is made with; with_options returns a copy, as the SDK's does."""
    made = []

    def __init__(self, max_retries=2, timeout=None, api_key=None, calls=None):
        self.max_retries, self.calls = max_retries, calls if calls is not None else []
        self.messages = self
        FakeAnthropic.made.append({"max_retries": max_retries, "timeout": timeout})

    def with_options(self, max_retries=None, **kwargs):
        return FakeAnthropic(self.max_retries if max_retries is None else max_retries, calls=self.calls)

    def create(self, **kwargs):
        self.calls.append(("create", self.max_retries, kwargs.get("timeout")))
        return type("Response", (), {"usage": None, "content": []})()

    def stream(self, **kwargs):
        self.calls.append(("stream", self.max_retries, kwargs.get("timeout")))
        return "stream"


def test_calls_given_the_time_left_are_made_without_sdk_retries():
    from eval.run import NoRetriesWithinCap
    inner = FakeAnthropic(max_retries=1)
    client = NoRetriesWithinCap(inner)
    client.messages.create(model="m", timeout=12.0)
    client.messages.stream(model="m", timeout=3.0)
    client.messages.create(model="m")  # no time limit given: the pinned retry setting applies
    assert inner.calls == [("create", 0, 12.0), ("stream", 0, 3.0), ("create", 1, None)]


def test_the_test_run_client_makes_capped_calls_without_retries(monkeypatch):
    import anthropic

    import eval.run as run
    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-different-fake-key")
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    client = run.build_client(simulator=True)
    client.messages.create(purpose="simulate", model="m", timeout=30.0)
    assert isinstance(client.messages._client, run.NoRetriesWithinCap)
    assert client.messages._client._client.calls[-1] == ("create", 0, 30.0)


def test_the_agents_client_keeps_its_retries_as_in_production(monkeypatch):
    # Each agent attempt already gets half the time left in its message deadline, so a retry fits inside the cap;
    # dropping retries made slow calls fail where production would retry (quick run, run 3).
    import anthropic

    import eval.run as run
    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-different-fake-key")
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    client = run.build_client()
    client.messages.create(purpose="route", model="m", timeout=7.0)
    assert not isinstance(client.messages._client, run.NoRetriesWithinCap)
    assert client.messages._client.calls[-1] == ("create", 1, 7.0)


# -- the budget crossed in the middle of a turn ---------------------------------------------------------------

class PipelineLike:
    """Like the agent pipeline: any exception inside a turn becomes a handoff reply rather than escaping."""

    def __init__(self, microdollars):
        self.microdollars = microdollars

    def handle(self, turn):
        try:
            SINK.get()("write", "claude-sonnet-5-5", "sdk", {}, 1, 1, 1, self.microdollars)
            yield SentenceEvent("Your visit is booked.")
            yield DoneEvent(route="scheduling", ticket=None, outcome="answered")
        except Exception:
            yield SentenceEvent("I've passed this to our team.")
            yield DoneEvent(route="none", ticket=None, outcome="error")


def test_crossing_the_budget_records_a_flag_instead_of_raising_inside_the_agent():
    from eval.budget import BudgetExceeded
    budget = RunBudget(1.0)
    budget.record("write", "m", "sdk", {}, 1, 1, 1, 1_500_000)
    assert budget.crossed
    with pytest.raises(BudgetExceeded):
        budget.check()


def test_crossing_the_budget_mid_turn_stops_the_attempt_instead_of_handing_off(tmp_path):
    budget = RunBudget(1.0)
    result = run_case(case("t", 1), lambda db, ops: PipelineLike(1_500_000), ScriptedCaller(["hi", "more"]), budget,
                      tmp_path)
    assert result.stopped == "budget" and result.handed_off is False
    assert sum(m["role"] == "caller" for m in result.conversation) == 1  # no further turn after the crossing


def test_a_budget_stopped_attempt_is_not_graded_or_scored(tmp_path):
    from eval.run import run_graded
    from tests.eval.test_grader import FakeRunner
    from tests.eval.test_run_safety import SETTINGS, _cases
    runner = FakeRunner()
    attempts, summary = run_graded(_cases(3), "t", cap_usd=1.0, out=tmp_path,
                                   factory=lambda db, ops: PipelineLike(400_000),
                                   simulator_factory=lambda: ScriptedCaller(["hi"]), runner=runner,
                                   model="gpt-5.6-sol", settings=SETTINGS)
    stopped = [a for a in attempts if a.stopped == "budget"]
    assert [a.case_id for a in stopped] == ["c2"]
    prompts = " ".join(runner.prompts)
    assert "c0|1" in prompts and "c2|1" not in prompts
    assert stopped[0].all_correct is None and summary.stopped_at_budget and summary.scenarios == 2
    assert [a["case_id"] for a in map(json.loads, (tmp_path / "attempts.jsonl").read_text().splitlines())] == ["c0", "c1", "c2"]


def test_the_adversarial_runner_does_not_score_a_case_that_crossed_the_budget(tmp_path):
    from eval.run_adversarial import run_adversarial
    budget = RunBudget(1.0)
    budget.spent_usd = 0.9
    result = run_adversarial(lambda db, ops: PipelineLike(200_000), tmp_path, budget=budget)
    assert result.stopped_at_budget and result.cases == []
