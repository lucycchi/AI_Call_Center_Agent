"""A model check on every reply sentence that touches money (R42, D43).

Code cannot list every way to promise a waiver, refund or discount ("we won't charge you", "it's on us"), so each
sentence about money is put to Claude Haiku 5.5 with the published terms and the sentence before it. The check
fails closed: a refusal, an error, a timeout or an unreadable answer blocks the sentence. A plain statement of published
member benefits or plan prices, with no favour or promise wording, is released in code first (published_only)."""

import json
import logging
import re

from app.config import SETTINGS
from app.core import deadline

log = logging.getLogger("meridian.money_check")

MONEY = re.compile(r"[$%]|\b(fees?|charges?|charged|charging|costs?|price[sd]?|pricing|free|refund\w*|credit\w*|discount\w*|"
                   r"waiv\w*|owe[sd]?|bill\w*|invoice\w*|pay\w*|money|dollars?|percent|cheaper|reimburs\w*|quotes?|"
                   r"on the house|on us|no charge|reduc\w*|lower)\b", re.I)

# The published money terms, from the current customer documents (Comfort Club overview, 2026 fee schedule, FAQ,
# catalog, warranty terms).
PUBLISHED_TERMS = """- Diagnostic visit $89 for non-members, credited toward a repair approved on the same visit; waived for Comfort Club and Plus members.
- After-hours emergency dispatch $149 for non-members; waived for members. Holiday emergency dispatch $199.
- Seasonal tune-up $129 per system for non-members; included twice a year for members.
- Late cancellation or reschedule inside 24 hours: $49 for everyone, members too; free more than 24 hours before the window. No-show $89 for non-members, $0 for members.
- Water heater flush $119 for non-members and Standard members; included for Plus members.
- Comfort Club (Standard): $189 per year per system, or $16.99 per month (monthly plans have a 12-month minimum
  commitment); each additional system at the same address $99 per year (Standard and Plus).
  Standard includes: two seasonal tune-ups per year (one cooling, one heating);
  priority scheduling (members are booked ahead of non-members); the diagnostic fee ($89) waived on all service calls;
  15% off all repairs (parts and labor); no after-hours dispatch fee on emergency calls;
  annual reminder and filter-change notifications; $500 off any full system replacement.
- Comfort Club Plus: $269 per year per system (no monthly option). Everything in Standard, plus:
  an annual water heater flush and inspection, an annual whole-home plumbing inspection, 15% off plumbing repairs (Plus only; Standard gets 0%
  off plumbing), and $500 off any full system replacement (Standard members also receive this; listed in the fee
  schedule as a "$500 full system replacement credit", also said as "$500 off a replacement" or "a new system").
- The repair discount applies to parts and labor on residential HVAC repairs.
- Annual plans bill once on the enrollment date and auto-renew each year on the same date; monthly plans bill on the
  enrollment day each month. A renewal reminder email goes out 30 days before renewal. Existing members keep their
  enrollment price until their next renewal date, when the current price applies.
- Members may cancel auto-renewal at any time before the renewal date. Annual plans: a prorated refund within the first
  60 days only if no tune-up has been performed in the current term; non-refundable once a tune-up has been performed.
  Monthly plans cancelled before the 12-month minimum are charged the remaining balance of the minimum term.
- Standard members may upgrade to Plus at any time; the difference ($80) is prorated for the months remaining in the term.
- Memberships transfer to a new homeowner at the same service address, not to a new address.
- Free in-home replacement estimate. Price-book and catalog ranges are typical prices; the technician confirms the final price on site.
- A duplicate charge is usually a pending authorization that drops off in 3 to 5 business days.
- No diagnostic fee when the technician confirms a repair is covered by warranty. Financing on repairs over $1,000.
- Repairs carry a 1-year labor warranty on the part repaired: if the same part fails within a year, the return visit and
  labor are free (parts too if Meridian supplied them). Full system installations have a 2-year labor warranty, 5 years
  if the customer was a member at installation; manufacturer parts warranties are separate and cover parts only.
- Card or ACH by a secure payment link; no card numbers by phone, no checks or cash to technicians."""
RULES = f"""You check one sentence an HVAC company's customer assistant is about to send, before the caller sees it.
Answer whether the sentence promises or grants the caller anything about money beyond the published terms below:
a waiver, refund, credit, discount, reduced or free price, a firm repair total, or not charging a fee that applies.
Stating a published term, quoting a published price or range, explaining a charge, or saying a team member will
review something is not a promise. A member benefit stated as a member benefit ("members get 15% off repairs",
"you qualify for the 15% member discount") is a published term.
It is a promise when:
- something is waived, free, credited or refunded that the published terms do not waive, free, credit or refund
  (the $49 late-cancellation fee is never waived; holiday dispatch is never waived);
- a member-only benefit is stated as the caller's without saying it is because they are a member
  ("your next tune-up is free");
- it is framed as a favour for this caller ("for you", "this time", "just this once", "today").
Use the previous sentence to understand what "it" or "that" refers to.

Published terms:
{PUBLISHED_TERMS}"""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["promises_beyond_published_terms"],
          "properties": {"promises_beyond_published_terms": {"type": "boolean"}}}


# Promises worded as a personal favour are blocked in code, before the model is asked.
FAVOUR = re.compile(r"\b(?:waiv\w*|free|refund\w*|credit\w*|no charge|on us|on the house)\b[^.,;]{0,30}\b(?:for you|this time|"
                    r"this once|just this|today)\b|\b(?:for you|this time|this once)\b[^.,;]{0,30}\b(?:waiv\w*|free|refund\w*)",
                    re.I)


def touches_money(sentence: str) -> bool:
    return bool(MONEY.search(sentence))


# A plain statement of published member benefits and plan prices is released in code, without the model (D43): every
# money mention in it must be one of these published phrases, it must name a plan (or follow a sentence that does), and
# it must not speak to or for anyone ("I", "we", "you"), name a favour, or touch refunds, late or holiday fees,
# non-member terms or anything else. Every other money sentence still goes to the model and fails closed.
_END = r"(?=\s*(?:[,.;:)]|$|\band (?:(?:an?|the|no|two|priority|annual)\b|\$|15%)|\bwhich\b|\bper\b|\bfor (?:Comfort|Standard|Plus|members)\b))"
_DIAGNOSTIC = (r"(?:(?:the |a )?\$89 diagnostic fee (?:waived|waiver)|(?:a )?waiver of the \$89 diagnostic fee|"
               r"(?:the )?diagnostic fee \(\$89\) waived)(?: on all service calls)?")
_PHRASES = [
    (_DIAGNOSTIC, None),
    (r"no after-hours dispatch fee(?: on emergency calls)?", None),
    (r"15% off all repairs(?: \(parts and labor\))?", None),
    (r"(?:the same waiver and )?15% repair discount", None),
    (r"15% off plumbing repairs", "plus"),
    (r"(?:a )?\$500 (?:off (?:any|a) (?:full system replacement|new system|replacement)|"
     r"credit toward a full system replacement|full system replacement credit)", None),
    (r"\$189 (?:per|a) year(?: per system)?", "standard"),
    (r"\$16\.99 (?:per|a) month", "standard"),
    (r"\$269 (?:per|a) year(?: per system)?", "plus price"),
    (r"\$99 (?:per|a) year", "additional"),
]
_SOURCES = re.compile(r"\((?:[\w-]+/)*[\w.-]+\.(?:md|pdf|csv)\)|\b(?:2026 )?Residential Fee Schedule\b|\bahead of non-members\b", re.I)
_PLAN = re.compile(r"\b(?:members?|Comfort Club|Plus|Standard|membership|plan)\b")
_NOT_PLAIN = re.compile(r"\b(?:i|i'll|i'd|i'm|i've|me|my|we|we'll|we're|we've|we'd|us|our|you|your|you're|yours|you'll|"
                        r"today|tonight|now|this (?:time|once|visit|call|repair|job)|just|special|exception|courtesy|"
                        r"complimentary|since|joining|join|sign\w*|non-members?|nonmembers?|late|cancel\w*|holiday|"
                        r"no-show|refund\w*|reimburs\w*|free|instead|extra|additional discount|installations?|"
                        r"if|unless|guarantee\w*)\b|[’']ll\b", re.I)


_STATEMENT_WORDS = set("""a an and also as both each every get gets getting include includes including included adds add
along with all of the that it its is are cost costs priced price plan plans member members membership comfort club
standard plus per system on for or to in at year a-year annual annually month monthly benefits benefit following these
those here what list lists offers offer provides provide receive receives plus' per-system then too
one two seasonal tune ups cooling heating priority scheduling reminder filter change notifications inspection
overview maintenance water heater flush whole home plumbing""".split())  # the plan's published non-money benefits


def published_only(sentence: str, previous: str = "") -> bool:
    """True when the sentence plainly states published member benefits or plan prices and nothing else about money."""
    rest = _SOURCES.sub(" ", sentence)
    if FAVOUR.search(sentence) or _NOT_PLAIN.search(rest):
        return False
    if not _PLAN.search(rest) and not (re.match(r"(?:It|That|This|The plan|Each)\b", rest) and _PLAN.search(previous)):
        return False
    for pattern, condition in _PHRASES:
        for match in list(re.finditer(pattern + _END, rest, re.I)):
            before = rest[:match.start()]
            if condition == "plus" and (not re.search(r"\bPlus\b", before) or re.search(r"\bStandard\b|\bComfort Club(?! Plus)", before)):
                continue
            if condition == "standard" and re.search(r"\bPlus\b[^,;]{0,30}$", before):
                continue
            if condition == "plus price" and not re.search(r"\bPlus\b[^,;]{0,30}$", before):
                continue
            if condition == "additional" and "additional system" not in sentence.lower():
                continue
            rest = rest[:match.start()] + " " * (match.end() - match.start()) + rest[match.end():]
    # A full-sentence allowlist: once the published terms are removed, every word left must belong to a plain
    # statement of them ("Comfort Club members also get ..."); any other word sends the sentence to the model.
    return not touches_money(rest) and all(w.lower() in _STATEMENT_WORDS for w in re.findall(r"[A-Za-z']+", rest))


_CLAUSE = re.compile(r"[,;]|\band\b|\bor\b", re.I)


def wrong_plan_price(sentence: str) -> bool:
    """A plan named with another plan's price in the same clause ("Comfort Club Plus is $189 per year", "$269 per year
    for Standard"): a wrong fact, blocked in code. A clause naming both plans or neither is left to the other checks."""
    for clause in _CLAUSE.split(sentence):
        plus, standard = bool(re.search(r"\bPlus\b", clause)), bool(re.search(r"\bStandard\b", clause))
        if plus and not standard and re.search(r"\$(?:189|16\.99)\b", clause):
            return True
        if standard and not plus and re.search(r"\$269\b", clause):
            return True
    return False


class MoneyCheck:
    """Called with (sentence, previous sentence); True means the sentence may be released."""

    def __init__(self, client):
        self._client = client

    def __call__(self, sentence: str, previous: str) -> bool:
        if FAVOUR.search(sentence) or wrong_plan_price(sentence):
            return False
        if published_only(sentence, previous):
            return True
        try:
            deadline.check()
            timeout = deadline.per_attempt()
            response = self._client.messages.create(
                **({"timeout": timeout} if timeout is not None else {}), purpose="check",
                model=SETTINGS.router_model, max_tokens=SETTINGS.router_max_tokens, system=RULES,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": f"Previous sentence: {previous or '(none)'}\nSentence to check: {sentence}"}])
            if response.stop_reason == "refusal":
                return False
            verdict = json.loads("".join(b.text for b in response.content if b.type == "text"))
            return verdict["promises_beyond_published_terms"] is False
        except Exception as error:  # fail closed
            log.error("money check failed, sentence blocked: %s", error)
            return False
