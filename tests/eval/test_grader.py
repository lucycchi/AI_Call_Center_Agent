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
    return Attempt("c1", db_path=str(db), conversation=[{"role": "caller", "text": "book"},
                                                        {"role": "agent", "text": "Monday, October 19, 8am to 12pm. Book it?"},
                                                        {"role": "caller", "text": "yes"}, {"role": "agent", "text": "Booked."}],
                   done_events=[{"db_actions": []}, {"db_actions": ["booked appointment 160"] if booked else []}])


def test_a_booking_case_is_checked_in_the_database_copy(tmp_path):
    from eval.grade_conversations import database_checks
    assert database_checks(_case("hvac repair"), _attempt_with_db(tmp_path)) == {"booking_correct": True,
                                                                                 "no_unexpected_writes": True}
    missing = database_checks(_case("hvac repair"), _attempt_with_db(tmp_path / "x", booked=False))
    assert missing["booking_correct"] is False and missing["booking_problems"]


def test_conversations_are_graded_by_codex_and_the_database_together(tmp_path):
    from eval.grade_conversations import grade_attempts
    attempt = _attempt_with_db(tmp_path)
    runner = FakeRunner(lambda i: {"correct": True, "requests": [{"request": "hvac repair", "correct": True}]})
    [graded] = grade_attempts([attempt], {"c1": _case("hvac repair")}, runner, tickets=lambda a: [])
    assert graded.all_correct is True and graded.grades["booking_correct"] is True
    no_booking = _attempt_with_db(tmp_path / "y", booked=False)
    [graded] = grade_attempts([no_booking], {"c1": _case("hvac repair")}, runner, tickets=lambda a: [])
    assert graded.all_correct is False  # Codex said fine, but nothing was booked in the database copy


def test_the_rubric_settles_the_close_cases():
    rubric = (ROOT / "eval" / "grader_prompt.md").read_text()
    assert "a guess beyond the documents" in rubric and "fails, even when a caveat follows it" in rubric
    assert "the technician confirms the final price on site\", is a key fact" in rubric
    assert "whatever its passages contained" in rubric


@pytest.mark.parametrize("error", ["ERROR: Selected model is at capacity. Please try a different model.",
                                   "ERROR: exceeded retry limit, last status: 429 Too Many Requests"])
def test_codex_at_capacity_or_rate_limited_is_retried(monkeypatch, error):
    import eval.grader as grader
    calls = []

    class Result:
        stdout, stderr = error, ""

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 2:
            Path(command[command.index("-o") + 1]).write_text("[]")
        return Result()
    monkeypatch.setattr(grader.subprocess, "run", fake_run)
    monkeypatch.setattr(grader.time, "sleep", lambda s: None)
    assert grader.codex_runner("PROMPT") == "[]" and len(calls) == 2


def test_the_grader_is_given_the_membership_renewal_price(tmp_path):
    import shutil
    from eval.grade_conversations import _account_facts
    db = tmp_path / "c.sqlite"
    shutil.copy(ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite", db)
    facts = _account_facts({"caller_card": {"customer_id": "MHC-10001", "membership_tier": "standard"}, "fixtures": []}, str(db))
    assert facts["membership_renewal_price"] == "$189.00 a year, the current published price"


class FakeOpenAI:
    def __init__(self):
        self.responses, self.calls = self, 0

    def create(self, model, input, max_output_tokens):
        self.calls += 1
        usage = type("Usage", (), {"input_tokens": 1_000_000, "output_tokens": 0})()
        return type("Response", (), {"output_text": "[]", "usage": usage})()


def test_the_api_grader_fallback_runs_under_the_run_budget(monkeypatch):
    from eval.budget import BudgetExceeded, RunBudget
    from eval.grader import GraderError, api_runner
    monkeypatch.setenv("GRADER_MODEL", "some-model")
    monkeypatch.setenv("GRADER_MAX_OUTPUT_TOKENS", "100000")
    monkeypatch.delenv("GRADER_PRICES_PER_MILLION", raising=False)
    with pytest.raises(GraderError):  # without prices the cap cannot be enforced, so it does not run
        api_runner("PROMPT", budget=RunBudget(8.0), client=FakeOpenAI())
    monkeypatch.setenv("GRADER_PRICES_PER_MILLION", "3,10")
    budget, client = RunBudget(8.0), FakeOpenAI()
    assert api_runner("PROMPT", budget=budget, client=client) == "[]"
    api_runner("PROMPT", budget=budget, client=client)
    budget.spent_usd = 7.5  # $1 of output could still be written, which would cross the $8 cap
    with pytest.raises(BudgetExceeded):  # so the call is refused before it is made, not charged after it overshoots
        api_runner("PROMPT", budget=budget, client=client)
    assert client.calls == 2 and budget.spent_usd == 7.5  # the refused call was never made


def _check_files(tmp_path, monkeypatch, n=40):
    import csv as csvmod

    import eval.grader_check as check
    results = tmp_path / "retrieval"
    results.mkdir()
    verdicts = [Verdict(f"q{k}|combined", correct=k % 2 == 0, model="m") for k in range(n)]
    write_verdicts(verdicts, results / "verdicts.jsonl")
    (results / "answers_to_grade.jsonl").write_text("".join(json.dumps({"qid": f"q{k}", "mode": "combined", "question": "q",
                                                                        "answer": "a", "reference_answer": "r"}) + "\n"
                                                            for k in range(n)))
    for name, value in {"RESULTS": results, "SHEET": tmp_path / "sheet.csv", "HIDDEN": tmp_path / "hidden.json",
                        "OUT": tmp_path}.items():
        monkeypatch.setattr(check, name, value)
    return check, csvmod


def test_rewriting_the_grader_check_sheet_keeps_every_grade_already_given(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    rows = list(csvmod.DictReader(check.SHEET.open()))
    for row in rows:
        row["fable_correct (yes or no)"], row["claude_correct (yes or no)"] = "yes", "no"
    with check.SHEET.open("w", newline="") as handle:
        writer = csvmod.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    check.write_sheet()
    again = list(csvmod.DictReader(check.SHEET.open()))
    assert [r["id"] for r in again] == [r["id"] for r in rows]
    assert all(r["fable_correct (yes or no)"] == "yes" and r["claude_correct (yes or no)"] == "no" for r in again)


def test_the_sheet_is_not_rewritten_if_graded_answers_would_be_dropped(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.SHEET.write_text("id,question,answer,reference_answer,author_correct (yes or no),fable_correct (yes or no)\n"
                           "old|combined,q,a,r,,yes\n")
    with pytest.raises(SystemExit):
        check.write_sheet()
    assert "old|combined" in check.SHEET.read_text()


def test_the_table_reads_fables_column_unless_the_author_graded(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    rows = list(csvmod.DictReader(check.SHEET.open()))
    hidden = json.loads(check.HIDDEN.read_text())
    for row in rows:
        row["fable_correct (yes or no)"] = "yes" if hidden[row["id"]] else "no"
    with check.SHEET.open("w", newline="") as handle:
        writer = csvmod.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    check.write_table()
    table = json.loads((tmp_path / "grader_check.json").read_text())
    assert table["agreement"] == 1.0 and "Fable" in table["checker"] and table["graded"] == len(rows)
    rows[0]["author_correct (yes or no)"] = "no" if hidden[rows[0]["id"]] else "yes"
    with check.SHEET.open("w", newline="") as handle:
        writer = csvmod.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    check.write_table()
    table = json.loads((tmp_path / "grader_check.json").read_text())
    assert table["checker"] == "author" and table["graded"] == 1 and table["agreement"] == 0.0


def test_answers_keep_the_passages_they_were_written_from_and_are_graded_against_them(tmp_path):
    from app.knowledge.index import Chunk
    from app.knowledge.search import ScoredChunk
    from eval.grade_retrieval import answer_items
    from eval.retrieval_eval import answer_both_ways

    class Searcher:
        def __init__(self, text):
            self.text = text

        def search(self, question, mode="combined", k=5):
            return [ScoredChunk(Chunk("faq#1", "faq/customer_faq.md", "Fees", "2026-03-02", self.text, 14, 19), 0.7, 2)]
    out = tmp_path / "answers.jsonl"
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89"}],
                     Searcher("Diagnostic fee: $89."), lambda q, c: "$89", whole_kb="KB", out=out)
    answers = [json.loads(line) for line in out.read_text().splitlines()]
    assert answers[1]["passages"] == ["[faq/customer_faq.md, Fees, 2026-03-02] Diagnostic fee: $89."]
    items = answer_items(answers, Searcher("The index changed since."))
    assert items[1]["passages"] == ["[faq/customer_faq.md, Fees, 2026-03-02] Diagnostic fee: $89."]
    assert not items[1].get("passages_searched_again")
    old = answer_items([{k: v for k, v in answers[1].items() if k != "passages"}], Searcher("Searched again."))
    assert old[0]["passages_searched_again"] is True and "Searched again." in old[0]["passages"][0]


def test_a_grade_is_not_carried_onto_a_changed_answer(tmp_path, monkeypatch):
    check, csvmod = _check_files(tmp_path, monkeypatch)
    check.write_sheet()
    rows = list(csvmod.DictReader(check.SHEET.open()))
    for row in rows:
        row["fable_correct (yes or no)"] = "yes"
    with check.SHEET.open("w", newline="") as handle:
        writer = csvmod.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    answers = check.RESULTS / "answers_to_grade.jsonl"
    answers.write_text(answers.read_text().replace('"answer": "a"', '"answer": "a new answer"'))
    with pytest.raises(SystemExit):  # the old grades would be lost or misattached
        check.write_sheet()
    check.write_sheet(new=True)
    again = list(csvmod.DictReader(check.SHEET.open()))
    assert all(not r["fable_correct (yes or no)"] and r["answer"] == "a new answer" for r in again)
    [archived] = list((tmp_path / "grader_check_archive").glob("*.csv"))
    assert "yes" in archived.read_text()


def test_items_the_grader_leaves_out_are_asked_again_once():
    from eval.grader import GraderError, grade
    items = [{"id": f"c{k}|1", "type": "conversation"} for k in range(3)]
    calls = []

    def runner(prompt):
        calls.append(prompt)
        ids = [i["id"] for i in json.loads(prompt.split("ITEMS:", 1)[1])]
        keep = ids[:-1] if len(calls) == 1 else ids  # the first answer leaves one item out
        return json.dumps([{"id": i, "correct": True} for i in keep])
    assert [v.id for v in grade(items, runner)] == [i["id"] for i in items] and len(calls) == 2
    with pytest.raises(GraderError):
        grade(items, lambda prompt: json.dumps([]))
