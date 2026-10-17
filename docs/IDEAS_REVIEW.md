# Ideas Review: AI Call Center Agent

A skeptical review of the project's intent (the PRD, the data's own rules, the decision log, the design and the research) before any code is written. I checked the data myself: I read every knowledge-base file (including the PDF fee schedule and the holiday-hours image), read about 45 transcripts in full, tallied the opening request of all 420 transcripts, and queried every table in the SQLite database.

Findings already raised and ruled on in `docs/DESIGN_PRD_REVIEW.md` or in the design's "Reviewer Concerns" section are not repeated, except where I say the applied fix is wrong or incomplete.

Each finding is marked **definitely wrong** (the documents or data show it) or **unclear, needs confirmation**, with a severity (high, medium, low), a proposed change and a rough cost.

**A note on my call-reason counts.** To check the design against the data, I sorted all 420 transcripts by their opening request with simple keyword rules. This is a rough check, not a replacement for the planned discovery step, but the corpus is so uniform (see issue 3) that the groups are clear:

| Rough group | Calls | Share |
|---|---|---|
| New service booking (repairs, tune-ups, including 16 "burning smell" calls) | 132 | 31% |
| Billing and payments (invoice questions, balance, pay an invoice, disputes, double charges, refunds) | 77 | 18% |
| Comfort Club membership (what it includes, renewal, cancel, upgrade, autopay) | 75 | 18% |
| Warranty (claims, transfer, registration, repeat repair) | 45 | 11% |
| Existing appointment (move, cancel, confirm, technician late) | 38 | 9% |
| Complaints and requests for a manager | 16 | 4% |
| Replacement estimates | 12 | 3% |
| Gas smell or carbon-monoxide alarm | 9 | 2% |
| Hiring, commercial work, wrong number | 16 | 4% |

So the observed top three are very likely booking, billing and membership, with warranty fourth.

---

## Top issues, ranked

### 1. Most top-three calls are account lookups and account actions, and the design has no tools for them

**Definitely wrong (the gap), high severity.**

- Choosing handled call reasons to meet the top-three requirement (D12), `docs/DECISIONS.md` line 174: "For each of the real top three, the agent answers its knowledge questions through document search … bookings use the database."
- Handling stale and conflicting documents (D7), `docs/DECISIONS.md` line 104: "hand off questions that depend on the caller's own account unless the database answers them".
- `docs/DESIGN.md` line 121: "or the answer depends on the caller's own account (such as a locked-in membership price), it hands off."
- What the human agents actually do in these calls:
  - `call_data/call_transcripts/CALL-20260708-0255.txt`: "You have an open balance of $245 on INV-233442, due on the 6th."
  - `call_data/call_transcripts/CALL-20260707-0096.txt` line 11: "Your term ends on the, uh, 4th of next month and it renews that day at $189."
  - `call_data/call_transcripts/CALL-20260709-0347.txt`: "You can do that from the customer portal under Payment Methods, or I can send you a secure link to add a card."
  - `call_data/call_transcripts/CALL-20260718-0349.txt`: "Done. Auto-renew is off and you'll get a confirmation email."

**Problem.** Treating billing and membership as "knowledge questions answered through document search" does not match the calls. Of about 77 billing calls, only the 11 double-charge calls can be answered from the documents alone (the FAQ's "Duplicate charges" section). Balance questions (15) and "what is this invoice for" (13) need a read of the `invoices` table. Paying an invoice (14) needs a payment link. Of about 75 membership calls, the "what does it include / how much" calls (28) are document answers. Renewal questions (14) need the customer's `membership_renewal_date`. Cancelling auto-renew (13), upgrading (6) and setting up autopay (14) are actions, and the database has no column for auto-renew or autopay. No knowledge-base file mentions autopay at all. Warranty claims (14 of the 45 warranty calls) need the customer's `system_install_date` and then a booking.

The design's own example of an account question that must hand off ("a locked-in membership price") is in fact answerable. `call_data/knowledge_base/membership/comfort_club_overview.md` line 31 says: "Existing members are locked at their enrollment price until their next renewal date, at which point the current price applies." So the renewal price is always the current price ($189 or $269), and the database holds the renewal date.

**Rough effect on containment.** With bookings, appointment changes and document-only answers, my rough ceiling is about 55 percent. Adding three read-only lookups (invoice balance and line items, membership renewal date, system install date and brand) adds about 40 calls and brings it to about 65 percent. That is the difference between missing and meeting the PRD's 60 to 75 percent target, with no extra risk, because the lookups only read the database.

**Why the reviewer cares.** "Judgment on scope" and "Is the containment number real?" The reviewer will ask "what's my balance?" as Omar Patel, whose open invoice the schema itself advertises (`call_data/scheduling_db/SCHEMA.md` line 58: "Has open invoice INV-204411 for $478.00"). A handoff there looks like missing work, not caution.

**Proposed change.** Add a decision now: "Account lookups and actions in scope." In scope: read-only lookups of the caller's open invoices (balance, due date, line items, read as recorded), membership tier and renewal date, and system brand and install date. Out of scope, always handed off with a ticket: payment links, autopay, cancelling auto-renew, upgrades, enrolment, and anything that changes money or membership. Report this "action gap" as its own line in the containment ceiling, so the reviewer sees the agent stopped on purpose. **Cost:** about half a day for the three lookups and their tests. Pay for it from issue 8.

---

### 2. No transcript customer exists in the database, and this affects every account-based test case, not only bookings

**Definitely wrong: the applied fix is incomplete. High severity.**

- The "Reviewer Concerns" section (simulated callers lack a real customer and dates, R1-3) was recorded as an unconfirmed fix and moved to `docs/DESIGN.md` line 173: "how scheduling test cases get a real customer and dates inside the three-week slot range, and what the expected booking is;" listed under "Left for the spec stage".
- `docs/DESIGN.md` line 80: "Test conversations are run by a second AI playing the caller, given the transcript as its script".
- What I measured: 131 distinct account numbers appear in the transcripts and **0** exist in `customers`; 130 phone numbers, **0** in the database; 42 invoice numbers, **0** in `invoices`. Example: `call_data/call_transcripts/CALL-20260706-0101.txt` has a caller "Linda Foster" with account "MHC-35307", while the seeded Linda Foster is MHC-10001.

**Problem.** The deferral covers only scheduling. But every call that needs the customer's record (bookings, appointment changes, balance, invoice questions, renewal dates, warranty claims, which is well over half the corpus) will fail at the first step ("I can't find that account") if the simulated caller reads the transcript as written. The containment number would then be measuring a lookup failure. Billing cases are worse: the invoices in the transcripts ($245, $2,890, $312) do not exist, so a test case needs an invoice planted in its test copy of the database.

**Why the reviewer cares.** It decides whether the headline number means anything. It also blocks the day-1 to day-2 test-set work, so it cannot wait for the spec.

**Proposed change.** Decide now, as part of the test-set design: each held-out case is bound to a real database customer chosen to match the transcript's facts (zone, tier, brand, install age). The simulated caller is given a "caller card" with that customer's name, account number, phone and address, not the transcript's. Relative dates ("tomorrow", "this Saturday") are read against the fixed "now" (issue 5). Billing cases insert their own invoice into the fresh test database copy. **Cost:** about 3 to 4 hours, mostly a fixture builder, and it removes a large source of simulator noise.

---

### 3. The transcripts are built from a few dozen templates, so the held-out set is not independent and the test is smaller than it looks

**Definitely wrong (as planned), high severity.**

- `docs/DESIGN.md` line 77: "The 420 transcripts are split once, with a fixed random seed and stratified by call reason … into a working set (about 300) used for tuning and a held-out set (about 120) used only for the final measurement."
- `docs/DESIGN.md` line 148: "and the margin of error given the test set size."
- What I measured: after removing names, numbers and filler, the 420 calls have about 83 distinct opening requests. The 3,556 agent turns use only 202 distinct lines. Example: 15 calls open with the identical "I have a tech coming tomorrow but something came up. Can I move it?" and 14 with "I want to set up autopay for my membership."

**Problem.** A split by call reason puts copies of the same template in both the working set and the held-out set. Tuning the prompt on the working copy is tuning on the held-out copy, so "held out" protects nothing. Also, 120 held-out calls are really about 50 to 60 distinct scenarios, so a margin of error computed on 120 makes the number look about one and a half times more precise than it is.

**Why the reviewer cares.** "Does the test set reflect real calls?" and "Did you catch the traps?" A reviewer who notices the templating (it is obvious after reading ten files) will discount any number that ignores it. Spotting it and saying so is a strong signal of honesty about the data.

**Proposed change.** Group transcripts by template (normalised opening request plus the agent's response pattern) and split by template, not by transcript, so no template appears on both sides. Weight each held-out template by its real call count when computing containment, and report both "calls" and "distinct scenarios" with the margin of error on scenarios. This also simplifies labelling (see the overbuilding section). **Cost:** about 2 hours, and it saves labelling time.

---

### 4. "Explaining invoice line items" is a trap: the invoices contradict the published fees

**Definitely wrong (the design treats it as safe), high severity.**

- Choosing handled call reasons (D12), `docs/DECISIONS.md` line 174: "the agent answers the safe part (such as explaining invoice line items) and hands off the rest."
- Seeded test customer Omar Patel's invoice INV-204411 in `call_data/scheduling_db/invoices.csv`: "Diagnostic visit" 8900, "Contactor replacement" 24500, "After-hours dispatch" 14400 cents.
- `call_data/knowledge_base/faq/customer_faq.md` line 6: "After-hours dispatch fee is $149"; line 15: "Diagnostic fee: $89. Applied as credit toward the repair if you approve the repair during the same visit."
- `call_data/knowledge_base/pricing/2026_fee_schedule.pdf`: "Diagnostic visit $89 Waived Waived" (non-member, Comfort Club, Plus).

**Problem.** Omar's after-hours line is $144, which matches neither the current $149 nor the old $129. He was also charged the $89 diagnostic fee on top of a repair, although the FAQ says it is credited when the repair goes ahead. Across all 81 invoices, all 45 that carry a diagnostic fee also carry repair lines, with no credit, and 22 invoices charge Comfort Club members a diagnostic fee that membership waives. So "explaining a line item" honestly almost always shows a charge that disagrees with policy. An agent that reads the line items and then cites the fee schedule will either defend a wrong bill or start a dispute it has no authority to settle.

**Why the reviewer cares.** Omar is one of four advertised test customers. This looks like a planted trap, and "a confident wrong answer is worse than a handoff."

**Proposed change.** Write the rule in code now. The agent reads invoice lines exactly as recorded and never says a charge is correct or incorrect. If the caller questions any charge, or any line differs from the current fee schedule (a check the code can do for the fixed fees: diagnostic, after-hours, holiday, late cancellation), it hands off as a billing dispute, with the mismatch written into the ticket. Add Omar's invoice as a named test case and mention the trap in the findings. **Cost:** about 1 to 2 hours.

---

### 5. The 24-hour fee rule needs a clock time, and the design applies it to cancellations only

**Definitely wrong, medium-high severity.**

- Rescheduling, cancelling and confirming in scope (D13), `docs/DECISIONS.md` line 189: "cancel (free the old slot in the same database transaction; inside 24 hours state the $49 late fee from the current FAQ, and hand off any waiver request) and reschedule (book the new slot and free the old one together)".
- `call_data/knowledge_base/faq/customer_faq.md` line 12: "Cancellations **or reschedules** more than 24 hours before the window are free. Inside 24 hours there is a $49 late-cancellation fee."
- `call_data/README.md` line 26: "Treat **2026-10-16** as 'today.'" (a date, no time).
- 15 transcripts open with "I have a tech coming tomorrow but something came up. Can I move it?" (for example `call_data/call_transcripts/CALL-20260711-0063.txt` line 8). None of the 15 mentions a fee.

**Problem.** The design charges the late fee for cancelling but not for rescheduling, which contradicts the current FAQ. The transcripts show the human staff skipping the fee on "tomorrow" reschedules, so reference answers copied from staff would be wrong (this is the exact trap the design warns about elsewhere). "Inside 24 hours" also cannot be computed from a date alone. The database has slots on 2026-10-16 itself (3 open, 5 members-only) and 31 existing appointments on 16 and 17 October, so whether the fee applies, and whether this morning's window can still be booked, depends on an unstated time of day.

**Proposed change.** Fix "now" as a date and time with a time zone (for example 2026-10-16 09:00, US Central time) in one setting used everywhere. Apply the $49 notice to both cancelling and rescheduling inside 24 hours. Never offer a window that has already started. Update the rescheduling decision's choice text to match. **Cost:** about 1 hour.

---

### 6. Whole zones have no slots for some services, and the seeded appointments break the zone rule

**Definitely wrong (the data), medium-high severity.**

- `call_data/scheduling_db/SCHEMA.md` line 48: "find `open` slots … matching the customer's zone, the requested service_type, and the requested date/window."
- `docs/DESIGN.md` line 127: "offer the requested slot if open, or nearby alternatives if not;"
- What I measured in `appointment_slots`:
  - The north zone has **no plumbing slots at all**, and 108 of the 154 customers (70 percent) live in the north, including seeded customers Linda Foster (Round Rock) and Daniel Reyes (Georgetown).
  - The central zone (Austin, including seeded customer Grace Okafor) has **no estimate slots**, so no replacement estimate can be booked for any Austin customer.
  - South has only 5 open tune-up slots in three weeks.
- 113 of the 159 existing appointments are in a zone that does not match the customer's city.
- Each technician has slots in both the 12:00-16:00 and the 13:00-17:00 windows on the same day, and the two technicians with both skills (Jun Park, Sam Igwe) have a heating-and-cooling row and a plumbing row for the same window. The seed already holds 19 cases where one technician is booked in both overlapping afternoon windows.

**Problem.** "Offer alternatives" has nothing to offer for a north-zone plumbing request, which is a common call ("my kitchen sink is backing up", "water heater pilot light keeps going out"). The PRD's own words are "complete or decline the booking". The design has no decline path. Following the schema literally also lets one technician be booked twice in overlapping hours. Confirming a seeded appointment will read back a technician from the wrong zone.

**Why the reviewer cares.** A reviewer who tries "book a plumber for Linda Foster" gets a dead end unless decline-and-hand-off is designed. These gaps are the kind of database trap "honesty about the data" is judged on.

**Proposed change.** Add three rules now. (1) If no eligible slot exists in the three-week range for that zone and service, say so plainly and hand off with a ticket ("no plumbing capacity in north zone"). This counts as a clean decline, not a failure. (2) Follow the schema's zone rule for new bookings and leave existing appointments as recorded, with the mismatch documented in the findings. (3) Decide whether to also refuse a slot whose technician is already booked in an overlapping window. I recommend yes: one extra query, about 1 hour. Either way, document the choice. **Cost:** about 2 to 3 hours including test cases.

---

### 7. "Burning smell from the vents" is 16 calls and the safety rule does not classify it

**Unclear, needs confirmation, medium-high severity.**

- `docs/DESIGN.md` line 115: "**Immediate danger** (smell of gas or rotten eggs, carbon monoxide alarm, sparks, smoke or flames from a unit, electrical burning smell with tripped breakers)".
- `call_data/knowledge_base/policies/escalation_and_safety.md` line 9: "Electrical burning smell combined with tripped breakers".
- `call_data/call_transcripts/CALL-20260706-0101.txt` line 8: "I need to schedule a service call. I smell something burning from the vents." The human agent booked a normal visit, as in all 16 such calls.
- `call_data/knowledge_base/faq/troubleshooting_before_you_call.md` line 8: "Reset any tripped breaker once."

**Problem.** A burning smell with no mention of breakers falls between the two safety classes. A keyword check on "burning" escalates all 16 calls (about 4 percent of containment). A check that needs "breaker" books them, as the staff did. If the agent also follows the troubleshooting guide, it may tell a caller with a burning smell to reset a breaker, which is the dangerous combination the safety policy names. The earlier cross-company review noted that staff booked these calls but nobody ruled on the class.

**Proposed change.** Decide now. My recommendation: a burning smell alone is "urgent", so the agent gives a short fixed reply (turn the system off at the thermostat, do not reset breakers, leave if there is smoke) and makes a priority handoff, never a normal booking. Label all 16 test cases that way. Never offer breaker-reset advice in the same conversation as a burning smell. Record it as a decision with the trade-off (about 4 points of containment). **Cost:** 30 minutes plus test cases.

---

### 8. The cut order does not protect the schedule; the heavy work is all marked never-cut or not listed

**Definitely wrong: the applied fix is incomplete. High severity.**

- Suggested-question buttons without caching, and the cut order (D16), `docs/DECISIONS.md` line 228: "Cut order if time runs short: the buttons, then the cost-per-conversation breakdown, the consistency runs, the extra measures beyond the core retrieval and answer set, the adversarial set down to 15 cases, then the threshold curve."
- `docs/DESIGN_PRD_REVIEW.md` line 365, the ruling on "The plan is unlikely to finish": "Noted: addressed by the cut order and never-cut list".
- `docs/PRD.md` line 102: "A smaller system that works and is measured beats a larger one that is neither."

**Problem.** Everything in the cut order is small (perhaps 4 to 6 hours in total). The large items are either never-cut or not mentioned: a second AI simulating callers over 420 transcripts, with re-runs of every failure; three-way labelling of 80 transcripts by two AI models and the author; three retrieval modes plus a second chunking setting; a staff page with flagging, correction notes and export; a reserved budget for a private reviewer link, spending alerts and downtime alerts; a pre-deploy test run; a 30-case adversarial set; the image transcription; and now the account lookups from issue 1. In four days, starting from no code, cutting the buttons and the cost breakdown does not save the plan.

**Proposed change.** Replace the cut order with one that names the big items, and simplify some up front:
- Label templates, not transcripts (issue 3). The author labels each of the roughly 80 templates once, which gives exact labels for all 420 calls in about an hour, independent of any model. This makes the 80-transcript, two-model labelling (D14) unnecessary; keep one model pass only as a cross-check if time allows.
- Run the held-out set as one weighted case per template (about 50 to 60 conversations), not 120 near-duplicates.
- Compare two retrieval modes (keyword-only against combined), not three plus a chunking variant (see the overbuilding section on knowledge-base size).
- Cut the private-link budget reserve, the pre-deploy test run and the flag export before any measured number. Keep flagging itself (it is the first step of the feedback loop).

**Cost:** 1 hour of planning; saves an estimated 1 to 1.5 days.

---

## Remaining findings by area

### 1. Contradictions

**Two current documents disagree on the service area, and the design breaks its own "hand off" rule to resolve it.** *Definitely wrong, medium.*
- Handling stale and conflicting documents (D7), `docs/DECISIONS.md` line 104: "hand off if two current documents still disagree."
- `call_data/knowledge_base/faq/customer_faq.md` line 2: "_Last updated: 2026-03-02_" and line 7 lists the service area without Dripping Springs or Manor.
- `call_data/knowledge_base/policies/service_area.md` line 2: "_Updated 2026-04-01_" and line 13: "**Newly added April 2026:** Dripping Springs (78620) and Manor (78653)."
- `docs/DESIGN.md` line 126: "Dripping Springs and Manor are served (added April 2026)".

The design picks the newer document, which is right, but as written the decision would hand off every service-area question that retrieves both files. **Change:** amend the decision to "the later effective date wins, recorded in a conflict register; hand off only conflicts the register does not settle", and list this pair in the register. **Cost:** 15 minutes.

**The document-handling decision's choice text and evidence no longer match the design or the data.** *Definitely wrong, medium.*
- (D7) `docs/DECISIONS.md` line 104: "Leave the archive folder and the undated old FAQ copy out of search". The design (`docs/DESIGN.md` lines 90 to 92) also excludes `services/scheduling_guide.md` and `services/duct_cleaning.md`, and treats `policies/escalation_and_safety.md` as internal.
- (D7) `docs/DECISIONS.md` line 102: "Current files are dated; stale ones (archive folder, old FAQ copy) are undated". The same claim is in `docs/PRD_REVIEW.md` line 268. This is false: `services/scheduling_guide.md` is dated ("_Rev 2024-11_") but stale, while `services/technician_arrival_and_etas.md` and `faq/troubleshooting_before_you_call.md` have no date but nothing newer replaces them.

**Change:** rewrite the choice as "an explicit document list decides", and drop the "dated means current" claim. **Cost:** 15 minutes.

**The agent-build decision says the AI writes every reply; the design has fixed replies written in code.** *Definitely wrong, low.*
- Agent built as a router plus code-controlled flows (D10), `docs/DECISIONS.md` line 146: "The AI writes every reply."
- `docs/DESIGN.md` line 115: "a fixed reply written in code tells the caller to leave the home immediately".

**Change:** "The AI writes every reply except the fixed safety replies." **Cost:** 5 minutes.

**The model decision still says the grader is "picked in the spec" through an API.** *Definitely wrong, low.* The AI models and services decision (D5), `docs/DECISIONS.md` line 75: "an OpenAI model (picked in the spec) grades test answers". Grading through Codex (D15) changed this, but D5 is not marked as amended. **Change:** add a one-line "amended by" note. **Cost:** 5 minutes.

**The earlier PRD review's answers still describe the replaced scope rule.** *Definitely wrong, low.* `docs/PRD_REVIEW.md` line 242: "A common reason that is risky to automate … is escalated instead. Scheduling counts as one of the three handled reasons if it ranks there". This is the rule replaced by the scope decision (D12). **Change:** add a note pointing to the replacement. **Cost:** 5 minutes.

**The design misdescribes how staff identify callers.** *Definitely wrong, low.* `docs/DESIGN.md` line 124: "identify the customer by account number and name, as the human agents do in the transcripts". The transcripts use three methods: account number and name (131 calls), name and service address (107), name and phone (125). How to handle a missing account number is already left for the spec; I only correct the factual claim, because a simulated caller following a "name and address" transcript will not offer an account number.

### 2. Required items unmet, made optional or at risk

- **Containment target (60 to 75 percent) is at risk for a fixable reason.** See issue 1: without read-only lookups the rough ceiling is about 55 percent.
- **"Answer the top 3 call drivers accurately" through retrieval (PRD line 44) is at risk for billing.** If billing is a top-three driver, the documents answer only the double-charge questions. The two-list approach (D12) is sound, but the findings document should show, per top-three driver, how many calls are answered from documents, how many from database lookups, and how many are handed off and why. *Unclear, needs confirmation, medium.* **Cost:** part of the findings write-up.
- **"Complete or decline the booking" (PRD line 14).** No decline path exists. See issue 6.
- **The schema's "Confirm: look up scheduled appointments" for customers with several appointments.** 42 customers have two to five scheduled appointments. "Move my appointment" needs a "which one?" step. *Unclear, low.* Spec-level, but note it in the rescheduling decision. **Cost:** 30 minutes.
- Literal requirements table: no other item is unmet. Every row in `docs/PRD_REVIEW.md` lines 162 to 193 has a home in the design.

### 3. Things in the data the design has not accounted for

- **The technician-delay document is not classified, and it grants a waiver the design forbids.** *Definitely wrong, medium.* `call_data/knowledge_base/services/technician_arrival_and_etas.md` line 8: "Agents may waive the diagnostic fee for delays over 30 minutes past the window without supervisor approval." It is undated, written for agents, and missing from the design's document list (`docs/DESIGN.md` lines 89 to 92). If it is searchable, the agent may tell a caller "I've waived your fee", against the design's code rule "no waivers". It also says "Appointment windows are 4-hour blocks", but the Tuesday and Thursday evening window is three hours. The 9 "my technician is late" calls need live dispatch data the agent does not have, so they should hand off anyway. **Change:** mark it internal (it feeds the waiver-handoff rule), and add a "technician late" test case. **Cost:** 15 minutes.
- **The troubleshooting guide is a procedure the design ignores.** *Unclear, low-medium.* `call_data/knowledge_base/faq/troubleshooting_before_you_call.md` line 3: "Agents should walk customers through these before booking a non-emergency visit." No human agent in the transcripts does this (0 transcripts mention a filter or breaker). Decide either "offer the matching quick check in one message before booking" or "skip, with the reason", and never combine breaker advice with a burning smell (issue 7). **Cost:** 30 minutes either way.
- **Waitlist promises.** *Unclear, low-medium.* 34 transcripts have staff offering "the waitlist for cancellations". There is no waitlist in the database; only the stale scheduling guide mentions one. Simulated callers will ask. **Change:** one rule: the agent never promises a waitlist; it offers the next open slots, or a handoff ticket marked "wants earlier slot". **Cost:** 15 minutes.
- **Autopay has no document at all.** 14 calls. Under issue 1 these are handed off; list them as a documentation gap in the findings (a real FDE finding for the exec team). **Cost:** none.
- **Duplicate customer names.** *Unclear, low.* 11 names belong to two or three customers (two "Michael Chen" accounts, both in Round Rock), and a transcript "Linda Foster" has a different account number from the seeded one. Name-only lookup must never pick a record. This is covered by the deferred identity question; I add only the data fact.
- **Seeded appointment rows are internally inconsistent.** *Definitely wrong (the data), low.* 87 of 159 appointments have a `created_at` after "today", and issue descriptions do not match service types (for example "Kitchen drain backed up" booked as an `estimate`). Confirming such an appointment reads nonsense back to the caller. **Change:** read back date, window, service type and technician only, never the issue text; set `created_at` on new bookings to the fixed "now". **Cost:** 15 minutes.
- **Membership expiry turns out not to matter in this data.** All 56 members have renewal dates from 2026-11-01 onward, so no member is expired today. The deferred members-only question can be settled in one line ("tier is standard or plus"), with a note that auto-renew makes expiry moot inside the three-week window.
- **Holiday hours fall outside the booking range.** The image's holidays (Thanksgiving 26 to 27 November and later) are all after the last slot (2026-11-05). Transcribing the image is still right for "are you open on Thanksgiving?" questions, but no booking logic needs it.
- **The PDF fee schedule is a table.** "Converted to text" (`docs/DESIGN.md` line 93) should keep row and column pairs ("Diagnostic visit, Comfort Club: Waived"). A plain text dump loses which column a price belongs to. *Unclear, low.* **Cost:** 30 minutes.

### 4. Weak or unjustified decisions, and missing decisions

- **Missing decision: account lookups and actions in scope.** See issue 1.
- **Missing decision: how redirect-only calls count toward containment.** *Unclear, medium.* Wrong numbers (5), hiring questions (6, which the safety policy sends to "careers page on website") and estimate requests are resolved with no human. The design's containment rule ("the agent never handed off, and every request the caller made was graded correct") would count them as contained, adding about 3 points for trivial work. **Change:** decide now; report containment with and without them. **Cost:** 15 minutes.
- **Missing decision: what "containment" means on the live dashboard.** *Unclear, low-medium.* The test definition needs a grade, and live traffic has none. Define live containment as "no handoff, no error, not flagged, not abandoned mid-flow", and say on the dashboard that it is an upper bound. **Cost:** 15 minutes.
- **Call-reason accuracy is measured on 40 cases with a 90 percent target.** *Definitely wrong (statistically), medium.* Ground-truth labels (D14), `docs/DECISIONS.md` line 202: "router accuracy on the held-out 40". At 90 percent on 40 cases the margin of error is about plus or minus 9 points, so the success criterion "Call-reason sorting accuracy: at least 90 percent" (`docs/DESIGN.md` line 194) cannot be confirmed. Template labelling (issue 8) labels all 420 calls and fixes this at no cost. The router also labels single messages, while the labels describe whole calls; score the router on the caller's first substantive message.
- **The grader's model is not fixed or reproducible.** *Unclear, low.* Grading through Codex (D15) uses "the strongest model" on a personal subscription, so the reviewer cannot re-run the grading with the same model. The model name is recorded, which is good; also commit the grader prompt and every verdict, and state in the README that re-grading needs the API fallback.

### 5. Feasibility in four working days

See issue 8. With issues 1 to 7 added (about 1.5 days of new work) and the simplifications in issue 8 (saving about 1 to 1.5 days), the plan is tight but feasible. Without the simplifications, it is not. The work most at risk is the held-out run on day 4: it depends on the test fixtures (issue 2), the agent, the grader and the deployment all being finished. **Change:** run a 10-case held-out "dress rehearsal" at the end of day 3 using the full harness, and freeze the agent after it. **Cost:** 1 hour, which buys schedule certainty.

### 6. Over-built relative to "a smaller system that works and is measured"

- **The retrieval evaluation is large for a very small knowledge base.** *Unclear, medium.* The current customer-facing documents total about 2,100 words (under 3,000 tokens) in roughly 35 sections. The design measures recall, precision, hit rate, mean reciprocal rank, coverage, stale-trap accuracy, faithfulness, answer relevance, citation accuracy and correct refusal, across three retrieval modes plus an alternative chunking (`docs/DESIGN.md` lines 95 to 108). With 35 sections, "top five" covers one seventh of the whole corpus. A reviewer may ask "why retrieve at all?" **Change:** keep the required pipeline, keep the core set already named in the cut order (recall and hit rate at five, stale-trap accuracy, answer correctness, faithfulness), and add one cheap, honest comparison: "whole current knowledge base in the prompt" against retrieval, on answer correctness. That answers the obvious question with a number and shows judgment. Drop precision, mean reciprocal rank and the second chunking setting. **Cost:** saves about half a day; the comparison costs about 1 hour.
- **Three-way labelling (D14).** Replaced by template labelling; see issue 8.
- **An AI simulating callers from the full transcript script.** Kept but narrowed: with caller cards (issue 2) and one case per template (issue 3), it runs about 60 conversations, not 120 plus re-runs.
- **A reserved spending budget for a private reviewer link.** *Unclear, low.* With a $5 daily cap, about $0.06 per conversation and a per-visitor rate limit, the cap allows about 80 conversations a day. A spend alert plus the clean "cap reached" handoff is enough for a prototype; the private-link budget can be described rather than built. **Cost:** saves about 2 hours.

### 7. Should be decided now, not at the spec stage

These items were deferred to the spec in `docs/DESIGN.md` lines 168 to 179 or are new above. Each changes the test set, the containment ceiling or the scope, so they belong at the intent stage:

1. How test cases get a real customer, dates and invoices (issue 2). It blocks day-1 to day-2 work.
2. Which account lookups and actions are in scope (issue 1).
3. The fixed "now" date, time and time zone (issue 5).
4. How the warranty-visit flag is set on a new booking. 45 warranty calls (about 11 percent, the fourth driver) are mostly "book a warranty diagnostic at no charge"; seeded customers Grace Okafor and Daniel Reyes are both inside the 2-year installation labour warranty (`call_data/knowledge_base/warranty/warranty_policy.md` line 10). The rule decides whether those calls count as contained and which reference answers say "no diagnostic fee". Recommended rule: set the flag in code when the install date is within 2 years of "now", or the caller reports a repeat failure of a part repaired within 1 year (staff to confirm); otherwise 0.
5. The no-slot decline rule and the overlapping-technician rule (issue 6).
6. The burning-smell class (issue 7).
7. Whether redirect-only calls count as contained (area 4).

The rest of the deferred list (offer ordering, post-handoff chat wording, staff-page password, latency budget, reset mechanism, rate-limit numbers, simultaneous bookings) can stay at the spec stage.

---

## Decisions that are sound (do not revisit)

- **Reporting honest containment (D1):** reporting the real number with its ceiling is exactly what "would you stake your reputation on it in front of a CEO" rewards.
- **Voice deferred (D3):** voice is optional and four days is already tight; keeping the core text-in, text-out costs nothing.
- **Hosting on Fly.io (D4):** a disk that survives restarts is required by the data README's "bookings must actually write to it"; free hosts fail that.
- **Nightly database reset (D6):** keeps one real database while protecting the demo; correctly left as a PM question.
- **Judging "resolved" (D8):** code checks where exact answers exist, a grader from another company for prose, and a measured human check of the grader.
- **Handoff ticket and staff page (D9):** makes "hands off with enough context" visible at low cost.
- **Router plus code-controlled flows (D10):** policy in code is the only way the members-only, refund and emergency rules cannot be talked around.
- **Two lists for the top-three requirement (D12):** showing the observed top three next to the agent's scope is honest and meets the PRD's wording.
- **Rescheduling, cancelling and confirming in scope (D13):** the schema calls them expected behaviour, and Linda Foster's appointment invites the test (fix only the fee wording, issue 5).
- **Buttons without cached answers (D16):** one answer path, measured like typed text.
- **In the design:** the explicit document list, the code safety check running before the router, booking as a conditional update in one transaction, a separate log database the reset never touches, and evaluation on a fresh database copy are all right and should stay.

---

**Verdict: approve with changes.** The architecture and the evidence-first approach are right, but the intent misreads what the top call drivers need (account lookups, not document answers), cannot yet build a valid test set (no transcript customer exists in the database, and the templated corpus leaks across the split), and the cut order would not save the schedule. All three fixes are cheap if decided now.

---

## Glossary

- **Account lookup:** reading a caller's own record in the database (for example their balance or renewal date) without changing it.
- **Account action:** changing something about the caller's account or money (for example sending a payment link or cancelling auto-renew).
- **Action gap:** the calls the agent could understand but deliberately hands off because they need an action it is not allowed to take.
- **Caller card:** the small set of facts (name, account number, phone, address, request) given to the AI that plays the caller in a test.
- **Call driver / call reason:** why a customer called.
- **Conflict register:** a written list of documents that disagree and which one wins, with the reason.
- **Containment rate:** the share of calls the agent finishes without a human.
- **Containment ceiling:** the highest containment possible given what the agent is allowed to handle.
- **Cut order:** the agreed order in which work is dropped if time runs out.
- **Database transaction:** a group of database changes that all happen together or not at all.
- **Fixture:** prepared test data (for example a planted invoice) loaded into a test copy of the database.
- **Grader:** an AI model that scores whether the agent's answer was correct.
- **Held-out set:** test cases kept aside and not used while tuning, so the final measurement is fair.
- **Hit rate at five / recall at five:** whether, and how much of, the needed text appears in the top five search results.
- **Leakage:** when the same or near-identical examples are used both to tune and to measure, which makes results look better than they are.
- **Margin of error:** how far a percentage measured on a small sample may be from the true value.
- **Mean reciprocal rank / precision:** further search-quality scores (how near the top the first right result is; how many returned results are relevant).
- **Router:** the step that decides which flow a caller's message belongs to.
- **Seeded data:** the starting rows the database ships with, including the four test customers.
- **Simulated caller:** a second AI model that plays the customer in a test conversation.
- **Stratified split:** dividing data so each part keeps the same share of every category.
- **Template (transcript template):** a call pattern that repeats across many transcripts with only names, numbers and filler words changed.
- **Token:** the unit AI models read and write, roughly three-quarters of a word.
- **Zone:** the area (north, central, south) a customer's city belongs to, which decides which technicians and slots apply.

## Rulings

Recorded 2026-10-17. Claude checked the review's main data claims against `call_data/` and they held: none of the 131 transcript account numbers exist in the database; the north zone has no plumbing slots and only the north and south zones have estimate slots; Omar Patel's invoice charges $144 after-hours and an $89 diagnostic fee on top of a repair; the 420 calls open with about 77 distinct requests. All accepted changes are applied to `docs/DESIGN.md`.

| Finding | Ruling |
|---|---|
| Most top-three calls are account lookups and actions | Accepted: three read-only lookups in scope, actions hand off as the action gap (account lookups (D17)). |
| No transcript customer exists in the database | Accepted: caller cards with real database customers and invoice fixtures (test-set construction (D20)). |
| The transcripts are built from templates, so the held-out set leaks | Accepted: split by template, one weighted case per template, margin of error on scenarios (D20). |
| "Explaining invoice line items" is a trap | Accepted: invoice rule in code, Omar Patel as a named test case (data rules (D21)). |
| The 24-hour fee needs a clock time and applies to reschedules | Accepted: fixed "now" of 2026-10-16 09:00 Austin time; fee on both (D21). |
| Whole zones lack slots; seeded appointments break the zone rule | Accepted: clean decline path, overlapping-technician refusal, existing appointments left as recorded and documented (D21). |
| Burning smell has no safety class | Accepted: urgent fixed reply and priority handoff (burning smell (D19)). |
| The cut order does not protect the schedule | Accepted: template labeling replaces the three-way sample (template labeling (D18), replacing (D14)); simplifications and a new cut order naming the big items (simplifications and cut order (D23), replacing (D16)). |
| The service-area documents disagree and the document decision's text no longer matches | Accepted: explicit document list and conflict register; the technician-delay document marked internal (document list and conflict register (D22), replacing (D7)). |
| The build decision says the AI writes every reply | Accepted: the burning-smell decision (D19) records the fixed safety replies as the exception to the build decision (D10). |
| The model decision still names an API grader | Already covered: grading through Codex (D15) amends the models decision (D5). |
| The PRD review's answers describe the replaced scope rule | Fixed: notes added in `docs/PRD_REVIEW.md`. |
| Staff identify callers three ways; duplicate names | Accepted: name plus account number, address or phone, never name alone (D21). |
| Troubleshooting guide, waitlist promises, read-back of issue text, membership tiers, PDF table, warranty flag | Accepted as recommended (D21, D22). |
| Redirect-only calls and live containment | Accepted: containment reported with and without redirect-only calls; live containment labelled an upper bound. |
| Router accuracy on 40 cases; scoring single messages | Accepted: all held-out calls labeled through templates; router scored on the first substantive message (D18). |
| Grader reproducibility | Accepted: grader prompt and verdicts committed; README notes the API fallback. |
| Day-4 risk | Accepted: 10-case rehearsal at the end of day 3, then the agent is frozen (D20). |
| Over-built retrieval evaluation; private reviewer budget | Accepted: two retrieval modes plus a whole-knowledge-base comparison; precision, mean reciprocal rank and a second chunking setting dropped; the reviewer budget described, not built (D23). |
