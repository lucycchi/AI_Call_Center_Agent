I found several build-blocking contract errors. Most importantly, the final run cannot pass its own freeze check, booking idempotency is not safe across the two databases, and the evaluation pipeline cannot produce many of the metrics the Results tab requires.

## Top five issues

- **Frozen tag rejects the completed application (F1)** — Rank 1  
  > “Produces: `run_final()` refusing to start if the held-out hash differs from `data/split.json` or the code differs from the `agent-frozen` tag.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:591))  
  > “...run the 10-case working-set rehearsal at the end of day 3, and freeze the agent (tag `agent-frozen`).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:442))

  Tasks 20–25 change application code after the tag is created. A repository-wide comparison against `agent-frozen` therefore rejects the intended final build.  
  Why it matters: the final held-out run and final summary cannot execute as written.  
  Classification: **DEFINITELY WRONG**.  
  Question: Which explicit files constitute the frozen “agent”—core prompts, thresholds, retrieval artifacts and flows—or should the tag move until after deployment code is complete?

- **Booking idempotency is split across non-atomic databases (F2)** — Rank 2  
  > “Consumes: `eligible_slots` (Task 10), ops store `confirmations` (Task 13, a fake in these tests).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:258))  
  > “Calling `book` twice with the same confirmation id returns the same appointment id and leaves one appointment row (R84).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:265))  
  > “When a booking commits but logging fails, the caller still receives the confirmation...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:373))

  The appointment commits in the scheduling SQLite file, while the idempotency result lives in the operations SQLite file. If the first commits and `save_confirmation` fails, a retry has no durable result to return. The sequential fake-store test cannot expose this failure window.  
  Why it matters: a repeated “yes” can create a duplicate appointment or return an inconsistent result, breaking confirmation idempotency (R84) and the 100% booking-correctness target.  
  Classification: **DEFINITELY WRONG**.  
  Question: Is the scheduling database meant to store the confirmation ID with the appointment, or is there an explicit recovery/reconciliation protocol for a scheduling commit followed by an operations-store failure?

- **The final metrics have no complete producer (F3)** — Rank 3  
  > “Produces: `... Summary(containment, containment_without_redirects, scope_ceiling, adjusted_ceiling, wrong_confident, interval_low, interval_high, scenarios, weighted_calls)`.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:395))  
  > “The adversarial folder has at least 30 cases...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:424))  
  > “It shows ... handoff, booking and lookup correctness, retrieval and answer measures, the adversarial pass rate, grader agreement, label agreement...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:532))

  The scoring summary omits routing accuracy, handoff correctness and quality, booking correctness, lookup correctness, knowledge measures, adversarial pass rate and both agreement tables. Task 18 creates adversarial files but never runs or scores them. Task 23 merely renders fields.  
  Why it matters: final evaluation results (R67), adversarial reporting (R20), answer measures (R31) and handoff-quality grading (R57) can be absent or fabricated while all listed tests pass.  
  Classification: **DEFINITELY WRONG**.  
  Question: Which task owns executing and aggregating each required metric into the final summary schema?

- **The Fly machine-count test checks an impossible configuration property (F4)** — Rank 4  
  > “`fly.toml` declares one machine that never auto-stops...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:570))

  Current Fly configuration separates application configuration from VM count; count is managed through `fly scale count`, not a machine-count declaration in `fly.toml`. The official CLI describes `fly scale count` as the operation that changes VM count, while the configuration reference covers mounts, services and VM size, not desired count. [Fly scale-count documentation](https://fly.io/docs/flyctl/scale-count/), [Fly configuration reference](https://fly.io/docs/reference/configuration/).  
  Why it matters: the test either cannot be implemented honestly or passes by checking a made-up field. Accidentally deploying two machines breaks the architecture’s single-worker lock, scheduler and single-disk assumptions.  
  Classification: **DEFINITELY WRONG**.  
  Question: Should `scripts/deploy.sh` enforce one machine and verify it through `fly status`/the Machines API after deployment?

- **The engine stream cannot carry its required result metadata (F5)** — Rank 5  
  > “`Engine.handle(turn: Turn) -> Iterator[str]` yielding checked sentences...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:57))  
  > “`GET /api/stream/{message_id}` (server-sent events of checked sentences, then a `done` event with route, ticket and proof receipt).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:464))

  An iterator of strings has no defined way to return the final route, ticket, receipt, outcome or database actions. Although `Reply` is declared, `Engine.handle` neither returns nor yields it.  
  Why it matters: the web layer, receipts, evaluation harness and logging will invent incompatible side channels or require interface rework after Task 1.  
  Classification: **DEFINITELY WRONG**.  
  Question: Is the stream meant to yield typed sentence and completion events, or should `Engine.handle` return a result object containing both the stream and eventual metadata?

# Full findings by pass

## 1. Tests against requirements

### Task-by-task coverage ledger

| Task | Assessment |
|---|---|
| Project setup and core interface (T1) | Partial: result metadata has no contract—engine metadata (F5). |
| Template grouping (T2) | Partial: the tests do not prove grouping uses both request and staff-response patterns—template grouping false assurance (F6). |
| Call-reason labeling (T3) | Partial: independence, complete coverage and agreement artifacts are not asserted—discovery evidence incomplete (F7). |
| Findings document (T4) | Partial: required columns, methodology, agreement and exact executive findings can be absent—discovery evidence incomplete (F7). |
| Document conversion/register (T5) | Partial: only two conflicts are asserted—conflict-register completeness (F8). |
| Search index (T6) | Inadequate for meaning-based search and top-five semantics—semantic retrieval untested (F9). |
| Frozen cases (T7) | Partial: per-reason population reporting and evidence review are not proven—split publication incomplete (F10). |
| Retrieval evaluation (T8) | Incomplete: the whole-KB answer comparison is deferred without a later completion task—benchmark never completed (F11). |
| Account flows (T9) | Helper results are tested, but required conversational outcomes are not—flow tests stop at helpers (F12). |
| Slot eligibility (T10) | Missing served-but-handoff behavior for Manor and Dripping Springs—flow tests stop at helpers (F12). |
| Scheduling transactions (T11) | Missing read-back confirmation behavior, multiple-appointment selection and two operations’ idempotency; also cross-database failure—idempotency split (F2), flow tests stop at helpers (F12). |
| Safety (T12) | Main classification works, but several fixed-reply and urgent-class requirements are unasserted—flow tests stop at helpers (F12). |
| Operations store (T13) | Schema existence can pass with no actual operational logging—logging not proven (F13). |
| Engine pipeline (T14) | Good safety precedence tests, but several routing rules and result metadata remain unproved—engine metadata (F5), future dependencies (F28). |
| Knowledge/reply flow (T15) | Core safety checks are useful, but required latency and source behavior are incomplete—latency target unmeasured (F14). |
| Handoff flow (T16) | Basic behavior is checked; ticket actionability and booking/log failure recovery are not—idempotency split (F2), flow tests stop at helpers (F12). |
| Evaluation harness (T17) | Required metrics are absent and the interval test is degenerate—missing metric producers (F3), bootstrap test false assurance (F15). |
| Grader/adversarial set (T18) | Cases are counted but not executed; verdict publication and agreement output are unproved—adversarial evaluation unrun (F16). |
| Rehearsal/quick run (T19) | Threshold arithmetic is sound; quick-run success is undefined—quick run has no oracle (F17). |
| Chat/API (T20) | Missing daily/site rate limits, IP backstop, greeting facts and handoff receipt—public guard coverage incomplete (F18). |
| Spending/reviewer link (T21) | Missing test-run budget separation and one-use token behavior—budget and reviewer safeguards incomplete (F19). |
| Staff view (T22) | Missing most live numbers, receipt fields and correction-note persistence—staff evidence incomplete (F20). |
| Results tab (T23) | Presentation tests are comprehensive, but producers are absent—missing metric producers (F3). |
| Operations jobs (T24) | Missing double-run prevention, failed-write alert and verifiable external monitoring—operations guarantees incomplete (F21). |
| Fly deployment (T25) | Machine-count test is invalid; rollback location and cut order conflict—Fly count (F4), deployment contradictions (F22). |
| Final run (T26) | Freeze condition rejects the completed repo—frozen tag (F1). |
| Repository deliverables (T27) | Does not require verdict files and scans only two classes of key—deliverable audit incomplete (F23). |

### Template grouping can pass without the staff-response half (F6)

> “Two calls whose first caller lines differ only by names and numbers ... get the same template id.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:75))

The shared-request test never supplies differing staff responses. A grouping implementation based only on the first caller line passes even though template grouping (R1) requires the same request **and staff response pattern**.  
Classification: **DEFINITELY WRONG**.

### Discovery artifacts are only checked superficially (F7)

> “With a fake Haiku client returning ... `label_with_haiku` stores that pair.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:91))  
> “The findings document contains the headings ...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:107))

These tests do not prove independent Codex labeling of every template (R3), report both required agreement rates (R4), produce the top four or five table with all columns and method (R5), or emit the three specific executive findings (R8). Headings and two small helper fixtures can pass with a materially incomplete document.  
Classification: **DEFINITELY WRONG**.

### Conflict-register completeness is not tested (F8)

> “The conflict register has a row for the service area ... and for the diagnostic fee...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:122))

Every document conflict must be recorded under conflict register completeness (R25). Checking two known rows permits all other conflicts to be omitted.  
Classification: **DEFINITELY WRONG**.

### Meaning-based retrieval can be absent (F9)

> “With a fake embedder, a keyword search for ‘diagnostic fee’ puts the Fees chunk first.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:146))

No test invokes `mode="meaning"`, verifies cosine ordering, confirms combined mode uses both rankings, limits results to five, or checks that the threshold uses the leading meaning score. Meaning-plus-keyword retrieval (R28) can therefore be implemented as keyword-only and pass.  
Classification: **DEFINITELY WRONG**.

### Split publication and reference review are not proven (F10)

> “No template id appears in both `working` and `held_out`. Every call reason with at least two templates appears in both sets.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:174))

The split test does not assert the published calls and template counts per reason for corpus, working set and held-out set required by split reporting (R9). Nor does it verify that expected outcomes and reference answers were frozen before tuning rather than merely present when the test ran.  
Classification: **DEFINITELY WRONG**.

### The whole-knowledge-base benchmark is never completed (F11)

> “...graded by the grader in Task 18; until then the comparison records answers only.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:192))

Task 18 has no step that returns to this output and grades it. Retrieval comparison (R30) therefore stops with unscored answers even though Milestone 2 promises comparison numbers.  
Classification: **DEFINITELY WRONG**.

### Flow tests stop at helper functions (F12)

> “`is_action_request` is True for ‘send me a payment link’ ...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:224))  
> “`zone_for("Manor") is None`.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:239))  
> “Calling `book` twice with the same confirmation id...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:265))  
> “`fixed_reply("danger")` contains ‘leave your home’...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:289))

These can pass while the application still fails to:

- hand off after two identity failures or for a new customer—caller identification (R45);
- silently create the low-priority fee-mismatch ticket—invoice mismatch handling (R47);
- create an action-gap handoff—money/membership actions (R48);
- tell Manor and Dripping Springs callers they are served and then hand off—service-area decline (R51);
- read back and wait for a clear yes—booking confirmation (R52);
- tell a repeat-repair caller that the diagnostic fee is conditional—warranty review (R53);
- ask which appointment when several exist—appointment selection (R54);
- apply confirmation idempotency to cancellation and rescheduling—confirmation idempotency (R84);
- cover no-heat/no-cooling urgent cases or all mandatory fixed-reply instructions—safety replies (R35–R37).

Classification: **DEFINITELY WRONG**.

### Schema existence can pass with no logging (F13)

> “Every table in the architecture's operations diagrams exists after `OpsStore` opens a new file...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:308))

No test runs a conversation and asserts that its messages, replies, route, retrieval, database actions, handoff, timing, model cost and errors were recorded and masked. No-op logging methods can pass the operations logging requirement (R73).  
Classification: **DEFINITELY WRONG**.

### The live latency target is not measured (F14)

> “Each released sentence is yielded within the budget of 2.5 seconds ... using a fake writer that takes 1 second.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:353))

The 2.5-second budget applies to the **first** checked sentence, not every later sentence. More importantly, the success target requires median first sentence below 2.5 seconds and median full reply below 4 seconds over at least 50 warm live messages. A one-second fake proves neither.  
Classification: **DEFINITELY WRONG**.

### The bootstrap test accepts a constant implementation (F15)

> “...for 20 scenarios all contained it is `(1.0, 1.0)`.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:403))

Any implementation returning `(1, 1)` passes. The test does not prove template-level resampling, call weighting, seed 7, 2,000 resamples or 95% quantiles required by containment interval reporting (R17).  
Classification: **DEFINITELY WRONG**.

### Adversarial and grader outputs are created, not evaluated (F16)

> “The adversarial folder has at least 30 cases ... and each case has an expected pass condition.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:424))

There is no execution test, pass-rate calculation, booking-rule/instruction-extraction 100% check, fixed Codex command check, committed-verdict check or full agree/disagree table check. Adversarial reporting (R20), answer measures (R31), verdict retention (R18) and grader agreement (R19) can all remain unmet.  
Classification: **DEFINITELY WRONG**.

### Quick run has no oracle (F17)

> “Produces: ... `quick_run(n=20) -> bool`.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:438))  
> “`quick_run` refuses to run on held-out cases.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:440))

Nothing says which correctness or safety conditions make the result `False`.  
Classification: **UNCLEAR**. The two likely readings are:

- it is only an infrastructure smoke test, in which case `True` after any completed run satisfies it; or
- it is a deployment gate, in which case safety, booking and answer pass criteria must be defined.

### Public-site guard coverage is incomplete (F18)

> “The 21st message within 10 minutes from one visitor gets a plain handoff message...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:469))

The test omits 100 messages/day per visitor, 60/minute site-wide and the Fly-supplied client-address backstop from rate limits (R62). It also checks no greeting/capability text or one fact per customer card under chat presentation (R64), and only a booking receipt—not a handoff receipt—under proof receipts (R66).  
Classification: **DEFINITELY WRONG**.

### Budget separation and one-use reviewer behavior are untested (F19)

> “`GET /r/<correct token>` sets a reviewer session and redirects to `/`...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:493))

The same token is never requested twice, so it can remain reusable despite one-use reviewer links (R85). There is also no assertion that test evaluation uses a separate key and budget, as spending isolation (R61) requires.  
Classification: **DEFINITELY WRONG**.

### Staff evidence and feedback fields are incomplete (F20)

> “Receipts show ‘supported by documents’, ‘not enough evidence’ or ‘handoff required’...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:512))  
> “`pipeline.export_flags` writes each flagged conversation as a candidate test case file.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:515))

The tests omit conversations, handoffs, errors, median reply time, upper-bound labeling and the new-ticket badge from staff metrics (R70); safety decision, route, dated passages, stale exclusions, database action and handoff reason from receipts (R71); and correction-note persistence/export from feedback (R75).  
Classification: **DEFINITELY WRONG**.

### Operational guarantees can pass while absent (F21)

> “A message that starts while the reset holds the gate waits...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:551))  
> “A reset that fails twice records `failed` and sends one alert.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:553))

Nothing tests two concurrent scheduler invocations, the actual 03:00 schedule, a failed database-write alert, dashboard visibility of a failed reset, or that the external uptime monitor really calls the health endpoint. These are explicit operations requirements (R74, R76, R86).  
Classification: **DEFINITELY WRONG**.

### Deliverable checks miss verdicts and most secrets (F23)

> “The repository contains ... `eval/grader_prompt.md`, `data/results/final/`. No file outside `.env` matches an Anthropic or OpenAI key pattern.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:604))

Repository contents (R80) also require grading verdicts, which are not asserted. The secret scan ignores Voyage keys, reviewer tokens, session secrets, webhook credentials, staff credentials and Fly tokens.  
Classification: **DEFINITELY WRONG**.

## 2. Contradictions

### Rollback is put outside the README (F22)

> “Create: ... `docs/ROLLBACK.md` (linked from the README) ...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:565))

The rollback runbook requirement (R83), retention and rollback decision (D31), and architecture all say the one-page runbook is **in the README**, not merely linked from it.  
Classification: **DEFINITELY WRONG**.

### Mandatory deploy gate conflicts with the approved cut order (F24)

> “`scripts/deploy.sh` runs `python -m eval.quick_run` before `fly deploy` and stops if it fails.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:570))

The approved cut order explicitly permits removing the pre-deploy quick test run (R22). As written, cutting it makes deployment fail even though deployment is never-cut.  
Classification: **DEFINITELY WRONG**.

### Handoff package disagrees with the architecture (F25)

> “Create: `app/flows/handoff.py`...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:362))

The architecture assigns ticket behavior to `app/handoff/`, while the plan puts it in `app/flows/`. This is small but will produce either duplicate ownership or architecture drift.  
Classification: **DEFINITELY WRONG**.

### The shipped index omits the specified keyword artifact (F26)

> “Output: `data/index/chunks.jsonl`, `data/index/embeddings.npy`.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:140))

The architecture says the shipped index contains embeddings **plus a keyword index**.  
Classification: **UNCLEAR**. The two likely readings are:

- BM25 is rebuilt from `chunks.jsonl` at every process start; or
- a serialized keyword index is intended but missing from the plan’s outputs and Docker checks.

## 3. Order

### Frozen tag occurs before later application work (F1)

> “...freeze the agent (tag `agent-frozen`).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:442))

Tasks 20–25 subsequently change the engine’s integration, limits, staff data, jobs and deployment. See frozen tag rejects completed code (F1).  
Classification: **DEFINITELY WRONG**.

### Retrieval evaluation depends on a later grader with no revisit (F11)

> “...graded by the grader in Task 18; until then the comparison records answers only.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:192))

Task 8 cannot meet its promised output when built, and Task 18 does not finish it.  
Classification: **DEFINITELY WRONG**.

### Scheduling consumes the later operations store (F27)

> “Consumes: ... ops store `confirmations` (Task 13, a fake in these tests).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:258))

Classification: **UNCLEAR**. The two likely readings are:

- Task 11 defines a stable confirmation-store protocol and Task 13 later implements it; or
- Task 11 only works with a test fake and must be redesigned when the real store arrives.

The protocol must be explicit because its failure semantics determine confirmation idempotency (R84).

### The engine is built before two flows it consumes (F28)

> “Consumes: safety (Task 12), ops store (Task 13), flows (Tasks 9 to 11, 15, 16).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:321))

Task 14 precedes knowledge flow (T15) and handoff flow (T16).  
Classification: **UNCLEAR**. The two likely readings are:

- Task 14 uses explicit fake protocols and Tasks 15–16 conform to those contracts; or
- the engine uses provisional assumptions and is reworked later.

No flow protocols are declared in Task 14, making the second reading likely.

### Human labeling can stall Milestone 1 (F29)

> “...when the author returns it, `pipeline.agreement` reports author-versus-Codex and Codex-versus-Haiku agreement.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:93))

Task 4 consumes the labels and must report agreement, but the plan gives no provisional artifact or explicit pause point.  
Classification: **UNCLEAR**. The two likely readings are:

- Milestone 1 blocks until the author returns the sheet; or
- findings are generated provisionally and regenerated after the sheet returns.

All milestones otherwise end in something observable; no additional milestone-end finding was found.

## 4. Expected values

No incorrect arithmetic, database value, date, unit or ordering expectation was found. The problematic examples are under-specified or degenerate, not numerically wrong.

Checked calculations:

- Configuration date (T1): Austin was UTC−05:00 on 2026-10-16, so `2026-10-16T09:00:00-05:00` is correct.
- Corpus size (T2): 420 transcript files after ignoring `:Zone.Identifier` twins is correct.
- Agreement (T3): one match out of two labels is \(1/2=0.5\).
- Reason ranking (T4): two booking calls out of three gives \(2/3=0.666\ldots\), rounded to `0.667`; booking duration \(120+60=180\) seconds \(=3.0\) minutes.
- Live baseline checks (T4): \(355/420=84.52\%\), about 85%; \(308/420=73.33\%\), about 73%; \(108/420=25.71\%\), about 26%. The 11 dropped bookings also matches the data review.
- RRF ordering (T6), constant 60:

  - `a`: \(1/61+1/63=0.032266\)
  - `b`: \(1/62+1/61=0.032522\)
  - `c`: \(1/63+1/62=0.032002\)

  Therefore `b` sorts first, as expected.

- Retrieval values (T8): one of two spans gives recall `0.5`; two answerable questions of three gives \(2/3=0.666\ldots\), rounded to `0.667`.
- Account data (T9): Linda’s account, phone, address and membership values; Omar’s 47,800-cent balance and three line items; Grace’s Lennox/install date all match the SQLite database.
- Date parsing (T10), from Friday 2026-10-16 09:00:

  - tomorrow morning → Saturday 2026-10-17;
  - this Saturday → 2026-10-17;
  - next Tuesday → 2026-10-20;
  - the requested Tuesday evening window is `16:00-19:00`.

  Slot 56 is the earliest eligible north-zone HVAC repair slot for Monday morning.

- Warranty and fees (T11): Linda’s 2023-05-14 installation is more than two years old, so flag 0; Grace and Daniel are under two years, so flag 1. A 13:00 same-day appointment is four hours away, so the $49 fee is 4,900 cents.
- Weighted containment (T17): \(10/(10+30)=0.25\).
- All-contained interval (T17): every resample of twenty all-contained scenarios is 1, so `(1.0, 1.0)` is mathematically correct, though it does not test the algorithm.
- Threshold selection (T19): among zero-wrong points, threshold 0.4 has containment 0.65 versus 0.55 at 0.6, so 0.4 is correct.
- Limits/budgets (T20–T21): the 21st message exceeds the 20-per-10-minute limit; 2,500 characters truncates to 2,000; $0.39 is below the approximately $0.40 limit and $0.41 is above it; site and alert values of $10 and $5 match the specification.
- Staff login (T22): five failed attempts are allowed; the sixth is the refused attempt. Twelve-hour session duration matches the requirement.
- Operations (T24): 31 days is older than a 30-day retention window; 3 errors in 12 messages is \(3/12=25\%\), above 20%; two errors remain below the count threshold of three.
- Consistency option (T26): 30 cases × 3 runs = 90 conversations.

## 5. Feasibility

### Fly machine count is not a `fly.toml` property (F4)

> “`fly.toml` declares one machine...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:570))

See Fly machine-count test (F4).  
Classification: **DEFINITELY WRONG**.

### Engine output cannot satisfy web and evaluation consumers (F5)

> “`Engine.handle(turn: Turn) -> Iterator[str]`...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:57))

See engine result metadata (F5).  
Classification: **DEFINITELY WRONG**.

### POST/SSE persistence contract is missing (F30)

> “`POST /api/message` ... returning 202; `GET /api/stream/{message_id}`...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:464))

A 202 response means processing outlives the POST, but no job state, replay buffer, ownership lookup or behavior for “stream connects before/after completion” is specified. Reloaded histories add another persistence consumer.  
Classification: **UNCLEAR**. The two likely readings are:

- the POST creates a persisted message/reply job and the SSE endpoint replays stored events; or
- an in-memory task/queue owns the stream, losing work and metadata on restart.

### Several tasks are too large for their stated single red-green cycle (F31)

> “Write the failing tests with FastAPI's test client and a fake engine...” followed by cookie, ownership, limiting, idempotency, UI, receipt, language and reload behavior. ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:466))

Chat/API (T20), Staff view (T22) and operations jobs (T24) each combine multiple independent components behind one “write all tests, then implement” cycle. Failures will not identify a narrow responsible unit, and Task 20 cannot be made green until API persistence, cookies, rate limiting, JavaScript and conversation state all exist.  
Classification: **UNCLEAR**. The two likely readings are:

- each bullet is intended as its own internal test-first subcycle; or
- the task truly requires one monolithic failing suite and implementation phase.

### Outside uptime monitoring is not buildable from the task (F32)

> “Set up a free outside uptime monitor on `/health` once the site is live (R86).” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:558))

No service, configuration artifact, alert destination, interval, credential handling or acceptance check is given. Unlike the webhook alerts, this cannot be reproduced from the repository.  
Classification: **DEFINITELY WRONG**.

I did not find a model/API feasibility error: current Anthropic documentation lists the planned model IDs, and its Sonnet migration documentation supports `output_config={"effort": ...}`. [Anthropic models](https://platform.claude.com/docs/en/models/overview), [Sonnet migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide).

## 6. Risks

### Paid evaluation has no hard stop or separate budget enforcement (F33)

> “The simulator is Sonnet 5.5 ... ending the call when its goal is met or refused; every conversation is saved.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:406))  
> “...run the final held-out set once...” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:595))

There is no maximum turns, tokens, wall time, retry count, per-run cost or hard evaluation budget. “Goal met or refused” is model-determined and can loop. The plan also omits enforcement of the separate test key/budget required by spending isolation (R61). Anthropic documents `max_tokens` as the strict output-spend ceiling; effort is only a soft control. [Anthropic thinking controls](https://platform.claude.com/docs/en/build-with-claude/thinking).  
Classification: **DEFINITELY WRONG**.

### Secret scanning gives false assurance (F23)

> “No file outside `.env` matches an Anthropic or OpenAI key pattern.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:604))

Voyage, reviewer, session, staff, webhook and Fly secrets can be committed while the test stays green.  
Classification: **DEFINITELY WRONG**.

### External calls have no timeout behavior (F34)

> “error wrapper `safe(step) -> FlowResult` turning exceptions into handoffs.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:366))

Catching exceptions does not handle a model, embedding or webhook call that never returns. Such a call can hold the single worker, miss reply-speed targets and prevent a handoff.  
Classification: **UNCLEAR**. The two likely readings are:

- all SDK clients receive centrally pinned connect/read/total timeouts; or
- only raised exceptions are handled, leaving hung requests unbounded.

### Reviewer token exposure is defined too narrowly (F35)

> “...a correct token ... redirects to `/` with no token in the address; ... the token never appears in the logs.” ([PLAN.md](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PLAN.md:493))

The test can inspect only application logs, while a token in a URL path can appear in browser history or platform/proxy request logs before the redirect.  
Classification: **UNCLEAR**. The two likely readings are:

- “logs” means application-controlled logs only; or
- it means all logs and history, which a path token plus ordinary redirect does not guarantee.

**ADDITION findings:** none. Every issue above concerns behavior already required by the approved specification, architecture or decisions.

# Clarifying questions, ordered by build impact

- **Frozen-agent boundary (F1):** Which precise files must match the frozen state during the final run, and may web/operations/deployment code change after that freeze?
- **Confirmation transaction ownership (F2):** Where is the durable idempotency record written so that appointment mutation and confirmation result cannot diverge?
- **Final-summary ownership (F3):** Which task computes each required routing, handoff, booking, lookup, retrieval, answer, adversarial and agreement metric?
- **Engine completion contract (F5):** Should `Engine.handle` yield typed events, return a stream-plus-result object, or persist metadata for later lookup?
- **Deployment cardinality (F4):** How will the deployment command set and then verify exactly one Fly machine?
- **Quick-run meaning (F17):** Is it a smoke test or a correctness gate, and what exact failures block deployment?
- **SSE lifecycle (F30):** Must message processing and event replay survive process restart or client reconnection?
- **Human labeling gate (F29):** Does Milestone 1 wait for the author’s labels, or may findings be provisional and regenerated?
- **Evaluation budget (F33):** What are the hard per-conversation and per-run limits for turns, tokens, retries, time and dollars?
- **Reviewer secrecy (F35):** Does “never logged” cover only application logs, or Fly/proxy logs and browser history as well?

## Rulings

Recorded 2026-10-17. Codex found no wrong expected values; every finding concerned a contract gap. The author accepted every recommended fix, and the plan (`docs/PLAN.md`) was rewritten with the tasks renumbered 1 to 28. The architecture changes are recorded as architecture refinements (D36) and applied to `docs/ARCHITECTURE.md`.

| Finding | Ruling |
|---|---|
| Frozen tag rejects the completed application (F1) | Freeze only the agent-behaviour files and index by hash (Task 20); web, operations and deployment code may change (Task 27 checks both hashes). |
| Booking idempotency split across databases (F2), scheduling consumes the later store (F27) | Confirmations live in a new `agent_confirmations` table in the scheduling database, written in the same transaction (Task 11; D36). |
| Final metrics have no producer (F3) | Full `Summary` schema defined in Task 18, extended in Task 19 (adversarial, answers, grader), assembled and validated in Task 27. |
| Fly machine count is not a `fly.toml` property (F4) | `fly scale count 1` then `fly status` check in the deploy script; auto-stop off, minimum running 1 (Task 26). |
| Engine stream cannot carry metadata (F5) | Typed `SentenceEvent` and `DoneEvent` from Task 1 onward (D36). |
| Template grouping ignores staff responses (F6) | Test with the same request and different staff outcomes (Task 2). |
| Discovery checked superficially (F7) | Codex labels every template blind; findings table header, method, both agreements and three named executive findings tested (Tasks 3, 4). |
| Conflict register completeness (F8) | One row per conflicting fact in the data-review fact table (Task 5). |
| Meaning-based search untested (F9) | Meaning-mode ordering, combined using both lists, five results, top meaning score (Task 6). |
| Split publication and freeze not proven (F10) | Per-reason counts file and held-out hash committed before tuning (Task 7). |
| Whole-knowledge-base benchmark never graded (F11) | Graded in Task 19. |
| Flow tests stop at helpers (F12) | New conversation-level test task (Task 17) and fuller safety-reply tests (Task 12). |
| Logging not proven (F13) | Task 17 checks every record of a full conversation and its masking. |
| Latency target unmeasured (F14) | First-sentence test (Task 14) and a live measurement over at least 50 warm messages (Task 26). |
| Bootstrap test degenerate (F15) | Non-trivial interval case with weights and a repeatability check (Task 18). |
| Adversarial and grader outputs not evaluated (F16) | Adversarial runs scored, exact Codex command, verdicts committed, full agree/disagree table (Task 19). |
| Quick run has no oracle (F17) | Fails on any safety or booking miss or knowledge correctness below 0.8 (Task 20). |
| Public guard coverage incomplete (F18) | Daily, site-wide and address-backstop limits, greeting, customer facts, handoff receipt (Task 21). |
| Budget separation and one-use token untested (F19) | Separate evaluation key and pools; second token use refused (Tasks 18, 22). |
| Staff evidence incomplete (F20) | Live numbers, receipt fields, badge, correction notes and export tested (Task 23). |
| Operational guarantees untested (F21) | Double-run refusal, 03:00 schedule, write-failure alert, dashboard notice, uptime-monitor verification (Task 25). |
| Rollback outside the README (F22) | Runbook inside the README (Task 26). |
| Deliverable checks miss verdicts and secrets (F23) | Verdict files required; broader secret scan (Task 28). |
| Deploy gate conflicts with the cut order (F24) | `--skip-quick-run` flag if the quick run is cut (Task 26). |
| Handoff package path (F25) | `app/handoff/` as in the architecture (Task 15). |
| Keyword index artifact (F26) | Rebuilt from shipped chunks at startup (Task 6; D36). |
| Engine built before its flows (F28) | Knowledge and handoff flows moved ahead of the engine, sharing a flow protocol (Tasks 14 to 16). |
| Human labeling can stall Milestone 1 (F29) | Findings generated provisionally and regenerated when the sheet returns (Task 3). |
| Stream lifecycle missing (F30) | Sentences saved and replayed; unfinished messages after a restart become handoffs (Tasks 13, 21; D36). |
| Tasks too large for one cycle (F31) | Test groups are separate test-first cycles (plan header; Tasks 21, 23, 25). |
| Uptime monitor not buildable (F32) | UptimeRobot free plan, 5-minute checks, email, verified by stopping the machine (Task 25). |
| Paid evaluation unbounded (F33) | Turn, token, time, retry and $8-per-run limits with a separate key (Task 18; D36). |
| External calls have no timeouts (F34) | 20, 5 and 5 second timeouts and a 15-second message deadline (Global Constraints, Task 15; D36). |
| Reviewer token exposure (F35) | Token in the link's fragment, posted once and cleared (Task 22; D36). |
