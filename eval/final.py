"""The final held-out measurement (R23): every held-out case run once on the frozen agent and graded, then one
summary holding every Summary field plus the retrieval, answers, adversarial, grader-check and label-agreement
sections that the Results tab shows (app/web/results.py).

Run: python -m eval.final run --confirm-held-out
                                 checks the held-out hash in data/split.json and the agent hash in
                                 data/agent_freeze.json, runs and grades every held-out case (Codex grading), and
                                 writes data/results/final/; tell the author first
     python -m eval.final summary  rebuilds data/results/final/summary.json once a missing section exists (for example
                                 after the adversarial run or the author's blind grades)
     python -m eval.final consistency --confirm-held-out
                                 the optional consistency runs: 30 held-out cases, three runs each, seed 3

The run's own numbers are kept in run_summary.json; summary.json is written only when every field and section is
present, so until then the Results tab says the final results are not yet run. Web, operations and deployment code
may change before the run (eval/freeze.py covers only the agent)."""

import argparse
import json
import random
from dataclasses import fields
from pathlib import Path

from eval.run import ROOT, check_results_folder, refuse_held_out
from eval.scoring import Summary

# Where each section comes from, relative to the project folder; run python -m eval.run_adversarial again for the
# final measurement, on the frozen agent, before the summary is finished.
SECTION_FILES = {
    "retrieval": "data/results/retrieval/summary.json",
    "answers": "data/results/retrieval/answer_scores.json",
    "adversarial": "data/results/adversarial/summary.json",
    "grader_agreement": "data/results/grader_check.json",
    "label_agreement": "data/label_agreement.json",
}
SECTIONS = tuple(SECTION_FILES)
LEFT_OUT = {"settings"}  # run settings are kept in the run's own files, not in the Results tab's sections
CONSISTENCY_CASES, CONSISTENCY_RUNS, CONSISTENCY_SEED = 30, 3, 3


class IncompleteSummary(Exception):
    pass


def final_folder(root: Path) -> Path:
    return root / "data" / "results" / "final"


def held_out_cases(root: Path, confirmed: bool) -> tuple[dict, list[dict]]:
    """The split record and the held-out cases, after every check: confirmation, the held-out hash, the agent hash."""
    if not confirmed:
        raise SystemExit("refusing: the final run sends the held-out cases to the agent and to Codex; tell the author, "
                         "then pass --confirm-held-out")
    split = json.loads((root / "data" / "split.json").read_text())
    refuse_held_out(split["held_out"], final=True, root=root)
    return split, [json.loads((root / "data" / "testset" / f"{cid}.json").read_text()) for cid in split["held_out"]]


def validate(summary: dict) -> None:
    missing = [f.name for f in fields(Summary) if f.name not in summary]
    missing += [s for s in SECTIONS if not isinstance(summary.get(s), dict) or not summary[s]]
    if missing:
        raise IncompleteSummary(f"the final summary is missing {', '.join(missing)}")


def _section(root: Path, name: str) -> dict | None:
    path = root / SECTION_FILES[name]
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if k not in LEFT_OUT} if isinstance(data, dict) else None


def finish_summary(root: Path = ROOT) -> dict:
    """The run's numbers, the freeze hashes and every section, validated, then written as summary.json."""
    out = final_folder(root)
    summary = json.loads((out / "run_summary.json").read_text())
    summary["held_out_hash"] = json.loads((root / "data" / "split.json").read_text())["held_out_hash"]
    summary["agent_hash"] = json.loads((root / "data" / "agent_freeze.json").read_text())["hash"]
    for name in SECTIONS:
        summary[name] = _section(root, name)
    validate(summary)
    partial = out / "summary.json.partial"
    partial.write_text(json.dumps(summary, indent=1))
    partial.replace(out / "summary.json")
    return summary


def run_final(runner=None, root: Path = ROOT, confirmed: bool = False) -> dict:
    """Run and grade every held-out case once, then finish the summary. Raises IncompleteSummary, with the run kept,
    if a section does not exist yet; finish_summary completes it later."""
    _, cases = held_out_cases(root, confirmed)
    out = final_folder(root)
    check_results_folder(out, overwrite=False, final=True)
    if runner is None:
        from eval.run import run_graded as runner
    runner(cases, out.name, out=out)
    (out / "summary.json").replace(out / "run_summary.json")
    return finish_summary(root)


def consistency_cases(held_out: list[str]) -> list[str]:
    return sorted(random.Random(CONSISTENCY_SEED).sample(sorted(held_out), min(CONSISTENCY_CASES, len(held_out))))


def run_consistency(runner=None, root: Path = ROOT, confirmed: bool = False) -> dict:
    """The optional consistency runs: the same 30 held-out cases three times; the share whose first attempt was
    correct in all three runs."""
    split, cases = held_out_cases(root, confirmed)
    chosen = set(consistency_cases(split["held_out"]))
    cases = [c for c in cases if c["case_id"] in chosen]
    folder = final_folder(root) / "consistency"
    outs = [folder / f"run{n}" for n in range(1, CONSISTENCY_RUNS + 1)]
    for out in outs:
        check_results_folder(out, overwrite=False, final=True)
    if runner is None:
        from eval.run import run_graded as runner
    correct = []
    for out in outs:
        attempts, _ = runner(cases, out.name, out=out)
        correct.append({a.case_id for a in attempts if a.attempt == 1 and a.all_correct is True})
    always = set.intersection(*correct)
    result = {"cases": len(cases), "runs": CONSISTENCY_RUNS, "seed": CONSISTENCY_SEED,
              "correct_all_three": len(always) / len(cases) if cases else None,
              "correct_each_run": [len(c) / len(cases) if cases else None for c in correct],
              "not_always_correct": sorted(chosen - always)}
    (folder / "summary.json").write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "summary", "consistency"])
    parser.add_argument("--confirm-held-out", action="store_true",
                        help="the author has been told: run the held-out cases and send them to Codex")
    args = parser.parse_args()
    if args.command == "summary":
        summary = finish_summary()
    else:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        run = run_final if args.command == "run" else run_consistency
        summary = run(confirmed=args.confirm_held_out)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
