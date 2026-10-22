"""The fresh test set: 30 new cases written blind by Codex, one per sub-reason, weighted by its calls."""

import pytest

from eval import fresh_cases as fresh


def test_there_is_one_slot_per_sub_reason_and_the_weights_are_the_420_calls():
    slots = fresh.slots()
    assert len(slots) == 30
    assert len({(s["reason"], s["sub_reason"]) for s in slots}) == 30
    assert sum(s["calls_weight"] for s in slots) == 420
    assert {s["case_id"] for s in slots} == {f"F{n:02d}" for n in range(1, 31)}
    # The two "cancel" sub-reasons stay apart: the appointment one is named as the case builder names it.
    assert ("existing appointment", "cancel appointment") in {(s["reason"], s["sub_reason"]) for s in slots}


@pytest.mark.parametrize("sub,outcome,why", [
    ("pay an invoice", "contained", None),         # the agent sends a payment link (author's choice, 2026-10-21)
    ("upgrade", "contained", None),                # the agent enrols or upgrades after a read-back
    ("autopay", "contained", None),                # an autopay link, under the author-supplied autopay policy
    ("cancel", "contained", None),                 # the agent turns auto-renew off; a refund request still hands off
    ("refund", "handed_off", "dispute"),
    ("hvac repair", "contained", None),
])
def test_expected_outcomes_follow_the_new_scope(sub, outcome, why):
    # The author's choices of 2026-10-21: payment and autopay links, enrolment, upgrades and cancelling auto-renew.
    assert fresh.expected("billing" if sub in ("pay an invoice", "refund") else "membership", sub, "south") == (outcome, why)


@pytest.mark.parametrize("kind,outcome", [("action:payment link", "contained"), ("action:enrol", "contained"),
                                          ("action:upgrade", "contained"), ("action:autopay", "contained"),
                                          ("action:cancel auto-renew", "contained"), ("action:refund", "handed_off"),
                                          ("knowledge", "contained")])
def test_second_requests_follow_the_new_scope(kind, outcome):
    [request] = fresh.requests_for({"extra_requests": [{"request": "r", "kind": kind, "caller_words": "w"}]}, "south")
    assert request["expected_outcome"] == outcome


def _scenario(**changes):
    base = {"sub_reason": "pay an invoice",
            "caller_script": ["Hi, I need to pay my bill, the one for ${amount}.", "{name}, account {account}.",
                              "Text it to {phone} please.", "That's all, thanks."],
            "card_needs": {"city": None, "tier": None, "brand": None, "install_after": None, "install_before": None},
            "invoice": {"amount_dollars": 312, "paid": False}, "appointment": None, "extra_requests": [],
            "knowledge": {"reference_answer": "Agents send a secure payment link by text or email, valid for 24 hours.",
                          "evidence": [{"file": "faq__customer_faq.md", "heading": "Payment",
                                        "phrases": ["Agents send a secure payment link"]}]}}
    return base | changes


def test_a_scenario_becomes_a_case_with_a_real_customer_and_its_invoice():
    slot = next(s for s in fresh.slots() if s["sub_reason"] == "pay an invoice")
    case = fresh.build_case(slot, _scenario())
    card = case["caller_card"]
    assert case["case_id"] == slot["case_id"] and case["calls_weight"] == slot["calls_weight"]
    assert case["caller_script"][1] == f"{card['name']}, account {card['customer_id']}."
    assert card["phone"] in case["caller_script"][2] and "{" not in " ".join(case["caller_script"])
    [invoice] = [f for f in case["fixtures"] if f["table"] == "invoices"]
    assert invoice["row"]["customer_id"] == card["customer_id"] and invoice["row"]["balance_cents"] == 31200
    assert "$312" in case["caller_script"][0]
    assert case["expected_outcome"] == "contained" and case["needs_documents"]
    assert case["evidence_spans"][0]["file"] == "faq__customer_faq.md"
    assert case["source"] == "fresh: written blind by Codex"


def test_a_scenario_with_an_unknown_placeholder_or_a_phrase_not_in_the_documents_is_refused():
    slot = next(s for s in fresh.slots() if s["sub_reason"] == "pay an invoice")
    with pytest.raises(ValueError, match="placeholder"):
        fresh.build_case(slot, _scenario(caller_script=["My email is {email_address}."]))
    bad = {"reference_answer": "x", "evidence": [{"file": "faq__customer_faq.md", "heading": "Payment",
                                                  "phrases": ["we take cash at the door"]}]}
    with pytest.raises(ValueError, match="matches 0 lines"):
        fresh.build_case(slot, _scenario(knowledge=bad))


def test_an_existing_appointment_case_gets_an_appointment_on_its_fixed_day():
    slot = next(s for s in fresh.slots() if s["sub_reason"] == "reschedule")
    scenario = _scenario(sub_reason="reschedule", invoice=None, knowledge=None,
                         appointment={"window": None, "service": "hvac_repair"},
                         caller_script=["I need to move tomorrow's appointment.", "{name}, {address} in {city}."])
    case = fresh.build_case(slot, scenario)
    assert case["appointment"]["slot_date"] == "2026-10-17"
    assert case["caller_card"]["service_address"] in case["caller_script"][1]


# -- the guard ---------------------------------------------------------------------------------------------------

def _frozen(tmp_path):
    root = tmp_path / "repo"
    (root / "data" / "testset_fresh").mkdir(parents=True)
    (root / "data" / "testset_fresh" / "F01.json").write_text('{"case_id": "F01"}')
    fresh.freeze(root)
    return root


def test_the_fresh_set_runs_only_with_its_flag_once_per_agent_and_unchanged(tmp_path):
    root = _frozen(tmp_path)
    with pytest.raises(SystemExit, match="--fresh-final"):
        fresh.refuse(["F01"], final=False, agent_hash="a1", root=root)
    fresh.refuse(["F01"], final=True, agent_hash="a1", root=root)
    fresh.record_run("a1", "fresh-a1", root=root)
    with pytest.raises(SystemExit, match="already ran"):
        fresh.refuse(["F01"], final=True, agent_hash="a1", root=root)
    fresh.refuse(["F01"], final=True, agent_hash="b2", root=root)
    (root / "data" / "testset_fresh" / "F01.json").write_text('{"case_id": "F01", "changed": true}')
    with pytest.raises(SystemExit, match="changed since"):
        fresh.refuse(["F01"], final=True, agent_hash="b2", root=root)


def test_an_unfrozen_set_never_runs(tmp_path):
    root = tmp_path / "repo"
    (root / "data" / "testset_fresh").mkdir(parents=True)
    with pytest.raises(SystemExit, match="not frozen"):
        fresh.refuse(["F01"], final=True, agent_hash="a1", root=root)


def test_the_run_command_refuses_the_fresh_set_without_its_flag(monkeypatch):
    import eval.run as run

    def never(*args, **kwargs):
        raise AssertionError("a test must never start a real run")
    monkeypatch.setattr(run, "run_graded", never)
    monkeypatch.setattr(run, "build_client", never)
    monkeypatch.setattr(fresh, "refuse", lambda ids, final, agent_hash, root=None: (_ for _ in ()).throw(
        SystemExit("refusing to run fresh cases without --fresh-final")) if not final else None)
    monkeypatch.setattr("sys.argv", ["eval.run", "--set", "fresh"])
    with pytest.raises(SystemExit, match="--fresh-final"):
        run.main()


def test_an_appointment_for_a_service_gets_a_customer_in_a_zone_that_offers_it():
    # Seen building the set: a plumbing reschedule drew a north-zone customer, and the north zone has no plumbing slots.
    slot = next(s for s in fresh.slots() if s["sub_reason"] == "reschedule")
    scenario = _scenario(sub_reason="reschedule", invoice=None, knowledge=None,
                         appointment={"window": None, "service": "plumbing", "date": "2026-10-19"},
                         caller_script=["I need to move my plumbing visit on Monday.", "{name}, {phone}."])
    case = fresh.build_case(slot, scenario)
    assert case["caller_card"]["zone"] != "north"


def test_an_appointment_no_free_technician_can_hold_is_planted_and_marked():
    # Seen building the set: a tune-up confirmation for Thursday 4 to 7 had no free technician in any zone.
    slot = next(s for s in fresh.slots() if s["sub_reason"] == "confirm")
    scenario = _scenario(sub_reason="confirm", invoice=None, knowledge=None,
                         appointment={"window": "16:00-19:00", "service": "hvac_tune_up"},
                         caller_script=["Is my tune-up Thursday from 4 to 7 still on?", "{name}, {account}."])
    case = fresh.build_case(slot, scenario)
    assert case["appointment"]["window"] == "16:00-19:00" and case["appointment"]["source"] == "planted with overlap"
    tables = [f["table"] for f in case["fixtures"]]
    assert "appointment_slots" in tables and "appointments" in tables


def test_resume_grades_the_saved_fresh_run_and_never_starts_a_new_one(monkeypatch, tmp_path):
    # Seen on the first fresh run: grading crashed after the conversations were saved; they are graded, not run again.
    import eval.run as run
    calls = []

    def never(*args, **kwargs):
        raise AssertionError("resume must never start a new run")

    class Summary:
        def to_json(self):
            return {}
    monkeypatch.setattr(run, "run_graded", never)
    monkeypatch.setattr(run, "resume_graded", lambda cases, out, **kw: calls.append((len(cases), out.name)) or (None, Summary()))
    monkeypatch.setattr(fresh, "refuse", lambda ids, final, agent_hash, root=None: None)
    monkeypatch.setattr(fresh, "record_run", lambda agent, folder, root=None: calls.append(("recorded", folder)))
    monkeypatch.setattr("sys.argv", ["eval.run", "--set", "fresh", "--fresh-final", "--name", "fresh-x", "--resume"])
    run.main()
    assert calls == [(30, "fresh-x"), ("recorded", "fresh-x")]
