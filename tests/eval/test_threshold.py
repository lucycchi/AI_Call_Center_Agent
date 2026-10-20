from pathlib import Path

import pytest

from eval.freeze import freeze_agent
from eval.quick_run import judge
from eval.threshold import Point, choose_threshold, curve

ROOT = Path(__file__).resolve().parents[2]


def test_the_threshold_with_fewest_wrong_answers_then_most_containment_is_chosen():
    points = [Point(0.2, 0.70, 3), Point(0.4, 0.65, 0), Point(0.6, 0.55, 0)]
    assert choose_threshold(points) == 0.4


def test_the_curve_answers_above_the_threshold_and_hands_off_below():
    questions = [{"qid": "a", "score": 0.8, "correct": True}, {"qid": "b", "score": 0.5, "correct": False},
                 {"qid": "c", "score": 0.3, "correct": True, "unanswerable": True}]
    points = {p.threshold: p for p in curve(questions, thresholds=[0.25, 0.4, 0.6, 0.9])}
    assert (points[0.25].containment, points[0.25].wrong_confident) == (1 / 3, 1)  # "c" answered: correct only as a refusal
    assert (points[0.6].containment, points[0.6].wrong_confident) == (1 / 3, 0)
    assert (points[0.9].containment, points[0.9].wrong_confident) == (0.0, 0)


def _case(cid, sub="hvac repair", needs_documents=False):
    return {"case_id": cid, "sub_reason": sub, "needs_documents": needs_documents, "calls_weight": 1}


def _attempt(cid, correct=True, **grades):
    from eval.harness import Attempt
    return Attempt(cid, all_correct=correct, grades=grades)


def test_the_quick_run_refuses_held_out_cases():
    import json
    held = json.loads((ROOT / "data" / "split.json").read_text())["held_out"][0]
    from eval.quick_run import working_cases
    with pytest.raises(ValueError):
        working_cases([held])


def test_the_quick_run_fails_on_safety_booking_or_knowledge_and_says_why():
    cases = {c["case_id"]: c for c in [_case("s", "burning smell"), _case("b"), _case("k", "transfer", True), _case("k2", "transfer", True)]}
    good = [_attempt("s"), _attempt("b", booking_correct=True), _attempt("k", knowledge_correct=True), _attempt("k2", knowledge_correct=True)]
    assert judge(good, cases).passed
    bad = [_attempt("s", False), _attempt("b", booking_correct=False), _attempt("k", knowledge_correct=False),
           _attempt("k2", knowledge_correct=True)]
    result = judge(bad, cases)
    assert not result.passed and len(result.reasons) == 3


def test_the_freeze_hash_covers_the_agent_and_not_the_web_layer(tmp_path):
    import shutil
    root = tmp_path / "repo"
    for part in ("app/core", "app/safety", "app/web", "data/index"):
        (root / part).mkdir(parents=True)
    (root / "app/core/engine.py").write_text("a")
    (root / "app/safety/check.py").write_text("b")
    (root / "app/web/page.py").write_text("c")
    (root / "app/config.py").write_text("d")
    (root / "data/index/chunks.jsonl").write_text("e")
    first = freeze_agent(root)
    (root / "app/web/page.py").write_text("changed")
    assert freeze_agent(root) == first
    (root / "app/safety/check.py").write_text("changed")
    assert freeze_agent(root) != first


def test_the_chosen_rule_on_the_working_set_curve_and_its_floor():
    import json
    report = json.loads((ROOT / "data" / "results" / "threshold.json").read_text())
    points = [Point(**p) for p in report["points"]]
    assert choose_threshold(points, report["questions"]) == 0.25
    from app.config import SETTINGS
    assert SETTINGS.retrieval_threshold == 0.25


def test_knowledge_is_judged_over_every_graded_knowledge_request():
    cases = {"k": {**_case("k", "what it includes or price", True),
                   "requests": [{"request": "what it includes or price", "kind": "sub-reason"},
                                {"request": "how much it costs", "kind": "knowledge"},
                                {"request": "whether it covers plumbing", "kind": "knowledge"}]},
             "b": {**_case("b"), "requests": [{"request": "hvac repair", "kind": "sub-reason"}]}}
    graded = _attempt("k", knowledge_correct=False,
                      requests=[{"request": "what it includes or price", "correct": True},
                                {"request": "how much it costs", "correct": True},
                                {"request": "whether it covers plumbing", "correct": True}])
    assert judge([graded, _attempt("b")], cases).passed  # three of three knowledge requests right


def test_the_quick_run_passes_on_two_of_three_and_stops_once_settled():
    from eval.quick_run import QuickResult, two_of_three
    results = iter([QuickResult(True), QuickResult(True), QuickResult(False)])
    calls = []

    def run(n):
        calls.append(n)
        return next(results)
    final = two_of_three(run)
    assert final.passed and calls == [1, 2]
    results = iter([QuickResult(False, ["a"]), QuickResult(True), QuickResult(False, ["b"])])
    calls.clear()
    final = two_of_three(run)
    assert not final.passed and calls == [1, 2, 3] and final.reasons


def test_a_safety_or_booking_failure_in_any_run_fails_the_quick_run():
    from eval.quick_run import QuickResult, two_of_three
    results = iter([QuickResult(False, ["safety case s failed"], hard=True), QuickResult(True), QuickResult(True)])
    calls = []

    def run(n):
        calls.append(n)
        return next(results)
    final = two_of_three(run)
    assert not final.passed and calls == [1] and final.reasons == ["run 1: safety case s failed"]
    cases = {c["case_id"]: c for c in [_case("s", "burning smell"), _case("b")]}
    retry_broke_booking = [_attempt("s"), _attempt("b", False, booking_correct=True), _attempt_n("b", 2, booking_correct=False)]
    result = judge(retry_broke_booking, cases)
    assert not result.passed and result.hard


def _attempt_n(cid, n, correct=True, **grades):
    from eval.harness import Attempt
    return Attempt(cid, attempt=n, all_correct=correct, grades=grades)


def test_the_quick_run_fails_with_no_attempts_or_a_stopped_or_incomplete_run():
    from eval.harness import Attempt
    cases = {c["case_id"]: c for c in [_case("a"), _case("b")]}
    assert not judge([], cases).passed
    assert not judge([_attempt("a")], cases).passed  # "b" never ran
    stopped = Attempt("b", all_correct=True, stopped="budget")
    assert not judge([_attempt("a"), stopped], cases).passed
    errored = Attempt("b", all_correct=False, stopped="error", error="boom")
    assert not judge([_attempt("a"), errored], cases).passed
    assert judge([_attempt("a"), _attempt("b")], cases).passed


def test_the_quick_run_command_exits_nonzero_when_it_fails(monkeypatch):
    import eval.quick_run as quick
    from eval.quick_run import QuickResult
    monkeypatch.setattr(quick, "quick_run_twice_of_three", lambda: QuickResult(False, ["run 1: no attempts"], hard=True))
    with pytest.raises(SystemExit) as stopped:
        quick.main()
    assert stopped.value.code == 1
    monkeypatch.setattr(quick, "quick_run_twice_of_three", lambda: QuickResult(True))
    with pytest.raises(SystemExit) as stopped:
        quick.main()
    assert stopped.value.code == 0


def test_the_freeze_hash_covers_the_data_files_the_agent_reads(tmp_path):
    root = tmp_path / "repo"
    for part in ("app/core", "data/kb_text", "call_data/knowledge_base/internal", "call_data/knowledge_base/faq"):
        (root / part).mkdir(parents=True)
    (root / "app/core/engine.py").write_text("a")
    (root / "data/document_list.csv").write_text("path,status,audience,effective_date,reason\n"
                                                 "internal/notes.md,current,internal,,x\nfaq/faq.md,current,customers,,y\n")
    (root / "data/kb_text/pricing__2026_fee_schedule.md").write_text("- Diagnostic, Non-member: $89")
    (root / "call_data/knowledge_base/internal/notes.md").write_text("internal")
    (root / "call_data/knowledge_base/faq/faq.md").write_text("faq")
    first = freeze_agent(root)
    for path in ("data/kb_text/pricing__2026_fee_schedule.md", "call_data/knowledge_base/internal/notes.md"):
        (root / path).write_text("changed")
        assert freeze_agent(root) != first, path
        first = freeze_agent(root)
    text = (root / "data/document_list.csv").read_text()
    (root / "data/document_list.csv").write_text(text.replace("faq/faq.md,current", "faq/faq.md,stale"))
    assert freeze_agent(root) != first


def test_each_graded_retrieval_run_is_kept_under_the_agent_it_measured(tmp_path):
    from eval.grade_retrieval import keep_run
    (tmp_path / "answers_to_grade.jsonl").write_text("a\n")
    (tmp_path / "verdicts.jsonl").write_text("v\n")
    first = keep_run(tmp_path, "abc123")
    second = keep_run(tmp_path, "abc123")
    assert first != second and first.parent == tmp_path / "runs" / "abc123"
    assert (second / "verdicts.jsonl").read_text() == "v\n" and (second / "answers_to_grade.jsonl").read_text() == "a\n"


def test_the_threshold_pools_every_run_of_the_current_agent(tmp_path):
    import json
    from eval.threshold import pooled_verdicts
    for agent, run, correct in [("now", "1", True), ("now", "2", False), ("old", "1", True)]:
        folder = tmp_path / "runs" / agent / run
        folder.mkdir(parents=True)
        (folder / "verdicts.jsonl").write_text(json.dumps({"id": "q1|combined", "correct": correct}) + "\n")
    runs = pooled_verdicts(tmp_path, "now")
    assert sorted(v["q1|combined"]["correct"] for v in runs) == [False, True]


def test_pooled_runs_count_each_answer_once_in_the_curve():
    from eval.threshold import choose_threshold, curve
    one = [{"qid": "q1", "score": 0.3, "correct": True}, {"qid": "q2", "score": 0.3, "correct": True}]
    two = [{"qid": "q1", "score": 0.3, "correct": True}, {"qid": "q2", "score": 0.3, "correct": False}]
    [point] = curve(one + two, [0.25])
    assert point.containment == 0.75 and point.wrong_confident == 1
    assert choose_threshold(curve(one + two), 4) == 0.25
