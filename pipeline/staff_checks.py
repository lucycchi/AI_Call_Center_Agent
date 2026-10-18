"""The seven staff policy-error patterns found in the data review, checked against current documents."""

import re
from collections import Counter

from pipeline.transcripts import Call

# A confirmed booking, not just an offered slot.
BOOKING = re.compile(r"you're booked|book a warranty diagnostic|book that as a warranty", re.I)


def errors_in(call: Call) -> list[str]:
    caller = " ".join(call.customer_lines)
    staff = " ".join(call.agent_lines)
    found = []
    if re.search(r"waitlist", staff, re.I):
        found.append("offered a waitlist")
    if re.search(r"burning", caller, re.I) and re.search(r"you're booked", staff, re.I):
        found.append("booked a burning smell as a normal visit")
    if re.search(r"call you back today", staff, re.I):
        found.append("promised a manager callback today")
    if re.search(r"tomorrow", caller, re.I) and re.search(r"move", caller, re.I) and re.search(r"\bmoved\b", staff, re.I) \
            and "$49" not in staff:
        found.append("moved a next-day appointment without the $49 fee")
    if re.search(r"the diagnostic fee plus the", staff, re.I):
        found.append("explained an invoice as the diagnostic fee plus the repair")
    if re.search(r"let's schedule it|can you book|book it", caller, re.I) and not BOOKING.search(staff):
        found.append("dropped a booking the caller asked for")
    if re.search(r"refund", staff, re.I) and re.search(r"two business days", staff, re.I):
        found.append("promised a refund callback in two business days")
    return found


def staff_policy_errors(calls: list[Call]) -> Counter:
    return Counter(error for call in calls for error in errors_in(call))
