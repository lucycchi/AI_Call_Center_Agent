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


def _load() -> Settings:
    data = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    seed = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
    return Settings(
        now=datetime(2026, 10, 16, 9, 0, tzinfo=AUSTIN),
        router_model=os.environ.get("ROUTER_MODEL", "claude-haiku-5-5"),
        writer_model=os.environ.get("AGENT_MODEL", "claude-sonnet-5-5"),
        scheduling_db_path=Path(os.environ.get("DATABASE_PATH", data / "scheduling.sqlite")),
        seed_db_path=seed,
        ops_db_path=Path(os.environ.get("OPS_DATABASE_PATH", data / "operations.sqlite")),
        per_visitor_daily_usd=_float("PER_VISITOR_DAILY_USD", 0.40),
        site_daily_usd=_float("DAILY_SPEND_CAP_USD", 10.0),
        reviewer_daily_usd=_float("REVIEWER_DAILY_USD", 3.0),
        spend_alert_usd=_float("SPEND_ALERT_USD", 5.0),
        anthropic_timeout_s=20,
        voyage_timeout_s=5,
        webhook_timeout_s=5,
        message_deadline_s=15,
        eval_run_cap_usd=_float("EVAL_RUN_CAP_USD", 8.0),
        eval_max_caller_turns=12,
        eval_conversation_seconds=60,
    )


SETTINGS = _load()


def real_now() -> datetime:
    return datetime.now(AUSTIN)
