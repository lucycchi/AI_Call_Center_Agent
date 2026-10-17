# Top 5 issues by impact

## 1. The held-out set is used before the final measurement (C1)

> “Split the templates ... into a working set used for tuning and a held-out set used only for the final measurement” ([SPEC.md:48](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:48))  
> “Run a 10-case held-out rehearsal through the full harness at the end of day 3” ([SPEC.md:60](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:60))

**Problem:** The held-out template split (R9) promises final-only use, but the day-3 rehearsal (R21) consumes ten cases before the final run. Freezing afterward does not restore independence: the author sees failures, logs, grader behavior and harness defects.

**Why it matters:** This compromises the headline containment and accuracy evidence, which the PRD says must be credible and free from leakage.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Should the rehearsal use working-set cases, or are those ten held-out results part of the final measurement with no later rerun?

## 2. One frozen clock cannot run both the simulation and operations (C2)

> “Every date and time calculation uses it, never the server clock.” ([SPEC.md:19](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:19))  
> “Restore the scheduling tables ... at 03:00 Austin time every night” ([SPEC.md:130](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:130))

**Problem:** The fixed date rule conflicts with daily spending limits, rate-limit windows, “today’s” monitoring, latency measurement, alerts and the nightly reset. Those require actual wall or monotonic time; using the fixed instant means days never roll over and 03:00 never arrives.

**Why it matters:** A literal build cannot reset data, expire limits or measure latency correctly.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Is fixed “now” only for customer-facing scheduling and policy calculations, with operational jobs and metrics using real Austin/monotonic time?

## 3. The spec treats blocked and proposed decisions as approved (C3)

> “Builds on: the approved design (`docs/DESIGN.md`) and the decision log” ([SPEC.md:3](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:3))  
> “Claude Haiku 5.5 sorts transcripts and routes messages ... (D25)” ([SPEC.md:25](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:25))

**Problem:** The approved design’s footer says its approval gate remains blocked pending five unconfirmed fixes ([DESIGN.md:484](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:484)). The button/cut-order decision (D24), routing-model decision (D25), handled-reason decision (D26), data-rules decision (D27) and spending-budget decision (D28) are all still marked `proposed`, but the spec turns them into requirements.

**Why it matters:** Engineers will implement owner-unapproved behavior in routing, warranty handling, call scope, budget protection and scheduling.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Has the author approved the five unconfirmed design fixes and the proposed decisions (D24–D28), or must the spec remain blocked?

## 4. The warranty flag can waive fees without evidence and misses valid coverage (R1)

> “sets the warranty-visit flag when the system install date is within 2 years ... or the caller reports a repeat failure of a part repaired within the last year; otherwise the flag is off.” ([SPEC.md:98](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:98))

**Problem:** The database contains no repair history or membership-at-installation history. The current warranty says members at installation receive five years, lists exclusions, and says coverage is determined after diagnosis. The rule therefore:

- trusts an unverifiable caller claim to create a no-diagnostic-fee appointment;
- denies the five-year installation warranty after year two;
- treats installation age as proof that the reported failure is covered.

**Why it matters:** It silently creates wrong fee outcomes while appearing deterministic and correct.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Must warranty eligibility default to staff review unless the database contains evidence, or will historical repair and membership-at-installation data be added?

## 5. The public budget can still be exhausted before the reviewer arrives (R2)

> “the demo breaking because ... the budget was used up” ([SPEC.md:15](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:15))  
> “the site as a whole $10 a day; reaching either limit gives a clean handoff” ([SPEC.md:109](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:109))

**Problem:** Per-visitor limits do not reserve capacity for the reviewer. Multiple sessions or addresses can consume the shared $10, after which the reviewer sees only handoffs. That is the anti-goal verbatim.

**Why it matters:** The first and most important deliverable, the live site, can look broken while all controls operate as specified.

**Classification:** ADDITION. Confidence: 9/10.

**Cost:** Roughly 80–150 lines plus tests; about half a day in the implementation milestone and one hour in deployment. New moving parts: signed reviewer access, a separately reserved counter, secret delivery and expiry.

**If left out:** Any distributed probe can starve the review session.

**Question:** Do you want a reserved reviewer budget/private token, or are you accepting that the global cap can disable the core demo?

# Full findings by pass

## 1. Contradictions

### Held-out rehearsal consumes final-only evidence (C1)

Quotes, impact, classification and question are in the top-five section.

### Fixed simulation time conflicts with operational time (C2)

Quotes, impact, classification and question are in the top-five section.

### Proposed decisions are represented as settled inputs (C3)

Quotes, impact, classification and question are in the top-five section.

### Duplicate-charge calls are both handled and handed off (C4)

> “**Handled:** ... billing questions ... being charged twice” ([SPEC.md:33](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:33))  
> “If the caller questions any charge, the agent hands off as a billing dispute.” ([SPEC.md:92](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:92))

A caller saying they were charged twice is questioning a charge. One engineer will answer the documented pending-authorisation explanation; another will hand off immediately.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Is a duplicate-charge question answered first and handed off only if both charges posted, or is every account-specific duplicate-charge report immediately handed off?

### The consistency run is both first and third in the cut order (C5)

> “Optionally (first to cut), run about 30 held-out cases three times each” ([SPEC.md:62](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:62))  
> “cut in this order ... the suggested-question buttons; the cost-per-conversation breakdown; the consistency runs” ([SPEC.md:161](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:161))

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Is the consistency run the first cut, or does it follow the buttons and cost breakdown?

### The spending alert threshold is fixed and left to the builder (C6)

> “The author is alerted when daily spend passes $5.” ([SPEC.md:109](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:109))  
> “Exact spending-alert threshold ... [is left to the builder].” ([SPEC.md:169](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:169))

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Is $5 mandatory, or may the builder choose the threshold?

## 2. Ambiguity

### Transcript-template equivalence is subjective (A1)

> “calls that share the same request and staff response pattern once names, numbers and filler words are removed” ([SPEC.md:37](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:37))

Two readings:

1. exact normalized-text grouping;
2. semantic grouping of differently worded requests and responses.

The author probably means semantic grouping checked by a human. The choice changes template counts, held-out membership, weights and leakage claims.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What objective rule or adjudication determines whether two transcripts are the same template?

### Failed-case reruns have no scoring rule (A2)

> “re-run every failed case once to separate real failures from simulator noise.” ([SPEC.md:51](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:51))

Two readings:

1. the first failure remains the scored result and the retry is only diagnostic;
2. a passing retry replaces or overrides the failure.

The author probably means the first result remains scored and inconsistent cases are reported separately. Otherwise asymmetric retries inflate results.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Which run enters containment and correctness, and how is fail-then-pass reported?

### “Twenty answers per call” names the wrong kind of call (A3)

> “about 20 answers per call” ([SPEC.md:57](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:57))

Two readings:

1. twenty answers per Codex invocation/batch;
2. twenty answer judgments from each customer conversation.

The author probably means twenty answers per Codex batch, matching the offline-grading decision (D15).

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Does “call” mean a Codex invocation or a simulated customer call?

### Hybrid retrieval has no fusion contract (A4)

> “Retrieve with combined meaning-based search ... and keyword search, returning the top five pieces.” ([SPEC.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:70))

Two readings:

1. merge normalized vector and keyword scores with chosen weights;
2. retrieve two lists and combine them through rank fusion or deduplication.

The author probably means reciprocal-rank fusion or another explicit rank merge. Different choices produce different top-five results and make the threshold in the retrieval-threshold curve (R32) incomparable.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What score normalization, fusion, deduplication and threshold value does combined search expose?

### Router confidence and topic changes have no decision rule (A5)

> “low routing confidence ... goes to a handoff.” ([SPEC.md:83](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:83))  
> “the router sees a clear change of topic” ([SPEC.md:85](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:85))

Two readings:

1. trust an LLM-provided self-confidence field;
2. compute confidence from calibrated route probabilities or an explicit score.

The author probably means a structured router result with a working-set-selected threshold. “Clear change” needs the same treatment.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What router output and threshold define low confidence and a clear topic change?

### Code-enforced reply rules lack enforcement semantics (A6)

> “it never promises a firm repair total, a discount, a refund or a fee waiver, and these rules are enforced in code on every reply.” ([SPEC.md:87](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:87))

Two readings:

1. keyword/regex blocking;
2. structured generation plus a semantic validator or second classifier.

The author probably means structured response types plus narrow prohibited-output checks. Regex alone will miss paraphrases and incorrectly block legitimate descriptions of published member discounts.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What observable validator result blocks a reply, and what happens on a false positive or validator failure?

### Conversation identity and lifetime are undefined (A7)

> “with a conversation identifier” ([SPEC.md:78](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:78))  
> “A visitor is identified by a browser session cookie” ([SPEC.md:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:110))

Two readings:

1. one cookie equals one conversation indefinitely;
2. a cookie identifies a visitor who may own several separately expiring conversations.

The author probably means the second. The spec does not define creation, expiry, restart recovery, concurrent tabs or ownership checks.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What is the visitor-to-conversation mapping and TTL, especially across tabs and server restarts?

### Margin of error does not identify the estimate it belongs to (A8)

> “Report the margin of error computed on distinct held-out scenarios (templates), not on the weighted call count” ([SPEC.md:56](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:56))

Two readings:

1. compute an unweighted binomial interval over templates;
2. compute an interval for the call-count-weighted containment estimate using templates as clusters.

The author probably means the second, but the method is not given. An unweighted interval does not describe the weighted containment reported by the containment calculation (R15).

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Which estimator and confidence level must be used for weighted containment?

### Live containment lost the approved design’s definition (A9)

> “containment labelled as an upper bound and shown only above a minimum number of conversations” ([SPEC.md:121](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:121))

Two readings:

1. every conversation without a handoff is contained;
2. no handoff, no error, no flag and no abandoned active flow, as the approved design stated.

The author probably means the second. The spec also does not define when a conversation is considered finished.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What events close a live conversation, and exactly which closed conversations count toward the upper bound?

## 3. Untestable requirements

### Evaluation metrics lack scoring rubrics (U1)

> “Measure answers: correctness ... faithfulness ... citation accuracy ... and correct refusal” ([SPEC.md:73](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:73))

The success table gives thresholds, but not:

- how claims are segmented for faithfulness;
- whether partially correct answers pass;
- how conflicting grader verdicts are resolved;
- the denominator for citation accuracy;
- whether a refusal that also states unsupported facts passes.

No test can reproduce the percentages from the requirement alone.

**Missing:** scoring rubric, unit of analysis and tie/partial-credit rules.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Is each metric binary per answer, per claim or per conversation, and what exact grader rubric decides it?

### “Error-rate spike” has no threshold or window (U2)

> “alert the author on ... an error-rate spike” ([SPEC.md:128](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:128))

A human cannot verify this without a baseline, window, minimum sample and trigger threshold.

**Missing:** threshold and observable alert timing.

**Classification:** UNCLEAR. Confidence: 10/10.

**Question:** What count/rate over what interval must fire an alert?

### Handoff quality is reduced to field presence (U3)

> “Every handoff creates a ticket with five fields” ([SPEC.md:102](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:102))

Five nonempty fields do not establish the goal that a human can continue without asking the caller to repeat themselves. “What the agent already tried” could be meaningless boilerplate and still pass.

**Missing:** an example or observable sufficiency rubric.

**Classification:** UNCLEAR. Confidence: 8/10.

**Question:** What minimum contents make a ticket sufficient, beyond field presence?

### “Under about” has no pass boundary (U4)

> “Median first checked sentence under about 2.5 seconds; median full reply under about 4 seconds” ([SPEC.md:157](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:157))

**Missing:** an exact threshold, start/end timestamps, warm/cold-run policy and sample size.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Are 2.5 and 4.0 seconds hard limits, and is measurement from server receipt to browser render?

## 4. Gaps in the flow

### Cancelling a members-only booking loses its original restriction (G1)

> “Cancelling frees the slot ...; rescheduling books the new slot and frees the old one” ([SPEC.md:100](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:100))

The supplied schema says freeing means setting the slot to `open`, while a booked row no longer records whether it was formerly `reserved_members`. After cancellation, a non-member can book what was originally a members-only slot.

**Classification:** DEFINITELY WRONG. Confidence: 10/10.

**Question:** Where is the original availability class stored so cancellation and rescheduling can restore `open` versus `reserved_members` correctly?

### A database error cannot always create a handoff (G2)

> “Every model, search or database error becomes a handoff” ([SPEC.md:104](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:104))

If the failing database is the operations database holding tickets, the required handoff cannot be persisted. Retrying through the same path can loop.

**Classification:** DEFINITELY WRONG. Confidence: 9/10.

**Question:** What caller-visible fallback applies when ticket storage itself is unavailable, and where is that failure recorded?

### Post-handoff conversation never reaches the existing ticket (G3)

> “After a handoff, the chat stays open ...; the caller may keep asking other questions” ([SPEC.md:103](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:103))

The ticket is created before later messages, but no step updates or links subsequent context. The human receives an incomplete snapshot despite the “full context” goal.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Does the ticket link the live transcript, append subsequent turns, or intentionally stop collecting context at creation?

### Nightly reset has no concurrency or retry semantics (G4)

> “Restore the scheduling tables ... at 03:00 Austin time every night with a scheduler inside the app” ([SPEC.md:130](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:130))

The flow omits the seed source, transaction boundary, behavior for an active booking, duplicate scheduler execution, process restart during reset and retry after partial failure.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Is reset one idempotent exclusive transaction, and what happens to requests active when it starts?

## 5. Hidden assumptions

### Offline grading assumes interactive Codex access and unused quota (H1)

> “an OpenAI frontier model run through the author's Codex subscription labels templates and grades answers” ([SPEC.md:25](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:25))

This assumes Codex is installed, authenticated, selectable to the intended model, callable in repeatable batches, and has enough remaining plan allowance. OpenAI documents that Codex plan usage varies and can be exhausted; the spec does not say when the API fallback takes over or how identical structured verdicts are produced. [OpenAI Codex plan guidance](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What exact command/output schema runs grading, and what automatically triggers the API fallback?

### “Fixed model version and settings” names neither (H2)

> “with a fixed model version and settings” ([SPEC.md:51](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:51))

The model family names are valid, but the spec does not record concrete API IDs, region/provider, decoding settings or SDK versions. Anthropic publishes concrete active IDs such as `claude-sonnet-5-5` and `claude-haiku-5-5`; reproducibility requires the IDs actually sent and the returned version metadata. [Anthropic model-status table](https://platform.claude.com/docs/en/about-claude/model-deprecations)

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Which exact API IDs, SDK versions and request parameters are frozen for each role?

### The in-app scheduler assumes a singleton healthy process (H3)

> “with a scheduler inside the app” ([SPEC.md:130](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:130))

This assumes exactly one scheduler survives deploys and restarts. Multiple web workers can run it twice; an unhealthy app cannot run or report its own missed reset. Fly’s deployment guidance treats schedulers as singleton process groups. [Fly.io scheduled-task guidance](https://fly.io/django/)

**Classification:** UNCLEAR. Confidence: 8/10.

**Question:** Is the scheduler a dedicated singleton process, a web-process background task or an external scheduled machine?

### Cookie and network-address limiting assumes trusted proxy behavior (H4)

> “A visitor is identified by a browser session cookie, with the network address as a backstop.” ([SPEC.md:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:110))

The requirement assumes signed cookies, secure flags, trusted proxy headers and a defined policy for shared NATs and IPv6 rotation. Different implementations either let visitors forge/bypass limits or block unrelated reviewers.

**Classification:** UNCLEAR. Confidence: 8/10.

**Question:** Which address supplied by Fly is trusted, and what signing, expiry and cookie flags are mandatory?

## 6. Traceability

### The known log-retention and privacy gap remains unresolved (T1)

> “Log every conversation ... in a separate operations database ...; phone numbers and emails are masked in logs.” ([SPEC.md:127](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:127))

The personal-data gap (F26) in the PRD review called out retention and deletion. The spec masks only phone numbers and email, leaving names, addresses, account numbers, invoice details and full conversation text indefinitely. It also leaves the database unbounded.

**Classification:** ADDITION. Confidence: 10/10.

**Cost:** About 100–200 lines including migration and tests; roughly half to one day in implementation and one hour in deployment. New moving parts: retention timestamp, purge job, configurable TTL, masking policy and access tests.

**If left out:** Sensitive account context persists indefinitely and the operations disk can eventually fill.

**Question:** What fields must be masked, who may see raw text, and what retention/deletion period applies?

### A PM-only scheduling-scope question is silently treated as closed (T2)

> “Never cut: ... confirming, cancelling and rescheduling” ([SPEC.md:163](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:163))

The PRD review still says only the PM can confirm whether the schema’s reschedule/cancel/confirm behavior exceeds the PRD’s simpler booking bar ([PRD_REVIEW.md:293](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD_REVIEW.md:293)). The spec’s open-question list omits it.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** Did the author’s scheduling-scope decision (D13) explicitly supersede that PM question?

### Warranty automation is extra PRD scope based on an unapproved decision (T3)

> “**Handled:** ... warranty questions and claims” ([SPEC.md:33](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:33))

The PRD asks for the top three drivers plus scheduling; warranty is fourth. The handled-reason decision (D26) adds it but remains proposed. This is not inherently bad scope, but it has no approved trace to the PRD and introduces the broken fee logic in the warranty-visit flag (R53).

**Classification:** UNCLEAR. Confidence: 10/10.

**Question:** Is warranty formally approved core scope, or should it remain a documented follow-up until the warranty data problem is solved?

### The PRD review’s rollback requirement is dropped (T4)

> “Deploy to Fly.io on one always-on machine” ([SPEC.md:131](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:131))

The rollback/versioning gap (F30) from the PRD review is not addressed. Forward deployment is specified, but not reverting a bad prompt, document index, code release or database reset.

**Classification:** ADDITION. Confidence: 8/10.

**Cost:** Roughly 30–80 lines/configuration; two to four hours during implementation and about one hour for a deployment rehearsal. New moving parts: release identifier, prompt/index version, seed backup and rollback runbook.

**If left out:** A bad deployment or index rebuild can leave the public demo unusable with no bounded recovery path.

**Question:** Is Fly release rollback plus a versioned database/index snapshot required, or is manual rebuild accepted?

## 7. Risk

### Warranty status can silently create wrong fees (R1)

Quotes, impact, classification and question are in the top-five section.

### Public traffic can starve the reviewer budget (R2)

Quotes, cost, impact and question are in the top-five section.

### The internal-document leak check only catches an undefined form of verbatim copying (R3)

> “every reply is checked in code for verbatim text from internal documents” ([SPEC.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:88))

A whole-document comparison catches nothing; short n-grams generate false positives; paraphrased internal instructions bypass either. Sentence-by-sentence release also misses text split across sentence boundaries.

**Classification:** UNCLEAR. Confidence: 9/10.

**Question:** What minimum span, normalization and cross-sentence rule constitutes a match, and is paraphrased instruction disclosure also forbidden?

### Shared-password protection is underspecified for the highest-value data view (R4)

> “The full all-visitors queue and the flag-a-reply control sit behind a shared password” ([SPEC.md:123](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:123))

There is no password storage rule, session expiry, attempt limit, CSRF protection or delivery mechanism to the reviewer. A guessed or leaked password exposes every visitor’s transcript and permits feedback tampering.

**Classification:** UNCLEAR. Confidence: 8/10.

**Question:** What authentication/session controls protect the all-visitors queue, and how is the credential delivered without committing it?

### Fixed safety patterns can fail silently on paraphrase and negation (R5)

> “checked in code against fixed lists of words and patterns in three safety classes” ([SPEC.md:79](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:79))

A literal matcher may miss transcription errors and paraphrases or falsely trigger on “I do not smell gas.” Because it runs before routing and always wins, both false negatives and false positives look intentional.

**Classification:** UNCLEAR. Confidence: 8/10.

**Question:** What normalization, negation handling and adversarial variants must the deterministic safety matcher cover?

# Clarifying questions, ordered by build impact

1. Are the blocked design fixes and proposed decisions covering buttons/cut order (D24), routing (D25), handled reasons (D26), data rules (D27) and spending (D28) now owner-approved?
2. Must the day-3 rehearsal (R21) use working-set cases, or does it become part of the single final held-out result?
3. Is fixed “now” limited to customer-facing business rules, with real wall/monotonic time used for operations?
4. What evidence is required before setting the warranty-visit flag (R53), especially for five-year member coverage and repeat repairs?
5. Will the reviewer receive reserved budget capacity, or is shared-cap starvation accepted?
6. How is the original `open` versus `reserved_members` state restored after cancellation or rescheduling?
7. Are duplicate-charge questions answered from the FAQ before escalation, or immediately treated as disputes?
8. Which run counts when a failed evaluation case is retried, and which confidence-interval method applies to weighted containment?
9. What exact rubrics compute correctness, faithfulness, citation accuracy and refusal?
10. What are the conversation lifecycle, ownership and TTL across tabs and restarts?
11. Does an existing handoff ticket receive subsequent conversation turns?
12. What retrieval-fusion and router-confidence algorithms are required?
13. What exact fallback is shown when ticket storage or the reset process fails?
14. What retention, masking and access rules apply to operations data?
15. What authentication controls protect the all-visitors staff view?
16. Did the author’s scheduling-scope decision (D13) supersede the remaining PM question?
17. Is warranty formally approved as a fourth handled driver?
18. What rollback guarantee is required for code, prompts, indexes and scheduling data?
19. Which cut order and spending-alert threshold are authoritative?
## Rulings

Recorded 2026-10-17. The author accepted every recommendation below; all are applied to `docs/SPEC.md`, and the design (`docs/DESIGN.md`) is brought in line.

**Real problems: fixed.**

| Finding | Ruling |
|---|---|
| Held-out rehearsal consumes final-only evidence (C1) | Rehearsal uses working-set cases (R21); recorded in test-set construction with the working-set rehearsal (D32), replacing (D20). |
| Fixed simulation time conflicts with operational time (C2) | Fixed "now" applies only to customer-facing scheduling and policy rules; operations use real time (section 2; data rules (D29)). |
| Proposed decisions represented as settled (C3) | The design records the author's acceptance of the deferred fixes; the open decisions are settled by the author at spec approval. |
| Warranty flag waives fees without evidence (R1) | Flag only on database install-date evidence; other claims booked as normal visits with a staff warranty-review note (R53; D29). |
| Cancelling a members-only booking loses its restriction (G1) | Freed slots return to their seeded status (R55; D29). |
| Duplicate-charge calls both handled and handed off (C4) | FAQ explanation first, handoff only if both charges posted (R81; D29). |
| Consistency run listed first and third in the cut order (C5) | Third in the cut order (R23). |
| Alert threshold both fixed and left to the builder (C6) | $5 is fixed (R61, R74). |
| Database error cannot always create a handoff (G2) | Plain "please phone" message, server log and alert when the operations database fails (R59). |
| Post-handoff turns never reach the ticket (G3) | Later messages are added to the open ticket (R58). |

**Wording settled (Claude's calls, accepted by the author).**

| Finding | Ruling |
|---|---|
| Template equivalence is subjective (A1) | Automatic normalised-text grouping plus a reviewed, committed merge list (R1). |
| Failed-case reruns have no scoring rule (A2) | First run is scored; fail-then-pass reported as flaky (R12). |
| "Twenty answers per call" (A3) | Per Codex run (R18). |
| Hybrid retrieval has no fusion contract (A4) | Reciprocal-rank fusion; threshold on the top piece's meaning-based score (R28). |
| Router confidence and topic changes undefined (A5) | Route plus "clear" or "unclear", tuned on the working set; topic change is a clear different route (R38, R40). |
| Code-enforced reply rules lack semantics (A6) | Structured reply types with narrow checks; blocks become handoffs and are counted (R42). |
| Conversation identity and lifetime undefined (A7) | One conversation per tab, stored to survive restarts, closed after 30 minutes idle (R82). |
| Margin of error estimator unspecified (A8) | 95 percent interval by resampling held-out templates (R17). |
| Live containment lost its definition (A9) | Closed conversations with no handoff, error, flag or abandoned flow, labelled an upper bound (R70). |
| Evaluation metrics lack rubrics (U1) | Pass or fail per answer with written rubrics; partly correct fails (R31). |
| "Error-rate spike" undefined (U2) | 3 or more errors in 10 minutes, or over 20 percent of at least 10 messages (R74). |
| Handoff quality reduced to field presence (U3) | Ticket quality graded with a rubric (R57). |
| "Under about" has no boundary (U4) | Hard limits of 2.5 and 4.0 seconds from server receipt, warm runs, at least 50 messages (section 4, R60). |
| Nightly reset concurrency and retries (G4) and singleton scheduler (H3) | One exclusive transaction from the seed file, locked, run at startup if missed, retried once, then alert (R76). |
| Codex grading command and fallback (H1) | Fixed `codex exec` command with JSON verdicts; API fallback switched on by hand (R18). |
| Model versions and settings unnamed (H2) | Model IDs, SDK version and request settings pinned and logged (section 2). |
| Cookie and address trust (H4) | Signed HttpOnly Secure cookie, SameSite=Lax, 7 days; Fly.io client address as backstop (R62). |
| Internal-text check undefined (R3) | 8 or more consecutive normalised words, checked across the whole reply (R43). |
| Shared-password controls (R4) | Hashed in a Fly.io secret, 12-hour sessions, 5 attempts per 15 minutes, forged-request protection (R72). |
| Safety matcher paraphrase and negation (R5) | Normalisation, speech-to-text variants, plain negation handling, errs toward safety (R34). |
| PM scheduling-scope question silently closed (T2) | Settled by the decision to include rescheduling, cancelling and confirming (D13); noted in the spec and PRD review. |
| Warranty automation rests on an unapproved decision (T3) | Approved when the author settles the handled-reason list (D26); fee logic fixed per (R1) above. |

**Additions: accepted with their cost.**

| Finding | Ruling |
|---|---|
| Public budget can still be exhausted (R2) | Secret reviewer link with its own $3-a-day reserve, about 2 to 3 hours (R61; spending budgets with a reviewer reserve (D30), replacing (D28)). |
| Log retention and privacy (T1) | 30-day log purge; phone, email and street address masked; about 2 to 3 hours, cuttable (R72, R73; retention, masking and rollback (D31)). |
| Rollback requirement dropped (T4) | One-page rollback runbook, practised once; about 1 hour (R83; D31). |
