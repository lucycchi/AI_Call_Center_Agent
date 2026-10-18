"""Current published prices, read from the converted fee schedule and holiday notice (the documents stay the source)."""

import re
from pathlib import Path

KB_TEXT = Path(__file__).resolve().parents[2] / "data" / "kb_text"


def _schedule() -> dict[str, int]:
    prices = {}
    for line in (KB_TEXT / "pricing__2026_fee_schedule.md").read_text().splitlines():
        match = re.match(r"- (.+?), (Non-member|Comfort Club Plus|Comfort Club): \$([\d.]+)$", line.strip())
        if match:
            prices[f"{match.group(1)}|{match.group(2)}"] = round(float(match.group(3)) * 100)
    return prices


SCHEDULE = _schedule()
HOLIDAY_DISPATCH_CENTS = round(float(re.search(r"holidays: \$([\d.]+)", (KB_TEXT / "policies__holiday_hours_2026.md")
                                               .read_text()).group(1)) * 100)
# Fixed fees an invoice line can be checked against: what the line says, and the current non-member price.
FIXED_FEES = {"diagnostic": SCHEDULE["Diagnostic visit|Non-member"],
              "after-hours": SCHEDULE["After-hours emergency dispatch|Non-member"],
              "holiday": HOLIDAY_DISPATCH_CENTS,
              "late cancellation": SCHEDULE["Late cancellation (<24h)|Non-member"]}
MEMBERSHIP_PRICE_CENTS = {"standard": SCHEDULE["Membership (annual, 1 system)|Comfort Club"],
                          "plus": SCHEDULE["Membership (annual, 1 system)|Comfort Club Plus"]}
