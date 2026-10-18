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
    words = re.findall(r"[A-Za-z0-9']+", text.split("\n", 3)[-1])
    concession = re.compile(r"waiv|refund|credit|discount|fee|charge|off", re.I)
    start = next(i for i in range(len(words) - 9) if not any(concession.search(w) for w in words[i:i + 9]))
    first, second = " ".join(words[start:start + 5]) + ".", " ".join(words[start + 5:start + 9]) + "."
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
    assert "never as he or she" in call["system"]


def test_the_writer_sends_history_as_text_never_as_stored_roles():
    client = FakeClient(["Sure."])
    list(write("policy answer", ["fact"], [{"role": "caller", "content": "hi"}, {"role": "agent", "content": "hello"}], client))
    messages = client.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["user"]
    assert "caller: hi" in messages[0]["content"] and "agent: hello" in messages[0]["content"]


# Milestone 3 gate fixes.

@pytest.mark.parametrize("sentence, rule", [
    ("The diagnostic fee will be waived for you.", "waiver"), ("I've removed the diagnostic charge.", "waiver"),
    ("That fee has been taken off your bill.", "waiver"),
    ("A refund has been issued to your card.", "refund"), ("I'll process a full refund today.", "refund"),
    ("You qualify for a 20 percent discount.", "discount"), ("That's 25% off for you.", "discount"),
])
def test_passive_and_roundabout_promises_fail(sentence, rule):
    result = check_sentence(sentence, "")
    assert (result.ok, result.rule) == (False, rule)


@pytest.mark.parametrize("sentence", ["You qualify for the 15% member discount on repairs.",
                                      "Annual plans are non-refundable once a tune-up has been performed."])
def test_published_terms_still_pass(sentence):
    assert check_sentence(sentence, "").ok


def test_breaker_reset_advice_is_blocked_once_a_burning_smell_was_mentioned():
    advice = "You can reset any tripped breaker once before booking."
    assert check_sentence(advice, "").ok
    result = check_sentence(advice, "", burning_mentioned=True)
    assert (result.ok, result.rule) == (False, "breaker_advice")
    stream = CheckedStream(iter(["Let's check a few things.", "Flip the breaker off and on."]), burning_mentioned=True)
    assert list(stream) == ["Let's check a few things."] and stream.blocked_rule == "breaker_advice"


def _customer_document_sentences():
    import csv
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    current = {r["path"].rsplit(".", 1)[0].replace("/", "__") for r in csv.DictReader((root / "data" / "document_list.csv").open())
               if r["status"] == "current" and r["audience"] == "customers"}
    for path in sorted((root / "data" / "kb_text").glob("*.md")):
        if path.stem in current:
            for line in path.read_text().splitlines():
                text = re.sub(r"^[-#*|\s\d.)]+", "", line).replace("**", "").strip()
                for sentence in re.split(r"(?<=[.!?])\s+", text):
                    if len(sentence.split()) >= 3:
                        yield path.stem, sentence


def test_every_sentence_of_the_current_customer_documents_passes_the_promise_checks():
    blocked = [(doc, s, check_sentence(s, "").rule) for doc, s in _customer_document_sentences()
               if not check_sentence(s, "").ok and check_sentence(s, "").rule != "internal_text"]
    assert not blocked, blocked[:5]


@pytest.mark.parametrize("sentence", [
    "As a Comfort Club member, your diagnostic fee will be waived.", "The $89 diagnostic fee gets credited toward the repair.",
    "That pending authorization will be removed automatically.", "The diagnostic fee is waived for members."])
def test_published_wording_from_the_documents_passes(sentence):
    assert check_sentence(sentence, "").ok, check_sentence(sentence, "").rule


@pytest.mark.parametrize("sentence, rule", [
    ("I'll refund you the $89.", "refund"), ("We'll credit your account $89.", "waiver"), ("We can drop the late fee.", "waiver"),
    ("We will refund the duplicate charge.", "refund"), ("I'll waive the after-hours fee this time.", "waiver"),
    ("Your diagnostic fee is waived today.", "waiver"),
])
def test_real_promises_fail(sentence, rule):
    result = check_sentence(sentence, "")
    assert (result.ok, result.rule) == (False, rule)


# Deny by default: a concession is blocked unless it is an approved published term.
@pytest.mark.parametrize("sentence", [
    "Since you're a member, the late fee will be waived this time.", "The fee will be waived automatically for you this once.",
    "Your fee will be waived within 2 days.", "We'll knock the trip charge off.", "That one's on us, no charge.",
    "I'll give you a 10% discount since you've been waiting."])
def test_concessions_that_are_not_published_terms_fail(sentence):
    assert not check_sentence(sentence, "").ok


def test_a_concession_split_over_two_sentences_fails():
    assert not check_sentence("It will be waived for you.", "The diagnostic fee is $89.").ok


@pytest.mark.parametrize("sentence", [
    "We take Visa, Mastercard and Amex for your invoice.", "I can take you through the charges on your invoice.",
    "We'll take a look at that charge for you.", "We remove the old unit, and the charge for haul-away is listed on the invoice.",
    "We credit the $89 diagnostic fee toward the repair if you approve it.", "We refund unused membership months, prorated.",
    "Members get a 15% discount on repairs.", "It's waived for members.", "Comfort Club members get $500 off a replacement."])
def test_ordinary_and_published_sentences_pass(sentence):
    previous = "The diagnostic fee is $89." if sentence.startswith("It's") else ""
    assert check_sentence(sentence, previous).ok, check_sentence(sentence, previous).rule
