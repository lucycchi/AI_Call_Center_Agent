"""Code checks on every sentence before it is released (R42, R43, R44, R60). A failing sentence is never shown;
the reply stops there and becomes a handoff."""

import csv
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = 8  # consecutive words shared with an internal document

FIRST_PERSON = r"\b(?:i|we)(?:'ll|’ll|'ve|’ve| will| can| could| have| am going to| are going to| would)?"
MONEY = r"(?:fee|charge|charges|bill|account|invoice|\$\d)"
# A passive "is waived" or "is credited" is a published rule only when the sentence ties it to one.
PUBLISHED = re.compile(r"\b(?:members?|comfort club|plus|toward the repair|if you approve|automatically|pending authori[sz]ation|"
                       r"drops? off|within \d+|business days|prorated)\b", re.I)
PASSIVE_WAIVER = re.compile(r"\b(?:is|are|will be|has been|have been|is being|gets|get|was|'ll be|’ll be)\s+"
                            r"(?:waived|removed|dropped|taken off|credited|reversed|refunded)\b", re.I)
RULES = [
    ("waiver", [rf"{FIRST_PERSON}\s+(?:waive|comp|drop|remove|credit|reverse|knock|take)\w*\b[^.]*{MONEY}",
                rf"{FIRST_PERSON}\s+(?:waive|comp)\b",
                r"\bwaiv\w* (?:it|that|this|the [\w-]+ fee) for you\b",
                r"\b(?:i|we)(?:'ve|’ve| have)\s+(?:removed|dropped|waived|credited|reversed|taken off)\b"]),
    ("refund", [rf"{FIRST_PERSON}\s+refund\w*\b", rf"{FIRST_PERSON}\s+(?:issued|issue|processed|process|give you|send|sent)\b[^.]*\brefund",
                r"\byou(?:'ll|’ll| will) (?:get|receive) (?:a |your )?(?:full )?refund\b",
                r"\b(?:your |a |the )?refund (?:has been|is|was|will be|is being) (?:issued|processed|sent|approved|on its way)"]),
    ("firm_total", [r"\bexactly \$\d", r"\b(?:the|your) total (?:will|would) (?:be|come to)\b",
                    r"\b(?:your|the) (?:repair|job|fix|bill)\b[^.]{0,30}\bwill (?:cost|be|come to)\b[^.]{0,10}\$[\d,]+(?:\.\d\d)?(?! ?(?:to|-|–))"]),
    ("discount", [rf"{FIRST_PERSON}\s+(?:give|offer|get) you (?:a |an extra )?discount",
                  r"\b(?!15\b)\d+ ?(?:%|percent) (?:off|discount)\b",
                  r"\bqualify for (?:a |an |the )?(?!15)(?:\w+ )?discount"]),
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
    if PASSIVE_WAIVER.search(said) and re.search(MONEY, said) and not PUBLISHED.search(said):
        return CheckResult(False, "refund" if "refunded" in said else "waiver")
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
