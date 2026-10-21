# Milestone 6 gate

Reviews of this milestone compare against `tortoise/milestone-5`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
tests/knowledge/test_search.py ..............                            [ 53%]
tests/ops/test_jobs.py ....................                              [ 54%]
tests/ops/test_live_spend_fixes.py ......                                [ 55%]
tests/ops/test_spend.py ...............................                  [ 57%]
tests/ops/test_store.py ............                                     [ 58%]
tests/pipeline/test_documents.py ..........                              [ 58%]
tests/pipeline/test_findings.py .....................                    [ 60%]
tests/pipeline/test_labels.py ..............                             [ 61%]
tests/pipeline/test_templates.py .........                               [ 61%]
tests/replies/test_checks.py ........................................... [ 64%]
......................                                                   [ 66%]
tests/replies/test_money_published.py .................................. [ 68%]
........................................................................ [ 73%]
..........................................                               [ 76%]
tests/safety/test_safety.py ............................................ [ 79%]
......                                                                   [ 80%]
tests/scheduling/test_eligibility.py ................................... [ 82%]
...........                                                              [ 83%]
tests/scheduling/test_transactions.py .................                  [ 84%]
tests/test_config.py ..........                                          [ 85%]
tests/test_deploy_config.py ............................................ [ 88%]
.......................                                                  [ 89%]
tests/test_engine_interface.py ....                                      [ 90%]
tests/test_repository.py ...................................             [ 92%]
tests/web/test_chat.py ....................................              [ 95%]
tests/web/test_live_fixes.py ....................                        [ 96%]
tests/web/test_results.py ................                               [ 97%]
tests/web/test_staff.py .................................                [100%]

======================= 1433 passed in 71.25s (0:01:11) ========================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 6 is ticked (2 of 2).

## Architecture check

Covered by the milestone 5 architecture checks (Codex and a fresh Claude agent), which compared everything since `tortoise/milestone-4`: the final held-out run code (`eval/final.py`, the resume path in `eval/run.py`, `eval/per_driver.py`) and the documents written for this milestone. Since `tortoise/milestone-5` no code has changed (`git diff tortoise/milestone-5..HEAD` over app, eval, pipeline, scripts and tests is empty). The architecture document was brought up to date in that gate's fixes (commit 173723a), including the final-run tools and the `data/results/final/` files.

## Reviews

Covered by the milestone 5 code reviews (Codex and a fresh Claude agent, base `tortoise/milestone-4`), which included the final-run code, the resume path that grades saved conversations without re-running them, the per-driver table and the README's repository checks; their findings and fixes are in `docs/gates/milestone-5.md`. No code has changed since `tortoise/milestone-5`.

The milestone's own results, for the author:
- **Final held-out run (Task 27):** the frozen agent 5b8f6899 on 15 held-out scenarios (122 weighted calls): containment 29.5% (scope ceiling 74.6%, adjusted ceiling 48.4%; human baselines 84.5% and 73.3%), no wrong confident answers, knowledge, lookups and every handoff correct, routing 76.2%, bookings 69.8%; correct on all three consistency runs 66.7%. Grading crashed once and resumed from the saved conversations. Results by call reason are in the README.
- **README and repository contents (Task 28):** the README for a junior engineer with every required section, its numbers checked against the final summary by `tests/test_repository.py`, which also confirms the required files are tracked and scans for committed secrets (none). The video outline is the video agent's; the video is published by the author.
- **Live build:** differs from the measured agent by the live fixes after the measurement (D51), as the README and Results tab say.

## Author's choices

No findings to choose from: the milestone 5 reviews covered this milestone's code, and their fixes are made.
