from app.config import SETTINGS, real_now


def test_fixed_now_is_friday_morning_in_austin():
    assert SETTINGS.now.isoformat() == "2026-10-16T09:00:00-05:00"
    assert SETTINGS.now.strftime("%A") == "Friday"


def test_models_are_pinned():
    assert SETTINGS.router_model == "claude-haiku-5-5"
    assert SETTINGS.writer_model == "claude-sonnet-5-5"


def test_live_spending_limits():
    assert SETTINGS.per_visitor_daily_usd == 0.40
    assert SETTINGS.site_daily_usd == 10.0
    assert SETTINGS.reviewer_daily_usd == 3.0
    assert SETTINGS.spend_alert_usd == 5.0


def test_timeouts_and_message_deadline():
    assert SETTINGS.anthropic_timeout_s == 20
    assert SETTINGS.voyage_timeout_s == 5
    assert SETTINGS.webhook_timeout_s == 5
    assert SETTINGS.message_deadline_s == 15


def test_paid_test_run_limits():
    assert SETTINGS.eval_run_cap_usd == 8.0
    assert SETTINGS.eval_max_caller_turns == 12
    assert SETTINGS.eval_conversation_seconds == 60


def test_operations_use_real_time_not_the_fixed_now():
    assert real_now().year >= 2026
    assert real_now() != SETTINGS.now


def test_example_env_file_gives_a_ten_dollar_site_cap_and_a_live_database_separate_from_the_seed(monkeypatch):
    from dotenv import dotenv_values

    from app.config import ROOT, load_settings

    values = {k: v for k, v in dotenv_values(ROOT / ".env.example").items() if v}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    assert settings.site_daily_usd == 10.0
    assert settings.scheduling_db_path.resolve() != settings.seed_db_path.resolve()
    assert settings.scheduling_db_path.is_absolute()


def test_settings_refuse_a_live_database_that_is_the_seed_file(monkeypatch):
    import pytest

    from app.config import ROOT, load_settings

    monkeypatch.setenv("DATABASE_PATH", str(ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"))
    with pytest.raises(ValueError, match="seed"):
        load_settings()


def test_model_ids_cannot_be_overridden_from_the_environment(monkeypatch):
    from app.config import load_settings

    monkeypatch.setenv("ROUTER_MODEL", "something-else")
    monkeypatch.setenv("AGENT_MODEL", "something-else")
    settings = load_settings()
    assert settings.router_model == "claude-haiku-5-5"
    assert settings.writer_model == "claude-sonnet-5-5"


def test_rate_limits_and_test_run_limits_are_pinned():
    assert SETTINGS.visitor_messages_per_10_min == 20
    assert SETTINGS.visitor_messages_per_day == 100
    assert SETTINGS.site_messages_per_minute == 60
    assert SETTINGS.eval_writer_max_tokens == 800
    assert SETTINGS.eval_simulator_max_tokens == 300
    assert SETTINGS.router_max_tokens == 200
    assert SETTINGS.eval_retries == 1
