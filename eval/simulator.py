"""The simulated caller (R12): Claude Sonnet 5.5 plays the caller from the case's caller card and the transcript's
caller lines, one message at a time, reading relative dates against the fixed "now"."""

from app.config import SETTINGS

DONE = "[DONE]"
RULES = """You are role-playing a customer contacting Meridian Home Comfort (heating, cooling and plumbing, Austin area)
through its website chat. Today is {now:%A} {now.day} {now:%B %Y}, {now:%-I%p} Austin time; read "tomorrow" or "Thursday"
against that.

Who you are (use exactly these details when asked; never invent others):
- Name: {name}
- Account number: {customer_id}
- Phone: {phone}
- Service address: {address}, {city}

What you want: follow the original caller's lines below, in order, adapting them naturally to what the assistant
says. Ask for each thing they asked for; accept, decline or choose the way they did. Do not add new requests.
Original caller lines:
{script}

Write only your next chat message: one or two short sentences, plain text. When everything you wanted is handled,
or you have been told a team member will follow up and you have nothing else to ask, reply with exactly {done}."""


def _transcript(conversation: list[dict]) -> str:
    return "\n".join(f"{'You' if m['role'] == 'caller' else 'Assistant'}: {m['text']}" for m in conversation)


class Simulator:
    def __init__(self, client):
        self._client = client

    def next(self, case: dict, conversation: list[dict], timeout: float | None = None) -> str | None:
        """timeout: the seconds left in the conversation, so the caller's model call cannot run past the cap."""
        card = case["caller_card"]
        system = RULES.format(now=SETTINGS.now, name=card.get("name", ""), customer_id=card.get("customer_id", ""),
                              phone=card.get("phone", ""), address=card.get("service_address", ""), city=card.get("city", ""),
                              script="\n".join(f"- {line}" for line in case["caller_script"]), done=DONE)
        content = (f"The chat so far:\n{_transcript(conversation)}\n\nYour next message:" if conversation
                   else "Start the chat with your first message.")
        response = self._client.messages.create(**({"timeout": max(timeout, 0.01)} if timeout is not None else {}),
                                                purpose="simulate", model=SETTINGS.writer_model,
                                                max_tokens=SETTINGS.eval_simulator_max_tokens, system=system,
                                                output_config={"effort": "low"}, messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return None if not text or DONE in text else text
