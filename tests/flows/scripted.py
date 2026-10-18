"""A scripted stand-in for the Anthropic client, so conversation tests run the real router and writer code.

The router's answer is looked up from the caller's message; the writer echoes the facts it was given, one per
sentence, so tests can see exactly what the flows chose to say."""

import json
import re


class Usage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens


class Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class Response:
    def __init__(self, text):
        self.content, self.stop_reason, self.usage = [Block(text)], "end_turn", Usage(400, 60)


class Stream:
    def __init__(self, facts):
        self.text_stream = iter([f"{fact.rstrip('.')}. " for fact in facts])
        self._final = Response("")
        self._final.usage = Usage(900, 120)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


def request(text, route, detail="none", service_type="none"):
    return {"text": text, "route": route, "detail": detail, "service_type": service_type}


class ScriptedClient:
    def __init__(self, routes):
        self.routes, self.messages, self.calls = routes, self, []

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        message = kwargs["messages"][-1]["content"].split("New message: ", 1)[1]
        # The longest matching key wins, so a specific script line beats a general one.
        for key in sorted(self.routes, key=len, reverse=True):
            if key in message.lower():
                return Response(json.dumps(self.routes[key]))
        return Response(json.dumps({"clear": False, "requests": [request(message, "handoff", "other")]}))

    def stream(self, **kwargs):
        self.calls.append(("stream", kwargs))
        facts = re.findall(r"^- (.*)$", kwargs["messages"][-1]["content"], re.M)
        return Stream(facts)
