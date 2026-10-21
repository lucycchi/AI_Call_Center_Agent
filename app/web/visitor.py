"""The visitor cookie (R62): a random visitor id, signed so it cannot be altered or guessed, HttpOnly, Secure,
SameSite=Lax, valid 7 days. The signing secret comes from the environment (a Fly.io secret in production)."""

import os
import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer

COOKIE = "meridian_visitor"
MAX_AGE_S = 7 * 24 * 3600
SECRET_VARIABLE = "VISITOR_COOKIE_SECRET"


def secret_from_environment() -> str:
    secret = os.environ.get(SECRET_VARIABLE, "")
    if len(secret) < 16:
        raise RuntimeError(f"{SECRET_VARIABLE} must be set to a random value of at least 16 characters")
    return secret


class VisitorCookie:
    def __init__(self, secret: str):
        if not secret:
            raise ValueError("the visitor cookie needs a signing secret")
        self._signer = URLSafeTimedSerializer(secret, salt="meridian-visitor")

    def read(self, value: str | None) -> str | None:
        """The visitor id in a valid, unexpired cookie, or None."""
        if not value:
            return None
        try:
            visitor_id = self._signer.loads(value, max_age=MAX_AGE_S)
        except BadSignature:  # also an expired signature
            return None
        return visitor_id if isinstance(visitor_id, str) and visitor_id else None

    def issue(self) -> tuple[str, str]:
        """A new visitor id and its signed cookie value."""
        visitor_id = uuid.uuid4().hex
        return visitor_id, self.sign(visitor_id)

    def sign(self, visitor_id: str) -> str:
        return self._signer.dumps(visitor_id)

    @staticmethod
    def set_on(response, value: str) -> None:
        response.set_cookie(COOKIE, value, max_age=MAX_AGE_S, httponly=True, secure=True, samesite="lax", path="/")
