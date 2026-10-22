"""Which knowledge-base documents are searchable, decided by data/document_list.csv (D22), not by folder."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "call_data" / "knowledge_base"
DOCUMENT_LIST = ROOT / "data" / "document_list.csv"
# Documents the author supplied, kept apart from the company's knowledge base and listed in their own file with who
# supplied them and when (the autopay policy, actions decision (D54)).
ADDED = ROOT / "data" / "kb_added"
ADDED_LIST = ROOT / "data" / "documents_added.csv"


def _rows() -> list[dict]:
    return list(csv.DictReader(DOCUMENT_LIST.open()))


def _added_rows() -> list[dict]:
    return list(csv.DictReader(ADDED_LIST.open())) if ADDED_LIST.exists() else []


def relative(path: Path) -> str:
    """The document's path as its list names it; author-supplied ones start with "added/"."""
    return str(path.relative_to(KB)) if path.is_relative_to(KB) else "added/" + str(path.relative_to(ADDED))


def searchable_documents() -> list[Path]:
    return [KB / r["path"] for r in _rows() if r["status"] == "current" and r["audience"] == "customers"] + \
        [ADDED / r["path"] for r in _added_rows() if r["status"] == "current" and r["audience"] == "customers"]


def internal_documents() -> list[Path]:
    return [KB / r["path"] for r in _rows() if r["status"] == "current" and r["audience"] == "internal"]


def effective_date(path: Path) -> str:
    rel = relative(path)
    rows = _rows() + [{**r, "path": "added/" + r["path"]} for r in _added_rows()]
    return next((r["effective_date"] for r in rows if r["path"] == rel), "")
