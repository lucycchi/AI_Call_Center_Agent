"""Run test conversations on the separate test key (R12 to R17).

Run: python -m eval.run --set working [--cases T1,T2] [--limit N] [--name RUN] [--overwrite]
Writes data/results/<RUN>/attempts.jsonl and summary.json; a folder that already holds attempts is refused unless
--overwrite is given (never with --final). Conversations are graded by Codex and the database copy
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


class NoRetriesWithinCap:
    """The Anthropic client for test runs: a call given a timeout (the time left in the conversation, or the agent's
    message deadline cut to it) is made with no SDK retries, so a retry cannot run past the 60-second cap; a call
    with no timeout keeps the pinned retry setting."""

    def __init__(self, client):
        self._client = client
        self.messages = self

    def _for(self, kwargs: dict):
        return self._client.with_options(max_retries=0) if kwargs.get("timeout") is not None else self._client

    def create(self, **kwargs):
        return self._for(kwargs).messages.create(**kwargs)

    def stream(self, **kwargs):
        return self._for(kwargs).messages.stream(**kwargs)


def build_client(simulator: bool = False):
    """The test key's client. The simulated caller's calls get no SDK retries within the conversation cap; the agent's
    keep their retries, as in production, since each attempt already gets half the time left in its message deadline."""
    import anthropic

    from app.config import SETTINGS
    from app.core.model_log import RecordingClient
    from eval.budget import require_eval_key
    inner = anthropic.Anthropic(api_key=require_eval_key(), max_retries=SETTINGS.eval_retries, timeout=SETTINGS.anthropic_timeout_s)
    return RecordingClient(NoRetriesWithinCap(inner) if simulator else inner, sdk_version=f"anthropic {anthropic.__version__}")


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
            "retries": SETTINGS.eval_retries, "simulator_retries_within_cap": 0, "anthropic_timeout_s": SETTINGS.anthropic_timeout_s,
            "message_deadline_s": SETTINGS.message_deadline_s, "max_caller_turns": SETTINGS.eval_max_caller_turns,
            "conversation_seconds": SETTINGS.eval_conversation_seconds, "run_cap_usd": SETTINGS.eval_run_cap_usd,
            "grader": grader}


def check_results_folder(out: Path, overwrite: bool, final: bool) -> None:
    """A results folder that already holds attempts is never silently replaced: the run refuses unless --overwrite
    was given, and --overwrite is never allowed with --final."""
    if overwrite and final:
        raise SystemExit("refusing: --overwrite is never allowed with --final; the final run writes a new folder")
    if (out / "attempts.jsonl").exists() and not overwrite:
        raise SystemExit(f"refusing to start: {out} already holds attempts; choose another --name, or pass --overwrite "
                         "to replace them")


def run_graded(cases: list[dict], name: str, cap_usd: float | None = None, *, out: Path | None = None, factory=None,
               simulator_factory=None, runner=None, model: str | None = None, settings: dict | None = None,
               overwrite: bool = False):
    """First runs of every case, graded by Codex and the database together; one retry of each failed case, graded the
    same way; then the summary. Returns the attempts and the summary.

    Nothing finished is lost: each attempt is appended to attempts.jsonl (ungraded) and to ungraded-first.jsonl or
    ungraded-retry.jsonl the moment it ends, and attempts.jsonl is rewritten with grades after each grading batch;
    Codex's verdicts go to verdicts.jsonl. A conversation that crashes is recorded as errored and the run goes on; a
    grading failure still writes a partial summary (its extra names the failure) before it is raised, and
    resume_graded can finish the grading later. A results folder that already holds attempts is refused unless
    overwrite is set."""
    out = out or ROOT / "data" / "results" / name
    check_results_folder(out, overwrite, final=False)
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("attempts.jsonl", "verdicts.jsonl", "ungraded-first.jsonl", "ungraded-retry.jsonl"):
        (out / stale).unlink(missing_ok=True)
    return _graded_run(cases, out, cap_usd, factory, simulator_factory, runner, model, settings, saved=None)


def resume_graded(cases: list[dict], out: Path, cap_usd: float | None = None, *, factory=None, simulator_factory=None,
                  runner=None, model: str | None = None, settings: dict | None = None):
    """Finish a run whose conversations were saved but whose grading did not finish: the saved first attempts are
    graded (never run again), each failed case gets its one retry (a retry already saved is graded, not run again),
    and attempts.jsonl, verdicts.jsonl and summary.json are written as run_graded writes them. Grades already given
    are kept, not asked for again. Refuses, before anything runs, when a case has no saved first attempt, when an
    attempt was saved more than once, or when an attempt already has more than one verdict."""
    saved = load_saved_attempts(cases, out)
    if settings is None:
        settings = saved.settings
    return _graded_run(cases, out, cap_usd, factory, simulator_factory, runner, model, settings, saved=saved)


class SavedAttempts:
    """A results folder's saved attempts, as resume_graded needs them."""

    def __init__(self, firsts, retries, graded, settings, spent_usd):
        self.firsts, self.retries, self.graded = firsts, retries, graded  # graded: ids of attempts already graded
        self.settings, self.spent_usd = settings, spent_usd


def _attempt_from(line: dict):
    from dataclasses import fields

    from eval.harness import Attempt
    names = {f.name for f in fields(Attempt)}
    return Attempt(**{k: v for k, v in line.items() if k in names})


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def load_saved_attempts(cases: list[dict], out: Path) -> SavedAttempts:
    """The attempts saved in out, rebuilt exactly as they were saved. An attempt attempts.jsonl marks graded comes back
    with its grades; any other comes from ungraded-first.jsonl or ungraded-retry.jsonl, written the moment the
    conversation ended and before any grading touched it (attempts.jsonl's ungraded lines are the fallback)."""
    ids = [c["case_id"] for c in cases]
    listed = _read_lines(out / "attempts.jsonl")
    ungraded = {1: _read_lines(out / "ungraded-first.jsonl"), 2: _read_lines(out / "ungraded-retry.jsonl")}
    twice = sorted(k for k, n in _counts(f"{a['case_id']}|{a['attempt']}" for a in listed).items() if n > 1)
    for number, lines in ungraded.items():
        twice += sorted(k for k, n in _counts(f"{a['case_id']}|{number}" for a in lines).items() if n > 1)
    if twice:
        raise SystemExit(f"refusing to resume: in {out}, attempts were saved more than once: {sorted(set(twice))}")
    verdicts = _counts(v.get("id") for v in _read_lines(out / "verdicts.jsonl"))
    regraded = sorted(k for k, n in verdicts.items() if n > 1)
    if regraded:
        raise SystemExit(f"refusing to resume: {out}/verdicts.jsonl shows attempts already graded twice: {regraded}")
    by_key = {(a["case_id"], number): a for number, lines in ungraded.items() for a in lines}
    graded_keys = set()
    for line in listed:
        key = (line["case_id"], line["attempt"])
        if line.get("graded"):
            by_key[key] = line
            graded_keys.add(key)
        elif key not in by_key:
            by_key[key] = {**line, "grades": {}, "all_correct": None}
    unknown = sorted(f"{cid}|{n}" for cid, n in by_key if cid not in ids)
    if unknown:
        raise SystemExit(f"refusing to resume: {out} holds attempts {unknown} of cases not in this run")
    missing = [cid for cid in ids if (cid, 1) not in by_key]
    if missing:
        raise SystemExit(f"refusing to resume: no saved first attempt for {missing} in {out}; resuming never runs a "
                         "first attempt again")
    ungraded_verdict = sorted(f"{cid}|{n}" for cid, n in by_key if f"{cid}|{n}" in verdicts and (cid, n) not in graded_keys)
    if ungraded_verdict:
        raise SystemExit(f"refusing to resume: attempts {ungraded_verdict} have a verdict but are not marked graded; "
                         "grading them again would grade them twice")
    attempts = {key: _attempt_from(line) for key, line in by_key.items()}
    firsts = [attempts[(cid, 1)] for cid in ids]
    retries = [attempts[(cid, 2)] for cid in ids if (cid, 2) in attempts]
    for retry in retries:
        first = attempts[(retry.case_id, 1)]
        if (retry.case_id, 1) not in graded_keys or first.all_correct is not False or first.stopped == "error":
            raise SystemExit(f"refusing to resume: {retry.case_id} has a saved retry but its first attempt is not a "
                             "graded failure")
    settings = next((line.get("settings") for line in listed if line.get("settings")), None)
    return SavedAttempts(firsts, retries, {id(a) for key, a in attempts.items() if key in graded_keys}, settings,
                         sum(a.cost_usd for a in attempts.values()))


def _counts(values) -> dict:
    from collections import Counter
    return Counter(values)


def _graded_run(cases, out, cap_usd, factory, simulator_factory, runner, model, settings, saved: SavedAttempts | None):
    """The shared body of run_graded and resume_graded: first attempts (run, or saved), graded; one retry of each
    failed case, graded; the summary."""
    from dataclasses import asdict

    from app.config import SETTINGS
    from eval.budget import RunBudget
    from eval.grade_conversations import grade_attempts
    from eval.grader import grader_model, runner_for
    from eval.harness import attempt_line, run_case
    from eval.scoring import score

    if factory is None or simulator_factory is None:
        from eval.simulator import Simulator
        client, caller = build_client(), build_client(simulator=True)
        factory, simulator_factory = factory or engine_factory(client), simulator_factory or (lambda: Simulator(caller))
    budget, by_id = RunBudget(cap_usd or SETTINGS.eval_run_cap_usd), {c["case_id"]: c for c in cases}
    runner, model = runner or runner_for(budget), model or grader_model()
    settings = settings if settings is not None else run_settings(model)
    out.mkdir(parents=True, exist_ok=True)
    done, graded, stopped, failure = [], set(), False, None
    if saved is not None:  # the saved attempts' spend counts against the run's cap, as it did when they ran
        budget.spent_usd = saved.spent_usd
        done += saved.firsts + saved.retries
        graded |= saved.graded

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

    def keep_verdicts(verdicts, attempts):
        """Each grading batch is saved as it finishes: its verdicts appended, its attempts rewritten as graded."""
        with (out / "verdicts.jsonl").open("a") as handle:
            handle.write("".join(json.dumps({**asdict(v), "model": model}) + "\n" for v in verdicts))
        for a in attempts:
            a.grades["grader_model"] = model
        graded.update(id(a) for a in attempts)
        save()

    def grade_batch(batch):
        errored = [a for a in batch if a.stopped == "error"]
        for a in errored:  # a crashed conversation is a failure, and is not sent to Codex
            a.all_correct, a.grades["error"] = False, a.error
        cut = [a for a in batch if a.stopped == "budget"]
        for a in cut:  # cut off by the run's cap: not sent to Codex, not scored, not retried
            a.all_correct, a.grades["stopped"] = None, "budget"
        result = grade_attempts([a for a in batch if a.stopped not in ("error", "budget")], by_id, runner, model=model,
                                on_verdicts=keep_verdicts)
        graded.update(id(a) for a in batch)
        save()
        return result + errored + cut

    try:
        if saved is None:
            firsts = grade_batch(run_batch(cases, 1, "first"))
            retries_saved = {}
        else:
            stopped = any(a.stopped == "budget" for a in saved.firsts)
            firsts = [a for a in saved.firsts if id(a) in graded]
            firsts += grade_batch([a for a in saved.firsts if id(a) not in graded])
            retries_saved = {a.case_id: a for a in saved.retries}
        again = [by_id[a.case_id] for a in firsts if a.all_correct is False and a.stopped != "error"]
        if not stopped:
            waiting = [retries_saved[c["case_id"]] for c in again
                       if c["case_id"] in retries_saved and id(retries_saved[c["case_id"]]) not in graded]
            grade_batch(waiting + run_batch([c for c in again if c["case_id"] not in retries_saved], 2, "retry"))
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
        if saved is not None:
            summary.extra["resumed"] = True
        if failure:
            summary.extra["failed"] = failure
            summary.extra["partial"] = True  # not a finished run's summary; resume_graded replaces it
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
    parser.add_argument("--set", choices=["working", "held_out", "fresh"], default="working")
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--name", default="")
    parser.add_argument("--provisional", action="store_true", help="grade outcomes only, without Codex")
    parser.add_argument("--final", action="store_true", help="the final held-out measurement (checks the freeze hashes)")
    parser.add_argument("--fresh-final", action="store_true", help="the one run of this agent version on the frozen "
                        "fresh test set (eval/fresh_cases.py)")
    parser.add_argument("--resume", action="store_true", help="grade the saved conversations of the stopped run --name "
                        "(eval.run.resume_graded: first attempts are never run again)")
    parser.add_argument("--overwrite", action="store_true", help="replace the attempts already in the results folder "
                        "(never with --final)")
    args = parser.parse_args()
    if args.overwrite and args.final:
        check_results_folder(Path(), overwrite=True, final=True)
    if args.set == "fresh" and (args.limit or args.provisional or args.cases):
        raise SystemExit("refusing: a fresh run is the whole fresh set, graded; no --limit, --provisional or --cases")
    if args.set == "fresh":
        from eval import fresh_cases
        from eval.freeze import freeze_agent
        ids = args.cases.split(",") if args.cases else [s["case_id"] for s in fresh_cases.slots()]
        agent = freeze_agent(ROOT)
        fresh_cases.refuse(ids, args.fresh_final, agent)
        folder = ROOT / "data" / "testset_fresh"
    else:
        split = json.loads((ROOT / "data" / "split.json").read_text())
        ids = args.cases.split(",") if args.cases else split[args.set]
        refuse_held_out(ids, args.final)
        folder = ROOT / "data" / "testset"
    load_dotenv(ROOT / ".env")
    cases = [json.loads((folder / f"{cid}.json").read_text()) for cid in ids]
    if args.limit:
        cases = cases[:args.limit]
    out = ROOT / "data" / "results" / (args.name or f"{args.set}-{datetime.now():%Y%m%d-%H%M%S}")
    if not args.resume:
        check_results_folder(out, args.overwrite, args.final)
    if args.resume:
        _, summary = resume_graded(cases, out)
    elif args.provisional:
        client = build_client()
        summary = run_all(cases, engine_factory(client), lambda: Simulator(build_client(simulator=True)), RunBudget(SETTINGS.eval_run_cap_usd),
                          grade=provisional_grade, out=out, settings=run_settings(None))
    else:
        _, summary = run_graded(cases, out.name, overwrite=args.overwrite)
    if args.set == "fresh":
        fresh_cases.record_run(agent, out.name)  # counted: at most three runs per agent version
    print(json.dumps(summary.to_json(), indent=1))
    print(f"results in {out}")


if __name__ == "__main__":
    main()
