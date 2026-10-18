"""Find the caller from what they said: a name together with an account number, phone or street address (R45)."""

import re

from app.accounts import normalise
from app.accounts.identity import Customer, identify
from app.ops.masking import PATTERNS

ACCOUNT = re.compile(r"\bmhc[\s-]*\d{5}\b", re.I)
PHONE = PATTERNS[1][0]
STREET = PATTERNS[2][0]
ASK = "Ask for the caller's full name and one of: their account number, service address or phone number."


def has_identifier(text: str) -> bool:
    return bool(ACCOUNT.search(text) or PHONE.search(text) or STREET.search(text))


def find_customer(db, text: str) -> Customer | None:
    account, phone, street = (m.group(0) if (m := p.search(text)) else None for p in (ACCOUNT, PHONE, STREET))
    if not (account or phone or street):
        return None
    rest = text
    for found in (account, phone, street):
        if found:
            rest = rest.replace(found, " ")
    words = normalise.words(rest)
    for size in (3, 2):
        for start in range(len(words) - size + 1):
            customer = identify(db, " ".join(words[start:start + size]), account, street, phone)
            if customer:
                return customer
    return None
