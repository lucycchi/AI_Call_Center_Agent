"""A code backstop for a message in another language (a non-goal, handed off with an English note, D47), which the
router may miss. Only strong signs count, since a false alarm hands off an ordinary English caller; accented
letters alone (José García) do not."""

import re

from app.flows.identify import has_identifier

WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
STRONG = re.compile(r"[¿¡]|[^\x00-ɏ\s\d\W]")  # inverted punctuation or a non-Latin script
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
FUNCTION_WORDS = set("""el los las mi por para que pueden puede usted está es una con del je vous nous est pas une mon
votre ne les des avec""".split())
ENGLISH = set("""a about after again all also am an and any anything appointment are as at ac air back be because been
before being bill book booked broken but by call can cancel charge charged could day did do does doing don't done for
from fix furnace get go good got had has have heat heater heating help hello hey hi how i i'm if in invoice is it it's
just know leak let like look make me membership month morning my need next no not now of off ok okay on one or other
our out over please plumbing price repair reschedule right said schedule see service should so some system tell thank
thanks that the their them then there they this time to today tomorrow tune up visit want was water way we week well
were what when where which who why will with work working would yeah yes you your already anyone around better
came come coming could've down fine first gonna great guess he hear heard her here his home hold house into last
maybe more much never new only really she someone something soon sorry still sure than thing think told too unit
until very wait went works um uh hmm account number ballpark""".split())


def english_words(text: str) -> int:
    return sum(w.lower() in ENGLISH for w in WORD.findall(text))


def other_language(text: str) -> bool:
    """Inverted punctuation, a non-Latin script, or two Spanish or French function words with little English,
    and never a message with an email address or account details in it."""
    if EMAIL.search(text) or has_identifier(text):
        return False
    if STRONG.search(text):
        return True
    words = WORD.findall(text)
    return sum(w.lower() in FUNCTION_WORDS for w in words) >= 2 and english_words(text) < 0.2 * len(words)
