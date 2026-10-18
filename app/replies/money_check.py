"""A model check on every reply sentence that touches money (R42, D43).

Code cannot list every way to promise a waiver, refund or discount ("we won't charge you", "it's on us"), so each
sentence about money is put to Claude Haiku 5.5 with the published terms and the sentence before it. The check
fails closed: a refusal, an error, a timeout or an unreadable answer blocks the sentence."""

import json
import logging
import re

from app.config import SETTINGS
from app.core import deadline

log = logging.getLogger("meridian.money_check")

MONEY = re.compile(r"[$%]|\b(fees?|charges?|charged|charging|costs?|price[sd]?|pricing|free|refund\w*|credit\w*|discount\w*|"
                   r"waiv\w*|owe[sd]?|bill\w*|invoice\w*|pay\w*|money|dollars?|percent|cheaper|reimburs\w*|quotes?|"
                   r"on the house|on us|no charge|reduc\w*|lower)\b", re.I)

# The published money terms, from the current customer documents (fee schedule, FAQ, membership, catalog, warranty).
PUBLISHED_TERMS = """- Diagnostic visit $89 for non-members, credited toward a repair approved on the same visit; waived for Comfort Club and Plus members.
- After-hours emergency dispatch $149 for non-members; waived for members. Holiday emergency dispatch $199.
- Seasonal tune-up $129 for non-members; included twice a year for members.
- Late cancellation or reschedule inside 24 hours: $49 for everyone; free more than 24 hours before the window. No-show $89 for non-members, $0 for members.
- Members get 15% off repairs; Plus members also 15% off plumbing repairs; members get $500 off a full system replacement (also said as "$500 off a replacement" or "a new system").
- Comfort Club $189 a year per system or $16.99 a month (12-month minimum); Plus $269 a year; upgrade difference $80, prorated.
- Annual plans: a prorated refund within the first 60 days only if no tune-up was done; non-refundable after a tune-up.
- Free in-home replacement estimate. Price-book and catalog ranges are typical prices; the technician confirms the final price on site.
- A duplicate charge is usually a pending authorization that drops off in 3 to 5 business days.
- No diagnostic fee when the technician confirms a repair is covered by warranty. Financing on repairs over $1,000.
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


class MoneyCheck:
    """Called with (sentence, previous sentence); True means the sentence may be released."""

    def __init__(self, client):
        self._client = client

    def __call__(self, sentence: str, previous: str) -> bool:
        if FAVOUR.search(sentence):
            return False
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
