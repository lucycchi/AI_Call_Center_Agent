"""Build one frozen test case per template (R10, R11, R29, R81).

Each case has a caller card tied to a real database customer (or a marked synthetic one), any
fixtures to plant in its database copy, its expected outcome under the handled-reason list (D26),
and, for questions answered from documents, a reference answer written from the current documents
with the exact evidence spans (file and line range) that support it.

Reference answers are drafted here from the current documents, never from what staff said in the
transcripts, and are spot-checked by the author before the held-out set is frozen.

Run: python -m eval.build_cases   (writes data/testset/ and data/split.json)
"""

import csv
import hashlib
import json
import random
import re
import sqlite3
from pathlib import Path

from app.knowledge.index import chunk_document
from app.scheduling.zones import zone_for
from pipeline.transcripts import load_transcripts

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
KB_TEXT = ROOT / "data" / "kb_text"
BRANDS = ("Trane", "Carrier", "Goodman", "Rheem", "Lennox", "American Standard")
CITIES = ("Round Rock", "Cedar Park", "Pflugerville", "Georgetown", "Leander", "Hutto", "Austin", "Kyle", "Buda")
ZONE_CAPACITY = {"north": {"plumbing": 0}, "central": {"estimate": 0}, "south": {}}

# How each sub-reason is handled, from the handled-reason list (D26) and the burning-smell decision (D19).
OUTCOMES = {
    "hvac repair": ("contained", None, "hvac_repair"), "plumbing": ("contained", None, "plumbing"),
    "tune-up": ("contained", None, "hvac_tune_up"), "burning smell": ("handed_off", "burning smell", None),
    "current balance": ("contained", None, None), "pay an invoice": ("handed_off", "action gap", None),
    "what an invoice is for": ("handed_off", "action gap", None),  # caller also asks to email an itemized copy
    "charged twice": ("contained", None, None), "quote dispute": ("handed_off", "dispute", None),
    "refund": ("handed_off", "dispute", None),
    "what it includes or price": ("contained", None, None), "renewal date": ("contained", None, None),
    "autopay": ("handed_off", "action gap", None), "cancel": ("handed_off", "action gap", None),
    "upgrade": ("handed_off", "action gap", None), "member discount on a new system": ("contained", None, None),
    "claim": ("contained", None, "hvac_repair"), "registration": ("contained", None, None),
    "transfer": ("contained", None, None), "repeat repair": ("contained", None, "hvac_repair"),
    "reschedule": ("contained", None, None), "confirm": ("contained", None, None),
    "technician late": ("handed_off", "late technician", None),
    "complaint or manager": ("handed_off", "complaint", None),
    "replacement estimate": ("contained", None, "estimate"),
    "gas, carbon monoxide or sparks": ("handed_off", "emergency", None),
    "hiring": ("redirect", None, None), "commercial": ("handed_off", "commercial", None),
    "wrong number": ("redirect", None, None),
}
OUTCOMES["cancel appointment"] = ("contained", None, None)

# Reference answers for questions answered from the current documents, with the sections that support them.
REFERENCES = {
    "charged twice": ("One of the two charges is usually a pending authorization that drops off in 3 to 5 business days. "
                      "If both charges post, Meridian opens a case with its payment processor.",
                      [("faq__customer_faq.md", "Duplicate charges")]),
    "what it includes or price": ("The Comfort Club costs $189 a year per system or $16.99 a month (12-month minimum), $99 per "
                                  "additional system. It includes two seasonal tune-ups a year, priority scheduling, the $89 "
                                  "diagnostic fee waived, 15% off repairs and no after-hours dispatch fee. Comfort Club Plus is "
                                  "$269 a year and adds a water heater flush and inspection, a plumbing inspection and 15% off "
                                  "plumbing repairs.",
                                  [("membership__comfort_club_overview.md", "Plans")]),
    "member discount on a new system": ("Comfort Club members (Standard and Plus) get $500 off a full system replacement. "
                                        "Replacements start with a free in-home estimate.",
                                        [("membership__comfort_club_overview.md", "Plans"),
                                         ("services__service_catalog.md", "System replacement")]),
    "registration": ("Meridian registers every installed unit with the manufacturer within 30 days of installation; "
                     "registration is required for the full parts warranty term.",
                     [("warranty__warranty_policy.md", "New system installation warranty")]),
    "transfer": ("Manufacturer parts warranties can transfer once to a new homeowner, usually within 90 days of the sale, with a "
                 "manufacturer transfer fee of $50 to $100. Meridian's labor warranty does not transfer.",
                 [("warranty__warranty_policy.md", "Warranty transfer")]),
    "claim": ("A full system installation has a 2-year Meridian labor warranty, so a unit installed within the last year is "
              "covered; a warranty diagnostic is booked and there is no diagnostic fee if the failure is covered.",
              [("warranty__warranty_policy.md", "New system installation warranty"),
               ("warranty__warranty_policy.md", "Filing a claim")]),
    "repeat repair": ("Repairs carry a 1-year labor warranty on the specific part repaired; if the same part fails within a "
                      "year, the return visit and labor are free.",
                      [("warranty__warranty_policy.md", "Repair warranty (Meridian labor warranty)")]),
    "replacement estimate": ("Replacements start with a free in-home estimate from a Comfort Advisor; a full residential split "
                             "system typically costs $8,000 to $16,000 installed, and the technician or advisor confirms the "
                             "price.",
                             [("services__service_catalog.md", "System replacement")]),
}
COMPRESSOR = ("If the unit is registered, the manufacturer covers the compressor part for 10 years. The 2-year Meridian "
              "installation labor warranty has ended for a 3-year-old system, so labor is billable; compressor replacement "
              "labor typically runs $600 to $900, confirmed by the technician on site.",
              [("warranty__warranty_policy.md", "Manufacturer parts warranty (residential, when registered)"),
               ("pricing__repair_price_book_2026.md", "HVAC repair")])


def expected_outcome(reason: str, sub: str, zone: str | None) -> tuple[str, str | None]:
    outcome, why, service = OUTCOMES[sub]
    if service and zone and ZONE_CAPACITY.get(zone, {}).get(service.replace("hvac_", ""), 1) == 0:
        return "clean_decline", f"no {service.replace('hvac_', '')} capacity in {zone} zone"
    return outcome, why


def _spans(sections: list[tuple[str, str]]) -> list[dict]:
    spans = []
    for file, heading in sections:
        chunk = next(c for c in chunk_document(KB_TEXT / file) if c.heading == heading)
        spans.append({"file": file, "heading": heading, "start_line": chunk.start_line, "end_line": chunk.end_line})
    return spans


def caller_card(db: sqlite3.Connection, zone: str | None, tier: str | None, brand: str | None,
                install_after: str | None, install_before: str | None, rng: random.Random | None = None) -> dict:
    rows = db.execute("select customer_id, name, phone, email, service_address, city, zip, membership_tier, "
                      "membership_renewal_date, system_brand, system_install_date from customers "
                      "where customer_id not in ('MHC-10001','MHC-10002','MHC-10003','MHC-10004') order by customer_id").fetchall()
    keys = ["customer_id", "name", "phone", "email", "service_address", "city", "zip", "membership_tier",
            "membership_renewal_date", "system_brand", "system_install_date"]
    matches = []
    for row in rows:
        card = dict(zip(keys, row))
        card["zone"] = zone_for(card["city"])
        if zone and card["zone"] != zone:
            continue
        if tier == "member" and card["membership_tier"] == "none" or tier not in (None, "member") and card["membership_tier"] != tier:
            continue
        if brand and card["system_brand"] != brand:
            continue
        if install_after and (card["system_install_date"] or "") < install_after:
            continue
        if install_before and (card["system_install_date"] or "9999") > install_before:
            continue
        matches.append(card)
    if matches:
        card = (rng or random.Random(0)).choice(matches)
        card["synthetic"] = False
        return card
    city = next(c for c in CITIES if zone_for(c) == (zone or "north"))
    return {"customer_id": f"MHC-9{int(hashlib.sha256(repr((zone, tier, brand, install_after)).encode()).hexdigest(), 16) % 10000:04d}", "name": "Jordan Rivera",
            "phone": "512-555-0199", "email": "jordan.rivera@example.com", "service_address": "100 Test Lane",
            "city": city, "zip": "78600", "membership_tier": tier if tier not in (None, "member") else ("standard" if tier else "none"),
            "membership_renewal_date": "2026-11-15" if tier else None, "system_brand": brand or "Trane",
            "system_install_date": install_after or "2020-01-01", "zone": zone or "north", "synthetic": True}


def _requirements(sub: str, text: str) -> dict:
    brand = next((b for b in BRANDS if b.lower() in text.lower()), None)
    city = next((c for c in CITIES if c.lower() in text.lower()), None)
    need = {"zone": zone_for(city) if city else None, "tier": None, "brand": brand, "install_after": None, "install_before": None}
    if sub in ("renewal date", "cancel", "upgrade", "autopay", "member discount on a new system"):
        need["tier"] = "standard" if sub == "upgrade" else "member"
    if sub in ("claim", "registration"):
        need["install_after"] = "2025-10-16"
    if "three years old" in text.lower():
        need["install_after"], need["install_before"] = "2023-01-01", "2023-12-31"
    return need


def _invoice_fixture(card: dict, text: str, n: int) -> dict:
    amounts = [int(a.replace(",", "")) for a in re.findall(r"\$([\d,]+)(?:\.\d\d)?", text)]
    total = (amounts[0] if amounts else 245) * 100
    repair = max(total - 8900, 0)
    lines = [{"desc": "Diagnostic visit", "cents": 8900}, {"desc": "Repair", "cents": repair}] if repair else [{"desc": "Diagnostic visit", "cents": total}]
    return {"table": "invoices", "row": {"invoice_id": f"INV-{900000 + n}", "customer_id": card["customer_id"],
                                         "appointment_id": None, "issued_date": "2026-10-02", "due_date": "2026-11-01",
                                         "amount_cents": total, "balance_cents": total, "line_items": json.dumps(lines)}}


def _appointment_fixtures(db: sqlite3.Connection, card: dict, date: str, window: str, n: int) -> list[dict]:
    """A new booked slot (so existing slots are untouched) and the caller's appointment in it."""
    tech = db.execute("select tech_id from technicians where home_zone = ? and skills like '%hvac%' order by tech_id",
                      (card["zone"],)).fetchone()[0]
    slot_id = 9000 + n
    return [{"table": "appointment_slots", "row": {"slot_id": slot_id, "slot_date": date, "window": window, "tech_id": tech,
                                                   "zone": card["zone"], "service_type": "hvac_repair", "status": "booked"}},
            {"table": "appointments", "row": {"appointment_id": 5000 + n, "slot_id": slot_id, "customer_id": card["customer_id"],
                                              "issue_description": "test appointment", "created_at": "2026-10-10",
                                              "status": "scheduled", "is_warranty_visit": 0}}]


def _window_in(text: str) -> str:
    match = re.search(r"\b(8|12|1|4) to (12|4|5|7)\b", text)
    return {("8", "12"): "08:00-12:00", ("12", "4"): "12:00-16:00", ("1", "5"): "13:00-17:00",
            ("4", "7"): "16:00-19:00"}.get(match.groups(), "08:00-12:00") if match else "08:00-12:00"


APPOINTMENT_DATES = {"reschedule": "2026-10-17", "confirm": "2026-10-22", "cancel appointment": "2026-10-21",
                     "technician late": "2026-10-16"}


def build_cases(out: Path, seed: int = 20261016) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    data = ROOT / "call_data"
    calls = {c.call_id: c for c in load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")}
    rows = list(csv.DictReader((ROOT / "data" / "templates.csv").open()))
    labels = {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}
    db = sqlite3.connect(SEED)
    rng = random.Random(seed)
    first = {}
    for r in rows:
        first.setdefault(r["template_id"], r)
    cases = []
    for n, (template, row) in enumerate(sorted(first.items())):
        reason, sub = labels[template]
        if reason == "existing appointment" and sub == "cancel":
            sub = "cancel appointment"
        call = calls[row["call_id"]]
        text = " ".join(call.customer_lines + call.agent_lines)
        need = _requirements(sub, text)
        card = caller_card(db, rng=rng, **need)
        fixtures = []
        if card["synthetic"]:
            fixtures.append({"table": "customers", "row": {k: card[k] for k in (
                "customer_id", "name", "phone", "email", "service_address", "city", "zip", "membership_tier",
                "membership_renewal_date", "system_brand", "system_install_date")}})
        if reason == "billing":
            fixtures.append(_invoice_fixture(card, " ".join(call.customer_lines), n))
        if sub in APPOINTMENT_DATES:
            fixtures += _appointment_fixtures(db, card, APPOINTMENT_DATES[sub], _window_in(text), n)
        outcome, why = expected_outcome(reason, sub, card["zone"])
        if re.search(r"maintenance plan|comfort club", " ".join(call.customer_lines), re.I) and reason == "new booking":
            outcome, why = "handed_off", "action gap"  # the caller also joins the Comfort Club, an action on membership
        reference, spans = (COMPRESSOR if "compressor" in text.lower() else REFERENCES.get(sub, (None, [])))
        case = {
            "case_id": template, "template_id": template, "family": row["family"], "calls_weight": int(row["template_calls"]),
            "reason": reason, "sub_reason": sub, "sample_call_id": call.call_id,
            "caller_script": call.customer_lines, "caller_card": card, "fixtures": fixtures,
            "expected_outcome": outcome, "expected_handoff_reason": why,
            "needs_documents": reference is not None, "reference_answer": reference, "evidence_spans": _spans(spans),
            "must_not": ["promise a waitlist"] if row["outcome"] == "waitlist" else [],
        }
        (out / f"{template}.json").write_text(json.dumps(case, indent=1))
        cases.append(case)
    return cases


def main() -> None:
    from eval.split import freeze_hash, split_templates, write_split_counts

    out = ROOT / "data" / "testset"
    cases = build_cases(out)
    rows = list(csv.DictReader((ROOT / "data" / "templates.csv").open()))
    labels = {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}
    split = split_templates(rows, labels)
    write_split_counts(rows, labels, split, ROOT / "data" / "split_counts.csv")
    held = [out / f"{t}.json" for t in split.held_out]
    (ROOT / "data" / "split.json").write_text(json.dumps({
        "seed": 20261016, "working": list(split.working), "held_out": list(split.held_out),
        "held_out_hash": freeze_hash(held), "status": "draft until the author spot-checks the reference answers"}, indent=1))
    print(f"{len(cases)} cases; working {len(split.working)} templates, held-out {len(split.held_out)} templates")


if __name__ == "__main__":
    main()
