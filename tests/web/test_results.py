"""The Results tab (Task 24; R67 to R69): the frozen held-out numbers with a plain definition of each, kept apart from
the live demo traffic box, the "try these" scenarios and the three executive callouts. No model is ever called; the
final summary is a fixture written to a temporary folder (the real one is made by Task 27)."""

import dataclasses
import html
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import AUSTIN
from app.ops.store import OpsStore
from app.web.main import create_app
from app.web.results import FIELDS, SECTIONS, executive_callouts
from eval.scoring import Summary
from tests.web.test_chat import FakeEngine

SECRET = "test-only-secret"
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=AUSTIN)


def summary_fixture() -> dict:
    summary = Summary(containment=0.62, containment_without_redirects=0.58, scope_ceiling=0.91, adjusted_ceiling=0.74,
                      action_gap=0.17, wrong_confident=1, knowledge_accuracy=0.9, routing_accuracy=0.95,
                      handoff_correct_safety_and_booking=1.0, handoff_correct_other=0.875, booking_correct=1.0,
                      lookup_correct=0.9, clean_declines=2, flaky=["T07"], interval_low=0.48, interval_high=0.76,
                      scenarios=15, weighted_calls=118, human_baseline=0.85, human_baseline_excluding_actions=0.73,
                      wrong_confident_cases=["T31"], wrong_confident_share=0.03).to_json()
    return summary | {"retrieval": {"recall_at_5": 0.92, "hit_rate_at_5": 0.95},
                      "answers": {"combined_correct": 0.88, "whole_kb_correct": 0.8},
                      "adversarial": {"pass_rate": 1.0, "booking_rule_pass_rate": 1.0, "extraction_pass_rate": 1.0},
                      "grader_agreement": {"agreement": 0.9, "both_right": 12},
                      "label_agreement": {"codex_vs_haiku": 1.0, "fable_vs_codex": 1.0}}


@pytest.fixture
def store(tmp_path):
    return OpsStore(tmp_path / "ops.sqlite", clock=lambda: NOW)


def results_page(store, tmp_path, summary: dict | None) -> str:
    path = tmp_path / "final" / "summary.json"
    if summary is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary))
    app = create_app(FakeEngine(store), store, cookie_secret=SECRET, clock=lambda: NOW, results_summary_path=path)
    client = TestClient(app, base_url="https://testserver")
    response = client.get("/results")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    return response.text


def section(page: str, name: str) -> str:
    match = re.search(rf'<section class="{name}"[^>]*>(.*?)</section>', page, re.S)
    assert match, f"no {name} section"
    return match.group(1)


# -- Frozen numbers and the live box -------------------------------------------------------------------------------

def test_frozen_numbers_sit_under_their_own_heading_apart_from_the_live_box(store, tmp_path):
    page = results_page(store, tmp_path, summary_fixture())
    frozen, live = section(page, "frozen-results"), section(page, "live-traffic")
    assert re.search(r"<h2>[^<]*frozen[^<]*test results[^<]*</h2>", frozen, re.I)
    assert re.search(r"<h2>[^<]*live demo traffic[^<]*</h2>", live, re.I)
    assert "62.0%" in frozen and "62.0%" not in live  # containment shows only with the frozen numbers
    for label in ("Conversations", "Handoffs", "Errors", "Median reply", "Live containment"):
        assert label in live
    assert "not enough conversations yet" in live  # live_numbers' label with no traffic
    assert page.index('class="frozen-results"') < page.index('class="live-traffic"')


def test_every_summary_field_is_shown_with_a_one_line_definition(store, tmp_path):
    page = results_page(store, tmp_path, summary_fixture())
    frozen = section(page, "frozen-results")
    for field in dataclasses.fields(Summary):
        assert field.name in FIELDS, f"no definition for {field.name}"
        label, _, definition = FIELDS[field.name]
        assert definition and "\n" not in definition and definition.endswith(".")
        row = re.search(rf'<tr data-field="{field.name}">(.*?)</tr>', frozen, re.S)
        assert row, f"{field.name} not shown"
        assert html.escape(label) in row.group(1) and html.escape(definition) in row.group(1)
    for name in ("retrieval", "answers", "adversarial", "grader_agreement", "label_agreement"):
        assert name in SECTIONS
        block = re.search(rf'<tbody data-section="{name}">(.*?)</tbody>', frozen, re.S)
        assert block and html.escape(SECTIONS[name][1]) in frozen
    assert "T31" in frozen and "T07" in frozen  # the listed cases are named
    assert "48.0% to 76.0%" in frozen or ("48.0%" in frozen and "76.0%" in frozen)


def test_without_a_final_summary_it_says_final_results_not_yet_run(store, tmp_path):
    page = results_page(store, tmp_path, None)
    frozen = section(page, "frozen-results")
    assert "Final results not yet run" in frozen
    assert "data-field" not in frozen
    assert "Live containment" in section(page, "live-traffic")


# -- Try these ----------------------------------------------------------------------------------------------------

SCENARIO_WORDS = [("linda foster", "plumb"), ("omar patel", "balance"), ("smell gas", "furnace"),
                  ("diagnostic fee", "$79"), ("members-only", ""), ("ignore", "instructions")]


def test_at_least_six_try_these_scenarios_each_with_an_expected_behaviour(store, tmp_path):
    page = results_page(store, tmp_path, None)
    tries = section(page, "try-these")
    items = re.findall(r'<li class="scenario">(.*?)</li>', tries, re.S)
    assert len(items) >= 6
    texts = []
    for item in items:
        link = re.search(r'<a class="try" href="([^"]+)" data-question="([^"]+)">', item)
        assert link, item
        href, question = html.unescape(link.group(1)), html.unescape(link.group(2))
        url = urlparse(href)
        assert url.path == "/" and parse_qs(url.query)["ask"] == [question]  # opens the Chat tab with the text
        expected = re.search(r'<p class="expected">Expected: ([^<]+)</p>', item)
        assert expected and len(expected.group(1)) > 20
        texts.append(question.lower() + " " + item.lower())
    for words in SCENARIO_WORDS:
        assert any(all(w in t for w in words) for t in texts), words


def test_the_chat_tab_fills_the_text_box_from_a_try_these_link_without_sending(store, tmp_path):
    results_page(store, tmp_path, None)
    client = TestClient(create_app(FakeEngine(store), store, cookie_secret=SECRET), base_url="https://testserver")
    chat = client.get("/").text
    nav = re.search(r'<nav class="tabs"[^>]*>(.*?)</nav>', chat, re.S).group(1)
    assert 'href="/"' in nav and 'href="/results"' in nav
    script = client.get("/static/chat.js").text
    handler = script.split("// Try these: fill the text box from the Results tab.")[1].split("// End of try these.")[0]
    assert 'get("ask")' in handler and "box.value" in handler and "replaceState" in handler
    assert "send(" not in handler and "fetch(" not in handler and "submit" not in handler


# -- Executive callouts -------------------------------------------------------------------------------------------

def test_exactly_three_executive_callouts_from_the_findings_document(store, tmp_path):
    for summary in (summary_fixture(), None):
        callouts = section(results_page(store, tmp_path, summary), "callouts")
        items = re.findall(r'<li class="callout"><strong>([^<]+)</strong>', callouts)
        assert items == ["Staff policy errors", "Capacity imbalance by zone", "Documentation gaps"]
    found = executive_callouts()
    assert len(found) == 3 and all(text and len(text) < 300 for _, text in found)
    assert "108 of 420" in found[0][1] and "north zone" in found[1][1]
