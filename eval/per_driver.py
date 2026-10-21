"""Results by call reason: accuracy on the reasons the agent is meant to handle, and the escalation rate and its
correctness on the rest (the PRD's "accuracy on the handled drivers and escalation rate on the rest"). Scored like the
summary (eval/scoring.py): first attempts only, weighted by the calls each case stands for.

Run: python -m eval.per_driver   (reads data/results/final/attempts.jsonl and the test cases' labels; writes
                                  data/results/final/per_driver.json; no model calls)"""

import json
from collections import defaultdict

from eval.run import ROOT
from eval.scoring import _contained


def _share(pairs: list[tuple[int, bool]]) -> float | None:
    total = sum(w for w, _ in pairs)
    return sum(w for w, ok in pairs if ok) / total if total else None


def by_driver(attempts: list, cases: list[dict]) -> list[dict]:
    by_case = {c["case_id"]: c for c in cases}
    first = {a.case_id: a for a in attempts if a.attempt == 1 and a.stopped != "budget" and a.case_id in by_case}
    groups = defaultdict(list)
    for cid, a in first.items():
        groups[by_case[cid]["reason"]].append((by_case[cid], a))
    rows = []
    for reason, members in groups.items():
        handled = [(c, a) for c, a in members if c["expected_outcome"] in ("contained", "redirect")]
        escalate = [(c, a) for c, a in members if c["expected_outcome"] == "handed_off"]
        rows.append({
            "reason": reason,
            "cases": len(members),
            "weighted_calls": sum(c["calls_weight"] for c, _ in members),
            "handled_cases": len(handled),
            "handled_accuracy": _share([(c["calls_weight"], _contained(a)) for c, a in handled]),
            "escalation_cases": len(escalate),
            "escalation_rate": _share([(c["calls_weight"], a.handed_off) for c, a in escalate]),
            "escalation_correct": _share([(c["calls_weight"], a.handed_off and a.grades.get("handoff_reason_correct") is True)
                                          for c, a in escalate]),
        })
    return sorted(rows, key=lambda r: -r["weighted_calls"])


def main() -> None:
    from eval.run import _attempt_from, _read_lines
    out = ROOT / "data" / "results" / "final"
    split = json.loads((ROOT / "data" / "split.json").read_text())
    cases = [json.loads((ROOT / "data" / "testset" / f"{cid}.json").read_text()) for cid in split["held_out"]]
    attempts = [_attempt_from(line) for line in _read_lines(out / "attempts.jsonl")]
    rows = by_driver(attempts, cases)
    (out / "per_driver.json").write_text(json.dumps(rows, indent=1))
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
