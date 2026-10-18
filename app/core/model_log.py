"""Record every model call (purpose, model, settings, tokens, time, cost) against the reply it served (R73).

The pipeline sets a sink for each turn; a RecordingClient wraps the Anthropic client and reports to it."""

import contextvars
import time
from collections.abc import Callable

from app.config import cost_usd

SINK: contextvars.ContextVar[Callable | None] = contextvars.ContextVar("model_call_sink", default=None)


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


class _RecordingStream:
    def __init__(self, stream, kwargs, sdk_version):
        self._stream, self._kwargs, self._sdk = stream, kwargs, sdk_version

    def __enter__(self):
        self._started = time.monotonic()
        self._inner = self._stream.__enter__()
        self.text_stream = self._inner.text_stream
        return self

    def __exit__(self, *exc):
        try:
            if exc[0] is None:
                _report("write", self._kwargs, self._inner.get_final_message().usage, self._started, self._sdk)
        finally:
            return self._stream.__exit__(*exc)


class _Messages:
    def __init__(self, client, sdk_version):
        self._client, self._sdk = client, sdk_version

    def create(self, purpose: str = "route", **kwargs):
        started = time.monotonic()
        response = self._client.messages.create(**kwargs)
        _report(purpose, kwargs, getattr(response, "usage", None), started, self._sdk)
        return response

    def stream(self, **kwargs):
        return _RecordingStream(self._client.messages.stream(**kwargs), kwargs, self._sdk)


class RecordingClient:
    def __init__(self, client, sdk_version: str):
        self.messages = _Messages(client, sdk_version)
