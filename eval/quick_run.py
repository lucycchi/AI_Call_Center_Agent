"""The quick test run before every deploy (R22): 20 working-set cases through the full harness with Codex grading.
It fails if any safety case fails, any booking database check fails, or knowledge correctness is below 0.8.

Run: python -m eval.quick_run   (test key and Codex; writes data/results/quick-<time>/)"""

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAFETY = {"gas, carbon monoxide or sparks", "burning smell"}
KNOWLEDGE_BAR = 0.8


@dataclass
class QuickResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def working_cases(ids: list[str]) -> list[dict]:
    split = json.loads((ROOT / "data" / "split.json").read_text())
    held = set(split["held_out"]) & set(ids)
    if held:
        raise ValueError(f"the quick run uses working-set cases only, not {sorted(held)}")
    return [json.loads((ROOT / "data" / "testset" / f"{cid}.json").read_text()) for cid in ids]


def _knowledge_verdicts(attempt, case: dict) -> list[bool]:
    """Codex's verdict on each knowledge request in the conversation (the sub-reason when it needs documents, and every
    listed knowledge request), or the conversation's knowledge verdict when there are none per request."""
    wanted = {r["request"] for r in case.get("requests", [])
              if r["kind"] == "knowledge" or (r["kind"] == "sub-reason" and case.get("needs_documents"))}
    per_request = [bool(r["correct"]) for r in attempt.grades.get("requests", []) if r.get("request") in wanted
                   and r.get("correct") is not None]
    if per_request:
        return per_request
    return [attempt.grades["knowledge_correct"]] if "knowledge_correct" in attempt.grades else []


def judge(attempts: list, cases: dict) -> QuickResult:
    first = [a for a in attempts if a.attempt == 1]
    reasons = []
    for a in first:
        if cases[a.case_id]["sub_reason"] in SAFETY and not a.all_correct:
            reasons.append(f"safety case {a.case_id} failed")
    for a in first:
        if a.grades.get("booking_correct") is False:
            reasons.append(f"booking check failed in {a.case_id}")
    knowledge = [v for a in first for v in _knowledge_verdicts(a, cases[a.case_id])]
    if knowledge and sum(knowledge) / len(knowledge) < KNOWLEDGE_BAR:
        reasons.append(f"knowledge correctness {sum(knowledge) / len(knowledge):.0%} is below {KNOWLEDGE_BAR:.0%}")
    return QuickResult(not reasons, reasons)


def two_of_three(run) -> QuickResult:
    """Pass when two of up to three runs pass; stop as soon as the result is settled. One run alone is too noisy."""
    results = []
    for attempt in (1, 2, 3):
        results.append(run(attempt))
        passed = sum(r.passed for r in results)
        if passed >= 2 or len(results) - passed >= 2:
            break
    reasons = [f"run {n}: {reason}" for n, r in enumerate(results, 1) for reason in r.reasons]
    return QuickResult(sum(r.passed for r in results) >= 2, reasons)


def quick_run_twice_of_three(n: int = 20, name: str = "quick") -> QuickResult:
    return two_of_three(lambda attempt: quick_run(n, f"{name}-run{attempt}"))


def quick_run(n: int = 20, name: str = "") -> QuickResult:
    from eval.run import run_graded
    split = json.loads((ROOT / "data" / "split.json").read_text())
    cases = working_cases(split["working"][:n])
    attempts, _ = run_graded(cases, name or "quick")
    return judge(attempts, {c["case_id"]: c for c in cases})


if __name__ == "__main__":
    result = quick_run_twice_of_three()
    print(json.dumps({"passed": result.passed, "reasons": result.reasons}, indent=1))
