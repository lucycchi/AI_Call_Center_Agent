"""The booking read-back check: only the read-back turn counts, and it accepts the usual spoken forms of a slot."""

import json
from pathlib import Path

import pytest

from eval.harness import Attempt
from tests.eval.test_conversation_grading import _book, _case, _checks, _db

ROOT = Path(__file__).resolve().parents[2]
OFFER = "I have two HVAC repair openings on Monday, October 19: 8:00 AM to 12:00 PM, or 12:00 PM to 4:00 PM."


def _offered_then_read_back(db, read_back: str, booked: str = "Booked: your HVAC repair visit.") -> Attempt:
    """Offer both windows, the caller picks one, the agent reads one back, the caller says yes, the agent books."""
    conversation = [{"role": "caller", "text": "I need a repair"},
                    {"role": "agent", "text": OFFER},
                    {"role": "caller", "text": "The afternoon one, please."},
                    {"role": "agent", "text": f"To read it back: an HVAC repair on {read_back}. Is that correct?"},
                    {"role": "caller", "text": "yes"},
                    {"role": "agent", "text": booked}]
    return Attempt("c1", db_path=str(db), conversation=conversation,
                   done_events=[{"db_actions": []}, {"db_actions": []}, {"db_actions": ["booked appointment 160"]}])


def test_a_booking_that_differs_from_the_read_back_fails_even_when_the_offer_named_it(tmp_path):
    # slot 56 is Monday, October 19, 8am to 12pm; the offer named it, but the read-back said 12 to 4
    wrong = _offered_then_read_back(_db(tmp_path / "a", sql=_book(56)), "Monday, October 19, 12:00 PM to 4:00 PM")
    assert _checks(_case(), wrong)["booking_correct"] is False
    right = _offered_then_read_back(_db(tmp_path / "b", sql=_book(56)), "Monday, October 19, 8:00 AM to 12:00 PM")
    assert _checks(_case(), right)["booking_correct"] is True


def test_the_smoke_run_pattern_where_the_booking_differed_from_its_read_back_fails(tmp_path):
    """Case Tb456e16e in smoke-task18b: the read-back said 12:00 PM to 4:00 PM, then 8am to 12pm was booked."""
    conversation = [
        {"role": "caller", "text": "Hi, I'd like to book a repair, my furnace won't kick on."},
        {"role": "agent", "text": "I'm sorry your furnace won't start."},
        {"role": "caller", "text": "My account number is MHC-10001."},
        {"role": "agent", "text": "I have three HVAC repair openings on Monday, October 19: 8:00 AM to 12:00 PM, "
                                  "12:00 PM to 4:00 PM, or 1:00 PM to 5:00 PM."},
        {"role": "caller", "text": "Monday 12:00 PM to 4:00 PM is fine, thanks."},
        {"role": "agent", "text": "To read it back: an HVAC repair on Monday, October 19, in the 12:00 PM to 4:00 PM window."},
        {"role": "agent", "text": "Is that correct?"},
        {"role": "caller", "text": "Yes, that's correct."},
        {"role": "agent", "text": "Booked: your HVAC repair visit on Monday, October 19, 8am to 12pm, with Marta Kowalski."}]
    attempt = Attempt("c1", db_path=str(_db(tmp_path, sql=_book(56))), conversation=conversation,
                      done_events=[{"db_actions": []}] * 3 + [{"db_actions": ["booked appointment 160"]}])
    checks = _checks(_case(), attempt)
    assert checks["booking_correct"] is False
    assert any("read back" in p for p in checks["booking_problems"])


SMOKE = ROOT / "data" / "results" / "smoke-task18b" / "attempts.jsonl"


@pytest.mark.skipif(not SMOKE.exists(), reason="the smoke-task18b results are not present")
def test_the_real_smoke_run_conversation_fails_the_read_back_check():
    from eval.grade_conversations import _read_back_before
    [saved] = [json.loads(line) for line in SMOKE.open() if json.loads(line)["case_id"] == "Tb456e16e"]
    attempt = Attempt("Tb456e16e", conversation=saved["conversation"], done_events=saved["done_events"])
    # appointment 160 went to the 8-to-12 window on October 19, after a read-back of 12 to 4
    assert _read_back_before(attempt, "booked appointment 160", "2026-10-19", "08:00-12:00") is False
    # appointment 161 went to 12 to 4, after a read-back of 12 to 4
    assert _read_back_before(attempt, "booked appointment 161", "2026-10-19", "12:00-16:00") is True


@pytest.mark.parametrize("text, slot_date, window", [
    ("Tuesday the 3rd, eight to noon", "2026-11-03", "08:00-12:00"),
    ("Tuesday, November 3, in the morning window", "2026-11-03", "08:00-12:00"),
    ("11/3, 8am-12pm", "2026-11-03", "08:00-12:00"),
    ("the 3rd, from 8 to 12", "2026-11-03", "08:00-12:00"),
    ("the 19th, the afternoon window", "2026-10-19", "12:00-16:00"),
    ("October 19, noon to four", "2026-10-19", "12:00-16:00"),
    ("10/19 from 8 to 12", "2026-10-19", "08:00-12:00"),
    ("Tuesday the 27th, 1 to 5", "2026-10-27", "13:00-17:00"),
    ("10/27, the afternoon window", "2026-10-27", "13:00-17:00"),
    ("Friday the 30th, the evening window", "2026-10-30", "16:00-19:00"),
])
def test_the_read_back_accepts_the_usual_spoken_forms(text, slot_date, window):
    from eval.grade_conversations import names_slot
    assert names_slot(text, slot_date, window), text


@pytest.mark.parametrize("text, slot_date, window", [
    ("Tuesday the 4th, eight to noon", "2026-11-03", "08:00-12:00"),  # the wrong day
    ("Tuesday, eight to noon", "2026-11-03", "08:00-12:00"),  # a weekday alone is ambiguous more than a week out
    ("November 3, the afternoon window", "2026-11-03", "08:00-12:00"),  # the wrong window
    ("Good morning! November 3, 12 to 4", "2026-11-03", "08:00-12:00"),  # a greeting is not a window
    ("10/3, 8 to 12", "2026-11-03", "08:00-12:00"),  # the wrong month
    ("the morning window", "2026-11-03", "08:00-12:00"),  # no date at all
])
def test_the_read_back_still_rejects_the_wrong_slot(text, slot_date, window):
    from eval.grade_conversations import names_slot
    assert not names_slot(text, slot_date, window), text


def _no_booking(db, conversation) -> Attempt:
    return Attempt("c1", db_path=str(db), conversation=conversation, done_events=[{"db_actions": []}] * 3)


def test_a_booking_the_caller_never_confirmed_is_a_miss_not_a_fault(tmp_path):
    # Quick run T9e29febc: the caller said "Book it" but never chose one of the offered slots (D49).
    conversation = [{"role": "caller", "text": "I need a repair"}, {"role": "agent", "text": OFFER + " Which one suits you?"},
                    {"role": "caller", "text": "Book it."}, {"role": "agent", "text": "Which opening would you like?"},
                    {"role": "caller", "text": "No, that's it. Thanks."}]
    checks = _checks(_case(), _no_booking(_db(tmp_path), conversation))
    assert checks["booking_correct"] is False and checks["booking_fault"] is False


def test_a_confirmed_read_back_with_nothing_booked_is_a_fault(tmp_path):
    conversation = [{"role": "caller", "text": "I need a repair"}, {"role": "agent", "text": OFFER},
                    {"role": "caller", "text": "The morning one."},
                    {"role": "agent", "text": "Just to confirm: an HVAC repair on Monday, October 19, 8:00 AM to 12:00 PM. "
                                              "Can you give me a clear yes?"},
                    {"role": "caller", "text": "Yes, please book it."}, {"role": "agent", "text": "Done."}]
    checks = _checks(_case(), _no_booking(_db(tmp_path), conversation))
    assert checks["booking_correct"] is False and checks["booking_fault"] is True


def test_a_wrong_booking_is_a_fault(tmp_path):
    wrong = _offered_then_read_back(_db(tmp_path, sql=_book(56)), "Monday, October 19, 12:00 PM to 4:00 PM")
    assert _checks(_case(), wrong)["booking_fault"] is True


def test_the_quick_run_fails_hard_only_on_booking_faults():
    from eval.harness import Attempt
    from eval.quick_run import judge
    case = {"case_id": "c1", "calls_weight": 1, "reason": "new booking", "sub_reason": "hvac repair",
            "expected_outcome": "contained", "requests": []}
    missed = Attempt("c1", stopped="caller ended", grades={"booking_correct": False, "booking_fault": False})
    faulty = Attempt("c1", stopped="caller ended", grades={"booking_correct": False, "booking_fault": True})
    assert not any("booking check failed" in r for r in judge([missed], {"c1": case}).reasons)
    assert any("booking check failed" in r for r in judge([faulty], {"c1": case}).reasons)
