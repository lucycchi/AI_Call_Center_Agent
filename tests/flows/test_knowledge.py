import time

import pytest

from app.flows.knowledge import answer
from app.knowledge.index import Chunk
from app.knowledge.search import ScoredChunk
from app.replies.checks import CheckedStream


def chunk(text, document="services/service_catalog.md", heading="Plumbing (residential)"):
    return Chunk("services__service_catalog#5", document, heading, "2026-02-10", text, 31, 36)


class FakeSearcher:
    def __init__(self, results):
        self.results = results

    def search(self, question, mode="combined", k=5):
        return self.results


def test_a_weak_match_hands_off_for_lack_of_evidence():
    searcher = FakeSearcher([ScoredChunk(chunk("Drain clearing ($149 - $290)"), 0.21, 3.0)])
    result = answer("how much is drain clearing", searcher, threshold=0.4)
    assert result.handoff_reason == "not enough evidence" and result.reply_type == "handoff"


def test_a_price_answer_carries_its_source_and_the_final_price_line():
    searcher = FakeSearcher([ScoredChunk(chunk("Drain clearing ($149 - $290 depending on access)"), 0.71, 3.0)])
    result = answer("how much does it cost to clear a clogged drain", searcher, threshold=0.4)
    assert result.reply_type == "price answer" and result.handoff_reason is None
    assert result.sources == ["services/service_catalog.md", "pricing/repair_price_book_2026.csv"]  # the final-price line's
    facts = " ".join(result.facts)
    assert "services/service_catalog.md" in facts and "the technician confirms the final price on site" in facts


def test_a_policy_answer_has_no_price_line():
    searcher = FakeSearcher([ScoredChunk(chunk("Memberships do not transfer to a new address.",
                                               "membership/comfort_club_overview.md", "Transfer"), 0.66, 2.0)])
    result = answer("does my membership move with me", searcher, threshold=0.4)
    assert result.reply_type == "policy answer"
    assert "final price" not in " ".join(result.facts)


def test_the_first_checked_sentence_is_released_within_the_time_budget():
    searcher = FakeSearcher([ScoredChunk(chunk("Drain clearing ($149 - $290)"), 0.71, 3.0)])

    def slow_writer():
        time.sleep(1.0)
        yield "Drain clearing usually runs $149 to $290."
        yield "The technician confirms the final price on site."

    arrived = time.monotonic()
    answer("how much is drain clearing", searcher, threshold=0.4)
    first = next(iter(CheckedStream(slow_writer(), money_check=lambda sentence, previous: True)))
    assert first and time.monotonic() - arrived < 2.5


BOOK, CATALOG = "pricing/repair_price_book_2026.csv", "services/service_catalog.md"


@pytest.mark.parametrize("question, document, heading, text", [
    ("How much does it cost to clear a clogged drain?", BOOK, "Plumbing", "- Drain clearing: $149 to $290"),
    ("How much is a capacitor replacement?", CATALOG, "HVAC Repair", "| Capacitor replacement | $180 – $260 |"),
    ("How much is labor on a compressor?", BOOK, "HVAC repair", "- Compressor replacement labor: $600 to $900"),
])
def test_a_repair_price_that_varies_by_job_gets_the_final_price_line_and_its_source(question, document, heading, text):
    result = answer(question, FakeSearcher([ScoredChunk(chunk(text, document, heading), 0.7, 2.0)]), threshold=0.25)
    facts = " ".join(result.facts)
    assert result.reply_type == "price answer" and "the technician confirms the final price on site" in facts
    assert "Typical prices. The technician confirms the final price on site. [source: pricing/repair_price_book_2026.csv" in facts
    assert "pricing/repair_price_book_2026.csv (2026), 2026 Repair Price Book" in result.passages
    assert BOOK in result.sources and any("confirms the final price" in c.text for c in result.chunks)


@pytest.mark.parametrize("question, document, heading, text", [
    ("How much is a tune-up for non-members?", CATALOG, "Maintenance tune-up", "- $129 for non-members (one system)."),
    ("How much is a tune-up?", BOOK, "HVAC repair", "- Run capacitor replacement: $180 to $260"),
    ("What happens if I cancel the same day? Is there a fee?", BOOK, "Fee", "- Late cancellation: $49"),
    ("Is the after-hours emergency fee $129?", BOOK, "Fee", "- After-hours dispatch: $149 (Waived for members)"),
    ("Is the diagnostic fee still $79?", CATALOG, "HVAC Repair", "Diagnostic visit ($89, credited toward repair)."),
    ("My system is 18 years old and I'm thinking about replacing it. What would that cost?", CATALOG, "System replacement",
     "- Free in-home estimate with a Comfort Advisor."),
    ("How much to replace my water heater?", BOOK, "Plumbing", "- Water heater replacement, 50gal tank: $1800 to $2600"),
    ("What's the exact price of a new Trane XR16 heat pump?", CATALOG, "HVAC Repair", "| Compressor replacement | $600 – $900 |"),
])
def test_fixed_fees_tune_ups_and_replacements_get_no_final_price_line(question, document, heading, text):
    result = answer(question, FakeSearcher([ScoredChunk(chunk(text, document, heading), 0.7, 2.0)]), threshold=0.25)
    assert result.reply_type == "policy answer" and "final price" not in " ".join(result.facts)
    assert not any("Repair Price Book" in p for p in result.passages)
