from app.core.engine import Engine
from app.core.types import DoneEvent, SentenceEvent, Turn


class FakePipeline:
    """Stands in for the safety, routing and flow steps built in later tasks."""

    def run(self, turn):
        yield SentenceEvent("Hello, how can I help?")
        yield DoneEvent(route="knowledge", ticket=None, receipt={}, outcome="answered", db_actions=[])


def test_handle_yields_sentences_then_exactly_one_done_event():
    events = list(Engine(pipeline=FakePipeline()).handle(Turn("c1", "v1", "m1", "hello")))

    assert [type(e) for e in events] == [SentenceEvent, DoneEvent]
    assert events[0].text == "Hello, how can I help?"
    assert events[-1].route == "knowledge"


def test_handle_adds_a_done_event_if_the_pipeline_forgets_one():
    class Forgetful:
        def run(self, turn):
            yield SentenceEvent("Partial answer.")

    events = list(Engine(pipeline=Forgetful()).handle(Turn("c1", "v1", "m2", "hi")))

    assert sum(isinstance(e, DoneEvent) for e in events) == 1
    assert isinstance(events[-1], DoneEvent)


def test_nothing_is_yielded_after_the_first_done_event():
    class Chatty:
        def run(self, turn):
            yield SentenceEvent("One.")
            yield DoneEvent(route="knowledge", ticket=None)
            yield SentenceEvent("Late sentence.")
            yield DoneEvent(route="knowledge", ticket=None)

    events = list(Engine(pipeline=Chatty()).handle(Turn("c1", "v1", "m3", "hi")))
    assert [type(e) for e in events] == [SentenceEvent, DoneEvent]


def test_a_crashing_pipeline_still_ends_with_one_error_done_event():
    class Crashing:
        def run(self, turn):
            yield SentenceEvent("Started.")
            raise RuntimeError("database gone")

    events = list(Engine(pipeline=Crashing()).handle(Turn("c1", "v1", "m4", "hi")))
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].outcome == "error"
    assert sum(isinstance(e, DoneEvent) for e in events) == 1
