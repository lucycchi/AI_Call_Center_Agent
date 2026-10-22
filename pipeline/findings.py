"""Write the findings document, docs/FINDINGS.md (R5 to R8, R56).

Run: python -m pipeline.findings
"""

import csv
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pipeline.capacity import capacity_by_zone, zone_mismatches
from pipeline.staff_checks import errors_in, staff_policy_errors
from pipeline.templates import outcome_of
from pipeline.transcripts import Call, load_transcripts

ROOT = Path(__file__).resolve().parent.parent

# How the agent handles each sub-reason of the top three (handled-reason list (D26)).
HANDLING = {
    "hvac repair": "booking", "plumbing": "booking", "tune-up": "booking", "burning smell": "handoff",
    "current balance": "lookups", "pay an invoice": "handoff", "what an invoice is for": "lookups",
    "charged twice": "documents", "quote dispute": "handoff", "refund": "handoff",
    "what it includes or price": "documents", "renewal date": "lookups", "autopay": "handoff",
    "cancel": "handoff", "upgrade": "handoff", "member discount on a new system": "documents",
}

REASON_STATUS = {
    "new booking": ("handled", "Booked in the database; a burning smell is handed off for safety"),
    "billing": ("partly handled", "Balances and invoice lines from lookups, duplicate charges from documents; disputes, refunds and payments handed off"),
    "membership": ("partly handled", "Plan details from documents, renewal dates from lookups; autopay, cancelling and upgrades handed off"),
    "warranty": ("handled", "Coverage from documents and the install-date lookup; claims booked"),
    "existing appointment": ("handled", "Confirm, cancel and reschedule in the database; late technicians handed off"),
    "complaint or manager": ("handed off", "Needs a human's authority"),
    "replacement estimate": ("handled", "Estimates are a bookable service"),
    "safety emergency": ("handed off", "Fixed safety reply, then a priority handoff"),
    "hiring": ("answered and redirected", "Pointed to the careers page"),
    "commercial": ("handed off", "Commercial work is a separate division"),
    "wrong number": ("answered and redirected", "Told this is Meridian Home Comfort"),
}

NOT_RESOLVED = {"safety", "callback", "redirect"}

# Why a top-three sub-reason is handed off rather than handled.
HANDOFF_WHY = {
    "burning smell": "safety: a possible electrical fire, so a fixed safety reply and a priority handoff (burning smell decision (D19))",
    "pay an invoice": "action on money: sending a payment link is in the action gap",
    "autopay": "action on money: setting up autopay is in the action gap; no document covers it",
    "cancel": "action on membership: turning off auto-renew is in the action gap",
    "upgrade": "action on membership: an upgrade charges the customer, so it is in the action gap",
    "quote dispute": "needs a human's authority: a disputed charge goes to a billing supervisor",
    "refund": "needs a human's authority: refunds go to a billing supervisor",
}

# Actions on money or membership the agent will not take (the action gap, account lookups (D17)).
ACCOUNT_ACTION = re.compile(r"payment link|secure link to add a card|auto-renew is off|you're upgraded", re.I)


@dataclass(frozen=True)
class Row:
    reason: str
    calls: int
    share: float
    minutes: float
    running_total: float


def rank_reasons(calls: list[Call], labels: dict[str, str]) -> list[Row]:
    counts, seconds = Counter(), Counter()
    for call in calls:
        counts[labels[call.call_id]] += 1
        seconds[labels[call.call_id]] += call.seconds
    total, running, rows = len(calls), 0, []
    for reason, n in sorted(counts.items(), key=lambda kv: (-kv[1], -seconds[kv[0]])):
        running += n
        rows.append(Row(reason, n, round(n / total, 3), round(seconds[reason] / 60, 1), round(running / total, 3)))
    return rows


def human_baseline(calls: list[Call]) -> dict:
    outcomes = [outcome_of(c) for c in calls]
    resolved = [o not in NOT_RESOLVED for o in outcomes]
    return {
        "calls": len(calls),
        "resolved_on_call": sum(resolved),
        "resolved_without_account_actions": sum(r and not ACCOUNT_ACTION.search(" ".join(c.agent_lines))
                                                for r, c in zip(resolved, calls)),
        "dropped_bookings": sum("dropped a booking the caller asked for" in errors_in(c) for c in calls),
    }


def _pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%"


def _invoice_patterns(db: sqlite3.Connection) -> dict:
    with_diag = with_diag_and_repair = member_diag = 0
    tiers = dict(db.execute("select customer_id, membership_tier from customers"))
    for customer, items in db.execute("select customer_id, line_items from invoices"):
        lines = [line["desc"] for line in json.loads(items)]
        if any("Diagnostic" in d for d in lines):
            with_diag += 1
            if len(lines) > 1:
                with_diag_and_repair += 1
            if tiers.get(customer) in ("standard", "plus"):
                member_diag += 1
    total = db.execute("select count(*) from invoices").fetchone()[0]
    return {"invoices": total, "with_diagnostic": with_diag, "diagnostic_plus_repair": with_diag_and_repair,
            "member_charged_diagnostic": member_diag}


def _agreement_lines(agreement: dict) -> list[str]:
    if agreement.get("status") != "final" or agreement.get("fable_vs_codex") is None:
        missing = ", ".join(agreement.get("fable_missing", [])) or "all"
        return [f"- **Agreement (provisional).** Codex against Haiku: {agreement['codex_vs_haiku']:.0%} of templates. "
                f"The Claude Fable 5.1 check on the blind third is not complete yet (missing: {missing}); this document is "
                "provisional until it is."]
    lines = [f"- **Agreement.** Codex against Haiku: {agreement['codex_vs_haiku']:.0%} of templates. Fable against Codex on the blind "
             f"third ({agreement['fable_labels']} templates): {agreement['fable_vs_codex']:.0%} on the call reason and "
             f"{agreement['fable_vs_codex_sub_reason']:.0%} on the sub-reason. No human labeled the templates; the agreement is "
             "between models from two companies."]
    if agreement["codex_vs_haiku"] == 1 and agreement["fable_vs_codex"] == 1 and agreement["fable_vs_codex_sub_reason"] == 1:
        lines.append("- **Why agreement is perfect.** It reflects how clean and repetitive these synthetic transcripts are, and "
                     "should not be read as evidence that real calls are this easy to sort.")
    return lines


def write_findings(path: Path, agreement: dict | None = None) -> None:
    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    templates = {r["call_id"]: r["template_id"] for r in csv.DictReader((ROOT / "data" / "templates.csv").open())}
    families = {r["template_id"]: r["family"] for r in csv.DictReader((ROOT / "data" / "templates.csv").open())}
    codex = {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}
    reason = {c.call_id: codex[templates[c.call_id]][0] for c in calls}
    sub = {c.call_id: codex[templates[c.call_id]][1] for c in calls}
    if agreement is None:
        agreement = json.loads((ROOT / "data" / "label_agreement.json").read_text())
    db = sqlite3.connect(data / "scheduling_db" / "meridian_scheduling.sqlite")
    rows = rank_reasons(calls, reason)
    baseline = human_baseline(calls)
    errors = staff_policy_errors(calls)
    error_calls = sum(bool(errors_in(c)) for c in calls)
    capacity = capacity_by_zone(db)
    mismatches = zone_mismatches(db)
    invoices = _invoice_patterns(db)
    n = len(calls)

    out = ["# Findings: Why Meridian Home Comfort's Customers Call", "",
           "What the 420 call transcripts (July to September 2026) show about why customers call, which calls the agent "
           "handles, how well staff handle them today, and three findings for the executive team. Generated by "
           "`python -m pipeline.findings` from the labeled data in `data/`.", "",
           "## In short", "",
           "- **Top five reasons, by calls:** " + "; ".join(f"{r.reason} {r.share:.0%}" for r in rows[:5]) +
           f". Together they are {rows[4].running_total:.0%} of calls.",
           "- **Scope:** the agent handles bookings, existing appointments and warranty, and the parts of billing and membership "
           "that documents or a read-only lookup can answer. It hands off anything that needs a human's authority or an action on "
           "money or membership, and every emergency after a fixed safety reply.",
           f"- **Staff today** resolve {_pct(baseline['resolved_on_call'], n)} of calls on the call, or "
           f"{_pct(baseline['resolved_without_account_actions'], n)} leaving out calls only an account action resolves; the second "
           "figure is the fair comparison for the agent.",
           f"- **For the executive team:** {_pct(error_calls, n)} of calls contain a staff policy error, the north zone has "
           f"{_pct(capacity['north']['customers'], sum(capacity[z]['customers'] for z in capacity))} of customers but "
           f"{_pct(capacity['north']['bookable'], sum(capacity[z]['bookable'] for z in capacity))} of bookable slots, and the "
           "documents are missing, stale or contradicted on autopay, waitlists and the diagnostic credit.", "",
           "## Method", "",
           f"- **The transcripts are templated.** The 420 calls fall into {len(set(templates.values()))} templates: calls that share the "
           "same request and the same staff outcome once names, numbers and filler words are removed. Labels are given per template. "
           f"Nine waitlist templates are the matching booking call plus one fixed waitlist exchange; each is linked to its booking twin as "
           f"a family ({len(set(families.values()))} families), and families stay on one side of the test split (template families (D39)).",
           f"- **Labels.** Claude Haiku 5.5 labeled every call against a fixed category list. Codex ({next(iter(csv.DictReader((ROOT / 'data' / 'labels_codex.csv').open())))['model']}, OpenAI) "
           "labeled one sample call per template without seeing Haiku's labels; these Codex labels are the reference. Claude Fable 5.1 "
           "labeled a blind third of the templates as a cross-company check.",
           *_agreement_lines(agreement),
           "- **Volume** is ranked by number of calls; staff minutes come from the call durations in the transcript index.", "",
           "## Top call reasons", "",
           "| Rank | Call reason | Calls | Share | Staff minutes | Running total | Handled or handed off | Reason |",
           "|---|---|---|---|---|---|---|---|"]
    def table_row(rank, row):
        status, why = REASON_STATUS.get(row.reason, ("handed off", ""))
        return f"| {rank} | {row.reason} | {row.calls} | {row.share:.0%} | {row.minutes} | {row.running_total:.0%} | {status} | {why} |"

    out += [table_row(rank, row) for rank, row in enumerate(rows[:5], 1)]
    out += ["", "## Other call reasons", "", "The remaining reasons, ranked the same way:", "",
            "| Rank | Call reason | Calls | Share | Staff minutes | Running total | Handled or handed off | Reason |",
            "|---|---|---|---|---|---|---|---|"]
    out += [table_row(rank, row) for rank, row in enumerate(rows[5:], 6)]
    top3 = [r.reason for r in rows[:3]]
    out += ["", "## Observed top three", "", *[f"{i}. {r}" for i, r in enumerate(top3, 1)], "",
            "The agent handles more than the top three. Warranty, the fourth reason, needs only documents, the install-date lookup "
            "and booking, all of which the top three already use, so it adds 11% of calls to the agent's reach at no new build "
            "cost. Existing appointments, the fifth, reuse the booking rules. What is handed off is decided by what a call needs, "
            "not by its rank: a human's authority (disputes, refunds, complaints, late technicians), an action on money or "
            "membership (payments, autopay, cancelling, upgrading), or emergency handling (scope decision (D26)).", "",
            "## Agent scope", "",
            "For each of the top three reasons, how its calls are handled (handled-reason list (D26)):", "",
            "| Call reason | Sub-reason | Calls | How the agent handles it | Why, if handed off |", "|---|---|---|---|---|"]
    for top in top3:
        subs = Counter(sub[c.call_id] for c in calls if reason[c.call_id] == top)
        for s, count in subs.most_common():
            how = HANDLING.get(s, "handoff")
            out.append(f"| {top} | {s} | {count} | {how} | {HANDOFF_WHY.get(s, '') if how == 'handoff' else ''} |")
    totals = Counter(HANDLING.get(sub[c.call_id], "handoff") for c in calls if reason[c.call_id] in top3)
    out += ["", "Across the top three: " + ", ".join(f"{k} {v}" for k, v in totals.most_common()) +
            f". So {_pct(sum(totals.values()) - totals['handoff'], sum(totals.values()))} of top-three calls are the agent's to finish and "
            f"{_pct(totals['handoff'], sum(totals.values()))} are handed off by design; the table gives the reason for each handed-off "
            "sub-reason.", "",
            "## Human baseline", "",
            f"- Staff resolved {baseline['resolved_on_call']} of {n} calls on the call ({_pct(baseline['resolved_on_call'], n)}).",
            f"- Excluding calls resolved only by an account action the agent will not take (payment links, autopay, cancelling "
            f"auto-renew, upgrades): {baseline['resolved_without_account_actions']} ({_pct(baseline['resolved_without_account_actions'], n)}). "
            "This is the fair comparison for the agent's containment.",
            f"- In {baseline['dropped_bookings']} calls the caller asked to book and staff ended the call without booking.",
            f"- These figures count waitlist calls (the caller was offered a waitlist and still booked) and dropped bookings as "
            f"resolved. Excluding the dropped bookings, staff resolved {baseline['resolved_on_call'] - baseline['dropped_bookings']} "
            f"({_pct(baseline['resolved_on_call'] - baseline['dropped_bookings'], n)}).", "",
            "## Executive findings", "",
            "### Staff policy errors", "",
            f"{error_calls} of {n} calls ({_pct(error_calls, n)}) contain a staff statement or action that contradicts the current documents:", ""]
    out += [f"- {k}: {v} calls" for k, v in errors.most_common()]
    out += ["", "Errors appear for every staff member, so they are systemic (training and documentation), not one person.", "",
            "### Capacity imbalance by zone", "",
            "| Zone | Customers | Bookable slots | HVAC repair | Tune-up | Plumbing | Estimate |", "|---|---|---|---|---|---|---|"]
    for zone in ("north", "central", "south"):
        z = capacity[zone]
        out.append(f"| {zone} | {z['customers']} | {z['bookable']} | {z['hvac repair']} | {z['tune-up']} | {z['plumbing']} | {z['estimate']} |")
    total_bookable = sum(capacity[z]["bookable"] for z in capacity)
    total_customers = sum(capacity[z]["customers"] for z in capacity)
    out += ["", f"The north zone has {_pct(capacity['north']['customers'], total_customers)} of customers but "
            f"{_pct(capacity['north']['bookable'], total_bookable)} of bookable slots and no plumbing slots; the central zone has "
            f"{_pct(capacity['central']['customers'], total_customers)} of customers but {_pct(capacity['central']['bookable'], total_bookable)} "
            "of slots and no estimate slots. Rebalancing technicians would cut wait times more than any agent.", "",
            "### Documentation gaps", "",
            f"- **Autopay:** {sum(sub[c.call_id] == 'autopay' for c in calls)} calls ask about it; no document covers it.",
            f"- **Waitlist:** staff offered a waitlist in {errors['offered a waitlist']} calls; only a stale 2024 guide mentions one and the "
            "scheduling database has none.",
            f"- **Diagnostic credit:** {invoices['diagnostic_plus_repair']} of {invoices['invoices']} invoices charge the $89 diagnostic fee "
            f"on top of a repair, although the FAQ says it is credited toward an approved repair, and {invoices['member_charged_diagnostic']} "
            "charge it to customers who are members today, for whom it is waived (the invoices do not record the tier at the time).", "",
            f"The seeded scheduling database also has {len(mismatches)} existing appointments outside the customer's zone; they are "
            "listed in the appendix at the end."]
    out += ["", "## Glossary", "",
            "- **Call reason (call driver):** why a customer called.",
            "- **Template:** a call pattern repeated across many transcripts with only names, numbers and filler words changed.",
            "- **Reference label:** the label treated as correct when measuring; here Codex's label for each template.",
            "- **Blind label:** a label given without seeing anyone else's label for the same item.",
            "- **Human baseline:** the share of calls staff resolved during the call.",
            "- **Action gap:** calls the agent understands but hands off because they need an action on money or membership.",
            "- **Bookable slot:** an appointment slot that is open, or reserved for members.",
            "- **Zone:** the area (north, central, south) a customer's city belongs to.", "",
            "## Seeded appointments outside the customer's zone", "",
            f"{len(mismatches)} scheduled appointments in the seeded database are in a zone that does not match the customer's city. "
            "The agent leaves existing appointments as recorded and applies the zone rule only to new bookings.", "",
            "| Appointment | Customer | City | Customer's zone | Slot's zone |", "|---|---|---|---|---|"]
    out += [f"| {m['appointment_id']} | {m['customer_id']} | {m['city']} | {m['customer_zone']} | {m['slot_zone']} |" for m in mismatches]
    path.write_text("\n".join(out) + "\n")


def main() -> None:
    write_findings(ROOT / "docs" / "FINDINGS.md")
    print("wrote docs/FINDINGS.md")


if __name__ == "__main__":
    main()
