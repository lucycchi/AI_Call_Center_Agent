"""Deployment to Fly.io (Task 26, R77, R83): fly.toml, the Dockerfile and its .dockerignore, the first-start entrypoint,
scripts/deploy.sh (run against a fake scripts/fly and a fake quick run in a temporary copy, never the real flyctl) and
scripts/measure_latency.py (run against a fake server through an injected HTTP client, never the live site)."""

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SEED = "call_data/scheduling_db/meridian_scheduling.sqlite"
sys.path.insert(0, str(ROOT / "scripts"))


# --- fly.toml ---------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fly() -> dict:
    return tomllib.loads((ROOT / "fly.toml").read_text())


def test_fly_toml_mounts_a_volume_at_data(fly):
    mounts = fly["mounts"] if isinstance(fly["mounts"], list) else [fly["mounts"]]
    assert [m["destination"] for m in mounts] == ["/data"]
    assert mounts[0]["source"]


def test_fly_toml_keeps_one_machine_always_on(fly):
    service = fly["http_service"]
    assert service["auto_stop_machines"] == "off"
    assert service["min_machines_running"] == 1
    assert service["force_https"] is True


def test_fly_toml_checks_health(fly):
    checks = fly["http_service"]["checks"]
    assert any(c["path"] == "/health" and c.get("method", "GET").upper() == "GET" for c in checks)


def test_fly_toml_puts_both_databases_on_the_volume(fly):
    env = fly["env"]
    assert env["DATABASE_PATH"].startswith("/data/")
    assert env["OPS_DATABASE_PATH"].startswith("/data/")
    assert env["DATABASE_PATH"] != env["OPS_DATABASE_PATH"]


def test_fly_toml_holds_no_secret_values(fly):
    text = (ROOT / "fly.toml").read_text()
    for name in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "REVIEWER_TOKEN", "STAFF_PASSWORD_HASH", "ALERT_WEBHOOK_URL",
                 "VISITOR_COOKIE_SECRET", "EVAL_ANTHROPIC_API_KEY"):
        assert name not in text


# --- Dockerfile and .dockerignore -------------------------------------------------------------------------------------

def dockerfile() -> str:
    return (ROOT / "Dockerfile").read_text()


def copy_sources() -> list[str]:
    sources = []
    for line in dockerfile().splitlines():
        words = line.split()
        if words and words[0].upper() == "COPY" and not any(w.startswith("--from") for w in words):
            sources += [w for w in words[1:-1] if not w.startswith("--")]
    return sources


def test_dockerfile_copies_the_search_index_and_the_seed_database():
    sources = copy_sources()
    assert any(s.rstrip("/") == "data/index" for s in sources)
    assert SEED in sources


def test_dockerfile_copies_what_the_results_tab_reads():
    sources = copy_sources()
    assert "docs/FINDINGS.md" in sources
    assert any(s.startswith("data/result") for s in sources)  # data/results/final when Task 27 has written it


def test_dockerfile_runs_one_worker_of_the_app_factory():
    text = dockerfile()
    assert "app.web.main:build_app" in text and "--factory" in text
    assert re.findall(r"--workers[\" ,]+(\d+)", text) == ["1"]


def test_dockerfile_never_copies_the_whole_project_or_secrets():
    for source in copy_sources():
        assert source not in (".", "./", "*")
        assert ".env" not in source and "testset" not in source and "split" not in source


def dockerignore_rules() -> list[tuple[bool, str]]:
    rules = []
    for line in (ROOT / ".dockerignore").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append((line.startswith("!"), line.lstrip("!").strip("/")))
    return rules


def in_context(path: str) -> bool:
    """Docker's rule for one path: the last matching pattern wins; a pattern also matches everything under it."""
    included = True
    parts = path.split("/")
    for negated, pattern in dockerignore_rules():
        if any(fnmatch.fnmatchcase("/".join(parts[:i]), pattern) for i in range(1, len(parts) + 1)):
            included = negated
    return included


def test_dockerignore_starts_by_excluding_everything():
    assert dockerignore_rules()[0] == (False, "*")


@pytest.mark.parametrize("path", [
    ".env", ".env.example", ".git/config", ".venv/bin/python", "data/testset/T0a995037.json", "data/split.json",
    "data/results/quick-final-run1/summary.json", "data/results/threshold.json", "data/eval/action_requests.jsonl",
    "data/labels_codex.csv", "call_data/call_transcripts/x.txt", "eval/run.py", "tests/conftest.py",
    "app/__pycache__/x.pyc", "data/scheduling.sqlite", "data/operations.sqlite",
])
def test_the_image_leaves_out(path):
    assert not in_context(path)


@pytest.mark.parametrize("path", [
    "app/web/main.py", "data/index/chunks.jsonl", "data/index/embeddings.npy", "data/document_list.csv",
    "data/kb_text/pricing__2026_fee_schedule.md", "call_data/knowledge_base/x.md", SEED, "docs/FINDINGS.md",
    "data/results/final/summary.json", "requirements.txt", "scripts/entrypoint.sh",
])
def test_the_image_includes(path):
    assert in_context(path)


def test_every_copied_source_is_in_the_build_context():
    for source in copy_sources():
        if "[" not in source:  # the optional results folder is a wildcard
            assert in_context(source.rstrip("/")), source


# --- the first-start entrypoint and /health ---------------------------------------------------------------------------

def entrypoint_copy(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "call_data" / "scheduling_db").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "entrypoint.sh", project / "scripts" / "entrypoint.sh")
    shutil.copy(ROOT / SEED, project / SEED)
    return project


def run_entrypoint(project: Path, volume: Path, *command: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_PATH": str(volume / "scheduling.sqlite"),
           "OPS_DATABASE_PATH": str(volume / "operations.sqlite")}
    return subprocess.run(["bash", str(project / "scripts" / "entrypoint.sh"), *command], env=env,
                          capture_output=True, text=True, timeout=30)


def test_entrypoint_copies_the_seed_to_an_empty_volume_then_runs_the_command(tmp_path):
    project, volume = entrypoint_copy(tmp_path), tmp_path / "data"
    result = run_entrypoint(project, volume, "echo", "started")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("started")
    assert (volume / "scheduling.sqlite").read_bytes() == (ROOT / SEED).read_bytes()


def test_entrypoint_never_overwrites_the_live_database(tmp_path):
    project, volume = entrypoint_copy(tmp_path), tmp_path / "data"
    volume.mkdir()
    (volume / "scheduling.sqlite").write_bytes(b"live bookings")
    assert run_entrypoint(project, volume, "true").returncode == 0
    assert (volume / "scheduling.sqlite").read_bytes() == b"live bookings"


def test_the_fly_health_check_passes_on_a_freshly_started_volume(tmp_path, fly):
    from app.ops.store import OpsStore
    from app.web.main import create_app

    project, volume = entrypoint_copy(tmp_path), tmp_path / "data"
    assert run_entrypoint(project, volume, "true").returncode == 0
    store = OpsStore(volume / "operations.sqlite")
    app = create_app(engine=None, store=store, cookie_secret="x" * 32, scheduling_db=volume / "scheduling.sqlite")
    path = fly["http_service"]["checks"][0]["path"]
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(path)
    assert response.status_code == 200 and response.json() == {"ok": True}


# --- scripts/deploy.sh ------------------------------------------------------------------------------------------------

FAKE_FLY = """#!/usr/bin/env bash
echo "$*" >> "$FLY_LOG"
if [[ "$1" == "status" ]]; then echo "$FAKE_STATUS"; fi
if [[ "$1" == "deploy" && -n "${FAIL_DEPLOY:-}" ]]; then exit 1; fi
exit 0
"""
FAKE_QUICK_RUN = """#!/usr/bin/env bash
echo quick >> "$QUICK_LOG"
exit "${QUICK_EXIT:-0}"
"""


def machines(n: int) -> str:
    return json.dumps({"Name": "meridian", "Hostname": "meridian.fly.dev",
                       "Machines": [{"id": f"m{i}", "state": "started"} for i in range(n)]})


@pytest.fixture
def deploy(tmp_path):
    project, bin_dir = tmp_path / "project", tmp_path / "bin"
    (project / "scripts").mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy(ROOT / "scripts" / "deploy.sh", project / "scripts" / "deploy.sh")
    for path, text in ((project / "scripts" / "fly", FAKE_FLY), (bin_dir / "fake-quick-run", FAKE_QUICK_RUN)):
        path.write_text(text)
        path.chmod(0o755)
    fly_log, quick_log = tmp_path / "fly.log", tmp_path / "quick.log"

    def run(*args, status=machines(1), **env):
        environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "QUICK_RUN": "fake-quick-run",
                       "FLY_LOG": str(fly_log), "QUICK_LOG": str(quick_log), "FAKE_STATUS": status,
                       "FLYCTL": "/nonexistent/flyctl", **env}
        result = subprocess.run(["bash", str(project / "scripts" / "deploy.sh"), *args], env=environment,
                                capture_output=True, text=True, timeout=60)
        calls = fly_log.read_text().splitlines() if fly_log.exists() else []
        quick = quick_log.read_text().splitlines() if quick_log.exists() else []
        return result, calls, quick

    return run


def test_deploy_runs_the_quick_run_then_deploy_scale_and_status(deploy):
    result, calls, quick = deploy()
    assert result.returncode == 0, result.stderr
    assert quick == ["quick"]
    assert [c.split()[0] for c in calls] == ["deploy", "scale", "status"]
    assert calls[1] == "scale count 1 --yes"
    assert calls[2] == "status --json"


def test_a_failed_quick_run_stops_before_any_fly_command(deploy):
    result, calls, quick = deploy(QUICK_EXIT="1")
    assert result.returncode != 0
    assert quick == ["quick"] and calls == []


def test_skip_quick_run_deploys_without_it(deploy):
    result, calls, quick = deploy("--skip-quick-run")
    assert result.returncode == 0, result.stderr
    assert quick == [] and [c.split()[0] for c in calls] == ["deploy", "scale", "status"]


@pytest.mark.parametrize("count", [0, 2])
def test_deploy_fails_unless_exactly_one_machine_runs(deploy, count):
    result, calls, _ = deploy(status=machines(count))
    assert result.returncode != 0
    assert "machine" in (result.stderr + result.stdout).lower()


def test_unreadable_status_fails(deploy):
    result, _, _ = deploy(status="not json")
    assert result.returncode != 0


def test_a_failed_deploy_does_not_scale(deploy):
    result, calls, _ = deploy("--skip-quick-run", FAIL_DEPLOY="1")
    assert result.returncode != 0
    assert [c.split()[0] for c in calls] == ["deploy"]


def test_unknown_options_are_refused(deploy):
    result, calls, quick = deploy("--yolo")
    assert result.returncode != 0 and calls == [] and quick == []


def test_deploy_runs_fly_only_through_scripts_fly():
    for line in (ROOT / "scripts" / "deploy.sh").read_text().splitlines():
        code = line.split("#", 1)[0]
        assert "flyctl" not in code
        assert not re.search(r"(^|[\s;&|(])fly\s", code), line


# --- scripts/measure_latency.py ---------------------------------------------------------------------------------------

class FakeSite:
    """The chat API: POST /api/message returns 202, GET /api/stream/{id} two sentences then done."""

    def __init__(self, clock):
        self.clock, self.posts, self.cookies_seen = clock, [], set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/message":
            body = json.loads(request.content)
            self.posts.append(body)
            self.clock.now += 0.1
            return httpx.Response(202, json={"message_id": body["message_id"]},
                                  headers={"set-cookie": f"visitor={len(self.posts)}; Path=/"})
        if request.method == "GET" and request.url.path.startswith("/api/stream/"):
            self.cookies_seen.add(request.headers.get("cookie"))
            self.clock.now += 1.0  # the first sentence arrives 1.1 s after the post
            text = ('event: sentence\ndata: {"text": "One."}\n\n'
                    'event: sentence\ndata: {"text": "Two."}\n\n'
                    'event: done\ndata: {"route": "knowledge", "outcome": "answered"}\n\n')
            return httpx.Response(200, content=text.encode(), headers={"content-type": "text/event-stream"})
        return httpx.Response(404)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_measure_sends_at_least_fifty_messages_after_warm_up_and_reports_medians():
    import measure_latency

    clock = Clock()
    site = FakeSite(clock)
    lines, clients = [], []

    def factory():
        clients.append(1)
        return httpx.Client(transport=httpx.MockTransport(site), base_url="https://meridian.example")

    def on_line(event, text):  # each streamed event advances the fake clock by the time it took to arrive
        clock.now += {"sentence": 0.0, "done": 1.5}.get(event, 0.0)

    report = measure_latency.measure(
        "https://meridian.example", messages=50, warmup=3, pace_s=0,
        client_factory=factory, clock=clock, sleep=lambda s: None, on_event=on_line, log=lines.append)
    assert len(site.posts) == 53
    assert report.count == 50
    assert report.median_first_sentence_s == pytest.approx(1.1)
    assert report.median_full_reply_s == pytest.approx(2.6)
    assert len({p["message_id"] for p in site.posts}) == 53
    assert len(clients) == 53  # a fresh visitor for each message, so one visitor's budget is not what is measured


def test_measure_refuses_fewer_than_fifty_messages():
    import measure_latency

    with pytest.raises(ValueError):
        measure_latency.measure("https://x", messages=49)


def test_limit_replies_are_counted_as_failures_not_timings():
    import measure_latency

    def limited(request):
        if request.method == "POST":
            return httpx.Response(202, json={})
        return httpx.Response(200, content=b'event: sentence\ndata: {"text": "slow down"}\n\n'
                                           b'event: done\ndata: {"route": "limit", "outcome": "limit"}\n\n')

    report = measure_latency.measure(
        "https://x", messages=50, warmup=0, pace_s=0, sleep=lambda s: None,
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(limited), base_url="https://x"))
    assert report.count == 0 and report.failures == 50
    assert report.median_first_sentence_s is None


def test_measure_latency_command_line_parses_the_base_url():
    import measure_latency

    args = measure_latency.parse_args(["https://meridian.fly.dev", "--messages", "60"])
    assert args.base_url == "https://meridian.fly.dev" and args.messages == 60 and args.warmup >= 1


def test_the_deployed_site_is_reviewer_only(fly):
    # Reviewer-only mode (D50): a $0 public budget refuses every public message before any model call.
    assert float(fly["env"]["PER_VISITOR_DAILY_USD"]) == 0.0


def test_on_a_reviewer_only_site_each_visitor_opens_the_reviewer_link_first():
    # D50: public messages are refused, so the measurement signs each fresh visitor in with the reviewer link.
    import measure_latency

    clock, reviewer_posts = Clock(), []
    site = FakeSite(clock)

    def handler(request):
        if request.method == "POST" and request.url.path == "/api/reviewer":
            reviewer_posts.append(json.loads(request.content)["token"])
            return httpx.Response(200, json={"reviewer": True})
        return site(request)

    def factory():
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://meridian.example")

    report = measure_latency.measure("https://meridian.example", messages=50, warmup=3, pace_s=0, client_factory=factory,
                                     clock=clock, sleep=lambda s: None, log=lambda line: None,
                                     reviewer_token="rv-token-0123456789abcdef")
    assert reviewer_posts == ["rv-token-0123456789abcdef"] * 53 and report.count == 50


def test_the_reviewer_token_comes_from_the_environment_not_the_command_line(monkeypatch):
    import measure_latency

    monkeypatch.setenv("REVIEWER_TOKEN", "rv-token-0123456789abcdef")
    assert measure_latency.reviewer_token(measure_latency.parse_args(["https://x.example", "--reviewer"])) == \
        "rv-token-0123456789abcdef"
    assert measure_latency.reviewer_token(measure_latency.parse_args(["https://x.example"])) is None
