"""The author's blind labeling sheet: about a third of the templates, with no AI labels (R4).

Run: python -m pipeline.sheet   (writes data/author_label_sheet.csv)
"""

import csv
import random
from pathlib import Path

from pipeline.transcripts import Call

ROOT = Path(__file__).resolve().parent.parent


def write_author_sheet(samples: dict[str, Call], path: Path, seed: int = 17) -> None:
    chosen = sorted(random.Random(seed).sample(sorted(samples), round(len(samples) / 3)))
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["template_id", "sample_call_id", "caller_request", "your_reason", "your_sub_reason"])
        for template_id in chosen:
            call = samples[template_id]
            writer.writerow([template_id, call.call_id, " / ".join(call.customer_lines[:3]), "", ""])


def main() -> None:
    from pipeline.label_codex import samples_by_template
    from pipeline.transcripts import load_transcripts

    data = ROOT / "call_data"
    calls = load_transcripts(data / "call_transcripts", data / "call_transcripts_index.csv")
    samples = samples_by_template(calls, ROOT / "data" / "templates.csv")
    out = ROOT / "data" / "author_label_sheet.csv"
    write_author_sheet(samples, out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
