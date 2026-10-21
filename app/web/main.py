"""The web layer (R62, R64 to R66): the chat page, message requests and the sentence stream.

Each caller message is an ordinary request (POST /api/message) that returns 202 at once; the reply is worked out in a
background thread, one message at a time per conversation, and its checked sentences are pushed to the stream for
that message id (GET /api/stream/{message_id}) as the engine releases them, then a done event. The app is built by
create_app with the engine and operations store passed in, so tests use fakes; build_app wires the real agent."""

import asyncio
import json
import logging
import shutil
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import real_now
from app.core.model_log import SINK
from app.core.state import ConversationState, NotYourConversation
from app.core.types import DoneEvent, SentenceEvent, Turn
from app.handoff.flow import ERROR_MESSAGE
from app.web.health import health_routes
from app.web.limits import LIMIT_MESSAGE, Limits
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
    """One message's reply as it is released: the sentences so far, then the done event's payload (set last)."""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.sentences: list[str] = []
        self.done: dict | None = None


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


def create_app(engine, store, cookie_secret: str, clock=real_now, limits: Limits | None = None, workers: int = 4,
               stream_timeout_s: float = 40.0, trust_fly_header: bool = False, spend=None,
               reviewer_token: str | None = None, staff_password_hash: str | None = None, gate=None, alerts=None,
               scheduling_db: Path | None = None) -> FastAPI:
    """trust_fly_header: trust the Fly-Client-IP header for the address limit; anywhere else a client could forge it.
    spend: an app.ops.spend.Spend that each turn's model calls are recorded against (the engine's pipeline asks it
    for a refusal after its safety check). reviewer_token: the secret behind the reviewer link (R85).
    staff_password_hash: the shared staff password's hash (R72); None turns staff sign-in off.
    gate: the reset gate (app/ops/gate.py), held shared for each reply. alerts: checked for an error burst after each
    reply. scheduling_db: the live scheduling file that GET /health opens (R76)."""
    app = FastAPI(title="Meridian Home Comfort chat", docs_url=None, redoc_url=None, openapi_url=None)
    cookies = VisitorCookie(cookie_secret)
    limits = limits or Limits(clock)
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reply")
    replies: OrderedDict[tuple[str, str], Reply] = OrderedDict()  # this process's replies, newest last
    registry_lock = threading.Lock()
    conversation_locks: dict[str, threading.Lock] = {}
    app.state.executor = executor
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    chat_page = (HERE / "templates" / "chat.html").read_text().replace(
        "<!-- staff panel -->", (HERE / "templates" / "staff_panel.html").read_text())
    app.include_router(reviewer_routes(store, reviewer_token))
    app.include_router(staff_routes(store, cookie_secret, staff_password_hash, clock, trust_fly_header))
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

    def remember(key: tuple[str, str], reply: Reply) -> None:
        """Keep this reply for its stream; finished ones beyond the newest thousand are replayed from the store."""
        replies[key] = reply
        for old in [k for k, r in replies.items() if r.done is not None][:max(0, len(replies) - KEEP_REPLIES)]:
            del replies[old]

    def saved_reply(visitor_id: str, message_id: str) -> Reply | None:
        """A reply from the store: finished, or left unfinished by a restart, which becomes a plain handoff (R59)."""
        end = store.reply_end(visitor_id, message_id)
        if end:
            reply = Reply("")
            reply.sentences, reply.done = end["sentences"], end["done"]
            return reply
        request = store.request_reply(visitor_id, message_id)
        if request is None:
            return None
        agent = request["agent_message_id"]
        reply = Reply(request["conversation_id"])
        reply.sentences = (store.sentences(agent) if agent else []) + [ERROR_MESSAGE]
        quietly(store.log_event, "error", "reply left unfinished by a restart", request["conversation_id"])
        finish(reply, message_id, DoneEvent(route="unknown", ticket=None, outcome="incomplete"))
        return reply

    def process(reply: Reply, turn: Turn, shortened: bool) -> None:
        with lock_for(turn.conversation_id):  # one message at a time per conversation
            done = None
            if shortened:
                reply.sentences.append(SHORTENED)
            # This reply thread's model calls count against the visitor's budget (R61); reset after the turn, so a
            # reused thread never keeps it. The pipeline passes each call on to this sink as it records it.
            sink = SINK.set(spend.recorder(turn.visitor_id) if spend else None)
            try:
                with gate.shared() if gate else nullcontext():  # waits while the nightly reset runs (R74)
                    for event in engine.handle(turn):
                        if isinstance(event, SentenceEvent):
                            reply.sentences.append(event.text)
                        elif isinstance(event, DoneEvent):
                            done = event
                            break
            except Exception as error:  # the engine ends every turn itself; this is the last resort
                log.exception("reply failed for conversation %s: %s", turn.conversation_id, error)
            finally:
                SINK.reset(sink)
            if alerts:
                alerts.check_errors()
            if done is None:
                reply.sentences.append(ERROR_MESSAGE)
                done = DoneEvent(route="unknown", ticket=None, outcome="error")
            finish(reply, turn.message_id, done)

    @app.post("/api/message", status_code=202)
    def message(body: MessageIn, request: Request):
        visitor_id = request.state.visitor_id
        try:
            ConversationState.load(store, body.conversation_id, visitor_id)  # opens a new conversation for this visitor
        except NotYourConversation:
            raise HTTPException(404, "conversation not found") from None
        key = (visitor_id, body.message_id)
        accepted = {"message_id": body.message_id}
        with registry_lock:  # the same message sent twice, even across a restart: one reply
            if key in replies or store.reply_end(*key) or store.request_reply(*key):
                return accepted
            reply = Reply(body.conversation_id)
            remember(key, reply)
        if not body.text.strip():  # nothing to answer: no engine call, no limit counted
            reply.sentences.append(TELL_ME_MORE)
            finish(reply, body.message_id, DoneEvent(route="none", ticket=None, outcome="answered"))
            return accepted
        peer = request.client.host if request.client else None
        address = (request.headers.get("fly-client-ip") or peer) if trust_fly_header else peer
        if limits.allow(visitor_id, address):
            reply.sentences.append(LIMIT_MESSAGE)
            finish(reply, body.message_id, DoneEvent(route="limit", ticket=None, outcome="limit"))
            return accepted
        text = body.text[:MAX_CHARACTERS]  # cut before the engine, so the router never sees more
        executor.submit(process, reply, Turn(body.conversation_id, visitor_id, body.message_id, text),
                        len(body.text) > MAX_CHARACTERS)
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
                "step": step, "step_label": label,
                "messages": [{"role": m["role"], "text": m["content"]} for m in store.history(conversation_id, 200)]}

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
            sent, waited, pause = 0, 0.0, 0.002
            while True:
                done = reply.done  # read before the sentences: it is set only after the last one
                while sent < len(reply.sentences):
                    yield _sse("sentence", {"text": reply.sentences[sent]})
                    sent += 1
                if done is not None:
                    yield _sse("done", done)
                    return
                if waited >= stream_timeout_s:
                    yield _sse("sentence", {"text": ERROR_MESSAGE})
                    yield _sse("done", {"route": "unknown", "ticket": None, "outcome": "incomplete", "proof": None})
                    return
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
                             guard=spend.refusal)  # asked after the safety check, so emergencies always get through
    return create_app(Engine(pipeline), store, cookie_secret=secret, trust_fly_header=behind_fly(), spend=spend,
                      reviewer_token=token_from_environment(),
                      staff_password_hash=password_hash_from_environment(), gate=gate, alerts=alerts,
                      scheduling_db=SETTINGS.scheduling_db_path)
