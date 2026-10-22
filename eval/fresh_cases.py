"""The fresh test set: 30 new cases written blind by Codex, one per sub-reason, weighted by its calls.

Every one of the 52 call templates was already used, as the working set or the held-out set, and the held-out set was
seen once it was measured. So the improved agent is measured on new cases: Codex writes one scenario per sub-reason
in a folder holding only the current customer documents, two sample transcripts per sub-reason and its instructions
(eval/fresh_prompt.md), never the agent, its prompts or its results. This module turns each scenario into a case the
harness runs, with a real database customer, the fixtures it needs and its expected outcome under the new scope (the
agent sends payment and autopay links, enrols, upgrades and turns off auto-renew; refunds, disputes and fee waivers
stay with staff). Each case weighs as many calls as its sub-reason has in the 420 transcripts.

The set is frozen after the author's review and then runs only with --fresh-final, unchanged, and at most three times
per agent version (the result is their average and range), so nothing is tuned on it.

Run: python -m eval.fresh_cases write    (Codex writes the scenarios into data/fresh_scenarios/)
     python -m eval.fresh_cases build    (the cases, into data/testset_fresh/)
     python -m eval.fresh_cases freeze   (after the author's review)
     python -m eval.fresh_cases report   (each agent version's average and range, into data/results/fresh_report.json)
"""

import csv
import json
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from app.scheduling.zones import zone_for
from eval.build_cases import (APPOINTMENT_DATES, CUSTOMER_KEYS, KB_TEXT, OUTCOMES, SEED, ZONE_CAPACITY, _existing_appointment,
                              _invoice_fixture, _requirements, _spans, caller_card)
from eval.split import freeze_hash

ROOT = Path(__file__).resolve().parent.parent
FRESH = ROOT / "data" / "testset_fresh"
RAW = ROOT / "data" / "fresh_scenarios"
SPLIT = Path("data") / "fresh_split.json"
PROMPT = ROOT / "eval" / "fresh_prompt.md"
PLACEHOLDERS = {"name", "account", "phone", "address", "city", "amount"}
BATCH = 10
RUNS_PER_AGENT = 3  # the author's choice: each version's result is the average and range of three runs

# The new scope (author's choices, 2026-10-21): payment and autopay links, enrolment, upgrades and cancelling
# auto-renew are the agent's to finish; refunds, disputes and fee waivers stay with a person.
NEW_OUTCOMES = OUTCOMES | {sub: ("contained", None, None) for sub in ("pay an invoice", "upgrade", "autopay", "cancel")}
ACTIONS_DONE = {"payment link", "autopay", "enrol", "upgrade", "cancel auto-renew"}


def slots() -> list[dict]:
    """One slot per sub-reason, most calls first, weighted by its calls in the transcripts."""
    templates = {r["call_id"]: r["template_id"] for r in csv.DictReader((ROOT / "data" / "templates.csv").open())}
    labels = {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}
    counts = Counter(labels[t] for t in templates.values())
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    out = []
    for n, ((reason, sub), calls) in enumerate(ordered, 1):
        if reason == "existing appointment" and sub == "cancel":
            sub = "cancel appointment"
        out.append({"case_id": f"F{n:02d}", "reason": reason, "sub_reason": sub, "calls_weight": calls})
    return out


def expected(reason: str, sub: str, zone: str | None) -> tuple[str, str | None]:
    outcome, why, service = NEW_OUTCOMES[sub]
    if service and zone and ZONE_CAPACITY.get(zone, {}).get(service.replace("hvac_", ""), 1) == 0:
        return "clean_decline", f"no {service.replace('hvac_', '')} capacity in {zone} zone"
    return outcome, why


def requests_for(scenario: dict, zone: str, first: dict | None = None) -> list[dict]:
    """The scenario's second requests, each graded on its own."""
    out = []
    for extra in scenario.get("extra_requests") or []:
        kind, outcome, why = extra["kind"], "contained", None
        if kind.startswith("action:") and kind.split(":", 1)[1] not in ACTIONS_DONE:
            outcome, why = "handed_off", "action gap"
        elif kind == "earlier slot" and first:
            outcome, why = first["expected_outcome"], first["handoff_reason"]
        elif kind.startswith("booking:"):
            service = kind.split(":")[1].replace("hvac_", "")
            if ZONE_CAPACITY.get(zone, {}).get(service, 1) == 0:
                outcome, why = "clean_decline", f"no {service} capacity in {zone} zone"
        out.append({"request": extra["request"], "kind": kind, "expected_outcome": outcome, "handoff_reason": why,
                    "caller_words": extra.get("caller_words", ""), "reference": None})
    return out


def _fill(lines: list[str], card: dict, amount: int | None) -> list[str]:
    values = {"name": card["name"], "account": card["customer_id"], "phone": card["phone"],
              "address": card["service_address"], "city": card["city"], "amount": str(amount) if amount is not None else None}
    out = []
    for line in lines:
        for key in re.findall(r"\{(\w+)\}", line):
            if key not in PLACEHOLDERS or values[key] is None:
                raise ValueError(f"unknown placeholder {{{key}}} in {line!r}")
        out.append(re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], line))
    return out


def _plant_with_overlap(db: sqlite3.Connection, need: dict, day: str, wanted: dict, n: int,
                        rng: random.Random) -> tuple[dict, dict, list[dict]]:
    """The caller's appointment on a new slot for a technician with the skill, even one already busy in an overlapping
    window: used only when no free technician can hold the window the story names. Existing-appointment calls never
    book this slot, and the agent's overlap rule (R50) applies only to slots it books."""
    service = wanted.get("service") or "hvac_repair"
    zone = need["zone"] or next(z for z in sorted(ZONE_CAPACITY) if ZONE_CAPACITY[z].get(service.replace("hvac_", ""), 1))
    card = caller_card(db, rng=rng, **(need | {"zone": zone}))
    skill = {"plumbing": "plumbing", "estimate": "estimate"}.get(service, "hvac")
    (tech,) = db.execute("select tech_id from technicians where home_zone = ? and skills like ? order by tech_id",
                         (card["zone"], f"%{skill}%")).fetchone()
    window, slot_id, appointment_id = wanted.get("window") or "08:00-12:00", 9000 + n, 5000 + n
    slot = {"table": "appointment_slots", "row": {"slot_id": slot_id, "slot_date": day, "window": window, "tech_id": tech,
                                                  "zone": card["zone"], "service_type": service, "status": "booked"}}
    booking = {"table": "appointments", "row": {"appointment_id": appointment_id, "slot_id": slot_id,
                                                "customer_id": card["customer_id"], "issue_description": "test appointment",
                                                "created_at": "2026-10-10", "status": "scheduled", "is_warranty_visit": 0}}
    return card, {"appointment_id": appointment_id, "slot_id": slot_id, "slot_date": day, "window": window,
                  "tech_id": tech, "zone": card["zone"], "source": "planted with overlap"}, [slot, booking]


def build_case(slot: dict, scenario: dict) -> dict:
    sub, number = slot["sub_reason"], int(slot["case_id"][1:])
    if scenario["sub_reason"] != sub:
        raise ValueError(f"{slot['case_id']}: scenario is for {scenario['sub_reason']!r}, not {sub!r}")
    needs = scenario.get("card_needs") or {}
    need = _requirements(sub, "")  # the tier or install window the sub-reason itself requires
    need["zone"] = zone_for(needs["city"]) if needs.get("city") else None
    for key in ("tier", "brand", "install_after", "install_before"):
        need[key] = needs.get(key) or need[key]
    db = sqlite3.connect(SEED)
    rng = random.Random(7000 + number)
    appointment, fixtures = None, []
    if sub in APPOINTMENT_DATES:
        wanted = scenario.get("appointment") or {}
        service = (wanted.get("service") or "hvac_repair").replace("hvac_", "")
        if not need["zone"] and min(ZONE_CAPACITY[z].get(service, 1) for z in ZONE_CAPACITY) == 0:
            # Not every zone offers this service: the customer comes from one that does.
            need["zone"] = rng.choice(sorted(z for z in ZONE_CAPACITY if ZONE_CAPACITY[z].get(service, 1)))
        day = wanted.get("date") or APPOINTMENT_DATES[sub]  # a builder edit may move a day the database cannot hold
        zones = [need["zone"]] if needs.get("city") else [need["zone"]] + sorted(
            z for z in ZONE_CAPACITY if z != need["zone"] and ZONE_CAPACITY[z].get(service, 1))
        for n, zone in enumerate(zones):  # the story names no city: any zone whose technicians are free that day
            try:
                card, appointment, fixtures = _existing_appointment(db, need | {"zone": zone}, day, wanted.get("window"),
                                                                    wanted.get("service"), 100 + number, rng)
                break
            except ValueError:
                if n == len(zones) - 1:
                    card, appointment, fixtures = _plant_with_overlap(db, need, day, wanted, 100 + number, rng)
    else:
        card = caller_card(db, rng=rng, **need)
    if card["synthetic"]:
        fixtures.insert(0, {"table": "customers", "row": {k: card[k] for k in CUSTOMER_KEYS}})
    invoice = scenario.get("invoice")
    amount = int(invoice["amount_dollars"]) if invoice else None
    if invoice:
        fixtures.append(_invoice_fixture(card, f"${amount}", 100 + number, paid=bool(invoice.get("paid"))))
    script = _fill(scenario["caller_script"], card, amount)
    outcome, why = expected(slot["reason"], sub, card["zone"])
    first = {"request": sub, "kind": "sub-reason", "expected_outcome": outcome, "handoff_reason": why}
    requests = [first] + requests_for(scenario, card["zone"], first)
    handed = [r for r in requests if r["expected_outcome"] == "handed_off"]
    if handed:
        outcome, why = "handed_off", handed[0]["handoff_reason"]
    knowledge = scenario.get("knowledge") or {}
    spans = _spans([(e["file"], e["heading"], tuple(e["phrases"])) for e in knowledge.get("evidence") or []])
    return {
        "case_id": slot["case_id"], "template_id": slot["case_id"], "family": slot["case_id"],
        "calls_weight": slot["calls_weight"], "reason": slot["reason"], "sub_reason": sub, "sample_call_id": None,
        "source": "fresh: written blind by Codex", "caller_script": script, "caller_card": card,
        "appointment": appointment, "fixtures": fixtures, "requests": requests, "expected_outcome": outcome,
        "expected_handoff_reason": why, "needs_documents": bool(knowledge.get("reference_answer")),
        "reference_answer": knowledge.get("reference_answer"), "evidence_spans": spans, "must_not": [],
    }


# -- writing the scenarios ----------------------------------------------------------------------------------------

def _sample_calls(slot: dict, per: int = 2) -> list[Path]:
    """Two transcripts of the slot's sub-reason, from different templates where there are several."""
    templates = list(csv.DictReader((ROOT / "data" / "templates.csv").open()))
    labels = {r["template_id"]: (r["reason"], r["sub_reason"]) for r in csv.DictReader((ROOT / "data" / "labels_codex.csv").open())}
    sub = "cancel" if slot["sub_reason"] == "cancel appointment" else slot["sub_reason"]
    chosen, seen = [], set()
    for row in templates:
        if labels[row["template_id"]] == (slot["reason"], sub) and row["template_id"] not in seen:
            chosen.append(ROOT / "call_data" / "call_transcripts" / f"{row['call_id']}.txt")
            seen.add(row["template_id"])
    for row in templates:  # fewer templates than wanted: a second call of the same one
        if len(chosen) >= per:
            break
        path = ROOT / "call_data" / "call_transcripts" / f"{row['call_id']}.txt"
        if labels[row["template_id"]] == (slot["reason"], sub) and path not in chosen:
            chosen.append(path)
    return chosen[:per]


def _case_list(batch: list[dict]) -> str:
    lines = ["## The cases", ""]
    for slot in batch:
        day = APPOINTMENT_DATES.get(slot["sub_reason"])
        when = f"; the appointment is on {date.fromisoformat(day):%A %-d %B %Y}" if day else ""
        lines.append(f"- {slot['case_id']}: {slot['reason']}, sub-reason \"{slot['sub_reason']}\"{when}")
    return "\n".join(lines) + "\n"


def workspace(batch: list[dict], folder: Path) -> None:
    """The only files Codex sees: the current customer documents, sample calls and its instructions."""
    shutil.copytree(KB_TEXT, folder / "docs")
    (folder / "calls").mkdir()
    for slot in batch:
        text = "\n\n----\n\n".join(path.read_text() for path in _sample_calls(slot))
        (folder / "calls" / f"{slot['case_id']}.txt").write_text(text)
    (folder / "TASK.md").write_text(PROMPT.read_text() + "\n" + _case_list(batch))


def _json_array(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text[text.index("["):text.rindex("]") + 1])


def write_scenarios(model: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    all_slots = slots()
    for start in range(0, len(all_slots), BATCH):
        batch, out = all_slots[start:start + BATCH], RAW / f"batch-{start // BATCH + 1}.json"
        if out.exists():
            continue
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            workspace(batch, folder)
            last = folder / "reply.txt"
            prompt = "Read TASK.md in this folder and do what it says. Use only the files in this folder."
            subprocess.run(["codex", "exec", "-m", model, "-s", "read-only", "--ephemeral", "--skip-git-repo-check",
                            "-C", str(folder), "-o", str(last), prompt], stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=1800)
            scenarios = _json_array(last.read_text())
        ids = [s.get("case_id") for s in scenarios]
        if ids != [s["case_id"] for s in batch]:
            raise SystemExit(f"batch {start // BATCH + 1}: Codex returned cases {ids}")
        out.write_text(json.dumps({"model": model, "scenarios": scenarios}, indent=1))
        print(f"wrote {out}")


def build_all() -> list[dict]:
    scenarios = {}
    for path in sorted(RAW.glob("batch-*.json")):
        record = json.loads(path.read_text())
        for scenario in record["scenarios"]:
            scenarios[scenario["case_id"]] = scenario | {"written_by": record["model"]}
    FRESH.mkdir(parents=True, exist_ok=True)
    cases = []
    for slot in slots():
        case = build_case(slot, scenarios[slot["case_id"]])
        case["written_by"] = scenarios[slot["case_id"]]["written_by"]
        (FRESH / f"{slot['case_id']}.json").write_text(json.dumps(case, indent=1))
        cases.append(case)
    return cases


# -- freezing and the guard ---------------------------------------------------------------------------------------

def freeze(root: Path = ROOT) -> str:
    paths = sorted((root / "data" / "testset_fresh").glob("F*.json"))
    record = {"cases": [p.stem for p in paths], "hash": freeze_hash(paths), "frozen_on": date.today().isoformat(),
              "runs": []}
    (root / SPLIT).write_text(json.dumps(record, indent=1))
    return record["hash"]


def refuse(ids: list[str], final: bool, agent_hash: str, root: Path = ROOT) -> None:
    """Fresh cases run only when frozen, with --fresh-final, unchanged since the freeze, and at most three times per
    agent version."""
    if not (root / SPLIT).exists():
        raise SystemExit("refusing: the fresh test set is not frozen yet (python -m eval.fresh_cases freeze)")
    record = json.loads((root / SPLIT).read_text())
    if not final:
        raise SystemExit("refusing to run fresh cases without --fresh-final")
    if freeze_hash([root / "data" / "testset_fresh" / f"{cid}.json" for cid in record["cases"]]) != record["hash"]:
        raise SystemExit("refusing: the fresh cases have changed since they were frozen")
    if sum(run["agent_hash"] == agent_hash for run in record["runs"]) >= RUNS_PER_AGENT:
        raise SystemExit(f"refusing: this agent version ({agent_hash[:8]}) already ran {RUNS_PER_AGENT} times on the fresh set")
    if set(ids) - set(record["cases"]):
        raise SystemExit(f"refusing: {sorted(set(ids) - set(record['cases']))} are not fresh cases")


def record_run(agent_hash: str, folder: str, root: Path = ROOT) -> None:
    record = json.loads((root / SPLIT).read_text())
    record["runs"].append({"agent_hash": agent_hash, "folder": folder, "on": date.today().isoformat()})
    (root / SPLIT).write_text(json.dumps(record, indent=1))


def _contained(attempt: dict) -> bool:
    return bool(attempt.get("all_correct")) and not attempt["handed_off"] and not attempt.get("clean_decline")


def report(weights: dict[str, int] | None = None, root: Path = ROOT) -> dict:
    """Each agent version's fresh runs (measurement decision (D55)): the average and range over its runs of containment
    and the handoff rate, weighted by calls and as plain shares of the cases, from each run's first attempts."""
    weights = weights or {s["case_id"]: s["calls_weight"] for s in slots()}
    record = json.loads((root / SPLIT).read_text())
    out = {}
    for agent in dict.fromkeys(run["agent_hash"] for run in record["runs"]):
        folders = [run["folder"] for run in record["runs"] if run["agent_hash"] == agent]
        rates = {key: [] for key in ("containment_weighted", "handoff_weighted", "containment_cases", "handoff_cases")}
        for folder in folders:
            lines = (root / "data" / "results" / folder / "attempts.jsonl").read_text().splitlines()
            first = [a for a in map(json.loads, lines) if a.get("attempt") == 1]
            share = lambda test, by: 100 * sum(by(a) for a in first if test(a)) / sum(by(a) for a in first)  # noqa: E731
            rates["containment_weighted"].append(share(_contained, lambda a: weights[a["case_id"]]))
            rates["handoff_weighted"].append(share(lambda a: a["handed_off"], lambda a: weights[a["case_id"]]))
            rates["containment_cases"].append(share(_contained, lambda a: 1))
            rates["handoff_cases"].append(share(lambda a: a["handed_off"], lambda a: 1))
        out[agent] = {"runs": folders, **{key: {"average": round(sum(v) / len(v), 1), "low": round(min(v), 1),
                                               "high": round(max(v), 1)} for key, v in rates.items()}}
    return out


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "write":
        from eval.grader import CODEX_MODEL
        write_scenarios(CODEX_MODEL)
    elif command == "build":
        cases = build_all()
        print(f"{len(cases)} cases in {FRESH}; weights {sum(c['calls_weight'] for c in cases)} calls")
    elif command == "freeze":
        print(f"frozen: {freeze()}")
    elif command == "report":
        result = report()
        (ROOT / "data" / "results" / "fresh_report.json").write_text(json.dumps(result, indent=1))
        print(json.dumps(result, indent=1))
    else:
        raise SystemExit("usage: python -m eval.fresh_cases write|build|freeze|report")


if __name__ == "__main__":
    main()
