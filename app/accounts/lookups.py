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


ACTIONS = [r"\bpayment link\b", r"\b(can i|could i|i want to|i need to|i'd like to|let me|help me)\b.{0,12}\bpay\b", r"\bauto-?pay\b",
           r"\bcancel\b.*\b(auto-?renew\w*|membership|comfort club|plan|renewal)\b", r"\bupgrade\b",
           r"\b(sign me up|enrol+|join)\b", r"\brefund\b", r"\bwaive\b", r"\bdowngrade\b"]


def is_action_request(text: str) -> bool:
    """Taking an action on money or membership: payment links, autopay, cancelling auto-renew or the membership,
    upgrades, enrolment, refunds, fee waivers. These are handed off as the action gap (R48)."""
    return any(re.search(pattern, text, re.I) for pattern in ACTIONS)
