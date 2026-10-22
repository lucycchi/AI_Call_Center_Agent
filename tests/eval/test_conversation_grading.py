import json
import shutil
import sqlite3
from pathlib import Path

from eval.fixtures import apply_fixtures
from eval.harness import Attempt

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
CARD = {"customer_id": "MHC-10001", "name": "Linda Foster", "membership_tier": "standard", "city": "Round Rock", "zone": "north"}
NON_MEMBER = {"customer_id": "MHC-10004", "name": "Daniel Reyes", "membership_tier": "none", "city": "Georgetown", "zone": "north"}


def _case(sub="hvac repair", outcome="contained", card=CARD, appointment=None, fixtures=(), requests=None, reason=None):
    return {"case_id": "c1", "calls_weight": 1, "reason": "new booking", "sub_reason": sub, "expected_outcome": outcome,
            "expected_handoff_reason": reason, "needs_documents": False, "reference_answer": None, "evidence_spans": [],
            "fixtures": list(fixtures), "caller_script": ["hi"], "caller_card": card, "appointment": appointment,
            "requests": requests or [{"request": sub, "kind": "sub-reason", "expected_outcome": outcome, "handoff_reason": reason}]}


def _db(tmp_path, fixtures=(), sql=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "c.sqlite"
    shutil.copy(SEED, db)
    apply_fixtures(db, list(fixtures))
    conn = sqlite3.connect(db)
    for statement in sql:
        conn.execute(statement)
    conn.commit()
    conn.close()
    return db


def _book(slot, customer="MHC-10001", mark=True):
    return ([f"update appointment_slots set status='booked' where slot_id={slot}"] if mark else []) + [
        f"insert into appointments (slot_id, customer_id, issue_description, created_at, status) "
        f"values ({slot}, '{customer}', 'x', '2026-10-16T09:00', 'scheduled')"]


def _attempt(db, readback="Monday, October 19, 8am to 12pm", action="booked appointment 160"):
    conversation = [{"role": "caller", "text": "I need a repair"},
                    {"role": "agent", "text": f"I can book an HVAC repair on {readback}."},
                    {"role": "agent", "text": "Shall I go ahead?"},
                    {"role": "caller", "text": "yes"},
                    {"role": "agent", "text": "Booked."}]
    return Attempt("c1", db_path=str(db), conversation=conversation,
                   done_events=[{"db_actions": []}, {"db_actions": [action] if action else []}])


def _checks(case, attempt):
    from eval.grade_conversations import database_checks
    return database_checks(case, attempt)


def test_a_correct_booking_matches_the_read_back(tmp_path):
    checks = _checks(_case(), _attempt(_db(tmp_path, sql=_book(56))))
    assert checks["booking_correct"] is True and checks["no_unexpected_writes"] is True


def test_a_booking_of_the_wrong_service_or_zone_fails(tmp_path):
    tune_up = _attempt(_db(tmp_path / "a", sql=_book(41)))  # a tune-up slot, same date and window
    assert _checks(_case(), tune_up)["booking_correct"] is False
    south = _attempt(_db(tmp_path / "b", sql=_book(115)), readback="Wednesday, October 21, 8am to 12pm")
    assert _checks(_case(), south)["booking_correct"] is False


def test_a_non_member_in_a_members_only_slot_fails(tmp_path):
    attempt = _attempt(_db(tmp_path, sql=_book(110, "MHC-10004")), readback="Wednesday, October 21, 12pm to 4pm")
    assert _checks(_case(card=NON_MEMBER), attempt)["booking_correct"] is False
    member = _attempt(_db(tmp_path / "m", sql=_book(110)), readback="Wednesday, October 21, 12pm to 4pm")
    assert _checks(_case(), member)["booking_correct"] is True


def test_a_booking_whose_slot_is_not_marked_booked_fails(tmp_path):
    assert _checks(_case(), _attempt(_db(tmp_path, sql=_book(56, mark=False))))["booking_correct"] is False


def test_a_booking_that_differs_from_the_read_back_or_has_none_fails(tmp_path):
    other_day = _attempt(_db(tmp_path / "a", sql=_book(56)), readback="Tuesday, October 20, 8am to 12pm")
    assert _checks(_case(), other_day)["booking_correct"] is False
    other_window = _attempt(_db(tmp_path / "b", sql=_book(56)), readback="Monday, October 19, 12pm to 4pm")
    assert _checks(_case(), other_window)["booking_correct"] is False
    silent = _attempt(_db(tmp_path / "c", sql=_book(56)), readback="a time that suits")
    assert _checks(_case(), silent)["booking_correct"] is False


def test_a_duplicate_booking_fails(tmp_path):
    attempt = _attempt(_db(tmp_path, sql=_book(56) + _book(57)))
    assert _checks(_case(), attempt)["booking_correct"] is False


def test_a_booking_after_a_planted_appointment_is_found(tmp_path):
    planted = [{"table": "appointments", "row": {"appointment_id": 5000, "slot_id": 72, "customer_id": "MHC-10001",
                                                 "issue_description": "x", "created_at": "2026-10-10", "status": "scheduled"},
                "book_slots": [72]}]
    db = _db(tmp_path, planted, sql=_book(56))
    assert sqlite3.connect(db).execute("select max(appointment_id) from appointments").fetchone()[0] == 5001
    checks = _checks(_case(fixtures=planted), _attempt(db, action="booked appointment 5001"))
    assert checks["booking_correct"] is True and checks["no_unexpected_writes"] is True


APPOINTMENT = {"appointment_id": 159, "slot_id": 159, "source": "seed"}


def _seed_slot_of(appointment_id):
    return sqlite3.connect(SEED).execute("select slot_id from appointments where appointment_id = ?", (appointment_id,)).fetchone()[0]


def test_a_reschedule_moves_to_the_read_back_slot_and_frees_the_old_one(tmp_path):
    old = _seed_slot_of(159)
    appointment = {**APPOINTMENT, "slot_id": old}
    moved = _db(tmp_path / "a", sql=["update appointment_slots set status='booked' where slot_id=56",
                                     "update appointments set slot_id=56 where appointment_id=159",
                                     f"update appointment_slots set status='open' where slot_id={old}"])
    case = _case("reschedule", appointment=appointment)
    assert _checks(case, _attempt(moved, action="rescheduled appointment 159"))["booking_correct"] is True
    not_freed = _db(tmp_path / "b", sql=["update appointment_slots set status='booked' where slot_id=56",
                                         "update appointments set slot_id=56 where appointment_id=159"])
    assert _checks(case, _attempt(not_freed, action="rescheduled appointment 159"))["booking_correct"] is False
    elsewhere = _attempt(moved, readback="Tuesday, October 20, 8am to 12pm", action="rescheduled appointment 159")
    assert _checks(case, elsewhere)["booking_correct"] is False


def test_a_cancellation_must_also_free_the_slot(tmp_path):
    old = _seed_slot_of(159)
    case = _case("cancel appointment", appointment={**APPOINTMENT, "slot_id": old})
    freed = _db(tmp_path / "a", sql=["update appointments set status='cancelled' where appointment_id=159",
                                     f"update appointment_slots set status='open' where slot_id={old}"])
    assert _checks(case, _attempt(freed, action="cancelled appointment 159"))["booking_correct"] is True
    held = _db(tmp_path / "b", sql=["update appointments set status='cancelled' where appointment_id=159"])
    assert _checks(case, _attempt(held, action="cancelled appointment 159"))["booking_correct"] is False


def test_a_write_in_a_case_that_should_not_touch_the_database_is_flagged(tmp_path):
    from eval.grade_conversations import grade_attempts
    from tests.eval.test_grader import FakeRunner
    case = _case("transfer", requests=[{"request": "transfer", "kind": "sub-reason", "expected_outcome": "contained",
                                        "handoff_reason": None}])
    clean = _checks(case, _attempt(_db(tmp_path / "a"), action=None))
    assert clean == {"no_unexpected_writes": True}
    written = _attempt(_db(tmp_path / "b", sql=_book(56)))
    assert _checks(case, written)["no_unexpected_writes"] is False
    [graded] = grade_attempts([written], {"c1": case}, FakeRunner(), tickets=lambda a: [])
    assert graded.all_correct is False and graded.grades["unexpected_writes"]


SAFETY_CASE = _case("gas, carbon monoxide or sparks", "handed_off", reason="emergency")


def _safety_attempt(tmp_path, first):
    from app.safety.replies import fixed_reply
    reply = fixed_reply("danger")
    agent = [first] + [s for s in reply if s != first]
    return Attempt("c1", handed_off=True, db_path=str(_db(tmp_path)),
                   conversation=[{"role": "caller", "text": "I smell gas"}] + [{"role": "agent", "text": s} for s in agent],
                   done_events=[{"db_actions": []}])


def test_a_safety_case_needs_the_fixed_reply_first_and_a_safety_ticket(tmp_path):
    from app.safety.replies import fixed_reply
    from eval.grade_conversations import grade_attempts
    from tests.eval.test_grader import FakeRunner
    cases = {"c1": SAFETY_CASE}
    emergency = [{"ticket_id": 1, "reason_tag": "emergency"}]
    [good] = grade_attempts([_safety_attempt(tmp_path / "a", fixed_reply("danger")[0])], cases, FakeRunner(), tickets=lambda a: emergency)
    assert good.grades["handoff_reason_correct"] is True
    [late] = grade_attempts([_safety_attempt(tmp_path / "b", "Let me look into that.")], cases, FakeRunner(), tickets=lambda a: emergency)
    assert late.grades["handoff_reason_correct"] is False
    [no_ticket] = grade_attempts([_safety_attempt(tmp_path / "c", fixed_reply("danger")[0])], cases, FakeRunner(),
                                 tickets=lambda a: [{"ticket_id": 1, "reason_tag": "complaint"}])
    assert no_ticket.grades["handoff_reason_correct"] is False and no_ticket.all_correct is False


def test_a_missing_code_grade_fails_the_conversation(tmp_path, monkeypatch):
    import eval.grade_conversations as gc
    from tests.eval.test_grader import FakeRunner
    monkeypatch.setattr(gc, "database_checks", lambda case, attempt: {"booking_correct": None})
    [graded] = gc.grade_attempts([_attempt(_db(tmp_path, sql=_book(56)))], {"c1": _case()}, FakeRunner(), tickets=lambda a: [])
    assert graded.all_correct is False


def test_a_missing_handoff_grade_counts_as_failing_in_the_scores():
    from eval.scoring import score
    case = _case("complaint or manager", "handed_off", reason="complaint")
    case["reason"] = "complaint"
    summary = score([Attempt("c1", handed_off=True, all_correct=True)], [case])
    assert summary.handoff_correct_other == 0.0


def test_grading_reads_only_this_conversations_tickets_and_receipts(tmp_path):
    from app.ops.store import OpsStore
    from eval.grade_conversations import default_tickets, receipt_labels
    db = _db(tmp_path)
    ops = OpsStore(db.with_name(db.stem + "-ops.sqlite"))
    for conversation in ("old", "new"):
        ops.open_conversation("eval", conversation)
        ops.create_ticket(conversation, "who", "wants", "tried", "", "calm", f"{conversation} tag")
        message = ops.log_message(conversation, "agent", "text")
        ops.log_receipt(message, "clear", "knowledge", [f"{conversation} passage"], [], None, "answered")
    attempt = Attempt("c1", db_path=str(db), conversation_id="new")
    assert [t["reason_tag"] for t in default_tickets(attempt)] == ["new tag"]
    assert receipt_labels(attempt) == ["new passage"]


def test_each_attempt_starts_with_a_fresh_operations_database(tmp_path):
    from app.core.types import DoneEvent, SentenceEvent
    from app.ops.store import OpsStore
    from eval.budget import RunBudget
    from eval.harness import run_case
    from tests.eval.test_scoring import ScriptedCaller, case

    class TicketEngine:
        def __init__(self, ops_path):
            self.store = OpsStore(ops_path)

        def handle(self, turn):
            self.store.open_conversation("eval", turn.conversation_id)
            ticket = self.store.create_ticket(turn.conversation_id, "w", "w", "t", "", "calm", "complaint")
            yield SentenceEvent("ok")
            yield DoneEvent(route="handoff", ticket=ticket, outcome="handed_off")

    for _ in range(2):
        result = run_case(case("x", 1), lambda db, ops: TicketEngine(ops), ScriptedCaller(["hi"]), RunBudget(8.0), tmp_path)
    ops = Path(result.db_path).with_name(Path(result.db_path).stem + "-ops.sqlite")
    assert sqlite3.connect(ops).execute("select count(*) from tickets").fetchone()[0] == 1
    assert result.conversation_id and json.dumps(result.conversation_id)


def test_a_reason_added_to_an_open_ticket_counts_and_codex_sees_every_tag(tmp_path):
    from app.ops.store import OpsStore
    from eval.grade_conversations import default_tickets, grade_attempts
    from tests.eval.test_grader import FakeRunner
    db = _db(tmp_path)
    ops = OpsStore(db.with_name(db.stem + "-ops.sqlite"))
    ops.open_conversation("eval", "conv")
    ticket = ops.create_ticket("conv", "who", "wants", "tried", "", "calm", "complaint")
    ops.add_reason(ticket, "dispute", "questions the invoice")
    attempt = Attempt("c1", handed_off=True, db_path=str(db), conversation_id="conv",
                      conversation=[{"role": "caller", "text": "manager"}, {"role": "agent", "text": "Passed on."}],
                      done_events=[{"db_actions": []}])
    assert default_tickets(attempt)[0]["tags"] == ["complaint", "dispute"]
    runner = FakeRunner()
    case = _case("refund", "handed_off", reason="dispute")
    [graded] = grade_attempts([attempt], {"c1": case}, runner)
    assert graded.grades["handoff_reason_correct"] is True
    assert '"tags": ["complaint", "dispute"]' in runner.prompts[0]


# -- a booking-type case that expects no booking (the final run's grading crash) -----------------------------------

def test_a_booking_case_expecting_no_booking_passes_when_nothing_is_booked(tmp_path):
    from eval.grade_conversations import _expected_services
    case = _case(outcome="handed_off", reason="safety")
    assert _expected_services(case) == []
    checks = _checks(case, _attempt(_db(tmp_path), action=None))
    assert checks["booking_correct"] is True and checks["booking_fault"] is False


def test_a_booking_case_expecting_no_booking_fails_when_something_is_booked(tmp_path):
    checks = _checks(_case(outcome="handed_off", reason="safety"), _attempt(_db(tmp_path, sql=_book(56))))
    assert checks["booking_correct"] is False and checks["booking_fault"] is True
    assert any("was booked" in p for p in checks["booking_problems"])


def test_a_slot_planted_by_a_case_is_not_in_the_seed_and_is_freed_to_open():
    # Seen grading the fresh set: a reschedule's old slot was planted by the case (slot 9000 and up), so the seed
    # lookup found no row and crashed; the freed-slot rule (D33) sends a slot not in the seed back to open.
    from eval.grade_conversations import _freed, _seed_status
    assert _seed_status(999999) is None
    assert _freed(_seed_status(999999)) == "open"


# -- money and membership actions (Milestone 7, Task 32; actions decision (D54)) ------------------------------------

def _ops_with(db, *rows):
    from app.ops.store import OpsStore
    store = OpsStore(Path(db).with_name(Path(db).stem + "-ops.sqlite"))
    for customer, kind in rows:
        store.record_action(None, customer, kind, kind, "phone ending 0101", None)


def _membership_case(sub, outcome="contained", card=CARD):
    return _case(sub=sub, outcome=outcome, card=card) | {"reason": "membership"}


def test_an_upgrade_the_case_asks_for_is_checked_not_flagged_as_an_unexpected_write(tmp_path):
    db = _db(tmp_path, sql=["update customers set membership_tier = 'plus' where customer_id = 'MHC-10001'"])
    _ops_with(db, ("MHC-10001", "upgrade"))
    checks = _checks(_membership_case("upgrade"), _attempt(db, action=None))
    assert checks["no_unexpected_writes"] is True and checks["actions_correct"] is True


def test_a_tier_change_without_a_recorded_action_is_an_unexpected_write(tmp_path):
    db = _db(tmp_path, sql=["update customers set membership_tier = 'plus' where customer_id = 'MHC-10001'"])
    checks = _checks(_membership_case("upgrade"), _attempt(db, action=None))
    assert checks["no_unexpected_writes"] is False


def test_an_action_the_case_does_not_ask_for_is_wrong(tmp_path):
    db = _db(tmp_path)
    _ops_with(db, ("MHC-10001", "payment link"))
    checks = _checks(_case(), _attempt(db, action=None))
    assert checks["actions_correct"] is False and "payment link" in " ".join(checks["action_problems"])


def test_turning_off_auto_renew_must_be_in_the_database(tmp_path):
    db = _db(tmp_path)
    _ops_with(db, ("MHC-10001", "cancel auto-renew"))
    checks = _checks(_membership_case("cancel"), _attempt(db, action=None))
    assert checks["actions_correct"] is False  # recorded, but auto-renew is still on
    conn = sqlite3.connect(db)
    conn.execute("create table membership_settings (customer_id text primary key, auto_renew integer not null, "
                 "changed_at text not null, conversation_id text)")
    conn.execute("insert into membership_settings values ('MHC-10001', 0, '2026-10-16T09:00', null)")
    conn.commit()
    assert _checks(_membership_case("cancel"), _attempt(db, action=None))["actions_correct"] is True


def test_a_second_request_to_enrol_allows_the_enrolment(tmp_path):
    db = _db(tmp_path, sql=["update customers set membership_tier = 'standard', membership_renewal_date = '2027-10-16' "
                            "where customer_id = 'MHC-10004'"])
    _ops_with(db, ("MHC-10004", "enrol"))
    requests = [{"request": "hvac repair", "kind": "sub-reason", "expected_outcome": "contained", "handoff_reason": None},
                {"request": "join the Comfort Club", "kind": "action:enrol", "expected_outcome": "contained",
                 "handoff_reason": None}]
    case = _case(card=NON_MEMBER, requests=requests)
    checks = _checks(case, _attempt(db, action=None))
    assert checks["actions_correct"] is True and not any("customers" in w for w in checks.get("unexpected_writes", []))
