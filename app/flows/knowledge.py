"""Knowledge questions: answered only from retrieved passages, with their sources; a weak match hands off (R41)."""

import csv
import re
from pathlib import Path

from app.flows.protocol import FlowResult
from app.knowledge.index import Chunk

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
# Sections of those documents with fixed prices (tune-up, fees) or the free in-home replacement estimate.
FIXED_SECTIONS = {"Maintenance", "Fee", "Maintenance tune-up", "System replacement"}
# A question about a fixed fee or flat price, or about replacing a whole system or appliance, gets no final-price line;
# a named repair part ("capacitor replacement") is still a repair.
FIXED_WORDS = re.compile(r"\b(tune-?ups?|maintenance|cancel\w*|no-?show|after-?hours|emergency|holiday|diagnostic|dispatch|"
                         r"member\w*|plans?|permits?|disposal|flush)\b", re.I)
REPLACEMENT = re.compile(r"\b(replac\w*|new|install\w*|estimates?)\b", re.I)
REPAIR_PART = re.compile(r"\b(capacitor|contactor|refrigerant|recharge|drain|motor|thermostat|ignitor|igniter|coil|compressor)",
                         re.I)
# The document sentence the final-price line comes from, so the line has a source (as in the built index).
FINAL_PRICE_SOURCE = Chunk("pricing__repair_price_book_2026#0", "pricing/repair_price_book_2026.csv", "2026 Repair Price Book",
                           "2026", "# 2026 Repair Price Book\n\nTypical prices. The technician confirms the final price on site.", 1, 4)


def _varies_by_job(question: str, chunks: list[Chunk]) -> bool:
    """A repair or service price from the price book or catalog, which the technician confirms on site."""
    return (bool(PRICE_WORDS.search(question)) and not FIXED_WORDS.search(question)
            and (not REPLACEMENT.search(question) or bool(REPAIR_PART.search(question)))
            and any(c.document in PRICED and c.heading not in FIXED_SECTIONS for c in chunks))


def _fact(chunk: Chunk) -> str:
    return (f"{chunk.text} [source: {chunk.document}, {chunk.heading}"
            f"{', effective ' + chunk.effective_date if chunk.effective_date else ''}]")


def answer(question: str, searcher, threshold: float) -> FlowResult:
    results = searcher.search(question, mode="combined")
    # Combined search always keeps meaning search's first result, so this is the top meaning score (R28, R32).
    if not results or max(r.meaning_score for r in results) < threshold:
        return FlowResult([], "handoff", handoff_reason="not enough evidence")
    chunks = [r.chunk for r in results]
    # The final-price line is for repair prices that vary by job, not fixed fees, tune-ups, memberships or replacements;
    # it comes with the price book sentence it restates.
    reply_type = "price answer" if _varies_by_job(question, chunks) else "policy answer"
    if reply_type == "price answer" and FINAL_PRICE_SOURCE.chunk_id not in {c.chunk_id for c in chunks}:
        chunks.append(FINAL_PRICE_SOURCE)
    facts = [_fact(c) for c in chunks]
    sources = list(dict.fromkeys(c.document for c in chunks))
    passages = [f"{c.document} ({c.effective_date or 'undated'}), {c.heading}" for c in chunks]
    excluded = list(dict.fromkeys(old for document in sources for old in SUPERSEDED.get(document, [])))
    if SAVINGS.search(question):
        facts = facts + [NO_ESTIMATE]
    return FlowResult(facts + ([FINAL_PRICE] if reply_type == "price answer" else []), reply_type, sources,
                      passages=passages, excluded=excluded, chunks=chunks)
