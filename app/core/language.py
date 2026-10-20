"""A code backstop for messages the agent cannot read: another language (a non-goal, handed off with an English
note, D47) or nonsense (an unclear request, handed off, R38). The router may miss both."""

import re

WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
FOREIGN = re.compile(r"[¿¡ñáéíóúàèìòùâêîôûãõçäëïöüœß]|[^\x00-ɏ\s\d\W]", re.I)
ENGLISH = set("""a about after again all also am an and any anything appointment are as at ac air back be because been
before being bill book booked broken but by call can cancel charge charged could day did do does doing don't done for
from fix furnace get go good got had has have heat heater heating help hello hey hi how i i'm if in invoice is it it's
just know leak let like look make me membership month morning my need next no not now of off ok okay on one or other
our out over please plumbing price repair reschedule right said schedule see service should so some system tell thank
thanks that the their them then there they this time to today tomorrow tune up visit want was water way we week well
were what when where which who why will with work working would yeah yes you your already anyone around better
came come coming could've down fine first gonna great guess he hear heard her here his home hold house into last
maybe more much never new only really she someone something soon sorry still sure than thing think told too unit
until very wait went""".split())


def unreadable(text: str) -> str | None:
    """'other language', 'nonsense', or None for a message in English (or too short to tell)."""
    words = WORD.findall(text)
    if len(words) < 2:
        return None
    english = sum(w.lower() in ENGLISH for w in words) / len(words)
    if english >= 0.2:
        return None
    if FOREIGN.search(text):
        return "other language"
    if sum(w[0].isupper() for w in words) * 2 >= len(words):  # names and addresses
        return None
    return "other language" if len(words) >= 4 else "nonsense"
