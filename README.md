# Meridian Home Comfort chat agent

A chat agent for the customer calls of Meridian Home Comfort, a fictional heating, cooling and plumbing company in the
Austin, Texas area. It was built in four days as a take-home challenge (`docs/PRD.md`). It answers questions from the
company's documents, looks up accounts, books and changes appointments in the scheduling database, and hands
everything else to a person with a ticket.

## At a glance

- **Try it:** https://ai-call-center-agent-bvgy9q.fly.dev. Anyone can look around; chatting needs the reviewer link
  supplied with the submission (see [Who can chat](#who-can-chat)). Talk as one of the four test customers listed on
  the page, or press one of the "Try these" scenarios on the Results tab. Good things to try: an emergency ("I smell
  gas"), a members-only slot for a non-member, a disputed fee, or asking it to ignore its instructions.
- **Containment on held-out calls: 29.5%**, below the PRD's 60 to 75% target and the fair staff baseline of 73.3%.
  The most this agent could contain with its scope is 48.4%. See [Containment](#containment) and the honest reading
  under [Results](#results).
- **After Milestone 7, on 30 new test calls** (written blind after the first measurement, 3 runs per version): the
  share of calls handed to a person fell from 77.5% to **48.3%** and containment rose from 12.1% to **36.6%**,
  weighted by real calls. About 22% of calls need a person by design. See
  [The fresh test set](#the-fresh-test-set-milestone-7).
- **When it does not know, it hands off.** On the held-out calls it gave no confident wrong answers, every call that
  should have gone to a person did, with the right reason, and document answers and account lookups were all correct.
  The misses are calls it should have finished itself: routing was 76.2% right and bookings 69.8%.
- **Why customers call:** new bookings 32%, billing 18%, membership 17%, warranty 11%, existing appointments 9%
  (420 transcripts; see [Call drivers and scope](#call-drivers-and-scope)).

Where to read more:

| Document | What it covers |
| --- | --- |
| `docs/FINDINGS.md` | Why customers call, how the reasons were found, the scope, and three findings for the executive team |
| `docs/DATA_REVIEW.md` | The first look at the transcripts, documents and database, and the traps found in them |
| `docs/ARCHITECTURE.md` (diagrams in `docs/ARCHITECTURE.html`) | How the parts fit together |
| `docs/DECISIONS.md` | Every design decision, the options considered and why |
| `docs/SPEC.md` | The numbered requirements |
| `docs/FINAL_CHECKS.md` | The final browser QA, security audit and whole-project review, and what was fixed |

Codes in parentheses, such as (D50) or (R10), point to an entry in `docs/DECISIONS.md` (D) or `docs/SPEC.md` (R).

## What it does

A customer types into a chat window as they would talk to the call center. Every message goes through the same fixed
steps, and code, not the AI model, decides what is allowed:

1. **Safety first.** A check written in code looks for emergencies (gas or rotten-egg smell, carbon monoxide alarm,
   sparks or smoke, a burning smell, an active leak, no heat in freezing weather). An emergency gets a fixed reply
   written in code (for gas: leave the home and call 911 or the gas utility from outside) and a priority handoff. It
   runs on every message, even in the middle of a booking.
2. **Routing.** Claude Haiku 5.5 sorts the message into a flow: a knowledge question, an account question, scheduling,
   or a handoff.
3. **The flow does the work**, with its rules in code:
   - **Knowledge answers** come only from the company's current documents, found by search, and name the source
     document. If search is not confident, the agent hands off instead of guessing.
   - **Account lookups** read open invoices (exactly as recorded), membership tier and renewal date, and the
     customer's system brand and install date. The caller must first give their name plus an account number, phone
     number or service address.
   - **Money and membership actions** the company's own policy lets its staff take (actions decision (D54)): a
     secure payment link or autopay link, Comfort Club enrolment or an upgrade, and turning off auto-renew. Each is
     read back and needs a plain yes. Links are simulated: recorded as sent to the phone on file and shown in the
     Staff view. The agent never asks for, repeats or stores a card number. Autopay follows a policy the author
     supplied (`data/kb_added/policies/autopay.md`), since no company document covered it.
   - **Booking, rescheduling and cancelling** check the customer's zone, the service type, membership for
     members-only slots and technician overlaps. Before writing anything the agent reads back the date, window and
     service and waits for a plain yes; the change is one database transaction.
   - **Handoff** opens a ticket with five fields (who the caller is, what they want, what the agent already tried,
     constraints such as an emergency or a disputed fee, and the caller's mood), a reason tag and a ticket number. The
     chat stays open and says the team will be in touch within one business day.
4. **Every sentence is checked before it is shown.** Claude Sonnet 5.5 only writes the wording. Code blocks firm
   repair totals, waitlist promises, breaker advice after a burning smell and any run of eight words copied from an
   internal document; a Haiku check compares every sentence that mentions money with the published terms. A sentence
   that fails becomes a handoff.

What it never does:

- Take a payment, or a card or bank number, in the chat; grant a refund or a fee waiver; settle a dispute. These are
  handed off and tagged as the "action gap" (refunds and disputes as "dispute").
- Promise anything the business cannot take back: a refund, a waived fee, a firm price, a waitlist place, or that a
  team member will follow up (it may offer to pass a request on).
- Read internal documents or notes aloud, or read back an appointment's stored issue text or the customer's street
  address.
- Book an emergency. The held-out run found this rule broken after a burning smell; the live build fixes it (see
  [The live build after the measurement](#the-live-build-after-the-measurement)).

The site also has a **Results tab** (the frozen held-out numbers, each with a one-line definition, and one-click
"try these" scenarios) and a **Staff view** (the visitor's own tickets and live numbers; the full queue and flagging
behind a shared staff password).

### Who can chat

The site is public to view: the chat page, the Results tab and the four seeded test customers (Linda Foster, Omar
Patel, Grace Okafor, Daniel Reyes; synthetic people). Chatting is reviewer-only, to protect the API spend (the
reviewer-only decision (D50)). `fly.toml` sets the public budget to $0 (`PER_VISITOR_DAILY_USD = "0"`), so a public
message gets a reply saying chat is open to reviewers, before any model call. An emergency still gets its safety
advice and a priority ticket, since those are written in code.

One reusable reviewer link, which the author provides with the submission (it is not in this repository), starts a
7-day reviewer session in any browser that opens it. All reviewer sessions share a $3-a-day reserve (about 300 typical
conversations a day). The live key is a site-only key with a monthly limit in the Anthropic console, a hard stop
behind the site's own caps (about $25 a month covers a week at the full reserve). To open chat to the public later,
remove the `PER_VISITOR_DAILY_USD` line from `fly.toml` and redeploy.

### Costs

- Live site: at most $3 a day of reviewer chat (the reserve above) and a $10 site-wide daily cap in code; the author
  is alerted when daily spend passes $5.
- Per conversation: about $0.02 in the final held-out run ($0.39 for 18 conversations, the 15 first attempts and 3
  retries; this includes the simulated caller), and about $0.01 for the agent's own calls in the quick runs.
- Evaluation: every paid test run stops at $8 of recorded spend. The final held-out run cost $0.39 in Anthropic calls
  (`data/results/final/summary.json`, `extra.spent_usd`). Grading runs through Codex on the author's subscription, so
  it adds no API cost. Search embeddings use Voyage AI's free allowance.

## Call drivers and scope

The 420 transcripts fall into 52 templates (the same request and staff response with names and numbers changed).
Every call was labelled with a reason by Claude Haiku 5.5 and checked blind by Codex and Claude Fable 5.1; the method is
under [Evaluation](#evaluation) and the full write-up in `docs/FINDINGS.md`. The top five reasons:

| Rank | Call reason | Share of calls | What the agent does |
| --- | --- | --- | --- |
| 1 | New booking | 32% | Books it in the database; a burning smell is handed off for safety |
| 2 | Billing | 18% | Answers balances, invoice lines and duplicate charges; sends payment links; hands off disputes and refunds |
| 3 | Membership | 17% | Answers plan details, prices and renewal dates; enrols, upgrades, sets up autopay and turns off auto-renew |
| 4 | Warranty | 11% | Answers coverage from the documents and the system's install date; books warranty visits |
| 5 | Existing appointment | 9% | Confirms, reschedules and cancels; hands off late technicians |

**Why this scope.** The agent handles more than the top three. Warranty needs only documents, the install-date
lookup and booking, which the top three already use, so it adds 11% of calls at no new build cost; existing
appointments reuse the booking rules. What is handed off is decided by what a call needs, not by its rank: a human's
authority (disputes, refunds, complaints, late technicians) or emergency handling (scope decision (D26)). Payments,
autopay, enrolment, upgrades and cancelling auto-renew were handed off at first and are now done by the agent
(actions decision (D54)), so the share handed off by design fell from about 31% to about 22% of calls. Of the remaining 13% of calls, replacement estimates are booked,
hiring enquiries and wrong numbers are answered and redirected, and complaints, emergencies and commercial work are
handed off.

## Containment

Containment is the share of calls the agent finishes correctly without a human. A test conversation counts as
contained only if the agent never handed off and every request the caller made was graded correct. A clean decline
("no slot is available", with a ticket) is correct behaviour but not containment. Every number below is weighted by
how many real calls each held-out template stands for (`data/results/final/summary.json`).

| Measure | Value | Definition |
| --- | --- | --- |
| Containment | 29.5% | Weighted held-out calls the agent finished correctly with no handoff and no clean decline |
| 95% interval for containment | 3.6% to 56.9% | From resampling the 15 held-out templates 2,000 times; wide because there are only 15 |
| Containment without redirects | 29.5% | The same, leaving out calls that only need a redirect (wrong numbers, job enquiries) |
| Scope ceiling | 74.6% | Calls inside the reasons the agent handles: the most it could contain |
| Adjusted ceiling | 48.4% | The scope ceiling after removing calls the documents or database cannot answer and calls that need a money or membership action |
| Action gap | 16.4% | Calls the agent understands but must hand off because they need an action on money or membership |
| Human baseline | 84.5% | Share of all 420 transcript calls staff resolved on the call (355 of 420) |
| Human baseline excluding account actions | 73.3% | Staff resolution leaving out calls resolved only by an account action the agent never takes (308 of 420) |

**The fair comparison.** Staff can take payments, set up autopay and cancel memberships; the agent by design cannot.
So the agent's containment should be compared with the staff figure that leaves those calls out, 73.3%, not 84.5%.
Even then the gap is large: 29.5% against 73.3%. The adjusted ceiling, 48.4%, is the most this agent could contain on
the held-out calls with its current scope, so about 19 points were lost to mistakes and unnecessary handoffs and the
rest to scope. The staff figures also count some calls as resolved that staff handled wrongly (see the policy errors
below), so they flatter staff slightly.

Why the number is this low, and why it is reported as measured, is under
[Being honest about these numbers](#the-frozen-held-out-measurement).

## Results

### The fresh test set (Milestone 7)

Every one of the 52 call templates had been used, for tuning or for the held-out measurement, so the work in
Milestone 7 was measured on 30 new test calls: one per kind of call, written by Codex without seeing the agent,
weighted by how many of the 420 real calls each stands for, and frozen before any change (`data/testset_fresh/`,
hash in `data/fresh_split.json`). Each agent version ran on them 3 times, and the result is the average with the
lowest and highest run (measurement decision (D55); `python -m eval.fresh_cases report` writes
`data/results/fresh_report.json`). The fixes were found on the working set only; the fresh calls were only counted.

| Measure (average, lowest to highest run) | Before Milestone 7 | After Milestone 7 (the live build) |
| --- | --- | --- |
| Handed to a person, weighted by calls | 77.5% (61.4 to 86.7) | 48.3% (46.0 to 51.2) |
| Resolved by the agent, weighted by calls | 12.1% (2.6 to 26.2) | 36.6% (35.5 to 38.8) |
| Handed to a person, share of the 30 calls | 74.4% (70.0 to 76.7) | 58.9% (56.7 to 60.0) |
| Resolved by the agent, share of the 30 calls | 14.4% (6.7 to 20.0) | 26.7% (23.3 to 30.0) |

What changed, each with its evidence in `docs/DECISIONS.md`:

- **A handoff carries the whole interaction** (D56). A ticket keeps the caller's own words from the whole
  conversation and shows the conversation itself; handoff tickets a staff member could act on rose from 84.1% to
  96.4% of those graded.
- **Needless handoffs found on the working set** (D57): an "earlier slot" ticket after a booked visit, a pause read as
  a wrong number, a correction read as a complaint, a registration question answered without the policy, and a
  dropped invoice-copy request. Earlier-slot tickets fell from 1.3 a run to none.
- **Five money and membership actions** (D54): action-gap tickets fell from 7.0 a run to 2.0, with about 6 actions
  taken a run.

What is left (D58): the handoff rate is still about 27 points above the 22% that need a person by design, and
containment is short of the 60 to 75% target. No upgrade was taken in any run, and "dispute", "other" and "not
enough evidence" handoffs did not fall. The 29.5% below stays on record as the first, frozen measurement.

### The frozen held-out measurement

This is the one measurement made on the held-out set: the frozen agent (freeze hash `5b8f6899…`), 15 scenarios
standing for 122 weighted calls (each template counts as many calls as it has in the transcripts). Source:
`data/results/final/summary.json`. Containment and its ceilings are in the [Containment](#containment) table above.

| Measure | Result | What it means |
| --- | --- | --- |
| Scenarios / weighted calls | 15 / 122 | Held-out templates run once each, and the real calls they stand for |
| Wrong confident answers | 0 | Conversations finished without a handoff but graded wrong |
| Knowledge accuracy | 100% | Document questions answered correctly |
| Routing accuracy | 76.2% | Calls whose first message went to the flow the reference label names (target 90%) |
| Handoff correct, safety and booking | 100% | Safety and booking-rule calls that needed a handoff got one with the right reason |
| Handoff correct, other | 100% | All other calls that needed a handoff got one with the right reason |
| Booking correctness | 69.8% | Booking changes that passed every database check (target 100%) |
| Lookup correctness | 100% | Account lookups that read back the right balance, invoice or renewal date |
| Ticket actionable | 72.7% | Tickets a staff member could act on without asking the caller again (`extra.ticket_actionable`) |
| Clean declines | 1 | Calls correctly declined (no slot) with a ticket |
| Flaky cases | none | Cases that failed, then passed on the retry |
| Cost | $0.39 | Anthropic spend for the run's 18 attempts (15 first runs, 3 retries) |

**Consistency** (`data/results/final/consistency/summary.json`): every held-out case was run three more times. 67% of
the 15 cases were graded correct on all three runs (87%, 80% and 73% on each run); five cases were not always correct.

**What happened to the grading.** The final run crashed while grading, in the database check of a case that expected
no booking; the conversations themselves were already saved. After the check was fixed, a resume command graded the
saved first conversations without running them again, so the scored conversations are the original first attempts;
the summary records this as `resumed: true`.

**Being honest about these numbers.** Held-out containment, 29.5%, is far below what the same frozen agent scored on
the working set: its two quick runs on 20 working-set scenarios gave 64.2% and 64.9%
(`data/results/quick-20261021-064643-run1/summary.json` and `-run2/`), and quick runs during tuning were mostly
between 40% and 60%. Routing (76% against 100% on those quick runs) and bookings (70% against 94% and 100%) also
dropped. It is also below the 60 to 75% containment target in the PRD. The plain reading is that the many fixes made
while tuning on working-set cases fit those cases more than they generalise to calls the agent had not seen. The
held-out set is also small: 15 scenarios, so one case moves containment by up to 12 points, and the 95% interval runs
from 3.6% to 56.9%. Under the held-out rule (R10) nothing was changed after seeing these results; they are reported
as measured.

Looking at the first attempts (`data/results/final/attempts.jsonl`):

- Four cases (36 of 122 calls) were contained.
- Three cases the agent should have finished itself ended in a handoff instead: a "charged twice" billing question, a
  plumbing booking and a warranty repeat-repair visit (23 calls). The handoffs were correct behaviour, but not
  containment.
- Both burning-smell cases (16 calls) gave the fixed safety reply and a correct priority ticket, but when the
  simulated caller went on asking for a visit, the agent booked an ordinary appointment after a clear yes. The
  database check caught it as a booking fault. The rule is that an emergency is never booked, so this is a real bug
  in the frozen agent, and it is why booking correctness is 70%.
- The north-zone plumbing case should have been a clean decline (no plumbing slots in the north zone); the agent said
  there was no capacity but its ticket left out the problem, so it was graded wrong.

### The live build after the measurement

The numbers above are the frozen agent's (agent hash `5b8f6899`, in `data/results/final/summary.json`). The live demo
runs a later build with three changes made after the measurement and not re-measured, as the held-out rule (R10)
requires (live fixes after the measurement (D51)):

- After any safety reply, the agent never books, reschedules or offers slots in that conversation; it points to the
  emergency ticket instead (the burning-smell bug described above).
- A question about today's date or time is answered as the demo's fixed date (Friday 16 October 2026, 9:00 a.m. in
  Austin), since the demo runs on a fixed "now".
- A caller who gives their name and account number in the same message as an emergency is identified then, so the
  priority ticket carries their details and they are not asked for them again.

The final checks then changed the web and operations layers, not the agent: the Results tables, the reviewer-only
reply, and two operations-store fixes for a failing database. `docs/FINAL_CHECKS.md` lists what each final check
(browser QA, security audit, Codex whole-project review) found, what was fixed and what was left as a known limit.

### By call reason

Accuracy on the reasons the agent should handle itself, and the escalation rate on the rest, from the same frozen
held-out run, scored like the summary (first attempts, weighted by the calls each case stands for). Produced by
`python -m eval.per_driver` into `data/results/final/per_driver.json`; with 15 scenarios, each reason rests on one to
six cases.

| Call reason | Cases | Weighted calls | Handled by the agent: correct | Should be handed off: escalated, and with the right reason |
|---|---|---|---|---|
| New booking | 6 | 47 | 68% (3 cases) | 100%, 100% (2 cases) |
| Billing | 2 | 26 | 58% (2 cases) | none expected |
| Membership | 2 | 20 | none expected | 100%, 100% (2 cases) |
| Warranty | 2 | 14 | 57% (2 cases) | none expected |
| Existing appointment | 1 | 9 | none expected | 100%, 100% (1 case) |
| Complaint or manager | 1 | 5 | none expected | 100%, 100% (1 case) |
| Safety emergency | 1 | 1 | none expected | 100%, 100% (1 case) |

Every call that should go to a person did, with the right reason; the misses are calls the agent should have finished
itself. (The two burning-smell cases count under new booking: their handoff was right, but the booking that followed
was the fault described above.)

### Supporting measures

These were measured on the working set or on separate sets, not on the held-out cases.

- **Retrieval** (`data/results/retrieval/answer_scores.json` and the `retrieval` section of the final summary, 25
  working-set questions): combined search had a correct passage in the top five for every question (hit rate 100%,
  recall 93.2%), against 77.3% for keyword search alone, and found the current document on every stale-trap question.
  Answers written from combined search were 92% correct, 96% faithful to the passages, 100% correctly cited, and
  refused 100% of the unanswerable questions. Keyword-only answers were 68% correct; giving the model the whole
  knowledge base gave 88%.
- **Threshold** (`data/results/threshold.json`): at the chosen 0.25, 74% of the working-set question runs were
  contained with 2 wrong confident answers out of 50.
- **Adversarial set** (`data/results/adversarial/summary.json`): 32 of 32 passed, including every booking-rule and
  instruction-extraction attack.
- **Money check** (`data/results/money_check/summary.json`): on 137 labelled sentences it caught all 69 promises and
  released 67 of the 68 fair or published sentences (one over-block: "Members get 15% off repairs, and I can check
  today's openings for you."). This is the set it was tuned on, so it is not independent proof.
- **Grader check** (`data/results/grader_check.json`): Claude Fable 5.1, grading blind, agreed with Codex on 25 of 30
  answers (83.3%, against an 85% aim). In all five disagreements Fable said right where Codex said wrong, so Codex is
  the stricter grader.
- **Live reply times** (`data/results/latency/live-20261021.txt`): measured on 2026-10-21 against the deployed site
  (release v4) with `scripts/measure_latency.py --reviewer`: 3 warm-up messages, then 50 measured, each a fresh
  reviewer-link visitor, 31 seconds apart. All 50 replied, none failed. The median time to the first sentence was
  2.55 seconds (target under 2.5) and to the full reply 4.60 seconds (target under 4.0), so both targets were narrowly
  missed; the slowest replies were handoffs and long knowledge answers.

## Executive findings

Three findings for the executive team, from `docs/FINDINGS.md` (generated by `python -m pipeline.findings`). They are
about the business, not the agent, and the Results tab shows them as three short callouts.

1. **Staff policy errors.** 108 of 420 calls (26%) contain a staff statement or action that contradicts the current
   documents: offering a waitlist that does not exist (34 calls), booking a burning smell as a normal visit (16),
   promising a manager callback today (16), moving a next-day appointment without the $49 fee (15), explaining an
   invoice as the diagnostic fee plus the repair (13), dropping a booking the caller asked for (11), and promising a
   refund callback in two business days (8). Errors appear for every staff member, so they are a training and
   documentation problem, not one person.
2. **Capacity imbalance by zone.** The north zone has 70% of customers but 31% of bookable slots and no plumbing
   slots; the central zone has 10% of customers but 40% of slots and no estimate slots. Rebalancing technicians would
   cut wait times more than any agent.
3. **Documentation gaps.** 14 calls ask about autopay and no document covers it; staff offered a waitlist in 34 calls
   but only a stale 2024 guide mentions one and the scheduling database has none; and 45 of 81 invoices charge the $89
   diagnostic fee on top of a repair although the FAQ says it is credited toward an approved repair (22 of them to
   customers who are members today, for whom it is waived).

## Knowledge base and retrieval

**What is in the documents** (`docs/DATA_REVIEW.md`). The 17 files come in mixed formats: Markdown, plain text, a PDF
fee schedule, a CSV price book and a PNG image of holiday hours. `pipeline.convert` turns each into text: the fee
schedule keeps every price beside its label, the price book becomes one line per item, and the holiday-hours image
was transcribed by hand. Not everything is current. Four files are stale: an archived membership overview with old
prices, 2023 warranty terms, an undated copy of the FAQ with a $79 diagnostic fee, and a 2024 scheduling guide that
offers a waitlist the business no longer has. One is a placeholder, and one is an internal staff procedure that grants
fee waivers. `data/document_list.csv` marks every file, and only current customer-facing documents are searchable.
Where documents disagree, `data/conflict_register.csv` records each of the 19 known conflicts and which source wins.

**How search works.** Documents are split by section, keeping the document name, heading and effective date on
every piece; the fee table stays intact so every price keeps its label. Search combines keyword search and
meaning-based search (Voyage AI embeddings), keeping each list's top hit before merging by reciprocal-rank fusion
(the combined-search decision (D41)). Only files the document list marks current and customer-facing are in the index.
The retrieval threshold, below which the agent hands off instead of answering,
was chosen on working-set questions only, from a curve of containment against wrong confident answers, pooled over
every graded run (the pooled threshold decision (D48)): 0.25.

How well it works is under [Supporting measures](#supporting-measures): combined search found a correct passage in the
top five for every working-set question.

## Evaluation

The numbers come from simulated conversations, not from people. Every paid run uses `EVAL_ANTHROPIC_API_KEY`, stops
at $8 of recorded spend, caps each conversation at 12 caller turns and 60 seconds, and records the pinned model ids,
SDK version and settings with every attempt. Grading runs through the Codex command line tool (see [Install](#install)).

**Finding the call reasons.** The 420 transcripts fall into 52 templates (calls that are the same request and staff
response once names, numbers and filler are removed). Claude Haiku 5.5 labelled every call; Codex labelled one call
per template blind as the reference; Claude Fable 5.1 labelled a blind third (17 templates). They agreed 100% of the
time (`data/label_agreement.json`). No human labelled the templates, and perfect agreement says more about how clean
these synthetic transcripts are than about real calls. Commands: `python -m pipeline.templates`,
`python -m pipeline.label_haiku`, `python -m pipeline.label_codex`, `python -m pipeline.label_fable`,
`python -m pipeline.findings`.

**The test set.** `python -m eval.build_cases` builds one case per template in `data/testset/`: a caller script, a
caller card tied to a real database customer (name, account number, phone and address), any fixtures to plant (such
as the invoice the caller describes), the expected outcome (contained, handed off, clean decline or redirect), the
expected handoff reason, and for document questions a reference answer written from the current documents with the
exact lines that support it. Templates are split once with a fixed seed, by call reason and whole template families,
into a working set (37 templates, used for tuning) and a held-out set (15 templates, used only for the final
measurement). The split and a hash of the frozen held-out cases are in `data/split.json`.

**The held-out rule (R10) and its guard.** No prompt, threshold, chunking setting or category may change after seeing
the agent's results on held-out cases. In code: `eval/run.py` refuses held-out cases unless given `--final`, and with
it refuses unless the held-out files still match the frozen hash and the agent still matches the freeze hash in
`data/agent_freeze.json` (written by `python -m eval.freeze` at the day-3 freeze; it covers the agent's code, prompts,
thresholds, the search index and the documents it reads). One accidental exposure is recorded in the decision on the
held-out exposure (D46): before the guard existed, a test ran the held-out cases with a fake key, so the agent never
answered, and Codex saw the 15 held-out requests and reference answers once. No agent results existed, so nothing was
tuned on them, and the set was kept.

**How a test conversation runs.** Each attempt starts on a fresh copy of the seed database. Claude Sonnet 5.5 plays the
caller from the caller card and script; the caller talks to the same agent core the web app uses. Afterwards:

- **Database checks in code** (`eval/grade_conversations.py`): every booking is the right service, on the slot read
  back, in the caller's zone, members-only only for a member; reschedules and cancels free the old slot; any other
  changed row is an "unexpected write"; a handoff needs the right reason tag on its ticket.
- **Codex grading** (`eval/grader.py`, prompt and rubric in `eval/grader_prompt.md`): whole conversations go to Codex
  in batches of 20 through a fixed `codex exec` command, which returns a JSON verdict per request (answers, lookups,
  dropped requests, ticket quality), with the grader model recorded on every verdict. A partly correct answer fails.
  The model is pinned with `-m gpt-5.6-sol` and recorded as `grader_model`; `grader_reported_model` holds what the model
  says about itself when asked, which comes back as the family name "gpt-5", so the two differ without the model having
  changed.
- A case counts as correct only if Codex and every code check agree. The first run is the scored one; a failed case is
  run once more and reported as flaky if it then passes, never as passed.

**The runs:**

| What | Command | Writes |
| --- | --- | --- |
| A working-set run | `python -m eval.run --set working [--cases T1,T2] [--name RUN]` | `data/results/<RUN>/` |
| The quick run before every deploy: 20 working-set cases; two of up to three runs must pass, and any safety or booking fault fails it | `python -m eval.quick_run` | `data/results/quick-<time>-runN/` |
| The final held-out measurement (once, on the frozen agent) | `python -m eval.final run --confirm-held-out` | `data/results/final/` |
| Resume a final run whose grading stopped: grades the saved first conversations, never runs them again | `python -m eval.final resume --confirm-held-out` | `data/results/final/` |
| Consistency: every held-out case three times | `python -m eval.final consistency --confirm-held-out` | `data/results/final/consistency/` |
| Adversarial set: 32 hand-written attacks in `eval/adversarial/`, checked in code | `python -m eval.run_adversarial` | `data/results/adversarial/` |
| Money check on 137 labelled sentences (`data/eval/money_sentences.jsonl`) | `python -m eval.money_check_eval` | `data/results/money_check/` |
| Retrieval measures and answers: keyword-only, combined, and the whole knowledge base in the prompt | `python -m eval.retrieval_eval`, then `python -m eval.grade_retrieval` | `data/results/retrieval/` |
| The threshold curve (working set only) | `python -m eval.threshold` | `data/results/threshold.json` |
| The grader check | `python -m eval.grader_check sheet`, then `python -m eval.grader_check table` | `data/grader_check.csv`, `data/results/grader_check.json` |

**The grader check.** About 30 graded answers, chosen in advance across Codex's right and wrong verdicts, are graded
blind and compared with Codex. Claude Fable 5.1 graded them in place of the author (the grader-check stand-in
decision (D44)), so this is agreement between two models, not a human check.

## Monitoring

What the business can see once the agent is live:

- **Today's numbers**, at the top of the Staff view: conversations, handoffs, errors, median reply time and live
  containment (an upper bound, since a live chat has no grader to check the answers).
- **Each reply's receipt** ("How this reply was made"): the route, the dated passages it used and the checks it
  passed. A visitor sees their own; staff, signed in with the shared password, see every conversation, the full
  ticket queue, and can flag a wrong reply (the first step of the [Feedback loop](#feedback-loop)).
- **Costs:** every model call is logged in the operations database with its model, tokens, time and cost.
- **Alerts**, posted to `ALERT_WEBHOOK_URL`: an error burst (3 or more errors in 10 minutes, or more than 20% of at
  least 10 messages), a failed database write, a failed nightly reset, and daily spend passing $5.
- **Uptime**, checked from outside (below).

The scheduling tables are reset to the seed every night at 03:00 Austin time, so the demo always has open slots; the
operations database (conversations, tickets, costs, flags) is never reset.

### Uptime monitoring

Fly.io's own health check calls `/health` every 15 seconds and restarts the machine if it stops answering. An outside
monitor (UptimeRobot, free plan) checks `https://ai-call-center-agent-bvgy9q.fly.dev/health` every 5 minutes and
emails the author when it fails. It checks with HEAD, so `/health` answers HEAD as well as GET (a 405 at first showed
the live site as down). Tested once on 2026-10-21: with the machine's auto-start turned off, the machine was stopped at
16:10 UTC, the monitor reported the site down, and the machine was started again at 16:14 UTC (health 200 again,
auto-start back on). Without turning auto-start off, Fly would start the stopped machine on the monitor's next
request, so a stop alone does not test the alert.

## Feedback loop

How a wrong reply in production becomes a fix and a test:

1. **Flag.** In the Staff view, a staff member signs in with the shared password, opens a conversation and flags a
   reply as wrong with a correction note. The flag is saved in the operations database (phone numbers, emails and
   street addresses are already masked there).
2. **Export.** `python -m pipeline.export_flags` (options `--ops PATH` for the operations database, `--out DIR`)
   writes each flagged conversation as one JSON file in `data/candidates/`. A candidate is shaped like a test case:
   the caller's messages become the caller script, and each flag keeps the flagged reply and the staff note. It never
   writes to `data/testset/` or touches `data/split.json`.
3. **Review.** The author fills in the fields only a person can decide (caller card, expected outcome, reference
   answer and evidence lines) and moves the reviewed case into the working set. The held-out set stays frozen.
4. **Fix** the document, conflict-register entry, rule or prompt that caused the error.
5. **Re-run** the working set and the quick run (`python -m eval.quick_run`), which must pass.
6. **Deploy** with `scripts/deploy.sh`, which runs the quick run again first.

## Install

You need Python 3.12 and, for running evaluations, the Codex command line tool signed in to an OpenAI account.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then fill in the keys; .env is in .gitignore and must never be committed
```

The keys in `.env` (see `.env.example` for every setting and what it does):

| Name | Needed for |
| --- | --- |
| `ANTHROPIC_API_KEY` | Running the agent locally (terminal chat or web app) |
| `EVAL_ANTHROPIC_API_KEY` | Paid test runs; a separate key so a test run never spends the live key |
| `VOYAGE_API_KEY` | Search embeddings (the agent embeds each question) |
| `VISITOR_COOKIE_SECRET` | The web app: signs the visitor cookie (at least 16 random characters) |
| `REVIEWER_TOKEN`, `STAFF_PASSWORD_HASH`, `ALERT_WEBHOOK_URL` | Optional locally: the reviewer link, the staff sign-in and alerts |

The search index (`data/index/`) and the converted documents (`data/kb_text/`) are committed, so you do not need to
build them. If the documents change, rebuild them with `.venv/bin/python -m pipeline.convert` and then
`.venv/bin/python -m pipeline.build_index` (needs `VOYAGE_API_KEY`; a few cents).

## Run

**Terminal chat** (the quickest way to talk to the agent). It works on a fresh copy of the seeded scheduling database
and a scratch operations database, so nothing real changes:

```bash
.venv/bin/python -m app.cli      # reads ANTHROPIC_API_KEY and VOYAGE_API_KEY from .env
```

**The web app.** It does not read `.env` itself, so export it first. Run exactly one worker: the nightly reset lock,
the scheduler and the message limits live in that one process.

```bash
set -a; . ./.env; set +a
.venv/bin/uvicorn app.web.main:build_app --factory --workers 1 --port 8000
```

Then open http://localhost:8000. On first start the app copies the seed scheduling database
(`call_data/scheduling_db/meridian_scheduling.sqlite`, never written to) to `DATABASE_PATH` (default
`data/scheduling.sqlite`) and creates the operations database at `OPS_DATABASE_PATH` (default
`data/operations.sqlite`). Customer-facing "now" is fixed at Friday 2026-10-16 09:00 Austin time in `app/config.py`,
so bookings and fee windows behave the same every day. To make the staff password hash, run
`.venv/bin/python -m app.web.staff`; it asks for the password and prints the hash.

## Tests

```bash
.venv/bin/python -m pytest -q
```

About 1,440 tests run in a little over a minute. They use fakes for every paid service (Anthropic, Voyage, Codex,
Fly.io and the live site), so they cost nothing and need no keys. Scheduling tests run on temporary copies of the
seed database. `tests/test_repository.py` checks this README's sections and containment numbers against
`data/results/final/summary.json`, that the evidence files are committed, and that no tracked file holds a key or a
value from your local `.env` (it never prints the values).

## Rollback

One page for running, rolling back and restoring the live site, the rollback runbook requirement (R83). Every Fly.io
command goes through `scripts/fly`, which finds the Fly.io command line tool even when it is not on PATH (or set
`FLYCTL` to its path).

### What lives where

| Part | Where | Rolled back by |
| --- | --- | --- |
| Code, prompts, search index (`data/index/`), seed scheduling database, `docs/FINDINGS.md`, `data/results/final/` | The release image | Deploying an earlier release's image |
| Live scheduling database `/data/scheduling.sqlite`, operations database `/data/operations.sqlite` (conversations, tickets, costs, flags) | The volume `meridian_data` mounted at `/data` | Restoring the volume from a snapshot |
| Keys and passwords | Fly.io secrets | Not rolled back; set again by hand |

The machine count is always one: one worker holds the reset gate, the nightly scheduler and the message limits.

### Secrets

Set each once with `scripts/fly secrets set NAME=value`. Values never go in the repository, `fly.toml`, the
Dockerfile or this README. To keep a value out of shell history, read it first: `read -rs v && scripts/fly secrets
set NAME="$v"; unset v`. `scripts/fly secrets list` shows the names (never the values).

| Name | What it is |
| --- | --- |
| `ANTHROPIC_API_KEY` | A key made only for this site, in its own Anthropic console workspace with a monthly spend limit (the reviewer-only decision (D50)); not the test-run key, which stays only in the local `.env` |
| `VOYAGE_API_KEY` | The Voyage AI key for search embeddings |
| `VISITOR_COOKIE_SECRET` | Signs the visitor cookie; at least 16 random characters (the plan calls it `SESSION_SECRET`; the code reads `VISITOR_COOKIE_SECRET`). Changing it signs every visitor and staff member out |
| `REVIEWER_TOKEN` | The secret behind the reviewer link `https://<app>.fly.dev/#r=<token>`, at least 16 random characters; every browser that opens the link gets a 7-day reviewer session sharing the $3-a-day reserve |
| `STAFF_PASSWORD_HASH` | The staff password's hash, made with `.venv/bin/python -m app.web.staff`; never the password itself |
| `ALERT_WEBHOOK_URL` | Where alerts are posted (error bursts, failed writes, a failed nightly reset, spend passing $5) |

`DATABASE_PATH` and `OPS_DATABASE_PATH` are ordinary settings in `fly.toml` (both on `/data`), not secrets.

### First setup (once)

1. `scripts/fly apps create <app>` and put the name in `fly.toml` (`app = ...`).
2. `scripts/fly volumes create meridian_data --region dfw --size 1 --snapshot-retention 7 --yes` (daily snapshots,
   kept 7 days).
3. Set the six secrets above.
4. `scripts/deploy.sh` (below). On the first start the machine copies the seed scheduling database to the empty
   volume; it never overwrites an existing one.
5. Open `https://<app>.fly.dev/health`; it answers `{"ok": true}`. Point the free outside uptime monitor at it.

### Deploy

`scripts/deploy.sh` runs the quick test run (`python -m eval.quick_run`, paid, test key) and stops if it fails; then
`scripts/fly deploy`, `scripts/fly scale count 1 --yes`, and `scripts/fly status --json`, failing unless exactly one
machine runs. `--skip-quick-run` skips the quick run, only if it has been cut. Fly.io's health check on `/health`
restarts the machine if it stops answering.

### Roll back a release (bad code, prompt or index)

1. `scripts/fly releases --image` lists the releases, newest first, with each one's image
   (`registry.fly.io/<app>:deployment-...`). Pick the last good one.
2. `scripts/fly deploy --image registry.fly.io/<app>:deployment-<id>` releases that image again. Code, prompts and
   the search index go back together; the volume and the secrets are untouched. (It uses the `fly.toml` in the
   current folder, so check out the matching commit if `fly.toml` itself changed.)
3. `scripts/fly scale count 1 --yes`, then `scripts/fly status` shows one machine, and `/health` answers
   `{"ok": true}`.
4. Send one knowledge question in the chat and check the reply.

### Restore the volume from a snapshot (damaged data)

Only the scheduling database damaged: the nightly reset (03:00 Austin time) rebuilds it from the seed anyway. To do
it at once, `scripts/fly ssh console -C "rm /data/scheduling.sqlite"` then `scripts/fly machine restart <machine-id>`;
the start copies the seed again. The operations database is not touched.

The operations database damaged, or both:

1. `scripts/fly volumes list` gives the volume id (`vol_...`) and `scripts/fly status` the machine id.
2. `scripts/fly volumes snapshots list <volume-id>` lists the daily snapshots; pick the last one before the damage.
3. `scripts/fly volumes create meridian_data --snapshot-id <snapshot-id> --region dfw --size 1 --yes` makes a new
   volume from it (note its new id).
4. `scripts/fly machine clone <machine-id> --attach-volume <new-volume-id>:/data` starts a machine on the restored
   volume; then `scripts/fly machine destroy <old-machine-id> --force`.
5. `scripts/fly status` shows exactly one machine, and `/health` answers `{"ok": true}`. Check that the staff view
   shows the tickets expected up to the snapshot's time.
6. Once checked, `scripts/fly volumes destroy <old-volume-id>`, so a later deploy can never attach the damaged
   volume.

Anything written after the snapshot (bookings, conversations, tickets) is lost; bookings return to the seed at the
next nightly reset in any case.

### Practice record

The release rollback is practised once before submission, as the rollback runbook requirement (R83) asks. Practised on
2026-10-21 (04:49 UTC): from release v2 (the reviewer-only note and the design fixes) back to v1's image with
`scripts/fly deploy --image registry.fly.io/ai-call-center-agent-bvgy9q:deployment-01M5EB2PGFD4CCCSM30R5XPWJ6
--ha=false`, which took 20 seconds; `/health` answered `{"ok":true}` and the page showed v1 (no reviewer-only note).
Then forward again to v2's image in 16 seconds (now release v4), with the note back. The volume and its databases were
untouched throughout. The volume snapshot restore has not been practised.
