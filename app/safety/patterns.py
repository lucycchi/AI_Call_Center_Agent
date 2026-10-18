"""Fixed safety word lists (R34 to R37), written against normalised text: lower case, no punctuation or
apostrophes, and every run of a repeated letter collapsed to one ("smell" is "smel", "eggs" is "egs")."""

import re

# Common misspellings and speech-to-text swaps, applied after normalising.
SWAPS = {r"\bgaz\b": "gas", r"\bc o\b": "co", r"\bsee oh\b": "co", r"\bcarbon monoxyde\b": "carbon monoxide",
         r"\bsparkes\b": "sparks", r"\bbreakers?\b": "breaker"}

DANGER = [r"\bsmel\w*( of| like)?( natural)? gas\b", r"\bgas (smel|leak|odou?r)\w*", r"\bodou?r of( natural)? gas\b", r"\bleak\w* gas\b", r"\broten eg", r"\bmonoxide\b",
          r"\bco (detector|alarm|is going of|going of|beping)", r"\bspark\w*", r"\bsmoke\b", r"\bsmoking\b", r"\bflame\w*",
          r"\bon fire\b"]
BURNING = [r"\bburn\w*", r"\belectrical smel", r"\bmelting smel"]
BREAKER = [r"\bbreaker\b"]
LEAK = [r"\bleak\w*", r"\bflod\w*", r"\bburst\b", r"\bpouring\b", r"\bgushing\b"]
LEAK_SERIOUS = [r"\beverywhere\b", r"\bactive\b", r"\bflod\w*", r"\bburst\b", r"\bpouring\b", r"\bgushing\b", r"\bceiling\b",
                r"\bbasement\b"]
NO_HEAT = [r"\bno heat\b", r"\bheat (is out|stoped|died|quit|not working)", r"\b(furnace|heater) (died|is out|quit)\b"]
COLD = [r"\bfrezing\b", r"\bfroze\w*", r"\bcold\b", r"\bbelow\b", r"\bsnow\w*", r"\bice\b"]
NO_COOLING = [r"\bno (ac|cooling|air)\b", r"\bac (died|is out|stoped|quit|not working)", r"\bnot cooling\b"]
HOT = [r"\bhot\b", r"\bheat\b", r"\bextreme\b", r"\b(9\d|1\d\d) degres\b", r"\bheatwave\b"]
NEGATIONS = {"dont", "not", "no", "nope", "never", "didnt", "isnt", "without"}  # "do not" is caught by "not"
CLAUSE = "|"  # marks a clause boundary; a negation never reaches across one
BOUNDARY_WORDS = r"\b(but|though|although|however|now|also|and now|just)\b"


def normalise(text: str) -> str:
    text = re.sub(r"['’]", "", text.lower())
    text = re.sub(r"\bc\.\s?o\b\.?", "co", text)  # known abbreviations first ("c.o."), never other sentence ends
    text = re.sub(r"[,.;:!?()\n]+", f" {CLAUSE} ", text)
    text = re.sub(BOUNDARY_WORDS, rf"{CLAUSE} \1", text)
    text = re.sub(r"[^a-z0-9|]+", " ", text)
    text = re.sub(r"([a-z])\1+", r"\1", text)
    for pattern, replacement in SWAPS.items():
        text = re.sub(pattern, replacement, text)
    return " ".join(text.split())


def _clause_before(text: str, start: int) -> list[str]:
    """Up to three words before a match, stopping at a clause boundary ("no | but i smel gas" has none)."""
    words = text[:start].split()
    if CLAUSE in words:
        words = words[len(words) - words[::-1].index(CLAUSE):]
    return words[-3:]


def found(patterns: list[str], text: str) -> bool:
    """Any pattern matches without a plain negation in its own clause just before it ("i dont smel gas")."""
    return any(not NEGATIONS & set(_clause_before(text, match.start()))
               for pattern in patterns for match in re.finditer(pattern, text))
