"""One conversation's state, kept in the operations database so it survives a restart (R82)."""


class NotYourConversation(PermissionError):
    """The conversation belongs to a different visitor."""

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
    notes: list[str] = field(default_factory=list)
    reviewed_invoices: list[str] = field(default_factory=list)  # silent billing reviews already opened
    burning_mentioned: bool = False  # for the whole conversation: never advise resetting a breaker (R36)
    tags_opened: list[str] = field(default_factory=list)  # ticket reasons already opened in this conversation
    ticket_notes: int = 0  # later messages added to the open ticket
    pending_tickets: list[dict] = field(default_factory=list)  # staff tickets whose save failed, retried each message  # constraints for any ticket, such as a disputed fee

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
        if row["visitor_id"] != visitor_id:
            raise NotYourConversation(conversation_id)
        return cls(conversation_id, row["visitor_id"], row["customer_id"], active_flow=row["active_flow"],
                   **json.loads(row["flow_state"] or "{}"))

    def save(self, store) -> None:
        store.save_state(self.conversation_id, self.customer_id, self.active_flow, self.flow_state())
