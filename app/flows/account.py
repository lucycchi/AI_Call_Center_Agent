"""Account questions for an identified caller, from read-only lookups (R46, R47)."""

from datetime import date

from app.accounts.fee_check import fee_mismatches
from app.accounts.lookups import membership, open_invoices, system
from app.flows.protocol import FlowResult


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def account_answer(db, customer, detail: str | None, state, store) -> FlowResult:
    if detail in ("membership",):
        m = membership(db, customer.customer_id)
        if m.tier == "none":
            facts = ["There is no Comfort Club membership on this account."]
        else:
            facts = [f"Membership: Comfort Club {'Plus' if m.tier == 'plus' else 'Standard'}, renews {m.renewal_date} "
                     f"at {_money(m.renewal_price_cents)} a year, the current published price."]
        return FlowResult(facts, "account answer", db_actions=[f"membership lookup {customer.customer_id}"])
    if detail == "system":
        s = system(db, customer.customer_id)
        return FlowResult([f"System on record: {s.brand}, installed {s.install_date}."], "account answer",
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
            reviewed.append(invoice.invoice_id)
            store.create_ticket(None, f"{customer.name}, {customer.customer_id}", f"fee check on {invoice.invoice_id}",
                                "none; caller not told", "; ".join(mismatches), "", "billing review")
    facts.append("Read the lines exactly as recorded and never call a charge right or wrong.")
    return FlowResult(facts, "account answer", db_actions=[f"invoice lookup {customer.customer_id}"])
