"""Today's live numbers for the Staff view (R70): conversations, handoffs, errors, median reply time and live
containment. Days are real Austin days (operations use real time, not the agent's fixed "now").

Live containment is the share of conversations that ended today (closed or abandoned) that were closed with no
handoff ticket, no error, no flag on any reply and no abandoned flow. Nothing checks that the caller's need was
really met, so it is labelled an upper bound, and it is shown only from MIN_CONVERSATIONS ended conversations."""

from datetime import date, datetime
from statistics import median

from app.config import AUSTIN

MIN_CONVERSATIONS = 10
UPPER_BOUND = "upper bound"
NOT_ENOUGH = "not enough conversations yet"


def austin_day(stamp: str | None) -> date | None:
    if not stamp:
        return None
    moment = datetime.fromisoformat(stamp)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=AUSTIN)
    return moment.astimezone(AUSTIN).date()


def _today(rows: list[dict], key: str, today: date) -> list[dict]:
    return [row for row in rows if austin_day(row[key]) == today]


def live_numbers(store, today: date) -> dict:
    conversations = _today(store.read("select conversation_id, created_at from conversations"), "created_at", today)
    handoffs = _today(store.read("select ticket_id, created_at from tickets where conversation_id is not null"),
                      "created_at", today)
    errors = _today(store.read("select event_id, created_at from events where kind = 'error'"), "created_at", today)
    replies = _today(store.read("select full_reply_ms, created_at from messages where role = 'agent' and "
                                "full_reply_ms is not null"), "created_at", today)
    ended = _today(store.read(
        "select c.conversation_id, c.status, c.closed_at, "
        "exists (select 1 from tickets t where t.conversation_id = c.conversation_id) as handed_off, "
        "exists (select 1 from events e where e.conversation_id = c.conversation_id and e.kind = 'error') as errored, "
        "exists (select 1 from flags f join messages m using (message_id) "
        "        where m.conversation_id = c.conversation_id) as flagged "
        "from conversations c where c.status in ('closed', 'abandoned')"), "closed_at", today)
    contained = [c for c in ended if c["status"] == "closed" and not (c["handed_off"] or c["errored"] or c["flagged"])]
    enough = len(ended) >= MIN_CONVERSATIONS
    return {
        "day": today.isoformat(),
        "conversations": len(conversations),
        "handoffs": len(handoffs),
        "errors": len(errors),
        "median_reply_ms": round(median(r["full_reply_ms"] for r in replies)) if replies else None,
        "ended_conversations": len(ended),
        "contained_conversations": len(contained) if enough else None,
        "live_containment": round(len(contained) / len(ended), 3) if enough else None,
        "live_containment_label": UPPER_BOUND if enough else NOT_ENOUGH,
    }
