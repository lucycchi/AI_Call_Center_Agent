"""The money check knows every published term and releases a plain statement of them without the model (D43)."""
import json
from pathlib import Path

import pytest

from app.replies.money_check import PUBLISHED_TERMS, MoneyCheck, published_only

ROWS = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / "data" / "eval" / "money_sentences.jsonl").open()]


class NoModel:
    """A client that must not be called: any call fails, which the money check turns into a block."""
    def __init__(self):
        self.messages = self
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise RuntimeError("the model was asked")


@pytest.mark.parametrize("term", [
    "$189", "$16.99", "12-month minimum", "$99", "$269", "$80", "$500", "two seasonal tune-ups", "priority scheduling",
    "$89", "waived on all service calls", "15% off all repairs (parts and labor)", "no after-hours dispatch fee",
    "filter-change notifications", "water heater flush and inspection", "whole-home plumbing inspection",
    "15% off plumbing repairs", "$500 off any full system replacement", "auto-renew", "60 days",
    "remaining balance of the minimum term", "$149", "$199", "$129", "$49", "$119", "1-year labor warranty"])
def test_the_published_terms_cover_the_membership_overview_and_fee_schedule(term):
    assert term in PUBLISHED_TERMS


def test_the_published_benefit_sentences_blocked_in_quick_runs_are_labelled_to_be_released():
    rows = [r for r in ROWS if r.get("source") == "quick-run block"]
    assert len(rows) >= 15 and all(r["expected"] == "pass" for r in rows)
    near = [r["sentence"] for r in ROWS if r.get("source") == "added with the quick-run blocks"]
    assert "I'll waive the $89 fee for you since you're joining." in near
    assert all(r["expected"] == "block" for r in ROWS if r.get("source") == "added with the quick-run blocks")


# A sentence with words outside the plain statement vocabulary ("which ...") goes to the model instead (security review).
@pytest.mark.parametrize("row", [r for r in ROWS if r.get("source") == "quick-run block" and not r["sentence"].startswith("It ")
                                 and " which " not in r["sentence"]],
                         ids=lambda r: r["sentence"][:50])
def test_a_plain_statement_of_published_terms_is_released_without_the_model(row):
    client = NoModel()
    assert MoneyCheck(client)(row["sentence"], row["previous"]) is True and client.calls == 0


@pytest.mark.parametrize("row", [r for r in ROWS if r["expected"] == "block"], ids=lambda r: r["sentence"][:50])
def test_no_labelled_promise_is_released_by_the_code_pre_check(row):
    assert not published_only(row["sentence"])
    assert MoneyCheck(NoModel())(row["sentence"], row["previous"]) is False  # the model failing still blocks


@pytest.mark.parametrize("sentence", [
    "Comfort Club members get 15% off all repairs, and I can book that for you.",
    "Your next tune-up is included with Comfort Club.", "We'll waive the $89 diagnostic fee for Comfort Club members.",
    "Comfort Club members get a prorated refund within the first 60 days.", "Comfort Club members get 20% off all repairs.",
    "Comfort Club members get the $49 late-cancellation fee waived.", "Members get holiday dispatch free.",
    "Comfort Club members get 15% off all repairs, just this once.", "Comfort Club members get 15% off all repairs and installations.",
])
def test_anything_beyond_a_plain_published_statement_goes_to_the_model(sentence):
    assert not published_only(sentence)


def test_a_sentence_about_it_is_released_in_code_only_when_the_sentence_before_names_the_plan():
    sentence = next(r["sentence"] for r in ROWS if r.get("source") == "quick-run block" and r["sentence"].startswith("It "))
    assert published_only(sentence, "Standard is $189 per year per system or $16.99 per month.")
    assert not published_only(sentence, "Your visit is booked for Monday.") and not published_only(sentence, "")


# -- Security review: the code pre-check is a full-sentence allowlist, never a loophole -----------------------------

@pytest.mark.parametrize("sentence", [
    "Comfort Club members get 15% off all repairs (parts and labor), so this repair will be 15% off.",
    "Standard members get the $89 diagnostic fee waived on all service calls, which applies to today's visit.",
    "Comfort Club members get the $89 diagnostic fee waived on all service calls, effective immediately.",
    "Plus members get 15% off plumbing repairs, and that covers this job.",
    "Comfort Club members get 15% off all repairs (parts and labor) starting now.",
])
def test_published_terms_applied_to_this_caller_still_go_to_the_model(sentence):
    from app.replies.money_check import published_only
    assert not published_only(sentence, "")
