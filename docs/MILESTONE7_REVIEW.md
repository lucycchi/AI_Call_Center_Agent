## Top 5 issues

1. **Payment-data masking is bypassable (S1)**  
   [app/ops/masking.py:10](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/masking.py:10) masks only 13–19 digits separated by spaces or hyphens: `\d(?:[ -]?\d){12,18}`. Dotted card numbers such as `4111.1111.1111.1111` and 12-digit bank-style numbers remain unchanged. They are then persisted through `mask(text)` at [app/ops/store.py:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:110), including the accepted-message event at line 116. The same incomplete regex controls the rejection check at [app/core/pipeline.py:374](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:374).  
   **Why it matters:** payment credentials can enter conversation logs even though the money and membership actions decision (D54) and the author-supplied autopay policy say card and bank numbers never enter chat storage.  
   **Classification: DEFINITELY WRONG.**

2. **An emergency leaves a previous financial action armed (I1)**  
   The safety branch clears only `state.flow`, `state.active_flow`, and `state.pending` at [app/core/pipeline.py:356](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:356), leaving `state.action` intact. On the next message, the action confirmation executes at [app/core/pipeline.py:378](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:378), before the post-safety safeguard at line 434. Reproduced sequence: upgrade read-back → “I smell gas” → emergency ticket → “yes” → membership upgraded.  
   **Why it matters:** an acknowledgment following emergency instructions can authorize a stale money or membership action. Safety is supposed to leave the active flow under the active-flow safety rule (R40).  
   **Classification: DEFINITELY WRONG.**

3. **Committed actions can finish silently without a handoff (I2)**  
   The new confirmation shortcut passes committed results to `_written()` at [app/core/pipeline.py:382](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:382). `_written()` constructs a `CheckedStream` at [app/core/pipeline.py:742](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:742) but never examines its `blocked_rule` or `not_in_documents` state. It then reports `outcome="answered"` at line 387. The normal path deliberately emits committed confirmations as fixed text at [app/core/pipeline.py:582](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:582).  
   **Why it matters:** reproduced with a writer-generated waitlist promise: the upgrade committed, but the caller received no sentence, no ticket, and an “answered” result. This violates the blocked-sentence handoff requirement (R42) and checked sentence-release requirement (R60).  
   **Classification: DEFINITELY WRONG.**

4. **Membership mutation and action audit can be half-committed (D1)**  
   Enrolment and upgrade changes commit in the scheduling database at [app/flows/actions.py:137](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:137) and [app/flows/actions.py:145](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:145). Only afterward does the separate operations database receive `store.record_action(...)` at line 168. `state.action` has already been cleared at line 130.  
   **Why it matters:** if the audit insert fails, the membership remains changed while the caller gets an error handoff and Staff has no action record. That contradicts “every action is recorded” in the money and membership actions decision (D54).  
   **Classification: DEFINITELY WRONG.**

5. **Auto-renew state is write-only and survives the reset that should remove it (I4)**  
   Cancelling auto-renew writes `membership_settings` at [app/flows/actions.py:151](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:151). The membership lookup ignores that table and still says the plan “renews” at [app/flows/account.py:74](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/account.py:74). The nightly reset restores only tables present in the seed at [app/ops/jobs.py:30](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/jobs.py:30); the runtime-created table is neither cleared nor dropped.  
   **Why it matters:** callers receive contradictory renewal information, and one demo visitor’s setting persists across nightly resets, contrary to the money and membership actions decision (D54) and nightly reset requirement (R76).  
   **Classification: DEFINITELY WRONG.**

## Security

### Payment-data masking is bypassable (S1)

- Evidence: [app/ops/masking.py:10](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/masking.py:10), [app/ops/store.py:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:110), [app/core/pipeline.py:374](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:374).
- Targeted probes confirmed that `4111.1111.1111.1111` and `123456789012` are returned unchanged by `mask()`, while the ordinary spaced card format is masked.
- **Classification: DEFINITELY WRONG.**

### Action records escape 30-day retention (S2)

- The purge enumerates `sentences`, `receipts`, `model_calls`, and `ticket_messages`, then deletes events, messages, and conversations at [app/ops/store.py:368](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:368). It never deletes or detaches `account_actions`.
- The table stores `conversation_id`, `customer_id`, action details, destination, and timestamps without a cascading foreign key at [app/ops/schema.sql:42](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/schema.sql:42).
- **Why it matters:** identifying action records remain indefinitely after their conversation has been purged, contradicting the 30-day operations-log retention requirement (R73). Tickets have an explicit retention exception; action records do not.
- **Classification: DEFINITELY WRONG.**

No tracked keys, provider-token signatures, or private keys were found in the current tree or full Git history using common credential patterns.

## Parts working together

### An emergency leaves a previous financial action armed (I1)

- The safety reset at [app/core/pipeline.py:356](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:356) omits `state.action`; action confirmation runs at [app/core/pipeline.py:378](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:378) before the post-safety guard at line 434.
- **Classification: DEFINITELY WRONG.**

### Committed actions can finish silently without a handoff (I2)

- The shortcut at [app/core/pipeline.py:378](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:378) bypasses the normal committed-confirmation handling at [app/core/pipeline.py:582](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:582).
- Its `_written()` helper at [app/core/pipeline.py:742](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:742) discards the checker’s failure state and does not locally turn writer errors into tickets.
- **Classification: DEFINITELY WRONG.**

### Different account actions collapse into one request (I3)

- Every doable action is rewritten to the same `Request(..., "account", "action")` at [app/core/pipeline.py:533](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:533).
- Pending requests are deduplicated solely by `(route, detail)` at lines 538–543. Payment, autopay, enrolment, upgrade, and cancellation therefore have the same key.
- Reproduced with router output containing payment-link and autopay requests: only the payment request survived; no autopay action or handoff remained.
- **Why it matters:** correctly split multi-request messages still lose work, violating multi-request handling (R39).
- **Classification: DEFINITELY WRONG.**

### Auto-renew state is write-only and reset-resistant (I4)

- Written at [app/flows/actions.py:151](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:151), ignored by [app/flows/account.py:74](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/account.py:74), and omitted from reset by [app/ops/jobs.py:30](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/jobs.py:30).
- Repository-wide references show no production reader of `membership_settings`.
- **Classification: DEFINITELY WRONG.**

### New payment links are recorded as already expired (I5)

- Link expiry is calculated from the fixed demo time at [app/flows/actions.py:135](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:135), which is pinned to October 16 at [app/config.py:61](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/config.py:61).
- `created_at` comes from the operations store’s real clock at [app/ops/store.py:21](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:21) and [app/ops/store.py:267](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:267).
- On October 22, a newly recorded action therefore has a real creation date of October 22 and an expiry of October 17. Staff displays that expiry.
- **Why it matters:** the output violates the secure-link validity contract in the money and membership actions decision (D54) and the architecture’s “24 hours on” definition.
- **Classification: DEFINITELY WRONG.**

### Ticket “wants” is not the whole caller interaction (I6)

- Only the latest 20 history messages are loaded at [app/core/pipeline.py:274](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:274).
- `_caller_words()` truncates the result to 600 characters at [app/core/pipeline.py:200](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:200).
- `_only_identity()` also discards any message containing an identifier with four or fewer remaining words at [app/core/pipeline.py:203](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:203). For example, “MHC-10001 sink is backed up” is treated as identity-only.
- **Why it matters:** although Staff can open the separate transcript, the actionable `wants` field can omit the problem, contrary to the whole-interaction handoff decision (D56) and actionable-ticket requirement (R57).
- **Classification: DEFINITELY WRONG.**

## Requirements end to end

### The action grader accepts missing actions and unrelated customer corruption (E1)

- `_action_checks()` validates only rows that exist—`for action in done`—at [eval/grade_conversations.py:246](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/grade_conversations.py:246). It never requires an expected action to be present.
- Any customer-row change combined with a recorded enrolment or upgrade sets `explained=True` at line 265. The entire customer row is then exempted from unexpected-write detection at [eval/grade_conversations.py:345](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/grade_conversations.py:345), rather than only the membership fields.
- The test suite explicitly asserts that a requested cancellation with no recorded action is correct at [tests/eval/test_conversation_grading.py:317](/home/lucyc/gauntlet/AI_Call_Center_Agent/tests/eval/test_conversation_grading.py:317).
- The model-grader payload at [eval/grade_conversations.py:475](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/grade_conversations.py:475) receives the transcript and starting account facts, not the recorded actions or resulting customer row, so it cannot close this gap.
- **Why it matters:** a transcript that claims success while doing nothing—or corrupting unrelated customer data—can still be counted correct under the fresh-set three-run measurement decision (D55).
- **Classification: DEFINITELY WRONG.**

### Partial fresh runs consume full-run slots and enter the report (E2)

- `refuse()` rejects only unknown case IDs, not a proper subset of the frozen 30, at [eval/fresh_cases.py:275](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/fresh_cases.py:275).
- `--limit` is applied only after that guard at [eval/run.py:385](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/run.py:385).
- Every successful fresh invocation is recorded unconditionally at lines 412–413, including subset, limited, provisional, or duplicate resumed folders.
- The report calculates its denominator from whatever first attempts exist in the folder at [eval/fresh_cases.py:301](/home/lucyc/gauntlet/AI_Call_Center_Agent/eval/fresh_cases.py:301), without requiring all 30 cases.
- **Why it matters:** `--set fresh --fresh-final --limit 1` can consume one of the three allowed runs and be reported as a full run, contradicting the 30-case, three-run measurement decision (D55).
- **Classification: DEFINITELY WRONG.**

## Data loss and cost

### Membership mutation and action audit can be half-committed (D1)

- `state.action` is cleared before work at [app/flows/actions.py:127](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/actions.py:127).
- Scheduling-database changes commit at lines 137–159.
- The independent operations-database write occurs afterward at line 168.
- If that final write fails, `safe()` converts the exception into a generic handoff at [app/handoff/flow.py:57](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/handoff/flow.py:57), but cannot roll back the already committed membership mutation.
- **Why it matters:** callers and staff can be told the action failed even though customer data changed, with no durable action record explaining the mutation.
- **Classification: DEFINITELY WRONG.**

No new Milestone 7 uncapped paid-service path was found. Previously documented paid-service findings in `docs/FINAL_REVIEW.md` were not duplicated.

The unpaid pytest suite could not begin because the read-only environment provides no writable temporary directory; pytest failed before collection. Targeted Python/SQLite reproductions used memory only, made no project changes, and invoked no paid service.