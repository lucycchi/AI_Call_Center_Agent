import csv
import re
from pathlib import Path

import pytest

from app.safety.check import breaker_advice_allowed, check
from app.safety.replies import fixed_reply

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("text", [
    "I smell gas near my furnace", "my CO detector is going off", "My carbon monoxide detector is going off.",
    "there are sparks coming from the outdoor unit", "smells like rotten eggs", "i smel gass",
    "burning smell and the breaker tripped", "there's smoke coming out of the furnace", "I see flames by the water heater",
    "SMELL GAS!!!", "i think theres a gas leak"])
def test_danger(text):
    assert check(text, []).kind == "danger"


def test_burning_then_tripped_breaker_in_a_later_message_is_danger():
    assert check("and now the breaker tripped", ["I smell something burning from the vents"]).kind == "danger"


@pytest.mark.parametrize("text", ["I smell something burning from the vents", "there's a burnt smell when the heat runs",
                                  "smells like burning plastic"])
def test_burning(text):
    assert check(text, []).kind == "burning"


@pytest.mark.parametrize("text", ["water is leaking everywhere, active leak", "no heat and it's freezing",
                                  "the AC died and it's 100 degrees inside", "a pipe burst and the basement is flooding"])
def test_urgent(text):
    assert check(text, []).kind == "urgent"


@pytest.mark.parametrize("text", ["I don't smell gas, just want a tune-up", "I do not smell anything burning",
                                  "my gas furnace won't kick on", "I need my annual tune-up", "no smoke, it just won't start",
                                  "the AC runs but the air is warm"])
def test_clear(text):
    assert check(text, []).kind == "clear"


def test_an_ambiguous_message_gets_the_more_serious_class():
    assert check("burning smell and water leaking everywhere", []).kind == "burning"
    assert check("sparks and an active leak", []).kind == "danger"


def joined(kind, situation=""):
    return " ".join(fixed_reply(kind, situation))


def test_danger_reply():
    reply = joined("danger")
    for phrase in ("leave your home", "911", "gas utility", "from outside", "Don't flip switches",
                   "open windows near the furnace", "restart equipment"):
        assert phrase in reply, phrase


def test_burning_reply():
    reply = joined("burning").lower()
    for phrase in ("turn the system off at the thermostat", "don't reset breakers", "leave the home if there is smoke"):
        assert phrase in reply, phrase


def test_urgent_replies_fit_the_situation():
    assert "turn off the water supply" in joined("urgent", "water is leaking everywhere")
    assert "heat" in joined("urgent", "no heat and it's freezing")
    assert "cool" in joined("urgent", "the AC died and it's 100 degrees inside")


def test_breaker_advice_is_never_allowed_after_a_burning_smell():
    assert breaker_advice_allowed(["I smell something burning"]) is False
    assert breaker_advice_allowed(["my AC is warm"]) is True
    assert "reset" not in joined("burning").lower().replace("don't reset breakers", "")


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def test_fixed_replies_never_copy_eight_words_of_an_internal_document():
    internal = [row["path"] for row in csv.DictReader((ROOT / "data" / "document_list.csv").open()) if row["audience"] == "internal"]
    grams = set()
    for path in internal:
        words = _words((ROOT / "call_data" / "knowledge_base" / path).read_text())
        grams |= {tuple(words[i:i + 8]) for i in range(len(words) - 7)}
    for kind, situation in (("danger", ""), ("burning", ""), ("urgent", "leak"), ("urgent", "no heat"), ("urgent", "no cooling")):
        words = _words(joined(kind, situation))
        assert not {tuple(words[i:i + 8]) for i in range(len(words) - 7)} & grams, (kind, situation)


# Milestone 3 gate fixes.

@pytest.mark.parametrize("text", ["No, but I smell gas", "I'm not sure, I smell gas", "not really. i smell gas now",
                                  "I smell natural gas near the furnace", "There is a gas odor in the basement",
                                  "smells of natural gas", "nope, but there's smoke coming out of the vent"])
def test_danger_is_not_cancelled_by_a_negation_in_another_clause_and_gas_synonyms_count(text):
    assert check(text, []).kind == "danger"


@pytest.mark.parametrize("text", ["my natural gas furnace won't light", "I don't smell gas, just want a tune-up",
                                  "no gas smell, it just clicks"])
def test_a_gas_appliance_or_a_negated_smell_is_not_danger(text):
    assert check(text, []).kind == "clear"
