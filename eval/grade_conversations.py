"""Grade test conversations (R14, R57): code checks what the database copy can prove (bookings, cancellations,
moves, handoff reasons); Codex grades the rest (answers, lookups, dropped requests, ticket quality).

A conversation is correct only if both agree."""

import sqlite3
from pathlib import Path

from eval.grader import grade

ROOT = Path(__file__).resolve().parent.parent
BOOKING_SUBS = {"hvac repair", "plumbing", "tune-up", "replacement estimate", "burning smell"}
SEEDED_LAST_APPOINTMENT = 159


def _new_appointments(db: sqlite3.Connection, customer_id: str) -> list[tuple]:
    return db.execute("select appointment_id, status from appointments where customer_id = ? and appointment_id > ? "
                      "and appointment_id < 5000", (customer_id, SEEDED_LAST_APPOINTMENT)).fetchall()


def database_checks(case: dict, attempt) -> dict:
    """What the database copy shows against what the case expected."""
    checks = {}
    with sqlite3.connect(attempt.db_path) as db:
        customer = case["caller_card"]["customer_id"]
        wants_booking = case["sub_reason"] in BOOKING_SUBS or any(r["kind"].startswith("booking:") for r in case["requests"])
        if wants_booking:
            booked = [a for a in _new_appointments(db, customer) if a[1] == "scheduled"]
            should_book = any(r["expected_outcome"] == "contained" and (r["kind"].startswith("booking:") or
                                                                         (r["kind"] == "sub-reason" and case["sub_reason"] in BOOKING_SUBS))
                              for r in case["requests"])
            checks["booking_correct"] = bool(booked) if should_book else not booked
        appointment = case.get("appointment")
        if appointment and case["sub_reason"] in ("cancel appointment", "reschedule", "confirm"):
            status, slot = db.execute("select status, slot_id from appointments where appointment_id = ?",
                                      (appointment["appointment_id"],)).fetchone()
            checks["booking_correct"] = {"cancel appointment": status == "cancelled",
                                         "reschedule": status == "scheduled" and slot != appointment["slot_id"],
                                         "confirm": status == "scheduled" and slot == appointment["slot_id"]}[case["sub_reason"]]
    return checks


def _passages(case: dict) -> list[str]:
    out = []
    for span in case.get("evidence_spans", []):
        lines = (ROOT / "data" / "kb_text" / span["file"]).read_text().splitlines()
        out.append(f"[{span['file']}, {span['heading']}] " + " ".join(lines[span["start_line"] - 1:span["end_line"]]))
    return out


def _account_facts(case: dict, db_path: str | None = None) -> dict:
    facts = {"caller_card": case["caller_card"], "planted": [f["row"] for f in case.get("fixtures", [])],
             "existing_appointment": case.get("appointment")}
    tier = case["caller_card"].get("membership_tier")
    if tier in ("standard", "plus"):  # the lookup reads the renewal at the current published price (R46)
        from app.accounts.fees import MEMBERSHIP_PRICE_CENTS
        facts["membership_renewal_price"] = f"${MEMBERSHIP_PRICE_CENTS[tier] / 100:,.2f} a year, the current published price"
    if db_path:  # the customer's appointments in the seed, so a real one is not taken for an invented one
        from app.config import SETTINGS
        with sqlite3.connect(SETTINGS.seed_db_path) as seed:
            seed.row_factory = sqlite3.Row
            facts["scheduled_appointments_at_start"] = [dict(r) for r in seed.execute(
                "select a.appointment_id, s.slot_date, s.window, s.service_type, t.name as technician from appointments a "
                "join appointment_slots s using (slot_id) join technicians t using (tech_id) "
                "where a.customer_id = ? and a.status = 'scheduled'", (case["caller_card"]["customer_id"],))]
    return facts


def retrieved_passages(attempt) -> list[str]:
    """The text of every passage the agent's replies were written from, from its receipts and the built index."""
    import json
    from app.knowledge.index import load_index
    ops = Path(attempt.db_path).with_name(Path(attempt.db_path).stem + "-ops.sqlite")
    if not ops.exists():
        return []
    with sqlite3.connect(ops) as db:
        labels = [label for (raw,) in db.execute("select passages from receipts where passages is not null")
                  for label in json.loads(raw or "[]")]
    chunks, _ = load_index(ROOT / "data" / "index")
    by_label = {f"{c.document} ({c.effective_date or 'undated'}), {c.heading}": c.text for c in chunks}
    return [f"[{label}] {by_label[label]}" for label in dict.fromkeys(labels) if label in by_label]


def default_tickets(attempt) -> list[dict]:
    ops = Path(attempt.db_path).with_name(Path(attempt.db_path).stem + "-ops.sqlite")
    if not ops.exists():
        return []
    with sqlite3.connect(ops) as db:
        db.row_factory = sqlite3.Row
        tickets = [dict(r) for r in db.execute("select ticket_id, reason_tag, priority, who, wants, tried, constraints, mood from tickets")]
        for ticket in tickets:  # what staff see: the ticket and the caller's messages added to it after the handoff
            ticket["later_messages"] = [r[0] for r in db.execute(
                "select m.text_masked from ticket_messages t join messages m using (message_id) where t.ticket_id = ? "
                "order by m.message_id", (ticket["ticket_id"],))]
        return tickets


def grade_attempts(attempts: list, cases: dict, runner, tickets=default_tickets) -> list:
    items, keep = [], []
    for attempt in attempts:
        case = cases[attempt.case_id]
        opened = tickets(attempt)
        attempt.grades.update(database_checks(case, attempt))
        expected_reason = case.get("expected_handoff_reason")
        if case["expected_outcome"] == "handed_off" and expected_reason:
            attempt.grades["handoff_reason_correct"] = any(t["reason_tag"] == expected_reason for t in opened) or \
                case["sub_reason"] in ("gas, carbon monoxide or sparks", "burning smell")
        items.append({"id": f"{attempt.case_id}|{attempt.attempt}", "type": "conversation", "requests": case["requests"],
                      "expected_outcome": case["expected_outcome"], "expected_handoff_reason": expected_reason,
                      "reference_answer": case.get("reference_answer"), "passages": _passages(case),
                      "retrieved_passages": retrieved_passages(attempt),
                      "account_facts": _account_facts(case, attempt.db_path), "must_not": case.get("must_not", []),
                      "transcript": attempt.conversation, "tickets": opened})
        keep.append(attempt)
    for attempt, verdict in zip(keep, grade(items, runner)):
        attempt.grades.update({"knowledge_correct": verdict.knowledge_correct, "lookup_correct": verdict.lookup_correct,
                               "ticket_actionable": verdict.ticket_actionable, "requests": verdict.requests,
                               "why": verdict.why, "grader_model": verdict.model})
        attempt.grades = {k: v for k, v in attempt.grades.items() if v is not None}
        code_ok = all(attempt.grades.get(k, True) for k in ("booking_correct", "handoff_reason_correct"))
        attempt.all_correct = bool(verdict.correct) and code_ok
    return keep
