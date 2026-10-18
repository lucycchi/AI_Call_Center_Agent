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
from datetime import date, timedelta
from pathlib import Path

from app.config import SETTINGS
from app.scheduling.zones import zone_for
from pipeline.capacity import capacity_by_zone
from pipeline.transcripts import load_transcripts

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"
KB_TEXT = ROOT / "data" / "kb_text"
BRANDS = ("Trane", "Carrier", "Goodman", "Rheem", "Lennox", "American Standard")
CITIES = ("Round Rock", "Cedar Park", "Pflugerville", "Georgetown", "Leander", "Hutto", "Austin", "Kyle", "Buda")
# Open and members-only slots per zone and service in the seed, from the pipeline's capacity counts.
ZONE_CAPACITY = {zone: {"repair": c["hvac repair"], "tune_up": c["tune-up"], "plumbing": c["plumbing"], "estimate": c["estimate"]}
                 for zone, c in capacity_by_zone(sqlite3.connect(SEED)).items()}

# How each sub-reason is handled, from the handled-reason list (D26) and the burning-smell decision (D19).
OUTCOMES = {
    "hvac repair": ("contained", None, "hvac_repair"), "plumbing": ("contained", None, "plumbing"),
    "tune-up": ("contained", None, "hvac_tune_up"), "burning smell": ("handed_off", "burning smell", None),
    "current balance": ("contained", None, None), "pay an invoice": ("handed_off", "action gap", None),
    "what an invoice is for": ("contained", None, None),
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

# Reference answers for questions answered from the current documents. Each evidence span is a
# (converted file, section heading, phrases) triple: the span covers exactly the lines in that section
# holding those phrases, so the labels do not depend on how the documents are split into chunks (R29).
MEMBERSHIP, CATALOG, WARRANTY = "membership__comfort_club_overview.md", "services__service_catalog.md", "warranty__warranty_policy.md"
REFERENCES = {
    "charged twice": ("One of the two charges is usually a pending authorization that drops off in 3 to 5 business days. "
                      "If both charges post, Meridian opens a case with its payment processor.",
                      [("faq__customer_faq.md", "Duplicate charges", ("pending authorization",))]),
    "what it includes or price": ("The Comfort Club costs $189 a year per system or $16.99 a month (12-month minimum), $99 per "
                                  "additional system. It includes two seasonal tune-ups a year, priority scheduling, the $89 "
                                  "diagnostic fee waived, 15% off repairs and no after-hours dispatch fee. Comfort Club Plus is "
                                  "$269 a year and adds a water heater flush and inspection, a plumbing inspection and 15% off "
                                  "plumbing repairs.",
                                  [(MEMBERSHIP, "Plans", ("$189 per year", "15% off plumbing repairs")),
                                   (MEMBERSHIP, "Billing and renewal", ("12-month minimum",))]),
    "member discount on a new system": ("Comfort Club members (Standard and Plus) get $500 off a full system replacement. "
                                        "Replacements start with a free in-home estimate.",
                                        [(MEMBERSHIP, "Plans", ("$500 off any full system replacement",)),
                                         (CATALOG, "System replacement", ("Free in-home estimate", "Comfort Club members receive"))]),
    "registration": ("Meridian registers every installed unit with the manufacturer within 30 days of installation; "
                     "registration is required for the full parts warranty term.",
                     [(WARRANTY, "New system installation warranty", ("registers every installed unit",))]),
    "transfer": ("Manufacturer parts warranties can transfer once to a new homeowner, usually within 90 days of the sale, with a "
                 "manufacturer transfer fee of $50 to $100. Meridian's labor warranty does not transfer.",
                 [(WARRANTY, "Warranty transfer", ("may transfer once", "do **not** transfer"))]),
    "claim": ("A full system installation has a 2-year Meridian labor warranty, so a unit installed within the last year is "
              "covered; a warranty diagnostic is booked and there is no diagnostic fee if the failure is covered.",
              [(WARRANTY, "New system installation warranty", ("2-year labor warranty",)),
               (WARRANTY, "Filing a claim", ("warranty diagnostic",))]),
    "repeat repair": ("Repairs carry a 1-year labor warranty on the specific part repaired; if the same part fails within a "
                      "year, the return visit and labor are free.",
                      [(WARRANTY, "Repair warranty (Meridian labor warranty)", ("1-year labor warranty", "same part fails"))]),
    "replacement estimate": ("Replacements start with a free in-home estimate from a Comfort Advisor; a full residential split "
                             "system typically costs $8,000 to $16,000 installed, depending on tonnage, efficiency rating, "
                             "ductwork condition and brand.",
                             [(CATALOG, "System replacement", ("Free in-home estimate", "$8,000"))]),
}
COMPRESSOR = ("If the unit is registered, the manufacturer covers the compressor part for 10 years. The standard 2-year "
              "Meridian installation labor warranty has ended for a 3-year-old system, so labor is billable unless the customer "
              "was a Comfort Club member when it was installed (members get a 5-year labor warranty, which staff confirm); "
              "compressor replacement labor typically runs $600 to $900, confirmed by the technician on site.",
              [(WARRANTY, "Manufacturer parts warranty (residential, when registered)", ("| Trane |", "Labor to replace")),
               (WARRANTY, "New system installation warranty", ("2-year labor warranty", "5-year labor warranty")),
               ("pricing__repair_price_book_2026.md", "HVAC repair", ("Compressor replacement labor",)),
               ("pricing__repair_price_book_2026.md", "2026 Repair Price Book", ("confirms the final price",))])
MEMBERSHIP_SAVINGS = ("Comfort Club Standard is $189 a year per system (or $16.99 a month). Members have the $89 diagnostic fee "
                      "waived and get 15% off repairs (parts and labor), plus two seasonal tune-ups a year. The documents don't "
                      "say whether those benefits apply to a visit booked on the day you join, so a team member confirms that "
                      "when setting up the membership.",
                      [(MEMBERSHIP, "Plans", ("$189 per year", "15% off all repairs"))])
UPGRADE = ("Yes. Standard members can upgrade to Comfort Club Plus at any time; the $80 difference is prorated for the "
           "months left in the current term.",
           [(MEMBERSHIP, "Upgrades", ("may upgrade to Plus",))])
CANCEL_BEFORE_RENEWAL = ("Yes. Members can cancel auto-renewal at any time before the renewal date. An annual plan bills once on "
                         "the enrollment date and renews on the same date each year.",
                         [(MEMBERSHIP, "Cancellation", ("cancel auto-renewal",)),
                          (MEMBERSHIP, "Billing and renewal", ("Annual plans bill once",))])
NAMED_REFERENCES = {"MEMBERSHIP_SAVINGS": MEMBERSHIP_SAVINGS, "UPGRADE": UPGRADE,
                    "CANCEL_BEFORE_RENEWAL": CANCEL_BEFORE_RENEWAL, "COMPRESSOR": COMPRESSOR}


def expected_outcome(reason: str, sub: str, zone: str | None) -> tuple[str, str | None]:
    outcome, why, service = OUTCOMES[sub]
    if service and zone and ZONE_CAPACITY.get(zone, {}).get(service.replace("hvac_", ""), 1) == 0:
        return "clean_decline", f"no {service.replace('hvac_', '')} capacity in {zone} zone"
    return outcome, why


def _spans(sections: list[tuple[str, str, tuple[str, ...]]]) -> list[dict]:
    """Read each section straight from the converted file and keep only the lines holding its phrases."""
    spans = []
    for file, heading, phrases in sections:
        lines = (KB_TEXT / file).read_text().splitlines()
        first = next(n for n, line in enumerate(lines, 1) if re.fullmatch(rf"#+ {re.escape(heading)}", line.strip()))
        level = len(lines[first - 1]) - len(lines[first - 1].lstrip("#"))
        last = next((n - 1 for n in range(first + 1, len(lines) + 1)
                     if re.match(rf"#{{1,{level}}} ", lines[n - 1])), len(lines))
        found = []
        for phrase in phrases:
            hits = [n for n in range(first, last + 1) if phrase in lines[n - 1]]
            if len(hits) != 1:
                raise ValueError(f"{phrase!r} matches {len(hits)} lines in {file} {heading!r}")
            found += hits
        spans.append({"file": file, "heading": heading, "start_line": min(found), "end_line": max(found)})
    return spans


CUSTOMER_KEYS = ["customer_id", "name", "phone", "email", "service_address", "city", "zip", "membership_tier",
                 "membership_renewal_date", "system_brand", "system_install_date"]
RESERVED = ("MHC-10001", "MHC-10002", "MHC-10003", "MHC-10004")


def _customers(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(f"select {', '.join(CUSTOMER_KEYS)} from customers order by customer_id").fetchall()
    cards = [dict(zip(CUSTOMER_KEYS, row)) for row in rows]
    for card in cards:
        card["zone"] = zone_for(card["city"])
    return [c for c in cards if c["customer_id"] not in RESERVED]


def _matches(card: dict, zone, tier, brand, install_after, install_before) -> bool:
    if zone and card["zone"] != zone:
        return False
    if tier == "member" and card["membership_tier"] == "none" or tier not in (None, "member") and card["membership_tier"] != tier:
        return False
    if brand and card["system_brand"] != brand:
        return False
    if install_after and (card["system_install_date"] or "") < install_after:
        return False
    return not (install_before and (card["system_install_date"] or "9999") > install_before)


def caller_card(db: sqlite3.Connection, zone: str | None, tier: str | None, brand: str | None,
                install_after: str | None, install_before: str | None, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random(0)
    customers = _customers(db)
    matches = [c for c in customers if _matches(c, zone, tier, brand, install_after, install_before)]
    source = "transcript" if zone else "drawn"
    if matches:
        return {**rng.choice(matches), "synthetic": False, "zone_source": source}
    # No real customer matches: a synthetic one, numbered MHC-0xxxx, below every real id (MHC-10001 upwards).
    zone = zone or rng.choice(customers)["zone"]
    city = next(c for c in CITIES if zone_for(c) == zone)
    number = int(hashlib.sha256(repr((zone, tier, brand, install_after)).encode()).hexdigest(), 16) % 10000
    return {"customer_id": f"MHC-0{number:04d}", "name": "Jordan Rivera",
            "phone": "512-555-0199", "email": "jordan.rivera@example.com", "service_address": "100 Test Lane",
            "city": city, "zip": "78600", "membership_tier": tier if tier not in (None, "member") else ("standard" if tier else "none"),
            "membership_renewal_date": "2026-11-15" if tier else None, "system_brand": brand or "Trane",
            "system_install_date": install_after or "2020-01-01", "zone": zone, "synthetic": True, "zone_source": source}


PLAN = re.compile(r"maintenance plan|comfort club", re.I)
ENROL = re.compile(r"\b(add it|sign me up|enrol+ me|i(?:'d| would)? (?:like|want) to join)\b", re.I)

AGES = {w: n for n, w in enumerate("one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                   "fifteen sixteen seventeen eighteen nineteen twenty".split(), 1)}


def _requirements(sub: str, text: str) -> dict:
    brand = next((b for b in BRANDS if b.lower() in text.lower()), None)
    city = next((c for c in CITIES if c.lower() in text.lower()), None)
    need = {"zone": zone_for(city) if city else None, "tier": None, "brand": brand, "install_after": None, "install_before": None}
    if sub in ("renewal date", "cancel", "upgrade", "autopay", "member discount on a new system"):
        need["tier"] = "standard" if sub == "upgrade" else "member"
    if sub in ("claim", "registration"):
        need["install_after"] = "2025-10-16"
    if PLAN.search(text) and ENROL.search(text):
        need["tier"] = "none"  # a caller asking to join is not yet a member
    age = re.search(rf"\b(\d+|{'|'.join(AGES)}) years? old\b", text, re.I)
    if age:
        year = SETTINGS.now.year - int(AGES.get(age.group(1).lower(), age.group(1)))
        need["install_after"], need["install_before"] = f"{year}-01-01", f"{year}-12-31"
    return need


STREET = r"\d{2,5}(?: [A-Z][a-z]+)+ (?:St|Ln|Dr|Rd|Ct|Pass|Ave|Way|Blvd|Trl|Cv|Pl|Loop|Pkwy)\b"
NAME_LINE = re.compile(r"^((?i:(?:um|uh|sure|yeah|yes|okay|ok)[,.] )*(?i:it's |this is |my name is )?)"
                       r"([A-Za-z][a-z]+ [A-Z][a-z]+)(?=[,.]|$)")


def use_card(lines: list[str], card: dict) -> list[str]:
    """The transcript's lines with the caller's account number, name, phone and address replaced by the card's (R11)."""
    names = {m.group(2) for line in lines if (m := NAME_LINE.match(line.strip()))}
    out = []
    for line in lines:
        line = re.sub(r"MHC-\d+", card["customer_id"], line)
        line = re.sub(r"\b\d{3}-\d{3}-\d{4}\b", card["phone"], line)
        line = re.sub(rf"{STREET}(?:, (?:{'|'.join(CITIES)}))?", f"{card['service_address']}, {card['city']}", line)
        for name in names:
            line = re.sub(rf"\b{re.escape(name)}\b", card["name"], line, flags=re.I)
        out.append(line)
    return out


def _invoice_fixture(card: dict, text: str, n: int, paid: bool = False) -> dict:
    """The invoice the caller describes: their invoice number, the amount the invoice shows (not a quote), and
    already paid when the caller says they paid (charged twice, or asking for a refund)."""
    stated = re.search(r"invoice[^$]{0,30}\$([\d,]+)", text, re.I) or re.search(r"\$([\d,]+)", text)
    total = (int(stated.group(1).replace(",", "")) if stated else 245) * 100
    named = re.search(r"INV-\d{6}", text)
    repair = max(total - 8900, 0)
    lines = [{"desc": "Diagnostic visit", "cents": 8900}, {"desc": "Repair", "cents": repair}] if repair else [{"desc": "Diagnostic visit", "cents": total}]
    return {"table": "invoices", "row": {"invoice_id": named.group(0) if named else f"INV-{900000 + n}",
                                         "customer_id": card["customer_id"], "appointment_id": None,
                                         "issued_date": "2026-10-02", "due_date": "2026-11-01",
                                         "amount_cents": total, "balance_cents": 0 if paid else total, "line_items": json.dumps(lines)}}


def _window_in(text: str) -> str | None:
    match = re.search(r"\b(8|12|1|4) to (12|4|5|7)\b", text)
    return {("8", "12"): "08:00-12:00", ("12", "4"): "12:00-16:00", ("1", "5"): "13:00-17:00",
            ("4", "7"): "16:00-19:00"}.get(match.groups()) if match else None


APPOINTMENT_DATES = {"reschedule": "2026-10-17", "confirm": "2026-10-22", "cancel appointment": "2026-10-21",
                     "technician late": "2026-10-16"}


# What the caller's words say the appointment is for, when they say.
SERVICE_WORDS = [(re.compile(r"\b(fix|fixing|fixed|repair)\b", re.I), "hvac_repair"),
                 (re.compile(r"\btune-?up\b", re.I), "hvac_tune_up"),
                 (re.compile(r"\b(sink|drain|water heater|plumb\w*)\b", re.I), "plumbing"),
                 (re.compile(r"\bestimate\b", re.I), "estimate")]


def _service_in(lines: list[str]) -> str | None:
    text = " ".join(lines)
    return next((service for words, service in SERVICE_WORDS if words.search(text)), None)


def _overlaps(a: str, b: str) -> bool:
    (a1, a2), (b1, b2) = a.split("-"), b.split("-")
    return a1 < b2 and b1 < a2


def _existing_appointment(db: sqlite3.Connection, need: dict, day: str, window: str | None, service: str | None, n: int,
                          rng: random.Random) -> tuple[dict, dict, list[dict]]:
    """The caller's appointment, in order of preference: a matching real customer's scheduled appointment in the seed;
    an open seed slot booked for the card's customer; a new slot for a technician free in that window. The freed-slot
    rule (R55, D33) then covers every case: a seed slot returns to its seed status, booked ones and new ones to open."""
    customers = {c["customer_id"]: c for c in _customers(db)}
    rows = db.execute("select a.appointment_id, a.customer_id, s.slot_id, s.window, s.tech_id, s.zone, s.service_type "
                      "from appointments a join appointment_slots s using (slot_id) where a.status = 'scheduled' "
                      "and s.slot_date = ? order by a.appointment_id", (day,)).fetchall()
    upcoming = dict(db.execute("select a.customer_id, count(*) from appointments a join appointment_slots s using (slot_id) "
                               "where a.status = 'scheduled' and s.slot_date >= ? group by 1", (SETTINGS.now.date().isoformat(),)))
    # The caller's appointment is the only one they have coming up, so "my appointment" is unambiguous, and it is for
    # the service their words describe when they name one.
    seeded = [(row[:6], customers[row[1]]) for row in rows if row[1] in customers and (window is None or row[3] == window)
              and (service is None or row[6] == service) and upcoming.get(row[1]) == 1
              and row[5] == customers[row[1]]["zone"] and _matches(customers[row[1]], **need)]
    if seeded:
        (appointment_id, _, slot_id, slot_window, tech, zone), card = rng.choice(seeded)
        card = {**card, "synthetic": False, "zone_source": "transcript" if need["zone"] else "drawn"}
        return card, {"appointment_id": appointment_id, "slot_id": slot_id, "slot_date": day, "window": slot_window,
                      "tech_id": tech, "zone": zone, "source": "seed"}, []
    card = caller_card(db, rng=rng, **need)
    open_slots = db.execute("select slot_id, window, tech_id from appointment_slots where status = 'open' and zone = ? "
                            "and slot_date = ? and service_type = ? order by slot_id",
                            (card["zone"], day, service or "hvac_repair")).fetchall()
    open_slots = [s for s in open_slots if window is None or s[1] == window]
    appointment = {"table": "appointments", "row": {"appointment_id": 5000 + n, "slot_id": None, "customer_id": card["customer_id"],
                                                    "issue_description": "test appointment", "created_at": "2026-10-10",
                                                    "status": "scheduled", "is_warranty_visit": 0}}
    if open_slots:
        slot_id, slot_window, tech = open_slots[0]
        appointment["row"]["slot_id"], appointment["book_slots"] = slot_id, [slot_id]
        return card, {"appointment_id": 5000 + n, "slot_id": slot_id, "slot_date": day, "window": slot_window,
                      "tech_id": tech, "zone": card["zone"], "source": "booked open slot"}, [appointment]
    offered = {w for (w,) in db.execute("select distinct window from appointment_slots where strftime('%w', slot_date) = "
                                        "strftime('%w', ?)", (day,))}
    for slot_window in [window] if window else sorted(offered):
        if slot_window not in offered:
            continue
        for (tech,) in db.execute("select tech_id from technicians where home_zone = ? and skills like '%hvac%' order by tech_id",
                                  (card["zone"],)):
            busy = [w for (w,) in db.execute("select window from appointment_slots where tech_id = ? and slot_date = ?", (tech, day))]
            if not any(_overlaps(slot_window, w) for w in busy):
                slot_id = 9000 + n
                appointment["row"]["slot_id"] = slot_id
                slot = {"table": "appointment_slots", "row": {"slot_id": slot_id, "slot_date": day, "window": slot_window,
                                                              "tech_id": tech, "zone": card["zone"],
                                                              "service_type": service or "hvac_repair", "status": "booked"}}
                return card, {"appointment_id": 5000 + n, "slot_id": slot_id, "slot_date": day, "window": slot_window,
                              "tech_id": tech, "zone": card["zone"], "source": "planted"}, [slot, appointment]
    raise ValueError(f"no way to give the caller an appointment on {day} {window or ''} in {card['zone']}")


def extra_requests(case_id: str, zone: str, first: dict | None = None) -> list[dict]:
    """Requests in the call beyond its labelled sub-reason, from the reviewed list in data/case_requests.csv
    (written from every script and checked against the transcripts); each is graded on its own (R14, R39)."""
    extra = []
    for row in csv.DictReader((ROOT / "data" / "case_requests.csv").open()):
        if row["case_id"] != case_id:
            continue
        kind, outcome, why = row["kind"], "contained", None
        if kind == "action":
            outcome, why = "handed_off", "action gap"
        elif kind == "earlier slot":
            # Handled when the agent offers the earliest eligible slots; it shares the booking's outcome (a declined
            # or handed-off booking has no slot to improve on). Never promising a waitlist stays a must-not (R44).
            outcome, why = (first["expected_outcome"], first["handoff_reason"]) if first else ("contained", None)
        elif kind.startswith("booking:"):
            service = kind.split(":")[1].replace("hvac_", "")
            if ZONE_CAPACITY.get(zone, {}).get(service, 1) == 0:
                outcome, why = "clean_decline", f"no {service} capacity in {zone} zone"
        extra.append({"request": row["request"], "kind": kind, "expected_outcome": outcome, "handoff_reason": why,
                      "caller_words": row["caller_words"], "reference": row["reference"] or None})
        if kind == "earlier slot":
            extra[-1]["also_correct"] = "a handoff ticket marked 'wants an earlier slot', counted as a handoff"
    return extra


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
        appointment, fixtures = None, []
        if sub in APPOINTMENT_DATES:
            card, appointment, fixtures = _existing_appointment(db, need, APPOINTMENT_DATES[sub], _window_in(text),
                                                                _service_in(call.customer_lines), n, rng)
        else:
            card = caller_card(db, rng=rng, **need)
        if card["synthetic"]:
            fixtures.insert(0, {"table": "customers", "row": {k: card[k] for k in CUSTOMER_KEYS}})
        if reason == "billing":
            fixtures.append(_invoice_fixture(card, " ".join(call.customer_lines), n, paid=sub in ("charged twice", "refund")))
        outcome, why = expected_outcome(reason, sub, card["zone"])
        first_request = {"request": sub, "kind": "sub-reason", "expected_outcome": outcome, "handoff_reason": why}
        requests = [first_request] + extra_requests(template, card["zone"], first_request)
        handed = [r for r in requests if r["expected_outcome"] == "handed_off"]
        if handed:
            outcome, why = "handed_off", handed[0]["handoff_reason"]
        # The reference covers every knowledge request in the call: the sub-reason's, then each listed one.
        keys = ["COMPRESSOR" if "compressor" in text.lower() else sub] + [r["reference"] for r in requests[1:] if r.get("reference")]
        found = [ref for key in dict.fromkeys(keys) if (ref := NAMED_REFERENCES.get(key) or REFERENCES.get(key))]
        reference = " ".join(text for text, _ in found) or None
        spans = [span for _, section in found for span in section]
        case = {
            "case_id": template, "template_id": template, "family": row["family"], "calls_weight": int(row["template_calls"]),
            "reason": reason, "sub_reason": sub, "sample_call_id": call.call_id,
            "caller_script": use_card(call.customer_lines, card), "caller_card": card, "appointment": appointment,
            "fixtures": fixtures, "requests": requests, "expected_outcome": outcome, "expected_handoff_reason": why,
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
