"""Planted test data for one test case, written only into a copy of the seed database (R11, R13)."""

import sqlite3
from pathlib import Path

from app.config import SETTINGS


def apply_fixtures(db_path: Path, fixtures: list[dict]) -> None:
    if db_path.resolve() in (SETTINGS.seed_db_path.resolve(), SETTINGS.scheduling_db_path.resolve()):
        raise ValueError("fixtures may only be applied to a test copy, never the seed or the live database")
    db = sqlite3.connect(db_path)
    with db:
        for fixture in fixtures:
            row = fixture["row"]
            columns = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            # A plain insert: a planted row that collides with an existing one fails rather than replacing it.
            db.execute(f"insert into {fixture['table']} ({columns}) values ({marks})", list(row.values()))
            for slot_id in fixture.get("book_slots", []):
                db.execute("update appointment_slots set status = 'booked' where slot_id = ?", (slot_id,))
    db.close()


TABLES = {"appointments": "appointment_id", "appointment_slots": "slot_id", "customers": "customer_id", "invoices": "invoice_id"}


def snapshot(db_path: Path) -> dict:
    """Every row of the tables a conversation could change, by key."""
    db = sqlite3.connect(db_path)
    try:
        return {table: {row[0]: row for row in db.execute(f"select {key}, * from {table}")} for table, key in TABLES.items()}
    finally:
        db.close()


def start_state(fixtures: list[dict]) -> dict:
    """A fresh test copy as a conversation starts: the seed with the case's fixtures applied."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "start.sqlite"
        shutil.copy(SETTINGS.seed_db_path, db)
        apply_fixtures(db, fixtures)
        return snapshot(db)
