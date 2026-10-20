"""The grader check (R19): about 30 graded answers chosen in advance, spread across the grader's right and wrong
verdicts, for the author to grade blind; then the full agree and disagree table.

Run: python -m eval.grader_check sheet     writes data/grader_check.csv (no grader verdicts in it); grades already in
                                           the sheet are kept, and it refuses if any would be dropped
     python -m eval.grader_check table     reads Claude Fable 5.1's blind grades (it stands in for the author, D44),
                                           or the author's if the author column is filled, and writes
                                           data/results/grader_check.json
     python -m eval.grader_check table claude
                                           reads a second model's blind grades (claude_correct column) and writes
                                           data/results/grader_check_claude.json; a model-vs-model check, not the
                                           author's human check"""

import csv
import json
import sys
from pathlib import Path

from eval.grader import Verdict, agreement_table, choose_check_sample

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results" / "retrieval"
SHEET = ROOT / "data" / "grader_check.csv"
HIDDEN = ROOT / "data" / "results" / "grader_check_sample.json"
OUT = ROOT / "data" / "results"  # the grader's verdicts for the sample, kept apart


COLUMNS = {"author": ("author_correct (yes or no)", "grader_check.json"),
           "claude": ("claude_correct (yes or no)", "grader_check_claude.json"),
           "fable": ("fable_correct (yes or no)", "grader_check_fable.json")}
BASE = ["id", "question", "answer", "reference_answer"]
FABLE = "Claude Fable 5.1, standing in for the author (D44)"


def _graded(row: dict) -> dict:
    return {column: row[column] for column, _ in COLUMNS.values() if (row.get(column) or "").strip()}


def write_sheet() -> None:
    verdicts = [Verdict(**json.loads(line)) for line in (RESULTS / "verdicts.jsonl").open()]
    answers = {f"{a['qid']}|{a['mode']}": a for a in map(json.loads, (RESULTS / "answers_to_grade.jsonl").open())}
    sample = choose_check_sample(verdicts, n=30, seed=11)
    existing = {r["id"]: _graded(r) for r in csv.DictReader(SHEET.open())} if SHEET.exists() else {}
    dropped = sorted(i for i, grades in existing.items() if grades and i not in {v.id for v in sample})
    if dropped:
        raise SystemExit(f"refusing to rewrite {SHEET}: it holds grades for {dropped}, which are no longer in the sample")
    HIDDEN.write_text(json.dumps({v.id: v.correct for v in sample}, indent=1))
    columns = BASE + [column for column, _ in COLUMNS.values()]
    with SHEET.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for v in sample:
            a = answers[v.id]
            writer.writerow({"id": v.id, "question": a["question"], "answer": a["answer"],
                             "reference_answer": a.get("reference_answer") or "(cannot be answered: should hand off)",
                             **existing.get(v.id, {})})
    print(f"{len(sample)} answers in {SHEET}; grade a column yes or no without looking at the grader's verdicts")


def write_table(who: str | None = None) -> None:
    """who: author, claude or fable. By default the author's column if anyone filled it, otherwise Fable's, written as
    the grader check (grader_check.json)."""
    rows_all = list(csv.DictReader(SHEET.open()))
    main = who is None
    if main:
        who = "author" if any((r.get(COLUMNS["author"][0]) or "").strip() for r in rows_all) else "fable"
    column, out = COLUMNS[who]
    out = "grader_check.json" if main else out
    grader = json.loads(HIDDEN.read_text())
    rows = [r for r in rows_all if (r.get(column) or "").strip()]
    checker = [r[column].strip().lower().startswith("y") for r in rows]
    table = agreement_table(checker, [bool(grader[r["id"]]) for r in rows])
    if who != "author":  # agreement_table names its first column "author"; say who actually graded
        table = {k.replace("author", who): v for k, v in table.items()}
        table["note"] = f"{who} graded blind; this is model-vs-model agreement, not a human check"
    table["checker"] = FABLE if main and who == "fable" else who
    table["graded"] = len(rows)
    table["disagreements"] = [r["id"] for r, a in zip(rows, checker) if a != bool(grader[r["id"]])]
    (OUT / out).write_text(json.dumps(table, indent=1))
    print(json.dumps(table, indent=1))


if __name__ == "__main__":
    if sys.argv[1:2] == ["table"]:
        write_table(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        write_sheet()
