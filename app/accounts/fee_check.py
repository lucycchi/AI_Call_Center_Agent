"""Fixed fees on an invoice that differ from the current schedule; these open a silent billing-review ticket (R47)."""

from app.accounts.fees import FIXED_FEES
from app.accounts.lookups import Invoice


def fee_mismatches(invoice: Invoice) -> list[str]:
    found = []
    for desc, cents in invoice.lines:
        fee = next((key for key in FIXED_FEES if key in desc.lower()), None)
        if fee and cents != FIXED_FEES[fee]:
            found.append(f"{desc.lower()} {cents / 100:.2f} vs schedule {FIXED_FEES[fee] / 100:.2f}")
    return found
