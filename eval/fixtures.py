"""Planted test data for one test case, written only into a copy of the seed database (R11, R13)."""

import sqlite3
from pathlib import Path

from app.config import SETTINGS


def apply_fixtures(db_path: Path, fixtures: list[dict]) -> None:
    if db_path.resolve() == SETTINGS.seed_db_path.resolve():
        raise ValueError("fixtures may only be applied to a copy of the seed database")
    db = sqlite3.connect(db_path)
    with db:
        for fixture in fixtures:
            row = fixture["row"]
            columns = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            db.execute(f"insert or replace into {fixture['table']} ({columns}) values ({marks})", list(row.values()))
            for slot_id in fixture.get("book_slots", []):
                db.execute("update appointment_slots set status = 'booked' where slot_id = ?", (slot_id,))
    db.close()
