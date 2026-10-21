# Milestone 4 gate

Reviews of this milestone compare against `tortoise/milestone-3`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
tests/eval/test_grader_check_sheet.py .....                              [ 27%]
tests/eval/test_retrieval_metrics.py ..................                  [ 29%]
tests/eval/test_retrieval_runs.py .........                              [ 30%]
tests/eval/test_run_guards.py .......                                    [ 31%]
tests/eval/test_run_safety.py .........                                  [ 32%]
tests/eval/test_run_stops.py ............                                [ 34%]
tests/eval/test_scoring.py ...............                               [ 36%]
tests/eval/test_threshold.py .................                           [ 38%]
tests/flows/test_conversations.py ...................................... [ 42%]
........................................................................ [ 51%]
........................................................................ [ 60%]
....................................................                     [ 67%]
tests/flows/test_knowledge.py ...............                            [ 69%]
tests/handoff/test_handoff.py ..........                                 [ 70%]
tests/knowledge/test_search.py ..............                            [ 72%]
tests/ops/test_store.py ............                                     [ 73%]
tests/pipeline/test_documents.py .........                               [ 74%]
tests/pipeline/test_findings.py .....................                    [ 77%]
tests/pipeline/test_labels.py ..............                             [ 79%]
tests/pipeline/test_templates.py .........                               [ 80%]
tests/replies/test_checks.py .................................           [ 84%]
tests/safety/test_safety.py ............................................ [ 89%]
......                                                                   [ 90%]
tests/scheduling/test_eligibility.py ................................... [ 94%]
...........                                                              [ 96%]
tests/scheduling/test_transactions.py .................                  [ 98%]
tests/test_config.py ..........                                          [ 99%]
tests/test_engine_interface.py ....                                      [100%]

============================= 806 passed in 38.77s =============================
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

## Fixes and reruns

All the chosen findings were fixed test-first (commits ddf0797 to 962c869); the suite went from 517 to 638 tests, all passing.

- **Found while fixing:** the evaluation fix agent's first held-out guard test ran the real run command on the held-out set before the guard existed. With a fake key no agent turn ran and nothing was spent, but Codex graded the 15 empty conversations once and so saw the held-out requests and reference answers. The output was deleted and never committed. Recorded as keeping the held-out set after the grader saw it (D46).
- **Agent changes from the reruns:** a message in another language gets an English note and a handoff, with a code backstop when the router misses it, and the writer always writes in English (D47); nonsense is handed off; picking a slot in a reschedule is not taken for a new booking.
- **Adversarial set:** 32 of 32 pass with the independent checks (booking-rule and extraction attacks 100%), for $0.06.
- **Retrieval answers:** two fresh graded runs of the current agent (about $0.54 each); combined search 88% and 92% correct, 92% faithful in both.
- **Threshold:** one answer that guessed in one run and not the other moved the single-run pick to 0.45; pooled over both runs (50 answers) the same rule picks 0.25 (74% contained, 5 wrong confident answers). Pooling recorded as choosing the threshold from every graded run of the agent (D48).
- **Grader check:** a fresh sample of the new answers; Claude Fable 5.1 graded blind and agrees with Codex on 29 of 30 (97%). The old sheet and its grades are archived in `data/grader_check_archive/1.csv`. Grades now stay tied to the answer text they were given for.
- **Agent freeze:** recomputed over 61 files, hash `f7ecfd29d6725dd96953c769bf444a51a730befdf6628faeb126d5a47c49fd68`, the same hash both graded retrieval runs are filed under.
- **Architecture document:** updated for every point from both architecture checks, and the HTML page regenerated.
- **Not rerun:** the quick run (Task 20) was last passed before these fixes; the agent has changed since.

## Review of the fixes

Code reviews of `git diff ace46b0..HEAD` by Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent, both using `prompts/code-review.md`. Claude reproduced every original finding as fixed, ran all 638 tests (passed) and replayed the 505 saved caller lines through the old and new code; Codex could not start the suite (no writable temporary folder) and probed offline. Neither made paid calls; no held-out leakage was found. The quick run was stopped after its first 20 conversations ($0.41), since the agent will change.

| Finding | Codex | Claude |
|---|---|---|
| The language backstop hands off ordinary English, even mid-flow: an email, lowercase names and addresses, "Thermostat display blinking constantly", "Kitchen faucet drips constantly overnight", "José García"; it calls "gas smell", "either works" and "account number 48213" nonsense | yes (top) | yes (top) |
| Closing lines no longer end the chat ("Nope, that covers it. Thanks for your help!", "That's all I need, thank you so much."): 17 saved simulator lines regressed, and mid-flow they re-offer slots or go onto the ticket; some filler lines too ("sorry, hang on a sec") |  | yes (top) |
| Switching scheduling action needs a literal verb: "schedule a tune-up instead", "I don't need the Thursday visit anymore" and "when is my existing appointment?" no longer switch | yes (unclear) | yes (top) |
| The booking check accepts any earlier reply that named the slot, including the offer, so a booking that differs from the read-back passes (saved case Tb456e16e did this); the slot matcher misses some phrasings |  | yes (top) |
| Grader batches that succeeded are lost if a later batch fails (verdicts are saved only after every batch) | yes (top) |  |
| The API grader fallback runs under its own second $8 budget and charges after the call | yes (top) |  |
| Retrieval runs are filed under the agent hash at grading time, not at answer time; grading the same answers twice pools them twice | yes (top) | yes (unclear) |
| Grader-check grades survive a changed question or reference answer; starting a fresh sheet loses the hidden verdicts the archived grades were checked against | yes (top) | yes (unclear) |
| Ordinal picks from ordinary sentences: "The first option is too early", "The second doesn't work", "the second time it broke", "the third week of November" | yes | yes (unclear) |
| A message that identifies the caller and asks something ("This is Linda Foster, MHC-10001. Can you help me?") now opens a ticket instead of "found your account" |  | yes (unclear) |
| "Yes, sooner if possible" books the read-back slot instead of looking for earlier ones |  | yes (unclear) |
| Conversations stopped at the time or turn limit can pass the quick run | yes (unclear) |  |
| A simulator timeout at the 60-second cap is recorded as an error, not the time limit; the SDK retry can overshoot the cap |  | yes |
| Crossing the budget mid-turn becomes a handoff inside the agent, and that case is scored on the distorted conversation |  | yes (unclear) |
| Rerunning a run under the same name deletes the earlier run, including a final run |  | yes (unclear) |
| A handoff case with no expected reason can never pass |  | yes (unclear) |
| "discretion" is listed as internal-only but appears in a customer document; the gate notes say 60 frozen files, not 61 |  | yes |
| Tests too weak to catch the above (English sentences heavy in technical words, closing lines, paraphrased action switches, read-back mismatch, mid-batch grader failure, budget overshoot) | yes | yes |

## Author's choices on the review of the fixes

The author chose "All recommended" (2026-10-20): the language backstop only on strong signs (inverted punctuation, a non-Latin script or several common Spanish or French words, never with an email or account number) and no nonsense label in code, the "anything else?" shortcut only for messages with a common English word; wider closing and filler word lists tested on the 17 regressed simulator lines; the old action-switch rule except that a reply picking a slot or answering the offer never switches; no slot pick from a rejection or negation; "if possible" or "anything sooner" with a yes looks for earlier slots; an identifying calm message with no named handoff gets "found your account"; the booking check against the read-back just before the change, with more slot phrasings; grader batches saved as they finish; the API grader under the run's budget, checked before each call; retrieval runs filed under the agent hash at answer time, refused if the agent changed and never pooled twice; grader-check grades tied to question, reference, answer and passages, with hidden verdicts archived; time- and turn-limit stops fail the quick run, a cap timeout recorded as the time limit with no retry past it, crossing the budget mid-turn stopping the run; an existing run name refused; a handoff case without an expected reason passing on any reason; "discretion" dropped from the internal-only terms; the frozen file count corrected. Then the reruns, a new freeze and the full quick run.

## Fixes and reruns after the review of the fixes

All the chosen findings were fixed test-first (commits 910fc1e to 1334222); the suite went from 638 to 781 tests, all passing.

- **Found while checking the fixes:** the widened goodbye list counted "I'm confused" as a pleasantry, so "That's all, I'm confused" ended the chat; confusion was taken out and a confused caller is never closed out.
- **Found by the quick run:** a plain yes at a read-back ("That's fine, yes please go ahead and book it") switched to an appointment lookup when the router labelled it a confirm request, and "That's fine" was not a yes; a move offered another technician's slot at the visit's own date and window. Both fixed. Codex sometimes leaves an item out of a batch; the grader now asks once more for just those items.
- **Quick-run rule:** a booking the simulated caller never confirmed (it said "Book it" but never chose a slot) is a missed request, not a booking fault; the quick run fails outright only on a wrong change, an unexpected write or a confirmed read-back left unbooked (proposed decision D49).
- **Adversarial set:** 32 of 32 on the frozen agent.
- **Retrieval answers:** two graded runs of the frozen agent, combined search 92% and 96% correct, 96% faithful; the pooled threshold stays 0.25 (78% contained, 3 wrong confident answers over 50 answers).
- **Grader check:** a fresh sample of the frozen agent's answers; Claude Fable 5.1 agrees with Codex on 30 of 30. Earlier sheets are archived with their hidden verdicts.
- **Agent freeze:** hash `cfe0472409be496d646ce67830d4d185d9930f0f4c40dc8e3764bb6c45325419`, the hash both graded retrieval runs are filed under.
- **Quick run:** failed on the plan-savings case and a time-limit stop; see the next section.

## Last round: quick-run failures, the agent's own answers and the threshold

Every change test-first (commits 6167bbc to bae1eac); the suite is at 806 tests, all passing.

- **Test-run fidelity:** turning off SDK retries had also removed the agent's own retries, so slow calls failed where production retries; now only the simulated caller loses retries within the 60-second cap. The grader was never told the test's fixed date and judged a Monday 19 October booking as past against the real date; each conversation now carries its "now" and the rubric judges dates against it.
- **Plan savings (T9e29febc):** a question whether a plan saves money gets every member benefit, including the included tune-ups, and never a guess whether joining would save money.
- **The agent's own answers:** the retrieval answers had been written by a separate short prompt, so the answer measures and the threshold curve did not describe the agent. Combined-search answers now come from the agent's knowledge flow, writer and checks; keyword-only and whole-knowledge-base answers keep the short prompt as a search comparison. Measured this way the agent first scored 80% and 84% correct, 76% and 72% faithful and 0% correct refusal.
- **Fixes that showed:** the writer could not refuse a question the documents cannot answer (two of its rules contradicted each other); it now writes a hidden marker that, for a knowledge answer only, becomes a "not enough evidence" handoff with a ticket, and later sentences are still released. The final-price line now goes only on prices that vary by job, with the price-book passage it comes from.
- **Retrieval answers (agent-written, two graded runs):** combined search 88% correct, 96% faithful, 100% citation accuracy, refusal 100% and 67%.
- **Threshold:** the pooled curve over the two runs (50 answers) picks 0.35 (76% contained, 4 wrong confident answers, against 6 at 0.25 for the same containment); set to 0.35 as the agreed rule says (D48). The curve's runs were written with the threshold at 0, so they do not depend on its value.
- **Adversarial set:** 32 of 32.
- **Grader check:** a fresh sample of the latest answers; Claude Fable 5.1 agrees with Codex on 27 of 30 (90%), every disagreement a pass by Fable that Codex failed.
- **Agent freeze:** hash `836b241517d187b64528c0e70a9ed4be3994d2dd18434256870f2a8c9897f01e`; it differs from the agent that wrote the graded runs only in the threshold setting.
- **Quick run on the frozen agent:** passed 2 of 2. Knowledge 100% and 100%, bookings 100%, routing 100%, lookups 100%, safety and booking handoffs 100%, no wrong confident answers; containment 59% and 55% against a scope ceiling of 75% and an adjusted ceiling of 66%.
- **Settled:** the quick-run rule for a booking the caller never confirmed (D49), by the author.

## Review of the last round

Code reviews of `git diff a15994f..HEAD` (everything after the second review) by Codex (gpt-5.6-sol) and a fresh Claude agent. Claude ran all 806 tests (passed) and probed offline; Codex ran 21 targeted tests. No paid calls, no held-out runs.

| Finding | Codex | Claude |
|---|---|---|
| Hedged or deferring replies book at the read-back ("Alright, let me think about it", "That's fine, I'll call you back later", "fine I guess") since "fine" and "alright" became yes-words |  | yes (top) |
| The final-price line is missing on price-book ranges (a new water heater, a member asking about a blower motor, an emergency repair), contrary to the pricing rule (R42); its source sentence is not in the original price book | yes (top) | yes (top) |
| An unexpected database write never fails the quick run outright | yes (top) | yes |
| The threshold curve counts answers that end in the agent's handoff as contained or as wrong; counted as neither, the rule picks 0.25 and containment at 0.35 is 64%, not 76% |  | yes (top) |
| The threshold result is filed under a different agent hash from the freeze, so the threshold step cannot be rerun | yes (unclear) | yes (unclear) |
| Marker variants reach the caller ("[Not in documents]", "NOT IN DOCUMENTS", a cut-off "[NOT IN") |  | yes (top) |
| A marker-only writer reply on a booking or account turn sends the caller nothing |  | yes (top) |
| Agent-written retrieval answers run under a second, unenforced $8 counter | yes (top) |  |
| Retrieval grading still saves its verdicts only at the end | yes (top) |  |
| The confirmed read-back check misses the agent's own wording (clear "yes") and its yes rule, so a real booking fault can pass as a miss |  | yes |
| At a booking offer, "Tuesday doesn't work, what about Thursday?" can start a reschedule; "can't" is not a negation |  | yes (unclear) |
| A clear question after the caller's details is dropped by "found your account" |  | yes (unclear) |
| A pleasantry at a slot offer ("Perfect, appreciate it") ends the chat |  | yes (unclear) |
| Budget-cut cases vanish from the scores without a count |  | yes (unclear) |
| A booking after a mid-read-back question is flagged as not read back; a marker on a mixed booking and knowledge turn opens a not-enough-evidence ticket; a blocked sentence after the marker loses its label |  | yes (unclear) |

## Author's choices on the last round

The author chose "All recommended" (2026-10-20): "fine" and "alright" are no longer yes-words on their own and deferring phrases are hedges; the final-price line on every service-catalog or price-book range except fixed fees, tune-ups, cancellation fees, membership prices and the free replacement estimate, shown to the grader as the company pricing rule (R42); the marker matched in any case and spacing and a cut-off one stripped; an empty reply treated as a writer failure; at a slot offer a message naming a day or time switches action only with that action's verb, and "can't" is a negation; "found your account" only for a general request for help; at an open offer or read-back only "bye", "goodbye" or "that's all" end the chat; an unexpected write fails the quick run outright; the confirmed read-back check uses the agent's wording and yes rule; one $8 cap for retrieval runs; retrieval grades saved per batch; handoff answers counted as neither contained nor wrong confident in the curve, runs filed under an agent hash without the threshold setting, and the threshold set to the corrected curve's pick; budget-cut cases counted in the summary. The three minor items are accepted. Then the full rerun cycle.
