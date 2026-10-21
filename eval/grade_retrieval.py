"""Grade the retrieval answers (R30, R31): answers from keyword-only search, combined search and the whole knowledge
base, scored pass or fail on correctness, faithfulness, citation accuracy and correct refusal.

Run: python -m eval.grade_retrieval   (runs Codex; tell the author first)
Writes data/results/retrieval/verdicts.jsonl (each batch to verdicts.jsonl.partial as it is graded; the full file
is replaced only once every batch is in) and answer_scores.json. Refuses answers written under another agent
(answers_meta.json records the agent hash, the freeze hash without the retrieval threshold: eval.freeze.answers_hash),
and keeps each graded answer set under runs/<agent hash>/ only once."""

import json
from pathlib import Path

from eval.grader import Verdict, grade, grader_model, runner_for

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


def answers_to_grade(results: Path, agent_hash: str) -> tuple[list[dict], dict]:
    """The answers to grade and their record, refusing answers written under an agent other than the current one,
    answers with no record of their agent, and answers changed since the record was written."""
    from eval.retrieval_eval import META, file_sha256
    answers_path, meta_path = results / "answers_to_grade.jsonl", results / META
    if not meta_path.exists():
        raise SystemExit(f"refusing to grade: {meta_path} is missing, so the agent the answers came from is unknown; "
                         "run eval.retrieval_eval again to write fresh answers")
    meta = json.loads(meta_path.read_text())
    if meta.get("agent_hash") != agent_hash:
        raise SystemExit(f"refusing to grade: the answers were written under agent {meta.get('agent_hash')}, but the "
                         f"agent is now {agent_hash}; run eval.retrieval_eval again")
    if meta.get("answers_sha256") != file_sha256(answers_path):
        raise SystemExit(f"refusing to grade: {answers_path} changed after {META} was written")
    return [json.loads(line) for line in answers_path.open()], meta


def agent_hash() -> str:
    """The agent retrieval answers are filed under: the freeze hash without the retrieval threshold."""
    from eval import freeze
    return freeze.answers_hash()


def grade_and_save(items: list[dict], runner, model: str, results: Path) -> list[Verdict]:
    """Grades in batches, appending each finished batch to verdicts.jsonl.partial; verdicts.jsonl is replaced only
    once every batch is graded, so a failure keeps the finished batches and the previous complete verdicts."""
    from dataclasses import asdict
    partial = results / "verdicts.jsonl.partial"
    partial.write_text("")

    def keep(verdicts):
        with partial.open("a") as handle:
            handle.write("".join(json.dumps(asdict(v)) + "\n" for v in verdicts))
    verdicts = grade(items, runner, model, on_batch=keep)
    partial.replace(results / "verdicts.jsonl")
    return verdicts


ANSWERS_HASH = "answers_sha256"  # in each kept run: the hash of the answers it graded


def keep_run(results: Path, agent_hash: str) -> Path | None:
    """A copy of this graded run under the agent its answers were written under, so later runs add to it rather than
    replace it. The same answer set is kept only once: if a kept run of this agent already graded identical answers,
    nothing is kept and None is returned."""
    import shutil

    from eval.retrieval_eval import file_sha256
    runs = results / "runs" / agent_hash
    runs.mkdir(parents=True, exist_ok=True)
    digest = file_sha256(results / "answers_to_grade.jsonl")
    if any(run_answers_hash(d) == digest for d in runs.iterdir() if d.is_dir()):
        print(f"not kept: a run of agent {agent_hash} already graded these answers ({digest[:12]})")
        return None
    folder = runs / str(len([d for d in runs.iterdir() if d.is_dir()]) + 1)
    folder.mkdir()
    for name in ("answers_to_grade.jsonl", "verdicts.jsonl"):
        shutil.copy(results / name, folder / name)
    (folder / ANSWERS_HASH).write_text(digest + "\n")
    return folder


def run_answers_hash(folder: Path) -> str | None:
    """The hash of the answers a kept run graded: stored with it, or worked out from its copy for older runs."""
    from eval.retrieval_eval import file_sha256
    if (folder / ANSWERS_HASH).exists():
        return (folder / ANSWERS_HASH).read_text().strip()
    return file_sha256(folder / "answers_to_grade.jsonl") if (folder / "answers_to_grade.jsonl").exists() else None


def main() -> None:
    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher

    answers, meta = answers_to_grade(RESULTS, agent_hash())  # refuses before anything is called
    load_dotenv(ROOT / ".env")
    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)
    items = answer_items(answers, searcher)
    verdicts = grade_and_save(items, runner_for(), grader_model(), RESULTS)
    keep_run(RESULTS, meta["agent_hash"])
    scores = answer_scores(items, verdicts)
    scores["grader_model"] = grader_model()
    scores["passages_searched_again"] = sum(1 for i in items if i.get("passages_searched_again"))
    scores["grader_reported_model"] = sorted({v.reported_model for v in verdicts})
    (RESULTS / "answer_scores.json").write_text(json.dumps(scores, indent=1))
    print(json.dumps(scores, indent=1))


if __name__ == "__main__":
    main()
