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
        self._pending_lock = threading.Lock()  # the backup ticket file: one append or retry at a time
        self._db.execute("pragma journal_mode = wal")
        self._db.execute("pragma foreign_keys = on")
        self._db.executescript(SCHEMA)
        self._pending = Path(path).with_suffix(".pending.jsonl")  # staff tickets kept while the database failed
        self.on_write_failure: Callable[[Exception], None] | None = None  # set by Alerts.watch (R76)
        self.retry_pending()

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    def _failed(self, error: Exception) -> None:
        if self.on_write_failure:
            self.on_write_failure(error)

    def _write(self, sql: str, params: tuple = ()) -> int:
        try:
            with self._lock:
                return self._db.execute(sql, params).lastrowid
        except Exception as error:
            self._failed(error)
            raise

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

    def log_message(self, conversation_id: str, role: str, text: str, request_id: str | None = None,
                    accepted_text: str | None = None) -> int:
        """A caller message with a request id replaces that request's accepted placeholder (accept_message), so the
        message is stored once, in the order the agent handled it. accepted_text: accept_message's 'accepted' event,
        written in the same transaction as its placeholder."""
        now = self._now()
        try:  # the failure alert is sent after the lock is released: recording it takes the lock again
            with self._lock:  # the message and the conversation's last-message time are written together
                self._db.execute("begin immediate")
                try:
                    if role == "caller" and request_id:
                        self._db.execute("delete from messages where conversation_id = ? and role = 'caller' and "
                                         "request_id = ? and text_masked = '' and message_id not in (select message_id "
                                         "from ticket_messages)", (conversation_id, request_id))
                    message_id = self._db.execute("insert into messages (conversation_id, role, text_masked, "
                                                  "created_at, request_id) values (?, ?, ?, ?, ?)",
                                                  (conversation_id, role, mask(text), now, request_id)).lastrowid
                    self._db.execute("update conversations set last_message_at = ? where conversation_id = ?",
                                     (now, conversation_id))
                    if accepted_text is not None:
                        detail = json.dumps({"message_id": request_id, "text": mask(accepted_text)})
                        self._db.execute("insert into events (conversation_id, kind, detail, created_at) values "
                                         "(?, 'accepted', ?, ?)", (conversation_id, detail, now))
                    self._db.execute("commit")
                except BaseException:
                    self._db.execute("rollback")
                    raise
        except Exception as error:
            self._failed(error)
            raise
        return message_id

    def accept_message(self, conversation_id: str, request_id: str, text: str) -> int:
        """The web layer's record of a caller message it has accepted (202) but not yet handed to the agent: a caller
        message with no text (so the agent's history and the reloaded chat never show it twice or early) and an
        'accepted' event holding the masked text. A restart before the agent logs the message still finds it, as an
        unfinished reply (request_reply); the agent's own log_message replaces the placeholder. Both are written in
        one transaction: a placeholder without its text would lose the message and turn away its retry."""
        return self.log_message(conversation_id, "caller", "", request_id, accepted_text=text)

    def accepted_text(self, conversation_id: str, request_id: str) -> str | None:
        """The masked text of a caller message the web layer accepted, or None."""
        rows = self._rows("select detail from events where kind = 'accepted' and conversation_id = ? and "
                          "json_extract(detail, '$.message_id') = ? order by event_id limit 1", (conversation_id, request_id))
        return json.loads(rows[0]["detail"])["text"] if rows else None

    def message_text(self, message_id: int) -> str:
        return self._db.execute("select text_masked from messages where message_id = ?", (message_id,)).fetchone()[0]

    def log_sentence(self, message_id: int, text: str) -> None:
        self._write("insert into sentences (message_id, text_masked, created_at) values (?, ?, ?)",
                    (message_id, mask(text), self._now()))

    def sentences(self, message_id: int) -> list[str]:
        return [r["text_masked"] for r in self._rows("select text_masked from sentences where message_id = ? "
                                                     "order by sentence_id", (message_id,))]

    def request_reply(self, visitor_id: str, request_id: str) -> dict | None:
        """The visitor's caller message sent with this request id: its conversation and the agent message logged for
        it (None until the agent message exists; a later caller message before it means it belongs to that one), so the
        web stream can replay its saved sentences."""
        rows = self._rows("select m.conversation_id, m.message_id as caller_message_id, m.text_masked as caller_text, "
                          "(select min(a.message_id) from messages a where a.conversation_id = m.conversation_id and "
                          "a.role = 'agent' and a.message_id > m.message_id and not exists (select 1 from messages b "
                          "where b.conversation_id = m.conversation_id and b.role = 'caller' and b.message_id > "
                          "m.message_id and b.message_id < a.message_id)) as agent_message_id "
                          "from messages m join conversations c using (conversation_id) where c.visitor_id = ? and "
                          "m.request_id = ? and m.role = 'caller' order by m.message_id limit 1", (visitor_id, request_id))
        return rows[0] if rows else None

    def save_reply_end(self, conversation_id: str, request_id: str, sentences: list[str], done: dict) -> None:
        """The web stream's record that a message's reply finished: every sentence shown and the done event, kept as
        a 'reply end' event so a reconnect after a restart replays it. The request id is stored unmasked."""
        detail = json.dumps({"message_id": request_id, "sentences": [mask(s) for s in sentences], "done": done})
        self._write("insert into events (conversation_id, kind, detail, created_at) values (?, 'reply end', ?, ?)",
                    (conversation_id, detail, self._now()))

    def reply_end(self, visitor_id: str, request_id: str) -> dict | None:
        rows = self._rows("select e.detail from events e join conversations c using (conversation_id) where "
                          "e.kind = 'reply end' and c.visitor_id = ? and json_extract(e.detail, '$.message_id') = ? "
                          "order by e.event_id limit 1", (visitor_id, request_id))
        return json.loads(rows[0]["detail"]) if rows else None

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
            kept = ticket | {field: mask(ticket.get(field) or "") for field in ("who", "wants", "tried", "constraints")}
            with self._pending_lock, self._pending.open("a") as handle:  # masked on disk too (R73)
                handle.write(json.dumps(kept) + "\n")
            return None

    def retry_pending(self) -> None:
        with self._pending_lock:  # an append during a retry is not erased, and two retries never save a ticket twice
            self._retry_pending()

    def _retry_pending(self) -> None:
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

    # -- spending, alerts and the reviewer link (R61, R85) -------------------------------------------------------
    def add_spend(self, visitor_id: str, pool: str, day: str, microdollars: int) -> None:
        self._write("insert into spend (visitor_id, pool, day, microdollars) values (?, ?, ?, ?)",
                    (visitor_id, pool, day, microdollars))

    def spend_microdollars(self, day: str, pool: str | None = None, visitor_id: str | None = None) -> int:
        sql, params = "select coalesce(sum(microdollars), 0) from spend where day = ?", [day]
        if pool:
            sql, params = sql + " and pool = ?", params + [pool]
        if visitor_id:
            sql, params = sql + " and visitor_id = ?", params + [visitor_id]
        return self._db.execute(sql, params).fetchone()[0]

    def spend_rows(self) -> list[dict]:
        return self._rows("select * from spend order by spend_id")

    def log_alert(self, kind: str, detail: str) -> None:
        self._write("insert into alerts (kind, detail, sent_at) values (?, ?, ?)", (kind, detail, self._now()))

    def alerts(self, kind: str | None = None) -> list[dict]:
        if kind:
            return self._rows("select * from alerts where kind = ? order by alert_id", (kind,))
        return self._rows("select * from alerts order by alert_id")

    def visitor_kind(self, visitor_id: str | None) -> str | None:
        rows = self._rows("select kind from visitors where visitor_id = ?", (visitor_id,))
        return rows[0]["kind"] if rows else None

    def make_reviewer(self, visitor_id: str) -> None:
        self._write("insert into visitors (visitor_id, kind, first_seen) values (?, 'reviewer', ?) "
                    "on conflict (visitor_id) do update set kind = 'reviewer'", (visitor_id, self._now()))

    # -- the Staff view and flags (R70 to R72, R75) --------------------------------------------------------------
    def read(self, sql: str, params: tuple = ()) -> list[dict]:
        """A read-only query for the Staff view's numbers (app/ops/metrics.py)."""
        return self._rows(sql, params)

    def agent_messages(self, conversation_id: str) -> list[dict]:
        """The conversation's agent replies, oldest first, each with its receipt fields (None where it has none)."""
        return self._rows("select m.message_id, m.text_masked, m.created_at, r.safety_result, r.route, r.passages, "
                          "r.excluded, r.db_action, r.outcome_label, (r.message_id is not null) as has_receipt "
                          "from messages m left join receipts r using (message_id) where m.conversation_id = ? and "
                          "m.role = 'agent' order by m.message_id", (conversation_id,))

    def conversation_tickets(self, conversation_id: str) -> list[dict]:
        return self._rows("select * from tickets where conversation_id = ? order by ticket_id", (conversation_id,))

    def message(self, message_id: int) -> dict | None:
        rows = self._rows("select * from messages where message_id = ?", (message_id,))
        return rows[0] if rows else None

    def add_flag(self, message_id: int, correction: str) -> int:
        return self._write("insert into flags (message_id, correction, created_at) values (?, ?, ?)",
                           (message_id, mask(correction), self._now()))

    def flags(self) -> list[dict]:
        return self._rows("select f.*, m.conversation_id from flags f join messages m using (message_id) "
                          "order by f.flag_id")

    def conversation_messages(self, conversation_id: str) -> list[dict]:
        return self._rows("select message_id, role, text_masked, created_at from messages where conversation_id = ? "
                          "order by message_id", (conversation_id,))

    # -- background jobs: the nightly reset and the log purge (R74, D31) ----------------------------------------
    def start_job(self, job: str) -> int:
        return self._write("insert into job_runs (job, started_at) values (?, ?)", (job, self._now()))

    def finish_job(self, run_id: int, result: str) -> None:
        """finished_at stays empty for a failed run."""
        self._write("update job_runs set finished_at = ?, result = ? where run_id = ?",
                    (None if result == "failed" else self._now(), result, run_id))

    def job_runs(self, job: str) -> list[dict]:
        return self._rows("select * from job_runs where job = ? order by run_id", (job,))

    def purge_before(self, cutoff: str) -> int:
        """Delete conversations whose last message is before the cutoff, with their messages, sentences, receipts,
        model calls and events; flagged conversations are kept, and their tickets stay for staff, detached."""
        old = ("select conversation_id from conversations where last_message_at < ? and not exists (select 1 from "
               "flags f join messages m using (message_id) where m.conversation_id = conversations.conversation_id)")
        mine = f"select message_id from messages where conversation_id in ({old})"
        try:  # as in log_message, the failure alert waits until the lock is released
            with self._lock:
                self._db.execute("begin immediate")
                try:
                    n = len(self._db.execute(old, (cutoff,)).fetchall())
                    for table in ("sentences", "receipts", "model_calls", "ticket_messages"):
                        self._db.execute(f"delete from {table} where message_id in ({mine})", (cutoff,))
                    self._db.execute(f"update tickets set conversation_id = null where conversation_id in ({old})",
                                     (cutoff,))
                    self._db.execute(f"delete from events where conversation_id in ({old})", (cutoff,))
                    self._db.execute(f"delete from messages where conversation_id in ({old})", (cutoff,))
                    self._db.execute(f"delete from conversations where conversation_id in ({old})", (cutoff,))
                    self._db.execute("commit")
                except BaseException:
                    self._db.execute("rollback")
                    raise
        except Exception as error:
            self._failed(error)
            raise
        return n
