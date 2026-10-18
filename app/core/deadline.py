"""One deadline per caller message (15 seconds, R59), read by the router, the writer and the flows.

It is cooperative: work checks it before each model call, before each commit and between released sentences,
so nothing is still running, or committing, after the caller has been told their request was passed on."""

import contextvars
import time

DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar("message_deadline", default=None)


class DeadlinePassed(RuntimeError):
    pass


def start(seconds: float) -> contextvars.Token:
    return DEADLINE.set(time.monotonic() + seconds)


def remaining() -> float | None:
    deadline = DEADLINE.get()
    return None if deadline is None else max(deadline - time.monotonic(), 0.0)


def per_attempt(retries: int = 1) -> float | None:
    """The timeout for one model-call attempt: the time left shared across the attempt and its retries."""
    left = remaining()
    return None if left is None else max(left / (retries + 1), 0.01)


def passed() -> bool:
    left = remaining()
    return left is not None and left <= 0


def check() -> None:
    if passed():
        raise DeadlinePassed("the message deadline has passed")
