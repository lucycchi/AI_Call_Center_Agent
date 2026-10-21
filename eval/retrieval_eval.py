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
from eval.budget import BudgetExceeded  # one stop for every paid test run

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


META = "answers_meta.json"  # beside the answers: the agent hash they were written under and the answers' own hash


def file_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer_both_ways(questions: list[dict], searcher, writer: Callable[[str, str], str], whole_kb: str, out: Path,
                     model: str | None = None, agent_hash: str | None = None,
                     agent_answer: Callable[[str], tuple[str, list[str]]] | None = None, budget=None) -> None:
    """Answers from the top five keyword-only and combined passages and from the whole knowledge base, for grading.
    With agent_answer, the combined answers are the agent's own (its knowledge flow, writer and checks), so the answer
    measures and the threshold curve describe the agent, stored with the passages the agent's flow used; keyword-only and whole-knowledge-base answers keep the simple
    prompt, a comparison of search methods (R30).
    With agent_hash, answers_meta.json beside them records that hash and the answers file's own hash, so grading can
    refuse answers written under another agent. With budget (the run's one RunBudget, which the simple-prompt writer
    and the agent's own calls both spend from), the run stops with BudgetExceeded after the answer that crosses the
    cap, and the previous answers stay as they were."""
    partial = out.with_name(out.name + ".partial")  # replaces the previous answers only once every answer is written
    with partial.open("w") as handle:
        for q in questions:
            found = {mode: [s.chunk for s in searcher.search(q["question"], mode=mode, k=TOP)] for mode in ANSWER_MODES}
            contexts = [(mode, "\n\n".join(c.text for c in found[mode])) for mode in ANSWER_MODES] + [("whole_kb", whole_kb)]
            for mode, context in contexts:
                # The exact passages the answer was written from, so it is graded against them, not a later search.
                passages = [passage_label(c) for c in found.get(mode, [])]
                by_agent = agent_answer is not None and mode == "combined"
                if by_agent:
                    reply, passages = agent_answer(q["question"])
                else:
                    reply = writer(q["question"], context)
                if budget is not None and budget.crossed:
                    raise BudgetExceeded(f"retrieval run stopped at ${budget.spent_usd:.2f}, the ${budget.cap_usd:.2f} cap; "
                                         "the previous answers are kept")
                # The agent's reply ended in its handoff: a handoff at any threshold, never contained or wrong (R32).
                handoff = {"handed_off": AGENT_HANDOFF in reply} if by_agent else {}
                handle.write(json.dumps({"qid": q["qid"], "kind": q["kind"], "mode": mode, "question": q["question"],
                                         "answer": reply, "writer": "agent" if by_agent else "simple prompt", "model": model,
                                         "reference_answer": q.get("reference_answer"), "passages": passages, **handoff}) + "\n")
    partial.replace(out)
    if agent_hash is not None:
        from datetime import datetime
        (out.parent / META).write_text(json.dumps({"agent_hash": agent_hash, "answers_sha256": file_sha256(out),
                                                   "answers": out.name, "model": model,
                                                   "written_at": datetime.now().isoformat(timespec="seconds")}, indent=1))


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


def agent_hash() -> str:
    """The agent the answers are filed under: its freeze hash without the retrieval threshold (eval/freeze.py)."""
    from eval import freeze
    return freeze.answers_hash()


WRITER_EFFORT = "low"


AGENT_HANDOFF = "I'll pass your question to a team member, who will follow up."


def agent_answerer(searcher, client, money_check) -> Callable[[str], tuple[str, list[str]]]:
    """The agent's own answer to a knowledge question and the passages its flow used: its knowledge flow picks the
    facts and reply type (with the threshold at 0, so the curve can apply each threshold afterwards), its writer
    writes, and its sentence checks release each sentence; a blocked sentence or the writer's not-in-documents marker
    ends the reply with a handoff, as in the pipeline."""
    from app.flows.knowledge import answer
    from app.replies.checks import CheckedStream
    from app.replies.writer import write

    def ask(question: str) -> tuple[str, list[str]]:
        result = answer(question, searcher, 0.0)
        passages = [passage_label(c) for c in result.chunks]
        if result.reply_type == "handoff":
            return AGENT_HANDOFF, passages
        stream = CheckedStream(write(result.reply_type, result.facts, [{"role": "caller", "content": question}], client),
                               money_check=money_check)
        released = list(stream)
        return " ".join(released + ([AGENT_HANDOFF] if stream.blocked_rule or stream.not_in_documents else [])), passages
    return ask


def sonnet_writer(cap_usd: float | None = None, budget=None) -> Callable[[str, str], str]:
    """Sonnet with the separate test key, one retry, and a stop once the run's spend reaches the cap. With budget, it
    spends from the run's one RunBudget, shared with the agent's own calls, so the run has a single cap."""
    import anthropic

    from app.config import SETTINGS, cost_usd

    key = os.environ.get("EVAL_ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("EVAL_ANTHROPIC_API_KEY is not set; test runs never use the live key")
    if budget is None:
        from eval.budget import RunBudget
        budget = RunBudget(SETTINGS.eval_run_cap_usd if cap_usd is None else cap_usd)
    client = anthropic.Anthropic(api_key=key, max_retries=SETTINGS.eval_retries, timeout=SETTINGS.anthropic_timeout_s)

    def write(question: str, context: str) -> str:
        if budget.spent_usd >= budget.cap_usd:
            raise BudgetExceeded(f"test run stopped at ${budget.spent_usd:.2f}, the ${budget.cap_usd:.2f} cap")
        response = client.messages.create(model=SETTINGS.writer_model, max_tokens=SETTINGS.eval_writer_max_tokens,
                                          output_config={"effort": WRITER_EFFORT},
                                          messages=[{"role": "user", "content": ANSWER_PROMPT.format(context=context, question=question)}])
        usd = cost_usd(SETTINGS.writer_model, response.usage.input_tokens, response.usage.output_tokens)
        budget.record("eval writer", SETTINGS.writer_model, anthropic.__version__, {}, response.usage.input_tokens,
                      response.usage.output_tokens, 0, round(usd * 1_000_000))
        return "".join(b.text for b in response.content if b.type == "text").strip()

    write.budget = budget
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
        from app.core.model_log import SINK
        from app.replies.money_check import MoneyCheck
        from eval.budget import RunBudget
        from eval.run import build_client
        budget = RunBudget(SETTINGS.eval_run_cap_usd)  # one cap for the simple-prompt writer and the agent together
        client, writer = build_client(), sonnet_writer(budget=budget)
        token = SINK.set(budget.record)  # the agent's own calls (writer and money check) count against the cap
        try:
            answer_both_ways(working, searcher, writer, whole_kb, out / "answers_to_grade.jsonl", model=SETTINGS.writer_model,
                             agent_hash=agent_hash(), agent_answer=agent_answerer(searcher, client, MoneyCheck(client)),
                             budget=budget)
        finally:
            SINK.reset(token)
        cost = round(budget.spent_usd, 4)
    report["settings"] = run_settings(cost)
    (out / "summary.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k in ("set", "questions", "coverage", "coverage_basis", "keyword",
                                                               "meaning", "combined", "settings")}, indent=1))

if __name__ == "__main__":
    main()
