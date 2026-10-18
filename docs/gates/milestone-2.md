# Milestone 2 gate

Reviews of this milestone compare against `tortoise/milestone-1`, the last approval.

## Tests

**Passed:** `python -m pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Call_Center_Agent
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1, langsmith-0.14.11
collected 130 items

tests/eval/test_cases.py ...................................             [ 26%]
tests/eval/test_retrieval_metrics.py ................                    [ 39%]
tests/knowledge/test_search.py ..............                            [ 50%]
tests/pipeline/test_documents.py .......                                 [ 55%]
tests/pipeline/test_findings.py .....................                    [ 71%]
tests/pipeline/test_labels.py ..............                             [ 82%]
tests/pipeline/test_templates.py .........                               [ 89%]
tests/test_config.py ..........                                          [ 96%]
tests/test_engine_interface.py ....                                      [100%]

============================= 130 passed in 3.62s ==============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 2 is ticked (3 of 3).

## Architecture check

Run by Codex (gpt-5.6-sol, per-run override) and by a fresh Claude agent, both using `prompts/architecture-check.md`. Both found nothing missing from this milestone.

**Both found:**
- Combined search always keeps each list's top result before reciprocal-rank fusion; the document describes plain fusion only (summary table line 68 and the search sections).
- The retrieval answer run uses the ordinary Anthropic key rather than the separate test key (Codex adds: the library's default two retries instead of one, and no $8 budget stop).
- The evaluation-files table omits `data/split_counts.csv`, `data/knowledge_questions.jsonl` and `data/results/retrieval/` (`summary.json`, `answers_to_grade.jsonl`).

**Only the Claude agent found:**
- The ticket's reason list lacks four reasons the test cases expect: late technician, complaint, commercial and burning smell (fix before the handoff flow task, Task 15).
- Retrieval results do not record the model ID and settings, though the document says every run logs them.
- The stale-question check uses a typed-in list of excluded documents instead of reading `data/document_list.csv`.
- Evidence line numbers count lines in the converted copies under `data/kb_text/`, not the originals; the document should say so.
- Not documented: the pinned embedding model (voyage-4); planted appointment fixtures (slots from 9000, appointments from 5000); the extra test-case fields and the clean-decline and redirect outcomes; the zone capacity typed into the case builder rather than taken from the capacity counts.

**Only Codex found:**
- The "where the project stands" paragraph still says only milestone 1 is built.
- The outside-services diagram does not show the retrieval test sending passages and the whole knowledge base to Sonnet.

## Reviews

Code reviews of `git diff tortoise/milestone-1` by Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent, both using `prompts/code-review.md`. Claude ran all 111 tests (passed); Codex ran 36 (passed; the rest need a writable temporary folder its sandbox lacks). Claude also confirmed the held-out hash, byte-identical rebuilds of the cases and questions, and that the committed index matches the chunker.

| Finding | Codex | Claude |
|---|---|---|
| Caller scripts keep the transcript's account number, name and phone beside a different caller card (checked: 32 of 52 cases, 9 held out; e.g. script "MHC-25306, Robert Martinez", card MHC-70158 Robert Clark) | yes (top) | |
| Billing fixtures plant the wrong invoice: the quote dispute plants the quoted $89, not the invoiced $149; an invoice number the caller gives is not planted | yes (top) | yes (top) |
| Retrieval answer run uses the live key, default retries and no $8 stop | yes (top) | (architecture check) |
| The "join the membership and book" case expects only a handoff, so an agent that drops the booking can pass | yes (top) | |
| The membership-mention rule fires on any "Comfort Club" mention, e.g. "I'm a member" | | yes (latent) |
| Combined search is not plain reciprocal-rank fusion; it costs recall (93% against meaning-only 98%) | yes (wrong) | yes (unclear: builder's call allowed) |
| Keyword search's forced top result is arbitrary when no word matches (always the hours section) | | yes |
| Keyword-only mode still calls Voyage | yes | |
| Evidence spans are whole sections copied from the chunker, not the exact answering lines (R29) | | yes (top) |
| Coverage is set by how many unanswerable questions were written (20 of 23), not by the documents (R30) | | yes (top) |
| Stale-question accuracy cannot fail, since the index holds no old documents | | yes (unclear) |
| No keyword-only answers for the answer-correctness comparison | | yes (unclear) |
| Retrieval summary does not say it covers only the working set the fusion rule was tuned on | | yes (unclear) |
| Synthetic customer IDs (MHC-9xxxx) fall in the real ID range, and fixtures overwrite on a match | | yes (latent) |
| Fixture guard refuses only the seed file, not the live database (R13) | | yes |
| Install-age matching handles only "three years old"; the 18-year-old system case gets a 2019 install | yes | |
| Planted appointment slots are not in the seed, so a freed slot has no defined status; two double-book technician 1 | | yes (unclear) |
| Planted windows are not checked against the weekday (Saturday mornings only; evening window Tuesday and Thursday) | | yes (latent) |
| "What an invoice is for" expected to hand off because the caller asks for an emailed copy | | yes (unclear) |
| Plumbing and estimate clean declines depend on a random zone draw when the transcript names no city | | yes (unclear) |
| Tests too weak to catch the above | yes | yes |

## Author's choices

The author chose to fix everything recommended (all of groups A, B and C):

- **Test-case data:** write the caller card's identity into the scripts; plant the invoiced amount under the caller's invoice number; expect both the handled part and the handoff for calls with two requests (R39); narrow the membership-mention rule; read any stated system age; check planted windows against the weekday and avoid double-booking a technician; a freed planted slot goes back to open; record when a zone was drawn rather than taken from the transcript.
- **Safety:** the fixture loader refuses the live database as well as the seed; synthetic customer IDs sit outside the real range, and a collision fails instead of overwriting.
- **Refreeze:** the rebuilt cases change the held-out fingerprint. This is allowed because no agent tuning has happened (R10); it is recorded as a new decision with the new fingerprint.
- **Retrieval measures:** separate test key, one retry, $8 stop, and the model and settings recorded; summary names the set; evidence spans narrowed to the exact answering lines (R29); coverage over handled-reason caller questions only (R30); stale questions scored on the answer at grading (Task 19), with an index check and the excluded list read from the document list; keyword-only answers added; keyword-only mode skips Voyage and the keyword top is kept only when a word matches; keep-each-list's-top rule kept and recorded as a decision, re-measured and reported honestly against meaning-only.
- **Architecture document:** all wording fixes from both checks.

**After the fixes.** The retrieval answers were rerun on the separate test key (Sonnet 5.5, 800 tokens, low effort, one retry; $0.52): 72 answers from keyword-only search, combined search and the whole knowledge base for the 24 working-set questions, waiting for grading (Task 19). Working-set retrieval: keyword-only recall 69% and hit rate 71%; meaning-only 98% and 100%; combined 94% and 100%; stale-question hit rate 100% for combined; coverage 0.875 of handled-reason questions; no excluded document in the index. The author chose the revised Comfort Club savings answer (a team member confirms whether benefits apply on the day of joining) and settled the refreeze decision (D40).

## Review of the fixes

Codex (gpt-5.6-sol, per-run override) and a fresh Claude agent reviewed `git diff 68feeda..HEAD` against every finding and chosen fix above. Both ran all 131 tests (passed) and rebuilt the cases and questions byte for byte; the refrozen held-out hash verifies. Both found every original finding fixed except those below.

| Finding | Codex | Claude |
|---|---|---|
| Some requests in a call are still not listed: the renewal-date caller also asks "can I still cancel before then?"; the held-out repeat-repair caller asks "can you get someone out?"; the compressor caller says "let's schedule it" | yes (top) | yes (top; booking ones unclear) |
| The cancel case expects the customer's tune-up on 10/21, but the caller says "my brother-in-law ended up fixing it", which fits their repair on 10/28; appointments are chosen without the service type | | yes (top) |
| The "join the plan" caller is drawn as an existing Comfort Club Plus member | | yes (top) |
| Every planted invoice is fully unpaid, including the held-out "charged twice" caller (paid twice) and the refund caller | | yes (top) |
| Six reference answers state facts outside their evidence spans (for example the 12-month minimum; "the technician confirms the final price") | yes (top) | spans include lines in between (minor) |
| Coverage still depends on the hand-written question mix; the filter does not change the working-set figure (both out-of-scope questions are held out) | yes (unclear) | yes (unclear) |
| Retrieval results do not record the SDK versions, the $8 cap, timeouts, or Voyage's input type and retries | yes | |
| Planted-fixture id ranges (appointments from 5000, slots from 9000) still undocumented | yes | yes (harmless) |
| Combined-search decision (D41) still proposed | yes | yes (unclear) |
| Reschedule caller wants "any afternoon this week"; the first open afternoon is 10/21 | | yes (unclear) |
| Tests check names and addresses in one case only; no tests of tier, appointment service, invoice balance or span support against the caller's words and the reference | yes | yes |

**Author's choices on the review of the fixes:** fix everything recommended: a reviewed list of every request in each case (written from the scripts, checked by a fresh agent), read by the builder; seeded appointments matched on service type and preferring customers with one upcoming appointment; callers asking to join drawn as non-members; paid invoices for the charged-twice and refund calls; evidence spans covering every fact in the reference, with a test; coverage over the knowledge questions callers ask, weighted by calls; fuller run settings; fixture id ranges documented; stronger tests; no change to the reschedule case; one more held-out refreeze, recorded as a new decision replacing D40.

**After the second round.** A fresh Claude agent checked the reviewed request list against the full transcripts: 43 of 52 cases complete; the 9 waitlist calls lacked the caller's request for an earlier slot, now added (handled when the agent offers the earliest eligible slots; a "wants an earlier slot" ticket is also correct but counts as a handoff), at the author's choice. Held-out hash now 4423a9632bcd38f06b7945585c8bdf43bb005f5b038345d5a8b921cd303afa46 (D42, proposed). Retrieval answers rerun on the test key for the current questions.
