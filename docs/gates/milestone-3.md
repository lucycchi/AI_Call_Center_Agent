# Milestone 3 gate

Reviews of this milestone compare against `tortoise/milestone-2`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
rootdir: /home/lucyc/gauntlet/AI_Call_Center_Agent
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, langsmith-0.14.11
collected 432 items

tests/accounts/test_accounts.py ........................................ [  9%]
.........                                                                [ 11%]
tests/core/test_engine.py ..................                             [ 15%]
tests/eval/test_cases.py ...........................................     [ 25%]
tests/eval/test_retrieval_metrics.py ..................                  [ 29%]
tests/flows/test_conversations.py ...................................... [ 38%]
.....................................                                    [ 46%]
tests/flows/test_knowledge.py ....                                       [ 47%]
tests/handoff/test_handoff.py ..........                                 [ 50%]
tests/knowledge/test_search.py ..............                            [ 53%]
tests/ops/test_store.py ...........                                      [ 56%]
tests/pipeline/test_documents.py .........                               [ 58%]
tests/pipeline/test_findings.py .....................                    [ 62%]
tests/pipeline/test_labels.py ..............                             [ 66%]
tests/pipeline/test_templates.py .........                               [ 68%]
tests/replies/test_checks.py ...............................             [ 75%]
tests/safety/test_safety.py ............................................ [ 85%]
......                                                                   [ 87%]
tests/scheduling/test_eligibility.py ...........................         [ 93%]
tests/scheduling/test_transactions.py ...............                    [ 96%]
tests/test_config.py ..........                                          [ 99%]
tests/test_engine_interface.py ....                                      [100%]

============================= 432 passed in 16.49s =============================
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

## Review of the fixes

Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent reviewed `git diff 7a2979c..HEAD` against every finding and chosen fix above. Claude ran all 358 tests (passed); both reproduced their findings with offline probes. Most findings are fixed; these remain or are new.

| Finding | Codex | Claude |
|---|---|---|
| A goodbye closes the chat, and the next message ("actually wait, I smell gas") gets the closed text with no safety reply (the status check runs before safety) | | yes (top) |
| "C.O." is no longer understood ("the C.O. alarm is going off" is clear): punctuation became a clause mark before the swap | | yes (top) |
| A booking can still commit after the deadline (checked before the transaction, not before its commit) | yes (top) | |
| A committed booking can go unconfirmed: a failed warranty-review ticket, a writer failure or the deadline passing in the writer | yes (top) | yes (top) |
| Sentence checks now block published terms ("as a member, your diagnostic fee will be waived", "credited toward the repair", "the pending authorization will be removed"), while some real promises still pass ("I'll refund you the $89", "we'll credit your account") | | yes (top) |
| Picking by number is worse: a bare "2" loops; "the 2nd one" is read as 2 November | | yes (top) |
| A failed billing-review ticket is never retried (the invoice is marked reviewed first) | yes (top) | |
| The idle sweep can still close a conversation receiving a message (message insert and time update are separate writes) | yes (top) | |
| The burning-smell rule forgets after 20 stored messages | yes (top) | yes (unclear) |
| Stale documents missing from receipts: unquoted commas in `data/document_list.csv` cut the reason column | | yes |
| Real street names with "Old" or "The" ("1200 Old Mill Rd") are no longer masked | | yes |
| "Yes, Tuesday works" at a Monday read-back books Monday | | yes |
| A "no" or "yes" before a new scheduling action ("no, cancel my other appointment") hides the switch | yes | yes |
| The action-request backstop covers only the account route | yes | yes (unclear) |
| A past date this month ("October 10") stays in the past | yes | yes (low) |
| Failed state or receipt writes are silently dropped on a normal turn | yes | |
| A complete reply whose last sentence lands after 15 seconds also gets a handoff ticket | | yes |
| The dispute note is added to every later ticket, including emergencies; "anything earlier?" twice opens two tickets; "ok, all set" at a read-back ends the chat | | yes |
| Receipt outcome labels are engine words, not the plain labels of the reply receipt (R71) | | yes (unclear) |
| Each model call's timeout applies per attempt, so one retry can double it | | yes (unclear) |
| Tests miss each of the above | yes | yes |

**Author's choices on the review of the fixes:** fix everything recommended (items 1 to 21): safety before the closed check, abbreviations before clause marks, a lasting burning-smell flag; the deadline checked inside the transaction before commit; confirmations of committed changes as fixed sentences; a yes naming another day does not count; slot numbers and "the Nth one" pick slots; no handoff after a finished reply; "all set" is not a goodbye; sentence checks retuned and tested against every customer-document sentence; the document list quoted; the street denylist only for the word after the number, tested on every seeded address; message and time saved together; billing review marked after its ticket; a failed state save is an operations failure; billing notes only on billing tickets and one earlier-slot ticket; plain receipt labels; only a bare yes or no is a confirmation; the action backstop on scheduling and unambiguous knowledge requests; past dates told as passed; each model attempt gets half the time left.

## Second review of the fixes

Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent reviewed `git diff 2cb2201..HEAD`. Claude ran all 397 tests and compared probes against the code before this round; Codex probed in memory. Most of the 21 items are fixed; these remain or are new, several of them regressions.

| Finding | Codex | Claude |
|---|---|---|
| The abbreviation joiner joins across sentences: "It's not breaker B. I smell gas" is now clear (regression) | | yes (top) |
| The action backstop hands off questions and bookings ("how much does it cost to join", "what's your refund policy", "sign me up for a tune-up") (regression) | | yes (top) |
| Strict mode drops imperative payment requests ("I want to pay my bill") | yes (top) | |
| Promise checks: a published-terms word excuses a real waiver ("since you're a member, the late fee will be waived this time"); split sentences escape ("The fee is $89." "It will be waived for you."); ordinary sentences are blocked ("we take Visa ... for your invoice") | yes (top) | yes (top) |
| The writer is no longer bounded by the deadline (the check between sentences was removed) | yes (unclear) | yes (top) |
| Slot numbers beat dates ("first thing in the morning on Tuesday" picks Monday's first slot) (regression) | | yes (top) |
| "Yes, please confirm it" routed as a confirm request drops the booking; "Yes, Monday morning is fine" at a Monday read-back does not book; "yes, 12-4 works" books whatever was read back | yes | yes |
| A failed warranty-review ticket is lost after the booking commits | yes (top) | |
| Receipt writes still fail silently | yes (top) | |
| Membership action-gap tickets receive invoice notes | yes | |
| The per-attempt timeout's 0.5-second floor can exceed the time left | yes | |
| The burning-smell flag is not used by the burning-plus-breaker danger rule; the closed path reads 200 messages and the main path 20 | | yes |
| A writer instruction reaches the caller word for word ("Offer to check the caller's appointments again."); fixed confirmations show ISO dates and 24-hour windows | | yes |
| "I'm good" no longer ends a chat (regression); only the first tag of a combined ticket is remembered | | yes |
| Small: a race between the status read and the message insert; "3 the way it went down" masked as a street; confirmations skip the sentence checks | | yes (low) |
| Tests miss each of the above | yes | yes |

**Author's choices on the second review:** fix everything recommended (items 1 to 14), changing approach for two parts: the promise checks become deny by default (any concession word is blocked unless it matches an approved published term from the documents, judged with the sentence before it), and the action backstop catches only explicit requests on any route, leaving questions to the router; plus known-abbreviation joining only, the deadline checked before each later sentence, dates narrowing slot choices before ordinals, read-back yes rules, a retried warranty-review ticket, a retried receipt write, invoice notes only on dispute and billing tickets, no timeout floor, the burning flag in the danger rule, caller-facing fixed text, "I'm good" restored and every combined-ticket tag remembered. Left as they are: the narrow status-read race and one street over-mask.

## Third review of the fixes

Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent reviewed `git diff 90e5033..HEAD` with large phrase sets (Claude: 75 reply sentences, 85 request phrasings, every transcript caller line, whole conversations through the engine, all compared against 90e5033). Fixed and confirmed: the sentence-end safety bug, the writer deadline, dates before slot numbers, read-back yes rules for the reported phrases, the receipt retry, invoice notes, the burning flag, the fixed-text wording, "I'm good" and combined tags. Remaining:

| Finding | Codex | Claude |
|---|---|---|
| Approved-term keywords anywhere in the sentence or the one before excuse unrelated concessions ("As a member, the diagnostic fee and the late fee are both waived"; "A 50% discount applies to your next repair"; "Your prorated refund has been issued") (regression) | yes (top) | yes (top) |
| Promises with no listed word are never checked ("We won't charge you the late fee", "This visit is free of charge", "You'll get your money back", "We'll cover the cost") | | yes (top) |
| Published and ordinary sentences blocked: 15 of 39 in the probe set ("We accept all major credit cards", "There's no charge to cancel more than 24 hours before", "Refunds are handled by our billing team"); "well" read as "we'll" (regression) | yes | yes (top) |
| Action check: misses ("I’d like a refund" with a curly apostrophe, "Okay, sign me up", "Pay my bill please", "Take me off autopay", "Downgrade me", "Make sure my membership doesn't renew") and false hits ("How do I set up autopay?", "cancel my appointment, plus I have a question") (regressions) | yes (top) | yes (top) |
| The action backstop skips the handoff and redirect routes | yes | |
| A yes naming a time in other forms still books the read-back slot ("yes, 12-4 works", "Yes, Monday at 1 works") | yes (top) | |
| "Okay, I'm good" at a read-back ends the chat and drops the booking (regression); "I’m good" with a curly apostrophe does not end it | | yes |
| A failed warranty-review ticket is lost if the caller never writes again | | yes |
| A 10-millisecond timeout floor remains | yes | |
| Small: "May I have the 2nd one?" reads "may" as a month; tags recorded even when the ticket save failed; one test asserts a sentence that misstates the refund policy | | yes |

**Author's choices on the third review:** change approach (money promises checked by a model (D43)): every reply sentence about money goes to a Haiku check against the published money terms after the code rules, failing closed; the router decides action requests, with a code backstop for unmistakable requests only. Plus the smaller fixes: times in any form must match the read-back, a goodbye at a read-back needs "bye", curly apostrophes normalised, kept warranty-review tickets in a fallback file retried every message and at startup, no timeout floor, "may" as a month only before a day, tags recorded only when saved.

**Measured after the change:** on the 108 labelled sentences in `data/eval/money_sentences.jsonl`, the full sentence check caught 61 of 61 promises and released 47 of 47 published or ordinary sentences (`data/results/money_check/summary.json`); the instructions were tuned on this set, so the evaluation milestone measures it again on fresh sentences. In a real chat the first checked sentence took 2.1 to 4.7 seconds (budget 2.5), to be measured in the evaluation milestone.
