"""Record every model call (purpose, model, settings, tokens, time, cost) against the reply it served (R73).

The pipeline sets a sink for each turn; a RecordingClient wraps the Anthropic client and reports to it.

Before each call the client asks the pre-call check (PRE_CALL, set by the web layer for each turn, or a `before`
on the sink itself), which raises CallRefused when the visitor's budget is already spent, so a turn's second or third
call is refused once the first has crossed the cap; the pipeline turns that failure into its error handoff. The
check is a separate context variable because the pipeline wraps the web layer's sink in its own for each turn.

A streamed reply closed early (the caller's checks stopped at a blocked sentence, the message deadline passed, or the
reader stopped) still reports its usage: what the SDK has counted so far, and no less than an estimate of about four
characters a token for the text already streamed (and for the prompt, when the SDK has not reported it yet)."""

import contextvars
import json
import math
import time
from collections.abc import Callable

from app.config import cost_usd

SINK: contextvars.ContextVar[Callable | None] = contextvars.ContextVar("model_call_sink", default=None)
PRE_CALL: contextvars.ContextVar[Callable | None] = contextvars.ContextVar("model_call_pre_check", default=None)
CHARACTERS_PER_TOKEN = 4


class CallRefused(RuntimeError):
    """The visitor's spending budget refuses this model call (R61)."""


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens


def _before() -> None:
    for check in (PRE_CALL.get(), getattr(SINK.get(), "before", None)):
        if check is not None:
            check()


def _settings(kwargs: dict) -> dict:
    config = kwargs.get("output_config", {})
    return {"max_tokens": kwargs.get("max_tokens"), "effort": config.get("effort"),
            "format": config.get("format", {}).get("type")}


def _report(purpose: str, kwargs: dict, usage, started: float, sdk_version: str) -> None:
    sink = SINK.get()
    if sink is None or usage is None:
        return
    microdollars = round(cost_usd(kwargs["model"], usage.input_tokens, usage.output_tokens) * 1_000_000)
    sink(purpose, kwargs["model"], sdk_version, _settings(kwargs), usage.input_tokens, usage.output_tokens,
         round((time.monotonic() - started) * 1000), microdollars)


def _tokens(characters: int) -> int:
    return math.ceil(characters / CHARACTERS_PER_TOKEN)


class _RecordingStream:
    def __init__(self, stream, kwargs, sdk_version):
        self._stream, self._kwargs, self._sdk = stream, kwargs, sdk_version
        self._characters = 0

    def __enter__(self):
        self._started = time.monotonic()
        self._inner = self._stream.__enter__()
        self.text_stream = self._counted(self._inner.text_stream)
        return self

    def _counted(self, pieces):
        for piece in pieces:
            self._characters += len(piece)
            yield piece

    def _usage_so_far(self):
        """The usage of a stream that did not finish: the SDK's running count, raised to the estimate if lower."""
        try:
            usage = self._inner.current_message_snapshot.usage
            input_tokens, output_tokens = usage.input_tokens or 0, usage.output_tokens or 0
        except Exception:
            input_tokens = output_tokens = 0
        if not input_tokens:
            prompt = json.dumps(self._kwargs.get("system", "")) + json.dumps(self._kwargs.get("messages", []))
            input_tokens = _tokens(len(prompt))
        return _Usage(input_tokens, max(output_tokens, _tokens(self._characters)))

    def __exit__(self, *exc):
        try:
            usage = None
            if exc[0] is None:
                try:
                    usage = self._inner.get_final_message().usage
                except Exception:
                    usage = None
            _report("write", self._kwargs, usage or self._usage_so_far(), self._started, self._sdk)
        finally:
            return self._stream.__exit__(*exc)


class _Messages:
    def __init__(self, client, sdk_version):
        self._client, self._sdk = client, sdk_version

    def create(self, purpose: str = "route", **kwargs):
        _before()
        started = time.monotonic()
        response = self._client.messages.create(**kwargs)
        _report(purpose, kwargs, getattr(response, "usage", None), started, self._sdk)
        return response

    def stream(self, **kwargs):
        _before()
        return _RecordingStream(self._client.messages.stream(**kwargs), kwargs, self._sdk)


class RecordingClient:
    def __init__(self, client, sdk_version: str):
        self.messages = _Messages(client, sdk_version)
