"""Claude Fable 5.1 labels the blind third of the templates, in place of the author (D38),
without seeing Haiku's or Codex's labels.

Run: python -m pipeline.label_fable   (writes data/labels_fable.csv; about $0.30)
"""

import csv
from pathlib import Path

from pipeline.categories import check
from pipeline.label_haiku import Labeler, prompt_for
from pipeline.transcripts import Call

ROOT = Path(__file__).resolve().parent.parent
FABLE_MODEL = "claude-fable-5-1"


def label_blind_third(samples: dict[str, Call], template_ids: list[str], client: Labeler) -> dict[str, tuple[str, str]]:
    labels = {}
    for template_id in template_ids:
        answer = client.label(prompt_for(samples[template_id]))
        labels[template_id] = check(answer.get("reason", ""), answer.get("sub_reason", ""), template_id)
    return labels


def main() -> None:
    from dotenv import load_dotenv

    from pipeline.label_codex import samples_by_template
    from pipeline.label_haiku import AnthropicLabeler
    from pipeline.transcripts import load_transcripts

    load_dotenv(ROOT / ".env")
    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    samples = samples_by_template(calls, ROOT / "data" / "templates.csv")
    blind = [row["template_id"] for row in csv.DictReader((ROOT / "data" / "author_label_sheet.csv").open())]
    labels = label_blind_third(samples, blind, AnthropicLabeler(model=FABLE_MODEL, timeout_s=120))
    with (ROOT / "data" / "labels_fable.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["template_id", "sample_call_id", "reason", "sub_reason", "model"])
        for template_id, (reason, sub) in labels.items():
            writer.writerow([template_id, samples[template_id].call_id, reason, sub, FABLE_MODEL])
    print(f"Fable labeled {len(labels)} templates")


if __name__ == "__main__":
    main()
