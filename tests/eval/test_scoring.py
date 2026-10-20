import os
import sqlite3
from pathlib import Path

import pytest

from eval.budget import BudgetExceeded, RunBudget, require_eval_key
from eval.harness import Attempt, run_all, run_case
from eval.scoring import expected_route, score

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"


def case(case_id, weight, sub="hvac repair", reason="new booking", outcome="contained", needs_documents=False, why=None):
    return {"case_id": case_id, "calls_weight": weight, "reason": reason, "sub_reason": sub, "expected_outcome": outcome,
            "expected_handoff_reason": why, "needs_documents": needs_documents, "fixtures": [], "caller_script": ["hi"],
            "requests": [{"request": sub, "kind": "sub-reason", "expected_outcome": outcome, "handoff_reason": why}],
            "caller_card": {"customer_id": "MHC-10001"}}


def attempt(case_id, n=1, handed_off=False, correct=True, decline=False, route="scheduling", **grades):
    return Attempt(case_id=case_id, attempt=n, handed_off=handed_off, clean_decline=decline, all_correct=correct,
                   first_route=route, grades=grades)


def test_containment_is_weighted_by_real_calls():
    summary = score([attempt("a"), attempt("b", handed_off=True)], [case("a", 10), case("b", 30)])
    assert summary.containment == 0.25 and summary.weighted_calls == 40 and summary.scenarios == 2


def test_wrong_confident_clean_decline_flaky_and_redirects():
    cases = [case("w", 10), case("d", 10, sub="plumbing", outcome="clean_decline"), case("f", 10),
             case("r", 10, sub="wrong number", reason="wrong number", outcome="redirect")]
    attempts = [attempt("w", correct=False), attempt("d", decline=True, handed_off=True), attempt("f", correct=False),
                attempt("f", n=2), attempt("r", route="redirect")]
    summary = score(attempts, cases)
    assert summary.wrong_confident == 2 and summary.wrong_confident_cases == ["f", "w"]  # finished without a handoff, wrong
    assert summary.wrong_confident_share == 0.5
    assert summary.containment == 0.25  # only the redirect: the clean decline is correct but not contained
    assert summary.clean_declines == 1 and summary.flaky == ["f"]
    assert summary.containment_without_redirects == 0.0


def test_routing_accuracy_compares_the_first_route_with_the_template_label():
    cases = [case("b", 1), case("k", 1, sub="what it includes or price", reason="membership"),
             case("h", 1, sub="hiring", reason="hiring", outcome="redirect")]
    attempts = [attempt("b", route="scheduling"), attempt("k", route="account"), attempt("h", route="redirect")]
    assert round(score(attempts, cases).routing_accuracy, 3) == 0.667
    assert expected_route(case("k", 1, sub="what it includes or price", reason="membership")) == {"knowledge"}


def test_the_interval_resamples_scenarios_with_a_fixed_seed():
    cases, attempts = [case("a", 1), case("b", 3)], [attempt("a"), attempt("b", handed_off=True)]
    first = score(attempts, cases, seed=7, resamples=2000)
    assert (first.interval_low, first.interval_high) == (0.0, 1.0) and first.containment == 0.25
    again = score(attempts, cases, seed=7, resamples=2000)
    assert (again.interval_low, again.interval_high) == (first.interval_low, first.interval_high)


class ScriptedCaller:
    def __init__(self, lines):
        self.lines = list(lines)

    def next(self, case, conversation, timeout=None):
        return self.lines.pop(0) if self.lines else None


class Recorder:
    def __init__(self):
        self.paths = []

    def __call__(self, db_path, ops_path):
        self.paths.append(db_path)
        from app.core.types import DoneEvent, SentenceEvent

        class Engine:
            def handle(self, turn):
                yield SentenceEvent("ok")
                yield DoneEvent(route="knowledge", ticket=None)
        return Engine()


def test_each_case_runs_on_its_own_fresh_copy_and_the_seed_is_untouched(tmp_path):
    before = SEED.stat().st_mtime
    planted = case("p", 1)
    planted["fixtures"] = [{"table": "invoices", "row": {"invoice_id": "INV-999777", "customer_id": "MHC-10001",
                                                         "appointment_id": None, "issued_date": "2026-10-01",
                                                         "due_date": "2026-10-31", "amount_cents": 100, "balance_cents": 100,
                                                         "line_items": "[]"}}]
    factory = Recorder()
    budget = RunBudget(8.0)
    run_case(planted, factory, ScriptedCaller(["hello"]), budget, folder=tmp_path / "a")
    run_case(case("q", 1), factory, ScriptedCaller(["hello"]), budget, folder=tmp_path / "b")
    assert factory.paths[0] != factory.paths[1] and SEED.stat().st_mtime == before
    assert sqlite3.connect(factory.paths[0]).execute("select count(*) from invoices where invoice_id='INV-999777'").fetchone()[0] == 1
    assert sqlite3.connect(factory.paths[1]).execute("select count(*) from invoices where invoice_id='INV-999777'").fetchone()[0] == 0


def test_a_conversation_stops_at_12_caller_turns(tmp_path):
    result = run_case(case("t", 1), Recorder(), ScriptedCaller(["again"] * 50), RunBudget(8.0), folder=tmp_path)
    assert sum(m["role"] == "caller" for m in result.conversation) == 12 and result.stopped == "turn limit"


def test_a_conversation_stops_at_60_seconds(tmp_path):
    times = iter(range(0, 1000, 25))
    result = run_case(case("s", 1), Recorder(), ScriptedCaller(["again"] * 50), RunBudget(8.0), folder=tmp_path,
                      clock=lambda: next(times))
    assert result.stopped == "time limit" and sum(m["role"] == "caller" for m in result.conversation) < 12


def test_the_run_stops_at_the_budget_and_writes_a_partial_summary(tmp_path):
    budget = RunBudget(8.0)

    class CostlyCaller(ScriptedCaller):
        def next(self, case, conversation, timeout=None):
            budget.add(3.0)
            return super().next(case, conversation)
    cases = [case(f"c{n}", 1) for n in range(5)]
    summary = run_all(cases, Recorder(), lambda: CostlyCaller(["hello"]), budget, grade=lambda a, c: a, out=tmp_path)
    assert summary.stopped_at_budget is True and summary.scenarios < 5
    assert (tmp_path / "summary.json").exists() and (tmp_path / "attempts.jsonl").exists()


def test_a_failed_case_is_run_once_more_and_a_pass_on_the_retry_is_flaky(tmp_path):
    grades = iter([False, True])

    def grade(a, c):
        a.all_correct = next(grades)
        return a
    summary = run_all([case("x", 1)], Recorder(), lambda: ScriptedCaller(["hello"]), RunBudget(8.0), grade=grade, out=tmp_path)
    assert summary.flaky == ["x"] and summary.containment == 0.0


def test_the_harness_refuses_to_run_without_a_separate_test_key(monkeypatch):
    monkeypatch.delenv("EVAL_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        require_eval_key()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "same")
    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "same")
    with pytest.raises(RuntimeError):
        require_eval_key()
    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "different")
    assert require_eval_key() == "different"


def test_the_budget_raises_once_spend_reaches_the_cap():
    budget = RunBudget(8.0)
    budget.add(7.5)
    budget.check()
    with pytest.raises(BudgetExceeded):
        budget.add(0.6)  # the spend that crosses the cap stops the run at once
    assert budget.spent_usd == 8.1
    with pytest.raises(BudgetExceeded):
        budget.check()
    recorded = RunBudget(1.0)
    recorded.record("write", "claude-sonnet-5-5", "anthropic", {}, 10, 10, 5, 900_000)
    assert not recorded.crossed
    # a model call inside the agent never raises (that would become a handoff reply); it marks the budget crossed,
    # and the harness stops the attempt after the turn
    recorded.record("write", "claude-sonnet-5-5", "anthropic", {}, 10, 10, 5, 200_000)
    assert recorded.crossed
    with pytest.raises(BudgetExceeded):
        recorded.check()


class FakeSonnet:
    def __init__(self, replies):
        self.replies, self.calls, self.messages = list(replies), [], self

    def create(self, purpose="route", **kwargs):
        self.calls.append({"purpose": purpose, **kwargs})
        block = type("Block", (), {"type": "text", "text": self.replies.pop(0)})()
        return type("Response", (), {"content": [block], "stop_reason": "end_turn"})()


def test_the_simulated_caller_plays_the_card_and_the_script_and_says_when_it_is_done():
    from eval.simulator import Simulator
    client = FakeSonnet(["Hi, my AC is blowing warm.", "[DONE]"])
    simulated = case("s", 1)
    simulated["caller_card"] = {"customer_id": "MHC-10001", "name": "Linda Foster", "phone": "512-555-0101",
                                "service_address": "4412 Oak Hollow Dr", "city": "Round Rock"}
    simulated["caller_script"] = ["My AC is blowing warm.", "Yeah, it's MHC-10001."]
    simulator = Simulator(client)
    assert simulator.next(simulated, []) == "Hi, my AC is blowing warm."
    assert simulator.next(simulated, [{"role": "caller", "text": "Hi"}, {"role": "agent", "text": "Booked."}]) is None
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["max_tokens"] == 300 and call["purpose"] == "simulate"
    for part in ("Linda Foster", "MHC-10001", "512-555-0101", "4412 Oak Hollow Dr", "My AC is blowing warm.", "Friday",
                 "16 October 2026"):
        assert part in call["system"], part


def test_the_provisional_grade_compares_only_outcomes():
    from eval.run import provisional_grade
    assert provisional_grade(attempt("a", handed_off=True), case("a", 1, outcome="handed_off")).all_correct is True
    assert provisional_grade(attempt("a"), case("a", 1, outcome="handed_off")).all_correct is False
    graded = provisional_grade(attempt("a", decline=True), case("a", 1, outcome="clean_decline"))
    assert graded.all_correct is True and graded.grades["provisional"] is True


def _perfect(c):
    expected = c["expected_outcome"]
    return Attempt(c["case_id"], handed_off=expected == "handed_off", clean_decline=expected == "clean_decline",
                   all_correct=True, first_route="redirect" if expected == "redirect" else "scheduling",
                   grades={"handoff_reason_correct": True})


def test_a_perfect_agent_never_exceeds_either_ceiling():
    import json
    cases = [json.loads(p.read_text()) for p in sorted((ROOT / "data" / "testset").glob("*.json"))]
    summary = score([_perfect(c) for c in cases], cases)
    assert summary.containment == summary.adjusted_ceiling <= summary.scope_ceiling
    assert summary.containment_without_redirects == summary.adjusted_ceiling_without_redirects
    assert summary.adjusted_ceiling_without_redirects <= summary.scope_ceiling_without_redirects


def test_redirects_count_in_both_ceilings_and_action_gaps_only_leave_the_adjusted_one():
    cases = [case("r", 10, sub="wrong number", reason="wrong number", outcome="redirect"),
             case("g", 10, sub="autopay", reason="billing", outcome="handed_off", why="action gap"), case("c", 20)]
    summary = score([_perfect(c) for c in cases], cases)
    assert summary.scope_ceiling == 1.0 and summary.adjusted_ceiling == 0.75 and summary.containment == 0.75
    assert summary.scope_ceiling_without_redirects == 1.0 and summary.adjusted_ceiling_without_redirects == 2 / 3
