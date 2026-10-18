import json
from pathlib import Path

from app.knowledge.index import Chunk
from eval.knowledge_questions import build_questions
from eval.retrieval_eval import (answer_both_ways, compare_modes, coverage, hit_at_k, recall_at_k,
                                 stale_trap_passes)

ROOT = Path(__file__).resolve().parents[2]


def chunk(cid, kb_stem, start, end, document="faq/customer_faq.md"):
    return Chunk(f"{kb_stem}#{cid}", document, "H", "", "text", start, end)


A = {"file": "faq__customer_faq.md", "heading": "Fees", "start_line": 14, "end_line": 19}
B = {"file": "warranty__warranty_policy.md", "heading": "Warranty transfer", "start_line": 27, "end_line": 30}


def test_recall_and_hit_count_spans_found_in_the_top_five():
    results = [chunk(0, "faq__customer_faq", 14, 19)]
    assert recall_at_k(results, [A, B]) == 0.5
    assert hit_at_k(results, [A, B]) is True
    assert hit_at_k([chunk(1, "faq__customer_faq", 1, 3)], [A]) is False


def test_a_chunk_overlapping_a_needed_span_by_one_line_counts_as_found():
    assert recall_at_k([chunk(0, "faq__customer_faq", 19, 25)], [A]) == 1.0
    assert recall_at_k([chunk(0, "faq__customer_faq", 20, 25)], [A]) == 0.0


def test_only_the_top_five_results_count():
    results = [chunk(i, "faq__customer_faq", 1, 2) for i in range(5)] + [chunk(9, "faq__customer_faq", 14, 19)]
    assert recall_at_k(results, [A]) == 0.0


def test_coverage_is_the_share_of_questions_the_documents_can_answer():
    questions = [{"evidence_spans": [A]}, {"evidence_spans": [B]}, {"evidence_spans": []}]
    assert round(coverage(questions), 3) == 0.667


def test_stale_trap_passes_only_when_the_current_fact_is_found_and_nothing_excluded_comes_back():
    current = [chunk(0, "faq__customer_faq", 14, 19)]
    assert stale_trap_passes(current, [A]) is True
    stale = current + [chunk(1, "faq__faq_old_copy", 1, 5, document="faq/faq_old_copy.md")]
    assert stale_trap_passes(stale, [A]) is False
    assert stale_trap_passes([chunk(2, "faq__customer_faq", 1, 3)], [A]) is False


class FakeSearcher:
    def __init__(self, results_by_mode):
        self.results_by_mode = results_by_mode

    def search(self, question, mode="combined", k=5):
        class Scored:
            def __init__(self, c):
                self.chunk = c
        return [Scored(c) for c in self.results_by_mode[mode]][:k]


def test_compare_modes_reports_keyword_and_combined_side_by_side():
    searcher = FakeSearcher({"keyword": [chunk(0, "faq__customer_faq", 1, 3)], "meaning": [chunk(1, "faq__customer_faq", 14, 19)],
                             "combined": [chunk(1, "faq__customer_faq", 14, 19)]})
    questions = [{"qid": "q1", "question": "fee?", "kind": "answerable", "evidence_spans": [A]}]
    report = compare_modes(questions, searcher)
    assert report["keyword"]["hit_at_5"] == 0.0
    assert report["combined"]["hit_at_5"] == 1.0
    assert report["combined"]["recall_at_5"] == 1.0
    assert report["meaning"]["hit_at_5"] == 1.0
    assert report["questions"] == 1


def test_answers_are_produced_from_combined_search_and_from_the_whole_knowledge_base(tmp_path):
    searcher = FakeSearcher({"combined": [chunk(1, "faq__customer_faq", 14, 19)]})
    seen = []

    def writer(question, context):
        seen.append(context)
        return f"answer from {len(context)} characters"

    out = tmp_path / "answers.jsonl"
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89", "evidence_spans": [A]}],
                     searcher, writer, whole_kb="WHOLE KNOWLEDGE BASE TEXT", out=out)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert {r["mode"] for r in rows} == {"combined", "whole_kb"}
    assert any("WHOLE KNOWLEDGE BASE TEXT" in c for c in seen)
    assert all(r["reference_answer"] == "$89" for r in rows)


def test_question_set_has_the_case_questions_stale_traps_and_unanswerable_ones():
    questions = build_questions()
    kinds = {q["kind"] for q in questions}
    assert kinds == {"answerable", "stale_trap", "unanswerable"}
    assert sum(q["kind"] == "stale_trap" for q in questions) >= 6
    assert sum(q["kind"] == "unanswerable" for q in questions) >= 4
    assert sum(q.get("case_id") is not None for q in questions) == 10
    for q in questions:
        assert q["set"] in {"working", "held_out"}
        if q["kind"] != "unanswerable":
            assert q["evidence_spans"] and q["reference_answer"], q["qid"]
        else:
            assert not q["evidence_spans"]
    assert len({q["qid"] for q in questions}) == len(questions)


def test_every_kind_of_question_has_both_working_and_held_out_examples():
    questions = build_questions()
    for kind in ("answerable", "stale_trap", "unanswerable"):
        sets = {q["set"] for q in questions if q["kind"] == kind}
        assert sets == {"working", "held_out"}, kind
