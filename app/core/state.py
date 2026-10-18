"""One conversation's state, kept in the operations database so it survives a restart (R82)."""

from dataclasses import asdict, dataclass, field


@dataclass
class ConversationState:
    conversation_id: str
    visitor_id: str
    customer_id: str | None = None
    who: str | None = None          # the identified caller, for tickets
    active_flow: str | None = None  # "account" or "scheduling" while one is in progress
    flow: dict = field(default_factory=dict)
    pending: list[dict] = field(default_factory=list)  # requests waiting for the caller to be identified
    id_attempts: int = 0
    ticket_id: int | None = None
    tried: list[str] = field(default_factory=list)

    def flow_state(self) -> dict:
        data = asdict(self)
        for key in ("conversation_id", "visitor_id", "customer_id", "active_flow"):
            data.pop(key)
        return data

    @classmethod
    def load(cls, store, conversation_id: str, visitor_id: str) -> "ConversationState":
        import json
        row = store.conversation(conversation_id)
        if row is None:
            store.open_conversation(visitor_id, conversation_id)
            return cls(conversation_id, visitor_id)
        return cls(conversation_id, row["visitor_id"], row["customer_id"], active_flow=row["active_flow"],
                   **json.loads(row["flow_state"] or "{}"))

    def save(self, store) -> None:
        store.save_state(self.conversation_id, self.customer_id, self.active_flow, self.flow_state())
