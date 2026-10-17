"""The agent core's input and output: one caller turn in, typed events out."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Turn:
    conversation_id: str
    visitor_id: str
    message_id: str
    text: str


@dataclass(frozen=True)
class SentenceEvent:
    """One checked sentence, ready to show the caller."""

    text: str


@dataclass(frozen=True)
class DoneEvent:
    """The final event of a reply: what happened, for the web layer, logs and tests."""

    route: str
    ticket: int | None
    receipt: dict = field(default_factory=dict)
    outcome: str = "answered"
    db_actions: list[str] = field(default_factory=list)


Event = SentenceEvent | DoneEvent
