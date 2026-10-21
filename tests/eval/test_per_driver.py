"""Results by call reason (the PRD's accuracy on handled drivers and escalation rate on the rest), from first attempts,
scored the same way as the summary. Fake cases and attempts only."""

from dataclasses import dataclass, field

from eval.per_driver import by_driver


@dataclass
class A:
    case_id: str
    attempt: int = 1
    all_correct: bool | None = True
    handed_off: bool = False
    clean_decline: bool = False
    stopped: str = "caller ended"
    grades: dict = field(default_factory=dict)


def case(cid, reason, outcome, weight=10):
    return {"case_id": cid, "reason": reason, "sub_reason": "x", "expected_outcome": outcome, "calls_weight": weight,
            "requests": [{"expected_outcome": outcome, "handoff_reason": None}]}


def test_each_call_reason_gets_its_handled_accuracy_and_escalation_numbers():
    cases = [case("b1", "new booking", "contained", 30), case("b2", "new booking", "contained", 10),
             case("d1", "billing", "handed_off", 20)]
    attempts = [A("b1"), A("b2", all_correct=False), A("b2", attempt=2), A("d1", handed_off=True,
                                                                           grades={"handoff_reason_correct": True})]
    rows = {r["reason"]: r for r in by_driver(attempts, cases)}
    booking, billing = rows["new booking"], rows["billing"]
    assert booking["weighted_calls"] == 40 and booking["handled_cases"] == 2
    assert booking["handled_accuracy"] == 0.75  # by calls: 30 of 40 right on the first attempt (retries do not count)
    assert billing["escalation_rate"] == 1.0 and billing["escalation_correct"] == 1.0 and billing["handled_cases"] == 0
