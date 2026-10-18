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
    assert coverage(questions) is None  # no caller questions to measure


def test_stale_trap_passes_only_when_the_current_fact_is_found_and_nothing_excluded_comes_back():
    current = [chunk(0, "faq__customer_faq", 14, 19)]
    assert stale_trap_passes(current, [A]) is True
    stale = current + [chunk(1, "faq__faq_old_copy", 1, 5, document="faq/faq_old_copy.md")]
    assert stale_trap_passes(stale, [A]) is False
    assert stale_trap_passes([chunk(2, "faq__customer_faq", 1, 3)], [A]) is False


class FakeSearcher:
    def __init__(self, results_by_mode):
        self.results_by_mode = results_by_mode
        self.chunks = []

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
    searcher = FakeSearcher({"combined": [chunk(1, "faq__customer_faq", 14, 19)], "keyword": []})
    seen = []

    def writer(question, context):
        seen.append(context)
        return f"answer from {len(context)} characters"

    out = tmp_path / "answers.jsonl"
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89", "evidence_spans": [A]}],
                     searcher, writer, whole_kb="WHOLE KNOWLEDGE BASE TEXT", out=out)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert {r["mode"] for r in rows} == {"keyword", "combined", "whole_kb"}
    assert any("WHOLE KNOWLEDGE BASE TEXT" in c for c in seen)
    assert all(r["reference_answer"] == "$89" for r in rows)


def test_question_set_has_the_case_questions_stale_traps_and_unanswerable_ones():
    questions = build_questions()
    kinds = {q["kind"] for q in questions}
    assert kinds == {"answerable", "stale_trap", "unanswerable"}
    assert sum(q["kind"] == "stale_trap" for q in questions) >= 6
    assert sum(q["kind"] == "unanswerable" for q in questions) >= 4
    assert sum(q.get("case_id") is not None for q in questions) == 13
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


# Milestone 2 gate fixes.

def test_coverage_is_the_call_weighted_share_of_caller_questions_the_documents_answer():
    questions = [{"case_id": "a", "calls_weight": 3, "evidence_spans": [A], "handled_reason": True},
                 {"case_id": "b", "calls_weight": 1, "evidence_spans": [], "handled_reason": True},
                 {"case_id": None, "evidence_spans": [], "handled_reason": True}]
    assert coverage(questions) == 0.75


def test_the_run_settings_record_versions_limits_and_voyage_settings():
    from eval.retrieval_eval import run_settings
    settings = run_settings(answer_cost_usd=0.5)
    for key in ("anthropic_sdk", "voyage_sdk", "embedding_model", "voyage_input_type", "voyage_timeout_s", "voyage_retries",
                "writer_model", "writer_max_tokens", "writer_effort", "retries", "anthropic_timeout_s", "run_cap_usd", "top_k"):
        assert settings[key] is not None, key


def test_unanswerable_questions_outside_the_handled_reasons_are_marked():
    marked = {q["question"]: q["handled_reason"] for q in build_questions() if q["kind"] == "unanswerable"}
    assert marked["Can I set up autopay for my membership?"] is False
    assert marked["How much would you charge to replace four rooftop units at my strip mall?"] is False
    assert marked["Do you give a discount for veterans?"] is True


def test_excluded_documents_come_from_the_document_list():
    from eval.retrieval_eval import excluded_documents
    excluded = excluded_documents()
    assert "faq/faq_old_copy.md" in excluded and "internal/agent_discretion_notes.md" in excluded
    assert "faq/customer_faq.md" not in excluded


def test_report_checks_the_index_holds_no_excluded_document_and_names_the_set():
    searcher = FakeSearcher({m: [chunk(1, "faq__customer_faq", 14, 19)] for m in ("keyword", "meaning", "combined")})
    searcher.chunks = [chunk(1, "faq__customer_faq", 14, 19)]
    report = compare_modes([{"qid": "q1", "question": "fee?", "kind": "stale_trap", "evidence_spans": [A]}], searcher, "working")
    assert report["set"] == "working"
    assert report["index_has_excluded_documents"] is False
    assert report["combined"]["stale_trap_hit_at_5"] == 1.0


def test_answers_come_from_keyword_and_combined_search_and_the_whole_knowledge_base(tmp_path):
    searcher = FakeSearcher({"combined": [chunk(1, "faq__customer_faq", 14, 19)], "keyword": [chunk(0, "faq__customer_faq", 1, 3)]})
    out = tmp_path / "answers.jsonl"
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89", "evidence_spans": [A]}],
                     searcher, lambda q, c: "a", whole_kb="KB", out=out)
    assert {json.loads(l)["mode"] for l in out.read_text().splitlines()} == {"keyword", "combined", "whole_kb"}


class FakeUsage:
    input_tokens, output_tokens = 1_000_000, 100_000


def test_the_writer_uses_the_test_key_one_retry_and_stops_at_the_run_cap(monkeypatch):
    import eval.retrieval_eval as retrieval
    made = {}

    class Messages:
        def create(self, **kwargs):
            class Block:
                type, text = "text", "answer"

            class Response:
                content, usage = [Block()], FakeUsage()
            return Response()

    class Client:
        def __init__(self, **kwargs):
            made.update(kwargs)
            self.messages = Messages()

    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("anthropic.Anthropic", Client)
    write = retrieval.sonnet_writer(cap_usd=6.0)
    assert made["api_key"] == "test-key" and made["max_retries"] == 1
    write("q", "c")  # $2 input + $1 output at Sonnet 5.5 prices
    write("q", "c")
    import pytest
    with pytest.raises(retrieval.BudgetExceeded):
        write("q", "c")


def test_the_writer_refuses_to_fall_back_to_the_live_key(monkeypatch):
    import pytest

    import eval.retrieval_eval as retrieval
    monkeypatch.delenv("EVAL_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        retrieval.sonnet_writer()


def test_a_failed_answer_run_leaves_the_previous_answers_in_place(tmp_path):
    import pytest
    out = tmp_path / "answers.jsonl"
    out.write_text("previous answers\n")
    searcher = FakeSearcher({"combined": [], "keyword": []})

    def failing(question, context):
        raise RuntimeError("API error")

    with pytest.raises(RuntimeError):
        answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "evidence_spans": [A]}],
                         searcher, failing, whole_kb="KB", out=out)
    assert out.read_text() == "previous answers\n"
