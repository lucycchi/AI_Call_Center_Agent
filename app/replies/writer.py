"""The reply writer: Sonnet 5.5, streamed and split into sentences. It sees only the facts a flow chose and
short paraphrased rules, never an internal document as written (R42, R43)."""

import re
from collections.abc import Iterator

from app.config import SETTINGS
from app.core import deadline
from app.replies.types import REPLY_TYPES

RULES = f"""You write the replies of Meridian Home Comfort's customer assistant.
Today is {SETTINGS.now:%A} {SETTINGS.now.day} {SETTINGS.now:%B %Y}.
Use only the facts given; if they do not answer the question, say a team member will follow up.
Name the source document for any fact from a document.
Never promise a fee waiver, a refund, a discount beyond the published member discounts, a firm repair total or a waitlist.
Refer to technicians and staff by name or role, never as he or she.
Never say a team member will follow up unless the reply type is handoff or a fact says so.
State member benefits as member benefits ("Comfort Club members get ...").
Never guess beyond the facts: no "probably", "likely" or "should" about savings, eligibility, coverage or outcomes the
facts do not state; say plainly what the facts do not cover.
Always write in English, whatever language the caller used.
Answer completely: include every fact from the facts that answers what the caller asked, and nothing beyond it,
in as few plain sentences as that takes. No lists, no markdown."""

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(chunks: Iterator[str]) -> Iterator[str]:
    buffer = ""
    for chunk in chunks:
        buffer += chunk
        parts = SENTENCE_END.split(buffer)
        for sentence in parts[:-1]:
            if sentence.strip():
                yield sentence.strip()
        buffer = parts[-1]
    if buffer.strip():
        yield buffer.strip()


def write(reply_type: str, facts: list[str], history: list[dict], client) -> Iterator[str]:
    recent = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
    prompt = (f"Recent conversation:\n{recent or '(none)'}\n\nReply type: {reply_type}. {REPLY_TYPES[reply_type]}\n\n"
              "Facts:\n" + "\n".join(f"- {f}" for f in facts))
    messages = [{"role": "user", "content": prompt}]
    deadline.check()
    timeout = deadline.remaining()  # a streamed reply cannot be retried part-way, so it gets all the time left
    with client.messages.stream(**({"timeout": timeout} if timeout is not None else {}), model=SETTINGS.writer_model, max_tokens=SETTINGS.eval_writer_max_tokens, system=RULES,
                                messages=messages, output_config={"effort": "low"}) as stream:
        yield from split_sentences(stream.text_stream)
