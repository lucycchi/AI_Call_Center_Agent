"""Grading through Codex (R18, D15): batches of 20 items per `codex exec` run, each returning a JSON verdict with the
model name; an API fallback is switched on by hand (GRADER_BACKEND=api). The grading prompt and its rubric are in
eval/grader_prompt.md, and every verdict is written out."""

import json
import re
import os
import random
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT = (Path(__file__).parent / "grader_prompt.md").read_text().strip()
BATCH = 20
CODEX_MODEL = os.environ.get("GRADER_CODEX_MODEL", "gpt-5.6-sol")  # the per-run override; the configured model fails here


class GraderError(RuntimeError):
    pass


@dataclass
class Verdict:
    id: str
    correct: bool | None = None
    faithful: bool | None = None
    citation_ok: bool | None = None
    refusal_ok: bool | None = None
    ticket_actionable: bool | None = None
    knowledge_correct: bool | None = None
    lookup_correct: bool | None = None
    requests: list = field(default_factory=list)
    why: str = ""
    model: str = "unknown"  # the model the grading command was given
    reported_model: str = ""  # the name the model gave for itself, which is not reliable


def _flag(value):
    """A "partial" verdict fails; anything else that is not true or false is unknown."""
    if value == "partial":
        return False
    return value if isinstance(value, bool) else None


def _verdict(raw: dict) -> Verdict:
    return Verdict(id=raw["id"], correct=_flag(raw.get("correct")), faithful=_flag(raw.get("faithful")),
                   citation_ok=_flag(raw.get("citation_ok")), refusal_ok=_flag(raw.get("refusal_ok")),
                   ticket_actionable=_flag(raw.get("ticket_actionable")), knowledge_correct=_flag(raw.get("knowledge_correct")),
                   lookup_correct=_flag(raw.get("lookup_correct")),
                   requests=[{"request": r.get("request", ""), "correct": _flag(r.get("correct"))} for r in raw.get("requests") or []],
                   why=raw.get("why", ""), model=raw.get("model", "unknown"), reported_model=raw.get("model", ""))


def grade(items: list[dict], runner, model: str | None = None, on_batch=None) -> list[Verdict]:
    """Batches of 20; on_batch receives each batch's verdicts as soon as that batch is graded, so a failure in a later
    batch loses nothing already graded."""
    verdicts = []
    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        raw = runner(f"{PROMPT}\n\nITEMS:{json.dumps(batch)}")
        try:
            answers = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        except ValueError as error:
            raise GraderError(f"the grader did not return a JSON list: {raw[:120]!r}") from error
        by_id = {a.get("id"): a for a in answers}
        missing = [i["id"] for i in batch if i["id"] not in by_id]
        if missing:
            raise GraderError(f"the grader returned no verdict for {missing}")
        done = [_verdict(by_id[i["id"]]) for i in batch]
        if model:
            for verdict in done:
                verdict.model = model
        verdicts += done
        if on_batch:
            on_batch(done)
    return verdicts


def write_verdicts(verdicts: list[Verdict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(asdict(v)) + "\n" for v in verdicts))


def codex_command(prompt: str, out: str) -> list[str]:
    return ["codex", "exec", "-m", CODEX_MODEL, "-s", "read-only", "--ephemeral", "-o", out, prompt]


BUSY = re.compile(r"capacity|429|too many requests|rate limit", re.I)


def codex_runner(prompt: str, attempts: int = 5, wait_s: float = 120) -> str:
    """One Codex run; when the model is at capacity or rate-limited, wait and try again (up to five tries, two minutes apart)."""
    for attempt in range(1, attempts + 1):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "verdicts.txt"
            result = subprocess.run(codex_command(prompt, str(out)), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                    timeout=900)
            if out.exists() and out.read_text().strip():
                return out.read_text()
            errors = [line for line in (result.stdout + result.stderr).splitlines() if "ERROR" in line]
            message = errors[-1] if errors else "no error message"
        if not BUSY.search(message) or attempt == attempts:
            raise GraderError(f"Codex returned no verdicts: {message}")
        time.sleep(wait_s)
    raise GraderError("Codex returned no verdicts")


_API_BUDGET = []  # one run budget for fallback grading calls made outside a conversation run
MAX_OUTPUT_TOKENS = 32_000  # the most a fallback grading call may write; GRADER_MAX_OUTPUT_TOKENS overrides it


def input_token_estimate(prompt: str) -> int:
    """A generous count of the prompt's tokens (one per three bytes; English runs nearer four), for the cost check."""
    return len(prompt.encode()) // 3 + 1


def api_runner(prompt: str, budget=None, client=None) -> str:
    """The fallback when Codex is unavailable: the OpenAI API with GRADER_MODEL, switched on by hand, under the run's
    $8 cap. GRADER_PRICES_PER_MILLION ("input,output" US dollars) prices each call; without it the call is refused.
    Before each call the most it could cost (the input estimate and every allowed output token) is checked against
    what is left under the cap, and a call that could cross the cap is not made."""
    from eval.budget import BudgetExceeded, RunBudget

    if budget is None:
        if not _API_BUDGET:
            _API_BUDGET.append(RunBudget())
        budget = _API_BUDGET[0]
    try:
        price_in, price_out = (float(p) for p in os.environ["GRADER_PRICES_PER_MILLION"].split(","))
    except (KeyError, ValueError) as error:
        raise GraderError("set GRADER_PRICES_PER_MILLION to the grader model's prices so the run cap can be kept") from error
    budget.check()
    max_output = int(os.environ.get("GRADER_MAX_OUTPUT_TOKENS", MAX_OUTPUT_TOKENS))
    worst = (input_token_estimate(prompt) * price_in + max_output * price_out) / 1_000_000
    if budget.spent_usd + worst > budget.cap_usd:
        raise BudgetExceeded(f"grading call refused: it could cost up to ${worst:.2f}, and ${budget.spent_usd:.2f} of the "
                             f"${budget.cap_usd:.2f} cap is spent")
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    response = client.responses.create(model=os.environ["GRADER_MODEL"], input=prompt, max_output_tokens=max_output)
    usage = response.usage
    budget.add((usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000)
    return response.output_text


def runner_for(budget=None):
    """The grading runner; the API fallback charges its calls to the given run budget (the conversation run's own)."""
    if os.environ.get("GRADER_BACKEND", "codex") != "api":
        return codex_runner

    def runner(prompt: str) -> str:
        return api_runner(prompt, budget=budget)
    runner.__name__ = "api_runner"
    return runner


def grader_model() -> str:
    return os.environ.get("GRADER_MODEL", "unknown") if os.environ.get("GRADER_BACKEND", "codex") == "api" else CODEX_MODEL


def choose_check_sample(verdicts: list[Verdict], n: int = 30, seed: int = 11) -> list[Verdict]:
    """Answers for the author to grade blind (R19), chosen before seeing them, spread across right and wrong."""
    rng = random.Random(seed)
    right = [v for v in verdicts if v.correct is True]
    wrong = [v for v in verdicts if v.correct is False]
    rng.shuffle(right)
    rng.shuffle(wrong)
    take_wrong = min(len(wrong), max(n // 3, n - len(right)))
    sample = wrong[:take_wrong] + right[:n - take_wrong]
    rng.shuffle(sample)
    return sample


def agreement_table(author: list[bool], grader: list[bool]) -> dict:
    pairs = list(zip(author, grader))
    table = {"both_right": sum(a and g for a, g in pairs), "both_wrong": sum(not a and not g for a, g in pairs),
             "author_only": sum(a and not g for a, g in pairs), "grader_only": sum(g and not a for a, g in pairs)}
    table["agreement"] = (table["both_right"] + table["both_wrong"]) / len(pairs) if pairs else None
    return table
