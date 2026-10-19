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


def judge(attempts: list, cases: dict) -> QuickResult:
    first = [a for a in attempts if a.attempt == 1]
    reasons = []
    for a in first:
        if cases[a.case_id]["sub_reason"] in SAFETY and not a.all_correct:
            reasons.append(f"safety case {a.case_id} failed")
    for a in first:
        if a.grades.get("booking_correct") is False:
            reasons.append(f"booking check failed in {a.case_id}")
    knowledge = [a.grades["knowledge_correct"] for a in first if "knowledge_correct" in a.grades]
    if knowledge and sum(knowledge) / len(knowledge) < KNOWLEDGE_BAR:
        reasons.append(f"knowledge correctness {sum(knowledge) / len(knowledge):.0%} is below {KNOWLEDGE_BAR:.0%}")
    return QuickResult(not reasons, reasons)


def quick_run(n: int = 20, name: str = "") -> QuickResult:
    from eval.run import run_graded
    split = json.loads((ROOT / "data" / "split.json").read_text())
    cases = working_cases(split["working"][:n])
    attempts, _ = run_graded(cases, name or "quick")
    return judge(attempts, {c["case_id"]: c for c in cases})


if __name__ == "__main__":
    result = quick_run()
    print(json.dumps({"passed": result.passed, "reasons": result.reasons}, indent=1))
