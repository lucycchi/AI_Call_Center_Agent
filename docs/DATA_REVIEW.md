# Data Review: What the Calls, Documents and Schedule Show

A second look at the challenge data in `call_data/`, done on 2026-10-17 before writing the spec. It covers five views the author chose:

1. what staff achieved on each call (the human baseline);
2. call reasons ranked by staff minutes as well as by call count;
3. whether staff told callers what the current documents say;
4. one table of every fact in the knowledge base, with the conflicts between documents;
5. appointment capacity against demand.

**Method.** The 420 transcripts are highly templated (staff use about 360 distinct lines, and callers open with about 77 distinct requests once names, numbers and filler words are removed), so plain pattern rules can sort them reliably. A short Python script sorted every call by the caller's request and by the staff member's closing lines, checked every number and policy staff stated against the current documents, and counted open appointment slots in the SQLite database. No AI model was used, so the counts are exact and repeatable. Examples of every flagged pattern were read by hand to confirm the rule was right; two rules were corrected that way (one missed a billing wording, one misread a price range). The script lives outside the project (it is exploration, not product code); the discovery step in the build will redo this properly with checked labels (template labeling (D18)).

These counts are a first pass to inform the spec, not the final findings document the PRD asks for.

## 1. Call reasons, staff minutes and the human baseline

| Rank | Call reason | Calls | Share | Staff minutes | Share of minutes | Resolved by staff on the call |
|---|---|---|---|---|---|---|
| 1 | New service booking | 132 | 31% | 296 | 38% | 132 (100%) |
| 2 | Billing | 77 | 18% | 130 | 17% | 53 (69%) |
| 3 | Comfort Club membership | 75 | 18% | 126 | 16% | 75 (100%) |
| 4 | Warranty | 45 | 11% | 75 | 10% | 45 (100%) |
| 5 | Existing appointment (move, cancel, confirm, late technician) | 38 | 9% | 59 | 8% | 38 (100%) |
| 6 | Complaint or request for a manager | 16 | 4% | 26 | 3% | 0 (all called back) |
| 7 | Replacement estimate | 12 | 3% | 23 | 3% | 12 (100%) |
| 8 | Gas smell, carbon monoxide or sparks | 9 | 2% | 13 | 2% | 0 (safety instruction, then callback) |
| 9 | Hiring, commercial work, wrong number | 16 | 4% | 23 | 3% | 0 (redirected) |
| | **All calls** | **420** | | **769** | | **355 (85%)** |

**What it shows:**

- **The top three are the same by count and by minutes:** booking, billing and membership. Booking calls are also the longest (about 2.2 minutes against about 1.7 for billing and membership), so booking is an even larger share of staff time (38 percent) than of calls (31 percent). Billing edges membership by both measures (77 against 75 calls, 130 against 126 minutes). The ranking the agent's scope rests on is therefore stable, not an artefact of counting.
- **The human baseline is 85 percent resolved on the first call,** or about 82 percent after removing 11 calls where the caller asked to book and staff never did (section 2). The calls staff could not resolve are the same kinds the agent hands off: billing disputes and refunds (24), complaints (16), safety emergencies (9), commercial and hiring (11).
- **Staff resolve some calls only because they can take actions.** 47 calls (11 percent) were resolved by an account action the agent will not take: 14 payment links, 13 auto-renew cancellations, 14 autopay set-ups and 6 upgrades. This is the "action gap" the agent reports separately (account lookups (D17)). Comparing the agent's containment with the human 85 percent must account for it: the fair comparison is against the human rate excluding those actions, about 73 percent (308 of 420).

Sub-reasons that matter for the scope:

| Within | Sub-reason | Calls | What staff did |
|---|---|---|---|
| Booking | HVAC repair | 75 | Booked |
| Booking | Plumbing (sink, water heater) | 25 | Booked |
| Booking | Burning smell from the vents | 16 | Booked a normal visit |
| Booking | Tune-up | 16 | Booked |
| Billing | Quote different from invoice | 16 | Billing supervisor callback |
| Billing | Current balance | 15 | Read the balance |
| Billing | Pay an invoice | 14 | Sent a payment link |
| Billing | "What is this invoice for?" | 13 | Explained the line items and emailed a copy |
| Billing | Charged twice | 11 | Explained the pending authorisation |
| Billing | Refund demand | 8 | Billing supervisor callback |
| Membership | What it includes, price | 24 | Answered |
| Membership | Renewal date | 14 | Read the renewal date |
| Membership | Autopay | 14 | Sent a link |
| Membership | Cancel | 13 | Turned off auto-renew |
| Membership | Upgrade | 6 | Upgraded, sent a payment link |
| Membership | Member discount on a new system | 4 | Answered |
| Warranty | Claim | 21 | Booked a warranty diagnostic, or explained coverage |
| Warranty | Registration | 10 | Confirmed registration |
| Warranty | Transfer to a new homeowner | 8 | Explained and emailed the form |
| Warranty | Repeat repair | 6 | Booked a no-charge return visit |

**Timing.** Calls arrive from 7 a.m. to 7 p.m., matching the current FAQ's hours (Monday to Friday 7 a.m. to 7 p.m., Saturday 8 a.m. to 4 p.m.), with a peak at 2 p.m. (54 calls) and 28 calls in the 6 p.m. and 7 p.m. hours. Volume by month: July 156, August 164, September 100.

## 2. Did staff tell callers what the current documents say?

**Prices: always right.** Every price staff quoted matches the current documents: the $89 diagnostic fee, the $189 or $16.99 membership and $99 per additional system, the $269 Plus plan, the 15 percent member repair discount, the $500 member replacement credit, the $8,000 to $16,000 replacement range, the 1-year repair labour warranty and the 24-hour free-cancellation rule. No stale price from the archived documents was quoted in any month.

**Policy: wrong or risky in 108 of 420 calls (26 percent).**

| What staff did | Calls | What the current documents say |
|---|---|---|
| Offered a waitlist for cancellations | 34 | No current document mentions a waitlist; only the stale 2024 scheduling guide does, and the database has none. |
| Booked a "burning smell from the vents" call as a normal visit | 16 | The safety policy treats an electrical burning smell as an immediate safety escalation (with tripped breakers); no staff member asked about breakers. |
| Promised a manager would call back "today" | 16 | Supervisor escalations are a callback within 1 business day; "do not promise a specific outcome". |
| Moved an appointment set for tomorrow without mentioning the $49 fee | 15 | "Cancellations or reschedules more than 24 hours before the window are free. Inside 24 hours there is a $49 late-cancellation fee." |
| Explained an invoice as "the diagnostic fee plus the repair" | 13 | The $89 diagnostic fee is "applied as credit toward the repair if you approve the repair during the same visit." Two explanations are impossible: an $89 invoice described as the diagnostic fee plus a blower motor (a $550 to $950 repair). |
| Caller said "let's schedule it" and staff ended the call without booking | 11 | A dropped request (for example after a compressor warranty answer). |
| Told refund callers they would hear back in two business days | 8 | Supervisor callback within 1 business day. |

**Spread.** Problems appear for every staff member, from 18 percent of calls (Marcus) to 31 percent (Kayla), and in every month (waitlist offers rise from 8 in July to 15 in August and 11 in September). They are systemic: a training and documentation problem, not one person. The late-technician fee waivers staff gave (9 calls) were checked and are allowed: the technician was more than 30 minutes past the window, which the internal delay policy permits.

**What this means for the build:**

- Reference answers must come from the current documents, never from what staff said. The waitlist, the reschedule fee, the burning-smell handling, callback times and invoice explanations would all be copied wrong otherwise.
- The agent should be measured on finishing what the caller asked (a dropped booking is a failure even though the call "ended fine").
- The staff findings are themselves a deliverable for the executive team: 26 percent of calls contain a policy error that an agent following the documents would not make.

## 3. Every fact in the knowledge base, with conflicts

"Current" sources are the documents the agent may search or that feed its rules (document list and conflict register (D22)). "Stale" sources are excluded. "Data" means the database or transcripts.

| Fact | Current value and source | Conflicting value and source | Ruling |
|---|---|---|---|
| Diagnostic fee | $89, waived for members (FAQ 2026-03-02, fee schedule PDF 2026-01-01, price book, catalog 2026-02-10, membership 2026-01-01) | $79 (old FAQ copy) | Current wins; old copy excluded. |
| Diagnostic credited toward an approved repair | Yes (FAQ, catalog) | Invoices charge both; staff explain both (data) | Agent never says a charge is right or wrong; questioned charges hand off as billing disputes (data rules (D21)). |
| After-hours dispatch | $149, waived for members (FAQ, PDF, price book, membership) | $129 (old FAQ); $144 on seeded customer Omar Patel's invoice (data) | Current wins; the invoice is a planted billing trap. |
| Holiday dispatch | $199 (holiday hours image, price book) | none | |
| Late cancellation or reschedule | $49 inside 24 hours (FAQ, PDF, price book) | 48 hours' notice (stale 2024 scheduling guide) | Current wins; the fee applies to reschedules too. |
| No-show | $89 non-members, $0 members (PDF); "full diagnostic fee" (FAQ) | none | Consistent. |
| Phone hours | Monday to Friday 7–7, Saturday 8–4 (FAQ) | 8–6 and 9–1 (old FAQ) | Current wins. |
| Appointment windows | 8–12, 12–4, 1–5, plus 4–7 on Tuesday and Thursday (FAQ, schema) | 8–12 and 12–4 only (old FAQ); "4-hour blocks" (technician delay document, wrong for the 3-hour evening window) | FAQ and schema win. |
| Membership, standard | $189 a year, $16.99 a month (12-month minimum), $99 per extra system, 15% off repairs (membership, PDF) | $149, $12.99, $79, 10% off (archived overview) | Current wins. |
| Membership, Plus | $269 a year, adds water heater flush, plumbing inspection, 15% off plumbing (membership, PDF) | $219 (archived overview) | Current wins. |
| Membership cancellation | Cancel auto-renew any time; non-refundable once a tune-up is done; prorated refund in the first 60 days if no tune-up (membership) | Full prorated refund any time (archived overview) | Current wins. |
| Membership transfer | Stays with the address, transfers to the next homeowner (membership) | Moves with the homeowner to a new address (archived overview) | Current wins. |
| Price after renewal | Existing members keep their price until renewal, then the current price applies (membership) | none | So the renewal price is always $189 or $269. |
| Repair labour warranty | 1 year on the repaired part (warranty policy 2025-06-15) | 90 days (2023 warranty terms) | Current wins. |
| Installation labour warranty | 2 years; 5 years for members at installation (warranty policy) | 1 year; 2 years for members (2023 terms) | Current wins. |
| Manufacturer registration | Meridian registers every install within 30 days (warranty policy) | Only on request (2023 terms) | Current wins. |
| Service area | Adds Dripping Springs and Manor (service area 2026-04-01) | FAQ 2026-03-02 list without them; database zone map without them | Later date wins; their bookings hand off. |
| Not serviced | San Marcos, Bastrop (FAQ), plus Elgin, Lakeway west of 620 (service area) | none | Union of both lists. |
| Emergencies | Never booked; leave the home and call 911 or the gas utility for immediate danger (safety policy, schema) | Booked into same-day overflow slots (stale 2024 scheduling guide) | Current wins. |
| Waitlist | none | Offered (stale 2024 scheduling guide; staff in 34 calls) | Agent never promises one. |
| Fee waiver for a late technician | Agents may waive past 30 minutes (internal delay document, internal discretion notes) | none | Agent hands off waiver requests; it has no authority. |
| Supervisor callbacks | Within 1 business day (safety policy) | "Today" and "two business days" (staff) | Agent states 1 business day. |
| Payments | No card numbers by phone; secure link valid 24 hours; no checks or cash in the field (FAQ) | Checks accepted (old FAQ) | Current wins; payment requests hand off. |
| Financing | Repairs over $1,000 and all replacements (FAQ) | none | |
| Duplicate charges | Pending authorisation drops in 3 to 5 business days (FAQ) | none | |
| Replacement | Free estimate; typical $8,000 to $16,000; $500 off for members (catalog, PDF, membership) | none | |
| Tune-up | $129 non-members, included for members (catalog, price book, PDF) | none | |
| Duct cleaning | Third-party partner referral (catalog) | "TODO" placeholder (duct cleaning file) | Placeholder excluded. |
| Autopay | No document | Asked in 14 calls | Documentation gap; hand off. |

**Gaps for the executive team:** no document covers autopay (14 calls), the waitlist staff keep offering (34 calls), or how invoices should apply the diagnostic credit.

## 4. Appointment capacity against demand

"Today" is Friday 2026-10-16. Slots run to Thursday 2026-11-05: 528 slots, of which 323 are open, 42 members-only, 159 booked and 4 blocked.

| Zone | Customers in the database | Cities named by callers in the transcripts | Bookable slots (open plus members-only) | HVAC repair | Tune-up | Plumbing | Estimate |
|---|---|---|---|---|---|---|---|
| North (Round Rock, Cedar Park, Pflugerville, Georgetown, Leander, Hutto) | 108 (70%) | 76 (66%) | 114 (31%) | 54 | 26 | **0** | 34 |
| Central (Austin) | 15 (10%) | 0 (0%) | 145 (40%) | 52 | 19 | 74 | **0** |
| South (Kyle, Buda) | 31 (20%) | 39 (34%) | 106 (29%) | 29 | **7** | 40 | 30 |

Booking demand in the transcripts: HVAC repair (including burning smell) 91 calls (69 percent), plumbing 25 (19 percent), tune-ups 16 (12 percent), plus 12 replacement-estimate calls.

**What it shows:**

- **Capacity is in the wrong place.** The north zone holds 70 percent of customers and two-thirds of the callers who name a city, but only 31 percent of bookable slots, and no plumbing at all, although plumbing is 19 percent of booking demand. The central zone holds 10 percent of customers, no caller in the sample named Austin, yet it has 40 percent of slots, including 74 plumbing slots and no estimate slots.
- **South tune-ups are nearly gone:** 7 bookable in three weeks.
- **For the agent:** many realistic requests have no slot to offer (any north plumbing call, any Austin estimate), so the clean decline path (data rules (D21)) is a common case, not an edge case. Test cases must include it.
- **For the executive team:** rebalancing technicians from central to north, and adding a plumbing-skilled technician in the north, would do more for wait times than any agent. This is the kind of operational finding a Forward Deployed Engineer is expected to surface.

## 5. What this changes for the spec

1. The top three call reasons are booking, billing and membership, confirmed by both count and minutes. The spec can name them, subject to the labeled discovery step.
2. The containment comparison should be against the human first-call rate excluding account actions (about 73 percent), alongside the raw 85 percent.
3. Reference answers come from the current documents; the seven staff error patterns above become named test cases.
4. "Finished what the caller asked" is part of a correct outcome (no dropped bookings).
5. The clean decline is a common path and must be tested in every zone with a gap.
6. The fact table above is the starting conflict register and the source of the stale-trap test questions.
7. The findings document should carry three executive findings: the staff policy-error rate, the capacity misallocation, and the documentation gaps.

## Glossary

- **Call reason (call driver):** why a customer called, such as booking a repair or asking about a bill.
- **Template:** a call pattern repeated across many transcripts with only names, numbers and filler words changed.
- **Human baseline / first-call resolution:** the share of calls staff resolved during the call itself, without a callback or transfer.
- **Account action:** a change to the caller's money or membership, such as sending a payment link or turning off auto-renew.
- **Action gap:** calls the agent understands but hands off because they need an account action.
- **Staff minutes:** total call duration from the transcript index, a measure of staff workload.
- **Policy error:** a staff statement or action that contradicts the company's current documents.
- **Conflict register:** a list of facts on which documents disagree, with which one wins and why.
- **Stale document:** an outdated document excluded from what the agent can search.
- **Bookable slot:** an appointment slot marked open, or members-only for members.
- **Zone:** the area (north, central, south) a customer's city belongs to, which decides which technicians and slots apply.
- **Clean decline:** telling the caller plainly that no slot is available and handing off, counted as correct behaviour.
- **Pending authorisation:** a temporary hold on a card that disappears after a few days; it is not a real charge.
