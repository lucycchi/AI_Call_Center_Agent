"""Run test conversations on the separate test key (R12 to R17).

Run: python -m eval.run --set working [--cases T1,T2] [--limit N] [--name RUN]
Writes data/results/<RUN>/attempts.jsonl and summary.json. Conversations are graded by Codex and the database copy
together; --provisional compares only the observed outcome with the expected one, without Codex."""

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def provisional_grade(attempt, case):
    """Outcome only: handed off when a handoff was expected, declined when a decline was, otherwise neither."""
    expected = case["expected_outcome"]
    if expected == "handed_off":
        attempt.all_correct = attempt.handed_off
    elif expected == "clean_decline":
        attempt.all_correct = attempt.clean_decline
    else:
        attempt.all_correct = not attempt.handed_off and not attempt.clean_decline
    attempt.grades["provisional"] = True
    return attempt


class CappedPipeline:
    """The agent pipeline with its message deadline cut to the time left in the test conversation, so one reply
    cannot run past the 60-second cap (the deadline also bounds every model call's timeout)."""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.base = pipeline.deadline_s

    def run(self, turn):
        from eval.harness import TIME_LEFT
        left = TIME_LEFT.get()
        self.pipeline.deadline_s = self.base if left is None else min(self.base, left)
        yield from self.pipeline.run(turn)


def engine_factory(client):
    from app.config import SETTINGS
    from app.core.engine import Engine
    from app.core.pipeline import AgentPipeline
    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher
    from app.ops.store import OpsStore
    from app.replies.money_check import MoneyCheck
    from app.replies.writer import write
    from app.routing.router import route

    chunks, embeddings = load_index(ROOT / "data" / "index")
    searcher = Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings)

    def build(db_path, ops_path):
        return Engine(CappedPipeline(AgentPipeline(
            store=OpsStore(ops_path), scheduling_db=db_path, seed_db=SETTINGS.seed_db_path, searcher=searcher,
            route_fn=lambda text, history: route(text, history, client),
            writer=lambda reply_type, facts, history: write(reply_type, facts, history, client),
            threshold=SETTINGS.retrieval_threshold, money_check=MoneyCheck(client))))
    return build


def build_client():
    import anthropic

    from app.config import SETTINGS
    from app.core.model_log import RecordingClient
    from eval.budget import require_eval_key
    return RecordingClient(anthropic.Anthropic(api_key=require_eval_key(), max_retries=SETTINGS.eval_retries,
                                               timeout=SETTINGS.anthropic_timeout_s), sdk_version=f"anthropic {anthropic.__version__}")


def run_settings(grader: str | None) -> dict:
    """The pinned models, SDK and settings of every part of a test run (R12), saved with each attempt and the summary."""
    import anthropic

    from app.config import SETTINGS
    return {"sdk_version": f"anthropic {anthropic.__version__}", "now": SETTINGS.now.isoformat(),
            "simulator": {"model": SETTINGS.writer_model, "max_tokens": SETTINGS.eval_simulator_max_tokens, "effort": "low"},
            "router": {"model": SETTINGS.router_model, "max_tokens": SETTINGS.router_max_tokens, "effort": "low"},
            "writer": {"model": SETTINGS.writer_model, "max_tokens": SETTINGS.eval_writer_max_tokens, "effort": "low"},
            "check": {"model": SETTINGS.router_model, "max_tokens": SETTINGS.router_max_tokens, "effort": "low"},
            "embedding_model": SETTINGS.embedding_model, "retrieval_threshold": SETTINGS.retrieval_threshold,
            "retries": SETTINGS.eval_retries, "anthropic_timeout_s": SETTINGS.anthropic_timeout_s,
            "message_deadline_s": SETTINGS.message_deadline_s, "max_caller_turns": SETTINGS.eval_max_caller_turns,
            "conversation_seconds": SETTINGS.eval_conversation_seconds, "run_cap_usd": SETTINGS.eval_run_cap_usd,
            "grader": grader}


def run_graded(cases: list[dict], name: str, cap_usd: float | None = None, *, out: Path | None = None, factory=None,
               simulator_factory=None, runner=None, model: str | None = None, settings: dict | None = None):
    """First runs of every case, graded by Codex and the database together; one retry of each failed case, graded the
    same way; then the summary. Returns the attempts and the summary.

    Nothing finished is lost: each attempt is appended to attempts.jsonl (ungraded) the moment it ends, and the file is
    rewritten with grades after each grading batch; Codex's verdicts go to verdicts.jsonl. A conversation that crashes
    is recorded as errored and the run goes on; a grading failure still writes a partial summary before it is raised."""
    from dataclasses import asdict

    from app.config import SETTINGS
    from eval.budget import RunBudget
    from eval.grade_conversations import grade_attempts
    from eval.grader import grader_model, runner_for
    from eval.harness import attempt_line, run_case
    from eval.scoring import score

    if factory is None or simulator_factory is None:
        from eval.simulator import Simulator
        client = build_client()
        factory, simulator_factory = factory or engine_factory(client), simulator_factory or (lambda: Simulator(client))
    runner, model = runner or runner_for(), model or grader_model()
    settings = settings if settings is not None else run_settings(model)
    out = out or ROOT / "data" / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("attempts.jsonl", "verdicts.jsonl", "ungraded-first.jsonl", "ungraded-retry.jsonl"):
        (out / stale).unlink(missing_ok=True)
    budget, by_id = RunBudget(cap_usd or SETTINGS.eval_run_cap_usd), {c["case_id"]: c for c in cases}
    done, graded, stopped, failure = [], set(), False, None

    def save():
        partial = out / "attempts.jsonl.partial"
        partial.write_text("".join(attempt_line(a, settings, id(a) in graded) for a in done))
        partial.replace(out / "attempts.jsonl")

    def run_batch(batch, attempt, label):
        nonlocal stopped
        finished = []
        for case in batch:
            if budget.spent_usd >= budget.cap_usd:
                stopped = True
                break
            result = run_case(case, factory, simulator_factory(), budget, out / "databases", attempt=attempt)
            done.append(result)
            finished.append(result)
            with (out / "attempts.jsonl").open("a") as handle:
                handle.write(attempt_line(result, settings, graded=False))
            with (out / f"ungraded-{label}.jsonl").open("a") as handle:
                handle.write(json.dumps(asdict(result)) + "\n")
            if result.stopped == "budget":
                stopped = True
                break
        return finished

    def keep_verdicts(verdicts):
        with (out / "verdicts.jsonl").open("a") as handle:
            handle.write("".join(json.dumps({**asdict(v), "model": model}) + "\n" for v in verdicts))

    def grade_batch(batch):
        errored = [a for a in batch if a.stopped == "error"]
        for a in errored:  # a crashed conversation is a failure, and is not sent to Codex
            a.all_correct, a.grades["error"] = False, a.error
        result = grade_attempts([a for a in batch if a.stopped != "error"], by_id, runner, model=model,
                                on_verdicts=keep_verdicts)
        for a in result:
            a.grades["grader_model"] = model
        graded.update(id(a) for a in batch)
        save()
        return result + errored

    try:
        firsts = grade_batch(run_batch(cases, 1, "first"))
        again = [by_id[a.case_id] for a in firsts if a.all_correct is False and a.stopped != "error"]
        if not stopped:
            grade_batch(run_batch(again, 2, "retry"))
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        save()
        summary = score(done, cases, stopped_at_budget=stopped)
        summary.extra.update({"spent_usd": round(budget.spent_usd, 4), "grader_model": model, "settings": settings,
                              "ticket_actionable": _share([a.grades.get("ticket_actionable") for a in done if a.attempt == 1]),
                              "errored": [a.case_id for a in done if a.stopped == "error"],
                              "ungraded": [f"{a.case_id}|{a.attempt}" for a in done if id(a) not in graded]})
        if failure:
            summary.extra["failed"] = failure
        (out / "summary.json").write_text(json.dumps(summary.to_json(), indent=1))
    return done, summary


def _share(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def refuse_held_out(ids: list[str], final: bool, root: Path = ROOT) -> None:
    """Held-out cases run only in the final measurement (R10, R21): with --final, the held-out cases unchanged since
    they were frozen, and the agent matching its freeze record."""
    from eval.freeze import freeze_agent
    from eval.split import freeze_hash
    split = json.loads((root / "data" / "split.json").read_text())
    held = sorted(set(ids) & set(split["held_out"]))
    if not held:
        return
    if not final:
        raise SystemExit(f"refusing to run held-out cases {held} without --final")
    if freeze_hash([root / "data" / "testset" / f"{cid}.json" for cid in split["held_out"]]) != split["held_out_hash"]:
        raise SystemExit("refusing: the held-out cases differ from their frozen hash in data/split.json")
    record = json.loads((root / "data" / "agent_freeze.json").read_text())
    if freeze_agent(root) != record["hash"]:
        raise SystemExit("refusing: the agent no longer matches its freeze record in data/agent_freeze.json")


def main() -> None:
    from dotenv import load_dotenv

    from app.config import SETTINGS
    from eval.budget import RunBudget
    from eval.harness import run_all
    from eval.simulator import Simulator

    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["working", "held_out"], default="working")
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--name", default="")
    parser.add_argument("--provisional", action="store_true", help="grade outcomes only, without Codex")
    parser.add_argument("--final", action="store_true", help="the final held-out measurement (checks the freeze hashes)")
    args = parser.parse_args()
    split = json.loads((ROOT / "data" / "split.json").read_text())
    ids = args.cases.split(",") if args.cases else split[args.set]
    refuse_held_out(ids, args.final)
    load_dotenv(ROOT / ".env")
    cases = [json.loads((ROOT / "data" / "testset" / f"{cid}.json").read_text()) for cid in ids]
    if args.limit:
        cases = cases[:args.limit]
    out = ROOT / "data" / "results" / (args.name or f"{args.set}-{datetime.now():%Y%m%d-%H%M%S}")
    if args.provisional:
        client = build_client()
        summary = run_all(cases, engine_factory(client), lambda: Simulator(client), RunBudget(SETTINGS.eval_run_cap_usd),
                          grade=provisional_grade, out=out, settings=run_settings(None))
    else:
        _, summary = run_graded(cases, out.name)
    print(json.dumps(summary.to_json(), indent=1))
    print(f"results in {out}")


if __name__ == "__main__":
    main()
