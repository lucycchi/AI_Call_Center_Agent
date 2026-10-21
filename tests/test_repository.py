"""README, video outline and repository contents (Task 28, R78, R79, R80).

The README has the required sections and quotes the frozen held-out containment numbers exactly as
data/results/final/summary.json records them; the repository tracks the evidence files; no tracked file holds a key,
token or webhook secret; and the video outline covers the four topics in 3 to 4 minutes of speech.

The secret scan reads the local .env (when there is one) only to know which values to search for. Values are never
printed: a failure names the file and the variable or pattern name, never the matched text."""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SUMMARY = ROOT / "data" / "results" / "final" / "summary.json"
OUTLINE = ROOT / "docs" / "VIDEO_OUTLINE.md"


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [name for name in out.decode().split("\0") if name]


def sections(text: str) -> dict[str, str]:
    """Each Markdown heading (any level) mapped to the text up to the next heading of the same or a higher level."""
    found: dict[str, str] = {}
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), m.group(2).strip()) for i, line in enumerate(lines)
             if (m := re.match(r"^(#{1,6})\s+(.*)$", line))]
    for n, (i, level, title) in enumerate(heads):
        end = next((j for j, lv, _ in heads[n + 1:] if lv <= level), len(lines))
        found[title] = "\n".join(lines[i + 1:end])
    return found


# --- README -----------------------------------------------------------------------------------------------------------

REQUIRED_SECTIONS = ["What it does", "Install", "Run", "Tests", "Evaluation", "Results", "Containment",
                     "Executive findings", "Feedback loop", "Uptime monitoring", "Rollback"]


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text()


@pytest.mark.parametrize("title", REQUIRED_SECTIONS)
def test_readme_has_section(readme, title):
    assert title in sections(readme), f"README.md has no '{title}' heading"


# The Containment section's table: row label -> the summary.json field it must equal.
CONTAINMENT_ROWS = {
    "Containment": "containment",
    "Containment without redirects": "containment_without_redirects",
    "Scope ceiling": "scope_ceiling",
    "Adjusted ceiling": "adjusted_ceiling",
    "Action gap": "action_gap",
    "Human baseline": "human_baseline",
    "Human baseline excluding account actions": "human_baseline_excluding_actions",
}


def table_values(text: str) -> dict[str, str]:
    """First two cells of each Markdown table row: label -> value."""
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if len(cells) >= 2:
            rows[cells[0].strip("*")] = cells[1]
    return rows


@pytest.mark.parametrize("label,field", CONTAINMENT_ROWS.items())
def test_readme_containment_numbers_match_the_final_summary(readme, label, field):
    summary = json.loads(SUMMARY.read_text())
    rows = table_values(sections(readme).get("Containment", ""))
    assert label in rows, f"the README's Containment table has no '{label}' row"
    quoted = re.search(r"(\d+(?:\.\d)?)\s*%", rows[label])
    assert quoted, f"the README's '{label}' row gives no percentage"
    assert quoted.group(1) == f"{summary[field] * 100:.1f}", f"the README's '{label}' differs from summary.json {field}"


def test_readme_never_carries_the_reviewer_link(readme):
    assert "#r=" not in readme.replace("#r=<token>", ""), "README.md contains a reviewer link"


# --- repository contents (R80) ----------------------------------------------------------------------------------------

REQUIRED_FILES = ["data/document_list.csv", "data/conflict_register.csv", "data/labels_haiku.csv",
                  "data/labels_codex.csv", "data/labels_fable.csv", "eval/grader_prompt.md",
                  "data/results/final/verdicts.jsonl", "data/results/final/summary.json"]


@pytest.mark.parametrize("path", REQUIRED_FILES)
def test_repository_tracks(path):
    assert path in set(tracked_files()), f"{path} is not tracked by git"


def test_repository_tracks_the_test_set_with_caller_cards_and_reference_answers():
    cases = [p for p in tracked_files() if p.startswith("data/testset/") and p.endswith(".json")]
    assert cases, "no test cases are tracked under data/testset/"
    for path in cases:
        case = json.loads((ROOT / path).read_text())
        assert case.get("caller_card"), f"{path} has no caller card"
        assert "reference_answer" in case, f"{path} has no reference answer field"


# --- no secrets committed (R80) ---------------------------------------------------------------------------------------

BINARY_SUFFIXES = {".npy", ".sqlite", ".db", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".mp3",
                   ".mp4", ".wav", ".woff", ".woff2", ".zip", ".gz"}

# Full key shapes, so a mention of a prefix in the documentation is not a hit.
SECRET_PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9]{20,}"),
    "Voyage key": re.compile(r"\bpa-[A-Za-z0-9_-]{20,}"),
    "Fly.io token": re.compile(r"FlyV1\s+fm\d_[A-Za-z0-9+/=_-]{20,}"),
    "Slack webhook": re.compile(r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{8,}"),
    "Discord webhook": re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]{20,}"),
}

ENV_SECRETS = ["REVIEWER_TOKEN", "VISITOR_COOKIE_SECRET", "SESSION_SECRET", "STAFF_PASSWORD", "STAFF_PASSWORD_HASH",
               "ANTHROPIC_API_KEY", "EVAL_ANTHROPIC_API_KEY", "SITE_ANTHROPIC_API_KEY", "OPENAI_API_KEY",
               "VOYAGE_API_KEY", "ELEVENLABS_API_KEY", "ALERT_WEBHOOK_URL"]


def text_files() -> list[tuple[str, str]]:
    files = []
    for path in tracked_files():
        full = ROOT / path
        if path.startswith("data/index/") or full.suffix.lower() in BINARY_SUFFIXES or not full.is_file():
            continue
        raw = full.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        files.append((path, raw.decode("utf-8", errors="ignore")))
    return files


@pytest.fixture(scope="module")
def tracked_text() -> list[tuple[str, str]]:
    return text_files()


def test_no_tracked_file_holds_a_key_shape(tracked_text):
    hits = [f"{path}: {name}" for path, text in tracked_text for name, pattern in SECRET_PATTERNS.items()
            if pattern.search(text)]
    assert not hits, "secret-shaped text in tracked files: " + "; ".join(hits)


def test_no_tracked_file_holds_a_local_env_value(tracked_text):
    env = ROOT / ".env"
    if not env.exists():
        pytest.skip("no local .env to compare against")
    from dotenv import dotenv_values

    values = {name: value for name, value in dotenv_values(env).items()
              if name in ENV_SECRETS and value and len(value) >= 8}
    hits = [f"{path}: value of {name}" for path, text in tracked_text for name, value in values.items()
            if value in text]
    assert not hits, "local .env values in tracked files: " + "; ".join(hits)


# --- video outline (R79) ----------------------------------------------------------------------------------------------

OUTLINE_TOPICS = {
    "how the call drivers were found": [r"call drivers?", r"transcripts?"],
    "why this chunking and retrieval": [r"chunk", r"(retrieval|search)"],
    "how handoff works": [r"hand ?off"],
    "what the numbers say": [r"numbers", r"containment|contained|percent"],
}


@pytest.fixture(scope="module")
def outline() -> str:
    assert OUTLINE.exists(), "docs/VIDEO_OUTLINE.md is missing"
    return OUTLINE.read_text()


@pytest.mark.parametrize("topic", OUTLINE_TOPICS)
def test_video_outline_covers(outline, topic):
    text = outline.lower()
    for pattern in OUTLINE_TOPICS[topic]:
        assert re.search(pattern, text), f"the video outline does not cover {topic} (no '{pattern}')"


def test_video_outline_is_sized_for_three_to_four_minutes(outline):
    """Spoken lines are the quoted (>) voiceover lines when there are any, otherwise the whole outline; at about 165
    words a minute, 3 to 4 minutes is roughly 350 to 700 words."""
    spoken = [line.lstrip("> ") for line in outline.splitlines() if line.startswith(">")] or outline.splitlines()
    words = len(" ".join(spoken).split())
    assert 350 <= words <= 700, f"the video outline's voiceover is {words} words, not 350 to 700"
