# Milestone 4 gate

Reviews of this milestone compare against `tortoise/milestone-3`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```

tests/accounts/test_accounts.py ........................................ [  7%]
.........                                                                [  9%]
tests/core/test_engine.py ...................                            [ 13%]
tests/eval/test_cases.py ...........................................     [ 21%]
tests/eval/test_grader.py ...............                                [ 24%]
tests/eval/test_retrieval_metrics.py ..................                  [ 27%]
tests/eval/test_scoring.py .............                                 [ 30%]
tests/eval/test_threshold.py ........                                    [ 31%]
tests/flows/test_conversations.py ...................................... [ 39%]
........................................................................ [ 53%]
..                                                                       [ 53%]
tests/flows/test_knowledge.py ....                                       [ 54%]
tests/handoff/test_handoff.py ..........                                 [ 56%]
tests/knowledge/test_search.py ..............                            [ 58%]
tests/ops/test_store.py ...........                                      [ 61%]
tests/pipeline/test_documents.py .........                               [ 62%]
tests/pipeline/test_findings.py .....................                    [ 66%]
tests/pipeline/test_labels.py ..............                             [ 69%]
tests/pipeline/test_templates.py .........                               [ 71%]
tests/replies/test_checks.py ...............................             [ 77%]
tests/safety/test_safety.py ............................................ [ 85%]
......                                                                   [ 87%]
tests/scheduling/test_eligibility.py ................................... [ 93%]
...                                                                      [ 94%]
tests/scheduling/test_transactions.py ...............                    [ 97%]
tests/test_config.py ..........                                          [ 99%]
tests/test_engine_interface.py ....                                      [100%]

============================= 517 passed in 21.80s =============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 4 is ticked (3 of 3).

## Architecture check

Run by Codex (gpt-5.6-sol, per-run override) and by a fresh Claude agent, both using `prompts/architecture-check.md`. Claude ran all 517 tests (passed) and recomputed the agent freeze hash (matches).

**Both found:**
- The writer gets all the time left, not half; the document says every model attempt gets half.
- The reply checks also block promises that a team member will follow up; not documented.
- Codex grades whole conversations (requests, lookups, tickets), not only knowledge answers; a case passes only when Codex and the database checks both pass.
- The grader-check row still describes the author grading; Claude Fable 5.1 stands in (D44), and Codex's verdicts are kept apart in `grader_check_sample.json`.
- Attempt lines hold no model ids or settings, though the document and plan (Task 19) say they do.
- The quick run's two-of-three rule is not documented.

**Only the Claude agent found:**
- The fee-schedule answer gets a policy answer, not a price answer; the fee question flow's steps 5 and 6 should say a price answer comes only from the service catalog or repair price book.
- The slot finder also drops slots overlapping the caller's own visits (not documented), and that rule wrongly blocks moving a visit to an overlapping window on the same day, because the visit being moved still counts.
- `grader_check.py`'s default command reads the empty author column; rerunning it would overwrite Fable's results in `grader_check.json`.
- The model-call purpose list lacks "check"; the agent freeze also covers `app/flows`.
- Pipeline steps not documented: filler lines, "that's all" ending the chat, identification on any route, "anything else?" for short calm unclear messages, a later handoff joining the open ticket, "sign me up" after a plan discussion, the coverage answer added to a warranty claim, a same-day same-service booking becoming a move, and the handoff asking an unidentified caller for details.
- Evaluation pieces not documented: a fresh operations database per case, the threshold rule (0.25 floor, a wrong answer costs 2.5), the adversarial runner and the output files (verdicts, answer scores, threshold, adversarial summary, agent freeze, the ungraded first run).

**Only Codex found:**
- The status paragraph still says Milestone 4 is planned.
- Conversation runs write no per-run `verdicts.jsonl` (Task 19); only attempts and a summary.
- Recording spend does not itself enforce the $8 stop (Task 18); the cap is checked between conversations.
- Runs are buffered before writing, so an exception can lose finished conversations (R12).

## Reviews

Code reviews of `git diff tortoise/milestone-3` by Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent, both using `prompts/code-review.md`. Claude ran all 517 tests (passed) and reproduced findings with offline probes; Codex ran nine targeted tests (the rest need a writable temporary folder). Neither made paid calls. Held-out leakage was checked: no committed result contains a held-out case.

| Finding | Codex | Claude |
|---|---|---|
| Booking checks only look for some new appointment or a changed slot: no check of service, date, window, members-only, the slot marked booked, the read-back, duplicates or a freed slot on cancel; new appointments with ids from 5000 up are ignored (latent with planted appointments) | yes (top) | yes (top) |
| The quick run passes with a failed safety or booking case (two of three), passes with no attempts, ignores budget-stopped runs, and exits 0 on failure | yes (top) | yes |
| Wrong confident answers reported only as a weighted share, not a count with each one listed | yes (top) | yes |
| A crash mid-run loses every conversation and spend (only the budget stop is caught); a failure during retries loses the first run's Codex verdicts | (architecture) | yes (top) |
| Model ids and settings are not saved with runs (only in gitignored operations databases) | yes | yes |
| Re-running the grader-check sheet overwrites the Claude and Fable columns; the table reads the empty author column | yes (top) | (architecture) |
| Shortcuts drop real requests: "My AC cut out" and "Hold on, reschedule it" get "take your time"; "That's it, I want a manager" and "Nothing else has worked, book a repair" close the chat with no ticket | yes | yes (top) |
| A short unclear request for a person ("Just let me talk to a real person") gets "anything else?", not a handoff | yes | yes |
| Adversarial money-promise and internal-text checks rerun the agent's own checks, so cases a01, a27 and a29 cannot fail |  | yes (top) |
| Adversarial cases don't enforce their scenarios: non-English and nonsense cases need no handoff, the waitlist case no slots or ticket, the next-day move no database check | yes | yes |
| Published results are stale: the adversarial pass rate predates the latest agent changes; the grader check, retrieval verdicts and threshold curve used an older rubric and writer prompt |  | yes (top) |
| Paid adversarial runs and the API grader fallback have no run budget; the call that crosses the cap is allowed | yes (top) |  |
| The freeze hash misses files the agent reads at run time: the document list, the fee and holiday price text, the internal documents |  | yes |
| Containment counts redirects but neither ceiling does, so a perfect agent scores 0.668 against an adjusted ceiling of 0.631 |  | yes |
| Operations databases at fixed paths (such as quick-run1) are reopened, not cleared, and grading reads all their receipts and tickets, so an earlier run's records can pass a later one | yes |  |
| Retrieval faithfulness is graded against passages searched again, not the ones the answer was written from | yes |  |
| "8 to 12pm" and "8:00 to 12:00 PM" are not understood as a window (confirmed) | yes |  |
| A second handoff reason while a ticket is open only adds a note: no new reason tag, invoice notes or action-gap tag |  | yes (unclear) |
| "I'll take the first", "let's do the second" no longer pick a slot (regression) |  | yes |
| "Yes, the earlier the better" at a read-back offers earlier slots instead of booking |  | yes |
| A same-day move to an overlapping window is never offered and is refused as taken |  | yes |
| The 60-second conversation cap is checked only between calls, not enforced during one | yes |  |
| Missing handoff grades count as correct; safety cases' handoff reason is always correct |  | yes (unclear) |
| What the scope ceiling covers: action-gap calls fall outside it already, so the two ceilings differ only by clean declines |  | yes (unclear) |
| Nothing stops an accidental held-out run before the final run; about 10 lines would refuse it without a final flag and matching hashes |  | yes (addition) |
| The router's "set up autopay" example matches only a held-out case: checked, it comes from the spec's money actions (R48) and the plan, and has been in the router since Milestone 3; not a leak |  | yes (unclear, resolved) |
| Tests too weak to catch the above (filler and goodbye words inside requests, wrong bookings, crash mid-run, circular adversarial checks, positive ordinals, the two-of-three rule) | yes | yes |

## Author's choices

The author chose "All recommended" (2026-10-20):
- Fix every agent bug in the reviews test-first: the filler, goodbye and "anything else?" shortcuts, a second handoff reason adding its tag and notes to the open ticket, ordinal slot picks, "earlier" with a yes, same-day overlapping moves, and "8 to 12pm" windows.
- Fix every measurement problem: booking checks against the read-back and the freed slot, a strict quick run, wrong confident answers as a listed count, operations databases cleared per run, missing grades failing, adversarial checks independent of the agent's own and enforcing each case's outcome, and containment counted the same way as its ceilings.
- Fix result keeping: each conversation saved as it finishes, model ids and settings and per-run verdicts saved, a safe grader-check rerun reading Fable's column, retrieval answers keeping their passages, the freeze covering the data files the agent reads, the $8 cap on adversarial runs and the API grader, a held-out guard, and the 60-second cap enforced during calls.
- Open questions: action-gap calls stay inside the scope ceiling and are removed only in the adjusted ceiling (R16 wording); code checks that safety cases released the fixed reply first and made a ticket.
- Then rerun the stale results (adversarial set, retrieval answers and grading, threshold curve, Fable's grader check), recompute the agent freeze, update the architecture document, and rerun the gate.
