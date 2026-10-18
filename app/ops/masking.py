"""Mask phone numbers, emails and street addresses before anything is logged (R73). Names and account
numbers are kept, so staff can still find the caller."""

import re

STREET_TYPES = r"(?:st|street|ln|lane|dr|drive|rd|road|ct|court|ave|avenue|way|blvd|boulevard|pass|trl|trail|ter|terrace|pl|place|loop|pkwy|parkway|cv|cove|cir|circle)"
PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r"(?<![\w-])\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"), "[phone]"),
    (re.compile(rf"\b\d{{1,6}}(?: [A-Za-z]+){{1,4}} {STREET_TYPES}\b\.?", re.I), "[street]"),
]


def mask(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
