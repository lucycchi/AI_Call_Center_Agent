"""Independent check labels: Codex (an OpenAI frontier model, the author's subscription)
labels one sample transcript per template, never shown another model's label (R3).

Run: python -m pipeline.label_codex   (tell the author first, so Codex is set to a frontier model)
"""

import csv
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from pipeline.categories import category_text, check
from pipeline.transcripts import Call, load_transcripts

ROOT = Path(__file__).resolve().parent.parent

PROMPT = """Do not read or change any files. Label this customer call to a home heating, cooling and
plumbing company. Choose the caller's MAIN reason from this fixed list (reason: sub-reason):
CATEGORIES
{categories}

Transcript:
{transcript}

Reply with one line of JSON only: {{"reason": "...", "sub_reason": "...", "model": "<your model name>"}}"""


class CodexLabelError(ValueError):
    pass


def prompt_for(call: Call) -> str:
    lines = [f"Customer: {line}" for line in call.customer_lines]
    lines += [f"Agent: {line}" for line in call.agent_lines]
    return PROMPT.format(categories=category_text(), transcript="\n".join(lines))


def label_with_codex(samples: dict[str, Call], runner: Callable[[str], str],
                     haiku_labels: dict, model: str | None = None) -> dict[str, tuple[str, str, str]]:
    """haiku_labels is accepted only to make the independence explicit: it is never used."""
    del haiku_labels
    labels = {}
    for template_id, call in samples.items():
        raw = runner(prompt_for(call))
        try:
            answer = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError) as error:
            raise CodexLabelError(f"{template_id}: Codex did not return JSON: {raw[:80]!r}") from error
        reason, sub = check(answer.get("reason", ""), answer.get("sub_reason", ""), template_id)
        labels[template_id] = (reason, sub, model or answer.get("model", "unknown"))
    return labels


def codex_model() -> str:
    """The model Codex is configured to use, read from its config rather than asked of the model."""
    import re

    config = Path.home() / ".codex" / "config.toml"
    match = re.search(r'^\s*model\s*=\s*"([^"]+)"', config.read_text(), re.M) if config.exists() else None
    return match.group(1) if match else "unknown"


def codex_runner(prompt: str) -> str:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "answer.txt"
        result = subprocess.run(["codex", "exec", "-s", "read-only", "--ephemeral", "-o", str(out), prompt],
                                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
        if out.exists() and out.read_text().strip():
            return out.read_text()
        errors = [line for line in (result.stdout + result.stderr).splitlines() if "ERROR" in line]
        raise CodexLabelError(f"Codex returned no answer: {errors[-1] if errors else 'no error message'}")


def samples_by_template(calls: list[Call], templates_csv: Path) -> dict[str, Call]:
    by_id = {c.call_id: c for c in calls}
    samples = {}
    for row in csv.DictReader(templates_csv.open()):
        samples.setdefault(row["template_id"], by_id[row["call_id"]])
    return samples


def main() -> None:
    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    samples = samples_by_template(calls, ROOT / "data" / "templates.csv")
    labels = label_with_codex(samples, codex_runner, haiku_labels={}, model=codex_model())
    with (ROOT / "data" / "labels_codex.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["template_id", "sample_call_id", "reason", "sub_reason", "model"])
        for template_id, (reason, sub, model) in labels.items():
            writer.writerow([template_id, samples[template_id].call_id, reason, sub, model])
    print(f"Codex labeled {len(labels)} templates")




def validate_codex_file(path: Path, expected: dict[str, str]) -> list[str]:
    """Problems with a Codex labels file written outside this script (for example from the IDE)."""
    from pipeline.categories import CATEGORIES

    problems, seen = [], set()
    for row in csv.DictReader(path.open()):
        template = row.get("template_id", "")
        seen.add(template)
        if template not in expected:
            problems.append(f"{template}: not a known template")
            continue
        if row.get("sample_call_id") != expected[template]:
            problems.append(f"{template}: sample call should be {expected[template]}, got {row.get('sample_call_id')}")
        if (row.get("reason"), row.get("sub_reason")) not in CATEGORIES:
            problems.append(f"{template}: ({row.get('reason')}, {row.get('sub_reason')}) is not in the category list")
        if not row.get("model"):
            problems.append(f"{template}: model name is empty")
    problems += [f"{template}: missing" for template in expected if template not in seen]
    return problems


def write_input_file(samples: dict[str, Call], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["template_id", "sample_call_id", "transcript_file"])
        for template_id, call in samples.items():
            writer.writerow([template_id, call.call_id, f"call_data/call_transcripts/{call.call_id}.txt"])


def check_main() -> None:
    import sys

    rows = list(csv.DictReader((ROOT / "data" / "codex_label_input.csv").open()))
    problems = validate_codex_file(ROOT / "data" / "labels_codex.csv", {r["template_id"]: r["sample_call_id"] for r in rows})
    print("\n".join(problems) if problems else f"labels_codex.csv is valid: {len(rows)} templates")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        check_main()
    elif "--write-input" in sys.argv:
        _calls = load_transcripts(ROOT / "call_data" / "call_transcripts", ROOT / "call_data" / "call_transcripts_index.csv")
        write_input_file(samples_by_template(_calls, ROOT / "data" / "templates.csv"), ROOT / "data" / "codex_label_input.csv")
        print("wrote data/codex_label_input.csv")
    else:
        main()
