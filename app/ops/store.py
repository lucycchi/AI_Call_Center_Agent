"""The operations database: conversations, messages and their sentences, receipts, tickets, model calls,
events and spending (R57, R73). Every text field a caller could have written is masked before it is stored."""

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from app.config import real_now
from app.ops.masking import mask

log = logging.getLogger("meridian.ops")

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()
PRIORITY = {"emergency": 2, "burning smell": 2, "billing review": 0, "warranty review": 0}  # everything else is 1


class OpsStore:
    def __init__(self, path: Path, clock: Callable[[], datetime] = real_now):
        self._clock = clock
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.execute("pragma journal_mode = wal")
        self._db.execute("pragma foreign_keys = on")
        self._db.executescript(SCHEMA)
        self._pending = Path(path).with_suffix(".pending.jsonl")  # staff tickets kept while the database failed
        self.retry_pending()

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    def _write(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            return self._db.execute(sql, params).lastrowid

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(row) for row in self._db.execute(sql, params).fetchall()]

    def open_conversation(self, visitor_id: str, conversation_id: str, kind: str = "public") -> None:
        now = self._now()
        self._write("insert or ignore into visitors (visitor_id, kind, first_seen) values (?, ?, ?)", (visitor_id, kind, now))
        self._write("insert or ignore into conversations (conversation_id, visitor_id, created_at, last_message_at) "
                    "values (?, ?, ?, ?)", (conversation_id, visitor_id, now, now))

    def conversation(self, conversation_id: str) -> dict | None:
        rows = self._rows("select * from conversations where conversation_id = ?", (conversation_id,))
        return rows[0] if rows else None

    def save_state(self, conversation_id: str, customer_id: str | None, active_flow: str | None, flow_state: dict) -> None:
        self._write("update conversations set customer_id = ?, active_flow = ?, flow_state = ? where conversation_id = ?",
                    (customer_id, active_flow, json.dumps(flow_state), conversation_id))

    def close_idle(self, minutes: int = 30) -> None:
        """After that many minutes of real time with no message, a conversation closes, or is abandoned if a flow was
        in progress (R82). One statement, so a message arriving during the sweep keeps its conversation open."""
        cutoff = (self._clock() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        self._write("update conversations set status = case when active_flow is null then 'closed' else 'abandoned' end, "
                    "closed_at = ? where status = 'open' and last_message_at < ? and not exists (select 1 from messages m "
                    "where m.conversation_id = conversations.conversation_id and m.created_at >= ?)",
                    (self._now(), cutoff, cutoff))

    def reopen(self, conversation_id: str) -> None:
        self._write("update conversations set status = 'open', closed_at = null where conversation_id = ?", (conversation_id,))

    def end_conversation(self, conversation_id: str) -> None:
        self._write("update conversations set status = 'closed', closed_at = ? where conversation_id = ?",
                    (self._now(), conversation_id))

    def history(self, conversation_id: str, limit: int = 6) -> list[dict]:
        rows = self._rows("select role, text_masked from messages where conversation_id = ? and text_masked != '' "
                          "order by message_id desc limit ?", (conversation_id, limit))
        return [{"role": r["role"], "content": r["text_masked"]} for r in reversed(rows)]

    def log_agent_message(self, message_id: int, text: str) -> None:
        self._write("update messages set text_masked = ? where message_id = ?", (mask(text), message_id))

    def set_reply_stats(self, message_id: int, first_sentence_ms: int | None, full_reply_ms: int,
                        cost_microdollars: int) -> None:
        self._write("update messages set first_sentence_ms = ?, full_reply_ms = ?, cost_microdollars = ? "
                    "where message_id = ?", (first_sentence_ms, full_reply_ms, cost_microdollars, message_id))

    def log_message(self, conversation_id: str, role: str, text: str, request_id: str | None = None) -> int:
        now = self._now()
        with self._lock:  # the message and the conversation's last-message time are written together
            self._db.execute("begin immediate")
            try:
                message_id = self._db.execute("insert into messages (conversation_id, role, text_masked, created_at, "
                                              "request_id) values (?, ?, ?, ?, ?)",
                                              (conversation_id, role, mask(text), now, request_id)).lastrowid
                self._db.execute("update conversations set last_message_at = ? where conversation_id = ?",
                                 (now, conversation_id))
                self._db.execute("commit")
            except BaseException:
                self._db.execute("rollback")
                raise
        return message_id

    def message_text(self, message_id: int) -> str:
        return self._db.execute("select text_masked from messages where message_id = ?", (message_id,)).fetchone()[0]

    def log_sentence(self, message_id: int, text: str) -> None:
        self._write("insert into sentences (message_id, text_masked, created_at) values (?, ?, ?)",
                    (message_id, mask(text), self._now()))

    def sentences(self, message_id: int) -> list[str]:
        return [r["text_masked"] for r in self._rows("select text_masked from sentences where message_id = ? "
                                                     "order by sentence_id", (message_id,))]

    def log_receipt(self, message_id: int, safety_result: str, route: str, passages: list, excluded: list,
                    db_action: str | None, outcome_label: str) -> None:
        self._write("insert or replace into receipts values (?, ?, ?, ?, ?, ?, ?)",
                    (message_id, safety_result, route, json.dumps(passages), json.dumps(excluded), db_action, outcome_label))

    def receipt(self, message_id: int) -> dict | None:
        rows = self._rows("select * from receipts where message_id = ?", (message_id,))
        return rows[0] if rows else None

    def log_model_call(self, message_id: int | None, purpose: str, model_id: str, sdk_version: str, settings: dict,
                       input_tokens: int, output_tokens: int, ms: int, microdollars: int) -> None:
        self._write("insert into model_calls (message_id, purpose, model_id, sdk_version, settings, input_tokens, "
                    "output_tokens, ms, microdollars) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (message_id, purpose, model_id, sdk_version, json.dumps(settings), input_tokens, output_tokens, ms,
                     microdollars))

    def log_event(self, kind: str, detail: str, conversation_id: str | None = None) -> None:
        self._write("insert into events (conversation_id, kind, detail, created_at) values (?, ?, ?, ?)",
                    (conversation_id, kind, mask(detail), self._now()))

    def create_ticket(self, conversation_id: str | None, who: str, wants: str, tried: str, constraints: str, mood: str,
                      reason_tag: str, appointment_id: int | None = None) -> int:
        return self._write("insert into tickets (conversation_id, appointment_id, who, wants, tried, constraints, mood, "
                           "reason_tag, priority, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (conversation_id, appointment_id, mask(who), mask(wants), mask(tried), mask(constraints),
                            mood, reason_tag, PRIORITY.get(reason_tag, 1), self._now()))

    def create_ticket_or_keep(self, **ticket) -> int | None:
        """A staff ticket that must not be lost: if it cannot be saved, it goes to a fallback file next to the
        database and is saved by retry_pending, on every later message and at startup."""
        try:
            return self.create_ticket(**ticket)
        except Exception as error:
            log.error("%s ticket not saved, kept in %s: %s", ticket.get("reason_tag"), self._pending, error)
            with self._pending.open("a") as handle:
                handle.write(json.dumps(ticket) + "\n")
            return None

    def retry_pending(self) -> None:
        if not self._pending.exists():
            return
        waiting = [json.loads(line) for line in self._pending.read_text().splitlines() if line.strip()]
        still = []
        for ticket in waiting:
            try:
                self.create_ticket(**ticket)
            except Exception as error:
                log.error("kept %s ticket still not saved: %s", ticket.get("reason_tag"), error)
                still.append(ticket)
        if still:
            self._pending.write_text("".join(json.dumps(t) + "\n" for t in still))
        else:
            self._pending.unlink()

    def set_ticket_caller(self, ticket_id: int, who: str) -> None:
        """A caller identified after the handoff: the ticket now says who they are (R57)."""
        self._write("update tickets set who = ? where ticket_id = ?", (mask(who), ticket_id))

    def add_reason(self, ticket_id: int, reason_tag: str, constraints: str) -> None:
        """A later handoff reason in the same conversation: its tag and constraints join the open ticket (R57, R58)."""
        if reason_tag:
            self._write("insert or ignore into ticket_tags (ticket_id, tag) select ticket_id, ? from tickets "
                        "where ticket_id = ? and reason_tag != ?", (reason_tag, ticket_id, reason_tag))
        rows = self._rows("select constraints from tickets where ticket_id = ?", (ticket_id,))
        have = [c for c in (rows[0]["constraints"] or "").split("; ") if c and c != "none"] if rows else []
        added = [c for c in mask(constraints).split("; ") if c and c != "none" and c not in have]
        if added:
            self._write("update tickets set constraints = ? where ticket_id = ?", ("; ".join(have + added), ticket_id))

    def ticket_tags(self, ticket_id: int) -> list[str]:
        """The ticket's reason tag, then any added later."""
        return [r["tag"] for r in self._rows("select reason_tag as tag, 0 as n from tickets where ticket_id = ? union all "
                                             "select tag, rowid from ticket_tags where ticket_id = ? order by n",
                                             (ticket_id, ticket_id))]

    def append_to_ticket(self, ticket_id: int, message_id: int) -> None:
        self._write("insert or ignore into ticket_messages (ticket_id, message_id) values (?, ?)", (ticket_id, message_id))

    def ticket_messages(self, ticket_id: int) -> list[str]:
        return [r["text_masked"] for r in self._rows("select m.text_masked from ticket_messages t join messages m "
                                                     "using (message_id) where t.ticket_id = ? order by m.message_id",
                                                     (ticket_id,))]

    def tickets(self) -> list[dict]:
        """For staff only; visitors go through tickets_for_visitor."""
        return self._rows("select * from tickets order by ticket_id")

    def tickets_for_visitor(self, visitor_id: str) -> list[dict]:
        return self._rows("select t.* from tickets t join conversations c using (conversation_id) "
                          "where c.visitor_id = ? order by t.ticket_id", (visitor_id,))
