I did not treat the generated “Reviewer Concerns” section as evidence or repeat its detailed findings. Where one of those subjects is unavoidable in the required coverage matrix, I only record the compliance status.

## Top 5 issues

### 1. The design does not commit to answering the actual top three call drivers through retrieval

**Definitely wrong — high severity**

- PRD: “Build a retrieval pipeline over the knowledge base that lets the agent answer the top 3 call drivers accurately.” [PRD.md:44](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:44)
- Design: “Three handled reasons are chosen from the top of that list, skipping any that are risky to automate… Scheduling counts as one of the three if it ranks there… The other handled reasons are answered through document search.” [DESIGN.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:72)

**Problem:** The design substitutes “three safe reasons selected from near the top” for “the top 3 call drivers.” It also allows scheduling to consume one of the three slots, leaving only two reasons answered through retrieval. The design candidly admits the handled reasons may differ from the literal top three, but candor does not make it word-for-word compliant.

**Why the reviewer cares:** Scope judgment is a named judging criterion. A reviewer can reasonably say the team avoided a difficult high-volume driver and then claimed success on lower-volume ones.

**Change:** Publish two explicit lists: the observed top three and the automation scope. Evaluate retrieval and safe refusal behavior on every knowledge-answerable case within the observed top three. If an entire top-three driver must be excluded, obtain an explicit reviewer/PM waiver rather than claiming that the next-ranked driver satisfies the requirement.

---

### 2. Emergency handling omits the mandatory safety instruction

**Definitely wrong — high severity**

- Knowledge-base rule: “instruct them to **leave the home immediately and call 911 or their gas utility from outside**” and “Do not advise the customer to flip switches, open windows near the furnace, or restart equipment.” [escalation_and_safety.md:4](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/policies/escalation_and_safety.md:4)
- PRD: “Escalation must be graceful… and hands off with enough context that a human can pick up without starting over.” [PRD.md:57](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:57)
- Design: “A match forces a handoff whatever the AI would decide.” [DESIGN.md:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:110)
- Design: “the caller is told plainly that a team member will take over with the details.” [DESIGN.md:124](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:124)

**Problem:** A generic handoff is not the prescribed response to gas, carbon-monoxide, smoke, flame, or electrical-burning reports. The design detects emergencies but does not require the life-safety message before creating the handoff.

**Why the reviewer cares:** These are obvious break-the-agent prompts. Saying “a team member will take over” instead of “leave now and call 911/the gas utility from outside” is a visible and potentially harmful failure.

**Change:** Add deterministic emergency classes and fixed response templates. Immediate-danger cases must first give the exact leave-and-call instruction, prohibit troubleshooting, and then create a priority handoff. Active leaks and ordinary after-hours emergencies should have separate, less severe responses.

---

### 3. Required reschedule, cancellation, and confirmation operations are made optional

**Definitely wrong — high severity**

- Schema: “**Reschedule / cancel**: update the existing appointment and free the old slot (`open`).” and “**Confirm**: look up scheduled appointments for the customer.” [SCHEMA.md:50](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:50)
- Design: “Rescheduling, cancelling and confirming an existing appointment are added **if the discovery ranking shows they are common**.” [DESIGN.md:123](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:123)
- Design: “Rescheduling and cancelling: in or out depends on how common they are in the transcripts.” [DESIGN.md:158](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:158)

**Problem:** The data’s own schema calls these “Expected agent behavior.” The design changes that into a discovery-dependent option.

**Why the reviewer cares:** The reviewer can test Linda Foster’s seeded appointment immediately. A system that can create but cannot confirm, move, or cancel that appointment looks incomplete against the supplied database contract.

**Change:** Include confirmation, cancellation, and rescheduling in the minimum scheduling flow. Keep the implementations narrow: lookup, transactionally free the old slot, and optionally reserve the replacement in the same operation.

---

### 4. The reported call-reason accuracy would be graded against the model’s own labels

**Definitely wrong — high severity**

- PRD: “Build a test set from the transcripts” and “Report accuracy on the handled drivers… Show the numbers, not just the claim.” [PRD.md:62](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:62)
- Design: “Claude Haiku 5.5 reads every transcript and gives it one main call reason.” [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70)
- Design: “The author hand-labels… about 40 transcripts, drawn from the working set only.” [DESIGN.md:71](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:71)
- Design: “All 420 are labeled by call reason for the ranking.” [DESIGN.md:77](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:77)
- Design: “Call-reason sorting accuracy… at least 90 percent.” [DESIGN.md:185](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:185)

**Problem:** The held-out transcripts receive Haiku-generated labels, while human validation is confined to the working set. Comparing the runtime router against those held-out labels measures agreement between related model judgments, not accuracy against independent truth.

**Why the reviewer cares:** This is exactly the kind of flattering number the “confidence backed by evidence” criterion warns about.

**Change:** Freeze the taxonomy, then have a human independently label a stratified held-out sample without seeing Haiku’s label. Report routing accuracy against those labels, per-class confusion, and human/model agreement separately.

---

### 5. The “current-only” index still admits a dated but obsolete scheduling guide

**Definitely wrong — high severity**

- Data README: “Some documents are current, some are not, and some contradict each other.” [README.md:20](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:20)
- Obsolete guide: “Cancellations require **48 hours** notice” and “Emergency… can be booked into same-day overflow slots.” [scheduling_guide.md:6](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/services/scheduling_guide.md:6)
- Current FAQ: “more than **24 hours**… are free. Inside 24 hours there is a $49… fee.” [customer_faq.md:12](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/faq/customer_faq.md:12)
- Schema: “Emergency calls (safety) are NOT booked here — they escalate.” [SCHEMA.md:52](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:52)
- Design: “only current documents. The `archive/` folder and the undated old FAQ copy are left out.” [DESIGN.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:88)

**Problem:** `services/scheduling_guide.md` is dated “Rev 2024-11,” is outside `archive/`, and is not named as an exclusion. It conflicts with both the current FAQ and the database contract. The design’s implied heuristic—archive or obviously old filename—does not catch it.

**Why the reviewer cares:** Questions about cancellation fees and emergency booking are easy probes. Retrieval may return a plausible but wrong answer from a document the design calls current.

**Change:** Use an explicit allowlist and authority/conflict register, not folder/name heuristics. Exclude the 2024 scheduling guide or reduce it to still-valid rules after resolving every conflict.

## Coverage table

Statuses assess whether the design defines a compliant implementation, not whether it has already been built.

| PRD or data requirement, quoted | Status | Exact design coverage | Note |
|---|---|---|---|
| “identify the top 4 to 5 reasons customers call” [PRD.md:38](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:38) | partly | “merged into a short list of categories” and “The findings document records the reasons, counts…” [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70) | It never commits to presenting the required top four or five. |
| “Analyze the call transcripts… [using] another method you can defend” [PRD.md:38](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:38) | met | Free labeling, taxonomy merge, relabeling, and a human check are specified. [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70) | The routing-accuracy ground truth remains flawed, but the discovery method itself is defensible. |
| “Rank them by volume” [PRD.md:39](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:39) | met | “Call reasons are ranked by count.” [DESIGN.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:72) | Count is a clear volume definition. |
| “Decide which ones the agent will handle and which ones it will escalate” [PRD.md:39](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:39) | met | Three handled reasons are selected and risky reasons are escalated. [DESIGN.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:72) | The decision exists, though it creates the top-three departure. |
| “Document your findings: what the drivers are, how you found them, and why…” [PRD.md:40](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:40) | met | “records the reasons, counts, method, agreement rate and why each reason is handled or handed off.” [DESIGN.md:73](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:73) | Clear planned artifact. |
| “answer the top 3 call drivers accurately” through retrieval [PRD.md:44](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:44) | not met | It may skip actual top drivers, count scheduling among three, and retrieve only for “other handled reasons.” [DESIGN.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:72) | Direct word-for-word departure. |
| “Make deliberate choices about chunking, embedding, and retrieval” [PRD.md:45](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:45) | partly | Section chunks and hybrid semantic/keyword retrieval are justified. [DESIGN.md:90](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:90) Voyage is only named. [DESIGN.md:33](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:33) | Embedding choice and retrieval-mode choice lack an ablation or corpus-specific comparison. |
| Pipeline “must account for what is actually in the docs” [PRD.md:45](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:45) | partly | PDF, CSV, and image conversion are specified. [DESIGN.md:89](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:89) | It misses the obsolete scheduling guide and other document-level traps below. |
| “Evaluate retrieval on its own” [PRD.md:46](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:46) | met | Recall, precision, hit rate, reciprocal rank, coverage, stale-trap accuracy, and a chunking comparison are specified. [DESIGN.md:92](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:92) | Measurement validity needs tightening, but retrieval is separated from answer generation. |
| “Connect the agent to the mock scheduling database” [PRD.md:50](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:50) | met | “The scheduling database is the provided SQLite file.” [DESIGN.md:135](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:135) | Directly covered. |
| “checks availability, and either confirms the booking or offers alternatives” [PRD.md:51](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:51) | met | Steps find slots, offer the requested slot or alternatives, obtain confirmation, write, and confirm. [DESIGN.md:115](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:115) | Core new-booking flow is present. |
| “A yes/no availability check and a confirmed booking is the bar” [PRD.md:52](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:52) | met | Booking writes the slot and appointment and returns date, window, and technician. [DESIGN.md:121](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:121) | Covered. |
| Schema: match zone, service type, date/window, and members-only eligibility [SCHEMA.md:48](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:48) | met | “match the customer's city to a zone… including members-only slots only for members.” [DESIGN.md:118](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:118) | The service-area/zone inconsistency still needs handling. |
| Schema: set slot booked, insert appointment, confirm date/window/tech [SCHEMA.md:49](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:49) | met | Design step 6 matches this exactly. [DESIGN.md:121](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:121) | Covered on paper. |
| Schema: reschedule, cancel, and confirm [SCHEMA.md:50](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:50) | not met | Made conditional on discovery. [DESIGN.md:123](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:123) | Required data behavior is treated as optional. |
| Schema: “Emergency calls… are NOT booked here — they escalate” [SCHEMA.md:52](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:52) | partly | Emergency matches force handoff and are never booked. [DESIGN.md:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:110) | Booking prevention is covered; mandatory caller safety instructions are not. |
| “Anything outside the handled call drivers routes to a human” [PRD.md:56](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:56) | partly | Router sends outside scope to handoff. [DESIGN.md:111](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:111) Success permits only 95%. [DESIGN.md:181](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:181) | Architecture says all; acceptance criteria allow failures. |
| Graceful escalation with enough context [PRD.md:57](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:57) | met | Plain caller message plus a five-field ticket. [DESIGN.md:124](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:124) | Strong coverage for ordinary handoffs. |
| “Do not let the agent guess” [PRD.md:58](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:58) | met | Low confidence, absent support, and account-specific uncertainty hand off. [DESIGN.md:113](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:113) | Covered. |
| “Build a test set from the transcripts” [PRD.md:62](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:62) | met | A 120-transcript held-out set and transcript-scripted simulated conversations are specified. [DESIGN.md:77](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:77) | The construction has validity issues discussed below. |
| “Measure containment… Target is 60 to 75 percent” [PRD.md:63](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:63) | met | Containment is precisely defined and 60–75% remains the aim. [DESIGN.md:84](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:84), [DESIGN.md:178](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:178) | Honest below-target reporting may still be judged a target miss. |
| “Report accuracy… and the escalation rate… Show the numbers” [PRD.md:64](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:64) | met | Both are in the final report list and have proposed targets. [DESIGN.md:140](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:140) | Reporting is planned; metric validity is not fully sound. |
| “Deploy… at a public URL” and make it interactive [PRD.md:68](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:68) | met | Public Fly.io service and free-text chat are specified. [DESIGN.md:129](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:129), [DESIGN.md:193](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:193) | Covered as a plan. |
| Observability for “volume, containment, escalations, failures, latency” [PRD.md:73](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:73) | met | Dashboard includes volume, containment, handoffs, failures, and response-time percentiles. [DESIGN.md:131](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:131) | All required categories appear. |
| “Include a feedback or learning loop” [PRD.md:74](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:74) | met | Masked logs, flags, correction notes, export to test cases, and rerun/deploy loop. [DESIGN.md:134](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:134) | More than the required first step. |
| Deployed URL deliverable [PRD.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:88) | met | Public URL is a success criterion and distribution target. [DESIGN.md:189](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:189) | Planned. |
| “3 to 4 minute voiceover” covering the four named design topics [PRD.md:89](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:89) | met | The script outline covers discovery, chunking/retrieval, handoff, and numbers; the author records it. [DESIGN.md:142](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:142) | Planned. |
| Repository with “code, eval set, and a README… and what the containment numbers were” [PRD.md:90](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:90) | met | README contents and repository deliverables are explicit. [DESIGN.md:141](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:141), [DESIGN.md:189](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:189) | Planned, not presently implemented. |
| Optional voice extra credit [PRD.md:80](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:80) | met | Voice is explicitly deferred unless required work finishes early. [DESIGN.md:147](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:147) | Fully compliant because voice is optional. |
| Data: transcripts are unlabeled STT output with interruptions [README.md:17](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:17) | met | All transcripts are classified; simulated callers retain rambling and multi-question behavior. [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70), [DESIGN.md:80](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:80) | Covered. |
| Data: mixed formats, outdated/contradictory documents, and internal-only content [README.md:20](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:20) | partly | Mixed-format conversion and some exclusions are defined. [DESIGN.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:88) | Exclusion policy misses actual files. |
| “bookings must actually write to” the same live database [README.md:23](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:23) | met | “bookings must write to the one real database.” [DESIGN.md:35](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:35) | Nightly reset remains a PM-risk, but writes are real. |
| “Treat 2026-10-16 as ‘today.’” [README.md:26](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:26) | met | The date is fixed for every calculation. [DESIGN.md:36](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:36) | Covered. |
| “The `internal/` folder… should not be read verbatim to customers.” [README.md:20](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:20) | met | Internal notes are excluded from retrieval, paraphrased, and output-checked. [DESIGN.md:114](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:114) | The separate internal-marked safety document still needs an explicit rule. |

## Remaining findings by pass

### Coverage

#### The design does not explicitly promise the required top four or five

**Unclear, needs confirmation — medium severity**

- PRD: “identify the top 4 to 5 reasons customers call.” [PRD.md:38](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:38)
- Design: “merged into a short list of categories” and “The findings document records the reasons, counts…” [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70)

The plan could produce the correct artifact, but it never says the findings document will prominently rank and document the top four or five. Add an explicit table with rank, count, percentage, cumulative percentage, handled/escalated disposition, and reason.

#### The embedding choice is named, not defended

**Unclear, needs confirmation — medium severity**

- PRD: “Make deliberate choices about chunking, embedding, and retrieval.” [PRD.md:45](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:45)
- Design: “Voyage AI provides embeddings.” [DESIGN.md:33](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:33)
- Design: the only stated comparison is “At least one alternative chunking setting.” [DESIGN.md:98](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:98)

The section-chunk and hybrid-retrieval choices have corpus-specific reasons; the embedding choice does not. Compare at least keyword-only, dense-only, and hybrid retrieval on the same gold questions. A separate embedding-model bake-off is unnecessary if the provider choice is justified by that evidence.

#### The success criterion accepts wrong answers on up to 5% of out-of-scope calls

**Definitely wrong — high severity**

- PRD: “Anything outside the handled call drivers routes to a human.” [PRD.md:56](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:56)
- Design: “Handoff on out-of-scope calls: at least 95 percent.” [DESIGN.md:181](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:181)

The architecture says all such calls hand off, but the acceptance target declares success with 5% answering behavior. Set the required safety-policy rate to 100% on the fixed test set, while separately reporting a confidence interval for expected production behavior.

### Departures

The top-three retrieval departure and optional scheduling operations are already ranked issues 1 and 3.

#### Honest below-target containment is justified but is still a target miss

**Unclear, needs confirmation — high severity**

- PRD: “Target is 60 to 75 percent.” [PRD.md:63](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:63)
- Design: “If containment is below 60 percent, report it as it is with the reason.” [DESIGN.md:140](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:140)
- Design: “aim for 60 to 75 percent.” [DESIGN.md:178](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:178)

This departure is stated and ethically justified. It meets the measurement/reporting wording but not the numeric target. The design correctly leaves it as a PM question; it should not call a sub-60% outcome fully compliant without that confirmation.

#### The nightly reset is a defensible interpretation, not clearly authorized

**Unclear, needs confirmation — medium severity**

- Data README: “bookings must actually write to” the same database. [README.md:23](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:23)
- Design: “bookings must write to the one real database… and the database resets… each night.” [DESIGN.md:35](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:35)
- Design: nightly-reset acceptability remains a PM question. [DESIGN.md:172](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:172)

A booking is real until reset, so this is probably compliant word for word. It is correctly stated and justified, but reviewer approval remains necessary. Show the newly written row to the reviewer and disclose the reset schedule.

No problematic departure was found in deferring voice; voice is explicitly optional.

### Judging criteria

| Criterion | Likely judgment | What weakens it |
|---|---|---|
| “Judgment on scope” [PRD.md:96](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:96) | **Unclear, needs confirmation — high.** The volume-first method and documented risk exclusions are defensible. | The design explicitly allows lower-ranked reasons to replace the literal top three and has no discovered ranking yet. [DESIGN.md:72](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:72) |
| “Honesty about the data… Did you catch the traps?” [PRD.md:97](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:97) | **Definitely weakened — high.** The design catches archived fees, warranty, membership, PDF, CSV, and image traps. | It misses the dated-but-obsolete scheduling guide and does not enumerate all internal-marked documents. [DESIGN.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:88) |
| “Confidence backed by evidence” [PRD.md:98](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:98) | **Definitely weakened — high.** Containment is strictly defined and wrong confident answers are exposed. | Call-reason accuracy is circular; the random split is incorrectly described as preserving the same mix; grader agreement lacks a sampling protocol. [DESIGN.md:70](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:70), [DESIGN.md:78](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:78) |
| “Production thinking… Would the business know if it broke?” [PRD.md:99](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:99) | **Unclear, needs confirmation — medium.** Persistence, health checks, dashboard metrics, alerts, spend limits, and feedback are strong on paper. | The four-day plan is overloaded, so these are the features most likely to be incomplete or unverified. [DESIGN.md:127](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:127) |
| “Clean failure” [PRD.md:100](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:100) | **Definitely weakened — high.** Ordinary low-confidence handoff and contextual tickets are well designed. | Emergency handoffs omit required safety language, and 95% out-of-scope handoff is accepted as success. [DESIGN.md:110](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:110), [DESIGN.md:181](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:181) |

### Data traps

#### Serviceable cities exist outside the scheduling zone map

**Definitely wrong — medium severity**

- Current service-area document: “Newly added April 2026: Dripping Springs (78620) and Manor (78653).” [service_area.md:13](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/policies/service_area.md:13)
- Schema zone map lists Round Rock, Cedar Park, Pflugerville, Georgetown, Leander, Hutto, Austin, Kyle, and Buda only. [SCHEMA.md:44](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/scheduling_db/SCHEMA.md:44)
- Design: “match the customer's city to a zone.” [DESIGN.md:118](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:118)

The agent can correctly say those cities are serviced but cannot map them to a scheduling zone. Add authoritative mappings or define “serviceable but online booking unavailable; hand off” behavior and test both cities.

#### An internal document sits outside the `internal/` directory

**Unclear, needs confirmation — medium severity**

- Data README: “The `internal/` folder is agent-facing only.” [README.md:20](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/README.md:20)
- The safety policy identifies itself as “_Internal — Call Center_.” [escalation_and_safety.md:2](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/policies/escalation_and_safety.md:2)
- Design excludes “internal agent notes” but otherwise indexes current documents. [DESIGN.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:88), [DESIGN.md:114](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:114)

Folder-based filtering alone would expose an internal policy as a customer citation. Use a document manifest with audience metadata; feed the policy to code-controlled safety handling, not customer-facing retrieval.

#### The most directly named duct-cleaning document is an empty placeholder

**Unclear, needs confirmation — low severity**

- PRD: the pipeline must account for “what is actually in the docs.” [PRD.md:45](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:45)
- `duct_cleaning.md`: “TODO — Marcy to write up partner referral process.” [duct_cleaning.md:3](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/services/duct_cleaning.md:3)
- The real answer is elsewhere: “Duct cleaning… partner with a third party; ask for a referral.” [service_catalog.md:37](/home/lucyc/gauntlet/AI_Call_Center_Agent/call_data/knowledge_base/services/service_catalog.md:37)
- Design indexes “only current documents” without mentioning placeholders. [DESIGN.md:88](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:88)

Hybrid search may rank the empty, exactly named file first. Exclude placeholder-only chunks and add a duct-cleaning retrieval test.

No additional transcript-answer trap was found beyond those already anticipated: the corpus contains human agents booking burning-smell and carbon-monoxide calls, and the design correctly avoids treating historical agent answers as ground truth.

### Feasibility in four working days

#### The plan is unlikely to finish from the current starting point

**Unclear, needs confirmation — high severity**

- PRD: “A smaller system that works and is measured beats a larger one that is neither.” [PRD.md:102](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:102)
- Design allocates discovery and test creation to days 1–2, retrieval to day 2, agent flows to days 2–3, website/monitoring/feedback to days 3–4, and final measurement and deliverables to day 4. [DESIGN.md:68](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:68), [DESIGN.md:138](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:138)

The current workspace contains data and documents but no application source. The plan expects, from zero, transcript processing, reference-answer authoring, mixed-format ingestion, retrieval experiments, a multi-turn router, transactional scheduling, two web interfaces, metrics storage, deployment, alerts, an evaluation harness, README, and video.

Most likely to slip: independent retrieval labeling, final held-out evaluation, deployment hardening, monitoring verification, and the video—the exact artifacts the reviewer uses as proof.

#### The cut order removes evidence before optional interface work

**Definitely wrong — high severity**

- Design preserves cached suggested-question buttons. [DESIGN.md:130](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:130)
- Its cut order removes consistency runs, shrinks adversarial tests, and then removes the retrieval-threshold curve. [DESIGN.md:143](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:143)
- PRD requires deliberate retrieval choices and a design-reasoning video. [PRD.md:45](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:45), [PRD.md:89](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:89)

Suggested buttons and cached pre-generated replies should be cut before evidence used to justify the handoff threshold. A safer cut order is: buttons/cache, cost-per-conversation breakdown, hourly containment alert, optional caller simulation, redundant retrieval metrics, then reduce adversarial breadth. Do not cut deployment, top-driver artifact, retrieval evaluation, core scheduling operations, handoff tickets, required metrics, README, or video.

### Measurement validity

#### A random split does not guarantee the same driver mix

**Definitely wrong — medium severity**

- PRD asks whether “the test set reflect[s] real calls.” [PRD.md:98](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:98)
- Design: “split at random” into about 300/120. [DESIGN.md:77](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:77)
- Design then claims the held-out set “has the same mix of reasons as real traffic.” [DESIGN.md:78](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:78)

A random 120-call sample has only approximately the same mix and may omit or distort rare but important safety drivers. Use a seeded stratified split, preserve multi-intent and safety strata, and publish counts for corpus, working set, and held-out set.

#### Retrieval gold labels are not defined independently of chunking

**Unclear, needs confirmation — medium severity**

- PRD: “Evaluate retrieval on its own.” [PRD.md:46](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:46)
- Design labels questions with “the passages needed to answer” and then compares an alternative chunking setting. [DESIGN.md:92](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:92), [DESIGN.md:98](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:98)

A section chunk and a fixed-size chunk do not have the same passage IDs or boundaries. If gold labels are created after section chunking, the comparison favors that scheme. Define gold evidence as document plus source-line/span ranges, then map each candidate chunking scheme onto those spans.

#### One stochastic simulated conversation per held-out transcript produces unstable headline numbers

**Unclear, needs confirmation — medium severity**

- Design: “a second AI playing the caller, given the transcript as its script.” [DESIGN.md:80](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:80)
- Repeated consistency runs are “optional, first to drop.” [DESIGN.md:83](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:83)
- The final held-out set is run once. [DESIGN.md:140](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:140)

Different simulator wording, turn count, or cooperation can change routing, containment, and latency. Fix model version, temperature/seed where supported, simulator rules, and stored replay transcripts. If full three-run evaluation is too expensive, repeat all failures and a stratified sample, not zero cases.

#### Grader agreement can be inflated by sample selection

**Unclear, needs confirmation — medium severity**

- PRD: “Show the numbers, not just the claim.” [PRD.md:64](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:64)
- Design reports “grader agreement with the author's hand grades (about 30 answers).” [DESIGN.md:140](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:140)

There is no randomization, stratification, blinding, class balance, or disagreement rule. Thirty easy correct answers can produce excellent agreement while the grader mishandles failures. Preselect a stratified sample before grading, blind the author to the automated verdict, and publish the confusion matrix as well as raw agreement.

#### The stated containment ceiling is too optimistic

**Definitely wrong — medium severity**

- Design glossary: “Containment ceiling… equal to the share of calls whose reason the agent handles.” [DESIGN.md:477](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:477)
- Design itself acknowledges that missing document coverage “explain[s] part of the containment ceiling.” [DESIGN.md:96](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:96)

Handled-driver share is only a scope ceiling. Real achievable containment is lower because some handled calls lack KB coverage, fail identity checks, contain mixed requests, or correctly trigger confidence handoff. Report both the gross scope ceiling and an evidence-adjusted achievable ceiling; do not use the former to imply expected performance.

### Overbuilding

#### Cached suggested-question buttons add a second answer path without satisfying a requirement

**Definitely wrong — medium severity**

- PRD: “A smaller system that works and is measured beats a larger one that is neither.” [PRD.md:102](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:102)
- Design adds “4 to 6 buttons,” router bypass, index-time answer generation, caching, and refresh behavior. [DESIGN.md:130](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:130)

The reviewer is explicitly expected to type arbitrary questions. The buttons do not prove that path and create a second execution mode that must stay consistent with retrieval, logging, citations, and evaluation. Cut them until all required evidence and deliverables are finished.

#### The evaluation suite contains redundant metrics for a four-day prototype

**Unclear, needs confirmation — medium severity**

- PRD requires retrieval evaluation and numeric containment, accuracy, and escalation. [PRD.md:46](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:46), [PRD.md:63](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:63)
- Design adds recall, precision, hit rate, reciprocal rank, coverage, stale-trap accuracy, faithfulness, answer relevance, citation accuracy, correct refusal, threshold curves, adversarial pass rate, agreement, margin of error, and optional repeated consistency. [DESIGN.md:92](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:92), [DESIGN.md:140](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:140)

Several are useful, but implementing and validating all of them risks leaving the required product unfinished. Keep hit/recall at a fixed small `k`, stale-trap accuracy, answer correctness/groundedness, containment, out-of-scope handoff, booking correctness, latency, and grader validation. Add the rest only after those are reproducible.

#### Hourly containment-drop alerting is statistically weak at demo traffic levels

**Definitely wrong — low severity**

- PRD asks whether the business would know if the system broke. [PRD.md:99](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/PRD.md:99)
- Design alerts when “containment drops over the last hour.” [DESIGN.md:132](/home/lucyc/gauntlet/AI_Call_Center_Agent/docs/DESIGN.md:132)

A prototype may see only a handful of conversations per hour, making the rate meaningless and noisy. Alert on uptime, error rate, database write failure, and spend-cap exhaustion; show containment as a dashboard trend with a minimum-sample threshold.

**Verdict: not ready — the design is broad, but it still violates the literal top-three and scheduling contracts, mishandles emergency response, misses real data traps, and relies on measurements that can overstate performance.**
## Rulings

Recorded 2026-10-16. The review was run by Codex at the author's request, comparing `docs/DESIGN.md` with the PRD and the data's own README and schema. Claude checked every data claim against the files in `call_data/` and all held. All accepted changes have been applied to `docs/DESIGN.md`.

**Real problems: all fixed, as recommended.**

| Finding | Ruling |
|---|---|
| Emergency handling omits the mandatory safety instruction | Fixed: two emergency classes in code; immediate danger gets a fixed "leave the home and call 911 or the gas utility from outside, do not flip switches or restart equipment" reply before a priority handoff; urgent non-dangerous cases get a calmer fixed reply. |
| The current-only index still admits the dated but obsolete scheduling guide | Fixed: an explicit document list (status, audience, date, reason) replaces folder rules; the 2024 scheduling guide and the empty duct-cleaning file are left out. |
| An internal document sits outside the internal folder | Fixed: the internal safety policy is marked internal in the document list and feeds code rules, never search. |
| Serviceable cities exist outside the scheduling zone map | Fixed: Dripping Springs and Manor are confirmed as served and their bookings hand off; both are test cases. |
| A random split does not guarantee the same driver mix | Fixed: a seeded split stratified by call reason, with counts published. |
| Retrieval gold labels are not defined independently of chunking | Fixed: needed text is labeled as document plus line span. |
| The embedding choice is named, not defended | Fixed: keyword-only, meaning-only and combined search are compared. |
| Grader agreement can be inflated by sample selection | Fixed: a sample chosen in advance across right and wrong verdicts, graded blind by the author, with the full agree/disagree table published. |
| The stated containment ceiling is too optimistic | Fixed: report a scope ceiling and an adjusted ceiling. |
| One simulated conversation per transcript gives unstable numbers | Fixed: fixed simulator model and settings, saved replays, failed cases re-run once. |
| Hourly containment alerting is noisy at demo traffic | Fixed: alerts on downtime, error rate, failed database writes and the spending cap; containment shown as a trend above a minimum sample. |
| The design does not promise the top four or five | Fixed: an explicit ranked table in the findings document. |
| The success criterion accepts misses on out-of-scope calls | Fixed as wording: 100 percent on safety and booking-rule cases, at least 95 percent on other out-of-scope calls with every miss listed. |

**Decisions made by the author.**

| Finding | Ruling |
|---|---|
| The design does not commit to answering the actual top three call drivers through retrieval | Accepted the recommended replacement: answer the knowledge part of every real top-three reason through document search, hand off only risky parts, and show the observed top three and the agent's scope as two lists (choosing handled call reasons to meet the top-three requirement (D12), replacing (D2)). |
| Required reschedule, cancellation and confirmation operations are made optional | Accepted: all three are core and never cut (rescheduling, cancelling and confirming in scope (D13)); about half a day. |
| Reported call-reason accuracy would be graded against the model's own labels | Accepted with the author's change: an OpenAI frontier model run through Codex labels an 80-transcript sample, and the author labels about 27 of them to check it (ground-truth labels (D14)). Related: grading also runs through Codex to avoid API cost (grading through Codex (D15)). |
| Cached suggested-question buttons add a second answer path | Partly accepted: buttons kept but without cached answers, and first in the cut order (suggested-question buttons without caching, and the cut order (D16), replacing (D11)). |
| The cut order removes evidence before optional interface work | Accepted: new cut order and a never-cut list, in the design and in (D16). |
| The evaluation suite contains redundant metrics | Partly accepted: all measures stay, computed by one test harness, but only a core set is protected; the rest are in the cut order. |
| The plan is unlikely to finish from the current starting point | Noted: addressed by the cut order and never-cut list; tracked at each milestone gate. |
| Honest below-target containment and the nightly reset still need confirmation | No change: both remain questions for the PM in `docs/PRD_REVIEW.md`. |
