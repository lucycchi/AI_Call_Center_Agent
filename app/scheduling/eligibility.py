"""Which slots a caller may book, what to offer, and when to decline cleanly (R49, R50, R51)."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.scheduling.dates import DateRequest
from app.scheduling.zones import SERVED_WITHOUT_ZONE, zone_for

RANGE_DAYS = 21
PARTS = {"morning": {"08:00-12:00"}, "afternoon": {"12:00-16:00", "13:00-17:00"}}
SERVICE_NAMES = {"hvac_repair": "hvac repair", "hvac_tune_up": "tune-up", "plumbing": "plumbing", "estimate": "estimate"}


@dataclass(frozen=True)
class Slot:
    slot_id: int
    slot_date: str
    window: str
    tech_id: int
    zone: str
    service_type: str
    status: str


@dataclass(frozen=True)
class Offer:
    slots: list[Slot]
    decline_reason: str | None


def spoken_window(window: str) -> str:
    """ "08:00-12:00" as "8am to 12pm"."""
    def hour(text: str) -> str:
        h = int(text[:2])
        return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
    start, end = window.split("-")
    return f"{hour(start)} to {hour(end)}"


def spoken_when(slot_date: str, window: str) -> str:
    """ "2026-10-19", "08:00-12:00" as "Monday, October 19, 8am to 12pm"."""
    day = datetime.fromisoformat(slot_date)
    return f"{day:%A}, {day:%B} {day.day}, {spoken_window(window)}"


def _overlaps(a: str, b: str) -> bool:
    (a1, a2), (b1, b2) = a.split("-"), b.split("-")
    return a1 < b2 and b1 < a2


def _starts(slot: Slot, now: datetime) -> datetime:
    return datetime.fromisoformat(f"{slot.slot_date}T{slot.window[:5]}").replace(tzinfo=now.tzinfo)


def eligible_slots(db: sqlite3.Connection, customer, service_type: str, now: datetime) -> list[Slot]:
    """Open slots (or members-only ones for a member) in the customer's zone for that service, not yet started,
    within three weeks, whose technician has no booked overlapping window that day."""
    zone = zone_for(customer.city)
    if zone is None:
        return []
    statuses = ("open", "reserved_members") if customer.membership_tier in ("standard", "plus") else ("open",)
    last = (now.date() + timedelta(days=RANGE_DAYS)).isoformat()
    rows = db.execute(f"select slot_id, slot_date, window, tech_id, zone, service_type, status from appointment_slots "
                      f"where zone = ? and service_type = ? and status in ({', '.join('?' * len(statuses))}) "
                      f"and slot_date <= ? order by slot_date, window, slot_id", (zone, service_type, *statuses, last)).fetchall()
    booked = {}
    for tech, day, window in db.execute("select tech_id, slot_date, window from appointment_slots where status = 'booked'"):
        booked.setdefault((tech, day), []).append(window)
    # The caller's own scheduled visits: never offer a slot overlapping one of them.
    own = {}
    customer_id = getattr(customer, "customer_id", None)
    if customer_id:
        for day, window in db.execute("select s.slot_date, s.window from appointments a join appointment_slots s using (slot_id) "
                                      "where a.customer_id = ? and a.status = 'scheduled'", (customer_id,)):
            own.setdefault(day, []).append(window)
    return [slot for slot in map(lambda row: Slot(*row), rows)
            if _starts(slot, now) > now and not any(_overlaps(slot.window, w) for w in booked.get((slot.tech_id, slot.slot_date), []))
            and not any(_overlaps(slot.window, w) for w in own.get(slot.slot_date, []))]


def _wanted(slot: Slot, requested: DateRequest) -> bool:
    if requested.date and slot.slot_date != requested.date.isoformat():
        return False
    if requested.window:
        return slot.window == requested.window
    return requested.part is None or slot.window in PARTS[requested.part]


def _distinct(slots: list[Slot]) -> list[Slot]:
    """One slot per date and window: two technicians in the same window are the same choice for the caller."""
    seen, out = set(), []
    for slot in slots:
        if (slot.slot_date, slot.window) not in seen:
            seen.add((slot.slot_date, slot.window))
            out.append(slot)
    return out


def offer(db: sqlite3.Connection, customer, service_type: str, requested: DateRequest | None, now: datetime) -> Offer:
    zone = zone_for(customer.city)
    if zone is None:
        served = customer.city.strip().lower() in SERVED_WITHOUT_ZONE
        return Offer([], "served area without a scheduling zone" if served else "outside the service area")
    slots = eligible_slots(db, customer, service_type, now)
    if not slots:
        return Offer([], f"no {SERVICE_NAMES[service_type]} capacity in {zone} zone")
    if requested:
        wanted = [s for s in slots if _wanted(s, requested)]
        if wanted:
            return Offer(wanted[:1], None)
    target = requested.date if requested and requested.date else now.date()
    ranked = sorted(slots, key=lambda s: (abs((datetime.fromisoformat(s.slot_date).date() - target).days), s.slot_date,
                                          s.window, s.slot_id))
    return Offer(_distinct(ranked)[:3], None)
