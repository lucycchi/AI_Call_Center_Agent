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
from app.accounts.lookups import is_action_request
from app.core import deadline
from app.core.model_log import SINK
from app.core.state import ConversationState, NotYourConversation
from app.core.types import DoneEvent, Event, SentenceEvent, Turn
from app.flows import scheduling
from app.flows.account import account_answer
from app.flows.identify import ASK, find_customer, has_identifier
from app.flows.knowledge import answer
from app.flows.protocol import FlowResult
from app.handoff.flow import add_to_open_ticket, hand_off, safe
from app.replies.checks import CheckedStream, check_sentence
from app.routing.router import Request, RouteResult
from app.safety.check import breaker_advice_allowed, check
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
# A bare acknowledgement with nothing in progress needs no routing; a goodbye ends the chat (R82).
ACKNOWLEDGEMENT = re.compile(r"^\W*(yes|yeah|yep|ok|okay|thanks|thank you|great|perfect|got it|cool)\W*$", re.I)
ENDING = re.compile(r"^\W*(?:(?:no|nope|um|uh|ok|okay|thanks|thank you|great)\W+)*(that'?s (it|all|everything)|that covers it|"
                    r"bye|goodbye|nothing else|i'?m good)(\W+(thanks|thank you( so much)?|bye))*\W*$", re.I)
ANYTHING_ELSE = "Is there anything else I can help you with?"
GOODBYE = "Thanks for contacting Meridian Home Comfort. Have a great day."
NOT_YOURS = "I can't open that conversation. Please start a new one."
SCHEDULING_ACTIONS = ("book", "reschedule", "cancel", "confirm")
BILLING_TAGS = ("dispute", "billing review")  # tickets that carry the invoice notes
OTHER_ACTION = re.compile(r"\b(cancel|reschedule|move|book|change)\b", re.I)
BARE_REPLY = re.compile(r"^\W*(?:(?:um|uh|oh)\W+)?(yes|yeah|yep|yup|no|nope|sure|ok|okay|correct)\W*(?:please|thanks)?\W*$", re.I)


def _plain_label(outcome: str, tags: list[str], passages: list, db_actions: list) -> str:
    """The reply receipt's plain outcome label (R71)."""
    if "not enough evidence" in tags:
        return "not enough evidence"
    if outcome in ("handed_off", "declined", "safety", "limit", "error"):
        return "handoff required"
    if outcome == "redirect":
        return "redirected"
    if outcome == "ended":
        return "conversation ended"
    if passages:
        return "supported by documents"
    return "supported by account records" if db_actions else "answered"


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
                 deadline_s: float = SETTINGS.message_deadline_s, money_check: Callable[[str, str], bool] | None = None):
        self.store, self.scheduling_db, self.seed_db = store, scheduling_db, seed_db
        self.searcher, self.route_fn, self.writer, self.threshold = searcher, route_fn, writer, threshold
        self.guard, self.now, self.clock, self.deadline_s = guard, now, clock, deadline_s
        self.money_check = money_check  # None fails closed: every sentence touching money is blocked (D43)

    # -- one turn ---------------------------------------------------------------------------------------
    def run(self, turn: Turn) -> Iterator[Event]:
        started = time.monotonic()
        spent = [0]
        first_ms: list[int] = []
        agent_ref: list[int | None] = [None]  # the agent reply this turn's model calls belong to

        def record(purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars):
            spent[0] += microdollars
            self._quietly(self.store.log_model_call, agent_ref[0], purpose, model_id, sdk_version, settings,
                          input_tokens, output_tokens, ms, microdollars)
        sink, clock = SINK.set(record), deadline.start(self.deadline_s)
        try:
            yield from self._turn(turn, started, first_ms, lambda m: agent_ref.__setitem__(0, m))
        finally:
            SINK.reset(sink)
            deadline.DEADLINE.reset(clock)
            if agent_ref[0] is not None:
                self._quietly(self.store.set_reply_stats, agent_ref[0], first_ms[0] if first_ms else None,
                              round((time.monotonic() - started) * 1000), spent[0])

    def _quietly(self, write, *args) -> bool:
        """A logging write that must not stop the reply (for example, after a booking has committed)."""
        try:
            write(*args)
            return True
        except Exception as error:
            log.error("operations write failed (%s): %s", getattr(write, "__name__", "write"), error)
            return False

    def _turn(self, turn: Turn, started: float, first_ms: list, remember) -> Iterator[Event]:
        from dataclasses import replace
        turn = replace(turn, text=turn.text.replace("’", "'").replace("‘", "'"))  # phone keyboards send curly quotes
        self.store.close_idle()
        row = self.store.conversation(turn.conversation_id)
        if row and row["visitor_id"] != turn.visitor_id:
            yield SentenceEvent(NOT_YOURS)
            yield DoneEvent(route="none", ticket=None, outcome="forbidden")
            return
        state = ConversationState.load(self.store, turn.conversation_id, turn.visitor_id)
        earlier = [m["content"] for m in self.store.history(turn.conversation_id, 20) if m["role"] == "caller"]
        if row and row["status"] != "open":
            # Safety still runs: a gas report after a goodbye reopens the conversation for the safety reply.
            if check(turn.text, earlier, state.burning_mentioned).kind == "clear":
                yield SentenceEvent(CLOSED)
                yield DoneEvent(route="none", ticket=None, outcome="closed")
                return
            self.store.reopen(turn.conversation_id)
        self._quietly(self.store.retry_pending)  # staff tickets kept while the database failed
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
            self._quietly(self.store.log_sentence, agent_message, sentence)
            return SentenceEvent(sentence)

        def error_event(detail: str) -> None:
            self._quietly(self.store.log_event, "error", detail, turn.conversation_id)

        def ticket(reason_tag: str, constraints: str, wants: str, also_tags: list[str] = []) -> list[str]:  # noqa: B006
            context = {"store": self.store, "conversation_id": turn.conversation_id, "who": state.who, "wants": wants,
                       "tried": "; ".join(state.tried), "mood": _mood(turn.text)}
            notes = state.notes if reason_tag in BILLING_TAGS else []
            result = hand_off(context, reason_tag, "; ".join(c for c in [constraints, *notes] if c))
            if context.get("ticket_id"):  # remembered only once the ticket is saved
                state.ticket_id = context["ticket_id"]
                turn_tickets.append(context["ticket_id"])
                state.tags_opened += [tag for tag in also_tags + [reason_tag] if tag not in state.tags_opened]
            return result.facts

        def finish(route: str, outcome: str, receipt: dict, db_actions: list[str], label: str | None = None,
                   tags: list[str] = ()) -> DoneEvent:
            state.save(self.store)  # not quiet: without the state the conversation cannot continue (R59)
            self._quietly(self.store.log_agent_message, agent_message, " ".join(released))
            receipt_row = (agent_message, receipt.get("safety", "clear"), label or route, receipt.get("passages", []),
                           receipt.get("excluded", []), "; ".join(db_actions) or None,
                           _plain_label(outcome, list(tags), receipt.get("passages", []), db_actions))
            if not self._quietly(self.store.log_receipt, *receipt_row):
                self.store.log_receipt(*receipt_row)  # retried once; a second failure is an operations failure (R59)
            return DoneEvent(route=route, ticket=turn_tickets[-1] if turn_tickets else None, receipt=receipt,
                             outcome=outcome, db_actions=db_actions)

        # 1. Safety, before anything else, even mid-flow or over a limit (R34 to R37). The advice goes out first.
        if not breaker_advice_allowed([turn.text]):
            state.burning_mentioned = True  # kept for the whole conversation
        safety = check(turn.text, earlier, state.burning_mentioned)
        if safety.kind != "clear":
            state.flow, state.active_flow, state.pending = {}, None, []  # emergencies are never booked
            for sentence in fixed_reply(safety.kind, turn.text):
                yield emit(sentence)
            for sentence in ticket(SAFETY_TAGS[safety.kind], safety.kind, turn.text):
                yield emit(sentence)
            yield finish("safety", "safety", {"safety": safety.kind}, [])
            return
        # 2. Limits (R61).
        limit = self.guard(turn.visitor_id)
        if limit:
            yield emit(LIMIT)
            yield finish("limit", "limit", {"limit": limit}, [])
            return
        at_read_back = state.flow.get("step") == "readback"
        # A clear goodbye ends the chat, even with a flow open; at a read-back only "bye" does, since "okay, I'm good"
        # may answer the read-back.
        if ENDING.match(turn.text) and (not at_read_back or re.search(r"\b(bye|goodbye)\b", turn.text, re.I)):
            state.flow, state.active_flow, state.pending = {}, None, []
            yield emit(GOODBYE)
            done = finish("none", "ended", {"safety": "clear"}, [])
            self._quietly(self.store.end_conversation, turn.conversation_id)
            yield done
            return
        if not state.active_flow and not state.pending:
            if ACKNOWLEDGEMENT.match(turn.text):
                yield emit(ANYTHING_ELSE)
                yield finish("none", "answered", {"safety": "clear"}, [])
                return
        # 3. Route, keeping follow-ups inside an active flow (R38, R40).
        history = self.store.history(turn.conversation_id)
        routed = self._route(turn.text, history, error_event)
        flow_before = state.active_flow
        requests, offer_return = self._requests(state, turn.text, routed)
        route_label = flow_before if requests and requests[0].route == "continue" else routed.route
        # 4. Flows. Account and scheduling requests wait for identification together, then run in turn (R39).
        results: list[FlowResult] = []
        queued = False
        for request in requests:
            if request.route in ("account", "scheduling") and not self._action(request) or request.route == "continue":  # noqa: E501
                if request.route != "continue":
                    state.pending.append({"route": request.route, "detail": request.detail,
                                          "service_type": request.service_type, "text": request.text})
                queued = True
                continue
            results.append(safe(lambda r=request: self._flow(r), error_event))
        if queued:
            continuing = any(r.route == "continue" for r in requests)
            results += self._advance_safely(state, turn.text, error_event, continuing)
        written: list[FlowResult] = []
        handoffs: list[tuple[str, str, str]] = []  # reason tag, constraints, what the caller wants
        fixed: list[str] = []
        db_actions: list[str] = []
        outcome = "answered"
        for result in results:
            db_actions += result.db_actions
            if result.reply_type == "redirect":
                fixed += result.facts
                outcome = "redirect" if outcome == "answered" else outcome
                continue
            if result.reply_type == "decline":
                fixed.append(_decline_sentence(*result.facts))
                handoffs.append(("decline", result.facts[0], turn.text))
                continue
            if result.reply_type == "confirmation":
                # A committed change is confirmed in code, so nothing after it (the writer, the deadline, a ticket
                # write) can hide it from the caller. The fixed text still passes the sentence checks (R60).
                for sentence in result.facts:
                    if check_sentence(sentence, " ".join(released)).ok:
                        yield emit(sentence)
                    else:
                        log.error("fixed confirmation failed a check: %s", sentence)
                continue
            if result.handoff_reason and not (result.handoff_reason == "earlier slot" and "earlier slot" in state.tags_opened):
                handoffs.append((result.handoff_reason, "", turn.text))
            if result.facts and result.reply_type != "handoff":
                written.append(result)
        if offer_return and written:
            last = written[-1]
            written[-1] = FlowResult(last.facts + [OFFER_RETURN], last.reply_type, last.sources, passages=last.passages,
                                     excluded=last.excluded)
        # 5. Writer and checks: each sentence is released only once it passes (R36, R42, R43, R60).
        if written:
            facts = [fact for result in written for fact in result.facts]
            burning = state.burning_mentioned or not breaker_advice_allowed(earlier + [turn.text])
            try:
                stream = CheckedStream(self.writer(written[0].reply_type, facts, history), burning_mentioned=burning,
                                       money_check=self.money_check)
                for count_released, sentence in enumerate(stream):
                    # The deadline is checked before each later sentence, so a slow reply is cut off (R59).
                    if count_released and deadline.passed():
                        raise deadline.DeadlinePassed("the reply passed the message deadline")
                    yield emit(sentence)
                if stream.blocked_rule:
                    self._quietly(self.store.log_event, "blocked sentence",
                                  f"{stream.blocked_rule}: {stream.blocked_sentence}", turn.conversation_id)
                    handoffs.append(("blocked reply", stream.blocked_rule, turn.text))
            except Exception as error:
                log.error("writer failed: %s", error)
                error_event(f"writer failed: {type(error).__name__}: {error}")
                handoffs.append(("error", "the reply could not be finished", turn.text))
        # 6. Everything handed off this turn goes in one ticket (R39).
        if handoffs:
            tags = [tag for tag, _, _ in handoffs]
            fixed += ticket(tags[0], "; ".join(c for _, c, _ in handoffs if c),
                            "; ".join(dict.fromkeys(w for _, _, w in handoffs)), tags[1:])
            outcome = "declined" if tags[0] == "decline" else "handed_off"
        for sentence in fixed:
            yield emit(sentence)
        receipt = {"safety": "clear", "clear": routed.clear,
                   "sources": [s for r in written for s in r.sources],
                   "passages": [p for r in written for p in r.passages],
                   "excluded": list(dict.fromkeys(e for r in written for e in r.excluded))}
        label = f"{route_label}, {'clear' if routed.clear or route_label == flow_before else 'unclear'}"
        yield finish(route_label, outcome, receipt, db_actions, label, [tag for tag, _, _ in handoffs])

    # -- routing ----------------------------------------------------------------------------------------
    def _route(self, text: str, history: list[dict], error_event) -> RouteResult:
        try:
            return self.route_fn(text, history)
        except Exception as error:
            log.error("router failed: %s", error)
            error_event(f"router failed: {type(error).__name__}: {error}")
            return RouteResult("handoff", False, [Request(text, "handoff", "other")])

    def _requests(self, state: ConversationState, text: str, routed: RouteResult) -> tuple[list[Request], bool]:
        """The requests to handle this turn, and whether to offer a return to an interrupted flow."""
        if state.active_flow:
            first = routed.requests[0] if routed.requests else None
            asked_for_person = routed.clear and routed.route == "handoff" and any(r.detail == "person" for r in routed.requests)
            answering_id_prompt = has_identifier(text) and not state.customer_id
            confirming = bool(BARE_REPLY.match(text)) or scheduling.YES.search(text) and len(text.split()) <= 3
            new_topic = routed.clear and routed.route != state.active_flow and not answering_id_prompt and not confirming
            # A different scheduling action (book, then cancel another appointment) is a new topic too,
            # even after a leading "no" or "yes" ("no, cancel my other appointment instead").
            # At an offer or a read-back, a reply starting with yes or no answers it, unless it names another action.
            answers_read_back = state.flow.get("step") in ("offer", "readback", "which") \
                and (scheduling.AFFIRMATIVE.search(text) or scheduling.NO.search(text)) and not OTHER_ACTION.search(text)
            switched_action = routed.clear and state.active_flow == "scheduling" and first is not None \
                and first.route == "scheduling" and first.detail in SCHEDULING_ACTIONS \
                and first.detail != state.flow.get("kind") and not BARE_REPLY.match(text) and not answers_read_back
            if asked_for_person or switched_action:
                state.flow, state.active_flow = {}, None
                return routed.requests, False
            if new_topic:
                return routed.requests, state.active_flow == "scheduling"
            return [Request(text, "continue")], False
        if not routed.clear:
            return [Request(text, "handoff", "unclear")], False
        return routed.requests, False

    # -- flows ------------------------------------------------------------------------------------------
    @staticmethod
    def _action(request: Request) -> bool:
        """Money or membership actions are the action gap, whether the router or the code check spots them (R48).
        Only explicit requests count, on any route: "can I pay by card?" is a question the FAQ answers."""
        if request.route == "account" and request.detail == "action":
            return True
        # On every route but a handoff, which is already handed off with the router's own reason.
        return request.route != "handoff" and is_action_request(request.text)

    def _flow(self, request: Request) -> FlowResult:
        if self._action(request):
            return FlowResult([], "handoff", handoff_reason="action gap")
        if request.route == "knowledge" or request.detail == "charged twice":
            return answer(request.text, self.searcher, self.threshold)
        if request.route == "redirect":
            return FlowResult([REDIRECTS.get(request.detail, REDIRECTS["wrong number"])], "redirect")
        if self._action(request):
            return FlowResult([], "handoff", handoff_reason="action gap")
        tag = "unclear" if request.detail == "unclear" else HANDOFF_TAGS.get(request.detail or "other", "other")
        return FlowResult([], "handoff", handoff_reason=tag)

    def _advance_safely(self, state: ConversationState, text: str, error_event, continuing: bool) -> list[FlowResult]:
        holder: list[list[FlowResult]] = []
        result = safe(lambda: holder.append(self._advance(state, text, continuing)) or FlowResult([], "none"), error_event)
        return holder[0] if holder else [result]

    def _advance(self, state: ConversationState, text: str, continuing: bool = True) -> list[FlowResult]:
        """Identify the caller if needed, then answer every waiting account request and run the scheduling flow.
        The open flow only reads this message when the message is a follow-up to it (continuing)."""
        db = sqlite3.connect(self.scheduling_db)
        try:
            customer = self._customer(db, state)
            named = find_customer(db, text) if has_identifier(text) else None
            if named and (customer is None or named.customer_id != customer.customer_id):
                customer = None  # a message naming a different customer switches to that account
                state.flow = {}  # the previous customer's booking is not carried over
            if customer is None:
                found = named or find_customer(db, text)
                if found:
                    customer, state.customer_id = found, found.customer_id
                    state.who = f"{found.name}, {found.customer_id}"
                    state.id_attempts, state.notes = 0, []
                else:
                    state.active_flow = state.active_flow or "account"
                    if NEW_CUSTOMER.search(text):
                        state.flow, state.active_flow, state.pending = {}, None, []
                        return [FlowResult([], "handoff", handoff_reason="new customer")]
                    if has_identifier(text):
                        state.id_attempts += 1
                        if state.id_attempts >= 2:
                            state.flow, state.active_flow, state.pending = {}, None, []
                            return [FlowResult([], "handoff", handoff_reason="not identified")]
                        return [FlowResult(["No account matched those details. " + ASK], "account answer")]
                    return [FlowResult([ASK], "account answer")]
            results: list[FlowResult] = []
            # Account questions are answered first, so a question asked mid-booking does not wait behind it.
            for request in [r for r in state.pending if r["route"] == "account"]:
                state.pending.remove(request)
                results.append(account_answer(read_only(self.scheduling_db), customer, request["detail"], state, self.store))
            flow_text = text if continuing or not state.flow else None
            while True:
                if state.flow and flow_text is not None:
                    results.append(scheduling.step(db, self.seed_db, customer, state, flow_text, self.now, self.store))
                    if state.flow:
                        break
                    flow_text = ""
                elif state.flow:
                    break  # an open flow waits; the caller was offered a return to it
                if not state.pending:
                    break
                request = state.pending.pop(0)
                state.flow = {"kind": request["detail"] if request["detail"] in SCHEDULING_ACTIONS else "book",
                              "step": "start", "issue": request["text"]}
                if request["service_type"]:
                    state.flow["service"] = request["service_type"]
                flow_text = request["text"] if flow_text == "" else text
            state.active_flow = "scheduling" if state.flow else None
            return results or [FlowResult(["Ask how else you can help."], "policy answer")]
        finally:
            db.close()

    def _customer(self, db, state: ConversationState):
        if not state.customer_id:
            return None
        from app.accounts.identity import Customer
        row = db.execute("select customer_id, name, phone, email, service_address, city, zip, membership_tier "
                         "from customers where customer_id = ?", (state.customer_id,)).fetchone()
        return Customer(*row) if row else None
