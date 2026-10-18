"""Pinned settings. The fixed "now" drives customer-facing scheduling and policy rules;
operations (limits, the nightly reset, alerts, timing) use real time via real_now()."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

AUSTIN = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parent.parent


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    now: datetime
    router_model: str
    writer_model: str
    embedding_model: str
    scheduling_db_path: Path
    seed_db_path: Path
    ops_db_path: Path
    per_visitor_daily_usd: float
    site_daily_usd: float
    reviewer_daily_usd: float
    spend_alert_usd: float
    anthropic_timeout_s: int
    voyage_timeout_s: int
    webhook_timeout_s: int
    message_deadline_s: int
    eval_run_cap_usd: float
    eval_max_caller_turns: int
    eval_conversation_seconds: int
    visitor_messages_per_10_min: int
    visitor_messages_per_day: int
    site_messages_per_minute: int
    router_max_tokens: int
    eval_writer_max_tokens: int
    eval_simulator_max_tokens: int
    eval_retries: int


def _path(name: str, default: Path) -> Path:
    """Relative paths in the environment are read from the project folder, not the working directory."""
    value = Path(os.environ.get(name, default))
    return value if value.is_absolute() else ROOT / value


def load_settings() -> Settings:
    data = _path("DATA_DIR", ROOT / "data")
    seed = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
    live = _path("DATABASE_PATH", data / "scheduling.sqlite")
    if live.resolve() == seed.resolve():
        raise ValueError(f"DATABASE_PATH must not be the read-only seed file {seed}; use data/scheduling.sqlite")
    return Settings(
        now=datetime(2026, 10, 16, 9, 0, tzinfo=AUSTIN),
        router_model="claude-haiku-5-5",
        writer_model="claude-sonnet-5-5",
        embedding_model="voyage-4",
        scheduling_db_path=live,
        seed_db_path=seed,
        ops_db_path=_path("OPS_DATABASE_PATH", data / "operations.sqlite"),
        per_visitor_daily_usd=_float("PER_VISITOR_DAILY_USD", 0.40),
        site_daily_usd=_float("SITE_DAILY_USD", 10.0),
        reviewer_daily_usd=_float("REVIEWER_DAILY_USD", 3.0),
        spend_alert_usd=_float("SPEND_ALERT_USD", 5.0),
        anthropic_timeout_s=20,
        voyage_timeout_s=5,
        webhook_timeout_s=5,
        message_deadline_s=15,
        eval_run_cap_usd=_float("EVAL_RUN_CAP_USD", 8.0),
        eval_max_caller_turns=12,
        eval_conversation_seconds=60,
        visitor_messages_per_10_min=20,
        visitor_messages_per_day=100,
        site_messages_per_minute=60,
        router_max_tokens=200,
        eval_writer_max_tokens=800,
        eval_simulator_max_tokens=300,
        eval_retries=1,
    )


SETTINGS = load_settings()

# Published prices in US dollars per million input and output tokens (docs/MODEL_RESEARCH.md, 2026-10-06).
PRICES_PER_MILLION_USD = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES_PER_MILLION_USD[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def real_now() -> datetime:
    return datetime.now(AUSTIN)
