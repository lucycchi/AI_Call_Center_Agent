"""Group transcripts into templates: calls with the same request and the same staff outcome
once names, numbers and filler words are removed (R1). A reviewed merge list then joins
near-identical groups.

Run: python -m pipeline.templates   (writes data/templates.csv)
"""

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

from pipeline.transcripts import Call, load_transcripts

ROOT = Path(__file__).resolve().parent.parent
FILLER_WORDS = re.compile(r"\b(um+|uh+|so|yeah|okay|ok|hi|hey|hello|like|you know)\b")

# Openings that carry no request (line noise, small talk), skipped when finding the request.
FILLER_OPENINGS = ("sorry you cut out", "sorry i m driving", "can you hear me", "hold on my dog",
                   "one sec", "sorry one second")

# Generic wrappers around the caller's actual issue: "I need to schedule a service call. <issue>".
WRAPPERS = (r"^i need to schedule a service call ", r"^i m calling to book a repair ",
            r" and i d to get someone out to look at it$", r" what s the soonest you can get a tech out$")

# Staff outcome patterns, checked in order; the first match names the outcome.
OUTCOMES = (
    ("safety", r"leave the house right now"),
    ("waitlist", r"waitlist"),
    ("callback", r"billing supervisor|service manager|refund requests go to|someone will reach out|estimator call you"),
    ("redirect", r"careers page|this is meridian home comfort heating and air"),
    ("booked", r"you re booked|book a warranty diagnostic|book that as a warranty recall|advisor available"),
    ("moved", r"\bmoved\b"),
    ("cancelled", r"no cancellation fee"),
    ("confirmed", r"yes (monday|tuesday|wednesday|thursday|friday) .* for a"),
    ("action", r"auto renew is off|you re upgraded|payment link|secure link to add a card|sending that to the email|it ll come by text"),
    ("late_tech", r"on his way|previous job ran long"),
)


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = FILLER_WORDS.sub(" ", text)
    text = re.sub(r"\d+", "#", text)
    text = re.sub(r"[^a-z#: ]", " ", text)
    text = re.sub(r"(?<!#):|:(?!#)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


NAME_PHRASES = re.compile(r"\b(this is|my name is) [a-z]+ [a-z]+\b ?")


def request_of(call: Call) -> str:
    for line in call.customer_lines:
        norm = NAME_PHRASES.sub(" ", normalise(line)).strip()
        if norm and not norm.startswith(FILLER_OPENINGS):
            for wrapper in WRAPPERS:
                norm = re.sub(wrapper, " ", norm).strip()
            return norm
    return ""


def outcome_of(call: Call) -> str:
    staff = normalise(" ".join(call.agent_lines))
    for name, pattern in OUTCOMES:
        if re.search(pattern, staff):
            return name
    return "answered"


def _template_id(key: str) -> str:
    return "T" + hashlib.sha1(key.encode()).hexdigest()[:8]


def _read_merges(merges: Path) -> dict[str, str]:
    if not merges.exists():
        return {}
    return {row["from_template"]: row["to_template"] for row in csv.DictReader(merges.open())}


def group_templates(calls: list[Call], merges: Path) -> dict[str, str]:
    merge_map = _read_merges(merges)
    groups = {}
    for call in calls:
        template = _template_id(f"{request_of(call)}|{outcome_of(call)}")
        while template in merge_map:
            template = merge_map[template]
        groups[call.call_id] = template
    return groups


def families(calls: list[Call], groups: dict[str, str]) -> dict[str, str]:
    """Each waitlist template belongs to the family of its booking twin (template families (D39));
    every other template is its own family. Families stay on one side of the test split."""
    by_key = {}
    for call in calls:
        by_key.setdefault((request_of(call), outcome_of(call)), groups[call.call_id])
    family = {}
    for (request, outcome), template in by_key.items():
        twin = by_key.get((request, "booked")) if outcome == "waitlist" else None
        family[template] = twin or template
    return family


def main() -> None:
    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    groups = group_templates(calls, ROOT / "data" / "template_merges.csv")
    sizes = Counter(groups.values())
    family = families(calls, groups)
    out = ROOT / "data" / "templates.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["call_id", "template_id", "template_calls", "family", "request", "outcome"])
        for call in calls:
            template = groups[call.call_id]
            writer.writerow([call.call_id, template, sizes[template], family[template], request_of(call), outcome_of(call)])
    print(f"{len(calls)} calls in {len(sizes)} templates and {len(set(family.values()))} families -> {out}")


if __name__ == "__main__":
    main()
