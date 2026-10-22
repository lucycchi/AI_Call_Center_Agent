"""Account questions for an identified caller, from read-only lookups (R46, R47)."""

import logging
import re
from datetime import date

from app.accounts import normalise
from app.accounts.fee_check import fee_mismatches
from app.accounts.lookups import membership, open_invoices, system, system_age
from app.config import SETTINGS
from app.flows.actions import auto_renew_off
from app.flows.identify import STREET
from app.flows.protocol import FlowResult


log = logging.getLogger("meridian.account")


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# The service address on file (author's choice, quick run 20261021-031409: T70425efa, T9bb3779a, T9f56ade3). The
# lookups (R46) do not read the address aloud: the agent says, in fixed text, that visits go to the address on the
# account and that it never reads street addresses aloud. A changed address is handed to a team member ("address
# change"; it is not a money or membership action, so not the action gap of R48).
ADDRESS_ASK = re.compile(
    r"\b(?:confirm|check|verify|note|double-check)\b[^.?!]{0,40}\baddress\b|"
    r"\baddress\b[^.?!]{0,12}\b(?:on file|you have|on (?:the|my|your) account|on record|in the system|saved)\b|"
    r"\b(?:right|correct) address\b|\b(?:which|what) address\b|"
    r"\b(?:is|was) (?:the|this|that|my|our) (?:visit|appointment|tech\w*|booking)\b[^.?!]{0,15}\b(?:at|going to) "
    r"(?:the same|the address|my|our|\d{3,})",
    re.I)
ADDRESS_CHANGED = re.compile(
    r"\b(?:we|i) (?:just |recently )?moved\b(?! in\b)|\b(?:we|i) (?:just|recently) moved in\b|\bwe'?ve moved\b|"
    r"\bnew (?:service |home )?address\b|\baddress (?:has |is |was )?changed\b|"
    r"\b(?:change|changed|update|updated) (?:my|our|the) (?:service |home )?address\b|\bdifferent address\b", re.I)
# Statements that only name the address ("the service address is ...", "same address as before"): an address message
# once the caller is identified, but at the identity prompt they are how the caller identifies themselves.
ADDRESS_STATED = re.compile(r"\bsame address\b|\b(?:my|our|the) (?:service |home )?address is\b|\bservice address\b", re.I)
VISIT_ADDRESS = "Your visit is set for the service address on your account."
ACCOUNT_ADDRESS = "Visits for this account are set for the service address on your account."
PRIVATE = "For privacy, I don't read street addresses aloud."
CAN_UPDATE = "If the address has changed, a team member can update it."
WILL_UPDATE = "Since the address has changed, a team member needs to update it on your account."


def about_address(text: str, identified_before: bool) -> bool:
    """The caller asks to confirm, check or note their address, or says it has changed (identified earlier in the
    conversation, a plain statement of the address counts too)."""
    said = text.replace("’", "'")
    return bool(ADDRESS_ASK.search(said) or ADDRESS_CHANGED.search(said)
                or ADDRESS_STATED.search(said) and (identified_before or "?" in said))


def address_changed(text: str, customer) -> bool:
    """The caller says the address changed, or gives a street that is not the one on file (compared, never said)."""
    given = STREET.search(text)
    return bool(ADDRESS_CHANGED.search(text.replace("’", "'"))
                or given and normalise.street(given.group(0)) != normalise.street(customer.service_address))


def address_answer(customer, text: str, visit: bool) -> FlowResult:
    """Fixed text written in code, so no street address is ever read out; a changed address is handed off."""
    facts = [VISIT_ADDRESS if visit else ACCOUNT_ADDRESS, PRIVATE]
    if address_changed(text, customer):
        return FlowResult(facts + [WILL_UPDATE], "fixed", handoff_reason="address change")
    return FlowResult(facts + [CAN_UPDATE], "fixed")


def account_answer(db, customer, detail: str | None, state, store, text: str = "") -> FlowResult:
    if detail == "address":
        visit = bool(state.flow) or any(t.startswith(("booked appointment", "rescheduled appointment")) for t in state.tried)
        return address_answer(customer, text, visit)
    if detail in ("membership",):
        m = membership(db, customer.customer_id)
        if m.tier == "none":
            facts = ["There is no Comfort Club membership on this account."]
        elif auto_renew_off(db, customer.customer_id):  # turned off in this conversation or earlier (review finding I4)
            facts = [f"Membership: Comfort Club {'Plus' if m.tier == 'plus' else 'Standard'}; auto-renew is off, so it "
                     f"stays active until {m.renewal_date} and then ends."]
        else:
            facts = [f"Membership: Comfort Club {'Plus' if m.tier == 'plus' else 'Standard'}, renews {m.renewal_date} "
                     f"at {_money(m.renewal_price_cents)} a year, the current published price."]
        return FlowResult(facts, "account answer", db_actions=[f"membership lookup {customer.customer_id}"])
    if detail == "system":
        s = system(db, customer.customer_id)
        installed = (f"installed {s.install_date}, {system_age(s.install_date, SETTINGS.now.date())}" if s.install_date
                     else "install date not on record")
        return FlowResult([f"System on record: {s.brand}, {installed}."], "account answer",
                          db_actions=[f"system lookup {customer.customer_id}"])
    invoices = open_invoices(db, customer.customer_id)
    if not invoices:
        return FlowResult(["There are no open invoices on this account."], "account answer",
                          db_actions=[f"invoice lookup {customer.customer_id}"])
    facts = []
    for invoice in invoices:
        lines = "; ".join(f"{desc} {_money(cents)}" for desc, cents in invoice.lines)
        due = date.fromisoformat(invoice.due_date)
        facts.append(f"Invoice {invoice.invoice_id}: balance {_money(invoice.balance_cents)}, due {due.day} {due:%B %Y}; "
                     f"lines as recorded: {lines}.")
        # A fixed fee that differs from the current schedule opens a silent review for staff (R47).
        reviewed = state.reviewed_invoices
        mismatches = fee_mismatches(invoice)
        state.tried.append(f"read the invoice lines for {invoice.invoice_id}")
        state.notes += [f"fee differs from schedule: {m}" for m in mismatches if f"fee differs from schedule: {m}" not in state.notes]
        if mismatches and invoice.invoice_id not in reviewed:
            try:
                store.create_ticket(None, f"{customer.name}, {customer.customer_id}", f"fee check on {invoice.invoice_id}",
                                    "none; caller not told", "; ".join(mismatches), "", "billing review")
                reviewed.append(invoice.invoice_id)  # only once the review is saved, so a failure is tried again
            except Exception as error:
                log.error("billing review for %s not saved: %s", invoice.invoice_id, error)
    facts.append("Read the lines exactly as recorded and never call a charge right or wrong.")
    return FlowResult(facts, "account answer", db_actions=[f"invoice lookup {customer.customer_id}"])
