"""The agent core: text in, typed events out, independent of the web page (R33).

The pipeline (safety, limits, router, flows, writer and checks) is assembled in a later
task and passed in, so tests and the web layer use exactly the same entry point."""

from collections.abc import Iterator
from typing import Protocol

from app.core.types import DoneEvent, Event, Turn


class Pipeline(Protocol):
    def run(self, turn: Turn) -> Iterator[Event]: ...


class Engine:
    def __init__(self, pipeline: Pipeline):
        self._pipeline = pipeline

    def handle(self, turn: Turn) -> Iterator[Event]:
        """Yield checked sentences, then exactly one DoneEvent."""
        done = False
        for event in self._pipeline.run(turn):
            if isinstance(event, DoneEvent):
                if done:
                    continue
                done = True
            yield event
        if not done:
            yield DoneEvent(route="unknown", ticket=None, outcome="incomplete")
