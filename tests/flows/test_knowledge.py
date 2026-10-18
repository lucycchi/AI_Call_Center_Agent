import time

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
    assert result.sources == ["services/service_catalog.md"]
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
