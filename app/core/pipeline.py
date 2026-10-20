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
from app.core.language import WORD, english_words, other_language
from app.core.model_log import SINK
from app.core.state import ConversationState, NotYourConversation
from app.core.types import DoneEvent, Event, SentenceEvent, Turn
from app.flows import scheduling
from app.flows.account import account_answer
from app.flows.identify import ACCOUNT, ASK, PHONE, STREET, find_customer, has_identifier
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
                "commercial": "commercial", "person": "other", "other language": "other language", "other": "other"}
SAFETY_TAGS = {"danger": "emergency", "burning": "burning smell", "urgent": "emergency"}
ANGRY = re.compile(r"\b(ridiculous|unacceptable|furious|angry|done with|worst|terrible|sick of)\b|!{2,}", re.I)
OFFER_RETURN = "Offer to return to the booking afterwards."
NEW_CUSTOMER = re.compile(r"\b(i'?m new|i am new|new customer|first time (calling|customer)|don'?t have an account)\b", re.I)
# A bare acknowledgement with nothing in progress needs no routing; a goodbye ends the chat (R82).
ACKNOWLEDGEMENT = re.compile(r"^\W*(yes|yeah|yep|ok|okay|thanks|thank you|great|perfect|got it|cool)\W*$", re.I)
ENDING = re.compile(r"^\W*(?:(?:no|nope|um|uh|ok|okay|thanks|thank you|great)\W+)*(that'?s (it|all|everything)|that covers it|"
                    r"bye|goodbye|nothing else|i'?m good)(\W+(thanks|thank you( so much)?|bye))*\W*$", re.I)
ANYTHING_ELSE = "Is there anything else I can help you with?"
# Lines that ask nothing ("hold on", "can you hear me", "you cut out"): never routed, never a ticket.
FILLER = re.compile(r"\b(can you hear me|hold on|hang on|one sec(ond)?|(you|it|the line|the call) cut out|i'?m driving|"
                    r"repeat that|say that again|dog is barking|bear with me|give me (a|one) (sec|second|moment|minute))\b", re.I)
FILLER_WORDS = re.compile(r"\b(sorry|oh|um|uh|ok|okay|yeah|hi|hello|so|just|please|there|again|still|real quick|wait|a bit|"
                          r"(for )?a (sec|second|moment|minute)|could you|can you|would you|my|the|is|me|that|you|it)\b", re.I)
TAKE_YOUR_TIME = "No problem, take your time."
JOIN_CONSENT = re.compile(r"\b(add it|add that|add me|sign me up|let'?s do it|enrol+ me|go ahead and (add|join))\b", re.I)
PLAN_WORDS = re.compile(r"\b(comfort club|maintenance plan|membership|the plan)\b", re.I)
WARRANTY = re.compile(r"\b(warranty|warranties|covered|coverage|claim)\b", re.I)
# "That's all", "that's everything" or "that's it" with no question in the message is a goodbye wherever it comes.
GOODBYE_ANYWHERE = re.compile(r"\bthat'?s (all|everything|it)( i (need|needed|wanted))?\b|\bthat covers it\b|\bnothing else\b|"
                              r"\b(cheers|take care|thanks a bunch|appreciate it|have a (good|great|nice) (day|one|evening|weekend))\b",
                              re.I)
# Pleasantries, and remarks that ask for nothing ("I'm chatting on your website", "you just confirmed my appointment").
GOODBYE_WORDS = re.compile(r"\b(oh|sorry|about that|i think|i (needed|wanted)|needed|anyway|no|nope|yes|yeah|great|perfect|cool|"
                           r"alright|all right|ok|okay|thanks|thank you|so much|very much|appreciate it|bye|goodbye|for now|"
                           r"for today|i'?m good|then|really|have a (good|great|nice) (day|one)|you too|for me|and|so|"
                           r"for (your help|confirming|everything)|that'?s fine|good to know|"
                           r"i'?m (chatting )?(on|with) (your website( chat)?|meridian)|"
                           r"i'?m chatting|about my( \w+)? (tune-?up|appointment|visit)|this is (a )?chat|not a phone call|"
                           r"you (just )?confirmed my( \w+)? appointment|i don'?t think it'?s the wrong number|"
                           r"i can (hear you|see your messages)( fine)?|i'?ll hold off on the \w+ one)\b", re.I)
GOODBYE = "Thanks for contacting Meridian Home Comfort. Have a great day."
NOT_YOURS = "I can't open that conversation. Please start a new one."
SCHEDULING_ACTIONS = ("book", "reschedule", "cancel", "confirm")
BILLING_TAGS = ("dispute", "billing review")  # tickets that carry the invoice notes
ACTION_VERBS = {"cancel": r"cancel", "reschedule": r"reschedule|move|change", "book": r"book"}
NEGATION = re.compile(r"\b(not|don'?t|doesn'?t|won'?t|do not|no longer|anymore|never)\b", re.I)
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


def _only(text: str, phrases: re.Pattern, words: re.Pattern) -> bool:
    """The message is nothing but those phrases and pleasantries: no request is left in it."""
    return bool(phrases.search(text)) and not re.search(r"\w", words.sub(" ", phrases.sub(" ", text)))


def _details_only(text: str, customer) -> bool:
    """Nothing but the caller's name and account details ("linda foster mhc-10001")."""
    words = f"{customer.name} {customer.city}".split()
    for pattern in (ACCOUNT, PHONE, STREET, *(re.compile(rf"\b{re.escape(w)}\b", re.I) for w in words)):
        text = pattern.sub(" ", text)
    return not WORD.search(text)


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

        outer = SINK.get()  # a test run's budget, for example, also counts this turn's model calls

        def record(purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars):
            spent[0] += microdollars
            if outer:
                outer(purpose, model_id, sdk_version, settings, input_tokens, output_tokens, ms, microdollars)
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
                for tag in also_tags:
                    self._quietly(self.store.add_reason, context["ticket_id"], tag, "")
            return result.facts

        def add_reason(reason_tag: str, constraints: str) -> None:
            """A later reason joins the open ticket with its tag and, for billing, the invoice notes (R57, R58)."""
            notes = state.notes if reason_tag in BILLING_TAGS else []
            if self._quietly(self.store.add_reason, state.ticket_id, reason_tag if reason_tag != "unclear" else "",
                             "; ".join(c for c in [constraints, *notes] if c)) and reason_tag not in state.tags_opened:
                state.tags_opened.append(reason_tag)

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
        says_goodbye = ENDING.match(turn.text) or (_only(turn.text, GOODBYE_ANYWHERE, GOODBYE_WORDS) and "?" not in turn.text)
        if says_goodbye and (not at_read_back or re.search(r"\b(bye|goodbye)\b", turn.text, re.I)):
            state.flow, state.active_flow, state.pending = {}, None, []
            yield emit(GOODBYE)
            done = finish("none", "ended", {"safety": "clear"}, [])
            self._quietly(self.store.end_conversation, turn.conversation_id)
            yield done
            return
        if _only(turn.text, FILLER, FILLER_WORDS) and not has_identifier(turn.text):
            again = scheduling.repeat(state.flow) if state.flow else None
            if again:
                for sentence in CheckedStream(self.writer(again.reply_type, again.facts, self.store.history(turn.conversation_id)),
                                              money_check=self.money_check):
                    yield emit(sentence)
            else:
                yield emit(TAKE_YOUR_TIME)
            yield finish(state.active_flow or "none", "answered", {"safety": "clear"}, [])
            return
        if not state.active_flow and not state.pending:
            if ACKNOWLEDGEMENT.match(turn.text):
                yield emit(ANYTHING_ELSE)
                yield finish("none", "answered", {"safety": "clear"}, [])
                return
        identified_now = False
        # A caller who gives their details on any route is identified then, so they are not asked again later (R45);
        # an account number and a name may come in two messages. An open ticket is told who the caller is (R57).
        if not state.customer_id and (has_identifier(turn.text) or (earlier and has_identifier(earlier[-1]))):
            lookup = read_only(self.scheduling_db)
            try:
                found = find_customer(lookup, turn.text) or (find_customer(lookup, f"{earlier[-1]} {turn.text}") if earlier else None)
            finally:
                lookup.close()
            if found:
                state.customer_id, state.who, state.id_attempts = found.customer_id, f"{found.name}, {found.customer_id}", 0
                identified_now = found
                if state.ticket_id:
                    self._quietly(self.store.set_ticket_caller, state.ticket_id, state.who)
        # 3. Route, keeping follow-ups inside an active flow (R38, R40).
        history = self.store.history(turn.conversation_id)
        routed = self._route(turn.text, history, error_event)
        # Another language is handed off even if the router missed it (D47).
        if other_language(turn.text):
            routed = RouteResult("handoff", True, [Request(turn.text, "handoff", "other language")])
        flow_before = state.active_flow
        # A request for a person, or a reason the router named, is handed off even when the route is unclear (R38).
        names_a_handoff = any(r.route == "handoff" and r.detail in HANDOFF_TAGS and r.detail != "other" for r in routed.requests)
        # The calm shortcuts below need a common English word, so gibberish ("asdf qwer") still goes to a person.
        calm = _mood(turn.text) == "calm" and not names_a_handoff
        asks_nothing = "?" not in turn.text and calm and english_words(turn.text) > 0
        if identified_now and not state.active_flow and not state.pending and not routed.clear and calm \
                and (english_words(turn.text) or _details_only(turn.text, identified_now)):
            # A message that only gave the caller's details: nothing to hand off.
            yield emit(f"Thanks, {identified_now.name.split()[0]}, I've found your account. What can I help you with?")
            yield finish("account", "answered", {"safety": "clear"}, [])
            return
        if not routed.clear and not state.active_flow and not state.pending and asks_nothing and len(turn.text.split()) <= 15:
            # An unclear message that asks nothing ("okay, good to know") is not a request: no ticket (R38, tuned on
            # the working set). An angry message, a question or a longer message still goes to a handoff. With a ticket
            # open, the message was added to it at the start of the turn (R58).
            if state.ticket_id:
                state.ticket_notes += 1
                yield emit(f"I've added that to Ticket #{state.ticket_id}.")
            else:
                yield emit(ANYTHING_ELSE)
            yield finish("none", "answered", {"safety": "clear"}, [])
            return
        requests, offer_return = self._requests(state, turn.text, routed)
        # "Add it" or "sign me up" after the plan was discussed is a request to join, an action the agent cannot take (R48).
        if JOIN_CONSENT.search(turn.text) and any(PLAN_WORDS.search(m["content"]) for m in history[-4:] + [{"content": turn.text}]) \
                and not any(r.route == "handoff" or (r.route == "account" and r.detail == "action") for r in requests):
            requests = [*requests, Request(turn.text, "account", "action")]
        if any(r.route == "scheduling" for r in requests) and WARRANTY.search(turn.text) \
                and not any(r.route == "knowledge" for r in requests):
            requests = [Request(turn.text, "knowledge"), *requests]  # a warranty claim also gets the coverage answer
        route_label = flow_before if requests and requests[0].route == "continue" else routed.route
        # 4. Flows. Account and scheduling requests wait for identification together, then run in turn (R39).
        results: list[FlowResult] = []
        queued = False
        for request in requests:
            if request.route in ("account", "scheduling") and not self._action(request) or request.route == "continue":  # noqa: E501
                waiting = {(p["route"], p["detail"]) for p in state.pending}
                in_progress = request.route == "scheduling" and request.detail == state.flow.get("kind")
                # The router can split one request into two identical ones; each is handled once.
                if request.route != "continue" and (request.route, request.detail) not in waiting and not in_progress:
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
                elif stream.not_in_documents:  # the writer found the facts do not answer it: a ticket follows
                    handoffs.append(("not enough evidence", "", turn.text))
            except Exception as error:
                log.error("writer failed: %s", error)
                error_event(f"writer failed: {type(error).__name__}: {error}")
                handoffs.append(("error", "the reply could not be finished", turn.text))
        # 6. Everything handed off this turn goes in one ticket (R39). With a ticket already open in this conversation,
        # the message was added to it at the start of the turn and its reasons join it, so no new ticket is opened (R58).
        if handoffs and state.ticket_id:
            for tag, constraints, _ in handoffs:
                add_reason(tag, constraints)
            state.ticket_notes += 1
            fixed.append(f"I've added that to Ticket #{state.ticket_id}" +
                         ("; our team will contact you within one business day." if state.ticket_notes == 1 else "."))
            outcome = "handed_off"
        elif handoffs:
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
            # "Another action" means a verb for an action other than the flow's own ("book it" in a booking does not count).
            other = "|".join(v for k, v in ACTION_VERBS.items() if k != state.flow.get("kind"))
            # A reply that picks a slot ("the first one", "Tuesday at 3") answers the offer too, unless it turns one down.
            answers_read_back = state.flow.get("step") in ("offer", "readback", "which") \
                and (scheduling.AFFIRMATIVE.search(text) or scheduling.YES.search(text) or scheduling.NO.search(text) or
                     scheduling.picks_a_slot(text, state.flow, self.now) and not NEGATION.search(text)) \
                and not re.search(rf"\b({other})\b", text, re.I)
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
            reason = next((r.detail for r in routed.requests if r.route == "handoff" and r.detail in HANDOFF_TAGS
                           and r.detail not in ("other", "person")), "unclear")
            return [Request(text, "handoff", reason)], False  # an unclear complaint is still tagged a complaint
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
