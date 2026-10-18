# Milestone 3 gate

Reviews of this milestone compare against `tortoise/milestone-2`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Call_Center_Agent
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, langsmith-0.14.11
collected 301 items

tests/accounts/test_accounts.py .............................            [  9%]
tests/core/test_engine.py ............                                   [ 13%]
tests/eval/test_cases.py ...........................................     [ 27%]
tests/eval/test_retrieval_metrics.py ..................                  [ 33%]
tests/flows/test_conversations.py ...........                            [ 37%]
tests/flows/test_knowledge.py ....                                       [ 38%]
tests/handoff/test_handoff.py ..........                                 [ 42%]
tests/knowledge/test_search.py ..............                            [ 46%]
tests/ops/test_store.py .........                                        [ 49%]
tests/pipeline/test_documents.py .......                                 [ 52%]
tests/pipeline/test_findings.py .....................                    [ 59%]
tests/pipeline/test_labels.py ..............                             [ 63%]
tests/pipeline/test_templates.py .........                               [ 66%]
tests/replies/test_checks.py ......................                      [ 74%]
tests/safety/test_safety.py ...............................              [ 84%]
tests/scheduling/test_eligibility.py ....................                [ 91%]
tests/scheduling/test_transactions.py .............                      [ 95%]
tests/test_config.py ..........                                          [ 98%]
tests/test_engine_interface.py ....                                      [100%]

============================= 301 passed in 10.69s =============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 3 is ticked (9 of 9).

## Architecture check

Run by Codex (gpt-5.6-sol, per-run override) and by a fresh Claude agent, both using `prompts/architecture-check.md`.

**Both found:**
- An engine failure ends with an error done event but no handoff message, though the document says the handoff flow turns it into one; the 15-second deadline covers only flow steps, not routing or writing.
- `agent_confirmations` is not drawn in the scheduling database diagram.
- Switching to a different customer's account mid-conversation is not documented.

**Only the Claude agent found:**
- Errors are written only to the server log, never recorded as events, so the error alert has nothing to count.
- The dispute ticket's constraints do not carry the fee mismatch (flow 5.4, step 6).
- Receipts: `excluded` is always empty, passages lack dates, the route lacks clear or unclear; outcome labels differ from the document.
- An idle conversation mid-flow should become "abandoned", not "closed"; ending a chat when the caller ends it is not built.
- No retry of the operations write after a committed booking.
- Not documented: the acknowledgement shortcut past the router, several requests per message sharing one ticket, the closed-conversation reply, `app/flows/`, the model-call recorder and the terminal chat; the reply-check list and the "blocked sentence" event name need updating.

**Only Codex found:**
- The status paragraph is stale.
- After a plumbing decline the booking flow is left half open, and every capacity decline names "hvac repair".
- The reschedule diagram reads the seed before the transaction; the code reads it inside.
- The emergency ticket is created before the safety advice is released.
- The router's output limit is 2,000 tokens in code against 200 in settings (Milestone 1 found Haiku returns no JSON at 200).

## Reviews

Code reviews of `git diff tortoise/milestone-2` by Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent, both using `prompts/code-review.md`. Claude ran all 301 tests (passed) and reproduced each finding with offline probes; Codex ran 57 (the rest need a writable temporary folder) and probed in memory.

| Finding | Codex | Claude |
|---|---|---|
| Safety: "No, but I smell gas" and "not sure, I smell gas" pass as clear (a negation in another clause cancels the trigger) | | yes (top) |
| Safety: "natural gas" and "gas odor" pass as clear | yes (top) | |
| Breaker-reset advice is never blocked after a burning smell (the rule is unused; the troubleshooting FAQ says to reset a breaker) | | yes (top) |
| A hedged "ok" or "sure" ("ok wait, is there a fee?") counts as a clear yes and changes the database | | yes (top) |
| Slot choice: "the Tuesday one" picks Monday ("one" is read as first); calendar dates ("October 22", "the 22nd", "10/22") are not understood; an explicit date loops in a reschedule | | yes (top) |
| An unidentified caller's second account or scheduling request is dropped, and a later question gets its answer | | yes (top) |
| A step past the deadline keeps running and can commit a booking after the caller was told it was handed off; the router and writer are outside the deadline | yes (top) | yes |
| Operations database down: no message to the caller and nothing logged; a log write after a committed booking can hide the confirmation | yes (top) | yes |
| Reply checks miss passive and synonymous promises ("the fee will be waived for you", "a refund has been issued", "you qualify for a 20 percent discount", "I've removed the charge") | yes (top) | |
| A cancellation or reschedule that finds nothing still says it succeeded | yes (top) | |
| Idle close: mid-flow should be abandoned; a message arriving during the sweep can be closed | yes | yes |
| A decline forgets the requested service ("no hvac repair availability" for plumbing) | yes | (architecture) |
| Receipts lose the dated passages and excluded documents | yes | (architecture) |
| The dispute ticket lacks the fee mismatch; "tried" omits lookups | | yes |
| Street pattern false positives ("15 years old way", "2 systems at my place") count as identity attempts and are masked | | yes |
| Router output limit hard-coded at 2,000 | yes | yes |
| A different scheduling action mid-flow (book, then "cancel my other appointment") is treated as a follow-up | | yes (unclear) |
| Conversation ownership is not checked in the core | yes (unclear) | yes (unclear) |
| The action-gap code check is unused; the router alone decides | | yes (unclear) |
| The warranty flag is set on plumbing, tune-up and estimate bookings for a recent install | | yes (unclear) |
| No "wants an earlier slot" ticket path | | yes (unclear) |
| Tests too weak to catch the above (safety phrasing, hedged yes, dates, multi-request, deadline side effects, ops failure, echo writer, failed cancel) | yes | yes |

## Author's choices

The author chose to fix everything recommended (items 1 to 22):

- **Safety:** negations count only within their own clause; gas synonyms added; breaker-reset advice blocked once a conversation mentions burning; promise checks match what is promised (waived, refunded, removed, credited, discounted), not who says it.
- **Database changes:** only a plain yes confirms; failed changes are reported plainly; one cooperative per-message deadline (no background thread), checked before each model call, before each commit and between sentences; every failure path gives the phone-the-office message and is logged; a committed booking is always confirmed, with a retried log write.
- **Wrong answers:** dates before ordinal words, calendar dates understood, the reschedule loop fixed; every waiting request answered after identification; declines keep the service and close the flow; street pattern needs a street-type word.
- **Records:** dated passages and excluded documents in receipts; the fee mismatch and lookups in the dispute ticket; errors recorded as events; idle mid-flow conversations abandoned, the idle sweep safe against a new message, and the caller can end a chat; safety advice before the ticket; router output limit set to 2,000 in settings with the reason.
- **Open questions, all yes:** the core checks conversation ownership; the action-request code check backs up the router; the warranty flag only on HVAC repair visits; a "wants an earlier slot" ticket when the earliest slots are not enough; a different scheduling action counts as a new topic.
- **Documentation and tests:** all architecture updates; a test for every finding, an engine test with the operations database unavailable, and a fake writer that breaks rules.
