"""The agent pipeline: safety, limits, router, flows, writer and checks, in that order (R34, R38 to R40, R60).

Each caller message is logged; every reply sentence is released only once checked and saved for replay;
the turn ends with one DoneEvent saying what happened."""

import logging
import re
import sqlite3
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from app.accounts.lookups import read_only
from app.config import SETTINGS, real_now
from app.core.model_log import SINK
from app.core.state import ConversationState
from app.core.types import DoneEvent, Event, SentenceEvent, Turn
from app.flows import scheduling
from app.flows.account import account_answer
from app.flows.identify import ASK, find_customer, has_identifier
from app.flows.knowledge import answer
from app.flows.protocol import FlowResult
from app.handoff.flow import add_to_open_ticket, hand_off, safe
from app.replies.checks import CheckedStream
from app.routing.router import Request, RouteResult
from app.safety.check import check
from app.safety.replies import fixed_reply

log = logging.getLogger("meridian.pipeline")
CLOSED = "This conversation was closed after 30 minutes without a message. Please start a new one."
LIMIT = ("I can't continue this chat right now because the site has reached its usage limit. Please phone our office "
         "(Monday to Friday 7am to 7pm, or Saturday 8am to 4pm), or try again tomorrow.")
REDIRECTS = {"hiring": "We don't take job applications by phone; openings and applications are on the careers page of our website.",
             "wrong number": "This is Meridian Home Comfort, a heating, cooling and plumbing company in the Austin area; "
                             "it sounds like you may have the wrong number."}
HANDOFF_TAGS = {"dispute": "dispute", "complaint": "complaint", "late technician": "late technician",
                "commercial": "commercial", "person": "other", "other": "other"}
SAFETY_TAGS = {"danger": "emergency", "burning": "burning smell", "urgent": "emergency"}
ANGRY = re.compile(r"\b(ridiculous|unacceptable|furious|angry|done with|worst|terrible|sick of)\b|!{2,}", re.I)
OFFER_RETURN = "Offer to return to the booking afterwards."
NEW_CUSTOMER = re.compile(r"\b(i'?m new|i am new|new customer|first time (calling|customer)|don'?t have an account)\b", re.I)
# A bare acknowledgement or goodbye with nothing in progress needs no routing.
ACKNOWLEDGEMENT = re.compile(r"^\W*(yes|yeah|yep|ok|okay|thanks|thank you|great|perfect|got it|cool|nope|no)"
                             r"(\W+(that'?s (it|all|everything)|thanks|thank you( so much)?))*\W*$", re.I)
ANYTHING_ELSE = "Is there anything else I can help you with?"


def _decline_sentence(reason: str, city: str, service: str) -> str:
    if reason == "served area without a scheduling zone":
        return f"{city} is in our service area, but I can't book visits there from this chat."
    if reason == "outside the service area":
        return f"I'm sorry, {city} is outside our service area."
    return f"I'm sorry, there's no {service} availability for your area in the next three weeks."


def _mood(text: str) -> str:
    return "frustrated" if ANGRY.search(text) else "calm"


class AgentPipeline:
    def __init__(self, store, scheduling_db: Path, seed_db: Path, searcher, route_fn: Callable, writer: Callable,
                 threshold: float, guard: Callable[[str], str | None] = lambda visitor: None,
                 now: datetime = SETTINGS.now, clock: Callable[[], datetime] = real_now,
                 deadline_s: float = SETTINGS.message_deadline_s):
        self.store, self.scheduling_db, self.seed_db = store, scheduling_db, seed_db
        self.searcher, self.route_fn, self.writer, self.threshold = searcher, route_fn, writer, threshold
        self.guard, self.now, self.clock, self.deadline_s = guard, now, clock, deadline_s

    # -- one turn ---------------------------------------------------------------------------------------
    def run(self, turn: Turn) -> Iterator[Event]:
        started = time.monotonic()
        spent = [0]
        first_ms: list[int] = []
        agent_ref: list[int | None] = [None]  # the agent reply this turn's model calls belong to

        def record(purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars):
            spent[0] += microdollars
            self.store.log_model_call(agent_ref[0], purpose, model_id, sdk_version, settings, input_tokens, output_tokens,
                                      ms, microdollars)
        token = SINK.set(record)
        try:
            yield from self._turn(turn, started, spent, first_ms, lambda m: agent_ref.__setitem__(0, m))
        finally:
            SINK.reset(token)
            if agent_ref[0] is not None:
                self.store.set_reply_stats(agent_ref[0], first_ms[0] if first_ms else None,
                                           round((time.monotonic() - started) * 1000), spent[0])

    def _turn(self, turn: Turn, started: float, spent: list, first_ms: list, remember) -> Iterator[Event]:
        self.store.close_idle()
        row = self.store.conversation(turn.conversation_id)
        if row and row["status"] == "closed":
            yield SentenceEvent(CLOSED)
            yield DoneEvent(route="none", ticket=None, outcome="closed")
            return
        state = ConversationState.load(self.store, turn.conversation_id, turn.visitor_id)
        earlier = [m["content"] for m in self.store.history(turn.conversation_id, 20) if m["role"] == "caller"]
        caller_message = self.store.log_message(turn.conversation_id, "caller", turn.text, turn.message_id)
        if state.ticket_id:
            add_to_open_ticket({"store": self.store, "ticket_id": state.ticket_id}, caller_message)
        agent_message = self.store.log_message(turn.conversation_id, "agent", "")
        remember(agent_message)
        turn_tickets: list[int] = []
        released: list[str] = []

        def emit(sentence: str) -> SentenceEvent:
            if not first_ms:
                first_ms.append(round((time.monotonic() - started) * 1000))
            released.append(sentence)
            self.store.log_sentence(agent_message, sentence)
            return SentenceEvent(sentence)

        def ticket(reason_tag: str, constraints: str, wants: str) -> list[str]:
            context = {"store": self.store, "conversation_id": turn.conversation_id, "who": state.who, "wants": wants,
                       "tried": "; ".join(state.tried), "mood": _mood(turn.text)}
            result = hand_off(context, reason_tag, constraints)
            if context.get("ticket_id"):
                state.ticket_id = context["ticket_id"]
                turn_tickets.append(context["ticket_id"])
            return result.facts

        def finish(route: str, outcome: str, receipt: dict, db_actions: list[str]) -> DoneEvent:
            state.save(self.store)
            self.store.log_agent_message(agent_message, " ".join(released))
            self.store.log_receipt(agent_message, receipt.get("safety", "clear"), route, receipt.get("sources", []), [],
                                   "; ".join(db_actions) or None, outcome)
            return DoneEvent(route=route, ticket=turn_tickets[-1] if turn_tickets else None, receipt=receipt,
                             outcome=outcome, db_actions=db_actions)

        # 1. Safety, before anything else, even mid-flow or over a limit (R34 to R37).
        safety = check(turn.text, earlier)
        if safety.kind != "clear":
            state.flow, state.active_flow = {}, None  # emergencies are never booked
            for sentence in fixed_reply(safety.kind, turn.text) + ticket(SAFETY_TAGS[safety.kind], safety.kind, turn.text):
                yield emit(sentence)
            yield finish("safety", "safety", {"safety": safety.kind}, [])
            return
        # 2. Limits (R61).
        limit = self.guard(turn.visitor_id)
        if limit:
            yield emit(LIMIT)
            yield finish("limit", "limit", {"limit": limit}, [])
            return
        if not state.active_flow and ACKNOWLEDGEMENT.match(turn.text):
            yield emit(ANYTHING_ELSE)
            yield finish("none", "answered", {"safety": "clear"}, [])
            return
        # 3. Route, keeping follow-ups inside an active flow (R38, R40).
        history = self.store.history(turn.conversation_id)
        routed = self._route(turn.text, history)
        flow_before = state.active_flow
        requests, offer_return = self._requests(state, turn.text, routed)
        route_label = flow_before if requests and requests[0].route == "continue" else routed.route
        # 4. Flows.
        written: list[FlowResult] = []
        handoffs: list[tuple[str, str, str]] = []  # reason tag, constraints, what the caller wants
        fixed: list[str] = []
        db_actions: list[str] = []
        outcome = "answered"
        for request in requests:
            result = safe(lambda r=request: self._flow(state, r, turn.text), self.deadline_s)
            db_actions += result.db_actions
            if result.reply_type == "redirect":
                fixed += result.facts
                outcome = "redirect" if outcome == "answered" else outcome
            elif result.handoff_reason:
                if result.reply_type == "decline":
                    fixed.append(_decline_sentence(*result.facts))
                handoffs.append((result.handoff_reason, result.facts[0] if result.reply_type == "decline" else "",
                                 request.text))
            else:
                written.append(result)
        if offer_return and written:
            written[-1] = FlowResult(written[-1].facts + [OFFER_RETURN], written[-1].reply_type, written[-1].sources)
        # 5. Writer and checks: each sentence is released only once it passes (R42, R43, R60).
        if written:
            facts = [fact for result in written for fact in result.facts]
            try:
                stream = CheckedStream(self.writer(written[0].reply_type, facts, history))
                for sentence in stream:
                    yield emit(sentence)
                if stream.blocked_rule:
                    self.store.log_event("blocked sentence", f"{stream.blocked_rule}: {stream.blocked_sentence}",
                                         turn.conversation_id)
                    handoffs.append(("blocked reply", stream.blocked_rule, turn.text))
            except Exception as error:
                log.error("writer failed: %s", error)
                handoffs.append(("error", "the reply could not be written", turn.text))
        # 6. Everything handed off this turn goes in one ticket (R39).
        if handoffs:
            tags = [tag for tag, _, _ in handoffs]
            for sentence in ticket(tags[0], "; ".join(c for _, c, _ in handoffs if c), "; ".join(w for _, _, w in handoffs)):
                fixed.append(sentence)
            outcome = "declined" if tags[0] == "decline" else "handed_off"
        for sentence in fixed:
            yield emit(sentence)
        sources = [s for result in written for s in result.sources]
        yield finish(route_label, outcome, {"safety": "clear", "clear": routed.clear, "sources": sources}, db_actions)

    # -- routing ----------------------------------------------------------------------------------------
    def _route(self, text: str, history: list[dict]) -> RouteResult:
        try:
            return self.route_fn(text, history)
        except Exception as error:
            log.error("router failed: %s", error)
            return RouteResult("handoff", False, [Request(text, "handoff", "other")])

    def _requests(self, state: ConversationState, text: str, routed: RouteResult) -> tuple[list[Request], bool]:
        """The requests to handle this turn, and whether to offer a return to an interrupted flow."""
        if state.active_flow:
            asked_for_person = routed.clear and routed.route == "handoff" and any(r.detail == "person" for r in routed.requests)
            answering_id_prompt = has_identifier(text) and not state.customer_id
            new_topic = routed.clear and routed.route != state.active_flow and not answering_id_prompt \
                and not scheduling.YES.search(text) and not scheduling.NO.search(text)
            if asked_for_person:
                state.flow, state.active_flow = {}, None
                return routed.requests, False
            if new_topic:
                return routed.requests, state.active_flow == "scheduling"
            return [Request(text, "continue")], False
        if not routed.clear:
            return [Request(text, "handoff", "unclear")], False
        return routed.requests, False

    # -- flows ------------------------------------------------------------------------------------------
    def _flow(self, state: ConversationState, request: Request, text: str) -> FlowResult:
        if request.route == "knowledge" or request.detail == "charged twice":
            return answer(request.text, self.searcher, self.threshold)
        if request.route == "redirect":
            return FlowResult([REDIRECTS.get(request.detail, REDIRECTS["wrong number"])], "redirect")
        if request.route == "handoff":
            tag = "unclear" if request.detail == "unclear" else HANDOFF_TAGS.get(request.detail or "other", "other")
            return FlowResult([], "handoff", handoff_reason=tag)
        if request.route == "account" and request.detail == "action":
            return FlowResult([], "handoff", handoff_reason="action gap")
        if request.route in ("account", "scheduling"):
            state.pending.append({"route": request.route, "detail": request.detail, "service_type": request.service_type,
                                  "text": request.text})
            state.active_flow = request.route
        return self._advance(state, text)

    def _advance(self, state: ConversationState, text: str) -> FlowResult:
        """Identify the caller if needed, then work through the pending requests or the active flow."""
        db = sqlite3.connect(self.scheduling_db)
        try:
            customer = self._customer(db, state)
            named = find_customer(db, text) if has_identifier(text) else None
            if named and (customer is None or named.customer_id != customer.customer_id):
                customer = None  # a message naming a different customer switches to that account
            if customer is None:
                found = named or find_customer(db, text)
                if found:
                    customer, state.customer_id = found, found.customer_id
                    state.who = f"{found.name}, {found.customer_id}"
                    state.id_attempts = 0
                elif NEW_CUSTOMER.search(text):
                    state.flow, state.active_flow, state.pending = {}, None, []
                    return FlowResult([], "handoff", handoff_reason="new customer")
                elif has_identifier(text):
                    state.id_attempts += 1
                    if state.id_attempts >= 2:
                        state.flow, state.active_flow, state.pending = {}, None, []
                        return FlowResult([], "handoff", handoff_reason="not identified")
                    return FlowResult(["No account matched those details. " + ASK], "account answer")
                else:
                    return FlowResult([ASK], "account answer")
            if state.pending:
                request = state.pending.pop(0)
                if request["route"] == "account":
                    state.active_flow = "scheduling" if state.flow else None
                    return account_answer(read_only(self.scheduling_db), customer, request["detail"], state, self.store)
                state.flow = {"kind": request["detail"] or "book", "step": "start", "issue": request["text"]}
                if request["service_type"]:
                    state.flow["service"] = request["service_type"]
                state.active_flow = "scheduling"
            if not state.flow:
                state.active_flow = None
                return FlowResult(["Ask how else you can help."], "policy answer")
            return scheduling.step(db, self.seed_db, customer, state, text, self.now, self.store)
        finally:
            db.close()

    def _customer(self, db, state: ConversationState):
        if not state.customer_id:
            return None
        from app.accounts.identity import Customer
        row = db.execute("select customer_id, name, phone, email, service_address, city, zip, membership_tier "
                         "from customers where customer_id = ?", (state.customer_id,)).fetchone()
        return Customer(*row) if row else None
