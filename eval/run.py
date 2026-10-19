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
        return Engine(AgentPipeline(store=OpsStore(ops_path), scheduling_db=db_path, seed_db=SETTINGS.seed_db_path,
                                    searcher=searcher, route_fn=lambda text, history: route(text, history, client),
                                    writer=lambda reply_type, facts, history: write(reply_type, facts, history, client),
                                    threshold=SETTINGS.retrieval_threshold, money_check=MoneyCheck(client)))
    return build


def run_graded(cases: list[dict], name: str, cap_usd: float | None = None):
    """First runs of every case, graded by Codex and the database together in batches; one retry of each failed case,
    graded the same way; then the summary. Returns the attempts and the summary."""
    import anthropic
    from dataclasses import asdict

    from app.config import SETTINGS
    from app.core.model_log import RecordingClient
    from eval.budget import BudgetExceeded, RunBudget, require_eval_key
    from eval.grade_conversations import grade_attempts
    from eval.grader import grader_model, runner_for
    from eval.harness import run_case
    from eval.scoring import score
    from eval.simulator import Simulator

    client = RecordingClient(anthropic.Anthropic(api_key=require_eval_key(), max_retries=SETTINGS.eval_retries,
                                                 timeout=SETTINGS.anthropic_timeout_s), sdk_version=f"anthropic {anthropic.__version__}")
    out = ROOT / "data" / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    budget, factory, by_id = RunBudget(cap_usd or SETTINGS.eval_run_cap_usd), engine_factory(client), {c["case_id"]: c for c in cases}
    stopped = False

    def run_all_once(batch, attempt):
        nonlocal stopped
        done = []
        for case in batch:
            try:
                budget.check()
            except BudgetExceeded:
                stopped = True
                break
            result = run_case(case, factory, Simulator(client), budget, out / "databases", attempt=attempt)
            done.append(result)
            if result.stopped == "budget":
                stopped = True
                break
        return done

    runner, model = runner_for(), grader_model()

    def codex(prompt):
        return runner(prompt)
    firsts = grade_attempts(run_all_once(cases, 1), by_id, codex)
    retries = grade_attempts(run_all_once([by_id[a.case_id] for a in firsts if a.all_correct is False], 2), by_id, codex) \
        if not stopped else []
    attempts = firsts + retries
    for a in attempts:
        a.grades["grader_model"] = model
    with (out / "attempts.jsonl").open("w") as handle:
        for a in attempts:
            handle.write(json.dumps({**asdict(a), "first_run": a.attempt == 1}) + "\n")
    summary = score(attempts, cases, stopped_at_budget=stopped)
    summary.extra.update({"spent_usd": round(budget.spent_usd, 4), "grader_model": model,
                          "ticket_actionable": _share([a.grades.get("ticket_actionable") for a in firsts])})
    (out / "summary.json").write_text(json.dumps(summary.to_json(), indent=1))
    return attempts, summary


def _share(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def main() -> None:
    import anthropic
    from dotenv import load_dotenv

    from app.config import SETTINGS
    from app.core.model_log import RecordingClient
    from eval.budget import RunBudget, require_eval_key
    from eval.harness import run_all
    from eval.simulator import Simulator

    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["working", "held_out"], default="working")
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--name", default="")
    parser.add_argument("--provisional", action="store_true", help="grade outcomes only, without Codex")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    key = require_eval_key()
    client = RecordingClient(anthropic.Anthropic(api_key=key, max_retries=SETTINGS.eval_retries,
                                                 timeout=SETTINGS.anthropic_timeout_s), sdk_version=f"anthropic {anthropic.__version__}")
    split = json.loads((ROOT / "data" / "split.json").read_text())
    ids = args.cases.split(",") if args.cases else split[args.set]
    cases = [json.loads((ROOT / "data" / "testset" / f"{cid}.json").read_text()) for cid in ids]
    if args.limit:
        cases = cases[:args.limit]
    out = ROOT / "data" / "results" / (args.name or f"{args.set}-{datetime.now():%Y%m%d-%H%M%S}")
    if args.provisional:
        summary = run_all(cases, engine_factory(client), lambda: Simulator(client), RunBudget(SETTINGS.eval_run_cap_usd),
                          grade=provisional_grade, out=out)
    else:
        _, summary = run_graded(cases, out.name)
    print(json.dumps(summary.to_json(), indent=1))
    print(f"results in {out}")


if __name__ == "__main__":
    main()
