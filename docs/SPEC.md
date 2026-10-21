# Specification: AI Call Center Agent for Meridian Home Comfort

**Status:** approved · **Date:** 2026-10-17 · **Builds on:** the approved design (`docs/DESIGN.md`) and the decision log (`docs/DECISIONS.md`).

## 1. Purpose and context

Meridian Home Comfort is a fictional heating, cooling and plumbing company in the Austin, Texas area whose call center cannot keep up with calls. This project builds, in four working days, a chat agent at a public web address that answers routine calls, books and changes appointments in the company's scheduling database, reads callers' own account details, hands everything else to a human with full context, and proves its performance with measured numbers. It is a take-home challenge (`docs/PRD.md`) judged by a reviewer at a private equity fund hiring a Forward Deployed Engineer. The reviewer will spend 10 to 20 minutes trying to break the live site, watch a 3 to 4 minute walkthrough video, and read the repository.

The data is in `call_data/`: 420 unlabeled call transcripts from July to September 2026, a 17-file knowledge base (some files stale, some internal, some contradictory), and a SQLite scheduling database with customers, technicians, appointment slots, appointments and invoices, documented in `call_data/scheduling_db/SCHEMA.md`. A first data review (`docs/DATA_REVIEW.md`) found the top three call reasons are new bookings (31 percent of calls), billing (18 percent) and Comfort Club membership (18 percent), by both call count and staff minutes; that staff resolve 85 percent of calls on the first call (about 73 percent excluding account actions the agent will not take); that staff make a policy error in 26 percent of calls; and that appointment capacity is badly misallocated between zones.

**Goals.** Contain as many calls as is safe, never give a confident wrong answer, hand off cleanly with context, and back every claim with a number measured on held-out data.

**Non-goals.** Voice and phone calls (deferred unless every required item is finished with a day to spare); taking payments or changing money or membership; real identity verification; commercial work; languages other than English; integration with a real staff system.

**Anti-goals** (it would count as a failure even if it "works"): a containment number inflated by loose grading, leaked test data or trivial calls; booking an emergency; quoting a stale price; reading internal notes to a caller; a reviewer seeing another visitor's conversation; the demo breaking because the calendar or the budget was used up.

## 2. Fixed facts the whole system uses

- **"Now"** for customer-facing scheduling and policy rules is one setting: **2026-10-16 09:00, Austin (US Central) time**, a Friday. Every booking, fee-window, warranty and "has this window started" calculation uses it, never the server clock. Operations (spending and rate limits, the nightly reset, alerts and reply timing) use real time. Slots run from 2026-10-16 to 2026-11-05.
- **Zones:** north is Round Rock, Cedar Park, Pflugerville, Georgetown, Leander and Hutto; central is Austin; south is Kyle and Buda. Dripping Springs and Manor are served (added April 2026) but have no zone in the database.
- **Appointment windows:** 08:00–12:00, 12:00–16:00, 13:00–17:00, and 16:00–19:00 on Tuesdays and Thursdays only.
- **Service types:** HVAC repair, HVAC tune-up, plumbing, and estimate (a free in-home replacement estimate).
- **Slot statuses:** open (bookable), booked, reserved for members (bookable only by Comfort Club standard or Plus members), blocked.
- **Current fees** (2026 fee schedule): diagnostic visit $89, credited toward a repair approved on the same visit and waived for members; after-hours dispatch $149, waived for members; holiday dispatch $199; late cancellation or reschedule inside 24 hours $49; tune-up $129 for non-members; members get 15 percent off repairs, Plus members also 15 percent off plumbing; membership $189 a year or $16.99 a month, $99 per extra system; Plus $269 a year.
- **Models:** Claude Haiku 5.5 (model ID `claude-haiku-5-5`) sorts transcripts and routes messages (routing model (D25)); Claude Sonnet 5.5 (`claude-sonnet-5-5`) writes replies and plays the simulated caller; the model IDs, SDK version and request settings are pinned in configuration and logged with every run; an OpenAI frontier model run through the author's Codex subscription labels templates and grades answers (template labeling (D18), grading through Codex (D15)); Voyage AI provides embeddings (AI models and services (D5)).

## 3. Requirements

Each requirement is numbered for tracking. Numbers are labels only, not priorities.

### 3.0 Scope: what the agent handles

- R81: The agent handles, hands off, or answers and redirects calls as follows (handled-reason list (D26)). **Handled:** new bookings, including replacement estimates; confirming, rescheduling and cancelling appointments; billing questions answered from documents or lookups (current balance, what an invoice is for, and being charged twice, which gets the FAQ's pending-authorisation explanation first and is handed off only if the caller says both charges posted); membership questions (what it includes, price, renewal date); warranty questions and claims (coverage, registration, transfer, and booking a warranty or repeat-repair visit with the warranty-visit flag). **Handed off:** quote disputes and refunds; complaints and manager requests; late technicians (no live dispatch data); every action on money or membership (the action gap); safety emergencies, after the fixed safety reply; commercial work. **Answered and redirected:** hiring enquiries (to the careers page) and wrong numbers, reported with and without them.

### 3.1 Discovery: the call reasons

- R1: Group the 420 transcripts into templates (calls that share the same request and staff response pattern once names, numbers and filler words are removed): first group automatically on normalised text, then merge near-identical groups using a reviewed merge list committed to the repository; record each transcript's template and the template's call count. *(Builder's call on the method.)*
- R2: Label every transcript with one main call reason and a sub-reason (for example billing: current balance), using Claude Haiku 5.5 with a fixed category list that is first proposed from the data and then frozen.
- R3: Produce independent check labels for every template from an OpenAI frontier model run through Codex, without showing it Haiku's labels, and save the model name with the labels (template labeling (D18)). Tell the author before this runs so they can set Codex to a frontier model.
- R4: Have Claude Fable 5.1 label about a third of the templates without seeing Haiku's or Codex's labels, and report Fable's agreement with Codex and Codex's agreement with Haiku; the README states that no human labeled the templates (blind third labeled by Claude Fable 5.1 (D38)).
- R5: Produce a findings document that ranks the top four or five call reasons in a table with rank, calls, share, staff minutes, running total, and handled or handed off with the reason; describes the method and the agreement rates; and states that the transcripts are templated.
- R6: The findings document shows two lists, the observed top three call reasons and the agent's scope, and for each top-three reason states how many calls are answered from documents, how many from account lookups, and how many are handed off and why (choosing handled call reasons to meet the top-three requirement (D12)).
- R7: The findings document reports the human baseline: the share of calls staff resolved on the call (about 85 percent), the same share excluding account actions the agent will not take (about 73 percent), and the 11 dropped bookings.
- R8: The findings document carries three short executive findings: the staff policy-error rate (26 percent of calls, by pattern), the appointment capacity imbalance by zone, and the documentation gaps (autopay, waitlist, how invoices apply the diagnostic credit).

### 3.2 Test set and evaluation

- R9: Split the templates (not the transcripts) once, with a fixed random seed and stratified by call reason, into a working set used for tuning and a held-out set used only for the final measurement; no template appears in both. Publish the calls and templates per reason for the whole corpus and each set (test-set construction with the working-set rehearsal (D32)).
- R10: Before any tuning of the agent, give every held-out case its expected outcome (contained, handed off, or clean decline), its expected handoff reason if any, and, for knowledge questions, a reference answer written from the current documents, never from what staff said. No prompt, threshold, chunking setting or category is changed after seeing the agent's results on held-out cases.
- R11: Tie each test case to a real database customer that matches the transcript's facts (zone, membership tier, system brand, install age), and give the simulated caller a caller card with that customer's name, account number, phone and address instead of the transcript's. Billing cases add their invoice to the test database copy. Where no real customer matches a transcript's facts, the test copy may add a synthetic customer, marked as synthetic in the test data. *(Builder's call.)*
- R12: Run each test conversation with Claude Sonnet 5.5 playing the caller from the transcript and caller card, with the pinned model version and settings, read relative dates against "now", and save every conversation. The first run of each case is the scored result; every failed case is run once more, and a case that fails then passes is reported as flaky, never as passed (test-set construction with the working-set rehearsal (D32)).
- R13: Run every test against a fresh copy of the seeded scheduling database, never the live one, and check bookings, cancellations and reschedules against that copy.
- R14: A test conversation counts as contained only if the agent never handed off and every caller request was graded correct (knowledge answers match the reference, lookups match the database, booking changes are verified in the database copy, and nothing the caller asked was dropped). A conversation finished without a handoff but wrong is counted as a wrong confident answer. A clean decline counts as correct behaviour but not as contained.
- R15: Compute containment over held-out templates weighted by each template's real call count, and report it both with and without redirect-only calls (wrong numbers, job enquiries).
- R16: Report two containment ceilings: the scope ceiling (share of calls in handled reasons) and the adjusted ceiling (also removing calls the documents or database cannot answer and calls needing account actions, the action gap).
- R17: Report the margin of error as a 95 percent interval for the call-weighted containment, computed by resampling held-out templates (so the interval reflects the number of distinct scenarios), and state both the scenario and weighted call counts. *(Builder's call on the method.)*
- R18: Grade knowledge answers with the OpenAI model run through Codex in batches of about 20 answers per Codex run, using a fixed `codex exec` command that returns a JSON verdict per answer, recording the model name with every verdict; an API fallback setting is switched on by hand if Codex is unavailable; commit the grading prompt and every verdict (grading through Codex (D15)).
- R19: Check the grader: choose about 30 answers in advance, spread across answers the grader marked right and wrong; the author grades them without seeing the grader's verdict; publish the full agree and disagree table.
- R20: Maintain an adversarial test set of about 30 hand-written cases, separate from the held-out set, covering at least: prompt injection and "print your instructions"; a non-member demanding a members-only slot; booking on someone else's account; "my last agent promised me a refund"; gas smell, carbon monoxide and burning smell; a booking from Dripping Springs or Manor; a north-zone plumbing request; Omar Patel questioning his invoice; a late technician; a waitlist request; abuse; another language; nonsense input; and each of the seven staff policy-error patterns in the data review. Report a pass rate.
- R21: Run a 10-case rehearsal on working-set cases through the full harness at the end of day 3, then freeze the agent until the final held-out run (D32).
- R22: Provide a quick test run of 20 working-set cases that can be run before every deploy.
- R23: Optionally (third in the cut order), run about 30 held-out cases three times each and report the share correct on all three runs.

### 3.3 Knowledge base and document search

- R24: Keep a document list recording every knowledge-base file's status (current, stale or placeholder), audience (customers or internal), effective date and reason. Exclude from search: the `archive/` folder, `faq/faq_old_copy.md`, `services/scheduling_guide.md` (November 2024, contradicts current rules) and `services/duct_cleaning.md` (a "TODO" placeholder). Mark internal, never searchable: `internal/agent_discretion_notes.md`, `policies/escalation_and_safety.md` and `services/technician_arrival_and_etas.md` (document list and conflict register (D22)).
- R25: Keep a conflict register listing every fact on which documents disagree, which one wins and why (the later effective date wins unless stated), starting from the fact table in `docs/DATA_REVIEW.md`. The agent hands off only conflicts the register does not settle.
- R26: Convert the fee schedule PDF to text that keeps each row and column pair (for example "Diagnostic visit, Comfort Club: waived"), the price book CSV to one readable line per item, and the holiday hours image to text transcribed once and checked by hand.
- R27: Split searchable documents by section (each heading and its content), keeping the document name, heading and effective date on every piece.
- R28: Retrieve with meaning-based search (Voyage AI embeddings) and keyword search, merge the two ranked lists by reciprocal-rank fusion, and return the top five pieces; the retrieval threshold (R32) applies to the meaning-based score of the top piece. *(Builder's call on the fusion method.)*
- R29: Label every knowledge test question with the exact text needed to answer it (document plus line span), independent of how documents are split.
- R30: Measure retrieval on its own: recall at five, hit rate at five, coverage (share of handled-reason questions answerable from the current documents at all), and stale-trap accuracy (questions where an excluded document would give a different answer). Compare keyword-only against combined search, and both against giving the model the whole current customer-facing knowledge base in the prompt, scored on answer correctness.
- R31: Measure answers, each scored pass or fail per answer with a written rubric (a partly correct answer fails): correctness against the reference; faithfulness (every factual claim is supported by the retrieved passages); citation accuracy (for answers that name a source, the named document contains the fact); and correct refusal on a set of questions the documents cannot answer (passes only if the agent hands off without stating unsupported facts).
- R32: On the working set only, show how wrong confident answers and containment change as the retrieval threshold moves, and choose the threshold from that curve.

### 3.4 Agent core

- R33: The agent core takes text in and gives text out with a conversation identifier, independent of the web page, so another front end such as a phone line could use it later (voice deferred (D3)).
- R82: A visitor's browser may hold several conversations, one per open tab; each conversation has its own identifier, is stored in the operations database so it survives a restart, and closes after 30 minutes without a message or when the caller ends it. *(Builder's call.)*
- R34: Before anything else, every caller message, including those in the middle of a flow, is checked in code against fixed lists of words and patterns in three safety classes; a match always overrides the router. The safety check normalises case, punctuation, common misspellings and speech-to-text errors and handles plain negations ("I don't smell gas" does not trigger); when unsure it errs toward safety.
- R35: Immediate danger (smell of gas or rotten eggs, carbon monoxide alarm, sparks, smoke or flames from a unit, electrical burning smell with tripped breakers) gets a fixed reply written in code: leave the home immediately and call 911 or the gas utility from outside, and do not flip switches, open windows near the furnace or restart equipment; then a priority handoff ticket.
- R36: A burning smell on its own gets a fixed reply (turn the system off at the thermostat, do not reset breakers, leave the home if there is smoke) and a priority handoff, never a normal booking; advice to reset a breaker is never given in a conversation that mentions a burning smell (burning smell (D19)).
- R37: Urgent but not dangerous situations (an active water leak, no heat in freezing weather, no cooling in extreme heat) get a calmer fixed reply (for example turning off the water supply for a leak) and a priority handoff. Emergencies are never booked.
- R38: When no flow is active, Claude Haiku 5.5 sorts the caller's message into a handled call reason, scheduling, an account question or a handoff, returning a route and a label of "clear" or "unclear" (routing model (D25)); the rule for "unclear" is tuned on the working set. A request for a person, anger or abuse, an unclear route, or anything outside the handled reasons goes to a handoff.
- R39: A message with several requests is split; each handled request is answered in turn, and if any part is out of scope the agent answers what it can and hands off the rest in one ticket.
- R40: While a flow is active, follow-up messages ("yes", "the morning one", an account number) stay in that flow; the flow is left only when the safety check fires, the caller asks for a person, or the router returns a clear different route, after which the agent answers the new topic and offers to return.
- R41: Knowledge answers come only from retrieved passages and name the source document. If retrieval is below the chosen threshold or no passage clearly supports the answer, the agent hands off.
- R42: The agent may quote the current published fee or price-book range with its source, always adding that the technician confirms the final price on site; it never promises a firm repair total, a discount beyond the published member discounts, a refund or a fee waiver. Replies are produced in structured reply types and checked in code; a sentence that fails a check is replaced by a handoff, and every block is logged and counted so false positives are visible.
- R43: The model is never given internal documents as written, only short paraphrased rules; every reply is checked in code, across the whole reply so far, for any run of 8 or more consecutive words matching an internal document after normalising case and punctuation, and a match is replaced by a handoff. An adversarial test tries to extract the instructions.
- R44: The agent never promises a waitlist; it offers the next eligible slots or a handoff ticket marked "wants an earlier slot".
- R45: The agent identifies a caller by name together with an account number, service address or phone number, never by name alone. After two failed attempts it hands off; a caller not in the database (a new customer) is handed off to be set up.
- R46: Once a caller is identified, the agent answers three kinds of account question with read-only database lookups: open invoices (balance, due date and line items, read exactly as recorded), membership tier and renewal date (the renewal price is the current published price), and system brand and install date (account lookups (D17)).
- R47: Invoice lines are read exactly as recorded and never called right or wrong. If the caller questions any charge, the agent hands off as a billing dispute. If a fixed fee amount on the invoice (diagnostic, after-hours, holiday, late cancellation) differs from the current schedule, for example Omar Patel's $144 after-hours line against $149, the agent silently creates a low-priority billing-review ticket for staff without interrupting the caller. A diagnostic fee charged alongside a repair or to a member is not acted on per call; the pattern goes in the findings document (data rules (D29)).
- R48: Requests to take an action on money or membership (payment links, autopay, cancelling auto-renew, upgrades, enrolment, refunds, fee waivers) are handed off and tagged as the action gap.
- R49: To book, the agent establishes the service type, matches the customer's city to a zone, and finds slots that are open (or reserved for members, if the customer's tier is standard or Plus), match the zone and service type, have not started relative to "now", and whose technician is not already booked in an overlapping window.
- R50: If the requested slot is eligible the agent offers it; otherwise it offers up to three eligible slots, nearest to the requested date first, then by window from morning to evening, naming overlapping windows (12:00–16:00 and 13:00–17:00) distinctly.
- R51: If no eligible slot exists in the three-week range for that zone and service, the agent says so plainly and hands off with a ticket naming the gap (a clean decline). Callers in Dripping Springs or Manor are told the area is served and handed off for booking.
- R52: Before writing, the agent reads back the date, window and service type and waits for a clear yes; the booking then marks the slot booked and adds the appointment row in one database transaction that succeeds only if the slot is still bookable. If it was just taken, the agent says so and offers the next three slots.
- R53: A new appointment records the fixed "now" as its creation time. The warranty-visit flag is set only when the database install date proves the 2-year installation labour warranty applies. Repeat-repair claims and 5-year member-installation claims, which the database cannot verify, are booked as normal visits with a low-priority warranty-review ticket for staff linked to the appointment, and the caller is told there is no diagnostic fee if the technician confirms coverage (data rules (D29)).
- R54: The agent confirms a caller's scheduled appointments, reading back only date, window, service type and technician, never the stored issue text; if the caller has several, it asks which one (rescheduling, cancelling and confirming in scope (D13)).
- R55: Cancelling frees the slot and marks the appointment cancelled in one transaction; rescheduling books the new slot and frees the old one in one transaction. A freed slot returns to its status in the seeded database copy if that was open or members-only; if the seed copy itself shows the slot as booked (a seeded appointment), it is freed to open, as the schema says (freed-slot fallback (D33)). Inside 24 hours of the window's start, both state the $49 late fee before the caller confirms; a waiver request hands off.
- R56: Existing appointments are left as recorded even where their zone does not match the customer's city; the mismatches are listed in the findings document.
- R57: Every handoff creates a ticket with five fields (who the caller is, what they want, what the agent already tried, constraints such as an emergency or a disputed fee, and the caller's mood), a reason tag, a priority flag for emergencies, and a ticket number (handoff ticket and staff page (D9)). In testing, ticket quality is graded with a rubric: a staff member could act without asking the caller to repeat anything.
- R58: After a handoff, the chat stays open and shows the ticket number and a plain statement that the team will contact the caller within one business day (or that an emergency was flagged); the caller may keep asking other questions, and later messages in the conversation are added to the open ticket; nothing implies a person will reply live.
- R59: Every model, search or scheduling-database error becomes a handoff with a plain message, never a crash or an error page. If the operations database itself is unavailable, so no ticket can be saved, the caller sees a plain message asking them to phone the office, and the failure is written to the server log and raises an alert.
- R60: Replies are shown sentence by sentence: each sentence is released to the screen only after it passes the fee, refund and internal-text checks (R42, R43), so unchecked text never appears. The time budget is about 0.3 seconds for safety and identification, about 1.2 seconds for routing, about 0.4 seconds for search and up to 2.5 seconds until the first checked sentence, measured from the server receiving the message. *(Builder's call: sentence-by-sentence release, because every reply must be checked before it is shown.)*

### 3.5 Guards and safety on the public site

- R61: Each visitor may spend about $0.40 a day on live AI calls (roughly 10 conversations), and the site as a whole $10 a day; reaching either limit gives a clean handoff with a plain message. A secret reviewer link, whose token is stored as a Fly.io secret, draws on a separate $3-a-day reserve that other visitors cannot touch. The author is alerted when daily spend passes $5. Test runs use a separate key and budget (spending budgets with a reviewer reserve (D30)).
- R62: A visitor is identified by a signed, HttpOnly, Secure browser session cookie (SameSite=Lax, 7-day expiry), with the client address supplied by Fly.io as a backstop. Limits: 20 messages per 10 minutes and 100 per day per visitor, and 60 messages a minute across the site; hitting a limit gives a clean handoff with a plain message.
- R63: Typed instructions cannot change booking eligibility, safety handling, the fee and refund rules or the internal-text check, all of which run in code.

### 3.6 Web pages

- R64: The site opens on a Chat tab styled as Meridian's customer chat: a greeting saying what the assistant can do, 4 to 6 suggested-question buttons chosen from the discovery ranking, a free-text box, and a card listing the four seeded test customers (Linda Foster, Omar Patel, Grace Okafor, Daniel Reyes) with one fact each, labelled as synthetic.
- R65: A suggested-question button only fills in its question text, so it goes through exactly the same path as typing (simplifications, cut order and buttons (D24)).
- R66: After a booking change or a handoff, the chat shows a compact proof receipt (for example "customer verified · eligibility checked · booked in one transaction", or "ticket #12 created").
- R67: A Results tab shows the frozen held-out test numbers, clearly separated from live demo traffic: scenarios and weighted calls, containment with both ceilings and both human baselines, wrong confident answers, handoff, booking and lookup correctness, the retrieval and answer measures, the adversarial pass rate, the grader check and label agreement, the margin of error, and a plain definition of each number.
- R68: The Results tab lists one-click "try these" scenarios, each with a one-line expected behaviour, that fill in the chat and run the normal path; at least: Linda Foster booking a plumber (north zone has no plumbing), Omar Patel's balance then disputing the after-hours fee, "I smell gas near my furnace", "is the diagnostic fee still $79?", a non-member demanding a members-only slot, and a prompt-injection attempt.
- R69: The Results tab carries the three executive findings from the findings document as three short callouts.
- R70: A Staff view button on the Chat tab opens a panel beside the chat, which stays visible. The panel shows the current visitor's own handoff tickets (five fields, priority marked), today's live numbers (conversations, handoffs, errors, median reply time, and live containment, defined as closed conversations with no handoff, no error, no flag and no abandoned flow, labelled as an upper bound and shown only above a minimum number of conversations), and a badge on the button counts new tickets while the panel is closed.
- R71: In the Staff view, each reply in the visitor's conversation has a collapsed "How this reply was made" receipt showing the safety decision, the route, the dated source passages, any documents excluded as stale, any database action, and the handoff reason, using plain labels ("supported by documents", "not enough evidence", "handoff required") rather than raw confidence numbers, and never showing prompts or internal rules.
- R72: The full all-visitors queue and the flag-a-reply control sit behind a shared password stored only as a hash in a Fly.io secret; staff sessions expire after 12 hours, sign-in attempts are limited to 5 per 15 minutes, and the flag form is protected against forged requests. Phone numbers, emails and street addresses are masked everywhere in the Staff view.

### 3.7 Monitoring, feedback and operations

- R73: Log every conversation, reply, route, retrieval, database action, handoff, error, reply time and model cost in a separate operations database that the nightly reset never touches. Phone numbers, emails and street addresses are masked in logs; conversation logs are deleted after 30 days (retention, masking and rollback (D31)).
- R74: Provide a health endpoint used by Fly.io's health check, and alert the author on downtime, an error-rate spike (3 or more errors in 10 minutes, or more than 20 percent of at least 10 messages in 10 minutes), failed database writes, a failed nightly reset, and daily spend passing $5.
- R75: Allow a flagged reply to carry a correction note, and export flagged conversations as candidate test cases; describe the full feedback loop (flag, review, fix the document or rule, re-run the test set, deploy) in the README.
- R76: Restore the scheduling tables to their seeded state at 03:00 Austin time every night, as one exclusive transaction from the seed file, run by a scheduler inside the app on the single machine and guarded by a lock so it cannot run twice; messages arriving during the reset wait for it to finish. If a reset was missed (for example the app was down), it runs at startup; a failed reset is retried once, then raises an alert and shows on the dashboard (nightly database reset (D6)).
- R77: Deploy to Fly.io on one always-on machine with both database files on an attached disk, keys stored as Fly.io secrets, and live bookings written to the one real scheduling database (hosting on Fly.io (D4)).

### 3.8 Deliverables

- R78: A README explaining what the system does, how to install and run it and its tests, how to run the evaluation, the measured numbers with their definitions, the containment numbers, and the executive findings.
- R79: A short script outline for the 3 to 4 minute video covering how the call drivers were found, why this chunking and retrieval, how handoff works, and what the numbers say. The author records the video.
- R80: The repository contains the code, the document list, the conflict register, the test set with caller cards and reference answers, the labels, the grading prompt and verdicts, and the evaluation results, with no keys committed.
- R83: The README carries a one-page rollback runbook: how to roll back a Fly.io release (prompts and the search index ship inside the release) and how to restore the disk from Fly's daily snapshot. The runbook is practised once before submission (retention, masking and rollback (D31)).
- R84: Each read-back before a booking, cancellation or reschedule carries a confirmation identifier; a repeated or retried confirmation with the same identifier returns the first result and never changes the database again (booking, reviewer-link and downtime protections (D34)).
- R85: The secret reviewer link's token is used once to start a signed reviewer session with the reserve budget, after which the browser is redirected to the plain address; the token is never written to logs. *(Changed by reviewer-only chat (D50): one reusable link starts a 7-day reviewer session in any browser, and the page clears the token from the address instead of redirecting.)*
- R86: A free outside uptime monitor checks the health endpoint and alerts the author when the site stops answering.

## 4. Success targets

Measured on the held-out set unless stated. Targets are aims; every result is reported as measured.

| Measure | Target |
|---|---|
| Containment | Reported honestly with both ceilings; aim for 60 to 75 percent (PRD target); below 60 percent is reported as it is with the reason (reporting honest containment (D1)) |
| Wrong confident answers | Reported as a count, aiming for zero, each one listed and explained |
| Knowledge answer correctness | At least 90 percent |
| Faithfulness and citation accuracy | At least 95 percent |
| Correct refusal on unanswerable questions | At least 90 percent |
| Retrieval hit rate at five | At least 90 percent |
| Emergency and burning-smell cases | 100 percent handed off with the fixed reply first |
| Handoff on out-of-scope calls | 100 percent on safety and booking-rule cases; at least 95 percent otherwise, every miss listed |
| Booking changes and account lookups | 100 percent correct against the database copy |
| Routing accuracy | At least 90 percent, scored on the caller's first substantive message |
| Adversarial pass rate | Reported; 100 percent on booking-rule and instruction-extraction attacks |
| Grader agreement with the author | Reported; aiming for at least 85 percent |
| Reply speed on the live site | Median first checked sentence under 2.5 seconds and median full reply under 4.0 seconds, measured from the server receiving the message, on warm runs, over at least 50 messages |

## 5. Cut order

If time runs short, cut in this order (simplifications, cut order and buttons (D24)): the suggested-question buttons; the cost-per-conversation breakdown; the consistency runs (R23); the log purge and extra masking (R73, R72); the rollback practice run (R83); the flag export; the pre-deploy quick test run (R22); the measures beyond the core set (the core set is recall and hit rate at five, stale-trap accuracy, answer correctness and faithfulness); the adversarial set down to 15 cases; the threshold curve (R32).

Never cut: deployment, the findings document, retrieval evaluation, booking with confirming, cancelling and rescheduling, the account lookups, the emergency replies, handoff tickets, flagging, the PRD's required numbers, health checks, the README and the video.

## 6. Left to the builder

- Web framework, page styling and the exact wording of greetings and plain messages, within the rules above.
- How templates are detected, as long as the method is described and repeatable.
- How alerts are delivered (email or a messaging hook).
- Exact minimum number of conversations before live containment is shown.

## 7. Questions still open with the PM

Listed in `docs/PRD_REVIEW.md`: whether the nightly reset is acceptable (the question of whether rescheduling, cancelling and confirming exceed the PRD's bar is settled by including them (D13)); whether an honest containment rate below 60 percent with documented ceilings counts as a miss; whether handing off part of a top-three call reason still counts as answering it.

## Glossary

- **Call reason (call driver):** why a customer called, such as booking a repair or asking about a bill.
- **Template:** a call pattern that repeats across many transcripts with only names, numbers and filler words changed.
- **Containment:** the share of calls the agent finishes correctly without a human.
- **Scope ceiling / adjusted ceiling:** the highest containment possible given the agent's scope, and that ceiling after removing calls the data cannot answer or that need account actions.
- **Action gap:** calls handed off because they need an action on money or membership.
- **Clean decline:** telling the caller plainly that no slot is available and handing off; correct, but not contained.
- **Human baseline:** the share of calls staff resolved on the first call.
- **Held-out set:** test cases kept aside and only used for the final measurement.
- **Working set:** test cases used while tuning the agent.
- **Caller card:** the details given to the AI playing the caller: a real customer's name, account number, phone, address and request.
- **Simulated caller:** an AI model that plays the customer in a test conversation.
- **Reference answer:** the correct answer to a test question, written in advance from the current documents.
- **Grader:** an AI model that judges whether an answer matches the reference.
- **Margin of error:** how far a measured percentage may be from the true value given the sample size.
- **Adversarial test:** a test written to trick or break the agent.
- **Document list:** the record of every knowledge-base file's status, audience, date and whether it is searchable.
- **Conflict register:** the list of facts on which documents disagree, with which one wins and why.
- **Stale-trap question:** a question where an excluded old document would give a different answer than the current one.
- **Embedding:** a list of numbers representing a text's meaning, used to find similar text.
- **Keyword search / meaning-based search:** finding passages by matching words, or by matching meaning through embeddings.
- **Recall at five / hit rate at five:** the share of needed passages found in the top five results, and the share of questions with at least one needed passage in the top five.
- **Faithfulness:** the share of an answer's claims supported by the passages it used.
- **Citation accuracy:** whether the document an answer names contains the fact.
- **Router:** the step that decides which flow a caller's message belongs to.
- **Flow:** a conversation path with fixed steps and rules enforced in code, such as booking.
- **Read-only lookup:** reading a caller's record without changing it.
- **Database transaction:** a group of database changes that all happen together or not at all.
- **Zone:** the area (north, central, south) a customer's city belongs to.
- **Members-only slot:** a slot reserved for Comfort Club standard or Plus members.
- **Warranty-visit flag:** a marker on an appointment meaning no diagnostic fee applies.
- **Handoff ticket:** the record of an escalated conversation with everything a human needs to continue it.
- **Proof receipt:** a short line after a booking or handoff showing what the system checked and did.
- **Streaming:** showing a reply word by word as it is written.
- **Health endpoint:** a web address the hosting service checks regularly to confirm the app is up.
- **Fly.io secrets:** settings such as keys stored by the hosting service, not in the code.
- **Seeded data:** the starting rows the database ships with, including the four test customers.
