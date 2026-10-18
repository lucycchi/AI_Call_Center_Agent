"""Run test conversations on the separate test key (R12 to R17).

Run: python -m eval.run --set working [--cases T1,T2] [--limit N] [--name RUN]
Writes data/results/<RUN>/attempts.jsonl and summary.json. Until the Codex grader (Task 19) exists, grading is
provisional: the observed outcome is compared with the expected outcome only."""

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
    summary = run_all(cases, engine_factory(client), lambda: Simulator(client), RunBudget(SETTINGS.eval_run_cap_usd),
                      grade=provisional_grade, out=out)
    print(json.dumps(summary.to_json(), indent=1))
    print(f"results in {out}")


if __name__ == "__main__":
    main()
