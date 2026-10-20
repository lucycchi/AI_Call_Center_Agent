"""Measure retrieval on its own (R30): recall and hit rate at five, coverage, and hit rate on the
stale-trap questions, for keyword-only, meaning-only and combined search; and answers from keyword-only
search, from combined search and from the whole current knowledge base in the prompt, written out for
grading on answer correctness (Task 19). Stale-trap accuracy proper is judged on those answers: did the
agent give the current fact rather than the old one. Here the report also checks that no excluded
document is in the index at all.

Run: python -m eval.retrieval_eval   (needs the built index and VOYAGE_API_KEY; answers need EVAL_ANTHROPIC_API_KEY)
     python -m eval.retrieval_eval --measures-only   (recomputes the retrieval measures; keeps the graded answers)
"""

import csv
import json
import os
from collections.abc import Callable
from pathlib import Path

from app.knowledge.index import DOCUMENT_LIST, Chunk

ROOT = Path(__file__).resolve().parent.parent
TOP = 5
ANSWER_MODES = ("keyword", "combined")


def excluded_documents(document_list: Path = DOCUMENT_LIST) -> set[str]:
    """Every document the document list keeps out of search: stale, placeholder, or not customer-facing."""
    return {row["path"] for row in csv.DictReader(document_list.open())
            if row["status"] != "current" or row["audience"] != "customers"}


EXCLUDED = tuple(sorted(excluded_documents()))


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


def coverage(questions: list[dict]) -> float | None:
    """Share of the knowledge questions callers ask under handled reasons that the current documents answer at all,
    weighted by how many calls each comes from (R30). Only questions taken from the test cases count: hand-written
    questions would let the measure move with how many were written."""
    asked = [q for q in questions if q.get("case_id") and q.get("handled_reason", True)]
    calls = sum(q.get("calls_weight", 1) for q in asked)
    return sum(q.get("calls_weight", 1) for q in asked if q["evidence_spans"]) / calls if calls else None


def stale_trap_passes(results: list[Chunk], needed: list[dict], k: int = TOP) -> bool:
    top = results[:k]
    return hit_at_k(top, needed) and not any(c.document.startswith(EXCLUDED) for c in top)


def compare_modes(questions: list[dict], searcher, question_set: str = "working") -> dict:
    asked = [q for q in questions if q.get("case_id") and q.get("handled_reason", True)]
    report: dict = {"set": question_set, "questions": len(questions), "coverage": coverage(questions),
                    "coverage_basis": f"{len(asked)} caller questions from {sum(q.get('calls_weight', 1) for q in asked)} calls",
                    "index_has_excluded_documents": any(c.document.startswith(EXCLUDED) for c in searcher.chunks)}
    answerable = [q for q in questions if q["evidence_spans"]]
    for mode in ("keyword", "meaning", "combined"):
        results = {q["qid"]: [s.chunk for s in searcher.search(q["question"], mode=mode, k=TOP)] for q in answerable}
        traps = [q for q in answerable if q["kind"] == "stale_trap"]
        report[mode] = {
            "recall_at_5": sum(recall_at_k(results[q["qid"]], q["evidence_spans"]) for q in answerable) / max(len(answerable), 1),
            "hit_at_5": sum(hit_at_k(results[q["qid"]], q["evidence_spans"]) for q in answerable) / max(len(answerable), 1),
            "stale_trap_hit_at_5": (sum(stale_trap_passes(results[q["qid"]], q["evidence_spans"]) for q in traps) / len(traps))
            if traps else None,
            "misses": [q["qid"] for q in answerable if not hit_at_k(results[q["qid"]], q["evidence_spans"])],
        }
    return report


def passage_label(chunk) -> str:
    return f"[{chunk.document}, {chunk.heading}, {chunk.effective_date or 'undated'}] {chunk.text}"


def answer_both_ways(questions: list[dict], searcher, writer: Callable[[str, str], str], whole_kb: str, out: Path,
                     model: str | None = None) -> None:
    """Answers from the top five keyword-only and combined passages and from the whole knowledge base, for grading."""
    partial = out.with_name(out.name + ".partial")  # replaces the previous answers only once every answer is written
    with partial.open("w") as handle:
        for q in questions:
            found = {mode: [s.chunk for s in searcher.search(q["question"], mode=mode, k=TOP)] for mode in ANSWER_MODES}
            contexts = [(mode, "\n\n".join(c.text for c in found[mode])) for mode in ANSWER_MODES] + [("whole_kb", whole_kb)]
            for mode, context in contexts:
                # The exact passages the answer was written from, so it is graded against them, not a later search.
                passages = [passage_label(c) for c in found.get(mode, [])]
                handle.write(json.dumps({"qid": q["qid"], "kind": q["kind"], "mode": mode, "question": q["question"],
                                         "answer": writer(q["question"], context), "model": model,
                                         "reference_answer": q.get("reference_answer"), "passages": passages}) + "\n")
    partial.replace(out)


ANSWER_PROMPT = """You answer customer questions for Meridian Home Comfort using ONLY the company documents below.
If the documents do not answer the question, say you will pass the question to a team member. Never guess.

Documents:
{context}

Question: {question}"""


def run_settings(answer_cost_usd: float | None) -> dict:
    """Everything that shaped a run: SDK versions, models, token and retry limits, timeouts, and the spending cap."""
    import anthropic
    import voyageai

    from app.config import SETTINGS
    from app.knowledge.embedder import VOYAGE_RETRIES

    return {"anthropic_sdk": anthropic.__version__, "voyage_sdk": voyageai.__version__,
            "embedding_model": SETTINGS.embedding_model, "voyage_input_type": "query", "voyage_timeout_s": SETTINGS.voyage_timeout_s,
            "voyage_retries": VOYAGE_RETRIES, "writer_model": SETTINGS.writer_model,
            "writer_max_tokens": SETTINGS.eval_writer_max_tokens, "writer_effort": WRITER_EFFORT, "retries": SETTINGS.eval_retries,
            "anthropic_timeout_s": SETTINGS.anthropic_timeout_s, "run_cap_usd": SETTINGS.eval_run_cap_usd, "top_k": TOP,
            "answer_cost_usd": answer_cost_usd}


class BudgetExceeded(RuntimeError):
    pass


WRITER_EFFORT = "low"


def sonnet_writer(cap_usd: float | None = None) -> Callable[[str, str], str]:
    """Sonnet with the separate test key, one retry, and a stop once the run's spend reaches the cap."""
    import anthropic

    from app.config import SETTINGS, cost_usd

    key = os.environ.get("EVAL_ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("EVAL_ANTHROPIC_API_KEY is not set; test runs never use the live key")
    cap = SETTINGS.eval_run_cap_usd if cap_usd is None else cap_usd
    client = anthropic.Anthropic(api_key=key, max_retries=SETTINGS.eval_retries, timeout=SETTINGS.anthropic_timeout_s)
    spent = [0.0]

    def write(question: str, context: str) -> str:
        if spent[0] >= cap:
            raise BudgetExceeded(f"test run stopped at ${spent[0]:.2f}, the ${cap:.2f} cap")
        response = client.messages.create(model=SETTINGS.writer_model, max_tokens=SETTINGS.eval_writer_max_tokens,
                                          output_config={"effort": WRITER_EFFORT},
                                          messages=[{"role": "user", "content": ANSWER_PROMPT.format(context=context, question=question)}])
        spent[0] += cost_usd(SETTINGS.writer_model, response.usage.input_tokens, response.usage.output_tokens)
        return "".join(b.text for b in response.content if b.type == "text").strip()

    write.spent = spent
    return write


def main(argv: list[str] | None = None) -> None:
    import sys

    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher

    measures_only = "--measures-only" in (sys.argv[1:] if argv is None else argv)
    load_dotenv(ROOT / ".env")
    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)
    questions = [json.loads(line) for line in (ROOT / "data" / "knowledge_questions.jsonl").open()]
    working = [q for q in questions if q["set"] == "working"]
    out = ROOT / "data" / "results" / "retrieval"
    out.mkdir(parents=True, exist_ok=True)
    report = compare_modes(working, searcher, "working")
    if measures_only:
        previous = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {}
        cost = previous.get("settings", {}).get("answer_cost_usd")
        report["answers"] = "kept from the previous run (answers_to_grade.jsonl)"
    else:
        from app.config import SETTINGS

        whole_kb = "\n\n".join(p.read_text() for p in sorted((ROOT / "data" / "kb_text").glob("*.md")))
        writer = sonnet_writer()
        answer_both_ways(working, searcher, writer, whole_kb, out / "answers_to_grade.jsonl", model=SETTINGS.writer_model)
        cost = round(writer.spent[0], 4)
    report["settings"] = run_settings(cost)
    (out / "summary.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k in ("set", "questions", "coverage", "coverage_basis", "keyword",
                                                               "meaning", "combined", "settings")}, indent=1))

if __name__ == "__main__":
    main()
