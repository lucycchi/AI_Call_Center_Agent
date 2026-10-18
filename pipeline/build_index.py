"""Build the search index from the converted documents (R27, R28): chunks plus embeddings, shipped in each release.

Run: python -m pipeline.build_index   (needs VOYAGE_API_KEY; a few cents)
"""

from pathlib import Path

from app.knowledge.index import chunk_document, save_index

ROOT = Path(__file__).resolve().parent.parent


def build(kb_text: Path, out: Path, embedder) -> int:
    chunks = [chunk for path in sorted(kb_text.glob("*.md")) for chunk in chunk_document(path)]
    save_index(out, chunks, embedder.embed([c.text for c in chunks]))
    return len(chunks)


def main() -> None:
    from dotenv import load_dotenv

    from app.knowledge.embedder import VoyageEmbedder

    load_dotenv(ROOT / ".env")
    count = build(ROOT / "data" / "kb_text", ROOT / "data" / "index", VoyageEmbedder(input_type="document"))
    print(f"indexed {count} chunks -> data/index/")


if __name__ == "__main__":
    main()
