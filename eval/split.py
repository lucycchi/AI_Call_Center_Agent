"""Split templates into a working set (tuning) and a held-out set (final measurement only) (R9).

Whole template families are assigned to one side (template families (D39)), stratified by call reason
with a fixed seed. About 30 percent of each reason's families are held out; a reason with a single
family goes to one side, chosen by the seed.
"""

import csv
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

HELD_OUT_SHARE = 0.3


@dataclass(frozen=True)
class Split:
    working: tuple[str, ...]
    held_out: tuple[str, ...]


def split_templates(rows: list[dict], labels: dict[str, tuple[str, str]], seed: int = 20261016) -> Split:
    family_of = {r["template_id"]: r["family"] for r in rows}
    families_by_reason: dict[str, list[str]] = {}
    for template in sorted(family_of):
        reason = labels[template][0]
        fam = family_of[template]
        if fam not in families_by_reason.setdefault(reason, []):
            families_by_reason[reason].append(fam)
    rng = random.Random(seed)
    held_families = set()
    for reason in sorted(families_by_reason):
        fams = sorted(families_by_reason[reason])
        rng.shuffle(fams)
        count = max(1, round(HELD_OUT_SHARE * len(fams))) if len(fams) >= 2 else (1 if rng.random() < HELD_OUT_SHARE else 0)
        held_families.update(fams[:count])
    working = tuple(sorted(t for t, f in family_of.items() if f not in held_families))
    held = tuple(sorted(t for t, f in family_of.items() if f in held_families))
    return Split(working, held)


def write_split_counts(rows: list[dict], labels: dict, split: Split, out: Path) -> None:
    calls = {}
    for r in rows:
        calls[r["template_id"]] = int(r["template_calls"])
    held = set(split.held_out)
    table: dict[str, dict] = {}
    for template, n in calls.items():
        reason = labels[template][0]
        entry = table.setdefault(reason, {"reason": reason, "corpus_calls": 0, "corpus_templates": 0, "working_calls": 0,
                                          "working_templates": 0, "held_out_calls": 0, "held_out_templates": 0})
        side = "held_out" if template in held else "working"
        entry["corpus_calls"] += n
        entry["corpus_templates"] += 1
        entry[f"{side}_calls"] += n
        entry[f"{side}_templates"] += 1
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(next(iter(table.values()))))
        writer.writeheader()
        for reason in sorted(table, key=lambda r: -table[r]["corpus_calls"]):
            writer.writerow(table[reason])


def freeze_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
