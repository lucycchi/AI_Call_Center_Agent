import pytest

from app.replies.checks import CheckedStream, check_sentence
from app.replies.writer import split_sentences, write


@pytest.mark.parametrize("sentence, rule", [
    ("We'll waive the diagnostic fee for you.", "waiver"), ("I can waive that fee.", "waiver"),
    ("I've issued your refund.", "refund"), ("You'll get a full refund.", "refund"),
    ("Your repair will cost exactly $240.", "firm_total"), ("The total will be $480.", "firm_total"),
    ("I can put you on the waitlist.", "waitlist"), ("I'll add you to our waiting list.", "waitlist"),
    ("I can give you 20% off.", "discount"), ("I can give you a discount on this one.", "discount"),
])
def test_promises_the_agent_cannot_keep_fail(sentence, rule):
    result = check_sentence(sentence, "")
    assert (result.ok, result.rule) == (False, rule)


@pytest.mark.parametrize("sentence", [
    "Members get 15 percent off repairs.", "The diagnostic fee is waived for Comfort Club members.",
    "A tune-up is $129 for non-members.", "Drain clearing typically costs $149 to $290; the technician confirms the final price on site.",
    "If no tune-up has been performed, a prorated refund is available within the first 60 days.",
    "Comfort Club members get $500 off a full system replacement.", "We don't keep a waitlist, but I can offer the next open slots.",
])
def test_published_facts_pass(sentence):
    assert check_sentence(sentence, "").ok


def test_eight_words_of_an_internal_document_fail_even_across_sentences():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "call_data" / "knowledge_base" / "internal" / "agent_discretion_notes.md").read_text()
    import re
    words = re.findall(r"[A-Za-z0-9']+", text.split("\n", 3)[-1])[:12]
    first, second = " ".join(words[:5]) + ".", " ".join(words[5:9]) + "."
    assert check_sentence(first, "").ok
    result = check_sentence(second, first)
    assert (result.ok, result.rule) == (False, "internal_text")


def test_the_stream_releases_checked_sentences_and_stops_at_the_first_failure():
    stream = CheckedStream(iter(["The fee is $89.", "We'll waive it for you.", "Anything else?"]))
    assert list(stream) == ["The fee is $89."]
    assert stream.blocked_rule == "waiver"


def test_streamed_text_is_split_into_sentences():
    chunks = ["The diagnostic fee is $8", "9.00. It is credited toward the repa", "ir! Want to book? Ok"]
    assert list(split_sentences(iter(chunks))) == ["The diagnostic fee is $89.00.", "It is credited toward the repair!",
                                                   "Want to book?", "Ok"]


class FakeStream:
    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, chunks):
        self.calls = []
        self.messages = self
        self._chunks = chunks

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self._chunks)


def test_the_writer_streams_sentences_from_the_facts_only():
    client = FakeClient(["A tune-up is $129 (Service Catalog). ", "The technician confirms the final price on site."])
    sentences = list(write("price answer", ["A tune-up is $129 for non-members. [Service Catalog]"], [], client))
    assert sentences == ["A tune-up is $129 (Service Catalog).", "The technician confirms the final price on site."]
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert "A tune-up is $129 for non-members." in call["messages"][-1]["content"]
    assert "discretion" not in call["system"].lower()
