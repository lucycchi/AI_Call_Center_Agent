"""The secret reviewer link (R85, D34): https://<app>/#r=<token>. The token sits after the #, so the browser never
sends it in a request line and it never reaches Fly's or the app's request logs; reviewer.js posts it once in a
request body and clears it from the address.

The token is a secret in the environment (REVIEWER_TOKEN, a Fly.io secret), compared in constant time. The right
token, used for the first time, marks the signed visitor as a reviewer (their visitor id is in the signed cookie),
so their spending draws on the reviewer reserve. Only a hash of the token is stored, to remember that it was used,
including across restarts. A wrong, malformed or already used token, or no configured token, is a plain 404.
Nothing here ever logs the token or the request body."""

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
    router = APIRouter()
    if token and len(token) < MIN_LENGTH:
        log.warning("the reviewer token is shorter than %d characters, so the reviewer link is off", MIN_LENGTH)
        token = None
    expected = _digest(token) if token else None

    def not_found():
        return HTTPException(404, "not found")

    @router.post("/api/reviewer")
    async def reviewer(request: Request):
        body = await request.body()
        if expected is None or len(body) > MAX_BODY:
            raise not_found()
        try:
            supplied = json.loads(body).get("token")
        except (ValueError, AttributeError):
            raise not_found() from None
        if not isinstance(supplied, str) or not hmac.compare_digest(_digest(supplied), expected):
            raise not_found()
        if not store.use_token(hashlib.sha256(b"reviewer-link:" + expected).hexdigest()):
            raise not_found()  # the link works once
        store.make_reviewer(request.state.visitor_id)
        log.info("reviewer session started for visitor %s", request.state.visitor_id)
        return {"reviewer": True}

    return router
