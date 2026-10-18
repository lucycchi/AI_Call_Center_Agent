"""Book, cancel and reschedule, each in one database transaction with a confirmation id (R52 to R55, R84).

Every change runs under BEGIN IMMEDIATE, so the eligibility check is repeated under the write lock. The
first result for a confirmation id is stored in agent_confirmations in the same transaction; a repeated or
retried confirmation returns that result and never changes the database again."""

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.accounts.fees import SCHEDULE
from app.config import SETTINGS, real_now
from app.scheduling.eligibility import eligible_slots
from app.scheduling.seed import freed_status

CONFIRMATIONS_SQL = (Path(__file__).parent / "confirmations.sql").read_text()
LATE_FEE_CENTS = SCHEDULE["Late cancellation (<24h)|Non-member"]
REVIEW_CLAIMS = ("repeat repair", "member installation")  # warranty claims the database cannot verify (R53)
LABOUR_WARRANTY_YEARS = 2


@dataclass(frozen=True)
class BookingResult:
    status: str  # booked or taken
    appointment_id: int | None
    technician: str | None
    warranty_visit: bool
    warranty_review: bool


@dataclass(frozen=True)
class ChangeResult:
    status: str  # cancelled, rescheduled, taken or not found
    late_fee_cents: int


@dataclass(frozen=True)
class AppointmentSummary:
    appointment_id: int
    slot_date: str
    window: str
    service_type: str
    technician: str


def _after_change(db: sqlite3.Connection) -> None:
    """Runs after the change and before the commit; tests replace it to force a failure."""


def _transaction(db: sqlite3.Connection, confirmation_id: str, kind: type, change):
    """Run change() under the write lock, or return the stored first result for this confirmation id."""
    if db.in_transaction:
        db.commit()
    db.executescript(CONFIRMATIONS_SQL)
    db.execute("BEGIN IMMEDIATE")
    try:
        stored = db.execute("select result from agent_confirmations where confirmation_id = ?", (confirmation_id,)).fetchone()
        if stored:
            db.rollback()
            return kind(**json.loads(stored[0]))
        result = change()
        db.execute("insert into agent_confirmations (confirmation_id, result, created_at) values (?, ?, ?)",
                   (confirmation_id, json.dumps(asdict(result)), real_now().isoformat(timespec="seconds")))
        _after_change(db)
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


def _bookable(db: sqlite3.Connection, customer, slot_id: int, now: datetime) -> bool:
    row = db.execute("select service_type from appointment_slots where slot_id = ?", (slot_id,)).fetchone()
    if row is None or db.execute("select 1 from appointments where slot_id = ? and status = 'scheduled'", (slot_id,)).fetchone():
        return False
    return any(s.slot_id == slot_id for s in eligible_slots(db, customer, row[0], now))


def _technician(db: sqlite3.Connection, slot_id: int) -> str:
    return db.execute("select t.name from appointment_slots s join technicians t using (tech_id) where s.slot_id = ?",
                      (slot_id,)).fetchone()[0]


def _late_fee(db: sqlite3.Connection, slot_id: int, now: datetime) -> int:
    day, window = db.execute("select slot_date, window from appointment_slots where slot_id = ?", (slot_id,)).fetchone()
    starts = datetime.fromisoformat(f"{day}T{window[:5]}").replace(tzinfo=now.tzinfo)
    return LATE_FEE_CENTS if starts - now < timedelta(hours=24) else 0


def _own_scheduled(db: sqlite3.Connection, customer, appointment_id: int) -> int | None:
    row = db.execute("select slot_id from appointments where appointment_id = ? and customer_id = ? and status = 'scheduled'",
                     (appointment_id, customer.customer_id)).fetchone()
    return row[0] if row else None


def _warranty_visit(db: sqlite3.Connection, customer_id: str, now: datetime) -> bool:
    """Only when the install date proves the 2-year installation labour warranty still applies."""
    (installed,) = db.execute("select system_install_date from customers where customer_id = ?", (customer_id,)).fetchone()
    if not installed:
        return False
    today = now.date()
    return date.fromisoformat(installed) > today.replace(year=today.year - LABOUR_WARRANTY_YEARS)


def book(db: sqlite3.Connection, customer, slot_id: int, issue: str, confirmation_id: str, now: datetime,
         claim: str | None = None) -> BookingResult:
    def change() -> BookingResult:
        if not _bookable(db, customer, slot_id, now):
            return BookingResult("taken", None, None, False, False)
        review = claim in REVIEW_CLAIMS
        warranty = not review and _warranty_visit(db, customer.customer_id, now)
        db.execute("update appointment_slots set status = 'booked' where slot_id = ?", (slot_id,))
        cursor = db.execute("insert into appointments (slot_id, customer_id, issue_description, created_at, status, "
                            "is_warranty_visit) values (?, ?, ?, ?, 'scheduled', ?)",
                            (slot_id, customer.customer_id, issue, now.strftime("%Y-%m-%dT%H:%M"), int(warranty)))
        return BookingResult("booked", cursor.lastrowid, _technician(db, slot_id), warranty, review)
    return _transaction(db, confirmation_id, BookingResult, change)


def cancel(db: sqlite3.Connection, customer, appointment_id: int, confirmation_id: str, now: datetime,
           seed_db: Path = SETTINGS.seed_db_path) -> ChangeResult:
    def change() -> ChangeResult:
        slot_id = _own_scheduled(db, customer, appointment_id)
        if slot_id is None:
            return ChangeResult("not found", 0)
        fee = _late_fee(db, slot_id, now)
        db.execute("update appointments set status = 'cancelled' where appointment_id = ?", (appointment_id,))
        db.execute("update appointment_slots set status = ? where slot_id = ?", (freed_status(seed_db, slot_id), slot_id))
        return ChangeResult("cancelled", fee)
    return _transaction(db, confirmation_id, ChangeResult, change)


def reschedule(db: sqlite3.Connection, customer, appointment_id: int, new_slot_id: int, confirmation_id: str,
               now: datetime, seed_db: Path = SETTINGS.seed_db_path) -> ChangeResult:
    def change() -> ChangeResult:
        old_slot = _own_scheduled(db, customer, appointment_id)
        if old_slot is None:
            return ChangeResult("not found", 0)
        if not _bookable(db, customer, new_slot_id, now):
            return ChangeResult("taken", 0)
        fee = _late_fee(db, old_slot, now)
        db.execute("update appointment_slots set status = 'booked' where slot_id = ?", (new_slot_id,))
        db.execute("update appointments set slot_id = ? where appointment_id = ?", (new_slot_id, appointment_id))
        db.execute("update appointment_slots set status = ? where slot_id = ?", (freed_status(seed_db, old_slot), old_slot))
        return ChangeResult("rescheduled", fee)
    return _transaction(db, confirmation_id, ChangeResult, change)


def scheduled_appointments(db: sqlite3.Connection, customer_id: str) -> list[AppointmentSummary]:
    """Date, window, service and technician only; the stored issue text is never read back (R54)."""
    rows = db.execute("select a.appointment_id, s.slot_date, s.window, s.service_type, t.name from appointments a "
                      "join appointment_slots s using (slot_id) join technicians t using (tech_id) "
                      "where a.customer_id = ? and a.status = 'scheduled' order by s.slot_date, s.window",
                      (customer_id,)).fetchall()
    return [AppointmentSummary(*row) for row in rows]
