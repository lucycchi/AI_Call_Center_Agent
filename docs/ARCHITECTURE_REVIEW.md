## Top 5 issues

### Seed status cannot be reconstructed (F1) — rank 1

Quoted lines:

> “A read-only **seed copy** of the original file ships in each release: the nightly reset restores from it, and cancellations read it to restore a freed slot's original status...”  
> [ARCHITECTURE.md:83](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:83)

> `E->>SC: 5. original status of the old slot`  
> `SC-->>E: reserved_members`  
> [ARCHITECTURE.md:366](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:366)

The seed records Linda Foster’s slot 159 as `booked`, not as its supposed earlier `reserved_members` status:

> `159,2026-10-22,08:00-12:00,5,north,hvac_repair,booked`  
> [appointment_slots.csv:160](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/appointment_slots.csv:160)

**Problem:** The seed cannot reveal what a seeded booked slot was before it was booked. Cancelling Linda’s appointment either leaves the slot `booked` or requires an undocumented guess. The cancellation and rescheduling rule (R55) cannot work as described.

**Why it matters:** Confirming, cancelling, and rescheduling are never-cut behavior, and Linda is a prominently advertised test customer. A reviewer can expose this immediately.

**Classification:** **DEFINITELY WRONG**

**Question:** Where is a booked seed slot’s pre-booking status authoritatively stored: a new immutable mapping, an operations record, or an explicit rule derived from other data?

---

### Cross-database partial success has no outcome (F21) — rank 2

Quoted lines:

> “One transaction marks the slot booked and adds the appointment row...”  
> [ARCHITECTURE.md:350](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:350)

> `G-->>B: 7. checked sentences, one by one`  
> `E->>E: 8. log message, receipt and cost`  
> [ARCHITECTURE.md:300](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:300)

**Problem:** The booking transaction is in the scheduling database, while the receipt, conversation state, cost, and errors are in the operations database. Those files cannot participate in the described single transaction. The design never says what happens if the booking commits and the operations write then fails.

The two likely readings are:

- The booking remains successful and the caller receives confirmation despite missing logs and receipt.
- The operations failure is shown as a failure or handoff, although the appointment was already created.

**Why it matters:** The second reading invites a retry and duplicate or confusing bookings; the first violates the complete logging requirement (R73) and may lose the proof receipt (R66). Either can silently produce a wrong-looking result.

**Classification:** **UNCLEAR**

**Question:** After a scheduling commit succeeds, is that success authoritative even if operations logging fails, and what durable identifier lets the app reconcile or safely replay the missing operations records?

---

### Operations schema cannot produce required evidence (F4) — rank 3

Quoted lines:

> “A second SQLite file on the same disk, created by the app. It holds everything about how the agent behaves.”  
> [ARCHITECTURE.md:157](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:157)

> `INTEGER reply_ms "time to first checked sentence"`  
> `INTEGER cost_microdollars "AI cost of this reply"`  
> [ARCHITECTURE.md:189](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:189)

> “Log every conversation, reply, route, retrieval, database action, handoff, error, reply time and model cost...”  
> [SPEC.md:128](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:128)

**Problem:** The complete operations diagrams contain no individual error event or error status, no full-reply duration, and no model ID, SDK version, or request settings per model call. Tickets and conversations also lack creation/closure timestamps. Therefore the schema cannot reliably calculate:

- “no error” live containment and today’s handoffs (R70);
- the error-rate alert window (R74);
- median full reply under 4 seconds;
- the pinned-model/settings audit promised in the fixed facts.

**Why it matters:** These are displayed and measured claims. Deriving them approximately from message timestamps can produce plausible but wrong dashboard numbers.

**Classification:** **DEFINITELY WRONG**

**Question:** Is an omitted generic event/model-call table intended, or must these fields be added to the shown tables?

---

### Reset locking does not make messages wait (F3) — rank 4

Quoted lines:

> “SQLite, two files, write-ahead logging mode — write-ahead logging lets reads continue during writes.”  
> [ARCHITECTURE.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:70)

> “A background task in the app with a lock row in the operations database.”  
> [ARCHITECTURE.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:72)

> “...replaces the scheduling tables from the seed copy in one transaction, and records the run; messages arriving meanwhile wait.”  
> [ARCHITECTURE.md:608](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:608)

**Problem:** A lock row in the operations database can prevent two reset jobs, but it does not block handlers using the scheduling database. Write-ahead logging explicitly lets reads continue. No lock table appears in the operations schema, and no shared application gate is acquired by both handlers and the reset.

**Why it matters:** During reset, a request can read pre-reset data, block with `database is locked`, or make a decision against data that changes before its write. That contradicts the nightly reset behavior (R76).

**Classification:** **DEFINITELY WRONG**

**Question:** Must every request wait on an application-wide reset gate, or only scheduling operations—and what exact primitive owns that gate?

---

### One-way streaming is described as two-way (F2) — rank 5

Quoted lines:

> “Server-sent events (one-way stream from server to browser)”  
> [ARCHITECTURE.md:68](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:68)

> “The browser sends the message over the chat stream with its conversation id.”  
> [ARCHITECTURE.md:306](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:306)

**Problem:** A browser cannot send a caller message over a server-sent-event stream. Server-sent events only carry server-to-browser data.

**Why it matters:** This changes endpoint ownership, reconnect behavior, error responses, CSRF treatment, and how a browser correlates a submitted message with its streamed reply.

**Classification:** **DEFINITELY WRONG**

**Question:** Is the intended contract an HTTP `POST` for each message plus an SSE response/channel keyed by conversation and message identifier?

---

# Full findings by pass

## 1. Requirements coverage

### Required findings document has no producing component (F9)

Quoted lines:

> `pipeline/ | Template grouping, labeling sheets, Codex labeling, document list, conflict register, index build`  
> `data/ | Document list, conflict register, built index, labels, test set, results`  
> [ARCHITECTURE.md:662](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:662)

> “Produce a findings document...”  
> [SPEC.md:41](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:41)

**Problem:** No component or output owns the findings document, the top-reason table, human baselines, handled-versus-handoff breakdown, or three executive findings required by the discovery findings (R5–R8). This is a never-cut deliverable.

**Classification:** **DEFINITELY WRONG**

---

### Evaluation artifacts have no enforceable contract (F8)

Quoted lines:

> `eval/ | Test-set builder (caller cards, fixtures), simulator, Codex grader, metrics and reports`  
> [ARCHITECTURE.md:663](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:663)

> “The first run of each case is scored, failures are retried once and reported as flaky...”  
> [ARCHITECTURE.md:490](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:490)

**Problem:** The architecture names tools but gives no persistent identity or format for templates, split assignments, frozen expected outcomes, reference line spans, caller cards, fixtures, attempts, scored-first-run flags, grader model/settings, or blind author grades.

The two likely readings are:

- These are versioned JSON/CSV artifacts whose formats will be defined later.
- They are inferred from filenames and process order without an enforceable schema.

The second cannot demonstrate held-out isolation (R9, R10), first-run scoring (R12), model-attributed grading (R18), or the blind grader check (R19).

**Classification:** **UNCLEAR**

---

### Mid-flow topic changes have no router path (F6)

Quoted lines:

> `ENG -->|"message when no flow is active"| RTR["Router, Haiku 5.5"]`  
> [ARCHITECTURE.md:36](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:36)

> “...the flow is left only when ... the router returns a clear different route...”  
> [SPEC.md:86](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:86)

**Problem:** The diagram calls the router only when no flow is active, but the active-flow behavior (R40) requires a router result to recognize a clear topic change.

**Classification:** **DEFINITELY WRONG**

---

## 2. Contradictions

### Seed status cannot be reconstructed (F1)

See top-five finding. **DEFINITELY WRONG.**

### One-way streaming is described as two-way (F2)

See top-five finding. **DEFINITELY WRONG.**

### Billing reviews are not the required staff tickets (F5)

Quoted lines:

> `BILLING_REVIEWS { ... TEXT invoice_id ... TEXT detail ... TEXT created_at ... }`  
> [ARCHITECTURE.md:259](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:259)

> “alerts, job runs and billing reviews are not linked to other tables.”  
> [ARCHITECTURE.md:269](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:269)

> “...silently creates a low-priority billing-review ticket for staff...”  
> [SPEC.md:93](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:93)

**Problem:** A standalone `BILLING_REVIEWS` row has no ticket number, priority, status, conversation, customer, or place in the Staff queue. It is not the billing-review ticket required by the invoice rule (R47).

**Classification:** **DEFINITELY WRONG**

---

### The PII boundary contradicts itself (F10)

Quoted lines:

> `APP -->|"masked message text"| ANT["Anthropic: Haiku router and Sonnet writer"]`  
> [ARCHITECTURE.md:21](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:21)

> `CALLER -->|"text plus facts chosen by code"| ANT["Anthropic"]`  
> [ARCHITECTURE.md:580](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:580)

**Problem:** One diagram says Anthropic receives masked text; the data-boundary diagram says it receives caller text and selected account facts. Those lead to materially different redaction and prompt-building implementations.

**Classification:** **DEFINITELY WRONG**

---

### Appointment cardinality contradicts the actual database and lifecycle (F12)

Quoted lines:

> `APPOINTMENT_SLOTS ||--o| APPOINTMENTS : "is taken by"`  
> [ARCHITECTURE.md:90](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:90)

> `| slot_id | FK → appointment_slots |`  
> [SCHEMA.md:33](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:33)

**Problem:** The Mermaid relation says a slot has at most one appointment total. The supplied database has no unique rule on `appointments.slot_id`, and cancellation followed by rebooking naturally produces appointment history for the same slot. Conversely, nothing enforces the intended invariant of at most one `scheduled` appointment.

**Classification:** **DEFINITELY WRONG**

---

### Reviewer-reserve source documents remain contradictory (F23)

Quoted lines:

> “Spending and rate limits | Per-visitor, site-wide and reviewer-reserve budgets...”  
> [ARCHITECTURE.md:59](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:59)

> “A reserved budget for a private reviewer link is described in the README rather than built...”  
> [DESIGN.md:139](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:139)

The two likely readings are:

- The later reviewer-reserve decision (D30) and public-site budget requirement (R61) supersede this stale design sentence, so the reserve is built.
- The approved design still controls and the reserve is documentation only.

**Classification:** **UNCLEAR**

---

## 3. Failure paths

### Reset locking does not make messages wait (F3)

See top-five finding. **DEFINITELY WRONG.**

### Safety and spending/rate-limit order is ambiguous (F7)

Quoted lines:

> `ENG -->|"every message first"| SAFE["Safety check, in code"]`  
> `GUARDS["Spending and rate limits"] -->|"allow or hand off"| ENG`  
> [ARCHITECTURE.md:35](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:35)

**Problem:** The diagram places guards before the engine but says safety is first inside the engine.

The two likely readings are:

- Limits reject the message before safety, so a capped visitor reporting gas receives a generic budget handoff.
- Safety always runs first, and only non-safety processing is budget-gated.

Only the second meets the every-message safety check (R34) and fixed emergency reply (R35).

**Classification:** **UNCLEAR**

---

### Technician-overlap eligibility may not be rechecked at commit (F13)

Quoted lines:

> “...whose technician has no overlapping booking.”  
> [ARCHITECTURE.md:344](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:344)

> “...only if the slot is still bookable...”  
> [ARCHITECTURE.md:350](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:350)

**Problem:** Between offer and confirmation, another caller can book a different service-type slot for the same technician and overlapping window. Checking only the offered slot’s status is insufficient.

The two likely readings are:

- “Still bookable” re-runs every eligibility check inside a write-serializing transaction.
- It performs only a conditional status update on the offered slot.

**Classification:** **UNCLEAR**

---

### Reply-check rejection has no defined handoff transition (F18)

Quoted lines:

> `WRITER -->|"draft sentences"| GUARD["Reply checks, in code"]`  
> `GUARD -->|"checked sentences"| WEB`  
> [ARCHITECTURE.md:41](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:41)

**Problem:** There is no rejection edge. The design does not say whether a failed sentence stops generation, whether already released safe sentences remain, whether a ticket is created, or how the block is logged and counted as required by the structured reply checks (R42).

**Classification:** **UNCLEAR**

---

### Cross-database partial success has no outcome (F21)

See top-five finding. **UNCLEAR.**

---

### Mutating chat requests are not idempotent (F22)

Quoted lines:

> `B->>E: 8. "Yes"`  
> `E->>D: 9. one transaction, only if still bookable`  
> [ARCHITECTURE.md:334](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:334)

**Problem:** A double-click, browser retry, or lost response can submit the same confirmation twice. No request/confirmation identifier or uniqueness rule makes replay return the first result.

**Classification:** **ADDITION**

**Cost:** Roughly 60–100 lines plus schema and concurrency tests; about half a day; one new idempotency-key field or table. If omitted, the booking-correctness target can fail through duplicate mutation or “failed” UI after a successful commit.

---

## 4. Data model

### Operations schema cannot produce required evidence (F4)

See top-five finding. **DEFINITELY WRONG.**

### Appointment cardinality contradicts the actual database and lifecycle (F12)

See contradictions. **DEFINITELY WRONG.**

### Warranty-review notes have no storage destination (F14)

Quoted lines:

> `APPOINTMENTS { ... TEXT issue_description ... INTEGER is_warranty_visit ... }`  
> [ARCHITECTURE.md:120](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:120)

> “Repeat-repair claims and 5-year member-installation claims ... are booked as normal visits with a warranty-review note for staff...”  
> [SPEC.md:99](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/SPEC.md:99)

**Problem:** No appointment note, ticket link, or operations annotation is identified for this staff-visible warranty review.

The two likely readings are:

- Overload `issue_description`.
- Store a separate operations note/ticket associated with the appointment.

Those have different visibility, retention, and reset behavior.

**Classification:** **UNCLEAR**

---

### Purging messages can orphan or destroy flags (F15)

Quoted lines:

> `FLAGS { INTEGER message_id FK "reply flagged as wrong" ... }`  
> [ARCHITECTURE.md:213](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:213)

> `PRG -->|"deletes old messages and receipts"| ODB[("Operations database")]`  
> [ARCHITECTURE.md:600](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:600)

**Problem:** No deletion rule is given for a flagged message after 30 days.

The two likely readings are:

- Preserve flagged conversations beyond normal retention.
- Export then cascade-delete the message and flag.

Without a rule, foreign-key enforcement may block the purge, or the feedback evidence may disappear.

**Classification:** **UNCLEAR**

---

No existing ER field was found with a missing database type or missing plain-language meaning. The five provided scheduling tables’ declared SQLite types match the actual `sqlite_master` schema. The problems are omitted operational fields and incorrect cardinality/constraints, not mislabeled existing types.

## 5. Boundaries and risk

### The PII boundary contradicts itself (F10)

See contradictions. **DEFINITELY WRONG.**

### Conversation ownership enforcement is unstated (F11)

Quoted lines:

> `TEXT visitor_id FK "owner"`  
> [ARCHITECTURE.md:176](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:176)

> “The browser sends the message ... with its conversation id.”  
> [ARCHITECTURE.md:306](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:306)

**Problem:** The data can express ownership, but no request flow says the server checks that the submitted conversation belongs to the signed visitor.

The two likely readings are:

- Every read, write, and SSE subscription filters by both `conversation_id` and `visitor_id`.
- The implementation trusts an unguessable conversation identifier.

The second risks the explicit anti-goal of exposing another visitor’s conversation.

**Classification:** **UNCLEAR**

---

### Secret reviewer token needs a non-leaking exchange (F17)

Quoted lines:

> `A -->|"secret reviewer link"| C["Reviewer visitor, reserve budget"]`  
> [ARCHITECTURE.md:514](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:514)

**Problem:** A bearer token left in a URL can enter history, server access logs, screenshots, copied links, and referrer headers.

**Classification:** **ADDITION**

**Cost:** About 30–60 lines and tests, 2–4 hours, no new service: consume the token once, set the signed reviewer session, and redirect to a clean URL while suppressing token logging. If omitted, other visitors can consume the supposedly protected reviewer reserve.

---

### Downtime alerting depends on an unmodeled external service (F16)

Quoted line:

> “...downtime itself is alerted by the webhook service's uptime check.”  
> [ARCHITECTURE.md:612](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/ARCHITECTURE.md:612)

**Problem:** The system overview models an outbound alert webhook, but no external uptime monitor appears in the system, deployment, configuration, or failure ownership. The application cannot alert while fully down.

**Classification:** **ADDITION**

**Cost:** Little or no application code, roughly 1–2 hours of provider configuration and verification, plus one external moving part. If omitted, Fly may restart the machine, but the author does not receive the required downtime alert (R74).

---

## 6. Fit for size

### Standalone billing-review storage is both extra and insufficient (F5)

The separate `BILLING_REVIEWS` table duplicates the existing ticket concept but omits ticket behavior. Reusing the ticket path with a billing-review reason and low priority is smaller and meets the staff-visible requirement. **DEFINITELY WRONG.**

### Operations storage is too small for its assigned responsibilities (F4)

The broad `ops` package is reasonable, but the schema under it cannot carry its promised metrics, errors, model-call audit, timestamps, and scheduler lock. **DEFINITELY WRONG.**

### Evaluation storage is too vague for the evidence burden (F8)

A single `data/` folder description is too small a contract for held-out isolation, blind labels, retries, grader attribution, and reproducible metrics. **UNCLEAR.**

No other fit-for-size issue found. The router, two SQLite files, retrieval comparison, and separate evaluation toolkit are justified by explicit requirements.

## 7. Diagram quality

- The main-parts diagram is unnumbered and does not establish whether guards, safety, routing, and flow processing are sequential. This creates the safety-order ambiguity (F7) and active-flow contradiction (F6).
- The streaming flow describes a browser sending through a one-way stream (F2).
- The scheduling ER diagram gives false slot-to-appointment cardinality (F12).
- The request diagrams omit rejection, dependency-failure, operations-write-failure, and partial-success branches (F18, F21).
- The reset diagram claims requests wait without showing any edge from request processing to the reset lock (F3).
- No diagram exceeds about twelve boxes. The seven detailed request flows are numbered consistently with their accompanying text.

# Clarifying questions, ordered by build impact

1. Where is the pre-booking status of every seeded `booked` slot stored so cancellation and rescheduling can satisfy the freed-slot rule (R55)?
2. If a scheduling mutation commits but the operations write fails, what result must the caller see, and how is the missing receipt/log reconciled?
3. What is the complete operations event/model-call schema needed for errors, full-reply timing, model/settings attribution, ticket ordering, and live containment?
4. What shared lock or request gate makes messages actually wait during the nightly reset (R76)?
5. Is chat submission `POST` plus SSE, and what identifiers correlate a submission, streamed sentences, retries, and the final result?
6. Does safety always run before spending and rate limits, including for a visitor whose budget is already exhausted?
7. When a flow is active, when and how is the router invoked to detect a clear different topic?
8. Should fee mismatches create ordinary low-priority tickets, or is there a separate billing-review queue that the Staff view must expose?
9. Must every conversation/message/receipt query enforce both the submitted conversation identifier and the signed visitor identifier?
10. What versioned artifact formats enforce test split, pre-tuning freeze, reference spans, attempts, grader model/settings, and blind author labels?
11. Does Anthropic receive masked caller text, raw caller text, or a redacted structured projection of the caller message and account facts?
12. At booking commit, is technician-overlap eligibility rechecked under a write-serializing transaction, not merely the offered slot’s status?
13. Where is the staff-visible warranty-review note stored for claims that do not qualify for `is_warranty_visit`?
14. Are flagged conversations exempt from the 30-day purge, or exported and deleted with their flags?
15. Does the later reviewer-reserve decision (D30) explicitly supersede the design’s statement that the reserve is documentation only?
16. Which component generates and owns the mandatory discovery findings document (R5–R8)?
17. Which external uptime monitor performs the downtime alert required by the monitoring requirement (R74)?
18. Should reviewer-link tokens be exchanged for a signed session and immediately removed from the URL?
19. What idempotency key or equivalent invariant protects booking, cancellation, and rescheduling confirmations from retries and double submissions?
## Rulings

Recorded 2026-10-17. Claude checked the top finding against the data (seeded customer Linda Foster's slot 159 is "booked" in the seed) and it held. The author accepted every recommendation; all are applied to `docs/ARCHITECTURE.md`, with matching small updates to `docs/SPEC.md` and `docs/DESIGN.md`.

**Real problems: fixed.**

| Finding | Ruling |
|---|---|
| Seed status cannot be reconstructed (F1) | Restore the seed status if open or members-only; if the seed shows booked, free to open as the schema says (freed-slot fallback (D33); the freed-slot rule (R55) updated). |
| One-way streaming described as two-way (F2) | Each message is an ordinary request with a message id; its checked sentences stream back by server-sent events tied to that id. |
| Reset locking does not make messages wait (F3) | App-wide reset gate: messages hold it shared, the reset holds it exclusively; job runs still catch a missed reset. |
| Operations schema cannot produce required evidence (F4) | Added model-calls, events and confirmations tables; full reply time and request id on messages; created and closed times on conversations and tickets. |
| Billing reviews are not staff tickets (F5) and warranty-review notes have no home (F14) | Both are low-priority tickets with reason tags, the warranty one linked to the appointment; the separate table is dropped. |
| Mid-flow topic changes have no router path (F6) | The router runs on every non-emergency message; mid-flow its result only detects a clear topic change. |
| Safety and limit order ambiguous (F7) | Safety always first; emergency replies cost nothing and are never budget-gated. |
| Findings document has no producer (F9) | A pipeline step writes `docs/FINDINGS.md`. |
| PII boundary contradicts itself (F10) | Anthropic receives caller text plus code-chosen facts; only logs are masked; overview fixed. |
| Conversation ownership unstated (F11) | Every query filters by conversation id and signed visitor id unless a staff session is present. |
| Appointment cardinality wrong (F12) | A slot may have many appointments over time, at most one scheduled, enforced in code. |
| Technician overlap not rechecked at commit (F13) | All eligibility checks rerun inside a write-locked transaction. |
| Purging can destroy flags (F15) | The purge skips flagged conversations until exported. |
| Reply-check rejection has no path (F18) | Generation stops, released sentences stay, the rest becomes a handoff with a ticket, and a blocked event is logged. |
| Cross-database partial success (F21) | The booking stands and is confirmed; the operations write is retried, then logged to the server log with the appointment id and alerted. |
| Evaluation artifacts lack a contract (F8) | Evaluation files defined in a new section, with a held-out hash recorded in git before tuning. |
| Stale reviewer-reserve sentence (F23) | The design sentence now matches the reviewer-reserve decision (D30). |

**Additions: accepted with their cost** (booking, reviewer-link and downtime protections (D34)).

| Finding | Ruling |
|---|---|
| Mutating chat requests are not idempotent (F22) | Confirmation ids make a repeated "yes" return the first result; about 2 to 4 hours (new requirement R84). |
| Reviewer token in the address (F17) | One-time token exchanged for a signed session, then a redirect to a clean address; about 1 to 2 hours (R85). |
| Downtime alert needs an outside monitor (F16) | Free outside uptime monitor on the health endpoint; about 1 hour of setup (R86). |

The technology stack chosen in this stage is recorded as its own decision (technology stack (D35)).
