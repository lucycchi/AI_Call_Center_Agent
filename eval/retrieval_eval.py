"""Measure retrieval on its own (R30): recall and hit rate at five, coverage and stale-trap accuracy,
keyword-only against combined search, and answers from combined search against answers from the
whole current knowledge base in the prompt (graded later, Task 19).

Run: python -m eval.retrieval_eval   (needs the built index and VOYAGE_API_KEY; answers need ANTHROPIC_API_KEY)
"""

import json
from collections.abc import Callable
from pathlib import Path

from app.knowledge.index import Chunk

ROOT = Path(__file__).resolve().parent.parent
TOP = 5
EXCLUDED = ("archive/", "faq/faq_old_copy.md", "services/scheduling_guide.md", "services/duct_cleaning.md",
            "internal/", "policies/escalation_and_safety.md", "services/technician_arrival_and_etas.md")


def _found(chunk: Chunk, span: dict) -> bool:
    return (chunk.chunk_id.split("#")[0] == span["file"].removesuffix(".md")
            and chunk.start_line <= span["end_line"] and span["start_line"] <= chunk.end_line)


def recall_at_k(results: list[Chunk], needed: list[dict], k: int = TOP) -> float:
    if not needed:
        return 0.0
    top = results[:k]
    return sum(any(_found(c, s) for c in top) for s in needed) / len(needed)


def hit_at_k(results: list[Chunk], needed: list[dict], k: int = TOP) -> bool:
    return any(_found(c, s) for c in results[:k] for s in needed)


def coverage(questions: list[dict]) -> float:
    return sum(bool(q["evidence_spans"]) for q in questions) / len(questions)


def stale_trap_passes(results: list[Chunk], needed: list[dict], k: int = TOP) -> bool:
    top = results[:k]
    return hit_at_k(top, needed) and not any(c.document.startswith(EXCLUDED) for c in top)


def compare_modes(questions: list[dict], searcher) -> dict:
    report: dict = {"questions": len(questions), "coverage": coverage(questions)}
    answerable = [q for q in questions if q["evidence_spans"]]
    for mode in ("keyword", "combined"):
        results = {q["qid"]: [s.chunk for s in searcher.search(q["question"], mode=mode, k=TOP)] for q in answerable}
        traps = [q for q in answerable if q["kind"] == "stale_trap"]
        report[mode] = {
            "recall_at_5": sum(recall_at_k(results[q["qid"]], q["evidence_spans"]) for q in answerable) / max(len(answerable), 1),
            "hit_at_5": sum(hit_at_k(results[q["qid"]], q["evidence_spans"]) for q in answerable) / max(len(answerable), 1),
            "stale_trap_accuracy": (sum(stale_trap_passes(results[q["qid"]], q["evidence_spans"]) for q in traps) / len(traps))
            if traps else None,
            "misses": [q["qid"] for q in answerable if not hit_at_k(results[q["qid"]], q["evidence_spans"])],
        }
    return report


def answer_both_ways(questions: list[dict], searcher, writer: Callable[[str, str], str], whole_kb: str, out: Path) -> None:
    """Answers from the top five passages and from the whole knowledge base, written for grading."""
    with out.open("w") as handle:
        for q in questions:
            passages = "\n\n".join(s.chunk.text for s in searcher.search(q["question"], mode="combined", k=TOP))
            for mode, context in (("combined", passages), ("whole_kb", whole_kb)):
                handle.write(json.dumps({"qid": q["qid"], "kind": q["kind"], "mode": mode, "question": q["question"],
                                         "answer": writer(q["question"], context),
                                         "reference_answer": q.get("reference_answer")}) + "\n")


ANSWER_PROMPT = """You answer customer questions for Meridian Home Comfort using ONLY the company documents below.
If the documents do not answer the question, say you will pass the question to a team member. Never guess.

Documents:
{context}

Question: {question}"""


def sonnet_writer() -> Callable[[str, str], str]:
    import anthropic

    from app.config import SETTINGS

    client = anthropic.Anthropic(timeout=SETTINGS.anthropic_timeout_s)

    def write(question: str, context: str) -> str:
        response = client.messages.create(model=SETTINGS.writer_model, max_tokens=SETTINGS.eval_writer_max_tokens,
                                          output_config={"effort": "low"},
                                          messages=[{"role": "user", "content": ANSWER_PROMPT.format(context=context, question=question)}])
        return "".join(b.text for b in response.content if b.type == "text").strip()

    return write


def main() -> None:
    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher

    load_dotenv(ROOT / ".env")
    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)
    questions = [json.loads(line) for line in (ROOT / "data" / "knowledge_questions.jsonl").open()]
    working = [q for q in questions if q["set"] == "working"]
    out = ROOT / "data" / "results" / "retrieval"
    out.mkdir(parents=True, exist_ok=True)
    report = compare_modes(working, searcher)
    whole_kb = "\n\n".join(p.read_text() for p in sorted((ROOT / "data" / "kb_text").glob("*.md")))
    answer_both_ways(working, searcher, sonnet_writer(), whole_kb, out / "answers_to_grade.jsonl")
    (out / "summary.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k in ("questions", "coverage", "keyword", "combined")}, indent=1))


if __name__ == "__main__":
    main()
