"""The offline test run (R12, R13): each case on its own fresh copy of the seed database, with a simulated caller,
inside the run's budget. Every conversation is saved; a failed case is run once more."""

import contextvars
import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import SETTINGS
from app.core.model_log import SINK
from app.core.types import DoneEvent, SentenceEvent, Turn
from eval.budget import BudgetExceeded, RunBudget
from eval.fixtures import apply_fixtures
from eval.scoring import Summary, score

# Seconds left in the conversation while the agent answers; the eval engine caps its message deadline to it.
TIME_LEFT: contextvars.ContextVar[float | None] = contextvars.ContextVar("conversation_time_left", default=None)


@dataclass
class Attempt:
    case_id: str
    attempt: int = 1
    handed_off: bool = False
    clean_decline: bool = False
    all_correct: bool | None = None  # set by grading: the behaviour was right for the case
    first_route: str | None = None
    grades: dict = field(default_factory=dict)
    conversation: list[dict] = field(default_factory=list)
    done_events: list[dict] = field(default_factory=list)
    tickets: list[int] = field(default_factory=list)
    db_path: str | None = None
    stopped: str | None = None  # the caller ended, turn limit, time limit, budget or error
    seconds: float = 0.0
    cost_usd: float = 0.0
    conversation_id: str | None = None
    error: str | None = None
    models: dict = field(default_factory=dict)  # each purpose's model id, SDK version and settings, as called


def _remove(path: Path) -> None:
    for extra in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), path.with_suffix(".pending.jsonl")):
        extra.unlink(missing_ok=True)


def run_case(case: dict, engine_factory, simulator, budget: RunBudget, folder: Path, attempt: int = 1,
             clock=time.monotonic) -> Attempt:
    """One conversation: a fresh copy of the seed with the case's fixtures and a fresh operations database, then
    caller and agent turns. The 60-second cap holds during calls too: the caller's model call and the agent's
    message deadline get only the time left, and a reply still running at the cap is cut off."""
    folder.mkdir(parents=True, exist_ok=True)
    db, ops = folder / f"{case['case_id']}-{attempt}.sqlite", folder / f"{case['case_id']}-{attempt}-ops.sqlite"
    _remove(db)
    _remove(ops)
    shutil.copy(SETTINGS.seed_db_path, db)
    apply_fixtures(db, case["fixtures"])
    result = Attempt(case["case_id"], attempt, db_path=str(db), conversation_id=uuid.uuid4().hex)
    started, spent_before = clock(), budget.spent_usd
    cap = SETTINGS.eval_conversation_seconds

    def record(purpose, model_id, sdk_version, settings, *usage):
        entry = {"model_id": model_id, "sdk_version": sdk_version, "settings": settings}
        if entry not in result.models.setdefault(purpose, []):
            result.models[purpose].append(entry)
        budget.record(purpose, model_id, sdk_version, settings, *usage)
    token = SINK.set(record)
    try:
        engine = engine_factory(db, ops)
        while not result.stopped:
            if sum(m["role"] == "caller" for m in result.conversation) >= SETTINGS.eval_max_caller_turns:
                result.stopped = "turn limit"
                break
            if cap - (clock() - started) <= 0:
                result.stopped = "time limit"
                break
            budget.check()
            line = simulator.next(case, result.conversation, timeout=cap - (clock() - started))
            if not line:
                result.stopped = "caller ended"
                break
            result.conversation.append({"role": "caller", "text": line})
            left = cap - (clock() - started)
            if left <= 0:
                result.stopped = "time limit"
                break
            limit = TIME_LEFT.set(left)
            try:
                for event in engine.handle(Turn(result.conversation_id, "eval", uuid.uuid4().hex, line)):
                    if isinstance(event, SentenceEvent):
                        result.conversation.append({"role": "agent", "text": event.text})
                    elif isinstance(event, DoneEvent):
                        result.done_events.append(asdict(event))
                        if result.first_route is None and event.route not in ("none", "safety", "limit"):
                            result.first_route = event.route
                        if event.ticket:
                            result.tickets.append(event.ticket)
                        result.handed_off = result.handed_off or event.outcome in ("handed_off", "safety", "error", "limit")
                        result.clean_decline = result.clean_decline or event.outcome == "declined"
                    if clock() - started >= cap:
                        result.stopped = "time limit"
                        break
            finally:
                TIME_LEFT.reset(limit)
    except BudgetExceeded:
        result.stopped = "budget"
    except Exception as error:  # a crash is recorded with the attempt, never lost
        result.stopped, result.error = "error", f"{type(error).__name__}: {error}"
    finally:
        SINK.reset(token)
    result.seconds, result.cost_usd = clock() - started, budget.spent_usd - spent_before
    return result


def attempt_line(a: Attempt, settings: dict | None = None, graded: bool = True) -> str:
    return json.dumps({**asdict(a), "first_run": a.attempt == 1, "graded": graded, "settings": settings or {}}) + "\n"


def run_all(cases: list[dict], engine_factory, simulator_factory, budget: RunBudget, grade, out: Path,
            human: dict | None = None, settings: dict | None = None) -> Summary:
    """Every case's first run, then one retry of each failed case. Each attempt is written to out as it finishes, and
    the summary is written even when the run stops early or fails."""
    out.mkdir(parents=True, exist_ok=True)
    attempts: list[Attempt] = []
    stopped, failure = False, None
    with (out / "attempts.jsonl").open("w") as handle:
        def keep(a: Attempt) -> Attempt:
            handle.write(attempt_line(a, settings))
            handle.flush()
            attempts.append(a)
            return a

        def graded(a: Attempt, case: dict) -> Attempt:
            if a.stopped == "error":
                a.all_correct = False
                return a
            return grade(a, case)

        try:
            for case in cases:
                try:
                    budget.check()
                except BudgetExceeded:
                    stopped = True
                    break
                first = keep(graded(run_case(case, engine_factory, simulator_factory(), budget, out / "databases"), case))
                if first.stopped == "budget":
                    stopped = True
                    break
                if first.all_correct is False and first.stopped != "error":
                    second = keep(graded(run_case(case, engine_factory, simulator_factory(), budget, out / "databases",
                                                  attempt=2), case))
                    if second.stopped == "budget":
                        stopped = True
                        break
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
            raise
        finally:
            summary = score(attempts, cases, human=human, stopped_at_budget=stopped)
            summary.extra.update({"spent_usd": round(budget.spent_usd, 4), "settings": settings or {},
                                  "errored": [a.case_id for a in attempts if a.stopped == "error"]})
            if failure:
                summary.extra["failed"] = failure
            (out / "summary.json").write_text(json.dumps(summary.to_json(), indent=1))
    return summary
