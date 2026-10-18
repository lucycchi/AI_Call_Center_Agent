"""Label every transcript with Claude Haiku 5.5 against the frozen category list (R2).

Run: python -m pipeline.label_haiku   (writes data/labels_haiku.csv; about $0.10)
"""

import csv
import json
from pathlib import Path
from typing import Protocol

from pipeline.categories import category_text, check
from pipeline.transcripts import Call, load_transcripts

ROOT = Path(__file__).resolve().parent.parent

PROMPT = """You label customer calls to a home heating, cooling and plumbing company.
Choose the caller's MAIN reason for calling from this fixed list (reason: sub-reason):
{categories}

Transcript:
{transcript}

Answer with JSON only: {{"reason": "...", "sub_reason": "..."}}"""


class Labeler(Protocol):
    def label(self, prompt: str) -> dict: ...


def prompt_for(call: Call) -> str:
    lines = [f"Customer: {line}" for line in call.customer_lines]
    return PROMPT.format(categories=category_text(), transcript="\n".join(lines))


def label_with_haiku(calls: list[Call], client: Labeler) -> dict[str, tuple[str, str]]:
    labels = {}
    for call in calls:
        answer = client.label(prompt_for(call))
        labels[call.call_id] = check(answer.get("reason", ""), answer.get("sub_reason", ""), call.call_id)
    return labels


class AnthropicLabeler:
    """Real client: Haiku 5.5 with a JSON answer. Only used by main(), never in tests."""

    def __init__(self, model: str | None = None, timeout_s: int | None = None):
        import anthropic

        from app.config import SETTINGS

        self._client = anthropic.Anthropic(timeout=timeout_s or SETTINGS.anthropic_timeout_s)
        self._model = model or SETTINGS.router_model

    def label(self, prompt: str) -> dict:
        from pipeline.categories import CATEGORIES, REASONS

        schema = {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": REASONS},
                "sub_reason": {"type": "string", "enum": sorted({sub for _, sub in CATEGORIES})},
            },
            "required": ["reason", "sub_reason"],
            "additionalProperties": False,
        }
        response = self._client.messages.create(
            model=self._model, max_tokens=2000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}])
        if response.stop_reason == "refusal":
            raise ValueError(f"{self._model} declined to label: {response.stop_details}")
        return json.loads(next(block.text for block in response.content if block.type == "text"))


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    labels = label_with_haiku(calls, AnthropicLabeler())
    with (ROOT / "data" / "labels_haiku.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["call_id", "reason", "sub_reason"])
        for call_id, (reason, sub) in labels.items():
            writer.writerow([call_id, reason, sub])
    print(f"labeled {len(labels)} calls")


if __name__ == "__main__":
    main()
