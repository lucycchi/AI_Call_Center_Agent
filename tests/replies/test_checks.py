import pytest

from app.replies.checks import CheckedStream, check_sentence
from app.replies.writer import split_sentences, write


@pytest.mark.parametrize("sentence, rule", [
    ("Your repair will cost exactly $240.", "firm_total"), ("The total will be $480.", "firm_total"),
    ("I can put you on the waitlist.", "waitlist"), ("I'll add you to our waiting list.", "waitlist"),
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
    stream = CheckedStream(iter(["The fee is $89.", "We'll waive it for you.", "Anything else?"]),
                           money_check=lambda sentence, previous: "waive" not in sentence)
    assert list(stream) == ["The fee is $89."]
    assert stream.blocked_rule == "money promise"


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
    assert "Never say a team member will follow up unless" in call["system"]


def test_the_writer_sends_history_as_text_never_as_stored_roles():
    client = FakeClient(["Sure."])
    list(write("policy answer", ["fact"], [{"role": "caller", "content": "hi"}, {"role": "agent", "content": "hello"}], client))
    messages = client.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["user"]
    assert "caller: hi" in messages[0]["content"] and "agent: hello" in messages[0]["content"]


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


def test_every_sentence_of_the_current_customer_documents_passes_the_code_checks():
    blocked = [(doc, s, check_sentence(s, "").rule) for doc, s in _customer_document_sentences()
               if not check_sentence(s, "").ok and check_sentence(s, "").rule != "internal_text"]
    assert not blocked, blocked[:5]


# Money promises are judged by a model check on every sentence that touches money (D43).

def _labelled():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "data" / "eval" / "money_sentences.jsonl"
    return [json.loads(line) for line in path.open()]


def test_every_labelled_sentence_touches_money_or_is_a_plain_pass():
    from app.replies.money_check import touches_money
    for row in _labelled():
        if row["expected"] == "block":
            assert touches_money(row["sentence"]), row["sentence"]


@pytest.mark.parametrize("sentence", ["We're open Monday to Friday, 7am to 7pm.", "Manor is in our service area.",
                                      "Which of these slots suits you?", "Please leave your home right now."])
def test_sentences_without_money_never_reach_the_model(sentence):
    from app.replies.money_check import touches_money
    assert not touches_money(sentence)


class FakeChecker:
    def __init__(self, verdict="pass", stop_reason="end_turn", error=None):
        self.verdict, self.stop_reason, self.error, self.calls, self.messages = verdict, stop_reason, error, [], self

    def create(self, **kwargs):
        import json
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        block = type("Block", (), {"type": "text", "text": json.dumps({"promises_beyond_published_terms": self.verdict == "block"})})()
        return type("Response", (), {"content": [block], "stop_reason": self.stop_reason})()


def test_the_money_check_asks_haiku_with_the_published_terms_and_the_sentence_before():
    from app.replies.money_check import MoneyCheck
    client = FakeChecker("pass")
    assert MoneyCheck(client)("It's waived for members.", "The diagnostic fee is $89.") is True
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_config"]["format"]["type"] == "json_schema"
    assert call["purpose"] == "check"
    content = call["messages"][0]["content"]
    assert "It's waived for members." in content and "The diagnostic fee is $89." in content
    assert "$89" in call["system"] and "15%" in call["system"]


@pytest.mark.parametrize("client", [FakeChecker("block"), FakeChecker("pass", stop_reason="refusal"),
                                    FakeChecker(error=RuntimeError("timeout"))])
def test_the_money_check_fails_closed(client):
    from app.replies.money_check import MoneyCheck
    assert MoneyCheck(client)("Your fee will be waived.", "") is False


def test_a_money_sentence_with_no_promise_is_released():
    from app.replies.money_check import MoneyCheck
    stream = CheckedStream(iter(["A tune-up is $129.", "Anything else?"]), money_check=MoneyCheck(FakeChecker("pass")))
    assert list(stream) == ["A tune-up is $129.", "Anything else?"]





def test_the_money_check_evaluation_counts_misses_and_over_blocks():
    from eval.money_check_eval import evaluate
    rows = [{"sentence": "I'll waive it.", "previous": "", "expected": "block"},
            {"sentence": "A tune-up is $129.", "previous": "", "expected": "pass"}]
    report = evaluate(rows, lambda sentence, previous: True)
    assert report["missed_promises"] == ["I'll waive it."] and report["over_blocked"] == []
