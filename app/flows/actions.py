"""Money and membership actions the agent takes itself (money and membership actions decision (D54)).

The company's escalation policy lets its agents send payment links and handle Comfort Club enrolment, upgrades and
cancelling auto-renew; autopay follows a policy the author supplied (data/kb_added/policies/autopay.md). Each action
needs the caller identified, a read-back and a plain yes. Links are simulated: recorded in the operations database as
sent to the phone on file, never with a card or bank number, which the caller enters on the secure page. Membership
changes are written to the live scheduling database (the seed is never written); turning off auto-renew lives in a
table of the live copy that the nightly reset clears. Refunds, disputes and fee waivers are not actions here: they
still go to a person.
"""

import re
import sqlite3
from datetime import date, timedelta

from app.accounts.lookups import membership, open_invoices
from app.flows.protocol import FlowResult

NOT_HERE = re.compile(r"\b(refund\w*|waive\w*|waiver|dispute\w*|chargeback|credit (?:me|back)|reimburse\w*)\b", re.I)
AUTOPAY_OFF = re.compile(r"\b(cancel|stop|turn off|take me off|end|remove)\b.{0,20}\bauto-?pay\b|\bauto-?pay\b.{0,15}\boff\b", re.I)
AUTOPAY = re.compile(r"\bauto-?pay\b|\bautomatic (?:payments?|billing)\b|\b(?:card|payment method)\b.{0,40}\b(?:expired|"
                     r"replace|update|change|new)\b|\b(?:expired|new) card\b", re.I)
CANCEL = re.compile(r"\b(cancel\w*|turn off|stop|end|don'?t want)\b.{0,40}\b(auto-?renew\w*|renewal|membership|comfort club|"
                    r"plan|plus)\b|\b(?:won'?t|not|doesn'?t|don'?t) (?:auto-?)?renew\b|\bauto-?renew\w*\b.{0,10}\boff\b", re.I)
UPGRADE = re.compile(r"\bupgrad\w*\b|\b(?:switch|move|change|go)\b.{0,15}\b(?:to|up to) (?:the )?plus\b", re.I)
ENROL = re.compile(r"\b(join|sign (?:me |us )?up|enrol+\w*|become a member|add (?:it|the membership|the plan|me))\b", re.I)
PAYMENT = re.compile(r"\bpay(?:ing|ment)?\b.{0,30}\b(?:bill|invoice|balance)\b|\bpayment link\b|\blink to pay\b|"
                     r"\b(?:bill|invoice|balance)\b.{0,20}\bpay\b", re.I)

LINK_HOURS = 24
STANDARD, PLUS, STANDARD_MONTHLY, PLUS_DIFFERENCE = "$189", "$269", "$16.99", "$80"
NEVER_CARDS = "the caller enters card or bank details on that secure page, never in this chat"


def kind_of(text: str) -> str | None:
    """Which action the message asks for, or None for one that stays with a person (refunds, waivers, disputes)."""
    said = text.replace("’", "'")
    if NOT_HERE.search(said):
        return None
    if AUTOPAY_OFF.search(said):
        return "autopay off"
    if AUTOPAY.search(said):
        return "autopay link"
    if UPGRADE.search(said):
        return "upgrade"
    if CANCEL.search(said):
        return "cancel auto-renew"
    if ENROL.search(said):
        return "enrol"
    if PAYMENT.search(said):
        return "payment link"
    return None


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _phone(db: sqlite3.Connection, customer_id: str) -> str:
    phone = db.execute("select phone from customers where customer_id = ?", (customer_id,)).fetchone()[0] or ""
    return f"the phone number on the account ending in {re.sub(r'\\D', '', phone)[-4:]}"


def _long(day: str) -> str:
    when = date.fromisoformat(day)
    return f"{when.day} {when:%B %Y}"


def offer(db: sqlite3.Connection, customer, kind: str, state, now, text: str = "") -> FlowResult:
    """The read-back for the action, or a plain answer when there is nothing to do. Sets state.action to wait for a yes."""
    m = membership(db, customer.customer_id)
    to = _phone(db, customer.customer_id)
    tier = "Plus" if m.tier == "plus" else "Standard"
    readback, plan = None, None
    if kind == "payment link":
        invoices = open_invoices(db, customer.customer_id)
        if not invoices:
            return FlowResult(["There are no open invoices on this account, so there is nothing to pay right now."],
                              "account answer")
        total = sum(i.balance_cents for i in invoices)
        which = ", ".join(f"{i.invoice_id} (balance {_money(i.balance_cents)})" for i in invoices)
        readback = (f"Read back: a secure payment link for {which}, {_money(total)} in all, by text to {to}; it is valid "
                    f"for {LINK_HOURS} hours, and {NEVER_CARDS}.")
    elif kind == "autopay link":
        readback = (f"Read back: a secure autopay link by text to {to}, valid for {LINK_HOURS} hours. On that page the "
                    "caller enters card or bank details and agrees to the autopay terms; autopay starts only once the "
                    "form is completed, and a confirmation and a copy of the terms are emailed. Autopay charges invoices "
                    "on their due date and Comfort Club fees on the billing date, with a reminder 3 days before each "
                    "charge, and it can be turned off at any time.")
    elif kind == "autopay off":
        readback = ("Read back: turn off autopay on this account; it stops for charges at least one business day away, "
                    "and a confirmation is emailed.")
    elif kind == "enrol":
        if m.tier != "none":
            return FlowResult([f"This account already has Comfort Club {tier}, renewing {_long(m.renewal_date)}."],
                              "account answer")
        plan = "plus" if re.search(r"\bplus\b", text, re.I) else "standard"
        renews = (now.date() + timedelta(days=365)).isoformat()
        price = f"{PLUS} a year per system" if plan == "plus" else \
            f"{STANDARD} a year per system (or {STANDARD_MONTHLY} a month with a 12-month minimum)"
        readback = (f"Read back: enrol this account in Comfort Club {plan.title()} at {price}, starting today and renewing "
                    f"on {_long(renews)}; a secure payment link for the first charge goes by text to {to}, valid for "
                    f"{LINK_HOURS} hours, and {NEVER_CARDS}.")
    elif kind == "upgrade":
        if m.tier == "plus":
            return FlowResult([f"This account already has Comfort Club Plus, renewing {_long(m.renewal_date)}."],
                              "account answer")
        if m.tier == "none":
            return offer(db, customer, "enrol", state, now, text + " plus")
        readback = (f"Read back: upgrade this account from Comfort Club Standard to Plus today. The {PLUS_DIFFERENCE} "
                    "annual difference is prorated for the months left in the current term, and the renewal date stays "
                    f"{_long(m.renewal_date)}; a secure payment link for the prorated amount goes by text to {to}, "
                    f"valid for {LINK_HOURS} hours, and {NEVER_CARDS}.")
    elif kind == "cancel auto-renew":
        if m.tier == "none":
            return FlowResult(["There is no Comfort Club membership on this account."], "account answer")
        readback = (f"Read back: turn off auto-renew on Comfort Club {tier}; the membership stays active until "
                    f"{_long(m.renewal_date)} and then ends, and a confirmation is emailed. Refund terms: annual plans are "
                    "non-refundable once a tune-up has been performed in the current term; if none has been, a prorated "
                    "refund is available within the first 60 days, and a refund request goes to the billing team.")
    else:
        return FlowResult([], "handoff", handoff_reason="action gap")
    state.action = {"kind": kind, "step": "readback", "plan": plan}
    return FlowResult([readback + " Ask the caller for a clear yes before going ahead."], "read-back")


def auto_renew_off(db: sqlite3.Connection, customer_id: str) -> bool:
    """Whether auto-renew was turned off in this live copy (the table exists only once one was)."""
    if not db.execute("select 1 from sqlite_master where name = 'membership_settings'").fetchone():
        return False
    row = db.execute("select auto_renew from membership_settings where customer_id = ?", (customer_id,)).fetchone()
    return bool(row) and row[0] == 0


def perform(db_path, store, customer, state, conversation_id: str, now) -> FlowResult:
    """Do the action read back, after a plain yes. A membership change and its action record commit together: the
    change is written in a transaction that commits only once the record is saved (review finding D1)."""
    kind, plan = state.action["kind"], state.action.get("plan")
    state.action = {}
    db = sqlite3.connect(db_path, isolation_level=None)
    try:
        m = membership(db, customer.customer_id)
        to = _phone(db, customer.customer_id)
        sent, hours = to.removeprefix("the "), LINK_HOURS
        db.execute("begin immediate")
        try:
            if kind == "enrol":
                renews = (now.date() + timedelta(days=365)).isoformat()
                db.execute("update customers set membership_tier = ?, membership_renewal_date = ? where customer_id = ?",
                           (plan, renews, customer.customer_id))
                facts = [f"Done: the account is enrolled in Comfort Club {plan.title()}, renewing on {_long(renews)}.",
                         f"Sent: a secure payment link for the first charge by text to {to}, valid for {LINK_HOURS} hours."]
                detail = f"enrolled in {plan}, renews {renews}; first-charge payment link"
            elif kind == "upgrade":
                db.execute("update customers set membership_tier = 'plus' where customer_id = ?", (customer.customer_id,))
                facts = [f"Done: the account is upgraded to Comfort Club Plus; the renewal date stays "
                         f"{_long(m.renewal_date)}.",
                         f"Sent: a secure payment link for the prorated difference by text to {to}, valid for "
                         f"{LINK_HOURS} hours."]
                detail = "upgraded standard to plus; prorated-difference payment link"
            elif kind == "cancel auto-renew":
                db.execute("create table if not exists membership_settings (customer_id text primary key, "
                           "auto_renew integer not null, changed_at text not null, conversation_id text)")
                db.execute("insert or replace into membership_settings values (?, 0, ?, ?)",
                           (customer.customer_id, now.isoformat(timespec="seconds"), conversation_id))
                facts = [f"Done: auto-renew is off; the Comfort Club membership stays active until "
                         f"{_long(m.renewal_date)} and then ends. A confirmation goes to the email on the account."]
                detail, sent, hours = f"auto-renew off; active until {m.renewal_date}", "email on the account", None
            elif kind == "autopay off":
                facts = ["Done: autopay is off for charges at least one business day away. A confirmation goes to the "
                         "email on the account."]
                detail, sent, hours = "autopay off", "email on the account", None
            else:
                what = "payment link" if kind == "payment link" else "autopay link"
                facts = [f"Sent: a secure {what} by text to {to}, valid for {LINK_HOURS} hours; {NEVER_CARDS}."]
                detail = what
            store.record_action(conversation_id, customer.customer_id, kind, detail, sent, hours)
            db.execute("commit")
        except BaseException:
            db.execute("rollback")
            raise
    finally:
        db.close()
    state.tried.append(f"{kind} for {customer.customer_id}")
    return FlowResult(facts, "confirmation", db_actions=[f"{kind} {customer.customer_id}"])
