"""A slot's status in the untouched seed copy, which decides what a freed slot returns to (R55, D33)."""

from pathlib import Path

from app.accounts.lookups import read_only


def seed_status(seed_db: Path, slot_id: int) -> str | None:
    """None when the slot is not in the seed at all (one added for a test)."""
    db = read_only(seed_db)
    try:
        row = db.execute("select status from appointment_slots where slot_id = ?", (slot_id,)).fetchone()
    finally:
        db.close()
    return row[0] if row else None


def freed_status(seed_db: Path, slot_id: int) -> str:
    """Open or members-only as in the seed; a slot the seed shows booked, or does not have, is freed to open."""
    status = seed_status(seed_db, slot_id)
    return status if status in ("open", "reserved_members") else "open"
