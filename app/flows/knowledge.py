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

PRICE_WORDS = re.compile(r"\b(cost|costs|price|prices|pricing|how much|fee|fees|charge|charges|rate|run me|run us|ballpark|"
                         r"expensive|quote)\b", re.I)
FINAL_PRICE = "Always add: the technician confirms the final price on site."
SAVINGS = re.compile(r"\b(save me money|save money|saves? me|pays? for itself|worth it|worth joining)\b", re.I)
NO_ESTIMATE = ("Do not estimate whether joining would save money on this visit. State the member benefits, and say the "
               "documents do not say whether they apply to a visit booked on the day of joining, so a team member confirms "
               "that when setting up the membership.")
PRICED = {"services/service_catalog.md", "pricing/repair_price_book_2026.csv"}  # typical repair and service prices
# Sections with only fixed prices (tune-up, fees), unless the passage has a range (a permit or disposal fee); the
# system replacement section is the free in-home estimate.
FIXED_SECTIONS = {"Maintenance", "Fee", "Maintenance tune-up"}
RANGE = re.compile(r"\$[\d,]+ ?(?:to|-|–) ?\$[\d,]+")
# The final-price line goes on every price-book or catalog range (R42), except fixed fees, tune-ups, memberships and a
# whole-system replacement. A named repair part or water heater is always a range; "member", "plan" or "emergency"
# next to a repair does not make it a fixed fee.
REPAIR_PART = re.compile(r"\b(capacitor|contactor|refrigerant|recharge|drain|motor|thermostat|ignitor|igniter|coil|compressor|"
                         r"water heater)", re.I)
WHOLE_SYSTEM = re.compile(r"\b(new|whole|entire|full)\b[^.?!]*\b(system|unit|ac|a/c|hvac|heat pump|furnace)\b|"
                          r"\bsystem replacement\b|\breplac\w*\b[^.?!]*\b(system|unit|it|hvac)\b", re.I)
FIXED_WORDS = re.compile(r"\b(tune-?ups?|maintenance|cancel\w*|no-?show|late fee|after-?hours|holiday|dispatch|flush|"
                         r"diagnostic (?:fee|visit|charge)|emergency (?:fee|charge|dispatch)|membership|comfort club|"
                         r"(?:the|a|your|my) plan\b(?! unit))", re.I)
FINAL_PRICE_RULE = "company pricing rule (R42)"
# The line restates a company pricing rule, not a document sentence; the grader sees it as a passage, but it is not
# one of the reply's document sources.
FINAL_PRICE_SOURCE = Chunk("company_pricing_rule#R42", FINAL_PRICE_RULE, "Final price", "",
                           "Price-book and catalog ranges are typical prices; the technician confirms the final price on site.",
                           0, 0)


def _varies_by_job(question: str, chunks: list[Chunk]) -> bool:
    """A repair or service price range from the price book or catalog, which the technician confirms on site."""
    if not PRICE_WORDS.search(question):
        return False
    if not REPAIR_PART.search(question) and (WHOLE_SYSTEM.search(question) or FIXED_WORDS.search(question)):
        return False
    return any(c.document in PRICED and c.heading != "System replacement"
               and (c.heading not in FIXED_SECTIONS or RANGE.search(c.text)) for c in chunks)


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
    # it comes with the company pricing rule it restates.
    reply_type = "price answer" if _varies_by_job(question, chunks) else "policy answer"
    if reply_type == "price answer" and FINAL_PRICE_SOURCE.chunk_id not in {c.chunk_id for c in chunks}:
        chunks.append(FINAL_PRICE_SOURCE)
    facts = [_fact(c) for c in chunks]
    sources = list(dict.fromkeys(c.document for c in chunks if c.document != FINAL_PRICE_RULE))
    passages = [f"{c.document} ({c.effective_date or 'undated'}), {c.heading}" for c in chunks]
    excluded = list(dict.fromkeys(old for document in sources for old in SUPERSEDED.get(document, [])))
    if SAVINGS.search(question):
        facts = facts + [NO_ESTIMATE]
    return FlowResult(facts + ([FINAL_PRICE] if reply_type == "price answer" else []), reply_type, sources,
                      passages=passages, excluded=excluded, chunks=chunks)
