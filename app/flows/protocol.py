"""The shared flow protocol: every flow turns the conversation state and a caller message into facts for the
writer, a reply type, sources, an optional handoff reason and the database actions taken."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class FlowResult:
    facts: list[str]
    reply_type: str
    sources: list[str] = field(default_factory=list)
    handoff_reason: str | None = None
    db_actions: list[str] = field(default_factory=list)
    passages: list[str] = field(default_factory=list)  # dated sources used, for the receipt
    excluded: list[str] = field(default_factory=list)  # stale documents on the same subject, left out


class Flow(Protocol):
    def run(self, state: dict, text: str) -> FlowResult: ...
