"""The offline test run (R12, R13): each case on its own fresh copy of the seed database, with a simulated caller,
inside the run's budget. Every conversation is saved; a failed case is run once more."""

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
    stopped: str | None = None  # the caller ended, turn limit, time limit or budget
    seconds: float = 0.0
    cost_usd: float = 0.0


def run_case(case: dict, engine_factory, simulator, budget: RunBudget, folder: Path, attempt: int = 1,
             clock=time.monotonic) -> Attempt:
    """One conversation: a fresh copy of the seed with the case's fixtures, then caller and agent turns."""
    folder.mkdir(parents=True, exist_ok=True)
    db = folder / f"{case['case_id']}-{attempt}.sqlite"
    shutil.copy(SETTINGS.seed_db_path, db)
    apply_fixtures(db, case["fixtures"])
    engine = engine_factory(db, folder / f"{case['case_id']}-{attempt}-ops.sqlite")
    result = Attempt(case["case_id"], attempt, db_path=str(db))
    started, spent_before, conversation_id = clock(), budget.spent_usd, uuid.uuid4().hex
    token = SINK.set(budget.record)
    try:
        while True:
            if sum(m["role"] == "caller" for m in result.conversation) >= SETTINGS.eval_max_caller_turns:
                result.stopped = "turn limit"
                break
            if clock() - started >= SETTINGS.eval_conversation_seconds:
                result.stopped = "time limit"
                break
            budget.check()
            line = simulator.next(case, result.conversation)
            if not line:
                result.stopped = "caller ended"
                break
            result.conversation.append({"role": "caller", "text": line})
            for event in engine.handle(Turn(conversation_id, "eval", uuid.uuid4().hex, line)):
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
    except BudgetExceeded:
        result.stopped = "budget"
    finally:
        SINK.reset(token)
    result.seconds, result.cost_usd = clock() - started, budget.spent_usd - spent_before
    return result


def run_all(cases: list[dict], engine_factory, simulator_factory, budget: RunBudget, grade, out: Path,
            human: dict | None = None) -> Summary:
    """Every case's first run, then one retry of each failed case; attempts and the summary are written to out."""
    out.mkdir(parents=True, exist_ok=True)
    attempts: list[Attempt] = []
    stopped = False
    with (out / "attempts.jsonl").open("w") as handle:
        def keep(a: Attempt) -> Attempt:
            handle.write(json.dumps({**asdict(a), "first_run": a.attempt == 1}) + "\n")
            handle.flush()
            attempts.append(a)
            return a

        for case in cases:
            try:
                budget.check()
            except BudgetExceeded:
                stopped = True
                break
            first = keep(grade(run_case(case, engine_factory, simulator_factory(), budget, out / "databases"), case))
            if first.stopped == "budget":
                stopped = True
                break
            if first.all_correct is False:
                second = grade(run_case(case, engine_factory, simulator_factory(), budget, out / "databases", attempt=2), case)
                keep(second)
                if second.stopped == "budget":
                    stopped = True
                    break
    summary = score(attempts, cases, human=human, stopped_at_budget=stopped)
    summary.extra["spent_usd"] = round(budget.spent_usd, 4)
    (out / "summary.json").write_text(json.dumps(summary.to_json(), indent=1))
    return summary
