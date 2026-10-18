"""Agreement between labelers (R4): Claude Fable 5.1 against Codex on the blind third, Codex against Haiku."""

import json
from pathlib import Path


def agreement(a: dict[str, str], b: dict[str, str]) -> float | None:
    shared = [key for key in a if key in b]
    if not shared:
        return None
    return sum(a[key] == b[key] for key in shared) / len(shared)


def write_agreement(path: Path, codex: dict[str, str], haiku_by_template: dict[str, str],
                    fable: dict[str, str] | None) -> dict:
    """Fable labels the blind third in place of a human (D38); no human labeled the templates."""
    result = {
        "codex_vs_haiku": agreement(codex, haiku_by_template),
        "fable_vs_codex": agreement(fable, codex) if fable else None,
        "fable_labels": len(fable) if fable else 0,
        "human_labels": 0,
        "status": "final" if fable else "provisional",
    }
    path.write_text(json.dumps(result, indent=1))
    return result


def majority_by_template(templates: dict[str, str], per_call: dict[str, str]) -> dict[str, str]:
    from collections import Counter

    votes: dict[str, Counter] = {}
    for call_id, template in templates.items():
        if call_id in per_call:
            votes.setdefault(template, Counter())[per_call[call_id]] += 1
    return {template: counter.most_common(1)[0][0] for template, counter in votes.items()}


def main() -> None:
    import csv

    root = Path(__file__).resolve().parent.parent / "data"
    read = lambda name: list(csv.DictReader((root / name).open()))
    templates = {r["call_id"]: r["template_id"] for r in read("templates.csv")}
    haiku = majority_by_template(templates, {r["call_id"]: r["reason"] for r in read("labels_haiku.csv")})
    codex = {r["template_id"]: r["reason"] for r in read("labels_codex.csv")}
    fable = {r["template_id"]: r["reason"] for r in read("labels_fable.csv")}
    result = write_agreement(root / "label_agreement.json", codex, haiku, fable)
    sub = lambda name, key: {r[key]: (r["reason"], r["sub_reason"]) for r in read(name)}
    codex_sub, fable_sub = sub("labels_codex.csv", "template_id"), sub("labels_fable.csv", "template_id")
    result["fable_vs_codex_sub_reason"] = agreement(fable_sub, codex_sub)
    result["disagreements"] = {
        "codex_vs_haiku": {t: [codex[t], haiku.get(t)] for t in codex if codex[t] != haiku.get(t)},
        "fable_vs_codex": {t: [fable[t], codex[t]] for t in fable if fable[t] != codex.get(t)},
    }
    (root / "label_agreement.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
