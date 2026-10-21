"""Freeze the agent until the final held-out run (R21, D32): a hash of the agent-behaviour files, the search index
and the data files the agent reads while it runs (the document list, the converted documents it reads prices from,
and the internal documents its reply checks compare against). Web, operations and deployment code may still change.

Run: python -m eval.freeze   (writes data/agent_freeze.json)"""

import csv
import hashlib
import json
import re
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


def _hash(root: Path, without_threshold: bool) -> str:
    digest = hashlib.sha256()
    for path in agent_files(root):
        content = path.read_bytes()
        if without_threshold and path == root / "app" / "config.py":
            content = THRESHOLD_SETTING.sub(b"retrieval_threshold=<set from the curve>", content)
        digest.update(str(path.relative_to(root)).encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def freeze_agent(root: Path = ROOT) -> str:
    return _hash(root, without_threshold=False)


THRESHOLD_SETTING = re.compile(rb"retrieval_threshold\s*=\s*[^,\n)]*")


def answers_hash(root: Path = ROOT) -> str:
    """The freeze hash with app/config.py's `retrieval_threshold=...` setting left out. Retrieval answers are written
    with the threshold at 0 (eval/retrieval_eval.py agent_answerer) and the curve applies each threshold afterwards,
    so the setting cannot change them; filing runs under this hash keeps them pooled when the chosen threshold is
    written into the config (R32, D48). Any other change to the agent still files its answers apart."""
    return _hash(root, without_threshold=True)


def main() -> None:
    record = {"hash": freeze_agent(), "files": len(agent_files()), "covers": AGENT + internal_documents(),
              "frozen_at": datetime.now().isoformat(timespec="seconds"),
              "note": "The final held-out run checks the agent still matches this hash."}
    (ROOT / "data" / "agent_freeze.json").write_text(json.dumps(record, indent=1))
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
