"""Code checks on every sentence before it is released (R42, R43, R44, R60). A failing sentence is never shown;
the reply stops there and becomes a handoff."""

import csv
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.replies.money_check import touches_money

ROOT = Path(__file__).resolve().parents[2]
RUN = 8  # consecutive words shared with an internal document

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


# A definite promise that a person will follow up; a writer reply has no ticket behind it, so the promise is kept by
# blocking the sentence, which hands the reply off with a ticket. An offer ("I can pass it on if you'd like") is fine.
FOLLOW_UP_PROMISE = re.compile(r"\b(?:a |our )?(?:team member|someone|member of (?:our|the) team|our team|staff)\b[^.]{0,20}"
                               r"\b(?:will|'ll|is going to)\b[^.]{0,10}\b(?:follow up|contact|call|reach out|get back)|"
                               r"\bi(?:'ll| will| have|'ve)\s+pass(?:ed)?\b(?![^.]*\bif you)", re.I)
# The writer's sentence for "the facts do not answer this"; never shown, it ends the reply with a handoff.
NOT_IN_DOCUMENTS = "[NOT IN DOCUMENTS]"
# Any spelling of it in brackets ("[Not in documents]", "[NOT_IN_DOCUMENT]"), the all-caps token without them, or one
# cut off at the end of a sentence ("[NOT IN"), with any punctuation glued to it; "not in the documents" is English.
MARKER = re.compile(r"(?:\[\s*(?i:not[\s_]+in[\s_]+documents?)\s*\]|\bNOT[\s_]+IN[\s_]+DOCUMENTS?\b|"
                    r"\[\s*(?i:not(?:[\s_]+in(?:[\s_]+documents?)?)?)\W*$)[^\w$(]*")
BREAKER_ADVICE = re.compile(r"\breset\w*\b[^.]*\bbreaker|\bbreaker\b[^.]*\breset|\bflip\w*\b[^.]*\bbreaker", re.I)


def check_sentence(sentence: str, reply_so_far: str, burning_mentioned: bool = False) -> CheckResult:
    said = sentence.lower()
    # Never advise resetting a breaker in a conversation that mentions a burning smell (R36, D19).
    if burning_mentioned and BREAKER_ADVICE.search(sentence):
        return CheckResult(False, "breaker_advice")
    for rule, patterns in RULES:
        if any(re.search(p, said) for p in patterns):
            return CheckResult(False, rule)
    if FOLLOW_UP_PROMISE.search(sentence):
        return CheckResult(False, "follow_up_promise")
    # Across the whole reply so far, so a quote split over two sentences is still caught.
    words = _words(f"{reply_so_far} {sentence}")
    if any(tuple(words[i:i + RUN]) in INTERNAL_RUNS for i in range(len(words) - RUN + 1)):
        return CheckResult(False, "internal_text")
    return CheckResult(True)


class CheckedStream:
    """Yields each sentence once it passes; stops at the first failure and records which rule it broke, or at the
    not-in-documents marker, which is never yielded."""

    def __init__(self, sentences: Iterable[str], burning_mentioned: bool = False, money_check=None):
        self._sentences = sentences
        self._burning = burning_mentioned
        self._money_check = money_check  # (sentence, previous) -> bool; every sentence touching money goes to it
        self.blocked_rule: str | None = None
        self.blocked_sentence: str | None = None
        self.not_in_documents = False

    def __iter__(self) -> Iterator[str]:
        so_far = ""
        for sentence in self._sentences:
            if MARKER.search(sentence):  # never released; the rest of the line and later sentences still are
                self.not_in_documents, sentence = True, " ".join(MARKER.sub(" ", sentence).split())
                if not sentence:
                    continue
            result = check_sentence(sentence, so_far, self._burning)
            if result.ok and touches_money(sentence):
                previous = re.split(r"(?<=[.!?])\s+", so_far)[-1] if so_far else ""
                if self._money_check is None or not self._money_check(sentence, previous):
                    result = CheckResult(False, "money promise")  # no checker configured also fails closed
            if not result.ok:
                self.blocked_rule, self.blocked_sentence = result.rule, sentence
                return
            so_far = f"{so_far} {sentence}".strip()
            yield sentence
