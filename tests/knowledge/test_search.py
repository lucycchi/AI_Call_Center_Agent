from pathlib import Path

import numpy as np
import pytest

from app.knowledge.index import Chunk, chunk_document
from app.knowledge.search import Searcher, fuse

ROOT = Path(__file__).resolve().parents[2]
KB_TEXT = ROOT / "data" / "kb_text"


def all_chunks():
    chunks = []
    for path in sorted(KB_TEXT.glob("*.md")):
        chunks += chunk_document(path)
    return chunks


class FakeEmbedder:
    """Maps text to a small vector by the words it contains, so meaning search is predictable in tests."""

    VOCAB = ["membership", "comfort", "club", "price", "plan", "warranty", "labor", "fee", "diagnostic", "hours", "holiday"]

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            lower = text.lower()
            rows.append([lower.count(word) for word in self.VOCAB])
        vectors = np.array(rows, dtype=float) + 1e-6
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def test_faq_is_split_into_one_chunk_per_section_with_source_details():
    chunks = chunk_document(KB_TEXT / "faq__customer_faq.md")
    headings = [c.heading for c in chunks]
    assert "Fees" in headings and "Scheduling" in headings and "Payment" in headings
    fees = next(c for c in chunks if c.heading == "Fees")
    assert fees.document == "faq/customer_faq.md"
    assert fees.effective_date == "2026-03-02"
    assert "$89" in fees.text
    assert fees.start_line < fees.end_line


def test_no_chunk_comes_from_an_excluded_document():
    documents = {c.document for c in all_chunks()}
    for excluded in ["faq/faq_old_copy.md", "services/scheduling_guide.md", "services/duct_cleaning.md",
                     "internal/agent_discretion_notes.md", "policies/escalation_and_safety.md"]:
        assert excluded not in documents


def test_keyword_search_finds_the_fees_section_for_diagnostic_fee():
    searcher = Searcher(all_chunks(), FakeEmbedder())
    top = searcher.search("what is the diagnostic fee", mode="keyword")[0]
    assert "diagnostic" in top.chunk.text.lower() and "$89" in top.chunk.text


def test_meaning_search_orders_by_similarity():
    searcher = Searcher(all_chunks(), FakeEmbedder())
    results = searcher.search("comfort club membership plan price", mode="meaning")
    assert "Comfort Club" in results[0].chunk.text
    scores = [r.meaning_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_combined_search_uses_both_lists_and_returns_at_most_five():
    chunks = [
        Chunk("a", "doc/a.md", "A", "", "zebra zebra zebra", 1, 2),
        Chunk("b", "doc/b.md", "B", "", "membership comfort club plan", 1, 2),
        Chunk("c", "doc/c.md", "C", "", "nothing here", 1, 2),
    ] + [Chunk(f"x{i}", f"doc/x{i}.md", "X", "", f"filler {i}", 1, 2) for i in range(6)]
    searcher = Searcher(chunks, FakeEmbedder())
    results = searcher.search("zebra membership plan", mode="combined")
    ids = [r.chunk.chunk_id for r in results]
    assert "a" in ids  # only keyword search ranks the zebra chunk highly
    assert "b" in ids  # meaning search ranks the membership chunk highly
    assert len(results) <= 5


def test_reciprocal_rank_fusion_ranks_b_first():
    assert fuse([["a", "b", "c"], ["b", "c", "a"]])[0] == "b"


def test_top_meaning_score_is_the_best_meaning_match():
    searcher = Searcher(all_chunks(), FakeEmbedder())
    best = searcher.search("holiday hours", mode="meaning")[0].meaning_score
    assert searcher.top_meaning_score("holiday hours") == pytest.approx(best)


def test_built_index_round_trips_and_searches_the_same(tmp_path):
    from app.knowledge.index import load_index
    from pipeline.build_index import build

    build(KB_TEXT, tmp_path, FakeEmbedder())
    chunks, embeddings = load_index(tmp_path)
    assert len(chunks) == len(all_chunks())
    assert embeddings.shape[0] == len(chunks)
    loaded = Searcher(chunks, FakeEmbedder(), embeddings)
    assert loaded.search("diagnostic fee", mode="keyword")[0].chunk.chunk_id == \
        Searcher(all_chunks(), FakeEmbedder()).search("diagnostic fee", mode="keyword")[0].chunk.chunk_id


def test_embedding_model_is_pinned():
    from app.config import SETTINGS

    assert SETTINGS.embedding_model == "voyage-4"


def test_no_chunk_is_only_a_title_and_a_date_line():
    for chunk in all_chunks():
        content = [line for line in chunk.text.splitlines()
                   if line.strip() and not line.startswith("#") and not line.startswith("_")]
        assert content, chunk.chunk_id


def test_combined_search_always_keeps_the_top_result_of_each_list():
    chunks = [Chunk("m", "doc/m.md", "M", "", "membership comfort club plan price", 1, 2),
              Chunk("k", "doc/k.md", "K", "", "zebra zebra zebra zebra", 1, 2)] + \
             [Chunk(f"x{i}", f"doc/x{i}.md", "X", "", f"zebra membership filler {i}", 1, 2) for i in range(12)]
    searcher = Searcher(chunks, FakeEmbedder())
    meaning_top = searcher.search("zebra membership comfort club plan price", mode="meaning")[0].chunk.chunk_id
    keyword_top = searcher.search("zebra membership comfort club plan price", mode="keyword")[0].chunk.chunk_id
    combined = [r.chunk.chunk_id for r in searcher.search("zebra membership comfort club plan price", mode="combined")]
    tops = list(dict.fromkeys([meaning_top, keyword_top]))
    assert combined[:len(tops)] == tops
    assert len(combined) == 5


def test_meaning_only_mode_is_available_for_the_comparison():
    searcher = Searcher(all_chunks(), FakeEmbedder())
    assert searcher.search("holiday hours", mode="meaning")
