"""Read-only account lookups once a caller is identified (R46), and recognising money or membership actions (R48)."""

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.accounts.fees import MEMBERSHIP_PRICE_CENTS


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    issued_date: str
    due_date: str
    amount_cents: int
    balance_cents: int
    lines: list[tuple[str, int]]


@dataclass(frozen=True)
class Membership:
    tier: str
    renewal_date: str | None
    renewal_price_cents: int | None


@dataclass(frozen=True)
class System:
    brand: str | None
    install_date: str | None


def open_invoices(db: sqlite3.Connection, customer_id: str) -> list[Invoice]:
    rows = db.execute("select invoice_id, issued_date, due_date, amount_cents, balance_cents, line_items from invoices "
                      "where customer_id = ? and balance_cents > 0 order by due_date", (customer_id,)).fetchall()
    return [Invoice(*row[:5], [(line["desc"], line["cents"]) for line in json.loads(row[5])]) for row in rows]


def membership(db: sqlite3.Connection, customer_id: str) -> Membership:
    tier, renewal = db.execute("select membership_tier, membership_renewal_date from customers where customer_id = ?",
                               (customer_id,)).fetchone()
    # A membership renews at the current published price, not the price the member first paid.
    return Membership(tier, renewal, MEMBERSHIP_PRICE_CENTS.get(tier))


def system(db: sqlite3.Connection, customer_id: str) -> System:
    return System(*db.execute("select system_brand, system_install_date from customers where customer_id = ?",
                              (customer_id,)).fetchone())


# The code backstop to the router (R48, D43): only requests that are never questions. Everything else about joining,
# upgrading, refunds or payments is left to the router, which reads the whole message.
NOT_A_QUESTION = r"^(?!.*\b(?:how|what|why|when|does|do i|is there|is it)\b)"
UNMISTAKABLE = [
    r"\b(?:send|text|email|get) (?:me )?(?:a )?(?:payment )?link to pay\b", r"\b(?:send|text|email)\b.{0,12}\bpayment link\b",
    r"\b(?:can i get|could i get|i need|i want|i'd like)\b.{0,6}\bpayment link\b",
    NOT_A_QUESTION + r".*\b(?:set up|setup|put me on|sign me up for|turn on|start)\b.{0,12}\bauto-?pay\b",
    r"\b(?:take me off|cancel|stop|turn off)\b.{0,8}\bauto-?pay\b",
    NOT_A_QUESTION + r".*\b(?:cancel|end|stop)\b (?:my |the )?(?:comfort club |plus )?membership\b(?! (?:visit|tune))",
    NOT_A_QUESTION + r".*\b(?:cancel|turn off|stop)\b (?:my |the )?auto[- ]?renew\w*",
    r"\brefund me\b", r"^\W*(?:i want|i'd like|i need|i'm asking for|i am asking for)\b.{0,6}\b(?:a |my |full )*refund\b",
    r"\b(?:please )?waive (?:the|my|that) (?:[\w-]+ )?fee\b(?!.*\?)",
    r"\b(?:i want to|i need to|i'd like to|i would like to)\s+pay (?:my |the |this )?(?:bill|invoice|balance)\b",
    r"\bi need to pay invoice\b", r"^\W*pay my (?:bill|invoice|balance)\b",
    r"\bsign me up for (?:the |a )?(?:comfort club|membership|maintenance plan|plus)\b",
]


def is_action_request(text: str) -> bool:
    """An unmistakable request to act on money or membership, caught in code whatever the router said: a payment
    link, autopay, cancelling the membership or auto-renew, a refund, a fee waiver, paying a bill, or joining the
    plan. These are handed off as the action gap (R48)."""
    said = text.replace("’", "'").replace("‘", "'").lower()
    return any(re.search(pattern, said) for pattern in UNMISTAKABLE)
