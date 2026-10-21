# Milestone 5 gate

Reviews of this milestone compare against `tortoise/milestone-4`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
tests/flows/test_knowledge.py ..................................         [ 53%]
tests/handoff/test_handoff.py ..........                                 [ 54%]
tests/knowledge/test_search.py ..............                            [ 55%]
tests/ops/test_jobs.py ....................                              [ 56%]
tests/ops/test_spend.py ...............................                  [ 59%]
tests/ops/test_store.py ............                                     [ 60%]
tests/pipeline/test_documents.py ..........                              [ 60%]
tests/pipeline/test_findings.py .....................                    [ 62%]
tests/pipeline/test_labels.py ..............                             [ 63%]
tests/pipeline/test_templates.py .........                               [ 63%]
tests/replies/test_checks.py ........................................... [ 67%]
..............                                                           [ 68%]
tests/replies/test_money_published.py .................................. [ 70%]
........................................................................ [ 75%]
............................                                             [ 77%]
tests/safety/test_safety.py ............................................ [ 81%]
......                                                                   [ 81%]
tests/scheduling/test_eligibility.py ................................... [ 84%]
...........                                                              [ 84%]
tests/scheduling/test_transactions.py .................                  [ 86%]
tests/test_config.py ..........                                          [ 86%]
tests/test_deploy_config.py ............................................ [ 90%]
.............                                                            [ 91%]
tests/test_engine_interface.py ....                                      [ 91%]
tests/test_repository.py ...................................             [ 93%]
tests/web/test_chat.py ....................................              [ 96%]
tests/web/test_results.py ................                               [ 97%]
tests/web/test_staff.py ...............................                  [100%]

======================= 1368 passed in 70.90s (0:01:10) ========================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 5 is ticked (6 of 6).

## Architecture check

Run by Codex (gpt-5.6-sol) and by a fresh Claude agent, both using `prompts/architecture-check.md`, against `tortoise/milestone-4`. Claude ran all 1,368 tests (passed); the live build's agent hash differs from the frozen 5b8f6899, as expected after the live-only fixes (D51).

**Both found:**
- The web layer applies the message rate limits before the engine runs, so a rate-limited caller reporting gas gets the limit message instead of the safety advice; the document says safety comes first.
- The reviewer link is reusable (D50) but the document still calls it one-time; the used-tokens table is unused.
- Spending pools and rate-limit counts are described wrongly (counts are kept in memory and reset on restart, not rebuilt from stored messages).
- The project status is stale; closing a ticket is documented but there is no staff route for it; the cookie secret and alert webhook are missing from the secrets list.

**Only the Claude agent found:** event, alert and receipt label lists out of date; the live-only fixes (D51), the address answer and "address change" tag, the reload, logout and HEAD routes, the purge details, the final-run, resume, per-driver and flag-export tools, the `data/results/final/` files and the $0 public budget are undocumented.

**Only Codex found:** the invoice-to-appointment relation in the database diagram is drawn as required and unique.

## Reviews

Code reviews of `git diff tortoise/milestone-4..HEAD` by Codex (gpt-5.6-sol) and a fresh Claude agent, both using `prompts/code-review.md`. Claude ran the 240 web, operations, resume, final-run and deploy tests (passed) and probed offline; Codex could not start the suite (no writable temporary folder). No paid calls, no held-out data. Both found the cookies, reviewer token handling, staff sessions and form token, cross-visitor scoping, the Fly-Client-IP trust rule, the $0 refusal before any model call and the text escaping sound.

| Finding | Codex | Claude |
|---|---|---|
| Rate limits run before the safety check, so a rate-limited emergency gets no safety advice or priority ticket | yes (top) | yes (architecture) |
| The code-only money pre-check releases false terms: "15% off all repairs, including plumbing", a Plus-only plumbing inspection said of Standard, "$89 waived ... including water heater flush", "Standard and Plus are $269 per year" | yes (top) | yes (top) |
| A yes-word with details after a safety reply ("Sure, Linda Foster, MHC-10001") skips identification, leaving the emergency ticket without the caller |  | yes (top) |
| "What time?" or "what day?" at an open slot offer gets the demo clock instead of the slot |  | yes (top) |
| The stream-timeout, restart-replay and engine-crash fallbacks promise a team follow-up but open no ticket |  | yes (top) |
| A timed-out stream leaves its turn running; after a long wait (for example the reset gate) it can still book after the caller was told it was handed off | yes (top) |  |
| An accepted message exists only in memory until its worker starts, so a restart in that window loses it | yes (top) |  |
| The spending caps are check-then-spend; writer calls cut short (a blocked sentence, the deadline) are never counted, and concurrent or multi-call turns can pass the cap | yes (top) | yes (top) |
| Message-limit counts reset on every restart or deploy | yes | yes (architecture) |
| The staff form token is masked as a phone number about once in 300 sessions, breaking flagging |  | yes |
| Conversation rows and reply-end events are written before the limit check, and blank messages skip the limits |  | yes (unclear) |
| A promise that names the open ticket passes even with a new timed commitment ("within 10 minutes about Ticket #3") |  | yes (unclear) |
| Every open tab polls the staff panel every 8 seconds, and each poll and each Results view scans whole operations tables |  | yes (unclear) |
| The held-out conversations and databases ship in the image (nothing serves them) |  | yes (unclear) |
| A reused message id in another conversation is silently dropped; a failed reply-end save replays as a restart; a lookup failure in the safety path could lose the ticket; the staff sign-in limit is per exact address (IPv6 rotation) |  | yes (unclear) |
| The reviewer link's reusability against the one-time reviewer-token requirement (R85); intended by D50 | yes (unclear) |  |
| Tests too weak to catch the above | yes | yes |

## Author's choices

The author chose "All recommended" (2026-10-21); every agent change goes to the live build only, as live fixes after the measurement (D51), with the held-out numbers unchanged:
- the message rate limits apply after the safety check;
- the money pre-check sends to the model any sentence naming a plan with a service outside that plan's published list, or several plans with one price;
- details given with a yes after a safety reply identify the caller first;
- the date answer only when no booking offer or read-back is open;
- the timeout, restart and crash fallbacks open an error ticket;
- a timed-out turn is marked finished and cannot commit later;
- an accepted message is saved at once, so a restart hands it off rather than losing it;
- writer calls cut short are counted and the budget is checked before each model call in a turn;
- the staff form token is not masked;
- limits are checked before any row is written, and blank messages write nothing;
- only a restatement of the open ticket's own promise passes the follow-up rule;
- restart-cleared limit counts documented; the staff panel polls only while open; only the summary files ship in the image;
- accepted as they are: a reused message id across conversations, the per-address staff sign-in limit, a failed reply-end save, a lookup failure in the safety path, and the resume refusal after a partial run;
- the architecture document corrected for every point from both architecture checks, and the unused used-tokens table removed.
