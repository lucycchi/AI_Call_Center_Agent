# Milestone 1 gate

Reviews of this milestone compare against `tortoise/plan`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Call_Center_Agent
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, langsmith-0.14.11
collected 65 items

tests/pipeline/test_documents.py .......                                 [ 10%]
tests/pipeline/test_findings.py .....................                    [ 43%]
tests/pipeline/test_labels.py ..............                             [ 64%]
tests/pipeline/test_templates.py .........                               [ 78%]
tests/test_config.py ..........                                          [ 93%]
tests/test_engine_interface.py ....                                      [100%]

============================== 65 passed in 1.06s ==============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 1 is ticked (5 of 5).

## Architecture check

Run by Codex (gpt-5.6-sol, per-run override because the configured gpt-6.1-sol is not available on a ChatGPT-account Codex command line) and by a fresh Claude agent, both using `prompts/architecture-check.md`.

**Both found:**
- The evaluation-files table names a single `data/labels.csv` with the author's labels; the code writes `labels_haiku.csv`, `labels_codex.csv`, `labels_fable.csv` and `label_agreement.json`, and Claude Fable 5.1 labels the blind third (D38). The table also puts the merge list inside `templates.csv`, which is a separate file.
- The data-flow diagram omits that transcripts go to Anthropic offline for Haiku and Fable labeling, and says Codex receives "template text" rather than one full sample transcript per template.
- The engine's handling of a missing or repeated completion event differs from the document's promise (one terminal done event; an unfinished message becomes a handoff).

**Only the Claude agent found:**
- The slot service types in the database diagram should use the stored values (`hvac_repair`, `hvac_tune_up`, `plumbing`, `estimate`), and date fields should say they are written YYYY-MM-DD.
- `.env` and `.env.example` set `DAILY_SPEND_CAP_USD=5`, which `app/config.py` reads as the $10 site cap; and `DATABASE_PATH` points the live database at the read-only seed copy.
- Model IDs can be overridden from the environment, contradicting "pinned" (technology stack (D35)).
- The pipeline imports `app.scheduling.zones` and `app.config`, not shown in the code-structure diagram; the folder table omits the labeling, agreement, staff-check, capacity and conversion modules and `data/kb_text/`.

**Only Codex found:**
- The summary's "where the project stands" paragraph is stale (83 requirements, no code).
- The pinned settings lack the message-rate limits, evaluation token limits and retry count from the plan's global constraints.
- 52 templates against the plan's 70 to 120 estimate.
- The holiday transcription is written to `data/kb_text/policies__holiday_hours_2026.md`, not the plan's `data/kb_text/holiday_hours_2026.txt`.

## Reviews

Code reviews of `git diff tortoise/plan` by Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent, both using `prompts/code-review.md`. Both ran the tests: 48 passed (Codex could run 38; 10 need a writable temporary folder its sandbox lacks).

| Finding | Codex | Claude |
|---|---|---|
| `.env.example` and `.env` point the live scheduling database at the seed file | yes (top) | yes (top) |
| `DAILY_SPEND_CAP_USD=5` turns the $10 site cap into $5 | yes | yes |
| `CLASSIFIER_MODEL` in `.env.example` is ignored (code reads `ROUTER_MODEL`); `TODAY` unused | yes | yes |
| The engine yields sentences after the first done event, and sends no done event if the pipeline raises | yes | yes |
| Findings print reason-level Fable agreement as "including sub-reasons" | yes | yes |
| Findings print "perfect agreement" prose regardless of the numbers | | yes |
| The provisional path crashes when Fable labels are missing | | yes |
| Agreement marked "final" even if Fable labels are incomplete | yes | |
| Template grouping uses broad outcome buckets rather than staff response patterns, and does not remove names; 52 templates | yes (wrong) | checked by eye: groups correct; plan estimate off |
| Single-template reasons (hiring, commercial, wrong number) cannot appear in both sets | | yes |
| Findings ranking table lists all 11 reasons, not the top four or five | yes | |
| Agent-scope section gives a generic "why" for handoffs (wrong for the 16 burning-smell safety handoffs) and no whole-scope list | | yes |
| Human baseline counts waitlist calls and dropped bookings as resolved without saying so | | yes (unclear) |
| Transcript header line "Agent: <name>" is parsed as a staff line | | yes |
| Capacity "bookable" counts already-started slots and ignores technician overlap | | yes (unclear) |
| Member diagnostic-fee count uses today's tier | | yes (unclear) |
| Holiday transcription file path differs from the plan | yes | |
| Conversion never removes outputs for documents later excluded | yes (addition) | |
| Three-file labels against `data/labels.csv` in the architecture and plan | yes (unclear) | |
| Tests too weak to catch the above (config, engine, findings, agreement, templates) | yes (addition) | yes |
| Seed guard: refuse to start if the live path equals the seed | | yes (addition) |

## Author's choices

Recorded 2026-10-18. The author accepted every recommended fix:

- **Code, test-first:** point `DATABASE_PATH` at `data/scheduling.sqlite` and refuse to start if the live path is the seed file; rename the site cap setting to `SITE_DAILY_USD` and fix `.env.example` and `.env`; pin the model IDs (no environment override) and add the missing rate, test-token and retry settings; make the engine stop at the first done event and end with an error done event on a crash; fix the findings document (provisional path, sub-reason agreement from its own figure, conditional agreement wording, top-five table plus a table of the rest, a reason for each handed-off sub-reason, baseline note with the figure excluding dropped bookings, "members today" wording); mark agreement final only when every blind-third template has a Fable label; skip the transcript header line; clear converted documents before each conversion.
- **Documents:** update the architecture (label and template files, stored service-type values and date formats, offline transcripts to Anthropic, pipeline use of the app's zone map, folder table, status paragraph) and the plan (three label files, holiday file path, template estimate, family split).
- **Template grouping:** a dedicated transcript check was run twice (Claude Fable 5.1, and Codex at the author's request; reports in `docs/reviews/`). Both found no template needs splitting and names never affect grouping. They differed on the nine waitlist templates. The author chose to keep the 52 templates and link each waitlist template to its booking twin as a family that stays on one side of the test split (template families (D39), proposed).
