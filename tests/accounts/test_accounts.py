import shutil
import sqlite3
from pathlib import Path

import pytest

from app.accounts.fee_check import fee_mismatches
from app.accounts.identity import identify
from app.accounts.lookups import is_action_request, membership, open_invoices, read_only, system

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "call_data" / "scheduling_db" / "meridian_scheduling.sqlite"


@pytest.fixture
def db(tmp_path):
    copy = tmp_path / "copy.sqlite"
    shutil.copy(SEED, copy)
    return read_only(copy)


def test_name_with_account_identifies_and_name_alone_never_does(db):
    assert identify(db, "Linda Foster", "MHC-10001").customer_id == "MHC-10001"
    assert identify(db, "Linda Foster") is None


@pytest.mark.parametrize("kwargs", [{"account": "mhc 10001"}, {"phone": "512 555 0101"}, {"address": "4412 oak hollow dr"},
                                    {"address": "4412 Oak Hollow Drive, Round Rock"}, {"phone": "(512) 555-0101"}])
def test_identification_ignores_case_spaces_punctuation_and_dashes(db, kwargs):
    assert identify(db, "linda  foster", **kwargs).customer_id == "MHC-10001"


def test_a_wrong_second_fact_or_wrong_name_does_not_identify(db):
    assert identify(db, "Linda Foster", "MHC-10002") is None
    assert identify(db, "Omar Patel", "MHC-10001") is None
    assert identify(db, "Linda Foster", phone="512 555 0199") is None


def test_open_invoices_are_read_exactly_as_recorded(db):
    [invoice] = open_invoices(db, "MHC-10002")
    assert invoice.invoice_id == "INV-204411"
    assert (invoice.balance_cents, invoice.due_date) == (47800, "2026-11-01")
    assert invoice.lines == [("Diagnostic visit", 8900), ("Contactor replacement", 24500), ("After-hours dispatch", 14400)]
    assert open_invoices(db, "MHC-10001") == []


def test_fixed_fees_that_differ_from_the_current_schedule_are_found(db):
    [invoice] = open_invoices(db, "MHC-10002")
    assert fee_mismatches(invoice) == ["after-hours dispatch 144.00 vs schedule 149.00"]


def test_membership_renews_at_the_current_published_price(db):
    standard = membership(db, "MHC-10001")
    assert (standard.tier, standard.renewal_date, standard.renewal_price_cents) == ("standard", "2026-11-03", 18900)
    plus = membership(db, "MHC-10003")
    assert (plus.tier, plus.renewal_price_cents) == ("plus", 26900)
    assert membership(db, "MHC-10002").tier == "none" and membership(db, "MHC-10002").renewal_price_cents is None


def test_system_brand_and_install_date(db):
    found = system(db, "MHC-10003")
    assert (found.brand, found.install_date) == ("Lennox", "2025-11-30")


def test_lookups_cannot_write(db):
    with pytest.raises(sqlite3.OperationalError):
        db.execute("update customers set name = 'x'")


@pytest.mark.parametrize("text", ["send me a payment link", "set up autopay", "cancel my auto-renew",
                                  "I want to cancel my Comfort Club membership", "please waive the fee",
                                  "sign me up for the maintenance plan",
                                  "I need to pay invoice INV-263891.", "I want to pay my balance"])
def test_money_and_membership_actions_are_recognised(text):
    assert is_action_request(text)


@pytest.mark.parametrize("text", ["what's my balance", "I need to cancel my appointment", "what does the Comfort Club include",
                                  "when does my membership renew", "I'm a Comfort Club member",
                                  "Okay, I'll pay it through the portal.", "Can I pay it over the phone?"])
def test_questions_are_not_action_requests(text):
    assert not is_action_request(text)


# The code backstop catches only unmistakable requests; the router decides everything else (R48, D43).
def _labelled_actions():
    import json
    return [json.loads(line) for line in (ROOT / "data" / "eval" / "action_requests.jsonl").open()]


UNMISTAKABLE = ["send me a payment link", "Can I get a payment link?", "Text me a link to pay.", "I want to set up autopay",
                "Put me on autopay.", "Take me off autopay", "please cancel my Comfort Club membership", "Cancel my membership.",
                "turn off my auto-renew", "Please turn off auto renew.", "I want to cancel my auto-renew", "refund me the $89",
                "I want a refund", "I’d like a refund.", "please waive the fee", "I want to pay my bill", "Pay my bill please",
                "I would like to pay my invoice.", "I need to pay invoice INV-263891.", "sign me up for the Comfort Club"]


@pytest.mark.parametrize("text", UNMISTAKABLE)
def test_unmistakable_requests_are_caught_in_code(text):
    assert is_action_request(text)


def test_the_code_backstop_never_fires_on_a_labelled_question():
    hits = [row["text"] for row in _labelled_actions() if row["expected"] == "not action" and is_action_request(row["text"])]
    assert not hits, hits


def test_the_labelled_action_set_is_well_formed():
    rows = _labelled_actions()
    assert {row["expected"] for row in rows} == {"action", "not action"} and len(rows) >= 60
