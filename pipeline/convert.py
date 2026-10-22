"""Turn the knowledge base into searchable text (R26): the fee-schedule PDF keeps each row and
column pair, the price book becomes one line per item, the holiday image was transcribed by hand.

Run: python -m pipeline.convert   (writes data/kb_text/)
"""

import csv
import shutil
from pathlib import Path

from pypdf import PdfReader

from pipeline.documents import ROOT, relative, searchable_documents

COLUMNS = ("Non-member", "Comfort Club", "Comfort Club Plus")
OUT = ROOT / "data" / "kb_text"
HOLIDAY = ROOT / "data" / "holiday_hours_2026.txt"


def convert_pdf_table(path: Path) -> str:
    lines = [line.strip() for line in PdfReader(path).pages[0].extract_text().splitlines() if line.strip()]
    start = lines.index(COLUMNS[-1]) + 1
    end = next(i for i, line in enumerate(lines) if line.startswith("Notes:"))
    title = " ".join(lines[:2])
    out = [f"# {title}", "", lines[2], "", "## Fees by membership level", ""]
    cells = lines[start:end]
    for i in range(0, len(cells) - len(cells) % 4, 4):
        fee, *values = cells[i:i + 4]
        out += [f"- {fee}, {column}: {value}" for column, value in zip(COLUMNS, values)]
    out += ["", "## Notes", "", " ".join(lines[end:]).removeprefix("Notes: ")]
    return "\n".join(out) + "\n"


def convert_price_book(path: Path) -> str:
    out = ["# 2026 Repair Price Book", ""]
    categories: dict[str, list[str]] = {}
    for row in csv.DictReader(path.open()):
        low, high = row["low_price"], row["high_price"]
        price = f"${low}" if low == high else f"${low} to ${high}"
        note = f" ({row['notes']})" if row["notes"] else ""
        categories.setdefault(row["category"], []).append(f"- {row['description']}: {price}{note}")
    for category, items in categories.items():
        out += [f"## {category}", "", *items, ""]
    return "\n".join(out)


def main(out: Path = OUT) -> None:
    """Rebuild the folder from scratch, so a document later marked stale or internal is never left behind."""
    if out.exists():
        for old in out.iterdir():
            old.unlink()
    out.mkdir(parents=True, exist_ok=True)
    for path in searchable_documents():
        target = out / (relative(path).replace("/", "__").rsplit(".", 1)[0] + ".md")
        if path.suffix == ".pdf":
            target.write_text(convert_pdf_table(path))
        elif path.suffix == ".csv":
            target.write_text(convert_price_book(path))
        elif path.suffix == ".png":
            shutil.copy(HOLIDAY, target)
        else:
            shutil.copy(path, target)
    print(f"wrote {len(list(out.iterdir()))} files to {out}")


if __name__ == "__main__":
    main()
