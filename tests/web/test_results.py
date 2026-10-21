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

from app.config import AUSTIN, ROOT
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


def test_a_long_value_wraps_so_the_definitions_stay_on_screen(store, tmp_path):
    # Value cells never wrap, so one long value pushed "What it means" off the page; long lists are also cut short.
    settings = {f"setting_{i}": "x" * 20 for i in range(40)}
    summary = summary_fixture() | {"extra": {"settings": settings},
                                   "retrieval": {"keyword": {"misses": [f"case-T{i:08x}" for i in range(12)]}}}
    frozen = section(results_page(store, tmp_path, summary), "frozen-results")
    long_cells = re.findall(r'<td class="long">([^<]*)</td>', frozen)
    assert any("case-T00000000" in cell and "and 6 more (12 in all)" in cell for cell in long_cells)
    assert "case-T0000000b" not in frozen  # the list is truncated with a count
    assert "setting 39" in frozen and "{" not in frozen  # each setting is its own row, not a JSON blob
    assert re.search(r'<tr data-field="containment">.*?<td>62\.0%</td>', frozen, re.S)  # short values stay unwrapped
    page = results_page(store, tmp_path, summary)
    assert re.search(r"table\.numbers td\.long\s*\{[^}]*white-space:\s*normal", page)
    assert re.search(r"table\.numbers\s*\{[^}]*table-layout:\s*fixed", page)  # a long value cannot widen its column


def test_without_a_final_summary_it_says_final_results_not_yet_run(store, tmp_path):
    page = results_page(store, tmp_path, None)
    frozen = section(page, "frozen-results")
    assert "Final results not yet run" in frozen
    assert "data-field" not in frozen
    assert "Live containment" in section(page, "live-traffic")


@pytest.mark.parametrize("partial", ["run", "section", "field"])
def test_a_summary_without_the_validated_sections_is_not_shown_as_the_final_results(store, tmp_path, partial):
    """A run's own summary (for example the partial one a crashed grading run leaves) is never the final summary."""
    summary = summary_fixture()
    if partial == "run":
        summary = {k: v for k, v in summary.items() if k not in SECTIONS} | {"extra": {"failed": "x", "partial": True}}
    elif partial == "section":
        summary["adversarial"] = None
    else:
        del summary["containment"]
    frozen = section(results_page(store, tmp_path, summary), "frozen-results")
    assert "Final results not yet run" in frozen and "data-field" not in frozen


# -- Readable sections, the grader wording, consistency and the frozen-agent note ------------------------------------

COMMITTED = ROOT / "data" / "results" / "final" / "summary.json"
CONSISTENCY = {"cases": 15, "runs": 3, "seed": 3, "correct_all_three": 0.6666666666666666,
               "correct_each_run": [0.8666666666666667, 0.8, 0.7333333333333333],
               "not_always_correct": ["T28588235", "T3baed8ff", "T9f473de6", "Td1e329a6", "Teff9802d"]}


def committed_summary() -> dict:
    if not COMMITTED.exists():
        pytest.skip("no committed final summary")
    return json.loads(COMMITTED.read_text())


def block(frozen: str, name: str) -> str:
    match = re.search(rf'<tbody data-section="{name}">(.*?)</tbody>', frozen, re.S)
    assert match, f"no {name} section"
    return match.group(1)


def test_the_committed_summary_shows_readable_tables_not_json(store, tmp_path):
    frozen = section(results_page(store, tmp_path, committed_summary()), "frozen-results")
    assert "{" not in frozen and "}" not in frozen  # no raw JSON anywhere in the frozen results
    retrieval = block(frozen, "retrieval")
    for column in ("Keyword search", "Meaning search", "Combined"):  # search modes are columns
        assert f"<th scope=\"col\">{column}</th>" in retrieval
    assert "Hit in top 5" in retrieval and "77.3%" in retrieval and "97.7%" in retrieval
    assert "case-T2603f4e6" in retrieval
    answers = block(frozen, "answers")
    assert "Whole knowledge base" in answers and "92.0%" in answers and "not measured" in answers
    grader = block(frozen, "grader_agreement")
    assert "83.3%" in grader and "case-T7d8fb3e5 (whole knowledge base)" in grader
    labels = block(frozen, "label_agreement")
    assert re.search(r"Disagreements, Codex and Claude Haiku</th><td>none</td>", labels)
    assert re.search(r"Human labels</th><td>0</td>", labels)
    # The run settings: the four model roles are columns, and plain numbers are not turned into percentages.
    for column in ("Simulated caller", "Router", "Reply writer", "Reply check"):
        assert f"<th scope=\"col\">{column}</th>" in frozen
    assert "claude-sonnet-5-5" in frozen and "$0.39" in frozen and "$8.00" in frozen
    assert re.search(r"Search score threshold</th><td>0\.25</td>", frozen) and "25.0%" not in frozen
    assert re.search(r"Ticket actionable</th><td>72\.7%</td>", frozen)
    for _, (_, definition) in SECTIONS.items():
        assert html.escape(definition) in frozen


def test_section_values_are_escaped(store, tmp_path):
    summary = summary_fixture() | {"retrieval": {"set": "<script>x</script>", "keyword": {"misses": ["<b>"]}}}
    frozen = section(results_page(store, tmp_path, summary), "frozen-results")
    assert "<script>" not in frozen and "&lt;script&gt;" in frozen and "&lt;b&gt;" in frozen


def test_the_grader_check_is_described_as_claude_fable_grading_blind_not_a_human_check(store, tmp_path):
    page = results_page(store, tmp_path, summary_fixture())
    definition = SECTIONS["grader_agreement"][1]
    assert "Claude Fable 5.1" in definition and "not a human check" in definition and "blind" in definition
    assert "author's own" not in page and "own blind grades" not in page
    assert not re.search(r"(the author|a person|a human|staff) (graded|checked|reviewed)", page, re.I)


def test_the_consistency_result_is_shown_when_its_summary_exists(store, tmp_path):
    path = tmp_path / "final" / "consistency" / "summary.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(CONSISTENCY))
    frozen = section(results_page(store, tmp_path, summary_fixture()), "frozen-results")
    consistency = block(frozen, "consistency")
    assert re.search(r"Correct on all three runs</th><td>66\.7%</td>", consistency)
    assert re.search(r"Cases</th><td>15</td>", consistency) and re.search(r"Runs</th><td>3</td>", consistency)
    assert "86.7%, 80.0%, 73.3%" in consistency and "T28588235" in consistency
    assert "{" not in consistency


def test_without_a_consistency_summary_no_consistency_section_is_shown(store, tmp_path):
    frozen = section(results_page(store, tmp_path, summary_fixture()), "frozen-results")
    assert 'data-section="consistency"' not in frozen


def test_a_note_names_the_frozen_agent_hash_and_the_later_live_build(store, tmp_path):
    agent = "5b8f6899c76b23be395a0e225416a9d72ba3e9cdfa628e42a6c4b04e8eb33e45"
    frozen = section(results_page(store, tmp_path, summary_fixture() | {"agent_hash": agent}), "frozen-results")
    note = re.search(r'<p class="frozen-note">(.*?)</p>', frozen, re.S)
    assert note and agent in note.group(1) and "held-out" in note.group(1)
    assert "later build" in note.group(1) and "README" in note.group(1)
    assert frozen.index("<table") < frozen.index('class="frozen-note"')  # under the frozen numbers


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
