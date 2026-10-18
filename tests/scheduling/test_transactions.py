import shutil
import sqlite3
from pathlib import Path

import pytest

import app.scheduling.transactions as tx
from app.accounts.identity import identify
from app.config import SETTINGS
from app.scheduling.seed import seed_status

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
NOW = SETTINGS.now


@pytest.fixture
def path(tmp_path):
    copy = tmp_path / "copy.sqlite"
    shutil.copy(SEED, copy)
    return copy


@pytest.fixture
def db(path):
    return sqlite3.connect(path)


def who(db, name, account):
    return identify(db, name, account)


def slot_status(db, slot_id):
    return db.execute("select status from appointment_slots where slot_id = ?", (slot_id,)).fetchone()[0]


def count(db, table):
    return db.execute(f"select count(*) from {table}").fetchone()[0]


def test_booking_marks_the_slot_and_adds_the_appointment(db):
    result = tx.book(db, who(db, "Linda Foster", "MHC-10001"), 56, "AC blowing warm", "c-1", NOW)
    assert result.status == "booked" and result.technician == "Marta Kowalski"
    assert (result.warranty_visit, result.warranty_review) == (False, False)
    assert slot_status(db, 56) == "booked"
    row = db.execute("select slot_id, customer_id, created_at, status, is_warranty_visit, issue_description from appointments "
                     "where appointment_id = ?", (result.appointment_id,)).fetchone()
    assert row == (56, "MHC-10001", "2026-10-16T09:00", "scheduled", 0, "AC blowing warm")


def test_the_warranty_flag_needs_an_install_inside_the_two_year_labour_warranty(db):
    slot = next(s for s in tx.eligible_slots(db, who(db, "Grace Okafor", "MHC-10003"), "hvac_repair", NOW))
    assert tx.book(db, who(db, "Grace Okafor", "MHC-10003"), slot.slot_id, "no heat", "c-g", NOW).warranty_visit is True
    daniel = who(db, "Daniel Reyes", "MHC-10004")
    slot = next(s for s in tx.eligible_slots(db, daniel, "hvac_repair", NOW))
    assert tx.book(db, daniel, slot.slot_id, "no cool", "c-d", NOW).warranty_visit is True


def test_a_repeat_repair_claim_books_a_normal_visit_for_staff_warranty_review(db):
    result = tx.book(db, who(db, "Linda Foster", "MHC-10001"), 56, "blower again", "c-r", NOW, claim="repeat repair")
    assert (result.warranty_visit, result.warranty_review) == (False, True)


def test_the_same_confirmation_twice_changes_the_database_once(db):
    linda = who(db, "Linda Foster", "MHC-10001")
    first = tx.book(db, linda, 56, "AC", "c-same", NOW)
    appointments = count(db, "appointments")
    assert tx.book(db, linda, 56, "AC", "c-same", NOW) == first
    assert count(db, "appointments") == appointments
    cancelled = tx.cancel(db, linda, first.appointment_id, "c-cancel", NOW)
    assert tx.cancel(db, linda, first.appointment_id, "c-cancel", NOW) == cancelled


def test_a_failure_after_the_insert_leaves_neither_the_change_nor_the_confirmation(db, monkeypatch):
    before = count(db, "appointments")

    def fail(_db):
        raise RuntimeError("forced")
    monkeypatch.setattr(tx, "_after_change", fail)
    with pytest.raises(RuntimeError):
        tx.book(db, who(db, "Linda Foster", "MHC-10001"), 56, "AC", "c-fail", NOW)
    assert count(db, "appointments") == before and slot_status(db, 56) == "open"
    assert db.execute("select count(*) from agent_confirmations where confirmation_id = 'c-fail'").fetchone()[0] == 0


def test_a_slot_taken_between_offer_and_confirmation_is_refused(db, path):
    other = sqlite3.connect(path)
    other.execute("update appointment_slots set status = 'booked' where slot_id = 56")
    other.commit()
    before = count(db, "appointments")
    assert tx.book(db, who(db, "Linda Foster", "MHC-10001"), 56, "AC", "c-t", NOW).status == "taken"
    assert count(db, "appointments") == before


def test_a_slot_with_a_scheduled_appointment_is_refused_even_if_marked_open(db):
    db.execute("update appointment_slots set status = 'open' where slot_id = 159")
    db.commit()
    assert tx.book(db, who(db, "Linda Foster", "MHC-10001"), 159, "AC", "c-x", NOW).status == "taken"


def test_scheduled_appointments_never_include_the_issue_text(db):
    [summary] = tx.scheduled_appointments(db, "MHC-10001")
    assert (summary.slot_date, summary.window, summary.service_type, summary.technician) == \
        ("2026-10-22", "08:00-12:00", "hvac_repair", "Marta Kowalski")
    assert "AC blowing warm air" not in repr(summary)


def test_cancelling_a_seeded_appointment_frees_its_slot_to_open(db):
    result = tx.cancel(db, who(db, "Linda Foster", "MHC-10001"), 159, "c-c", NOW)
    assert (result.status, result.late_fee_cents) == ("cancelled", 0)
    assert seed_status(SEED, 159) == "booked" and slot_status(db, 159) == "open"
    assert db.execute("select status from appointments where appointment_id = 159").fetchone()[0] == "cancelled"


def test_a_cancelled_members_only_booking_returns_its_slot_to_members_only(db):
    linda = who(db, "Linda Foster", "MHC-10001")
    booked = tx.book(db, linda, 300, "AC", "c-m", NOW)
    assert booked.status == "booked"
    tx.cancel(db, linda, booked.appointment_id, "c-mc", NOW)
    assert slot_status(db, 300) == "reserved_members"


def test_only_the_callers_own_scheduled_appointment_can_be_changed(db):
    assert tx.cancel(db, who(db, "Omar Patel", "MHC-10002"), 159, "c-o", NOW).status == "not found"


def test_rescheduling_inside_24_hours_states_the_late_fee_and_moves_the_appointment(db):
    appointment, slot = db.execute("select appointment_id, slot_id from appointments where appointment_id = 2").fetchone()
    owner = db.execute("select name, customer_id from customers where customer_id = "
                       "(select customer_id from appointments where appointment_id = 2)").fetchone()
    caller = who(db, *owner)
    service = db.execute("select service_type from appointment_slots where slot_id = ?", (slot,)).fetchone()[0]
    new = next(s for s in tx.eligible_slots(db, caller, service, NOW))
    result = tx.reschedule(db, caller, appointment, new.slot_id, "c-rs", NOW)
    assert (result.status, result.late_fee_cents) == ("rescheduled", 4900)
    assert slot_status(db, new.slot_id) == "booked"
    assert slot_status(db, slot) == "open"  # seeded as booked, so freed to open
    assert db.execute("select slot_id from appointments where appointment_id = 2").fetchone()[0] == new.slot_id


def test_a_failed_reschedule_leaves_both_slots_unchanged(db, monkeypatch):
    caller = who(db, "Linda Foster", "MHC-10001")
    monkeypatch.setattr(tx, "_after_change", lambda _db: (_ for _ in ()).throw(RuntimeError("forced")))
    with pytest.raises(RuntimeError):
        tx.reschedule(db, caller, 159, 56, "c-rf", NOW)
    assert slot_status(db, 56) == "open" and slot_status(db, 159) == "booked"
    assert db.execute("select slot_id from appointments where appointment_id = 159").fetchone()[0] == 159


def test_the_warranty_flag_is_only_for_hvac_repair_visits(db):
    grace = who(db, "Grace Okafor", "MHC-10003")
    slot = next(s for s in tx.eligible_slots(db, grace, "plumbing", NOW))
    assert tx.book(db, grace, slot.slot_id, "sink", "c-gp", NOW).warranty_visit is False
