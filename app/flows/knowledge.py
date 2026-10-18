"""Knowledge questions: answered only from retrieved passages, with their sources; a weak match hands off (R41)."""

import re

from app.flows.protocol import FlowResult

PRICE_WORDS = re.compile(r"\b(cost|costs|price|prices|pricing|how much|fee|fees|charge|charges|rate|\$)", re.I)
FINAL_PRICE = "Always add: the technician confirms the final price on site."


def answer(question: str, searcher, threshold: float) -> FlowResult:
    results = searcher.search(question, mode="combined")
    # Combined search always keeps meaning search's first result, so this is the top meaning score (R28, R32).
    if not results or max(r.meaning_score for r in results) < threshold:
        return FlowResult([], "handoff", handoff_reason="not enough evidence")
    facts = [f"{r.chunk.text} [source: {r.chunk.document}, {r.chunk.heading}"
             f"{', effective ' + r.chunk.effective_date if r.chunk.effective_date else ''}]" for r in results]
    sources = list(dict.fromkeys(r.chunk.document for r in results))
    if PRICE_WORDS.search(question):
        return FlowResult(facts + [FINAL_PRICE], "price answer", sources)
    return FlowResult(facts, "policy answer", sources)
