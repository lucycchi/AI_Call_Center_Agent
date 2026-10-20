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
                     lambda q, c: "simple prompt", whole_kb="KB", out=out, agent_answer=lambda q: "the agent's reply")
    by_mode = {a["mode"]: a for a in map(json.loads, out.open())}
    assert by_mode["combined"]["answer"] == "the agent's reply" and by_mode["combined"]["writer"] == "agent"
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
    reply = ask("What is the diagnostic fee?")
    assert client.prompts[0]["system"] == RULES and "diagnostic fee is $89" in reply
    assert "waive" not in reply and "team member" in reply  # a blocked sentence ends the reply with a handoff
