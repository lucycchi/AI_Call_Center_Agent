"""Knowledge questions: answered only from retrieved passages, with their sources; a weak match hands off (R41)."""

import csv
import re
from pathlib import Path

from app.flows.protocol import FlowResult

DOCUMENT_LIST = Path(__file__).resolve().parents[2] / "data" / "document_list.csv"


def _superseded() -> dict[str, list[str]]:
    """Each current document and the stale documents the document list says it supersedes."""
    stale: dict[str, list[str]] = {}
    for row in csv.DictReader(DOCUMENT_LIST.open()):
        match = re.search(r"superseded by ([\w/.-]+\.\w+)", row["reason"])
        if row["status"] != "current" and match:
            stale.setdefault(match.group(1), []).append(row["path"])
    return stale


SUPERSEDED = _superseded()

PRICE_WORDS = re.compile(r"\b(cost|costs|price|prices|pricing|how much|fee|fees|charge|charges|rate|\$)", re.I)
FINAL_PRICE = "Always add: the technician confirms the final price on site."
SAVINGS = re.compile(r"\b(save me money|save money|saves? me|pays? for itself|worth it|worth joining)\b", re.I)
NO_ESTIMATE = ("Do not estimate whether joining would save money on this visit. State the member benefits, and say the "
               "documents do not say whether they apply to a visit booked on the day of joining, so a team member confirms "
               "that when setting up the membership.")
PRICED = {"services/service_catalog.md", "pricing/repair_price_book_2026.csv"}  # typical repair and service prices


def answer(question: str, searcher, threshold: float) -> FlowResult:
    results = searcher.search(question, mode="combined")
    # Combined search always keeps meaning search's first result, so this is the top meaning score (R28, R32).
    if not results or max(r.meaning_score for r in results) < threshold:
        return FlowResult([], "handoff", handoff_reason="not enough evidence")
    facts = [f"{r.chunk.text} [source: {r.chunk.document}, {r.chunk.heading}"
             f"{', effective ' + r.chunk.effective_date if r.chunk.effective_date else ''}]" for r in results]
    sources = list(dict.fromkeys(r.chunk.document for r in results))
    passages = [f"{r.chunk.document} ({r.chunk.effective_date or 'undated'}), {r.chunk.heading}" for r in results]
    excluded = list(dict.fromkeys(old for document in sources for old in SUPERSEDED.get(document, [])))
    # The final-price line is for typical repair and service prices, not fixed fees or membership prices.
    reply_type = "price answer" if PRICE_WORDS.search(question) and PRICED & set(sources) else "policy answer"
    if SAVINGS.search(question):
        facts = facts + [NO_ESTIMATE]
    return FlowResult(facts + ([FINAL_PRICE] if reply_type == "price answer" else []), reply_type, sources,
                      passages=passages, excluded=excluded)
