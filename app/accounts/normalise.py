"""Normalising what callers say before comparing it with the database: case, spaces, punctuation, dashes."""

import re

STREET_WORDS = {"drive": "dr", "street": "st", "lane": "ln", "road": "rd", "court": "ct", "avenue": "ave",
                "boulevard": "blvd", "trail": "trl", "cove": "cv", "place": "pl", "parkway": "pkwy", "terrace": "ter"}


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def name(text: str) -> str:
    return " ".join(words(text))


def account(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    return f"MHC-{digits}" if len(digits) == 5 else None


def phone(text: str) -> str:
    return re.sub(r"\D", "", text)[-10:]


def street(text: str) -> str:
    """The street part of an address (before any comma), with street-type words shortened."""
    return " ".join(STREET_WORDS.get(w, w) for w in words(text.split(",")[0]))
