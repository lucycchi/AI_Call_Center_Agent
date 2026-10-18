import shutil
from datetime import date
from pathlib import Path

import pytest

from app.accounts.identity import identify
from app.accounts.lookups import read_only
from app.config import SETTINGS
from app.scheduling.dates import DateRequest, parse_request
from app.scheduling.eligibility import eligible_slots, offer
from app.scheduling.zones import zone_for

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
NOW = SETTINGS.now  # Friday 2026-10-16 09:00, America/Chicago


@pytest.fixture
def db(tmp_path):
    copy = tmp_path / "copy.sqlite"
    shutil.copy(SEED, copy)
    return read_only(copy)


def customer(db, name, account):
    return identify(db, name, account)


def test_zones():
    assert zone_for("Round Rock") == "north" and zone_for("Kyle") == "south" and zone_for("Manor") is None


def test_no_capacity_is_a_clean_decline_naming_the_gap(db):
    assert offer(db, customer(db, "Linda Foster", "MHC-10001"), "plumbing", None, NOW).decline_reason \
        == "no plumbing capacity in north zone"
    result = offer(db, customer(db, "Grace Okafor", "MHC-10003"), "estimate", None, NOW)
    assert result.slots == [] and result.decline_reason == "no estimate capacity in central zone"


def test_an_eligible_requested_slot_is_offered_first(db):
    result = offer(db, customer(db, "Linda Foster", "MHC-10001"), "hvac_repair", DateRequest(date(2026, 10, 19), "morning"), NOW)
    first = result.slots[0]
    assert (first.slot_id, first.slot_date, first.window, first.tech_id) == (56, "2026-10-19", "08:00-12:00", 5)


def test_a_started_window_is_never_offered_and_members_only_slots_need_a_membership(db):
    linda = {s.slot_id for s in eligible_slots(db, customer(db, "Linda Foster", "MHC-10001"), "hvac_repair", NOW)}
    assert 1 not in linda  # members-only, but its 08:00-12:00 window started an hour ago
    members_only = {r[0] for r in db.execute("select slot_id from appointment_slots where status = 'reserved_members' "
                                             "and zone = 'north' and service_type = 'hvac_repair' and slot_date > '2026-10-16'")}
    # Slot 110 is members-only but technician 1 is booked 13:00-17:00 that day (slot 111), so it is excluded too.
    assert members_only - {110} and members_only - {110} <= linda and 110 not in linda
    daniel = {s.slot_id for s in eligible_slots(db, customer(db, "Daniel Reyes", "MHC-10004"), "hvac_repair", NOW)}
    assert not members_only & daniel


def test_a_technician_booked_in_an_overlapping_window_is_not_offered(db):
    tune_ups = {s.slot_id for s in eligible_slots(db, customer(db, "Linda Foster", "MHC-10001"), "hvac_tune_up", NOW)}
    assert 17 not in tune_ups  # technician 5 is booked 13:00-17:00 that day (slot 18)


def test_otherwise_up_to_three_nearest_first_then_morning_to_evening_with_overlapping_windows_distinct(db):
    linda = customer(db, "Linda Foster", "MHC-10001")
    result = offer(db, linda, "hvac_repair", DateRequest(date(2026, 10, 18)), NOW)  # a Sunday: no slots
    assert [(s.slot_date, s.window) for s in result.slots] == [
        ("2026-10-19", "08:00-12:00"), ("2026-10-19", "12:00-16:00"), ("2026-10-19", "13:00-17:00")]
    assert result.decline_reason is None


def test_requests_for_a_window_only_match_that_window(db):
    linda = customer(db, "Linda Foster", "MHC-10001")
    result = offer(db, linda, "hvac_repair", DateRequest(date(2026, 10, 19), window="13:00-17:00"), NOW)
    assert [s.slot_id for s in result.slots] == [58]


@pytest.mark.parametrize("text, expected", [
    ("tomorrow morning", DateRequest(date(2026, 10, 17), "morning")),
    ("this Saturday", DateRequest(date(2026, 10, 17))),
    ("this Sunday", DateRequest(date(2026, 10, 18))),
    ("next Tuesday evening", DateRequest(date(2026, 10, 20), window="16:00-19:00")),
    ("Thursday if possible, 4 to 7, after work", DateRequest(date(2026, 10, 22), window="16:00-19:00")),
    ("Monday if possible, 12 to 4", DateRequest(date(2026, 10, 19), window="12:00-16:00")),
    ("Next Tuesday if possible, the afternoon", DateRequest(date(2026, 10, 20), "afternoon")),
    ("Monday if possible, first thing in the morning", DateRequest(date(2026, 10, 19), "morning")),
    ("As soon as possible if possible, 8 to 12", DateRequest(None, window="08:00-12:00")),
    ("today", DateRequest(date(2026, 10, 16))),
])
def test_parse_request(text, expected):
    assert parse_request(text, NOW) == expected


def test_no_date_or_time_is_not_a_request():
    assert parse_request("my furnace won't kick on", NOW) is None


def test_this_saturday_offers_saturday_morning_when_eligible_else_nearest(db):
    linda = customer(db, "Linda Foster", "MHC-10001")
    result = offer(db, linda, "hvac_repair", parse_request("this Saturday", NOW), NOW)
    # Both north repair slots on Saturday 2026-10-17 are booked, so the nearest eligible ones follow.
    assert result.slots and all(s.slot_date != "2026-10-17" for s in result.slots)
    assert result.slots[0].slot_date == "2026-10-19"


def test_served_areas_without_a_zone_and_unserved_cities_are_declined_differently(db):
    from dataclasses import replace
    linda = customer(db, "Linda Foster", "MHC-10001")
    assert offer(db, replace(linda, city="Manor"), "hvac_repair", None, NOW).decline_reason == "served area without a scheduling zone"
    assert offer(db, replace(linda, city="San Marcos"), "hvac_repair", None, NOW).decline_reason == "outside the service area"


@pytest.mark.parametrize("text, expected", [
    ("October 22", DateRequest(date(2026, 10, 22))), ("Oct 28 in the morning", DateRequest(date(2026, 10, 28), "morning")),
    ("the 22nd", DateRequest(date(2026, 10, 22))), ("10/22", DateRequest(date(2026, 10, 22))),
    ("how about the 3rd", DateRequest(date(2026, 11, 3))),
])
def test_calendar_dates(text, expected):
    assert parse_request(text, NOW) == expected


def test_a_past_date_is_still_read_as_that_date():
    assert parse_request("October 10", NOW) == DateRequest(date(2026, 10, 10))


def test_a_past_date_is_answered_with_the_soonest_slots(db):
    from app.flows import scheduling
    from app.core.state import ConversationState
    state = ConversationState("c", "v", flow={"kind": "book", "step": "start", "service": "hvac_repair"})
    result = scheduling.step(db, SEED, customer(db, "Linda Foster", "MHC-10001"), state, "October 10 please", NOW, None)
    assert "already passed" in " ".join(result.facts)


@pytest.mark.parametrize("text, window", [
    ("Monday 12:00 PM to 4:00 PM", "12:00-16:00"), ("12pm-4pm", "12:00-16:00"), ("noon to 4", "12:00-16:00"),
    ("8:00 AM to 12:00 PM", "08:00-12:00"), ("8am", "08:00-12:00"), ("1pm", "13:00-17:00"), ("1 to 5 pm", "13:00-17:00"),
    ("4:00 to 7:00", "16:00-19:00"), ("12–4", "12:00-16:00"), ("from 12 until 4", "12:00-16:00")])
def test_clock_times_map_to_their_windows(text, window):
    assert parse_request(text, NOW).window == window
