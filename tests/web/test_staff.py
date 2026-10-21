"""The Staff view (Task 23; R70 to R72, R75): the panel beside the chat, the staff password and session, reply receipts,
masking and flagging. No model is ever called: the operations store is seeded directly, as the pipeline would write it."""

import json
import re
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import AUSTIN
from app.ops.metrics import live_numbers
from app.ops.store import OpsStore
from app.web.main import create_app
from app.web.staff import STAFF_COOKIE, hash_password, password_matches
from app.web.visitor import VisitorCookie
from tests.web.test_chat import FakeEngine

SECRET = "test-only-secret"
PASSWORD = "correct horse battery staple"
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=AUSTIN)


class Clock:
    def __init__(self, now: datetime = NOW):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return OpsStore(tmp_path / "ops.sqlite", clock=clock)


@pytest.fixture
def app(store, clock):
    return create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=clock,
                      staff_password_hash=hash_password(PASSWORD, iterations=1000))


def visitor(app, visitor_id: str, address: str = "testclient") -> TestClient:
    client = TestClient(app, base_url="https://testserver", client=(address, 50000))
    client.cookies.set("meridian_visitor", VisitorCookie(SECRET).sign(visitor_id))
    return client


def login(client, password=PASSWORD):
    return client.post("/api/staff/login", json={"password": password})


def staff(app, visitor_id="staffer", address="10.0.0.9") -> TestClient:
    client = visitor(app, visitor_id, address)
    assert login(client).status_code == 200
    return client


def ticket(store, visitor_id, conversation_id, **fields):
    store.open_conversation(visitor_id, conversation_id)
    values = {"who": "Linda Foster", "wants": "a repair visit", "tried": "reset the thermostat", "constraints": "none",
              "mood": "calm", "reason_tag": "complaint"} | fields
    return store.create_ticket(conversation_id, **values)


def reply(store, conversation_id, caller_text, agent_text, receipt=None):
    """A caller message and the agent's reply with its receipt, as the pipeline writes them."""
    store.log_message(conversation_id, "caller", caller_text)
    agent = store.log_message(conversation_id, "agent", "")
    store.log_agent_message(agent, agent_text)
    receipt = {"safety_result": "clear", "route": "knowledge", "passages": [], "excluded": [], "db_action": None,
               "outcome_label": "answered"} | (receipt or {})
    store.log_receipt(agent, **receipt)
    return agent


# -- Access ------------------------------------------------------------------------------------------------------

def test_password_hash_round_trip():
    stored = hash_password(PASSWORD, iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$") and PASSWORD not in stored
    assert password_matches(PASSWORD, stored)
    assert not password_matches("wrong", stored)
    assert not password_matches(PASSWORD, "") and not password_matches(PASSWORD, "garbage")


def test_a_visitor_sees_only_their_own_tickets(app, store):
    mine = ticket(store, "alice", "c-alice", wants="a plumber for Tuesday")
    ticket(store, "bob", "c-bob", wants="a refund on invoice 12")
    panel = visitor(app, "alice").get("/api/staff/panel")
    assert panel.status_code == 200
    body = panel.json()
    assert [t["ticket_id"] for t in body["tickets"]] == [mine]
    assert "refund" not in panel.text
    assert set(body["tickets"][0]) >= {"who", "wants", "tried", "constraints", "mood", "priority", "priority_label"}
    assert body["staff"] is False and body["form_token"] is None


def test_a_visitor_cannot_read_another_visitors_receipts(app, store):
    store.open_conversation("bob", "c-bob")
    reply(store, "c-bob", "hi", "Bob's private answer.")
    response = visitor(app, "alice").get("/api/staff/panel", params={"conversation_id": "c-bob"})
    assert response.status_code == 404


def test_the_queue_without_a_staff_session_is_403(app, store):
    ticket(store, "bob", "c-bob")
    assert visitor(app, "alice").get("/api/staff/queue").status_code == 403
    forged = visitor(app, "alice")
    forged.cookies.set(STAFF_COOKIE, "not-a-real-session")
    assert forged.get("/api/staff/queue").status_code == 403


def test_the_correct_password_starts_a_12_hour_staff_session(app, store, clock):
    ticket(store, "alice", "c-alice")
    ticket(store, "bob", "c-bob")
    client = visitor(app, "carol", "10.0.0.5")
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{STAFF_COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    assert "Max-Age=43200" in cookie and re.search(r"samesite=(lax|strict)", cookie, re.I)
    queue = client.get("/api/staff/queue")
    assert queue.status_code == 200 and len(queue.json()["tickets"]) == 2
    assert client.get("/api/staff/panel").json()["staff"] is True
    clock.now = NOW + timedelta(hours=11, minutes=59)
    assert client.get("/api/staff/queue").status_code == 200
    clock.now = NOW + timedelta(hours=12, minutes=1)
    assert client.get("/api/staff/queue").status_code == 403


def test_a_wrong_password_starts_no_session(app):
    client = visitor(app, "carol")
    response = login(client, "not it")
    assert response.status_code == 401 and STAFF_COOKIE not in response.headers.get("set-cookie", "")
    assert client.get("/api/staff/queue").status_code == 403


def test_no_configured_hash_means_no_sign_in(store, clock):
    app = create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=clock, staff_password_hash=None)
    assert login(visitor(app, "carol")).status_code in (401, 503)


def test_the_sixth_wrong_attempt_in_15_minutes_is_refused(app, clock):
    client = visitor(app, "mallory", "203.0.113.7")
    for _ in range(5):
        assert login(client, "guess").status_code == 401
        clock.now += timedelta(minutes=2)
    assert login(client, "guess").status_code == 429
    assert login(client, PASSWORD).status_code == 429  # locked, even with the right password
    fresh_cookie = visitor(app, "mallory-again", "203.0.113.7")  # a cleared cookie does not reset it
    assert login(fresh_cookie, PASSWORD).status_code == 429
    assert login(visitor(app, "someone", "198.51.100.1"), PASSWORD).status_code == 200  # other addresses unaffected
    clock.now += timedelta(minutes=16)
    assert login(client, PASSWORD).status_code == 200


def test_the_fly_header_counts_only_behind_fly(store, clock):
    def attempts(trust):
        app = create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=clock, trust_fly_header=trust,
                         staff_password_hash=hash_password(PASSWORD, iterations=1000))
        codes = []
        for n in range(6):
            client = visitor(app, f"v{n}", "10.1.1.1")  # one proxy address
            codes.append(client.post("/api/staff/login", json={"password": "guess"},
                                     headers={"fly-client-ip": f"198.51.100.{n}"}).status_code)
        return codes
    assert attempts(trust=True) == [401] * 6  # six different real clients
    assert attempts(trust=False)[-1] == 429  # the header is ignored: one address


def test_a_flag_without_the_form_token_is_rejected(app, store):
    store.open_conversation("alice", "c-alice")
    agent = reply(store, "c-alice", "what is the fee?", "The fee is $79.")
    client = staff(app)
    token = client.get("/api/staff/panel").json()["form_token"]
    assert token
    assert client.post("/api/staff/flag", json={"message_id": agent, "correction": "It is $89."}).status_code == 403
    assert client.post("/api/staff/flag", json={"message_id": agent, "correction": "x",
                                                "token": "forged"}).status_code == 403
    assert store.flags() == []
    other = staff(app, "other-staffer", "10.0.0.10")  # another session's token does not fit
    assert client.post("/api/staff/flag", json={"message_id": agent, "correction": "x",
                                                "token": other.get("/api/staff/panel").json()["form_token"]}
                       ).status_code == 403
    ok = client.post("/api/staff/flag", json={"message_id": agent, "correction": "It is $89.", "token": token})
    assert ok.status_code == 200
    assert len(store.flags()) == 1


def test_a_visitor_without_a_staff_session_cannot_flag(app, store):
    store.open_conversation("alice", "c-alice")
    agent = reply(store, "c-alice", "hi", "Hello.")
    response = visitor(app, "alice").post("/api/staff/flag", json={"message_id": agent, "correction": "x", "token": "t"})
    assert response.status_code == 403


# -- Numbers -----------------------------------------------------------------------------------------------------

def finished(store, conversation_id, *, handoff=False, error=False, flag=False, abandoned=False, reply_ms=1000):
    """A conversation that ended now: closed, or abandoned with a flow in progress."""
    store.open_conversation("v", conversation_id)
    agent = reply(store, conversation_id, "hello", "Hi there.")
    store.set_reply_stats(agent, 400, reply_ms, 100)
    if handoff:
        store.create_ticket(conversation_id, "Omar Patel", "a refund", "none", "none", "upset", "dispute")
    if error:
        store.log_event("error", "writer timed out", conversation_id)
    if flag:
        store.add_flag(agent, "wrong fee")
    if abandoned:
        store.save_state(conversation_id, None, "scheduling", {"flow": {"step": "offer"}})
        store._write("update conversations set status = 'abandoned', closed_at = ? where conversation_id = ?",
                     (store._now(), conversation_id))
    else:
        store.end_conversation(conversation_id)


def test_live_numbers_count_today_in_austin_time(store, clock):
    clock.now = datetime(2026, 10, 19, 23, 30, tzinfo=AUSTIN)  # yesterday in Austin, already 04:30 UTC today
    finished(store, "yesterday", handoff=True, error=True, reply_ms=9000)
    clock.now = NOW
    finished(store, "a", reply_ms=1000)
    finished(store, "b", handoff=True, reply_ms=3000)
    finished(store, "c", error=True, reply_ms=2000)
    store.open_conversation("v", "still-open")
    numbers = live_numbers(store, date(2026, 10, 20))
    assert numbers["conversations"] == 4
    assert numbers["handoffs"] == 1
    assert numbers["errors"] == 1
    assert numbers["median_reply_ms"] == 2000
    assert set(numbers) >= {"conversations", "handoffs", "errors", "median_reply_ms", "live_containment",
                            "live_containment_label"}


def test_silent_billing_review_tickets_are_not_handoffs(store):
    store.create_ticket(None, "Omar Patel", "billing review", "none", "none", "calm", "billing review")
    assert live_numbers(store, date(2026, 10, 20))["handoffs"] == 0


def test_no_replies_means_no_median(store):
    assert live_numbers(store, date(2026, 10, 20))["median_reply_ms"] is None


def test_live_containment_is_an_upper_bound_over_clean_closed_conversations(store):
    for n in range(6):
        finished(store, f"clean{n}")
    finished(store, "handed", handoff=True)
    finished(store, "errored", error=True)
    finished(store, "flagged", flag=True)
    finished(store, "abandoned", abandoned=True)
    store.open_conversation("v", "open-one")  # still open: not counted either way
    numbers = live_numbers(store, date(2026, 10, 20))
    assert numbers["live_containment"] == pytest.approx(0.6)
    assert numbers["live_containment_label"] == "upper bound"


def test_below_10_closed_conversations_it_reads_not_enough_yet(store):
    for n in range(9):
        finished(store, f"clean{n}")
    numbers = live_numbers(store, date(2026, 10, 20))
    assert numbers["live_containment"] is None
    assert numbers["live_containment_label"] == "not enough conversations yet"
    finished(store, "tenth")
    assert live_numbers(store, date(2026, 10, 20))["live_containment"] == 1.0


def test_the_panel_shows_todays_numbers_and_a_new_ticket_badge(app, store):
    first = ticket(store, "alice", "c-alice")
    second = ticket(store, "alice", "c-alice", reason_tag="emergency", wants="gas smell")
    client = visitor(app, "alice")
    body = client.get("/api/staff/panel").json()
    assert body["numbers"]["conversations"] == 1 and body["numbers"]["handoffs"] == 2
    assert body["new_tickets"] == 2 and body["latest_ticket_id"] == second
    assert client.get("/api/staff/panel", params={"seen": first}).json()["new_tickets"] == 1
    assert client.get("/api/staff/panel", params={"seen": second}).json()["new_tickets"] == 0
    urgent = [t for t in body["tickets"] if t["ticket_id"] == second][0]
    assert urgent["priority_label"] == "urgent"


def test_the_chat_page_has_the_staff_view_button_badge_and_panel(app):
    page = visitor(app, "alice").get("/").text
    assert 'id="staff-button"' in page and 'id="staff-badge"' in page and 'id="staff-panel"' in page
    assert "/static/staff.js" in page
    assert visitor(app, "alice").get("/static/staff.js").status_code == 200


# -- Receipts ----------------------------------------------------------------------------------------------------

NUMBER = re.compile(r"(?<![\w.-])0\.\d+|\b\d+\.\d{2,}\b(?!\))")  # a score such as 0.94; prices ($79.00) aside


def receipts(client, conversation_id):
    response = client.get("/api/staff/panel", params={"conversation_id": conversation_id})
    assert response.status_code == 200, response.text
    return response


def test_each_receipt_shows_its_parts_with_plain_labels(app, store, clock):
    store.open_conversation("alice", "c1")
    reply(store, "c1", "what is the diagnostic fee?", "The diagnostic fee is $89.",
          {"route": "knowledge", "outcome_label": "supported by documents",
           "passages": ["pricing__fees.md (2026-03-01), Diagnostic fee"],
           "excluded": ["pricing__fees_2024.md (2024-01-01)"]})
    clock.now += timedelta(seconds=5)
    reply(store, "c1", "is the warranty transferable?", "I'm not sure, so I'll pass you to our team.",
          {"route": "knowledge", "outcome_label": "not enough evidence"})
    clock.now += timedelta(seconds=5)
    store.log_message("c1", "caller", "book me a repair for Friday")
    booked = store.log_message("c1", "agent", "")
    store.log_agent_message(booked, "You're booked for Friday 8 to 11.")
    store.log_receipt(booked, "clear", "scheduling", [], [], "booked appointment 77", "supported by account records")
    clock.now += timedelta(seconds=5)
    store.log_message("c1", "caller", "I smell gas near my furnace")
    gas = store.log_message("c1", "agent", "")
    store.log_agent_message(gas, "Leave the house now and call 911.")
    store.create_ticket("c1", "caller not identified", "gas smell", "none", "danger", "scared", "emergency")
    store.log_receipt(gas, "danger", "safety", [], [], None, "handoff required")

    shown = receipts(visitor(app, "alice"), "c1").json()["replies"]
    assert [r["receipt"]["label"] for r in shown] == ["supported by documents", "not enough evidence",
                                                      "supported by account records", "handoff required"]
    fee, unsure, booking, emergency = (r["receipt"] for r in shown)
    assert set(fee) >= {"safety", "route", "passages", "excluded", "db_action", "handoff_reason", "label"}
    assert fee["safety"] == "no safety concern" and fee["route"] == "knowledge"
    assert fee["passages"] == ["pricing__fees.md (2026-03-01), Diagnostic fee"]
    assert fee["excluded"] == ["pricing__fees_2024.md (2024-01-01)"]
    assert fee["db_action"] == "none" and fee["handoff_reason"] is None
    assert booking["db_action"] == "booked appointment 77"
    assert "emergency" in emergency["safety"] and emergency["handoff_reason"] == "emergency"
    assert emergency["ticket"] is not None


def test_a_later_handoff_names_the_open_tickets_reason(app, store, clock):
    store.open_conversation("alice", "c1")
    store.create_ticket("c1", "Omar Patel", "refund", "none", "none", "upset", "dispute")
    clock.now += timedelta(seconds=5)
    reply(store, "c1", "and also my tech was late", "I've added that to your ticket.",
          {"route": "handoff", "outcome_label": "handoff required"})
    assert receipts(visitor(app, "alice"), "c1").json()["replies"][0]["receipt"]["handoff_reason"] == "dispute"


def test_receipts_never_show_a_number_score_or_prompt_text(app, store):
    store.open_conversation("alice", "c1")
    agent = reply(store, "c1", "what does the club cost?", "It is $189 a year.",
                  {"outcome_label": "supported by documents",
                   "passages": ["membership__comfort_club_overview.md (2026-01-15), Plans"]})
    store.log_model_call(agent, "writer", "claude-sonnet-5-5", "anthropic 1.0",
                         {"system": "SYSTEM PROMPT: You are the writer. Internal rule 7.", "score": 0.94}, 900, 40, 800, 1200)
    store.log_event("retrieval", "top score 0.94 for chunk 12", "c1")
    staff_client = staff(app)
    for client in (visitor(app, "alice"), staff_client):
        text = receipts(client, "c1").text
        assert "0.94" not in text and not NUMBER.search(text)
        assert "SYSTEM PROMPT" not in text and "Internal rule" not in text and "score" not in text.lower()
        assert "claude-sonnet" not in text


def test_staff_may_open_any_conversations_receipts(app, store):
    store.open_conversation("bob", "c-bob")
    reply(store, "c-bob", "hi", "Hello Bob.", {"outcome_label": "answered"})
    body = receipts(staff(app), "c-bob").json()
    assert body["replies"][0]["text"] == "Hello Bob."


# -- Masking and feedback ----------------------------------------------------------------------------------------

PHONE, EMAIL, STREET = "512-555-0142", "linda.foster@example.com", "4417 Oak Hollow Dr"


def seed_unmasked(store):
    """Rows written straight into the database, past the store's own masking, as an older or faulty writer might."""
    store.open_conversation("alice", "c1")
    store._write("insert into messages (conversation_id, role, text_masked, created_at) values (?, 'caller', ?, ?)",
                 ("c1", f"call me at {PHONE}", store._now()))
    agent = store._write("insert into messages (conversation_id, role, text_masked, created_at) values (?, 'agent', ?, ?)",
                         ("c1", f"I'll email {EMAIL} about the visit to {STREET}.", store._now()))
    store._write("insert into receipts values (?, 'clear', 'scheduling', ?, '[]', ?, 'supported by account records')",
                 (agent, json.dumps([f"customer note for {STREET}"]), f"booked at {STREET}"))
    ticket_id = store._write("insert into tickets (conversation_id, who, wants, tried, constraints, mood, reason_tag, "
                             "priority, created_at) values ('c1', ?, ?, ?, ?, 'calm', 'complaint', 1, ?)",
                             (f"Linda Foster {PHONE}", f"a visit to {STREET}", f"emailed {EMAIL}",
                              f"call ({PHONE[:3]}) {PHONE[4:]} after 5", store._now()))
    store._write("insert into ticket_messages values (?, ?)", (ticket_id, agent))
    return agent


def assert_masked(text):
    for raw in (PHONE, EMAIL, STREET, "555-0142", "Oak Hollow"):
        assert raw not in text, raw


def test_phone_numbers_emails_and_streets_are_masked_in_every_panel_response(app, store):
    agent = seed_unmasked(store)
    alice, staff_client = visitor(app, "alice"), staff(app)
    responses = [alice.get("/api/staff/panel"), receipts(alice, "c1"), staff_client.get("/api/staff/panel"),
                 receipts(staff_client, "c1"), staff_client.get("/api/staff/queue")]
    token = staff_client.get("/api/staff/panel").json()["form_token"]
    responses.append(staff_client.post("/api/staff/flag", json={"message_id": agent, "token": token,
                                                                 "correction": f"should have called {PHONE}"}))
    for response in responses:
        assert response.status_code == 200, response.text
        assert_masked(response.text)
    assert "[phone]" in responses[0].text and "[email]" in responses[1].text and "[street]" in responses[4].text
    assert "Linda Foster" in responses[0].text  # names stay, so staff can still find the caller


def test_a_flags_correction_note_is_stored_masked(app, store):
    store.open_conversation("alice", "c1")
    agent = reply(store, "c1", "is the diagnostic fee still $79?", "Yes, it is $79.")
    client = staff(app)
    token = client.get("/api/staff/panel").json()["form_token"]
    response = client.post("/api/staff/flag", json={"message_id": agent, "token": token,
                                                    "correction": f"It is $89 now; tell them to email {EMAIL}."})
    assert response.status_code == 200
    [flag] = store.flags()
    assert flag["message_id"] == agent and flag["conversation_id"] == "c1"
    assert flag["correction"] == "It is $89 now; tell them to email [email]."


def test_only_agent_replies_can_be_flagged(app, store):
    store.open_conversation("alice", "c1")
    caller = store.log_message("c1", "caller", "hello")
    client = staff(app)
    token = client.get("/api/staff/panel").json()["form_token"]
    for message_id in (caller, 9999):
        assert client.post("/api/staff/flag", json={"message_id": message_id, "token": token,
                                                    "correction": "x"}).status_code == 404
    assert store.flags() == []


def test_export_flags_writes_each_flagged_conversation_as_a_candidate_case(store, tmp_path, clock):
    from pipeline.export_flags import export_flags

    store.open_conversation("alice", "c1")
    wrong = reply(store, "c1", "is the diagnostic fee still $79?", "Yes, it is $79.")
    clock.now += timedelta(seconds=3)
    second = reply(store, "c1", f"ok, my number is {PHONE}", "Thanks.")
    store.add_flag(wrong, "The fee is $89 under the current price list.")
    store.add_flag(second, "Should have confirmed the number.")
    store.open_conversation("bob", "c2")
    other = reply(store, "c2", "do you install water heaters?", "We don't.")
    store.add_flag(other, "We do; see the plumbing services page.")
    store.open_conversation("carol", "c3")
    reply(store, "c3", "hi", "Hello.")  # never flagged: not exported

    out = tmp_path / "candidates"
    written = export_flags(store, out)
    assert len(written) == 2 and all(path.parent == out for path in written)
    cases = {json.loads(path.read_text())["source_conversation_id"]: json.loads(path.read_text()) for path in written}
    assert set(cases) == {"c1", "c2"}
    first = cases["c1"]
    assert first["case_id"].startswith("FLAG-") and first["candidate"] is True
    assert first["caller_script"] == ["is the diagnostic fee still $79?", "ok, my number is [phone]"]
    assert [f["correction"] for f in first["flags"]] == ["The fee is $89 under the current price list.",
                                                       "Should have confirmed the number."]
    assert first["flags"][0]["reply"] == "Yes, it is $79."
    assert {"caller_script", "caller_card", "fixtures", "requests", "expected_outcome", "expected_handoff_reason",
            "reference_answer", "must_not"} <= set(first)
    assert first["expected_outcome"] is None and first["reference_answer"] is None  # the author fills these in
    assert export_flags(store, out) == written  # the same file names on a second run, rewritten in place


def test_export_flags_never_writes_into_the_test_set(store):
    from pipeline import export_flags as module

    assert module.DEFAULT_OUT.name == "candidates" and "testset" not in str(module.DEFAULT_OUT)
    with pytest.raises(ValueError):
        module.export_flags(store, module.ROOT / "data" / "testset")


# -- Security review: concurrent guesses, logout and password changes ----------------------------------------------

def test_concurrent_wrong_guesses_cannot_pass_the_limit_while_the_hash_check_runs():
    # Each attempt is counted before the slow password check, so parallel guesses cannot all slip under five.
    from app.web.staff import SignInLimit
    limit = SignInLimit(Clock())
    held = [limit.reserve("10.0.0.1") for _ in range(7)]
    assert sum(r is not None for r in held) == 5
    limit.release("10.0.0.1", held[0])  # a correct password gives its attempt back
    assert limit.reserve("10.0.0.1") is not None and limit.reserve("10.0.0.1") is None


def test_logging_out_ends_the_session_on_the_server_too(app, store, clock):
    client = staff(app)
    cookie = client.cookies.get("meridian_staff")
    assert client.post("/api/staff/logout").status_code == 200
    copy = visitor(app, "someone-else", "10.0.0.10")
    copy.cookies.set("meridian_staff", cookie)
    assert copy.get("/api/staff/queue").status_code == 403
    restarted = create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=clock,
                           staff_password_hash=hash_password(PASSWORD, iterations=1000))
    again = visitor(restarted, "someone-else", "10.0.0.10")
    again.cookies.set("meridian_staff", cookie)
    assert again.get("/api/staff/queue").status_code == 403  # still ended after a restart


def test_changing_the_staff_password_ends_every_session(app, store, clock):
    cookie = staff(app).cookies.get("meridian_staff")
    changed = create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=clock,
                         staff_password_hash=hash_password("a new staff password", iterations=1000))
    client = visitor(changed, "staffer", "10.0.0.9")
    client.cookies.set("meridian_staff", cookie)
    assert client.get("/api/staff/queue").status_code == 403
