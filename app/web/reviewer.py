"""The secret reviewer link (R85, D34): https://<app>/#r=<token>. The token sits after the #, so the browser never
sends it in a request line and it never reaches Fly's or the app's request logs; reviewer.js posts it once in a
request body and clears it from the address.

The token is a secret in the environment (REVIEWER_TOKEN, a Fly.io secret), compared in constant time. The right
token marks the signed visitor as a reviewer (their visitor id is in the signed cookie), so their spending draws on
the reviewer reserve. The link is reusable (D50): every browser that opens it gets a reviewer session, and the shared
$3-a-day reserve and the key's console limit cap what it can spend. The token is never stored. A wrong or malformed
token, or no configured token, is a plain 404. Nothing here ever logs the token or the request body."""

import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger("meridian.reviewer")
TOKEN_VARIABLE = "REVIEWER_TOKEN"
MIN_LENGTH = 16
MAX_BODY = 1024


def token_from_environment() -> str | None:
    return os.environ.get(TOKEN_VARIABLE) or None


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def reviewer_routes(store, token: str | None) -> APIRouter:
    """token: the reviewer link's token (several, separated by commas, are also accepted)."""
    router = APIRouter()
    tokens = [t.strip() for t in (token or "").split(",") if t.strip()]
    if any(len(t) < MIN_LENGTH for t in tokens):
        log.warning("a reviewer token is shorter than %d characters, so that link is off", MIN_LENGTH)
    digests = [_digest(t) for t in tokens if len(t) >= MIN_LENGTH]

    def not_found():
        return HTTPException(404, "not found")

    @router.post("/api/reviewer")
    async def reviewer(request: Request):
        body = await request.body()
        if not digests or len(body) > MAX_BODY:
            raise not_found()
        try:
            supplied = json.loads(body).get("token")
        except (ValueError, AttributeError):
            raise not_found() from None
        if not isinstance(supplied, str):
            raise not_found()
        given = _digest(supplied)
        # Every configured token is compared, so the time taken says nothing about which one matched.
        matches = [d for d in digests if hmac.compare_digest(given, d)]
        if not matches:
            raise not_found()
        store.make_reviewer(request.state.visitor_id)
        log.info("reviewer session started for visitor %s", request.state.visitor_id)
        return {"reviewer": True}

    return router
