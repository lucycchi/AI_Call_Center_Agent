"""Freeze the agent until the final held-out run (R21, D32): a hash of the agent-behaviour files, the search index
and the data files the agent reads while it runs (the document list, the converted documents it reads prices from,
and the internal documents its reply checks compare against). Web, operations and deployment code may still change.

Run: python -m eval.freeze   (writes data/agent_freeze.json)"""

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ["app/core", "app/routing", "app/knowledge", "app/accounts", "app/scheduling", "app/safety", "app/replies",
         "app/handoff", "app/flows", "app/config.py", "data/index", "data/document_list.csv", "data/kb_text"]


def internal_documents(root: Path = ROOT) -> list[str]:
    """The internal documents the document list names; the reply checks read them (app/replies/checks.py)."""
    listing = root / "data" / "document_list.csv"
    if not listing.exists():
        return []
    return [f"call_data/knowledge_base/{row['path']}" for row in csv.DictReader(listing.open()) if row["audience"] == "internal"]


def agent_files(root: Path = ROOT) -> list[Path]:
    files = []
    for part in AGENT + internal_documents(root):
        path = root / part
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files += [p for p in sorted(path.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    return sorted(files)


def freeze_agent(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in agent_files(root):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def main() -> None:
    record = {"hash": freeze_agent(), "files": len(agent_files()), "covers": AGENT + internal_documents(),
              "frozen_at": datetime.now().isoformat(timespec="seconds"),
              "note": "The final held-out run checks the agent still matches this hash."}
    (ROOT / "data" / "agent_freeze.json").write_text(json.dumps(record, indent=1))
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
