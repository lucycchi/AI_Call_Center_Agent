"""The grader check (R19): about 30 graded answers chosen in advance, spread across the grader's right and wrong
verdicts, for the author to grade blind; then the full agree and disagree table.

Run: python -m eval.grader_check sheet     writes data/grader_check.csv (no grader verdicts in it)
     python -m eval.grader_check table     reads the author's grades and writes data/results/grader_check.json"""

import csv
import json
import sys
from pathlib import Path

from eval.grader import Verdict, agreement_table, choose_check_sample

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results" / "retrieval"
SHEET = ROOT / "data" / "grader_check.csv"
HIDDEN = ROOT / "data" / "results" / "grader_check_sample.json"  # the grader's verdicts for the sample, kept apart


def write_sheet() -> None:
    verdicts = [Verdict(**json.loads(line)) for line in (RESULTS / "verdicts.jsonl").open()]
    answers = {f"{a['qid']}|{a['mode']}": a for a in map(json.loads, (RESULTS / "answers_to_grade.jsonl").open())}
    sample = choose_check_sample(verdicts, n=30, seed=11)
    HIDDEN.write_text(json.dumps({v.id: v.correct for v in sample}, indent=1))
    with SHEET.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "question", "answer", "reference_answer", "author_correct (yes or no)"])
        for v in sample:
            a = answers[v.id]
            writer.writerow([v.id, a["question"], a["answer"], a.get("reference_answer") or "(cannot be answered: should hand off)", ""])
    print(f"{len(sample)} answers in {SHEET}; grade the last column yes or no without looking at the grader's verdicts")


def write_table() -> None:
    grader = json.loads(HIDDEN.read_text())
    rows = [r for r in csv.DictReader(SHEET.open()) if r["author_correct (yes or no)"].strip()]
    author = [r["author_correct (yes or no)"].strip().lower().startswith("y") for r in rows]
    table = agreement_table(author, [bool(grader[r["id"]]) for r in rows])
    table["graded"] = len(rows)
    table["disagreements"] = [r["id"] for r, a in zip(rows, author) if a != bool(grader[r["id"]])]
    (ROOT / "data" / "results" / "grader_check.json").write_text(json.dumps(table, indent=1))
    print(json.dumps(table, indent=1))


if __name__ == "__main__":
    write_table() if sys.argv[1:] == ["table"] else write_sheet()
