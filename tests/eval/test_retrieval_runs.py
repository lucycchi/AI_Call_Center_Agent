"""Retrieval answers carry the agent hash they were written under; grading refuses answers from another agent; each
answer set is kept and pooled once. Nothing here reaches a model, Codex or Voyage: every entry point is stubbed."""

import json

import pytest

from app.knowledge.index import Chunk
from app.knowledge.search import ScoredChunk


class Searcher:
    def search(self, question, mode="combined", k=5):
        return [ScoredChunk(Chunk("faq#1", "faq/customer_faq.md", "Fees", "2026-03-02", "Diagnostic fee: $89.", 14, 19), 0.7, 2)]


def _write_answers(folder, agent_hash, answer="$89"):
    from eval.retrieval_eval import answer_both_ways
    folder.mkdir(parents=True, exist_ok=True)
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89"}], Searcher(),
                     lambda q, c: answer, whole_kb="KB", out=folder / "answers_to_grade.jsonl", agent_hash=agent_hash)


def test_written_answers_record_the_agent_hash_and_their_own_hash(tmp_path):
    import hashlib
    _write_answers(tmp_path, "agent-a")
    meta = json.loads((tmp_path / "answers_meta.json").read_text())
    assert meta["agent_hash"] == "agent-a"
    assert meta["answers_sha256"] == hashlib.sha256((tmp_path / "answers_to_grade.jsonl").read_bytes()).hexdigest()


def test_grading_refuses_answers_written_under_another_agent_or_with_no_record(tmp_path):
    from eval.grade_retrieval import answers_to_grade
    _write_answers(tmp_path, "agent-a")
    answers, meta = answers_to_grade(tmp_path, "agent-a")
    assert len(answers) == 3 and meta["agent_hash"] == "agent-a"
    with pytest.raises(SystemExit, match="agent"):
        answers_to_grade(tmp_path, "agent-b")
    (tmp_path / "answers_meta.json").unlink()
    with pytest.raises(SystemExit, match="answers_meta"):
        answers_to_grade(tmp_path, "agent-a")
    _write_answers(tmp_path, "agent-a", answer="$99")
    (tmp_path / "answers_to_grade.jsonl").write_text((tmp_path / "answers_to_grade.jsonl").read_text().replace("$99", "$1"))
    with pytest.raises(SystemExit, match="changed"):  # the answers were edited after their record was written
        answers_to_grade(tmp_path, "agent-a")


def test_the_grading_command_refuses_before_anything_is_called(tmp_path, monkeypatch):
    import dotenv

    import app.knowledge.embedder as embedder
    import app.knowledge.index as index
    import eval.freeze as freeze
    import eval.grade_retrieval as grading

    def never(*args, **kwargs):
        raise AssertionError("a test must never reach the network or start grading")
    for module, name in [(dotenv, "load_dotenv"), (embedder, "VoyageEmbedder"), (index, "load_index"),
                         (grading, "grade"), (grading, "runner_for"), (grading, "keep_run")]:
        monkeypatch.setattr(module, name, never)
    monkeypatch.setattr(grading, "RESULTS", tmp_path)
    monkeypatch.setattr(freeze, "freeze_agent", lambda root=None: "agent-now")
    monkeypatch.setattr(freeze, "answers_hash", lambda root=None: "agent-now")
    _write_answers(tmp_path, "agent-then")
    with pytest.raises(SystemExit, match="agent"):
        grading.main()


def test_a_run_is_kept_under_the_answers_agent_and_an_identical_answer_set_is_kept_once(tmp_path):
    from eval.grade_retrieval import keep_run
    _write_answers(tmp_path, "agent-a")
    (tmp_path / "verdicts.jsonl").write_text(json.dumps({"id": "q1|combined", "correct": True}) + "\n")
    first = keep_run(tmp_path, "agent-a")
    assert first.parent == tmp_path / "runs" / "agent-a" and (first / "answers_sha256").read_text().strip()
    assert keep_run(tmp_path, "agent-a") is None  # the same answers graded again are not pooled twice
    assert len(list((tmp_path / "runs" / "agent-a").iterdir())) == 1
    _write_answers(tmp_path, "agent-a", answer="$89, plus the repair")
    second = keep_run(tmp_path, "agent-a")
    assert second is not None and second != first


def test_the_threshold_pools_each_answer_set_once(tmp_path):
    from eval.threshold import pooled_verdicts
    for run, digest, correct in [("1", "aaa", True), ("2", "aaa", False), ("3", "bbb", False)]:
        folder = tmp_path / "runs" / "now" / run
        folder.mkdir(parents=True)
        (folder / "verdicts.jsonl").write_text(json.dumps({"id": "q1|combined", "correct": correct}) + "\n")
        (folder / "answers_sha256").write_text(digest)
        (folder / "answers_to_grade.jsonl").write_text(json.dumps({"mode": "combined", "writer": "agent", "a": run}) + "\n")
    runs = pooled_verdicts(tmp_path, "now")
    assert sorted(v["q1|combined"]["correct"] for v in runs) == [False, True]  # run 2 repeats run 1's answers
    legacy = tmp_path / "runs" / "old"
    for run in ("1", "2"):  # older runs with no stored hash are told apart by their answers file
        (legacy / run).mkdir(parents=True)
        (legacy / run / "verdicts.jsonl").write_text(json.dumps({"id": "q1|combined", "correct": True}) + "\n")
        (legacy / run / "answers_to_grade.jsonl").write_text(json.dumps({"mode": "combined", "writer": "agent"}) + "\n")
    assert len(pooled_verdicts(tmp_path, "old")) == 1


def test_combined_answers_come_from_the_agents_own_knowledge_flow_and_writer(tmp_path):
    # The answer measures (R31) and the threshold curve (R32) must describe the agent, not a separate prompt.
    from eval.retrieval_eval import answer_both_ways
    out = tmp_path / "answers_to_grade.jsonl"
    answer_both_ways([{"qid": "q1", "question": "fee?", "kind": "answerable", "reference_answer": "$89"}], Searcher(),
                     lambda q, c: "simple prompt", whole_kb="KB", out=out,
                     agent_answer=lambda q: ("the agent's reply", ["[the agent's passage]"]))
    by_mode = {a["mode"]: a for a in map(json.loads, out.open())}
    assert by_mode["combined"]["answer"] == "the agent's reply" and by_mode["combined"]["writer"] == "agent"
    assert by_mode["combined"]["passages"] == ["[the agent's passage]"]  # what the agent's flow used, not a search
    assert by_mode["keyword"]["answer"] == by_mode["whole_kb"]["answer"] == "simple prompt"


class Stream:
    def __init__(self, text):
        self.text_stream = iter([text])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, text):
        self.text, self.prompts = text, []
        self.messages = self

    def stream(self, **kwargs):
        self.prompts.append(kwargs)
        return Stream(self.text)


def test_the_agent_answerer_writes_with_the_agents_rules_and_checks():
    from app.replies.writer import RULES
    from eval.retrieval_eval import agent_answerer
    client = FakeClient("The diagnostic fee is $89 (faq/customer_faq.md). I'll waive it for you.")
    ask = agent_answerer(Searcher(), client, money_check=lambda sentence, previous: "waive" not in sentence)
    reply, passages = ask("What is the diagnostic fee?")
    assert passages == ["[faq/customer_faq.md, Fees, 2026-03-02] Diagnostic fee: $89."]
    assert client.prompts[0]["system"] == RULES and "diagnostic fee is $89" in reply
    assert "waive" not in reply and "team member" in reply  # a blocked sentence ends the reply with a handoff


def test_the_agent_answerer_hands_off_where_the_writer_marks_the_documents_silent():
    from app.replies.checks import NOT_IN_DOCUMENTS
    from eval.retrieval_eval import AGENT_HANDOFF, agent_answerer
    ask = agent_answerer(Searcher(), FakeClient(f"The diagnostic fee is $89. {NOT_IN_DOCUMENTS}"), money_check=lambda s, p: True)
    reply, _ = ask("Do you offer a veterans discount?")
    assert reply == f"The diagnostic fee is $89. {AGENT_HANDOFF}" and "NOT IN" not in reply


class PriceSearcher:
    def search(self, question, mode="combined", k=5):
        return [ScoredChunk(Chunk("services__service_catalog#3", "services/service_catalog.md", "Plumbing (residential)",
                                  "2026-02-10", "Drain clearing ($149 – $290 depending on access)", 31, 36), 0.7, 2)]


def test_the_agent_answerers_passages_include_the_final_price_sentence_it_states():
    from eval.retrieval_eval import agent_answerer
    ask = agent_answerer(PriceSearcher(), FakeClient("Drain clearing runs $149 to $290."), money_check=lambda s, p: True)
    _, passages = ask("How much does it cost to clear a clogged drain?")
    assert any("Drain clearing" in p for p in passages)
    assert any(p.startswith("[company pricing rule (R42)") and "confirms the final price on site" in p for p in passages)


# -- one $8 cap for the whole retrieval run -------------------------------------------------------------------

def _costly(budget, usd, text):
    """A writer or agent answer that spends usd from the run's budget, as its model calls would."""
    def call(*args):
        budget.record("write", "m", "sdk", {}, 1, 1, 1, int(usd * 1_000_000))
        return text
    return call


def test_the_simple_prompt_and_the_agents_answers_share_one_budget_and_stop_at_its_cap(tmp_path):
    from eval.budget import BudgetExceeded, RunBudget
    from eval.retrieval_eval import answer_both_ways
    out = tmp_path / "answers_to_grade.jsonl"
    out.write_text("previous answers\n")
    budget = RunBudget(1.5)
    agent = _costly(budget, 0.5, None)
    questions = [{"qid": f"q{n}", "question": "fee?", "kind": "answerable", "reference_answer": "$89"} for n in range(3)]
    with pytest.raises(BudgetExceeded):
        answer_both_ways(questions, Searcher(), _costly(budget, 0.25, "simple"), whole_kb="KB", out=out, budget=budget,
                         agent_answer=lambda q: (agent(q) or "agent", []))
    assert out.read_text() == "previous answers\n"  # nothing partial over the old answers
    assert budget.spent_usd == 1.75  # $1 a question: stopped at the second question's agent answer, which crossed it
    assert not (tmp_path / "answers_meta.json").exists()


def test_the_simple_prompt_writer_spends_from_the_runs_budget(monkeypatch):
    import eval.retrieval_eval as retrieval
    from eval.budget import RunBudget
    from tests.eval.test_retrieval_metrics import FakeUsage

    class Messages:
        def create(self, **kwargs):
            class Block:
                type, text = "text", "answer"

            class Response:
                content, usage = [Block()], FakeUsage()
            return Response()

    class Client:
        def __init__(self, **kwargs):
            self.messages = Messages()

    monkeypatch.setenv("EVAL_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("anthropic.Anthropic", Client)
    budget = RunBudget(8.0)
    budget.record("write", "m", "sdk", {}, 1, 1, 1, 4_000_000)  # the agent's own calls already spent $4
    write = retrieval.sonnet_writer(budget=budget)
    write("q", "c")  # $3 at Sonnet 5.5 prices
    assert budget.spent_usd == pytest.approx(7.0) and not budget.crossed
    write("q", "c")
    assert budget.crossed
    with pytest.raises(retrieval.BudgetExceeded):
        write("q", "c")


# -- retrieval grading saved per batch ------------------------------------------------------------------------

def test_retrieval_grading_keeps_finished_batches_and_the_previous_verdicts_when_a_batch_fails(tmp_path):
    from eval.grade_retrieval import grade_and_save
    from tests.eval.test_grader import item
    from tests.eval.test_grader_batches import FailsOnSecondBatch
    (tmp_path / "verdicts.jsonl").write_text("previous verdicts\n")
    with pytest.raises(RuntimeError, match="batch two"):
        grade_and_save([item(n) for n in range(25)], FailsOnSecondBatch(), "m", tmp_path)
    assert (tmp_path / "verdicts.jsonl").read_text() == "previous verdicts\n"
    kept = [json.loads(line) for line in (tmp_path / "verdicts.jsonl.partial").open()]
    assert [v["id"] for v in kept] == [f"i{n}" for n in range(20)]


def test_retrieval_grading_replaces_the_verdicts_once_every_batch_is_graded(tmp_path):
    from eval.grade_retrieval import grade_and_save
    from tests.eval.test_grader import FakeRunner, item
    (tmp_path / "verdicts.jsonl").write_text("previous verdicts\n")
    verdicts = grade_and_save([item(n) for n in range(25)], FakeRunner(), "m", tmp_path)
    assert len(verdicts) == 25 and not (tmp_path / "verdicts.jsonl.partial").exists()
    assert [json.loads(line)["id"] for line in (tmp_path / "verdicts.jsonl").open()] == [f"i{n}" for n in range(25)]


# -- the threshold curve: handoffs, and runs filed under the answers hash -------------------------------------

def test_the_agents_combined_answers_record_whether_they_ended_in_a_handoff(tmp_path):
    from eval.retrieval_eval import AGENT_HANDOFF, answer_both_ways
    out = tmp_path / "answers_to_grade.jsonl"
    replies = {"fee?": "The fee is $89.", "discount?": f"The fee is $89. {AGENT_HANDOFF}"}
    answer_both_ways([{"qid": q, "question": q, "kind": "answerable", "reference_answer": None} for q in replies],
                     Searcher(), lambda q, c: "simple", whole_kb="KB", out=out,
                     agent_answer=lambda q: (replies[q], []))
    combined = {a["qid"]: a["handed_off"] for a in map(json.loads, out.open()) if a["mode"] == "combined"}
    assert combined == {"fee?": False, "discount?": True}


def test_a_handed_off_answer_is_neither_contained_nor_wrong_at_any_threshold():
    from eval.threshold import curve
    questions = [{"qid": "a", "score": 0.8, "correct": False, "handed_off": True},
                 {"qid": "b", "score": 0.8, "correct": True, "handed_off": True},
                 {"qid": "c", "score": 0.8, "correct": True}]
    for point in curve(questions, thresholds=[0.2, 0.5, 0.9]):
        assert point.wrong_confident == 0 and point.containment <= 1 / 3


def test_the_threshold_reads_the_handoff_flag_or_falls_back_to_the_handoff_text(tmp_path):
    from eval.retrieval_eval import AGENT_HANDOFF
    from eval.threshold import pooled_verdicts
    folder = tmp_path / "runs" / "now" / "1"
    folder.mkdir(parents=True)
    answers = [{"qid": "q1", "mode": "combined", "writer": "agent", "answer": "x", "handed_off": True},
               {"qid": "q2", "mode": "combined", "writer": "agent", "answer": f"Fee is $89. {AGENT_HANDOFF}"},
               {"qid": "q3", "mode": "combined", "writer": "agent", "answer": "Fee is $89."}]
    (folder / "answers_to_grade.jsonl").write_text("".join(json.dumps(a) + "\n" for a in answers))
    (folder / "verdicts.jsonl").write_text("".join(json.dumps({"id": f"{q}|combined", "correct": False}) + "\n"
                                                   for q in ("q1", "q2", "q3")))
    [run] = pooled_verdicts(tmp_path, "now")
    assert [run[f"{q}|combined"]["handed_off"] for q in ("q1", "q2", "q3")] == [True, True, False]


def _agent_tree(root, threshold="0.35", engine="a"):
    (root / "app/core").mkdir(parents=True, exist_ok=True)
    (root / "app/core/engine.py").write_text(engine)
    (root / "app/config.py").write_text("class Settings:\n    retrieval_threshold: float  # chosen on the curve\n\n"
                                        f"SETTINGS = Settings(\n    retrieval_threshold={threshold},\n    other=1,\n)\n")
    return root


def test_the_answers_hash_leaves_out_only_the_retrieval_threshold(tmp_path):
    from eval.freeze import answers_hash, freeze_agent
    one, two = _agent_tree(tmp_path / "one"), _agent_tree(tmp_path / "two", threshold="0.5")
    assert freeze_agent(one) != freeze_agent(two) and answers_hash(one) == answers_hash(two)
    assert answers_hash(one) != freeze_agent(one)
    (two / "app/config.py").write_text((two / "app/config.py").read_text().replace("other=1", "other=2"))
    assert answers_hash(one) != answers_hash(two)
    assert answers_hash(_agent_tree(tmp_path / "three", engine="b")) != answers_hash(one)


def test_retrieval_answers_are_filed_and_graded_under_the_answers_hash(tmp_path, monkeypatch):
    import eval.freeze as freeze
    import eval.grade_retrieval as grading
    import eval.retrieval_eval as retrieval
    import eval.threshold as threshold
    from eval.grade_retrieval import answers_to_grade, keep_run
    monkeypatch.setattr(freeze, "answers_hash", lambda root=None: "answers-x")
    monkeypatch.setattr(freeze, "freeze_agent", lambda root=None: "freeze-x")
    _write_answers(tmp_path, freeze.answers_hash())
    answers_to_grade(tmp_path, freeze.answers_hash())
    (tmp_path / "verdicts.jsonl").write_text(json.dumps({"id": "q1|combined", "correct": True}) + "\n")
    assert keep_run(tmp_path, "answers-x").parent.name == "answers-x"
    assert retrieval.agent_hash() == grading.agent_hash() == threshold.agent_hash() == "answers-x"
    assert threshold.hashes() == {"answers_hash": "answers-x", "freeze_hash": "freeze-x"}
