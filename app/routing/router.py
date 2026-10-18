"""The router: Claude Haiku 5.5 sorts a message into one or more requests, each with a route and a clear or
unclear label (R38, R39). A refusal or unreadable answer is an unclear handoff."""

import json
from dataclasses import dataclass, field

from app.config import SETTINGS

ROUTES = ["knowledge", "account", "scheduling", "handoff", "redirect"]
DETAILS = ["none", "balance", "invoice", "membership", "system", "charged twice", "action", "book", "reschedule", "cancel",
           "confirm", "dispute", "complaint", "late technician", "commercial", "person", "other", "hiring", "wrong number"]
SERVICES = ["none", "hvac_repair", "hvac_tune_up", "plumbing", "estimate"]
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["clear", "requests"],
    "properties": {
        "clear": {"type": "boolean"},
        "requests": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "route", "detail", "service_type"],
            "properties": {"text": {"type": "string"}, "route": {"enum": ROUTES}, "detail": {"enum": DETAILS},
                           "service_type": {"enum": SERVICES}}}},
    },
}
RULES = """You sort messages to Meridian Home Comfort's customer assistant (an HVAC and plumbing company in Austin).
Split the message into its separate requests, in the caller's words, and give each a route:
- knowledge: questions answered from company documents (prices, fees, hours, service area, membership terms, warranty terms, payment methods, being charged twice).
- account: questions about the caller's own account: balance or invoice ("balance", "invoice"), membership tier or renewal ("membership"), system brand or install date ("system"); any request to take an action on money or membership, such as a payment link, autopay, cancelling the membership or auto-renew, upgrading, joining, or a fee waiver ("action").
- scheduling: book a visit ("book", with the service: hvac_repair, hvac_tune_up for a tune-up, plumbing, or estimate for a system replacement), or reschedule, cancel or confirm an existing appointment.
- handoff: a disputed charge or quote, or a refund ("dispute"); a complaint or a manager ("complaint"); a technician who is late ("late technician"); commercial work ("commercial"); asking for a person ("person"); anything else outside these ("other").
- redirect: job enquiries ("hiring") or a wrong number ("wrong number").
Mark clear false if what the caller is asking is ambiguous, if they are angry or abusive, or if you are unsure of the route.
Callers often give their name, account number, phone or address, and may give different details from earlier in the
conversation (someone else in the household); that is normal and does not make a message unclear. Use detail "none" and service_type "none" when they do not apply."""


@dataclass(frozen=True)
class Request:
    text: str
    route: str
    detail: str | None = None
    service_type: str | None = None


@dataclass(frozen=True)
class RouteResult:
    route: str
    clear: bool
    requests: list[Request] = field(default_factory=list)


def _unclear(text: str) -> RouteResult:
    return RouteResult("handoff", False, [Request(text, "handoff", "other")])


def route(text: str, history: list[dict], client) -> RouteResult:
    recent = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    response = client.messages.create(
        model=SETTINGS.router_model, max_tokens=2000, system=RULES,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Recent conversation:\n{recent or '(none)'}\n\nNew message: {text}"}])
    if response.stop_reason == "refusal":
        return _unclear(text)
    try:
        data = json.loads("".join(b.text for b in response.content if b.type == "text"))
        requests = [Request(r["text"], r["route"], None if r["detail"] == "none" else r["detail"],
                            None if r["service_type"] == "none" else r["service_type"]) for r in data["requests"]]
    except (ValueError, KeyError, TypeError):
        return _unclear(text)
    if not requests or any(r.route not in ROUTES for r in requests):
        return _unclear(text)
    return RouteResult(requests[0].route, bool(data["clear"]), requests)
