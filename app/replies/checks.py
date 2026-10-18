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
RULES = [
    ("waiver", [rf"{FIRST_PERSON}\s+(?:waive|comp)\b", r"\bwaiv\w* (?:it|that|this|the [\w-]+ fee) for you\b",
                r"\b(?:fee|charge|it|that|this)\b[^.]{0,30}\b(?:will be|has been|is being|gets|was|'ll be)\s+"
                r"(?:waived|removed|dropped|taken off|credited|reversed)",
                r"\b(?:removed|dropped|waived|credited|reversed|took off)\b[^.]{0,20}\b(?:fee|charge)"]),
    ("refund", [rf"{FIRST_PERSON}\s+(?:issued|issue|processed|process|refunded|give you)\b[^.]*\brefund",
                rf"{FIRST_PERSON}\s+refunded\b", r"\byou(?:'ll|’ll| will) (?:get|receive) (?:a |your )?(?:full )?refund\b",
                r"\byour refund (?:has been|is|was) (?:issued|processed|on its way)",
                r"\brefund\b[^.]{0,20}\b(?:has been|was|will be|is being)\s+(?:issued|processed|sent|approved)",
                r"\b(?:issue|process|approve|send)\w* (?:you )?(?:a |your )?(?:full |partial )?refund"]),
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
