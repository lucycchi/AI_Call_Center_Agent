"""The Staff view (R70 to R72): the panel beside the chat, the shared staff password, the staff session, the
all-visitors queue and the flag-a-reply control.

Any visitor's panel shows only their own tickets and their own conversation's reply receipts, plus today's live
numbers. The shared password unlocks the full queue, any conversation's receipts and flagging.

- The password is stored only as a hash, in the STAFF_PASSWORD_HASH environment variable (a Fly.io secret), in the
  format pbkdf2_sha256$<iterations>$<salt, base64>$<hash, base64> (PBKDF2-HMAC-SHA256, 32-byte hash). Make one with
  `python -m app.web.staff` (it asks for the password and prints the hash; nothing is stored).
- A correct password starts a 12-hour staff session: a signed cookie separate from the visitor cookie, HttpOnly,
  Secure, SameSite=Strict, holding a random session id and the time it started.
- Sign-in attempts are limited per client address (Fly-Client-IP only behind Fly's proxy): after 5 wrong passwords
  in 15 minutes every attempt is refused until the oldest of them is 15 minutes old.
- Flags need a form token: an HMAC of the staff session id, returned in the panel and checked on every flag.
- Every string in every Staff view response is masked again (phone numbers, emails and street addresses), on top of
  the masking the store applies when it writes. Receipts carry plain labels only, never scores or prompt text.
Nothing here ever logs a password, hash, cookie or form token."""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from collections import deque
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field

from app.config import AUSTIN
from app.ops.masking import mask
from app.ops.metrics import live_numbers

log = logging.getLogger("meridian.staff")
HASH_VARIABLE = "STAFF_PASSWORD_HASH"
STAFF_COOKIE = "meridian_staff"
SESSION = timedelta(hours=12)
ATTEMPT_WINDOW = timedelta(minutes=15)
WRONG_ATTEMPTS_ALLOWED = 5
ITERATIONS = 600_000
ID = r"^[A-Za-z0-9_-]{1,64}$"
PRIORITY_LABELS = {2: "urgent", 1: "normal", 0: "low"}
SAFETY_LABELS = {"clear": "no safety concern", "danger": "emergency: safety instructions given first",
                 "burning": "burning smell: safety instructions given first",
                 "urgent": "urgent: safety instructions given first"}
LIMIT_REASON = "message or spending limit reached"


# -- the password hash --------------------------------------------------------------------------------------------

def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    encode = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"pbkdf2_sha256${iterations}${encode(salt)}${encode(digest)}"


def password_matches(password: str, stored: str | None) -> bool:
    try:
        scheme, iterations, salt, expected = (stored or "").split("$")
        if scheme != "pbkdf2_sha256" or not 1 <= int(iterations) <= 10_000_000:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def password_hash_from_environment() -> str | None:
    return os.environ.get(HASH_VARIABLE) or None


# -- sign-in limit -------------------------------------------------------------------------------------------------

class SignInLimit:
    """Wrong passwords per client address in the last 15 minutes, kept in memory (the app runs one worker)."""

    def __init__(self, clock):
        self.clock = clock
        self._lock = threading.Lock()
        self._wrong: dict[str, deque] = {}

    def _recent(self, key: str, now: datetime) -> deque:
        times = self._wrong.setdefault(key, deque())
        while times and times[0][0] <= now - ATTEMPT_WINDOW:
            times.popleft()
        return times

    def reserve(self, key: str):
        """Count an attempt before the slow password check, so parallel guesses cannot all pass; None when locked."""
        with self._lock:
            now, times = self.clock(), None
            times = self._recent(key, now)
            if len(times) >= WRONG_ATTEMPTS_ALLOWED:
                return None
            entry = (now, secrets.token_hex(4))
            times.append(entry)
            return entry

    def release(self, key: str, entry) -> None:
        """A correct password gives its attempt back."""
        with self._lock:
            times = self._wrong.get(key)
            if times and entry in times:
                times.remove(entry)


# -- shaping what the panel shows ----------------------------------------------------------------------------------

# Fields the server generates itself, never caller text: masking could break them (a form token starting with ten
# digits reads as a phone number), so they are passed through unchanged.
SERVER_TOKENS = frozenset({"form_token"})


def masked(value):
    """Every string in a response, masked again: nothing unmasked reaches the Staff view (but server tokens)."""
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, list):
        return [masked(v) for v in value]
    if isinstance(value, dict):
        return {k: v if k in SERVER_TOKENS else masked(v) for k, v in value.items()}
    return value


def sign_form(key: bytes, sid: str) -> str:
    """The form token for a staff session: an HMAC of its id."""
    return hmac.new(key, sid.encode("utf-8"), hashlib.sha256).hexdigest()


def _when(stamp: str) -> datetime:
    moment = datetime.fromisoformat(stamp)
    return moment if moment.tzinfo else moment.replace(tzinfo=AUSTIN)


def _list(raw: str | None) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(v) for v in values] if isinstance(values, list) else []


def ticket_view(store, row: dict) -> dict:
    return {"ticket_id": row["ticket_id"], "conversation_id": row["conversation_id"], "who": row["who"],
            "wants": row["wants"], "tried": row["tried"], "constraints": row["constraints"], "mood": row["mood"],
            "tags": store.ticket_tags(row["ticket_id"]), "priority": row["priority"],
            "priority_label": PRIORITY_LABELS.get(row["priority"], "normal"), "status": row["status"],
            "created_at": row["created_at"], "messages": store.ticket_messages(row["ticket_id"]),
            "conversation": store.ticket_conversation(row["ticket_id"])}


def replies_view(store, conversation_id: str) -> list[dict]:
    """Each agent reply with its "How this reply was made" receipt: plain labels, the dated passages, documents
    excluded as stale, the database action and the handoff reason. Never a score, never prompt text."""
    messages = store.agent_messages(conversation_id)
    tickets = store.conversation_tickets(conversation_id)
    shown = []
    for index, message in enumerate(messages):
        start = _when(message["created_at"])
        end = _when(messages[index + 1]["created_at"]) if index + 1 < len(messages) else None
        receipt = None
        if message["has_receipt"]:
            label = message["outcome_label"] or "answered"
            opened = [t for t in tickets if start <= _when(t["created_at"]) and (end is None or _when(t["created_at"]) < end)]
            reason, ticket_id = None, None
            if opened:
                reason, ticket_id = ", ".join(store.ticket_tags(opened[-1]["ticket_id"])), opened[-1]["ticket_id"]
            elif label == "handoff required":
                earlier = [t for t in tickets if _when(t["created_at"]) < start]
                if message["route"] == "limit":
                    reason = LIMIT_REASON
                elif earlier:
                    reason, ticket_id = ", ".join(store.ticket_tags(earlier[-1]["ticket_id"])), earlier[-1]["ticket_id"]
                else:
                    reason = message["route"]
            safety = message["safety_result"] or "clear"
            receipt = {"safety": SAFETY_LABELS.get(safety, safety), "route": message["route"],
                       "passages": _list(message["passages"]), "excluded": _list(message["excluded"]),
                       "db_action": message["db_action"] or "none", "handoff_reason": reason, "ticket": ticket_id,
                       "label": label}
        shown.append({"message_id": message["message_id"], "text": message["text_masked"],
                      "created_at": message["created_at"], "receipt": receipt})
    return shown


# -- routes --------------------------------------------------------------------------------------------------------

class LoginIn(BaseModel):
    password: str = Field(max_length=256)


class FlagIn(BaseModel):
    message_id: int
    correction: str = Field(default="", max_length=2000)
    token: str = Field(default="", max_length=200)


def staff_routes(store, cookie_secret: str, password_hash: str | None, clock, trust_fly_header: bool = False) -> APIRouter:
    router = APIRouter()
    limit = SignInLimit(clock)
    if password_hash and not password_hash.startswith("pbkdf2_sha256$"):
        log.warning("%s is not in the pbkdf2_sha256 format, so staff sign-in is off", HASH_VARIABLE)
        password_hash = None
    # Sessions are bound to the current password: changing it ends every session.
    bound = hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]
    signer = URLSafeSerializer(cookie_secret, salt=f"meridian-staff:{bound}")
    token_key = hashlib.sha256(b"meridian-staff-form:" + bound.encode() + cookie_secret.encode("utf-8")).digest()

    def sid_key(sid: str) -> str:
        # Letters only: the event log masks digit runs that look like phone numbers.
        return hashlib.sha256(sid.encode()).hexdigest().translate(str.maketrans("0123456789", "ghijklmnop"))

    def ended(sid: str) -> bool:
        """A session logged out on the server, kept in the events table so it stays ended after a restart."""
        return bool(store.read("select 1 from events where kind = 'staff session ended' and detail = ?",
                               (sid_key(sid),)))

    def session_id(request: Request) -> str | None:
        """The id of a valid, unexpired staff session, or None."""
        try:
            data = signer.loads(request.cookies.get(STAFF_COOKIE) or "")
            started = datetime.fromisoformat(data["started"])
        except (BadSignature, KeyError, TypeError, ValueError):
            return None
        now = clock()
        if not isinstance(data.get("sid"), str) or not (now - SESSION < started <= now + timedelta(minutes=5)):
            return None
        return None if ended(data["sid"]) else data["sid"]

    def form_token(sid: str) -> str:
        return sign_form(token_key, sid)

    def address(request: Request) -> str:
        peer = request.client.host if request.client else None
        found = (request.headers.get("fly-client-ip") or peer) if trust_fly_header else peer
        return found or f"visitor:{request.state.visitor_id}"

    def staff_only(request: Request) -> str:
        sid = session_id(request)
        if sid is None:
            raise HTTPException(403, "staff session required")
        return sid

    @router.post("/api/staff/login")
    def staff_login(body: LoginIn, request: Request, response: Response):
        key = address(request)
        attempt = limit.reserve(key)
        if attempt is None:
            raise HTTPException(429, "too many sign-in attempts; try again in 15 minutes")
        if not password_hash:
            limit.release(key, attempt)
            raise HTTPException(503, "staff sign-in is not set up")
        if not password_matches(body.password, password_hash):
            log.info("wrong staff password from one address")
            raise HTTPException(401, "wrong password")
        limit.release(key, attempt)
        sid = secrets.token_urlsafe(24)
        response.set_cookie(STAFF_COOKIE, signer.dumps({"sid": sid, "started": clock().isoformat()}),
                            max_age=int(SESSION.total_seconds()), httponly=True, secure=True, samesite="strict",
                            path="/")
        log.info("staff session started")
        return {"staff": True, "form_token": form_token(sid)}

    @router.post("/api/staff/logout")
    def staff_logout(request: Request, response: Response):
        sid = session_id(request)
        if sid is not None:  # ended on the server too, so a copied cookie stops working
            store.log_event("staff session ended", sid_key(sid))
        response.delete_cookie(STAFF_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return {"staff": False}

    @router.get("/api/staff/panel")
    def panel(request: Request, conversation_id: str | None = None, seen: int = 0):
        sid = session_id(request)
        visitor_id = request.state.visitor_id
        tickets = [ticket_view(store, row) for row in store.tickets_for_visitor(visitor_id)]
        replies = []
        if conversation_id:
            row = store.conversation(conversation_id)
            if row is None or (row["visitor_id"] != visitor_id and sid is None):
                raise HTTPException(404, "conversation not found")
            replies = replies_view(store, conversation_id)
        return masked({"staff": sid is not None, "form_token": form_token(sid) if sid else None,
                       "tickets": tickets, "new_tickets": sum(1 for t in tickets if t["ticket_id"] > seen),
                       "latest_ticket_id": max((t["ticket_id"] for t in tickets), default=0),
                       "numbers": live_numbers(store, clock().astimezone(AUSTIN).date()),
                       "conversation_id": conversation_id, "replies": replies})

    @router.get("/api/staff/queue")
    def queue(request: Request):
        staff_only(request)
        return masked({"tickets": [ticket_view(store, row) for row in reversed(store.tickets())]})

    @router.post("/api/staff/flag")
    def flag(body: FlagIn, request: Request):
        sid = staff_only(request)
        if not body.token or not hmac.compare_digest(body.token, form_token(sid)):
            raise HTTPException(403, "form token missing or wrong")
        message = store.message(body.message_id)
        if message is None or message["role"] != "agent":
            raise HTTPException(404, "reply not found")
        flag_id = store.add_flag(body.message_id, body.correction)
        return {"flag_id": flag_id}

    return router


if __name__ == "__main__":  # python -m app.web.staff: print a hash for STAFF_PASSWORD_HASH
    import getpass

    print(hash_password(getpass.getpass("Staff password: ")))
