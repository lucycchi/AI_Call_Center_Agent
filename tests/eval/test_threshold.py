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
