"""Which knowledge-base documents are searchable, decided by data/document_list.csv (D22), not by folder."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "call_data" / "knowledge_base"
DOCUMENT_LIST = ROOT / "data" / "document_list.csv"


def _rows() -> list[dict]:
    return list(csv.DictReader(DOCUMENT_LIST.open()))


def searchable_documents() -> list[Path]:
    return [KB / r["path"] for r in _rows() if r["status"] == "current" and r["audience"] == "customers"]


def internal_documents() -> list[Path]:
    return [KB / r["path"] for r in _rows() if r["status"] == "current" and r["audience"] == "internal"]


def effective_date(path: Path) -> str:
    rel = str(path.relative_to(KB))
    return next((r["effective_date"] for r in _rows() if r["path"] == rel), "")
