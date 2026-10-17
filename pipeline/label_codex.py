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
                     haiku_labels: dict) -> dict[str, tuple[str, str, str]]:
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
        labels[template_id] = (reason, sub, answer.get("model", "unknown"))
    return labels


def codex_runner(prompt: str) -> str:
    result = subprocess.run(["codex", "exec", "-s", "read-only", "--ephemeral", prompt],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


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
    labels = label_with_codex(samples, codex_runner, haiku_labels={})
    with (ROOT / "data" / "labels_codex.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["template_id", "sample_call_id", "reason", "sub_reason", "model"])
        for template_id, (reason, sub, model) in labels.items():
            writer.writerow([template_id, samples[template_id].call_id, reason, sub, model])
    print(f"Codex labeled {len(labels)} templates")


if __name__ == "__main__":
    main()
