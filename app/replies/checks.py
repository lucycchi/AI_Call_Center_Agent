"""Code checks on every sentence before it is released (R42, R43, R44, R60). A failing sentence is never shown;
the reply stops there and becomes a handoff."""

import csv
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = 8  # consecutive words shared with an internal document

# Deny by default (R42): a sentence offering any concession on money is blocked unless the concession is one of the
# published terms below. Blocks are logged and counted, so over-blocking is visible and cheap; a missed promise is not.
CONCESSIONS = [
    ("waiver", r"\bwaiv\w*"), ("waiver", r"\bcomp(?:ed|ing)?\b"), ("waiver", r"\bno charge\b"), ("waiver", r"\bon us\b"),
    ("waiver", r"\b(?:drop|remove|take|knock|reverse|zero)\w*\b[^.]{0,25}\b(?:fee|charge)s?\b[^.]{0,10}\boff\b"),
    ("waiver", r"\b(?:drop|remov|revers|zero)\w*\b[^.]{0,15}\b(?:the |your |that |this )?(?:[\w-]+ )?(?:fee|charge)s?\b"),
    ("waiver", r"\b(?:fee|charge)s?\b[^.]{0,20}\b(?:taken off|removed|dropped|reversed|zeroed)\b"),
    ("waiver", r"\bcredit\w*"), ("refund", r"\brefund\w*"),
    ("discount", r"\bdiscount\w*"), ("discount", r"\b\d+ ?(?:%|percent) off\b"), ("discount", r"\$\d[\d,]* off\b"),
]
# Wording that makes a concession personal ("for you", "this time") is never a published term.
PERSONAL = re.compile(r"\b(?:for you|this time|this once|just this|today|as a courtesy|since you'?ve|i'?ll|i will|i can|we'?ll|"
                      r"we will|we can|i'?ve|we'?ve|let me|you'?ll get|you will get)\b", re.I)
MEMBER = re.compile(r"\b(?:members?|comfort club|plus)\b", re.I)
APPROVED = {
    # The diagnostic fee and after-hours dispatch are waived for Comfort Club members (fee schedule, FAQ, membership).
    "waiver": [lambda t: re.search(r"\b(?:diagnostic|after-hours|dispatch)\b", t) and re.search(r"\bwaiv", t)
               and (MEMBER.search(t) or not re.search(r"\byour?\b", t)),
               # The diagnostic fee is credited toward a repair approved on the same visit; a $500 replacement credit.
               lambda t: re.search(r"\bcredit\w*\b[^.]{0,30}\btoward\w* (?:the )?repair", t),
               lambda t: re.search(r"\bcredit\b", t) and re.search(r"\$(?:500|0)\b", t)],
    "refund": [lambda t: re.search(r"\bprorat|\bnon-refundable\b|\brefund requests? (?:are|is) (?:handled|reviewed)", t)],
    "discount": [lambda t: re.search(r"\b(?:15|0) ?(?:%|percent)|\$500 off|\bmember discounts?\b|\bdiscount applies to\b", t)],
}


def _concession(sentence: str, previous: str) -> str | None:
    """The rule a sentence breaks by offering an unapproved concession, judged with the sentence before it
    (so "It will be waived for you." after "The diagnostic fee is $89." is still caught)."""
    said = sentence.lower()
    context = f"{previous.lower()} {said}"
    for rule, pattern in CONCESSIONS:
        if re.search(pattern, said):
            if PERSONAL.search(said) or not any(approve(context) for approve in APPROVED[rule]):
                return rule
    return None


FIRST_PERSON = r"\b(?:i|we)(?:'ll|’ll|'ve|’ve| will| can| could| have| am going to| are going to| would)?"
RULES = [
    ("firm_total", [r"\bexactly \$\d", r"\b(?:the|your) total (?:will|would) (?:be|come to)\b",
                    r"\b(?:your|the) (?:repair|job|fix|bill)\b[^.]{0,30}\bwill (?:cost|be|come to)\b[^.]{0,10}\$[\d,]+(?:\.\d\d)?(?! ?(?:to|-|–))"]),
    ("waitlist", [r"\b(?:put|add|place|sign)\w* you (?:on|to) (?:the |a |our )?(?:wait ?list|waiting list)",
                  r"\byou(?:'re|’re| are) on (?:the |a |our )?(?:wait ?list|waiting list)"]),
]


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    rule: str | None = None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", ""))


def _internal_runs() -> set[tuple[str, ...]]:
    runs = set()
    for row in csv.DictReader((ROOT / "data" / "document_list.csv").open()):
        if row["audience"] == "internal":
            words = _words((ROOT / "call_data" / "knowledge_base" / row["path"]).read_text())
            runs |= {tuple(words[i:i + RUN]) for i in range(len(words) - RUN + 1)}
    return runs


INTERNAL_RUNS = _internal_runs()


BREAKER_ADVICE = re.compile(r"\breset\w*\b[^.]*\bbreaker|\bbreaker\b[^.]*\breset|\bflip\w*\b[^.]*\bbreaker", re.I)


def check_sentence(sentence: str, reply_so_far: str, burning_mentioned: bool = False) -> CheckResult:
    said = sentence.lower()
    # Never advise resetting a breaker in a conversation that mentions a burning smell (R36, D19).
    if burning_mentioned and BREAKER_ADVICE.search(sentence):
        return CheckResult(False, "breaker_advice")
    for rule, patterns in RULES:
        if any(re.search(p, said) for p in patterns):
            return CheckResult(False, rule)
    previous = re.split(r"(?<=[.!?])\s+", reply_so_far.strip())[-1] if reply_so_far.strip() else ""
    rule = _concession(sentence, previous)
    if rule:
        return CheckResult(False, rule)
    # Across the whole reply so far, so a quote split over two sentences is still caught.
    words = _words(f"{reply_so_far} {sentence}")
    if any(tuple(words[i:i + RUN]) in INTERNAL_RUNS for i in range(len(words) - RUN + 1)):
        return CheckResult(False, "internal_text")
    return CheckResult(True)


class CheckedStream:
    """Yields each sentence once it passes; stops at the first failure and records which rule it broke."""

    def __init__(self, sentences: Iterable[str], burning_mentioned: bool = False):
        self._sentences = sentences
        self._burning = burning_mentioned
        self.blocked_rule: str | None = None
        self.blocked_sentence: str | None = None

    def __iter__(self) -> Iterator[str]:
        so_far = ""
        for sentence in self._sentences:
            result = check_sentence(sentence, so_far, self._burning)
            if not result.ok:
                self.blocked_rule, self.blocked_sentence = result.rule, sentence
                return
            so_far = f"{so_far} {sentence}".strip()
            yield sentence
