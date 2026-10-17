"""Agreement between labelers (R4): author against Codex, Codex against Haiku."""

import json
from pathlib import Path


def agreement(a: dict[str, str], b: dict[str, str]) -> float | None:
    shared = [key for key in a if key in b]
    if not shared:
        return None
    return sum(a[key] == b[key] for key in shared) / len(shared)


def write_agreement(path: Path, codex: dict[str, str], haiku_by_template: dict[str, str],
                    author: dict[str, str] | None) -> dict:
    result = {
        "codex_vs_haiku": agreement(codex, haiku_by_template),
        "author_vs_codex": agreement(author, codex) if author else None,
        "author_labels": len(author) if author else 0,
        "status": "final" if author else "provisional",
    }
    path.write_text(json.dumps(result, indent=1))
    return result
