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
