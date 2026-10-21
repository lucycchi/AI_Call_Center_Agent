"""Export flagged conversations as candidate test cases (R75), the first step of the feedback loop: flag, review,
fix the document or rule, re-run the test set, deploy.

Each conversation with at least one flagged reply becomes one JSON file in data/candidates/ (never data/testset/,
and data/split.json is never touched), shaped like the frozen test cases (eval/build_cases.py) so the author can
turn a reviewed candidate into a real case: the caller's messages become the caller script, and each flag keeps
the reply that was flagged and the staff correction note. The fields only the author can decide (caller card,
expected outcome, reference answer and evidence) are left empty. All text is already masked by the operations store.

Run: python -m pipeline.export_flags [--ops PATH] [--out DIR]"""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "candidates"
FORBIDDEN = (ROOT / "data" / "testset",)


def _case_id(conversation_id: str) -> str:
    return "FLAG-" + hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:10]


def candidate(store, conversation_id: str, flags: list[dict]) -> dict:
    messages = store.conversation_messages(conversation_id)
    replies = {m["message_id"]: m for m in messages if m["role"] == "agent"}
    return {
        "case_id": _case_id(conversation_id),
        "candidate": True,
        "status": "candidate from a staff flag: review before adding to the test set",
        "source_conversation_id": conversation_id,
        "template_id": None,
        "caller_script": [m["text_masked"] for m in messages if m["role"] == "caller" and m["text_masked"]],
        "transcript": [{"role": m["role"], "text": m["text_masked"]} for m in messages if m["text_masked"]],
        "flags": [{"message_id": f["message_id"], "reply": replies.get(f["message_id"], {}).get("text_masked", ""),
                   "correction": f["correction"] or "", "flagged_at": f["created_at"]} for f in flags],
        "caller_card": None,
        "appointment": None,
        "fixtures": [],
        "requests": [],
        "expected_outcome": None,
        "expected_handoff_reason": None,
        "needs_documents": None,
        "reference_answer": None,
        "evidence_spans": [],
        "must_not": [],
    }


def export_flags(store, out_dir: Path = DEFAULT_OUT) -> list[Path]:
    """Write one candidate per flagged conversation; returns the files written, in conversation order."""
    out_dir = Path(out_dir).resolve()
    if any(out_dir == f.resolve() or f.resolve() in out_dir.parents for f in FORBIDDEN):
        raise ValueError("candidates never go into the frozen test set")
    by_conversation: dict[str, list[dict]] = {}
    for flag in store.flags():
        by_conversation.setdefault(flag["conversation_id"], []).append(flag)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for conversation_id, flags in by_conversation.items():
        case = candidate(store, conversation_id, flags)
        path = out_dir / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2) + "\n")
        written.append(path)
    return written


def main() -> None:
    from app.config import SETTINGS
    from app.ops.store import OpsStore

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ops", type=Path, default=SETTINGS.ops_db_path, help="the operations database")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where candidates are written")
    args = parser.parse_args()
    if not args.ops.exists():
        raise SystemExit(f"no operations database at {args.ops}")
    written = export_flags(OpsStore(args.ops), args.out)
    print(f"wrote {len(written)} candidate test case(s) to {args.out}")


if __name__ == "__main__":
    main()
