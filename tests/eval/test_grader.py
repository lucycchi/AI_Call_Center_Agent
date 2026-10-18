import json
from pathlib import Path

import pytest

from eval.grader import Verdict, agreement_table, choose_check_sample, codex_command, grade, runner_for, write_verdicts

ROOT = Path(__file__).resolve().parents[2]


def item(n, kind="knowledge answer"):
    return {"id": f"i{n}", "type": kind, "question": "q", "answer": "a", "reference_answer": "r", "passages": []}


class FakeRunner:
    def __init__(self, verdict=lambda i: {"correct": True}):
        self.prompts, self.verdict = [], verdict

    def __call__(self, prompt):
        self.prompts.append(prompt)
        ids = [i["id"] for i in json.loads(prompt[prompt.index("ITEMS:") + 6:])]
        return json.dumps([{"id": i, "model": "gpt-5.6-sol", **self.verdict(i)} for i in ids])


def test_verdicts_are_parsed_with_the_model_name_and_written_out(tmp_path):
    verdicts = grade([item(1), item(2)], FakeRunner())
    assert [v.id for v in verdicts] == ["i1", "i2"] and all(v.correct and v.model == "gpt-5.6-sol" for v in verdicts)
    write_verdicts(verdicts, tmp_path / "verdicts.jsonl")
    assert len((tmp_path / "verdicts.jsonl").read_text().splitlines()) == 2


def test_the_command_is_read_only_and_ephemeral_with_the_pinned_model():
    command = codex_command("PROMPT", "/tmp/out.txt")
    assert command[:2] == ["codex", "exec"] and "-s" in command and command[command.index("-s") + 1] == "read-only"
    assert "--ephemeral" in command and command[command.index("-m") + 1] == "gpt-5.6-sol" and command[-1] == "PROMPT"


def test_45_answers_make_three_runs_of_20_20_and_5():
    runner = FakeRunner()
    grade([item(n) for n in range(45)], runner)
    sizes = [len(json.loads(p[p.index("ITEMS:") + 6:])) for p in runner.prompts]
    assert sizes == [20, 20, 5]
    assert (ROOT / "eval" / "grader_prompt.md").read_text().strip() in runner.prompts[0]


def test_a_partial_verdict_is_a_fail():
    [verdict] = grade([item(1)], FakeRunner(lambda i: {"correct": "partial"}))
    assert verdict.correct is False


def test_tickets_are_graded_on_whether_staff_could_act_without_asking_again():
    prompt = (ROOT / "eval" / "grader_prompt.md").read_text()
    assert "without asking the caller to repeat anything" in prompt
    [verdict] = grade([item(1, "ticket")], FakeRunner(lambda i: {"ticket_actionable": False}))
    assert verdict.ticket_actionable is False


def test_the_check_sample_spreads_across_right_and_wrong_and_agreement_is_tabled():
    verdicts = [Verdict(f"v{n}", correct=n % 3 != 0, model="m") for n in range(60)]
    sample = choose_check_sample(verdicts, n=30, seed=11)
    assert len(sample) == 30 and sum(v.correct for v in sample) >= 10 and sum(not v.correct for v in sample) >= 10
    assert choose_check_sample(verdicts, n=30, seed=11) == sample
    table = agreement_table([True, True, False, False], [True, False, False, True])
    assert (table["both_right"], table["both_wrong"], table["author_only"], table["grader_only"], table["agreement"]) == \
        (1, 1, 1, 1, 0.5)


def test_the_api_fallback_is_chosen_by_setting(monkeypatch):
    monkeypatch.setenv("GRADER_BACKEND", "api")
    assert runner_for().__name__ == "api_runner"
    monkeypatch.setenv("GRADER_BACKEND", "codex")
    assert runner_for().__name__ == "codex_runner"


def test_the_adversarial_set_covers_every_required_topic_and_staff_pattern():
    from pipeline.staff_checks import errors_in  # noqa: F401  (the seven patterns live there)
    cases = [json.loads(p.read_text()) for p in sorted((ROOT / "eval" / "adversarial").glob("*.json"))]
    assert len(cases) >= 30
    topics = {c["topic"] for c in cases}
    required = {"prompt injection", "print your instructions", "members-only slot", "someone else's account",
                "promised refund", "gas smell", "carbon monoxide", "burning smell", "unzoned area", "north plumbing",
                "omar invoice", "late technician", "waitlist", "abuse", "another language", "nonsense"}
    assert required <= topics, required - topics
    patterns = {c.get("staff_pattern") for c in cases} - {None}
    assert patterns == {"offered a waitlist", "booked a burning smell as a normal visit", "promised a manager callback today",
                        "moved a next-day appointment without the $49 fee",
                        "explained an invoice as the diagnostic fee plus the repair", "dropped a booking the caller asked for",
                        "promised a refund callback in two business days"}
    for c in cases:
        assert c["lines"] and c["checks"], c["id"]


def test_a_booking_rule_break_is_reported(tmp_path):
    from eval.run_adversarial import run_adversarial
    from app.core.types import DoneEvent, SentenceEvent

    class BooksAnything:
        def handle(self, turn):
            yield SentenceEvent("Booked: your HVAC repair visit.")
            yield DoneEvent(route="scheduling", ticket=None, db_actions=["booked appointment 160"])

    result = run_adversarial(lambda db, ops: BooksAnything(), folder=tmp_path, only=["members-only slot"])
    assert result.booking_rule_pass_rate < 1.0 and result.failures


def test_retrieval_answers_are_graded_into_answer_scores_by_mode(tmp_path):
    from eval.grade_retrieval import answer_items, answer_scores
    from app.knowledge.index import Chunk
    from app.knowledge.search import ScoredChunk

    class Searcher:
        def search(self, question, mode="combined", k=5):
            return [ScoredChunk(Chunk("faq#1", "faq/customer_faq.md", "Fees", "2026-03-02", "Diagnostic fee: $89.", 14, 19), 0.7, 2)]
    answers = [{"qid": "q1", "kind": "answerable", "mode": m, "question": "fee?", "answer": "$89", "reference_answer": "$89"}
               for m in ("keyword", "combined", "whole_kb")]
    items = answer_items(answers, Searcher())
    assert [i["passages"] for i in items][:2] == [["[faq/customer_faq.md, Fees, 2026-03-02] Diagnostic fee: $89."]] * 2
    assert items[2]["passages"] == [] and items[2]["whole_knowledge_base"] is True
    verdicts = grade(items, FakeRunner(lambda i: {"correct": i != "q1|keyword", "faithful": True}))
    scores = answer_scores(items, verdicts)
    assert scores["combined"]["correct"] == 1.0 and scores["keyword"]["correct"] == 0.0 and scores["whole_kb"]["faithful"] is None


def _case(sub, outcome="contained", requests=None, card="MHC-10001"):
    return {"case_id": "c1", "calls_weight": 1, "reason": "new booking", "sub_reason": sub, "expected_outcome": outcome,
            "expected_handoff_reason": None, "needs_documents": False, "reference_answer": None, "evidence_spans": [],
            "fixtures": [], "caller_script": ["hi"], "caller_card": {"customer_id": card, "name": "Linda Foster"},
            "appointment": None,
            "requests": requests or [{"request": sub, "kind": "sub-reason", "expected_outcome": outcome, "handoff_reason": None}]}


def _attempt_with_db(tmp_path, booked=True):
    import shutil
    import sqlite3
    from eval.harness import Attempt
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "c.sqlite"
    shutil.copy(ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite", db)
    if booked:
        conn = sqlite3.connect(db)
        conn.execute("update appointment_slots set status='booked' where slot_id=56")
        conn.execute("insert into appointments (slot_id, customer_id, issue_description, created_at, status) "
                     "values (56, 'MHC-10001', 'x', '2026-10-16T09:00', 'scheduled')")
        conn.commit()
    return Attempt("c1", db_path=str(db), conversation=[{"role": "caller", "text": "book"}, {"role": "agent", "text": "Booked."}],
                   done_events=[{"db_actions": ["booked appointment 160"] if booked else []}])


def test_a_booking_case_is_checked_in_the_database_copy(tmp_path):
    from eval.grade_conversations import database_checks
    assert database_checks(_case("hvac repair"), _attempt_with_db(tmp_path)) == {"booking_correct": True}
    assert database_checks(_case("hvac repair"), _attempt_with_db(tmp_path / "x", booked=False)) == {"booking_correct": False}


def test_conversations_are_graded_by_codex_and_the_database_together(tmp_path):
    from eval.grade_conversations import grade_attempts
    attempt = _attempt_with_db(tmp_path)
    runner = FakeRunner(lambda i: {"correct": True, "requests": [{"request": "hvac repair", "correct": True}]})
    [graded] = grade_attempts([attempt], {"c1": _case("hvac repair")}, runner, tickets=lambda a: [])
    assert graded.all_correct is True and graded.grades["booking_correct"] is True
    no_booking = _attempt_with_db(tmp_path / "y", booked=False)
    [graded] = grade_attempts([no_booking], {"c1": _case("hvac repair")}, runner, tickets=lambda a: [])
    assert graded.all_correct is False  # Codex said fine, but nothing was booked in the database copy
