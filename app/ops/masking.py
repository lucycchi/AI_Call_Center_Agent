"""Mask phone numbers, emails and street addresses before anything is logged (R73). Names and account
numbers are kept, so staff can still find the caller."""

import re

STREET_TYPES = r"(?:st|street|ln|lane|dr|drive|rd|road|ct|court|ave|avenue|way|blvd|boulevard|pass|trl|trail|ter|terrace|pl|place|loop|pkwy|parkway|cv|cove|cir|circle)"
# Words that follow a number but never name a street ("15 years old way past warranty", "2 systems at my place").
NOT_STREET_NAMES = (r"(?:years?|months?|weeks?|days?|hours?|minutes?|times?|systems?|units?|people|kids|dogs|degrees?|"
                    r"percent|of|at|in|on|to|for|my|your|our|is|was|are|more|less)")
# A card number (13 to 19 digits, spaced or not) is masked first, so no run of it is mistaken for a phone number; card
# numbers are never taken in chat, but one a caller types is never stored either (actions decision (D54)).
CARD = re.compile(r"(?<![\w-])\d(?:[ .-]?\d){12,18}(?![\w-])")  # spaces, dots or hyphens between digits
# A bank account or routing number: a bare run of 9 to 17 digits, masked after phone numbers (review finding S1).
BANK = re.compile(r"(?<![\w.-])\d{9,17}(?![\w-])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w-])\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
STREET = re.compile(rf"\b\d{{1,6}} (?!{NOT_STREET_NAMES}\b)[A-Za-z]+(?: [A-Za-z]+){{0,3}} {STREET_TYPES}\b\.?", re.I)
PATTERNS = [(CARD, "[card number]"), (EMAIL, "[email]"), (PHONE, "[phone]"), (BANK, "[bank number]"), (STREET, "[street]")]


def mask(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
