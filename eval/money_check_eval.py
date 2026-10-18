"""Measure the reply sentence check, the code rules plus the money check (D43), on the labelled sentences in
data/eval/money_sentences.jsonl.

Run: python -m eval.money_check_eval   (needs EVAL_ANTHROPIC_API_KEY; about 110 short Haiku calls)
Writes data/results/money_check/summary.json with accuracy, missed promises and over-blocks."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def evaluate(rows: list[dict], check) -> dict:
    missed = [r["sentence"] for r in rows if r["expected"] == "block" and check(r["sentence"], r["previous"])]
    over = [r["sentence"] for r in rows if r["expected"] == "pass" and not check(r["sentence"], r["previous"])]
    blocks = sum(r["expected"] == "block" for r in rows)
    return {"sentences": len(rows), "promises": blocks, "published_or_ordinary": len(rows) - blocks,
            "promises_caught": blocks - len(missed), "passes_released": len(rows) - blocks - len(over),
            "missed_promises": missed, "over_blocked": over}


def main() -> None:
    import anthropic
    from dotenv import load_dotenv

    from app.config import SETTINGS
    from app.core.model_log import RecordingClient
    from app.replies.money_check import MoneyCheck

    load_dotenv(ROOT / ".env")
    client = RecordingClient(anthropic.Anthropic(api_key=os.environ["EVAL_ANTHROPIC_API_KEY"], max_retries=1,
                                                 timeout=SETTINGS.anthropic_timeout_s), sdk_version=anthropic.__version__)
    rows = [json.loads(line) for line in (ROOT / "data" / "eval" / "money_sentences.jsonl").open()]
    money = MoneyCheck(client)

    def full_check(sentence: str, previous: str) -> bool:
        """The sentence check as the pipeline runs it: the code rules, then the model on sentences about money."""
        from app.replies.checks import check_sentence
        from app.replies.money_check import touches_money
        return check_sentence(sentence, previous).ok and (not touches_money(sentence) or money(sentence, previous))
    report = evaluate(rows, full_check)
    report["model"], report["anthropic_sdk"] = SETTINGS.router_model, anthropic.__version__
    out = ROOT / "data" / "results" / "money_check"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
