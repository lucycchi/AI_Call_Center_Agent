import json

import pytest

from app.core.model_log import SINK
from app.core.types import DoneEvent, SentenceEvent
from eval.budget import RunBudget
from eval.harness import run_case
from tests.eval.test_grader import FakeRunner
from tests.eval.test_scoring import Recorder, ScriptedCaller, case

SETTINGS = {"grader": "gpt-5.6-sol", "simulator": {"model": "claude-sonnet-5-5"}}


def _cases(n=4):
    return [case(f"c{k}", 1, sub="transfer", reason="warranty") for k in range(n)]


class Caller(ScriptedCaller):
    """Reports its model call the way the recording client does, and crashes on the named case."""

    def __init__(self, crash_on=None):
        super().__init__(["hello"])
        self.crash_on = crash_on

    def next(self, case, conversation, timeout=None):
        if case["case_id"] == self.crash_on:
            raise RuntimeError("simulator fell over")
        SINK.get()("simulate", "claude-sonnet-5-5", "anthropic 9.9", {"max_tokens": 300}, 10, 5, 1, 30)
        return super().next(case, conversation)


def _run(tmp_path, runner, crash_on=None):
    from eval.run import run_graded
    return run_graded(_cases(), "t", out=tmp_path, factory=Recorder(), simulator_factory=lambda: Caller(crash_on),
                      runner=runner, model="gpt-5.6-sol", settings=SETTINGS)


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_crash_in_the_last_case_is_recorded_and_the_run_still_finishes(tmp_path):
    attempts, summary = _run(tmp_path, FakeRunner(), crash_on="c3")
    saved = _lines(tmp_path / "attempts.jsonl")
    assert [a["case_id"] for a in saved] == ["c0", "c1", "c2", "c3"]
    assert saved[3]["stopped"] == "error" and "simulator fell over" in saved[3]["error"] and saved[3]["all_correct"] is False
    assert all(a["graded"] for a in saved[:3]) and len(_lines(tmp_path / "verdicts.jsonl")) == 3
    assert json.loads((tmp_path / "summary.json").read_text())["extra"]["errored"] == ["c3"]


class FailsOnRetries(FakeRunner):
    def __init__(self):
        super().__init__(lambda i: {"correct": False})

    def __call__(self, prompt):
        if self.prompts:
            raise RuntimeError("Codex is down")
        return super().__call__(prompt)


def test_a_grader_failure_during_retries_loses_nothing(tmp_path):
    with pytest.raises(RuntimeError, match="Codex is down"):
        _run(tmp_path, FailsOnRetries())
    saved = _lines(tmp_path / "attempts.jsonl")
    firsts, retries = [a for a in saved if a["attempt"] == 1], [a for a in saved if a["attempt"] == 2]
    assert len(firsts) == 4 and all(a["graded"] and a["all_correct"] is False for a in firsts)
    assert len(retries) == 4 and not any(a["graded"] for a in retries) and all(a["conversation"] for a in retries)
    assert len(_lines(tmp_path / "verdicts.jsonl")) == 4
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert "Codex is down" in summary["extra"]["failed"]


def test_each_run_saves_model_ids_settings_and_verdicts(tmp_path):
    _run(tmp_path, FakeRunner())
    saved = _lines(tmp_path / "attempts.jsonl")
    assert saved[0]["settings"] == SETTINGS
    assert saved[0]["models"]["simulate"] == [{"model_id": "claude-sonnet-5-5", "sdk_version": "anthropic 9.9",
                                               "settings": {"max_tokens": 300}}]
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["extra"]["settings"] == SETTINGS and summary["extra"]["grader_model"] == "gpt-5.6-sol"
    verdicts = _lines(tmp_path / "verdicts.jsonl")
    assert {v["id"] for v in verdicts} == {f"c{k}|1" for k in range(4)} and all(v["model"] == "gpt-5.6-sol" for v in verdicts)


def test_the_run_settings_name_every_model_and_the_sdk():
    from eval.run import run_settings
    settings = run_settings("gpt-5.6-sol")
    for part in ("simulator", "router", "writer", "check"):
        assert settings[part]["model"] and settings[part]["max_tokens"], part
    assert settings["grader"] == "gpt-5.6-sol" and settings["sdk_version"].startswith("anthropic ")


# -- the 60-second cap during calls ---------------------------------------------------------------------------

def test_the_caller_is_given_only_the_time_left(tmp_path):
    now, seen = [0.0], []

    class Timed(ScriptedCaller):
        def next(self, case, conversation, timeout=None):
            seen.append(timeout)
            now[0] += 40
            return super().next(case, conversation)
    result = run_case(case("t", 1), Recorder(), Timed(["a", "b"]), RunBudget(8.0), tmp_path, clock=lambda: now[0])
    assert seen == [60, 20] and result.stopped == "time limit"


def test_a_reply_still_running_at_the_cap_is_cut_off(tmp_path):
    now = [0.0]

    class Slow:
        def handle(self, turn):
            for n in range(10):
                now[0] += 10
                yield SentenceEvent(f"sentence {n}")
            yield DoneEvent(route="knowledge", ticket=None)
    result = run_case(case("t", 1), lambda db, ops: Slow(), ScriptedCaller(["hi"] * 3), RunBudget(8.0), tmp_path,
                      clock=lambda: now[0])
    assert result.stopped == "time limit" and sum(m["role"] == "agent" for m in result.conversation) == 6


def test_the_agents_message_deadline_is_capped_to_the_time_left():
    from eval.harness import TIME_LEFT
    from eval.run import CappedPipeline

    class Pipeline:
        deadline_s = 15

        def run(self, turn):
            yield self.deadline_s
    capped = CappedPipeline(Pipeline())
    token = TIME_LEFT.set(4.5)
    try:
        assert list(capped.run(None)) == [4.5]
    finally:
        TIME_LEFT.reset(token)
    assert list(capped.run(None)) == [15]


# -- the held-out guard ---------------------------------------------------------------------------------------

def _repo(tmp_path):
    from eval.freeze import freeze_agent
    from eval.split import freeze_hash
    root = tmp_path / "repo"
    (root / "data" / "testset").mkdir(parents=True)
    (root / "app" / "core").mkdir(parents=True)
    (root / "app" / "core" / "engine.py").write_text("agent")
    (root / "data" / "testset" / "H1.json").write_text('{"case_id": "H1"}')
    split = {"working": ["W1"], "held_out": ["H1"], "held_out_hash": freeze_hash([root / "data" / "testset" / "H1.json"])}
    (root / "data" / "split.json").write_text(json.dumps(split))
    (root / "data" / "agent_freeze.json").write_text(json.dumps({"hash": freeze_agent(root)}))
    return root


def test_held_out_cases_need_the_final_flag_and_matching_hashes(tmp_path):
    from eval.run import refuse_held_out
    root = _repo(tmp_path)
    refuse_held_out(["W1"], final=False, root=root)
    with pytest.raises(SystemExit, match="--final"):
        refuse_held_out(["W1", "H1"], final=False, root=root)
    refuse_held_out(["H1"], final=True, root=root)
    (root / "app" / "core" / "engine.py").write_text("tuned")
    with pytest.raises(SystemExit, match="freeze"):
        refuse_held_out(["H1"], final=True, root=root)
    (root / "app" / "core" / "engine.py").write_text("agent")
    (root / "data" / "testset" / "H1.json").write_text('{"case_id": "H1", "changed": true}')
    with pytest.raises(SystemExit, match="held-out cases"):
        refuse_held_out(["H1"], final=True, root=root)


def test_the_run_command_refuses_the_held_out_set_without_final(monkeypatch):
    import eval.run as run
    def never(*args, **kwargs):
        raise AssertionError("a test must never start a real run")
    monkeypatch.setattr(run, "run_graded", never)
    monkeypatch.setattr(run, "build_client", never)
    monkeypatch.setattr("sys.argv", ["eval.run", "--set", "held_out"])
    with pytest.raises(SystemExit, match="--final"):
        run.main()
