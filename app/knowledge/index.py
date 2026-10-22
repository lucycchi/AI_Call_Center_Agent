"""Split the converted documents into one chunk per section, and load or save the built index.

Each chunk keeps its source document, heading, effective date and line span, so answers can cite
their source and retrieval can be scored against exact evidence spans (R27, R29)."""

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_LIST = ROOT / "data" / "document_list.csv"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document: str
    heading: str
    effective_date: str
    text: str
    start_line: int
    end_line: int


def _source_of(kb_file: Path) -> tuple[str, str]:
    """The original document path and its effective date, from the document list."""
    stem = kb_file.stem.replace("__", "/")
    rows = list(csv.DictReader(DOCUMENT_LIST.open()))
    added = DOCUMENT_LIST.with_name("documents_added.csv")  # author-supplied documents, named "added/..." (D54)
    if added.exists():
        rows += [{**r, "path": "added/" + r["path"]} for r in csv.DictReader(added.open())]
    for row in rows:
        if row["path"].rsplit(".", 1)[0] == stem:
            return row["path"], row["effective_date"]
    return stem, ""


def chunk_document(kb_file: Path) -> list[Chunk]:
    document, effective = _source_of(kb_file)
    lines = kb_file.read_text().splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), document)
    sections, current, start = [], None, 1
    for number, line in enumerate(lines, 1):
        if line.startswith("## "):
            if current is not None or any(l.strip() for l in lines[start - 1:number - 1] if not l.startswith("# ")):
                sections.append((current or title, start, number - 1))
            current, start = line[3:].strip(), number
    sections.append((current or title, start, len(lines)))
    chunks = []
    for heading, first, last in sections:
        body = "\n".join(lines[first - 1:last]).strip()
        content = [l for l in body.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("_")]
        if not content:
            continue
        text = f"{title}\n{body}" if heading != title else body
        chunks.append(Chunk(f"{kb_file.stem}#{len(chunks)}", document, heading, effective, text, first, last))
    return chunks


def save_index(folder: Path, chunks: list[Chunk], embeddings: np.ndarray) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "chunks.jsonl").open("w") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk)) + "\n")
    np.save(folder / "embeddings.npy", embeddings)


def load_index(folder: Path) -> tuple[list[Chunk], np.ndarray]:
    chunks = [Chunk(**json.loads(line)) for line in (folder / "chunks.jsonl").open()]
    return chunks, np.load(folder / "embeddings.npy")
