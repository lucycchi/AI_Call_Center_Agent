"""The agent core: text in, typed events out, independent of the web page (R33).

The pipeline (safety, limits, router, flows, writer and checks) is assembled in a later
task and passed in, so tests and the web layer use exactly the same entry point."""

import logging
from collections.abc import Iterator
from typing import Protocol

from app.core.types import DoneEvent, Event, SentenceEvent, Turn
from app.handoff.flow import ERROR_MESSAGE, NO_TICKET_MESSAGE

log = logging.getLogger("meridian.engine")


class Pipeline(Protocol):
    def run(self, turn: Turn) -> Iterator[Event]: ...


class Engine:
    def __init__(self, pipeline: Pipeline):
        self._pipeline = pipeline

    def handle(self, turn: Turn) -> Iterator[Event]:
        """Yield checked sentences, then exactly one DoneEvent, which is always last.

        A pipeline that raises (for example, the operations database is unavailable, so no ticket can be saved)
        ends with a plain message asking the caller to phone the office, and the failure goes to the server log;
        one that stops without a done event ends with a plain handoff message (R59)."""
        try:
            for event in self._pipeline.run(turn):
                yield event
                if isinstance(event, DoneEvent):
                    return
        except Exception as error:  # every failure must still end the reply cleanly
            log.exception("turn failed for conversation %s: %s", turn.conversation_id, error)
            yield SentenceEvent(NO_TICKET_MESSAGE)
            yield DoneEvent(route="unknown", ticket=None, outcome="error", receipt={"error": type(error).__name__})
            return
        log.error("turn for conversation %s ended without a done event", turn.conversation_id)
        yield SentenceEvent(ERROR_MESSAGE)
        yield DoneEvent(route="unknown", ticket=None, outcome="incomplete")
