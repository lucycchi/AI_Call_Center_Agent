"""Grade the retrieval answers (R30, R31): answers from keyword-only search, combined search and the whole knowledge
base, scored pass or fail on correctness, faithfulness, citation accuracy and correct refusal.

Run: python -m eval.grade_retrieval   (runs Codex; tell the author first)
Writes data/results/retrieval/verdicts.jsonl and answer_scores.json."""

import json
from pathlib import Path

from eval.grader import Verdict, grade, grader_model, runner_for, write_verdicts

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results" / "retrieval"


def answer_items(answers: list[dict], searcher) -> list[dict]:
    """Each answer with the passages it was written from, as stored with the answer; answers saved before passages
    were stored are searched again the same way and flagged. Whole-knowledge-base answers were given every current
    document, too much to show, so their faithfulness is not graded."""
    from eval.retrieval_eval import passage_label
    items = []
    for a in answers:
        whole, again = a["mode"] == "whole_kb", "passages" not in a and a["mode"] != "whole_kb"
        passages = [] if whole else a["passages"] if not again else [passage_label(s.chunk)
                                                                     for s in searcher.search(a["question"], mode=a["mode"])]
        items.append({"id": f"{a['qid']}|{a['mode']}", "type": "knowledge answer", "question": a["question"],
                      "answer": a["answer"], "reference_answer": a.get("reference_answer"), "passages": passages,
                      "whole_knowledge_base": whole, "kind": a["kind"], "mode": a["mode"],
                      **({"passages_searched_again": True} if again else {})})
    return items


def answer_scores(items: list[dict], verdicts: list[Verdict]) -> dict:
    by_id = {v.id: v for v in verdicts}
    scores = {}
    for mode in ("keyword", "combined", "whole_kb"):
        rows = [(i, by_id[i["id"]]) for i in items if i["mode"] == mode and i["id"] in by_id]

        def share(values):
            values = [v for v in values if v is not None]
            return sum(values) / len(values) if values else None
        scores[mode] = {
            "answers": len(rows),
            "correct": share([v.correct for _, v in rows]),
            "faithful": None if mode == "whole_kb" else share([v.faithful for _, v in rows]),
            "citation_ok": share([v.citation_ok for _, v in rows]),
            "refusal_ok": share([v.refusal_ok for i, v in rows if not i["reference_answer"]]),
            "stale_trap_correct": share([v.correct for i, v in rows if i["kind"] == "stale_trap"]),
        }
    return scores


def main() -> None:
    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher

    load_dotenv(ROOT / ".env")
    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)
    answers = [json.loads(line) for line in (RESULTS / "answers_to_grade.jsonl").open()]
    items = answer_items(answers, searcher)
    verdicts = grade(items, runner_for(), grader_model())
    write_verdicts(verdicts, RESULTS / "verdicts.jsonl")
    scores = answer_scores(items, verdicts)
    scores["grader_model"] = grader_model()
    scores["passages_searched_again"] = sum(1 for i in items if i.get("passages_searched_again"))
    scores["grader_reported_model"] = sorted({v.reported_model for v in verdicts})
    (RESULTS / "answer_scores.json").write_text(json.dumps(scores, indent=1))
    print(json.dumps(scores, indent=1))


if __name__ == "__main__":
    main()
