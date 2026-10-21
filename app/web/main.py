"""The web layer (R62, R64 to R66): the chat page, message requests and the sentence stream.

Each caller message is an ordinary request (POST /api/message) that returns 202 at once; the reply is worked out in a
background thread, one message at a time per conversation, and its checked sentences are pushed to the stream for
that message id (GET /api/stream/{message_id}) as the engine releases them, then a done event. The app is built by
create_app with the engine and operations store passed in, so tests use fakes; build_app wires the real agent.

Live-only fixes after the measurement (D51):
- Safety before the message limits: a message over a limit is answered with the limit message only when the safety
  check finds nothing in it; otherwise the agent gets it, with the limit set for its guard (app/web/limits.py).
- Refused and blank messages write nothing; an accepted message is stored (as an accepted placeholder) before the
  work is submitted, so a restart replays it as unfinished.
- Every fallback reply (the stream giving up, a restart, the engine failing) opens one "error" ticket.
- A turn the stream has given up on never starts, and one starts only while there is time for its whole deadline
  before the stream would give up, so nothing it does lands after the caller was told it was passed on."""

import asyncio
import json
import logging
import shutil
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import real_now
from app.core.model_log import PRE_CALL, SINK
from app.core.types import DoneEvent, SentenceEvent, Turn
from app.handoff.flow import ERROR_MESSAGE, NO_TICKET_MESSAGE
from app.safety.check import check as safety_check
from app.safety.replies import fixed_reply
from app.web.health import health_routes
from app.web.limits import LIMIT_MESSAGE, TURN_LIMIT, Limits
from app.web.results import results_routes
from app.web.reviewer import reviewer_routes
from app.web.staff import staff_routes
from app.web.visitor import COOKIE, VisitorCookie

log = logging.getLogger("meridian.web")
ID = r"^[A-Za-z0-9_-]{1,64}$"
KEEP_REPLIES = 1000
MAX_CHARACTERS = 2000
TELL_ME_MORE = "Could you tell me a bit more?"
SHORTENED = (f"Your message was longer than {MAX_CHARACTERS:,} characters, so it was shortened and I read only the "
             f"first {MAX_CHARACTERS:,} characters.")
HERE = Path(__file__).resolve().parent


class MessageIn(BaseModel):
    conversation_id: str = Field(pattern=ID)
    message_id: str = Field(pattern=ID)
    text: str = Field(max_length=100_000)


class Reply:
    """One message's reply as it is released: the sentences so far, then the done event's payload (set last).

    Whoever closes it first (the reply thread with the engine's done event, or a fallback) settles its done event;
    a closed reply's turn never starts, and nothing the engine says after it closed is shown."""

    def __init__(self, conversation_id: str, text: str = ""):
        self.conversation_id, self.text = conversation_id, text  # the caller's message, for an error ticket
        self.sentences: list[str] = []
        self.done: dict | None = None
        self.accepted_at = time.monotonic()
        self.closed = False
        self._lock = threading.Lock()

    def begin(self) -> bool:
        """True if the turn may start: nothing has closed the reply yet."""
        with self._lock:
            return not self.closed

    def close(self) -> bool:
        """Claim the right to settle the done event; True only for the first caller."""
        with self._lock:
            if self.closed:
                return False
            self.closed = True
            return True


STEPS = {"start": "getting the details", "offer": "choosing a time", "readback": "confirming the booking",
         "which": "choosing which appointment", "new_date": "choosing a new time"}
CHANGES = [("booked appointment", "customer verified · eligibility checked · booked in one transaction"),
           ("rescheduled appointment", "customer verified · eligibility checked · rescheduled in one transaction"),
           ("cancelled appointment", "customer verified · cancelled in one transaction")]


def proof_receipt(done: DoneEvent) -> str | None:
    """The compact proof shown after a booking change or a handoff (R66); None for anything else."""
    parts = [proof for prefix, proof in CHANGES if any(action.startswith(prefix) for action in done.db_actions)]
    if done.ticket is not None:
        parts.append(f"ticket #{done.ticket} created")
    return " · ".join(parts) or None


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


def behind_fly() -> bool:
    """Fly sets FLY_APP_NAME on its machines, where its proxy writes Fly-Client-IP itself."""
    import os
    return bool(os.environ.get("FLY_APP_NAME"))


REVIEWER_ONLY_NOTE = ("Chat on this demo is open to project reviewers with a reviewer link. You can still look around: "
                      "the test customers, the suggested questions and the Results tab.")


def create_app(engine, store, cookie_secret: str, clock=real_now, limits: Limits | None = None, workers: int = 4,
               stream_timeout_s: float = 40.0, trust_fly_header: bool = False, spend=None,
               reviewer_token: str | None = None, staff_password_hash: str | None = None,
               results_summary_path: Path | None = None, gate=None, alerts=None,
               scheduling_db: Path | None = None, engine_deadline_s: float | None = None) -> FastAPI:
    """trust_fly_header: trust the Fly-Client-IP header for the address limit; anywhere else a client could forge it.
    spend: an app.ops.spend.Spend that each turn's model calls are recorded against and checked before (the engine's
    pipeline asks its guard, app/web/limits.py turn_guard, for a refusal after its safety check). reviewer_token: the secret behind the reviewer link (R85).
    staff_password_hash: the shared staff password's hash (R72); None turns staff sign-in off.
    results_summary_path: the final summary the Results tab shows (default data/results/final/summary.json).
    gate: the reset gate (app/ops/gate.py), held shared for each reply. alerts: checked for an error burst after each
    reply. scheduling_db: the live scheduling file that GET /health opens (R76). engine_deadline_s: the agent's own
    message deadline; a turn starts only while that much time is left before the stream would give up on it."""
    app = FastAPI(title="Meridian Home Comfort chat", docs_url=None, redoc_url=None, openapi_url=None)
    cookies = VisitorCookie(cookie_secret)
    limits = limits or Limits(clock)
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reply")
    replies: OrderedDict[tuple[str, str], Reply] = OrderedDict()  # this process's replies, newest last
    registry_lock = threading.Lock()
    replay_lock = threading.Lock()  # one restart replay (and its ticket) per message
    conversation_locks: dict[str, threading.Lock] = {}
    app.state.executor = executor
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    chat_page = (HERE / "templates" / "chat.html").read_text().replace(
        "<!-- staff panel -->", (HERE / "templates" / "staff_panel.html").read_text())
    if spend is not None and spend.per_visitor <= 0:  # reviewer-only (D50): say why a public message is refused
        chat_page = chat_page.replace('<p class="greeting">', '<p class="notice">' + REVIEWER_ONLY_NOTE + '</p>\n    <p class="greeting">', 1)
    app.include_router(reviewer_routes(store, reviewer_token))
    app.include_router(staff_routes(store, cookie_secret, staff_password_hash, clock, trust_fly_header))
    app.include_router(results_routes(store, clock, results_summary_path))
    if scheduling_db is not None:
        app.include_router(health_routes(store, scheduling_db))

    @app.get("/", response_class=HTMLResponse)
    def chat():
        return HTMLResponse(chat_page)

    @app.middleware("http")
    async def visitor(request: Request, call_next):
        visitor_id = cookies.read(request.cookies.get(COOKIE))
        issued = None
        if visitor_id is None:
            visitor_id, issued = cookies.issue()
        request.state.visitor_id = visitor_id
        response = await call_next(request)
        if issued:
            VisitorCookie.set_on(response, issued)
        return response

    def lock_for(conversation_id: str) -> threading.Lock:
        with registry_lock:
            return conversation_locks.setdefault(conversation_id, threading.Lock())

    def quietly(write, *args) -> None:
        try:
            write(*args)
        except Exception as error:
            log.error("operations write failed (%s): %s", getattr(write, "__name__", "write"), error)

    def finish(reply: Reply, message_id: str, done: DoneEvent) -> None:
        payload = {"route": done.route, "ticket": done.ticket, "outcome": done.outcome, "proof": proof_receipt(done)}
        quietly(store.save_reply_end, reply.conversation_id, message_id, list(reply.sentences), payload)
        reply.done = payload  # last: the stream reads it before the sentences

    overflow = {"day": None, "ticket": None}
    overflow_lock = threading.Lock()

    def overflow_ticket(text: str) -> int | None:
        """The day's merged emergency ticket for reports past the site-wide ceiling, with one alert; each report is
        added to it. Never raises: the caller already has the safety advice."""
        try:
            with overflow_lock:
                today = clock().date()
                if overflow["day"] != today:
                    overflow["day"] = today
                    overflow["ticket"] = store.create_ticket(None, "several callers", "emergency reports past the daily "
                                                             "ceiling; see the constraints", "fixed safety advice given",
                                                             "", "calm", "emergency")
                    if alerts:
                        alerts.send("safety overflow", "emergency reports passed the daily ceiling; merged into "
                                                       f"Ticket #{overflow['ticket']}")
                store.add_reason(overflow["ticket"], "", text[:200])
                return overflow["ticket"]
        except Exception as error:
            log.error("overflow emergency ticket not saved: %s", error)
            return None

    def settle(reply: Reply, sentence: str | list[str], done: DoneEvent) -> None:
        """A reply worked out here without the agent (a blank or refused message): kept in memory only, no rows."""
        reply.close()
        reply.sentences.extend([sentence] if isinstance(sentence, str) else sentence)
        reply.done = {"route": done.route, "ticket": done.ticket, "outcome": done.outcome, "proof": None}

    def error_ticket(conversation_id: str, text: str, detail: str) -> int | None:
        """An "error" handoff ticket for a reply that could not be finished, as app/handoff/flow.py hand_off opens."""
        who = None
        try:
            row = store.conversation(conversation_id)
            who = json.loads(row["flow_state"] or "{}").get("who") if row else None
        except Exception:
            pass
        try:
            return store.create_ticket(conversation_id, who or "caller not identified", text or "not stated",
                                       "nothing yet", detail, "calm", "error")
        except Exception as error:
            log.error("error ticket could not be saved for conversation %s: %s", conversation_id, error)
            quietly(store.log_event, "write failure", f"ticket not saved: error: {error}", conversation_id)
            return None

    def fall_back(reply: Reply, message_id: str, detail: str, outcome: str) -> None:
        """End the reply with the plain handoff message and its error ticket, once per message."""
        if not reply.close():
            return
        quietly(store.log_event, "error", detail, reply.conversation_id)
        ticket = error_ticket(reply.conversation_id, reply.text, detail)
        reply.sentences.append(ERROR_MESSAGE if ticket is not None else NO_TICKET_MESSAGE)
        finish(reply, message_id, DoneEvent(route="unknown", ticket=ticket, outcome=outcome))

    def remember(key: tuple[str, str], reply: Reply) -> None:
        """Keep this reply for its stream; finished ones beyond the newest thousand are replayed from the store."""
        replies[key] = reply
        for old in [k for k, r in replies.items() if r.done is not None][:max(0, len(replies) - KEEP_REPLIES)]:
            del replies[old]

    def from_end(end: dict) -> Reply:
        reply = Reply("")
        reply.sentences, reply.done, reply.closed = end["sentences"], end["done"], True
        return reply

    def saved_reply(visitor_id: str, message_id: str) -> Reply | None:
        """A reply from the store: finished, or left unfinished by a restart (accepted, or part-way through), which
        becomes a plain handoff with an error ticket (R59)."""
        end = store.reply_end(visitor_id, message_id)
        if end:
            return from_end(end)
        with replay_lock:
            end = store.reply_end(visitor_id, message_id)  # another stream may have just replayed it
            if end:
                return from_end(end)
            request = store.request_reply(visitor_id, message_id)
            if request is None:
                return None
            agent, conversation_id = request["agent_message_id"], request["conversation_id"]
            reply = Reply(conversation_id, request["caller_text"] or store.accepted_text(conversation_id, message_id) or "")
            reply.sentences = store.sentences(agent) if agent else []
            fall_back(reply, message_id, "reply left unfinished by a restart", "incomplete")
            return reply

    def out_of_time(reply: Reply) -> bool:
        """Too little time is left for the agent's whole deadline before the stream would give up."""
        if engine_deadline_s is None:
            return False
        return stream_timeout_s - (time.monotonic() - reply.accepted_at) < engine_deadline_s

    def process(reply: Reply, turn: Turn, shortened: bool, limit: str | None) -> None:
        with lock_for(turn.conversation_id):  # one message at a time per conversation
            done, failure = None, None
            with gate.shared() if gate else nullcontext():  # waits while the nightly reset runs (R74)
                if not reply.begin():
                    return  # the stream gave up while this waited, and opened its ticket: never act now
                if out_of_time(reply):
                    fall_back(reply, turn.message_id, "the reply could not start in time", "incomplete")
                    return
                if shortened:
                    reply.sentences.append(SHORTENED)
                # This reply thread's model calls count against the visitor's budget (R61), each checked before it
                # is made; the message limit it hit is the pipeline guard's (asked after safety). All are reset
                # after the turn, so a reused thread never keeps them.
                recorder = spend.recorder(turn.visitor_id) if spend else None
                tokens = (SINK.set(recorder), PRE_CALL.set(recorder.before if recorder else None),
                          TURN_LIMIT.set(limit))
                try:
                    for event in engine.handle(turn):
                        if isinstance(event, SentenceEvent):
                            if not reply.closed:  # after a fallback, nothing more is shown
                                reply.sentences.append(event.text)
                        elif isinstance(event, DoneEvent):
                            done = event
                            break
                except Exception as error:  # the engine ends every turn itself; this is the last resort
                    log.exception("reply failed for conversation %s: %s", turn.conversation_id, error)
                    failure = f"reply failed: {type(error).__name__}: {error}"
                finally:
                    SINK.reset(tokens[0])
                    PRE_CALL.reset(tokens[1])
                    TURN_LIMIT.reset(tokens[2])
            if done is None:
                fall_back(reply, turn.message_id, failure or "the reply ended without a done event", "error")
            elif reply.close():
                finish(reply, turn.message_id, done)
            if alerts:
                alerts.check_errors()

    def needs_safety_reply(conversation_id: str, text: str) -> str | None:
        """The safety kind the agent's own check (R34) finds, on the same history, so a refused message reporting a
        danger still reaches it; None when clear. Only reads; if it cannot read, "danger" (the agent's guard still
        refuses anything but the safety reply)."""
        try:
            row = store.conversation(conversation_id)
            text = text.replace("\u2019", "'").replace("\u2018", "'")
            if row is None:
                kind = safety_check(text, []).kind
            else:
                burning = bool(json.loads(row["flow_state"] or "{}").get("burning_mentioned"))
                earlier = [m["content"] for m in store.history(conversation_id, 20) if m["role"] == "caller"]
                kind = safety_check(text, earlier, burning).kind
            return None if kind == "clear" else kind
        except Exception as error:
            log.error("safety pre-check failed, passing the message to the agent: %s", error)
            return "danger"

    @app.post("/api/message", status_code=202)
    def message(body: MessageIn, request: Request):
        visitor_id = request.state.visitor_id
        row = store.conversation(body.conversation_id)  # only read: nothing is written for a refused message
        if row is not None and row["visitor_id"] != visitor_id:
            raise HTTPException(404, "conversation not found")
        key = (visitor_id, body.message_id)
        accepted = {"message_id": body.message_id}
        text = body.text[:MAX_CHARACTERS]  # cut before the engine, so the router never sees more
        with registry_lock:  # the same message sent twice, even across a restart: one reply
            if key in replies or store.reply_end(*key) or store.request_reply(*key):
                return accepted
            reply = Reply(body.conversation_id, text)
            remember(key, reply)
        if not body.text.strip():  # nothing to answer: no engine call, no limit counted, nothing written
            settle(reply, TELL_ME_MORE, DoneEvent(route="none", ticket=None, outcome="answered"))
            return accepted
        peer = request.client.host if request.client else None
        address = (request.headers.get("fly-client-ip") or peer) if trust_fly_header else peer
        limit = limits.allow(visitor_id, address)
        if limit:
            danger = needs_safety_reply(body.conversation_id, text)
            if not danger:
                settle(reply, LIMIT_MESSAGE, DoneEvent(route="limit", ticket=None, outcome="limit"))
                return accepted
            allowed = limits.allow_safety(visitor_id, address)
            if allowed == "advice":  # this visitor or network used its allowance: the advice, no ticket, no rows
                settle(reply, fixed_reply(danger, text), DoneEvent(route="safety", ticket=None, outcome="safety"))
                return accepted
            if allowed == "overflow":  # the site-wide ceiling: the advice, and the report joins one merged ticket
                settle(reply, fixed_reply(danger, text), DoneEvent(route="safety", ticket=overflow_ticket(text),
                                                                   outcome="safety"))
                return accepted
        try:
            store.open_conversation(visitor_id, body.conversation_id)
            owner = store.conversation(body.conversation_id)
            if owner is None or owner["visitor_id"] != visitor_id:  # opened by another visitor a moment ago
                raise HTTPException(404, "conversation not found")
            store.accept_message(body.conversation_id, body.message_id, text)  # before the work: survives a restart
        except BaseException:
            with registry_lock:
                replies.pop(key, None)
            raise
        executor.submit(process, reply, Turn(body.conversation_id, visitor_id, body.message_id, text),
                        len(body.text) > MAX_CHARACTERS, limit)
        return accepted

    @app.get("/api/conversation/{conversation_id}")
    def conversation(conversation_id: str, request: Request):
        """A reloaded tab's conversation so far and the booking step in progress, if any (R82)."""
        row = store.conversation(conversation_id)
        if row is None or row["visitor_id"] != request.state.visitor_id:
            raise HTTPException(404, "conversation not found")
        flow = (json.loads(row["flow_state"] or "{}").get("flow") or {}) if row["active_flow"] else {}
        step = flow.get("step")
        label = None
        if row["active_flow"] == "scheduling":
            label = "Booking in progress" + (f": {STEPS[step]}" if step in STEPS else "")
        return {"conversation_id": conversation_id, "status": row["status"], "active_flow": row["active_flow"],
                "step": step, "step_label": label, "messages": saved_messages(request.state.visitor_id, conversation_id)}

    def saved_messages(visitor_id: str, conversation_id: str) -> list[dict]:
        """The last 200 messages; each reply also comes with the sentences it was shown as and its proof, from the
        saved reply end of the caller message before it, so a reload looks as the reply did."""
        rows = store.read("select role, text_masked, request_id from messages where conversation_id = ? and "
                          "text_masked != '' order by message_id desc limit 200", (conversation_id,))
        messages, request_id = [], None
        for m in reversed(rows):
            message = {"role": m["role"], "text": m["text_masked"]}
            if m["role"] == "caller":
                request_id = m["request_id"]
            else:
                end = store.reply_end(visitor_id, request_id) if request_id else None
                message["sentences"] = end["sentences"] if end else [m["text_masked"]]
                message["proof"] = end["done"].get("proof") if end else None
                request_id = None
            messages.append(message)
        return messages

    @app.get("/api/stream/{message_id}")
    async def sentence_stream(message_id: str, request: Request):
        key = (request.state.visitor_id, message_id)
        with registry_lock:
            reply = replies.get(key)
        if reply is None:
            reply = await asyncio.to_thread(saved_reply, *key)
        if reply is None:
            raise HTTPException(404, "message not found")

        async def events():
            sent, waited, pause, gave_up = 0, 0.0, 0.002, False
            while True:
                done = reply.done  # read before the sentences: it is set only after the last one
                while sent < len(reply.sentences):
                    yield _sse("sentence", {"text": reply.sentences[sent]})
                    sent += 1
                if done is not None:
                    yield _sse("done", done)
                    return
                if waited >= stream_timeout_s and not gave_up:
                    # The turn is closed: if it has not started it never will, and its ticket is opened now.
                    await asyncio.to_thread(fall_back, reply, message_id, "the reply did not finish in time",
                                            "incomplete")
                    gave_up = True
                    continue
                await asyncio.sleep(pause)
                waited += pause
                pause = min(pause * 2, 0.05)  # quick at first, then every 50 milliseconds

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return app


def build_app() -> FastAPI:
    """The real app, wired as the terminal chat and eval/run.py wire the agent; never used by the tests.

    Run with one worker: uvicorn app.web.main:build_app --factory --workers 1 (needs ANTHROPIC_API_KEY,
    VOYAGE_API_KEY and VISITOR_COOKIE_SECRET in the environment; REVIEWER_TOKEN turns on the reviewer link and
    STAFF_PASSWORD_HASH the staff sign-in; ALERT_WEBHOOK_URL sends alerts)."""
    import anthropic

    from app.config import SETTINGS
    from app.core.engine import Engine
    from app.core.model_log import RecordingClient
    from app.core.pipeline import AgentPipeline
    from app.knowledge.embedder import VoyageEmbedder
    from app.knowledge.index import load_index
    from app.knowledge.search import Searcher
    from app.ops.alerts import Alerts
    from app.ops.gate import ResetGate
    from app.ops.jobs import Scheduler
    from app.ops.spend import Spend
    from app.ops.store import OpsStore
    from app.replies.money_check import MoneyCheck
    from app.replies.writer import write
    from app.routing.router import route
    from app.web.reviewer import token_from_environment
    from app.web.staff import password_hash_from_environment
    from app.web.limits import turn_guard
    from app.web.visitor import secret_from_environment

    secret = secret_from_environment()
    for path in (SETTINGS.scheduling_db_path, SETTINGS.ops_db_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS.scheduling_db_path.exists():  # the first start: the live copy begins as the seed
        shutil.copy(SETTINGS.seed_db_path, SETTINGS.scheduling_db_path)
    store = OpsStore(SETTINGS.ops_db_path)
    alerts = Alerts.from_environment(store)
    alerts.watch(store)
    spend = Spend(store, notify=lambda detail: alerts.send("spend", detail))
    gate = ResetGate()
    Scheduler(SETTINGS.scheduling_db_path, SETTINGS.seed_db_path, store, gate, alerts).start()  # resets if missed
    client = RecordingClient(anthropic.Anthropic(timeout=SETTINGS.anthropic_timeout_s, max_retries=1),
                             sdk_version=f"anthropic {anthropic.__version__}")
    chunks, embeddings = load_index(Path(__file__).resolve().parents[2] / "data" / "index")
    pipeline = AgentPipeline(store=store, scheduling_db=SETTINGS.scheduling_db_path, seed_db=SETTINGS.seed_db_path,
                             searcher=Searcher(chunks, VoyageEmbedder(input_type="query"), embeddings),
                             route_fn=lambda text, history: route(text, history, client),
                             writer=lambda reply_type, facts, history: write(reply_type, facts, history, client),
                             threshold=SETTINGS.retrieval_threshold, money_check=MoneyCheck(client),
                             guard=turn_guard(spend))  # asked after the safety check, so emergencies always get through
    return create_app(Engine(pipeline), store, cookie_secret=secret, trust_fly_header=behind_fly(), spend=spend,
                      reviewer_token=token_from_environment(),
                      staff_password_hash=password_hash_from_environment(), gate=gate, alerts=alerts,
                      scheduling_db=SETTINGS.scheduling_db_path, engine_deadline_s=SETTINGS.message_deadline_s)
