"""The operations database: conversations, messages and their sentences, receipts, tickets, model calls,
events and spending (R57, R73). Every text field a caller could have written is masked before it is stored."""

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from app.config import real_now
from app.ops.masking import mask

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

    def close_idle(self, minutes: int = 30) -> list[str]:
        """Close every open conversation with no message for that many minutes of real time (R82)."""
        cutoff = (self._clock() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        idle = [r["conversation_id"] for r in self._rows("select conversation_id from conversations where status = 'open' "
                                                         "and last_message_at < ?", (cutoff,))]
        for conversation_id in idle:
            self._write("update conversations set status = 'closed', closed_at = ? where conversation_id = ?",
                        (self._now(), conversation_id))
        return idle

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
        message_id = self._write("insert into messages (conversation_id, role, text_masked, created_at, request_id) "
                                 "values (?, ?, ?, ?, ?)", (conversation_id, role, mask(text), now, request_id))
        self._write("update conversations set last_message_at = ? where conversation_id = ?", (now, conversation_id))
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
