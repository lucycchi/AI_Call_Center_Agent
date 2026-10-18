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
        """Yield checked sentences, then exactly one DoneEvent, which is always last.

        A pipeline that stops without a done event ends with outcome "incomplete"; one that raises
        ends with outcome "error". The handoff flow (a later task) turns both into a handoff."""
        try:
            for event in self._pipeline.run(turn):
                yield event
                if isinstance(event, DoneEvent):
                    return
        except Exception as error:  # every failure must still end the reply cleanly
            yield DoneEvent(route="unknown", ticket=None, outcome="error", receipt={"error": type(error).__name__})
            return
        yield DoneEvent(route="unknown", ticket=None, outcome="incomplete")
