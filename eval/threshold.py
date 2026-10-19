"""The retrieval threshold, chosen on the working set from a curve of containment against wrong confident answers
(R32). Each working-set knowledge question is answered when its top meaning-based score clears the threshold, or
handed off when it does not; an answered question counts by its graded correctness.

Run: python -m eval.threshold   (needs VOYAGE_API_KEY and the graded retrieval answers; writes data/results/threshold.json)"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS = [round(0.20 + 0.05 * n, 2) for n in range(12)]  # 0.20 to 0.75


@dataclass(frozen=True)
class Point:
    threshold: float
    containment: float
    wrong_confident: int


def curve(questions: list[dict], thresholds: list[float] = THRESHOLDS) -> list[Point]:
    """questions: qid, the top meaning score, whether the combined-search answer was graded correct, and whether the
    documents cannot answer it (then a correct answer is a refusal, which hands off and is never contained)."""
    points = []
    for t in thresholds:
        answered = [q for q in questions if q["score"] >= t]
        contained = sum(1 for q in answered if q["correct"] and not q.get("unanswerable"))
        wrong = sum(1 for q in answered if not q["correct"])
        points.append(Point(t, contained / len(questions) if questions else 0.0, wrong))
    return points


FLOOR = 0.25  # below this a top match is close to random, so no threshold under it is considered
WRONG_COST = 2.5  # one wrong confident answer counts against two and a half correct contained ones


def choose_threshold(points: list[Point], questions: int = 100) -> float:
    """The most correct contained answers net of wrong confident ones (each costing WRONG_COST), among thresholds of
    at least FLOOR; on a tie, the lowest threshold."""
    eligible = [p for p in points if p.threshold >= FLOOR - 1e-9]
    best = max(eligible, key=lambda p: (round(p.containment * questions - WRONG_COST * p.wrong_confident, 6), -p.threshold))
    return best.threshold


def main() -> None:
    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher

    load_dotenv(ROOT / ".env")
    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)
    verdicts = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "data" / "results" / "retrieval" / "verdicts.jsonl").open()}
    questions = []
    for q in map(json.loads, (ROOT / "data" / "knowledge_questions.jsonl").open()):
        if q["set"] != "working":
            continue
        verdict = verdicts.get(f"{q['qid']}|combined")
        if verdict is None:
            continue
        score = max(r.meaning_score for r in searcher.search(q["question"], mode="combined"))
        questions.append({"qid": q["qid"], "score": round(score, 4), "correct": bool(verdict["correct"]),
                          "unanswerable": not q["evidence_spans"]})
    points = curve(questions)
    chosen = choose_threshold(points, len(questions))
    report = {"set": "working", "questions": len(questions), "chosen": chosen, "rule": {"floor": FLOOR, "wrong_cost": WRONG_COST},
              "points": [asdict(p) for p in points],
              "scores": questions,
              "note": "Containment and wrong confident answers over the working-set knowledge questions, from the graded "
                      "combined-search answers; the held-out questions are never used."}
    (ROOT / "data" / "results" / "threshold.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "scores"}, indent=1))


if __name__ == "__main__":
    main()
