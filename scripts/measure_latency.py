"""Measures the live site's reply times (Task 26 Step 4, the PRD's latency numbers): after a few warm-up messages, sends
at least 50 messages and reports the median time to the first sentence and to the full reply.

Each message is a fresh visitor (a new cookie jar) in a new conversation, so one visitor's spending allowance is not
what is measured. The site also limits each client address to 20 messages per 10 minutes, so messages are paced
(31 seconds apart by default: about 28 minutes for 50 messages and 3 warm-ups). Every message is a real, paid
conversation turn on the live site (a few cents each); a reply cut short by a limit counts as a failure, not a time.

Run: .venv/bin/python scripts/measure_latency.py https://<app>.fly.dev [--messages 50] [--warmup 3] [--pace 31]
     [--reviewer]   (on a reviewer-only site, D50: REVIEWER_TOKEN in the environment)
Targets: median first sentence under 2.5 seconds, full reply under 4.0 seconds."""

import argparse
import json
import statistics
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

MIN_MESSAGES = 50
FIRST_SENTENCE_TARGET_S, FULL_REPLY_TARGET_S = 2.5, 4.0
QUESTIONS = [  # knowledge questions a caller asks; no account details, so nothing is booked or looked up
    "What are your office hours?",
    "How much is the diagnostic fee for a service visit?",
    "Do you charge extra for an after-hours visit?",
    "What does the maintenance plan include?",
    "How often should I change my furnace filter?",
    "Is there a fee if I cancel my appointment?",
    "Are you open on Thanksgiving?",
    "What does the warranty on a new system cover?",
    "Do you service heat pumps?",
    "How long does a tune-up take?",
]


@dataclass
class Report:
    count: int = 0
    failures: int = 0
    first_sentence_s: list[float] = field(default_factory=list)
    full_reply_s: list[float] = field(default_factory=list)

    @property
    def median_first_sentence_s(self) -> float | None:
        return statistics.median(self.first_sentence_s) if self.first_sentence_s else None

    @property
    def median_full_reply_s(self) -> float | None:
        return statistics.median(self.full_reply_s) if self.full_reply_s else None


def _events(lines):
    """Server-sent events as (event, data) pairs."""
    event, data = None, []
    for line in lines:
        if line == "":
            if event is not None:
                yield event, json.loads("\n".join(data) or "{}")
            event, data = None, []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
    if event is not None:
        yield event, json.loads("\n".join(data) or "{}")


def one_message(client: httpx.Client, text: str, clock: Callable[[], float],
                on_event: Callable[[str, dict], None] | None = None) -> tuple[float | None, float | None, str]:
    """Sends one message and reads its stream: (seconds to first sentence, seconds to done, outcome)."""
    conversation_id, message_id = uuid.uuid4().hex, uuid.uuid4().hex
    start = clock()
    response = client.post("/api/message", json={"conversation_id": conversation_id, "message_id": message_id,
                                                 "text": text})
    if response.status_code != 202:
        return None, None, f"HTTP {response.status_code}"
    first = None
    with client.stream("GET", f"/api/stream/{message_id}") as stream:
        if stream.status_code != 200:
            return None, None, f"stream HTTP {stream.status_code}"
        for event, data in _events(stream.iter_lines()):
            if on_event:
                on_event(event, data)
            if event == "sentence" and first is None:
                first = clock() - start
            elif event == "done":
                return first, clock() - start, data.get("outcome") or "unknown"
    return first, None, "stream ended without done"


def measure(base_url: str, messages: int = MIN_MESSAGES, warmup: int = 3, pace_s: float = 31.0,
            client_factory: Callable[[], httpx.Client] | None = None, clock: Callable[[], float] = time.perf_counter,
            sleep: Callable[[float], None] = time.sleep, on_event: Callable[[str, dict], None] | None = None,
            log: Callable[[str], None] = print, reviewer_token: str | None = None) -> Report:
    """reviewer_token: on a reviewer-only site (D50) each fresh visitor opens the reviewer link before its message."""
    if messages < MIN_MESSAGES:
        raise ValueError(f"send at least {MIN_MESSAGES} messages after warm-up, not {messages}")
    factory = client_factory or (lambda: httpx.Client(base_url=base_url, timeout=60.0))
    report = Report()
    for n in range(warmup + messages):
        if n:
            sleep(pace_s)
        text = QUESTIONS[n % len(QUESTIONS)]
        with factory() as client:  # a fresh visitor each time
            try:
                if reviewer_token:
                    client.post("/api/reviewer", json={"token": reviewer_token}).raise_for_status()
                first, full, outcome = one_message(client, text, clock, on_event)
            except httpx.HTTPError as error:
                first, full, outcome = None, None, f"{type(error).__name__}"
        warm = n < warmup
        label = "warm-up" if warm else f"{n - warmup + 1}/{messages}"
        log(f"{label}: first sentence {_s(first)}, full reply {_s(full)}, {outcome}")
        if warm:
            continue
        if first is None or full is None or outcome in ("limit", "error", "incomplete") or outcome.startswith(
                ("HTTP", "stream")):
            report.failures += 1
            continue
        report.count += 1
        report.first_sentence_s.append(first)
        report.full_reply_s.append(full)
    return report


def _s(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f} s"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base_url", help="the site, such as https://<app>.fly.dev")
    parser.add_argument("--messages", type=int, default=MIN_MESSAGES, help="measured messages (at least 50)")
    parser.add_argument("--warmup", type=int, default=3, help="messages sent first and not measured")
    parser.add_argument("--pace", type=float, default=31.0, help="seconds between messages (the address limit)")
    parser.add_argument("--reviewer", action="store_true",
                        help="sign each visitor in with the reviewer link; the token is read from REVIEWER_TOKEN")
    return parser.parse_args(argv)


def reviewer_token(args: argparse.Namespace) -> str | None:
    """From the environment, never the command line, so it stays out of shell history and process lists."""
    import os
    return os.environ.get("REVIEWER_TOKEN") if args.reviewer else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = measure(args.base_url.rstrip("/"), messages=args.messages, warmup=args.warmup, pace_s=args.pace,
                     reviewer_token=reviewer_token(args))
    first, full = report.median_first_sentence_s, report.median_full_reply_s
    print(f"\nmeasured {report.count} replies ({report.failures} failed)")
    print(f"median first sentence: {_s(first)} (target under {FIRST_SENTENCE_TARGET_S} s)")
    print(f"median full reply:     {_s(full)} (target under {FULL_REPLY_TARGET_S} s)")
    met = first is not None and full is not None and first < FIRST_SENTENCE_TARGET_S and full < FULL_REPLY_TARGET_S
    print("targets met" if met else "targets NOT met: report the measured values")
    return 0 if report.count >= MIN_MESSAGES and met else 1


if __name__ == "__main__":
    sys.exit(main())
