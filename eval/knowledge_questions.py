"""The knowledge test questions for measuring retrieval on its own (R29, R30, R31).

Three kinds: answerable (from the test cases plus a hand-written set), stale traps (where an
excluded old document would give a different answer), and unanswerable (the documents do not
cover them; the agent should hand off). Each answerable or stale-trap question carries the exact
document lines that answer it. Reference answers come from the current documents only.

Run: python -m eval.knowledge_questions   (writes data/knowledge_questions.jsonl)
"""

import json
import random
from pathlib import Path

from eval.build_cases import _spans

ROOT = Path(__file__).resolve().parent.parent
FAQ, CATALOG, MEMBERSHIP = "faq__customer_faq.md", "services__service_catalog.md", "membership__comfort_club_overview.md"
WARRANTY, FEES = "warranty__warranty_policy.md", "pricing__2026_fee_schedule.md"

ANSWERABLE = [
    ("Are you open on Thanksgiving?", "Closed on Thanksgiving (November 26 and 27); the emergency line is open, and holiday "
     "emergency dispatch is $199.", [("policies__holiday_hours_2026.md", "Holidays"), ("policies__holiday_hours_2026.md", "Holiday dispatch fee")]),
    ("Do you service Manor?", "Yes. Manor (78653) was added to the service area in April 2026.",
     [("policies__service_area.md", "Service Area")]),
    ("Do you come out to San Marcos?", "No. San Marcos is not in the service area.",
     [("policies__service_area.md", "Service Area")]),
    ("How much is a tune-up?", "A seasonal tune-up is $129 for non-members and included for Comfort Club members.",
     [(CATALOG, "Maintenance tune-up")]),
    ("Do you offer financing?", "Yes, on repairs over $1,000 and all system replacements, through a financing partner; "
     "approval takes about 5 minutes.", [(FAQ, "Payment")]),
    ("Can I pay by card over the phone?", "Card numbers are never taken over the phone; Meridian sends a secure payment "
     "link by text or email, valid for 24 hours.", [(FAQ, "Payment")]),
    ("How much does it cost to clear a clogged drain?", "Drain clearing typically costs $149 to $290 depending on access; "
     "the technician confirms the final price on site.", [(CATALOG, "Plumbing (residential)")]),
    ("What appointment windows do you have?", "8am to 12pm, 12pm to 4pm and 1pm to 5pm, plus 4pm to 7pm on Tuesdays and "
     "Thursdays.", [(FAQ, "Scheduling")]),
    ("Do you do duct cleaning?", "Meridian does not do duct cleaning itself; it partners with a third party and can give "
     "a referral.", [(CATALOG, "Not offered")]),
    ("Is there a fee to cancel my appointment?", "Cancelling or rescheduling more than 24 hours before the window is free; "
     "inside 24 hours there is a $49 late-cancellation fee.", [(FAQ, "Scheduling")]),
]

STALE_TRAPS = [
    ("Is the diagnostic fee still $79?", "No, the diagnostic visit is $89, credited toward a repair approved on the same "
     "visit, and waived for Comfort Club members.", [(FAQ, "Fees"), (FEES, "Fees by membership level")]),
    ("I heard cancellations need 48 hours notice, is that right?", "No. Cancelling more than 24 hours before the window is "
     "free; inside 24 hours there is a $49 fee.", [(FAQ, "Scheduling")]),
    ("Isn't the repair warranty only 90 days?", "No. Meridian repairs carry a 1-year labor warranty on the part repaired.",
     [(WARRANTY, "Repair warranty (Meridian labor warranty)")]),
    ("Is the Comfort Club still $149 a year?", "No. It is $189 a year per system, or $16.99 a month with a 12-month minimum.",
     [(MEMBERSHIP, "Plans")]),
    ("Is the after-hours emergency fee $129?", "No. After-hours emergency dispatch is $149, waived for Comfort Club members.",
     [(FAQ, "Hours & Contact"), (FEES, "Fees by membership level")]),
    ("Are you only open until 6 on weekdays?", "No. Phone support is Monday to Friday 7am to 7pm and Saturday 8am to 4pm.",
     [(FAQ, "Hours & Contact")]),
    ("Does my membership move with me to my new house?", "No. A membership stays with the service address and transfers to "
     "the next homeowner there; it does not move to a new address.", [(MEMBERSHIP, "Transfer")]),
    ("Can I pay the technician with a check?", "No. Technicians do not accept checks or cash; payment is by card or ACH "
     "through a secure link.", [(FAQ, "Payment")]),
]

UNANSWERABLE = [
    "Can I set up autopay for my membership?",
    "How much would you charge to replace four rooftop units at my strip mall?",
    "What's the exact price of a new Trane XR16 heat pump?",
    "Do you give a discount for veterans?",
    "What is my technician's license number?",
]


def build_questions(seed: int = 20261016) -> list[dict]:
    split = json.loads((ROOT / "data" / "split.json").read_text())
    held = set(split["held_out"])
    questions = []
    for path in sorted((ROOT / "data" / "testset").glob("*.json")):
        case = json.loads(path.read_text())
        if case["needs_documents"]:
            asked = next(l for l in case["caller_script"] if not any(x in l.lower() for x in ("cut out", "driving", "hear me")))
            questions.append({"qid": f"case-{case['case_id']}", "case_id": case["case_id"], "question": asked,
                              "kind": "answerable", "set": "held_out" if case["case_id"] in held else "working",
                              "reference_answer": case["reference_answer"], "evidence_spans": case["evidence_spans"]})
    rng = random.Random(seed)
    groups = {"answerable": [(q, a, s) for q, a, s in ANSWERABLE], "stale_trap": [(q, a, s) for q, a, s in STALE_TRAPS],
              "unanswerable": [(q, None, []) for q in UNANSWERABLE]}
    for kind, items in groups.items():
        # About 30 percent of each kind is held out, and at least one, so every measure has held-out questions.
        order = list(range(len(items)))
        rng.shuffle(order)
        held_count = max(1, round(0.3 * len(items)))
        for position, n in enumerate(order):
            question, answer, sections = items[n]
            questions.append({"qid": f"{kind}-{n}", "case_id": None, "question": question, "kind": kind,
                              "set": "held_out" if position < held_count else "working",
                              "reference_answer": answer, "evidence_spans": _spans(sections)})
    return questions


def main() -> None:
    out = ROOT / "data" / "knowledge_questions.jsonl"
    questions = build_questions()
    out.write_text("".join(json.dumps(q) + "\n" for q in questions))
    print(f"{len(questions)} questions -> {out}")


if __name__ == "__main__":
    main()
