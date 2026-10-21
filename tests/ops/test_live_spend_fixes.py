"""Milestone 5 review fixes in spending (live-only, D51): a writer stream closed early still reports its usage, and
every model call in a turn checks the visitor's budget first. No model is ever called: fake clients stand in."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.model_log import PRE_CALL, SINK, CallRefused, RecordingClient
from app.core.types import DoneEvent, SentenceEvent
from app.ops.spend import Spend
from app.ops.store import OpsStore

MODEL = "claude-sonnet-5-5"


class Usage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens


class Snapshot:
    def __init__(self, usage):
        self.usage = usage


class FakeStream:
    def __init__(self, pieces, snapshot=None):
        self.text_stream = iter(pieces)
        if snapshot is not None:
            self.current_message_snapshot = snapshot

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        raise AssertionError("an early close has no final message")


class FakeClient:
    def __init__(self, stream=None, usage=Usage(1000, 1000)):
        self.messages, self._stream, self._usage = self, stream, usage

    def stream(self, **kwargs):
        return self._stream

    def create(self, **kwargs):
        class Response:
            usage = self._usage
        return Response()


def writer(client):
    """As app/replies/writer.py: the stream is used inside a generator that the caller may close early."""
    with client.messages.stream(model=MODEL, max_tokens=300, system="rules " * 100,
                                messages=[{"role": "user", "content": "facts " * 200}]) as stream:
        yield from stream.text_stream


def run_closed_early(client):
    seen = []
    token = SINK.set(lambda *args: seen.append(args))
    try:
        sentences = writer(RecordingClient(client, "sdk"))
        assert next(sentences) == "First sentence. "
        sentences.close()  # as CheckedStream returning at a blocked sentence, or the deadline
    finally:
        SINK.reset(token)
    return seen


def test_a_writer_stream_closed_early_still_reports_what_it_used_so_far():
    seen = run_closed_early(FakeClient(FakeStream(["First sentence. ", "Second. "], Snapshot(Usage(812, 5)))))
    [(purpose, model, _, _, input_tokens, output_tokens, _, microdollars)] = seen
    assert (purpose, model, input_tokens) == ("write", MODEL, 812)
    assert output_tokens >= 4 and microdollars > 0  # at least the tokens streamed so far (16 characters)


def test_without_any_usage_from_the_sdk_an_early_close_is_estimated_from_the_text():
    seen = run_closed_early(FakeClient(FakeStream(["First sentence. ", "Second. "])))
    [(_, _, _, _, input_tokens, output_tokens, _, microdollars)] = seen
    assert input_tokens > 0 and output_tokens >= 4 and microdollars > 0


@pytest.fixture
def store(tmp_path):
    return OpsStore(tmp_path / "ops.sqlite")


def test_a_second_model_call_in_a_turn_after_the_cap_is_crossed_is_refused(store):
    spend = Spend(store, per_visitor_usd=0.01)
    recorder = spend.recorder("v1")
    client = RecordingClient(FakeClient(usage=Usage(1000, 1000)), "sdk")  # about 1.8 cents for Sonnet
    sink, hook = SINK.set(recorder), PRE_CALL.set(recorder.before)
    try:
        client.messages.create(purpose="route", model=MODEL, max_tokens=10, messages=[])
        with pytest.raises(CallRefused):
            client.messages.create(purpose="money check", model=MODEL, max_tokens=10, messages=[])
        with pytest.raises(CallRefused):
            client.messages.stream(model=MODEL, max_tokens=10, messages=[])
    finally:
        SINK.reset(sink)
        PRE_CALL.reset(hook)
    assert len(store.spend_rows()) == 1  # the refused calls were never made


def test_the_web_layer_checks_the_budget_before_each_model_call_in_the_turn(store):
    from app.web.main import create_app
    spend = Spend(store, per_visitor_usd=0.01)
    outcomes = []

    class TwoCalls:
        def handle(self, turn):
            store.log_message(turn.conversation_id, "caller", turn.text, turn.message_id)
            client = RecordingClient(FakeClient(usage=Usage(1000, 1000)), "sdk")
            client.messages.create(model=MODEL, max_tokens=10, messages=[])
            try:
                client.messages.create(model=MODEL, max_tokens=10, messages=[])
                outcomes.append("called")
            except CallRefused:
                outcomes.append("refused")
            yield SentenceEvent("Done.")
            yield DoneEvent("knowledge", None)

    app = create_app(TwoCalls(), store, cookie_secret="test-only-secret", spend=spend)
    with TestClient(app, base_url="https://testserver") as client:
        message_id = uuid.uuid4().hex
        client.post("/api/message", json={"conversation_id": "c1", "message_id": message_id, "text": "hi"})
        client.get(f"/api/stream/{message_id}")
    assert outcomes == ["refused"]
    assert app.state.executor.submit(PRE_CALL.get).result() is None  # not kept on the reply thread


def test_the_recorder_is_still_a_plain_sink(store):
    spend = Spend(store)
    spend.recorder("v1")("write", MODEL, "sdk", {}, 10, 10, 1, 500)
    assert spend.totals("v1")["visitor"] == pytest.approx(0.0005)


# -- The unused one-time token table is gone (D50) -----------------------------------------------------------------

def test_the_store_has_no_one_time_token_table_or_method(store):
    assert not hasattr(store, "use_token")
    assert store.read("select name from sqlite_master where name = 'used_tokens'") == []
