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


# Explicit requests to act on money or membership, not questions about them (R48). Each pattern needs a request
# form: an imperative ("send me", "upgrade me", "please cancel"), or "I want / I'd like / I need / can you / could you".
ASK = r"(?:i want(?: to)?|i'?d like(?: to)?|i would like(?: to)?|i need(?: to)?|can you|could you|would you|please|can i get|" \
      r"could i get|i'?m asking for|go ahead and|let'?s)"
MEMBERSHIP = r"(?:membership|comfort club(?! tune)|maintenance plan|the plan|my plan|auto-?renew\w*|plus)"
ACTIONS = [
    rf"\b(?:send|text|email)\b.{{0,12}}\bpayment link\b", rf"\b{ASK}\b.{{0,12}}\bpayment link\b",
    rf"\b(?:set ?up|turn on|start|put me on|sign me up for)\b.{{0,20}}\bauto-?pay\b",
    rf"\b{ASK}\b.{{0,8}}\bcancel\b.{{0,20}}\b{MEMBERSHIP}", rf"^\W*cancel\b.{{0,20}}\b{MEMBERSHIP}",
    rf"\b(?:turn off|stop)\b.{{0,15}}\bauto-?renew\w*",
    rf"\b(?:sign me up|enrol+ me|add me)\b.{{0,20}}\b{MEMBERSHIP}", rf"\b{ASK}\b.{{0,4}}\b(?:join|sign up for|enrol+ in)\b.{{0,20}}\b{MEMBERSHIP}",
    rf"\bupgrade me\b", rf"^\W*upgrade\b", rf"\b{ASK}\b.{{0,4}}\bupgrade\b(?!.{{0,20}}\b(?:furnace|system|unit|ac|thermostat)\b)",
    rf"\b{ASK}\b.{{0,12}}\brefund\b", r"\brefund me\b",
    rf"\b(?:{ASK}\b.{{0,4}}|^\W*)(?:waive|drop|remove|take off)\b.{{0,20}}\b(?:fee|charge)",
    r"\b(?:i want to|i need to|i'?d like to|let me|help me|i'?m trying to)\s+pay\b",
]


def is_action_request(text: str) -> bool:
    """An explicit request to act on money or membership: a payment link, autopay, cancelling the membership or
    auto-renew, joining, upgrading, a refund, a fee waiver or paying a bill. These are handed off as the action gap
    (R48). Questions about the same subjects ("what's your refund policy?") are not requests."""
    return any(re.search(pattern, text, re.I) for pattern in ACTIONS)
