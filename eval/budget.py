"""Spending and key rules for paid test runs (R61, D30, D36): a separate test key and an $8 stop per run."""

import os

from app.config import SETTINGS


class BudgetExceeded(RuntimeError):
    pass


def require_eval_key() -> str:
    """The separate test key; never the live one."""
    key = os.environ.get("EVAL_ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("EVAL_ANTHROPIC_API_KEY is not set; test runs never use the live key")
    if key == os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("EVAL_ANTHROPIC_API_KEY is the same as the live key; test runs need their own key")
    return key


class RunBudget:
    def __init__(self, cap_usd: float = SETTINGS.eval_run_cap_usd):
        self.cap_usd, self.spent_usd = cap_usd, 0.0

    def add(self, usd: float) -> None:
        """Counts the spend; once it crosses the cap, the run stops here rather than at the next check."""
        self.spent_usd += usd
        self.check()

    def record(self, purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars) -> None:
        """A model-call sink: every call in a test run counts against the run's budget."""
        self.add(microdollars / 1_000_000)

    def check(self) -> None:
        if self.spent_usd >= self.cap_usd:
            raise BudgetExceeded(f"test run stopped at ${self.spent_usd:.2f}, the ${self.cap_usd:.2f} cap")
