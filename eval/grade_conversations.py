"""Grade test conversations (R14, R57): code checks what the database copy can prove (bookings, cancellations,
moves, handoff reasons); Codex grades the rest (answers, lookups, dropped requests, ticket quality).

A conversation is correct only if both agree."""

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from eval.grader import grade

ROOT = Path(__file__).resolve().parent.parent
SERVICE_OF = {"hvac repair": "hvac_repair", "plumbing": "plumbing", "tune-up": "hvac_tune_up", "replacement estimate": "estimate"}
BOOKING_SUBS = set(SERVICE_OF) | {"burning smell"}
SAFETY_KIND = {"gas, carbon monoxide or sparks": "danger", "burning smell": "burning"}
MEMBER_TIERS = ("standard", "plus")


def _expected_services(case: dict) -> list[str]:
    """The service of each booking the caller should end up with: one per booking request, the sub-reason's own
    booking counted once."""
    services = [r["kind"].split(":", 1)[1] for r in case["requests"]
                if r["kind"].startswith("booking:") and r["expected_outcome"] == "contained"]
    own = SERVICE_OF.get(case["sub_reason"])
    if own and own not in services and any(r["kind"] == "sub-reason" and r["expected_outcome"] == "contained"
                                           for r in case["requests"]):
        services.append(own)
    return sorted(services)


def _replies(conversation: list[dict]) -> list[str]:
    """The agent's whole reply to each caller message, in order."""
    replies = []
    for message in conversation:
        if message["role"] == "caller":
            replies.append("")
        elif replies:
            replies[-1] += " " + message["text"]
    return replies


HOUR_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
              10: "ten", 11: "eleven", 12: "twelve"}
DAY_PARTS = {8: "morning", 12: "afternoon", 13: "afternoon", 16: "evening"}  # the windows by their start hour


def _hour_forms(hour: int) -> list[str]:
    forms = {str(hour), f"{hour:02d}", str(hour % 12 or 12), HOUR_WORDS[hour % 12 or 12]}
    return sorted(forms, key=len, reverse=True) + (["noon", "midday"] if hour == 12 else [])


def names_slot(text: str, slot_date: str, window: str) -> bool:
    """The reply names this date and window, in any of the usual spoken or written forms: "October 19", "19 October",
    "Oct. 19", "10/19", "the 19th", "Monday the 19th", a weekday within the week ahead, "tomorrow"; "8am-12pm",
    "8 to 12", "eight to noon", or the window's part of the day ("the morning window", "Tuesday afternoon")."""
    day = date.fromisoformat(slot_date)
    suffix = r"(?:st|nd|rd|th)?"
    ordinal = r"(?:st|nd|rd|th)"
    dates = [re.escape(slot_date), rf"{day:%B}\s+{day.day}{suffix}\b", rf"\b{day.day}{suffix}\s+(?:of\s+)?{day:%B}",
             rf"\b{day:%b}\.?\s+{day.day}{suffix}\b", rf"(?<![\d/])0?{day.month}/0?{day.day}(?:/(?:20)?\d\d)?(?![\d/])",
             rf"\bthe\s+{day.day}{ordinal}\b", rf"\b{day:%A},?\s+(?:the\s+)?{day.day}{ordinal}\b"]
    from app.config import SETTINGS
    today = SETTINGS.now.date()
    if 0 <= (day - today).days < 7:
        dates.append(rf"\b{day:%A}\b")
    if day == today + timedelta(days=1):
        dates.append(r"\btomorrow\b")
    start, end = (int(part[:2]) for part in window.split("-"))
    times = [rf"\b(?:{'|'.join(_hour_forms(start))})(?::00)?\s*(?:[ap]\.?m\.?)?\s*(?:to|-|–|—|until|through|and)\s*"
             rf"(?:{'|'.join(_hour_forms(end))})(?::00)?(?!\d)"]
    part = DAY_PARTS.get(start)
    if part:  # "the morning window" or "Tuesday afternoon", never a greeting such as "good morning"
        times.append(rf"\b{part}\s+(?:window|slot|visit|appointment|time)\b|\bin\s+the\s+{part}\b|"
                     rf"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+{part}\b")
    return any(re.search(d, text, re.I) for d in dates) and any(re.search(t, text, re.I) for t in times)


_HOUR = r"(?:\d{1,2}(?::\d\d)?\s*(?:[ap]\.?m\.?)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midday)"
# Any appointment window in a reply ("8:00 AM to 12:00 PM", "08:00-12:00", "eight to noon", "the morning window").
WINDOW = re.compile(rf"\b{_HOUR}\s*(?:to|-|–|—|until|through)\s*{_HOUR}(?![\d:])|"
                    r"\b(?:morning|afternoon|evening)\s+(?:window|slot|visit|appointment|time)\b", re.I)


def _read_back_before(attempt, action: str, slot_date: str, window: str) -> bool:
    """The slot the change went to was read back: the most recent agent reply that names a window, before the one
    that reported the change, names this slot and no other window, and is the reply just before the report or a read-back
    ("Just to confirm ..."). Replies naming no window in between (an answer to a question asked at the read-back)
    do not matter; a reply in between naming or offering a different slot, or an offer of several, does."""
    replies = _replies(attempt.conversation)
    reported = next((n for n, event in enumerate(attempt.done_events) if action in event.get("db_actions", [])), None)
    if not reported:
        return False
    for n in range(reported - 1, -1, -1):
        reply = replies[n]
        # The read-back sentence itself decides when there is one, so a reply that also says another window is not
        # available ("I can't offer 12pm-4pm that day. To confirm, ... 1pm to 5pm.") still counts (T1dee0920).
        confirming = [s for s in re.split(r"(?<=[.!?])\s+", reply) if CONFIRMING.search(s) and WINDOW.search(s)]
        if confirming:  # only a confirming sentence that names a window ("... clear yes to confirm." names none)
            reply = " ".join(confirming)
        windows = [m.group(0) for m in WINDOW.finditer(reply)]
        others = [w for w in windows if not names_slot(f"{slot_date} {w}", slot_date, window)]
        if names_slot(reply, slot_date, window) and not others:
            return n == reported - 1 or bool(READ_BACK.search(replies[n]))
        if windows or names_slot(reply, slot_date, window):
            return False  # a different slot, or an offer of several, since the read-back
    return False


def _freed(seed_status: str) -> str:
    """A freed slot goes back to its seed status if that was open or members-only, otherwise open (D33)."""
    return seed_status if seed_status in ("open", "reserved_members") else "open"


def _slot_problems(db, start: dict, slot_id: int, case: dict, service: str | None) -> list[str]:
    from app.config import SETTINGS
    row = db.execute("select slot_date, window, zone, service_type, status from appointment_slots where slot_id = ?",
                     (slot_id,)).fetchone()
    if row is None:
        return [f"slot {slot_id} does not exist"]
    slot_date, window, zone, service_type, status = row
    card, problems = case["caller_card"], []
    if service and service_type != service:
        problems.append(f"slot {slot_id} is {service_type}, not {service}")
    if card.get("zone") and zone != card["zone"]:
        problems.append(f"slot {slot_id} is in the {zone} zone, not {card['zone']}")
    was = start["appointment_slots"][slot_id][-1]
    if was in ("booked", "blocked"):
        problems.append(f"slot {slot_id} was {was} before the call")
    if was == "reserved_members" and card.get("membership_tier") not in MEMBER_TIERS:
        problems.append(f"slot {slot_id} is members-only and the caller is not a member")
    if status != "booked":
        problems.append(f"slot {slot_id} is not marked booked")
    if db.execute("select count(*) from appointments where slot_id = ? and status = 'scheduled'", (slot_id,)).fetchone()[0] > 1:
        problems.append(f"slot {slot_id} holds more than one appointment")
    if datetime.fromisoformat(f"{slot_date}T{window[:5]}").replace(tzinfo=SETTINGS.now.tzinfo) <= SETTINGS.now:
        problems.append(f"slot {slot_id} has already started")
    return problems


def _slot_of(db, slot_id: int) -> tuple:
    return db.execute("select slot_date, window, service_type from appointment_slots where slot_id = ?", (slot_id,)).fetchone()


def _seed_status(slot_id: int) -> str:
    from app.config import SETTINGS
    with sqlite3.connect(SETTINGS.seed_db_path) as seed:
        return seed.execute("select status from appointment_slots where slot_id = ?", (slot_id,)).fetchone()[0]


# The agent's read-back wording ("Just to confirm ...", "To read it back ...", "Can you give me a clear yes?",
# 'a clear "yes"' with straight or curly quotes).
CONFIRMING = re.compile(r"\b(?:just )?to confirm\b|\bto read it back\b|\bjust to be sure\b", re.I)
READ_BACK = re.compile(r"\b(just to confirm|just to be sure|to read it back|can you give me a clear)\b|"
                       r"\bclear\s+[\"\u201c\u201d']?yes\b", re.I)


def _answers(attempt) -> list[tuple[str, str]]:
    """Each agent reply with the caller message that answered it."""
    replies, callers = _replies(attempt.conversation), [m["text"] for m in attempt.conversation if m["role"] == "caller"]
    return list(zip(replies, callers[1:]))


def _named(text: str, slots: list[dict]) -> list[dict]:
    return [s for s in slots if names_slot(text, s["slot_date"], s["window"])]


def _confirmed_a_read_back(attempt, slots: list[dict]) -> bool:
    """The caller gave a clear yes straight after an agent read-back, by the agent's own confirm rule (R52): the
    read-back's slot is found among slots, and a yes naming another day or time does not confirm it."""
    from app.config import SETTINGS
    from app.flows.scheduling import AFFIRMATIVE, HEDGE, confirms
    for reply, answer in _answers(attempt):
        if not READ_BACK.search(reply):
            continue
        read_back = _named(reply, slots)
        if read_back and any(confirms(answer, s["slot_date"], s["window"], SETTINGS.now) for s in read_back):
            return True
        if not read_back and AFFIRMATIVE.search(answer) and not HEDGE.search(AFFIRMATIVE.sub("", answer, count=1)):
            return True
    return False


def _picked_an_offered_slot(attempt, slots: list[dict]) -> bool:
    """The caller named one of the slots the agent had just offered in a way the agent's own picker reads (a day and
    window, a part of the day, an ordinal), so the agent could have booked it."""
    from app.config import SETTINGS
    from app.flows.scheduling import _pick
    offered = []
    for reply, answer in _answers(attempt):
        offered = _named(reply, slots) or offered
        if offered and _pick(answer, offered, SETTINGS.now):
            return True
    return False


def _slots_in(db) -> list[dict]:
    return [{"slot_date": d, "window": w} for d, w in db.execute("select distinct slot_date, window from appointment_slots "
                                                                 "order by slot_date, window")]


def conversation_now() -> str:
    """The test's fixed date and time, which every conversation happens at; the grader judges dates against it."""
    from app.config import SETTINGS
    return SETTINGS.now.strftime("%A %d %B %Y, %H:%M") + " (America/Chicago)"


def database_checks(case: dict, attempt) -> dict:
    """What the database copy shows against what the case expected, measured from the copy as the call started (the
    seed with the case's fixtures), so planted rows are never taken for the agent's. Problems go in "booking_problems"."""
    from eval.fixtures import snapshot, start_state
    start, now = start_state(case.get("fixtures", [])), snapshot(Path(attempt.db_path))
    checks, problems = {}, []
    allowed_appointments, allowed_slots = set(), set()
    customer = case["caller_card"]["customer_id"]
    new = [row for key, row in now["appointments"].items() if key not in start["appointments"] and row[3] == customer]
    with sqlite3.connect(attempt.db_path) as db:
        wants_booking = case["sub_reason"] in BOOKING_SUBS or any(r["kind"].startswith("booking:") for r in case["requests"])
        if wants_booking:
            expected = _expected_services(case)
            scheduled = [row for row in new if row[6] == "scheduled"]
            if not expected:
                problems += [f"appointment {row[0]} was booked" for row in scheduled]
            else:
                booked = sorted(_slot_of(db, row[2])[2] for row in scheduled)
                missed_only = False
                if booked != expected:
                    problems.append(f"booked {booked or 'nothing'}, expected {expected}")
                    # Fewer bookings than expected, none of them wrong, no confirmed read-back left unbooked and no
                    # offered slot the caller named: the caller never chose a slot, a missed request, not a fault (D49).
                    slots = _slots_in(db)
                    missed_only = all(service in expected for service in booked) and len(booked) < len(expected) \
                        and not _confirmed_a_read_back(attempt, slots) and not _picked_an_offered_slot(attempt, slots)
                for row in scheduled:
                    slot_date, window, service = _slot_of(db, row[2])
                    problems += _slot_problems(db, start, row[2], case, None)
                    if not _read_back_before(attempt, f"booked appointment {row[0]}", slot_date, window):
                        problems.append(f"appointment {row[0]} was not read back before it was booked")
                allowed_appointments |= {row[0] for row in new}
                allowed_slots |= {row[2] for row in new}
            checks["booking_correct"] = not problems
            checks["booking_fault"] = bool(problems) and not (missed_only and len(problems) == 1)
        appointment = case.get("appointment")
        kind = case["sub_reason"]
        if appointment and kind in ("cancel appointment", "reschedule", "confirm"):
            target = appointment["appointment_id"]
            old_slot = start["appointments"][target][2]
            row = now["appointments"].get(target)
            status, slot = (row[6], row[2]) if row else (None, None)
            own = []
            if new:
                own.append(f"new appointments {[r[0] for r in new]} for a {kind} call")
            if kind == "confirm":
                own += [] if (status, slot) == ("scheduled", old_slot) else ["the appointment changed"]
            elif kind == "cancel appointment":
                if status != "cancelled":
                    own.append(f"appointment {target} is {status}, not cancelled")
            else:
                if status != "scheduled" or slot == old_slot:
                    own.append(f"appointment {target} was not moved")
                else:
                    slot_date, window, service = _slot_of(db, slot)
                    own += _slot_problems(db, start, slot, case, _slot_of(db, old_slot)[2])
                    if not _read_back_before(attempt, f"rescheduled appointment {target}", slot_date, window):
                        own.append(f"appointment {target} was not moved to the slot read back")
                    allowed_slots.add(slot)
            if kind != "confirm":
                freed = now["appointment_slots"][old_slot][-1]
                if freed != _freed(_seed_status(old_slot)):
                    own.append(f"old slot {old_slot} is {freed}, not freed")
                if db.execute("select 1 from appointments where slot_id = ? and status = 'scheduled'", (old_slot,)).fetchone():
                    own.append(f"old slot {old_slot} still holds a scheduled appointment")
                allowed_appointments.add(target)
                allowed_slots.add(old_slot)
            problems += own
            checks["booking_correct"] = not own
            checks["booking_fault"] = bool(own)
    unexpected = [f"{table} {key} changed" for table in now for key in set(now[table]) | set(start[table])
                  if now[table].get(key) != start[table].get(key)
                  and not (table == "appointments" and key in allowed_appointments)
                  and not (table == "appointment_slots" and key in allowed_slots)]
    checks["no_unexpected_writes"] = not unexpected
    if unexpected and "booking_fault" in checks:  # an unexpected write is a fault too (D49)
        checks["booking_fault"] = True
    if problems:
        checks["booking_problems"] = problems
    if unexpected:
        checks["unexpected_writes"] = sorted(unexpected)
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


def _ops(attempt) -> Path:
    return Path(attempt.db_path).with_name(Path(attempt.db_path).stem + "-ops.sqlite")


def _this_conversation(attempt, column: str) -> tuple[str, tuple]:
    """Rows of this attempt's conversation only (older attempts without an id read the whole database)."""
    conversation = getattr(attempt, "conversation_id", None)
    return (f" and ({column} = ? or {column} is null)", (conversation,)) if conversation else ("", ())


def receipt_labels(attempt) -> list[str]:
    ops = _ops(attempt)
    if not ops.exists():
        return []
    where, params = _this_conversation(attempt, "m.conversation_id")
    with sqlite3.connect(ops) as db:
        return [label for (raw,) in db.execute("select r.passages from receipts r join messages m using (message_id) "
                                               f"where r.passages is not null{where} order by r.message_id", params)
                for label in json.loads(raw or "[]")]


def retrieved_passages(attempt) -> list[str]:
    """The text of every passage the agent's replies were written from, from its receipts and the built index."""
    from app.knowledge.index import load_index
    labels = receipt_labels(attempt)
    if not labels:
        return []
    chunks, _ = load_index(ROOT / "data" / "index")
    by_label = {f"{c.document} ({c.effective_date or 'undated'}), {c.heading}": c.text for c in chunks}
    return [f"[{label}] {by_label[label]}" for label in dict.fromkeys(labels) if label in by_label]


def default_tickets(attempt) -> list[dict]:
    """This conversation's tickets as staff see them: every reason tag (the first, then any added when a later
    handoff joined the ticket) and the caller's messages added after the handoff."""
    ops = _ops(attempt)
    if not ops.exists():
        return []
    where, params = _this_conversation(attempt, "conversation_id")
    with sqlite3.connect(ops) as db:
        db.row_factory = sqlite3.Row
        tickets = [dict(r) for r in db.execute("select ticket_id, reason_tag, priority, who, wants, tried, constraints, mood "
                                               f"from tickets where 1 = 1{where} order by ticket_id", params)]
        has_tags = db.execute("select 1 from sqlite_master where name = 'ticket_tags'").fetchone()
        for ticket in tickets:
            added = [r[0] for r in db.execute("select tag from ticket_tags where ticket_id = ? order by rowid",
                                              (ticket["ticket_id"],))] if has_tags else []
            ticket["tags"] = [ticket["reason_tag"]] + [t for t in added if t != ticket["reason_tag"]]
            ticket["later_messages"] = [r[0] for r in db.execute(
                "select m.text_masked from ticket_messages t join messages m using (message_id) where t.ticket_id = ? "
                "order by m.message_id", (ticket["ticket_id"],))]
        return tickets


def _tags(ticket: dict) -> list[str]:
    return ticket.get("tags") or [ticket["reason_tag"]]


def _safety_released_first(attempt, kind: str) -> bool:
    """The fixed safety reply was the first thing the agent said in answer to some caller message."""
    from app.safety.replies import fixed_reply
    first = fixed_reply(kind)[0]
    talk = attempt.conversation
    return any(m["role"] == "agent" and m["text"] == first and talk[n - 1]["role"] == "caller"
               for n, m in enumerate(talk) if n)


def grade_attempts(attempts: list, cases: dict, runner, tickets=default_tickets, model: str | None = None,
                   on_verdicts=None) -> list:
    """Code checks, then Codex. A conversation passes only when Codex says so and every code check that applies to
    it passed; a check that applies but is missing counts as failing. on_verdicts(verdicts, attempts) is called after
    each grading batch with that batch's verdicts and its newly graded attempts."""
    items, keep, required = [], [], []
    for attempt in attempts:
        case = cases[attempt.case_id]
        opened = tickets(attempt)
        checks = database_checks(case, attempt)
        attempt.grades.update(checks)
        needed = [k for k in ("booking_correct", "no_unexpected_writes") if k in checks]
        expected_reason = case.get("expected_handoff_reason")
        if case["expected_outcome"] == "handed_off":
            needed.append("handoff_reason_correct")
            if expected_reason:
                tagged = any(expected_reason in _tags(t) for t in opened)
            else:  # no reason expected: any reason passes, as long as the call was handed off
                tagged = attempt.handed_off or bool(opened)
            if case["sub_reason"] in SAFETY_KIND:
                tagged = tagged and _safety_released_first(attempt, SAFETY_KIND[case["sub_reason"]])
            attempt.grades["handoff_reason_correct"] = tagged
        items.append({"id": f"{attempt.case_id}|{attempt.attempt}", "type": "conversation", "requests": case["requests"],
                      "expected_outcome": case["expected_outcome"], "expected_handoff_reason": expected_reason,
                      "reference_answer": case.get("reference_answer"), "passages": _passages(case),
                      "retrieved_passages": retrieved_passages(attempt),
                      "account_facts": _account_facts(case, attempt.db_path), "must_not": case.get("must_not", []),
                      "transcript": attempt.conversation, "tickets": opened, "now": conversation_now()})
        keep.append(attempt)
        required.append(needed)
    position = [0]

    def apply(verdicts):
        """One graded batch: its attempts get their grades at once, then on_verdicts may save them, so a failure in
        a later batch keeps this one."""
        start = position[0]
        position[0] += len(verdicts)
        rows = list(zip(keep[start:position[0]], verdicts, required[start:position[0]]))
        for attempt, verdict, needed in rows:
            attempt.grades.update({"knowledge_correct": verdict.knowledge_correct, "lookup_correct": verdict.lookup_correct,
                                   "ticket_actionable": verdict.ticket_actionable, "requests": verdict.requests,
                                   "why": verdict.why, "grader_model": verdict.model})
            attempt.grades = {k: v for k, v in attempt.grades.items() if v is not None}
            code_ok = all(attempt.grades.get(k) is True for k in needed)
            attempt.all_correct = verdict.correct is True and code_ok
        if on_verdicts:
            on_verdicts(verdicts, [attempt for attempt, _, _ in rows])

    grade(items, runner, model, on_batch=apply)
    return keep
