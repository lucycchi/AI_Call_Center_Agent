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
