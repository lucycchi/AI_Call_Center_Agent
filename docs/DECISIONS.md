# Decisions

Every material decision for this project, in the order it was made. A model
can only propose a decision; only the author settles one.

## D1: If the honestly measured containment rate (the share of calls the agent finishes without a human) comes out below the PRD's 60 to 75 percent target, what do we report?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Report the honest number with the reason and the ceiling (the share of calls whose reason the agent handles)
  - Widen the agent's scope to more call reasons until the number reaches 60 percent
- **Research:**
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Finding F2: the target may be unreachable without answering calls the agent should hand off, which breaks the PRD's rule 'Do not let the agent guess'.
  - [https://www.twig.so/blog/voice-ai-agents-metrics-csat-aht-containment](https://www.twig.so/blog/voice-ai-agents-metrics-csat-aht-containment): Industry sources warn that containment alone misleads: a confident wrong answer still counts as contained.
- **Choice:** Report the honest number with the reason and the ceiling; still choose the scope to cover as many calls as safely possible.
- **Reason:** The PRD judges 'Is the containment number real?' and says 'a confident wrong answer is worse than a handoff'. Reporting a lower honest number still meets the literal requirement to measure and report containment; it only risks missing the target, which the review flagged as possibly unreachable.

## D2: How do we choose which call reasons the agent handles and which it hands to a human?

- **Status:** replaced by "How do we choose which call reasons the agent handles, while meeting the PRD's 'answer the top 3 call drivers' word for word?" (D12)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Pick from the transcripts by volume, leaving out risky reasons, and always handle scheduling
  - Pick three knowledge-base reasons and add scheduling as a fourth
  - Let the exec team's guesses decide
- **Research:**
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Finding F3: 'top 3 call drivers' may or may not include scheduling, and a common reason may be unsafe to automate.
  - [https://alhena.ai/blog/ai-to-human-handoff/](https://alhena.ai/blog/ai-to-human-handoff/): Hand off when the AI cannot, the customer will not, or the AI should not (high stakes).
- **Choice:** Choose from the transcripts, ranked by volume. A common reason that is risky to automate (emergencies, billing disputes, complaints) is escalated. Scheduling counts as one of the three handled reasons if it ranks there and is handled anyway if it does not.
- **Reason:** The PRD says the transcripts, not the exec team, show what matters, and judges 'Judgment on scope'. Scheduling is a required competency. This meets the PRD's 'top 3 call drivers' requirement as long as three handled reasons come from the ranked list; if one of the top three is unsafe, the next one down is handled instead and the reason is documented.

## D3: Do we build the voice extra credit (answering real phone calls)?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Leave it out of the plan; try it only if every required goal is built, tested and deployed with a day to spare
  - Plan it from the start alongside the chat agent
- **Research:**
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Finding F32: voice is about two to four days of work on its own; the project has four working days.
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Voice needs replies in under about a second, a phone provider, and speech-to-text and text-to-speech.
- **Choice:** Leave voice out of the plan and list it under open questions. Build the agent core to take text in and give text out, independent of the chat screen, so a phone front end can be added later without a rebuild.
- **Reason:** Voice is extra credit; the PRD says a chat agent 'is still a complete submission' and 'a smaller system that works and is measured beats a larger one'. Leaving it out drops no required item.

## D4: Where do we host the public web app?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Fly.io: one small always-on server with an attached disk, about $2 to $3 a month
  - Render free plus a free Turso hosted database: free, but sleeps and takes 30 to 60 seconds to wake
  - Oracle Cloud Always Free server: free, but the most setup and signup capacity problems
  - Hugging Face Spaces: free, but sleeps and loses its files
- **Research:**
  - [https://fly.io/pricing.md](https://fly.io/pricing.md): Pay as you go; small machine about $2 a month, disk $0.15 per GB a month; free allowance ended October 2024 for new accounts.
  - [https://snapdeploy.dev/state-of-free-hosting](https://snapdeploy.dev/state-of-free-hosting): Render free sleeps after 15 minutes; Hugging Face free disk is not kept; Railway is effectively paid after a trial.
  - [https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/): Oracle cut its free server allowance in mid-2026 with inconsistent enforcement.
- **Choice:** Fly.io, with the SQLite booking database on an attached disk.
- **Reason:** The data README says the reviewer tests against the same database and bookings must actually write to it, so the database must survive restarts. The reviewer opens the URL first, so the app should not sleep. Fly.io also supports the always-open connections a phone call would need later. Cost is small next to the AI spending.

## D5: Which AI models and services does the project use?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Claude Sonnet 5.5 for the conversation, Claude Haiku 5.5 for sorting transcripts, an OpenAI model for grading, Voyage AI for embeddings, a $5 daily spending cap
  - Claude Opus 5.5 or Fable 5.1 for the conversation
  - A Google or OpenAI model for the conversation
  - An embedding model running on our own server
- **Research:**
  - [https://openrouter.ai/benchmarks/tau2-bench-airline](https://openrouter.ai/benchmarks/tau2-bench-airline): Customer service benchmark run 2026-10-16: Sonnet 5.5 78.0% at $0.16 a task in 82 seconds; Opus 5.5 75.8% at $0.33; Fable 5.1 79.2% at $0.72; Haiku 5.5 75.3% at $0.012. The top twenty are within about five points, which is mostly noise.
  - [https://arxiv.org/abs/2601.00596](https://arxiv.org/abs/2601.00596): JourneyBench: an agent whose steps are controlled by code follows policy better than a larger model given one long prompt.
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Full comparison, industry measures and best practices.
- **Choice:** Claude Sonnet 5.5 runs the conversation; Claude Haiku 5.5 sorts the 420 transcripts by call reason; an OpenAI model (picked in the spec) grades test answers; Voyage AI's free allowance provides embeddings; AI spending has a hard cap of about $5 a day, after which the agent hands off.
- **Reason:** Sonnet 5.5 is in the top group, fastest of it, and half the price of Opus 5.5, and speed matters for a waiting caller. Grading with another company's model avoids the agent grading its own work. A hosted embedding service keeps the server small. The spending cap protects a public URL that reviewers will try to break.

## D6: How do we stop reviewers' test bookings from filling the calendar on the public site?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Reset the one real database to its original seeded data every night
  - Give each visitor a separate copy of the database
  - Never reset
- **Research:**
  - [call_data/README.md](call_data/README.md): 'The reviewer will test the live agent against the same database, so bookings must actually write to it.'
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Finding F4: reviewers trying to break the site can book every slot, so the next visitor sees no availability.
- **Choice:** Write every booking to the one real database, and restore the original seeded data once a night.
- **Reason:** A separate copy per visitor would break the data README's rule that bookings write to the same database. A nightly reset keeps that rule, keeps bookings visible until midnight, and keeps the scheduling demo working for every reviewer.

## D7: How does the agent deal with knowledge-base documents that are outdated, duplicated, internal-only or contradictory?

- **Status:** replaced by "How does the agent deal with knowledge-base documents that are outdated, duplicated, placeholders, internal-only or contradictory?" (D22)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Settle conflicts once when building the search index: leave stale documents out with a written list, use internal notes as hidden rules, hand off account-specific and still-conflicting questions
  - Index everything and let the agent prefer the newest document at answer time
  - Index everything and let the agent hand off whenever two results disagree
- **Research:**
  - [call_data/README.md](call_data/README.md): 'Some documents are current, some are not, and some contradict each other.' The internal folder 'should not be read verbatim to customers.'
  - [call_data/knowledge_base/](call_data/knowledge_base/): Current files are dated; stale ones (archive folder, old FAQ copy) are undated and give wrong fees, warranty terms, membership prices and transfer rules.
  - [https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026): An answer can be faithful to its retrieved document and still be wrong if that document is out of date.
- **Choice:** Leave the archive folder and the undated old FAQ copy out of search, with a written list of every excluded document and why; turn the internal agent notes into hidden rules (no firm prices, no refunds, hand off fee waivers and discounts); hand off questions that depend on the caller's own account unless the database answers them; hand off if two current documents still disagree.
- **Reason:** Deciding at index time makes the behaviour testable and repeatable instead of depending on the model's judgement on each call, and the exclusion list documents the traps that the PRD judges ('Did you catch the traps?'). Fee waivers and discounts need a human's authority. No required item is dropped: the top handled call reasons are still answered from the current documents.

## D8: Who judges whether each test conversation was resolved correctly?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Code checks bookings and handoffs; an OpenAI grader checks knowledge answers against reference answers from the current documents; the author hand-grades about 30 to measure grader agreement
  - An AI grader judges everything
  - The author hand-grades everything
- **Research:**
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Findings F10, F20 and F21: 'resolved' is undefined, transcript answers may be outdated, and grading with the agent's own model flatters it.
  - [https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026): Pair automated scoring with human review of a representative sample.
- **Choice:** Bookings and handoffs are checked by code; knowledge answers are graded by an OpenAI model against reference answers written from the current documents (drafted by Claude, spot-checked by the author); the author hand-grades about 30 answers and the agreement rate is reported.
- **Reason:** Code checks are exact where an exact answer exists. A different company's grader avoids self-grading. The hand-graded sample turns 'the grader is right' from a claim into a measured number, which the PRD asks for ('Show the numbers, not just the claim'). Reference answers come from current documents because staff in the transcripts may have quoted outdated policy.

## D9: What does a handoff to a human look like when there are no real staff behind the agent?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - A plain message to the caller plus a ticket on a staff page that shares a screen with the monitoring dashboard
  - A message to the caller only
  - A separate staff application
- **Research:**
  - [https://alhena.ai/blog/ai-to-human-handoff/](https://alhena.ai/blog/ai-to-human-handoff/): A clean handoff carries identity, intent, prior attempts, constraints and emotional state; 4 of 15 live deployments tested in 2026 passed no context.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Finding F13: 'hands off with enough context' implies something visible the reviewer can check.
- **Choice:** Tell the caller plainly what is happening, and create a ticket with the five handoff fields shown on a staff page that shares a screen with the monitoring dashboard.
- **Reason:** Makes the PRD's 'hands off with enough context that a human can pick up without starting over' visible and checkable by the reviewer, at about half a day, by reusing the dashboard screen the monitoring requirement needs anyway.

## D10: How is the agent built?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - A: one AI with four tools and the policy in its instruction prompt
  - B: a router that sorts each message into a handled call reason, scheduling or handoff, then code-controlled flows for each
  - C: a reviewed answer bank for the top questions, with the AI only rephrasing and running bookings
- **Research:**
  - [https://arxiv.org/abs/2601.00596](https://arxiv.org/abs/2601.00596): JourneyBench: agents whose policy steps are controlled in code follow policy far better than larger models given the whole policy in one prompt.
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Best practice: keep actions narrow and checked in code; ground every factual answer in a retrieved passage and hand off when none supports it.
- **Choice:** B: router plus code-controlled flows. Scheduling runs as fixed steps checked in code (identify customer, choose service, offer slots matching zone and membership, read back, book); knowledge answers come only from retrieved passages and hand off on low retrieval confidence or no supporting passage; handoff builds a five-field ticket. The AI writes every reply.
- **Reason:** The PRD rewards clean failure and evidence. B is the only option where booking rules and refusals cannot be argued around and where each part (routing, retrieval, answers, bookings, handoffs) has its own measured number. It meets every required item; C was rejected because it bends the literal requirement to build a retrieval pipeline with deliberate chunking, embedding and retrieval choices.

## D11: Should the chat offer common questions up front, combining the router approach with a menu of common questions?

- **Status:** replaced by "Should the suggested-question buttons use cached answers, and what is cut first if time runs short?" (D16)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Router plus flows with suggested-question buttons: buttons send their question into the same flows, with answers generated from the documents at index-build time and cached
  - Buttons that show pre-written canned answers (the rejected answer-bank approach)
  - No buttons; free text only
- **Research:**
  - [docs/DESIGN.md](docs/DESIGN.md): The answer-bank approach was rejected because it bends the PRD's requirement to answer through a retrieval pipeline; buttons that are shortcuts into the same flows avoid that.
  - [docs/PRD.md](docs/PRD.md): Reviewers 'will ask their own questions and try to break it', so the free-text path must still be fully built and is what the test set measures.
- **Choice:** Keep the router and code-controlled flows, and add 4 to 6 suggested-question buttons chosen from the discovery ranking. A click sends that question straight to its flow (skipping only the router); its answer is generated from retrieved documents when the index is built and cached, and refreshed on every rebuild. The free-text box stays.
- **Reason:** Faster for callers (one click, instant reply), no misrouting on common questions, and the reviewer sees at once what the agent handles. It keeps every answer grounded in the retrieval pipeline, so no PRD requirement is bent. Cost is about 2 to 3 hours; it does not shorten the build, because the free-text path is still required.

## D12: How do we choose which call reasons the agent handles, while meeting the PRD's 'answer the top 3 call drivers' word for word?

- **Status:** settled
- **Replaces:** "How do we choose which call reasons the agent handles and which it hands to a human?" (D2)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Answer the knowledge part of every real top-three reason through document search; within a risky reason, answer the safe part and hand off the rest; show the observed top three and the agent's scope as two lists
  - Choose three safe reasons from near the top of the ranking, skipping risky ones (the replaced rule)
- **Research:**
  - [docs/DESIGN_PRD_REVIEW.md](docs/DESIGN_PRD_REVIEW.md): Codex: the replaced rule substitutes 'three safe reasons from near the top' for 'the top 3 call drivers' and may leave a real top-three reason unanswered through retrieval.
  - [call_data/knowledge_base/policies/escalation_and_safety.md](call_data/knowledge_base/policies/escalation_and_safety.md): Lists what agents can resolve directly (scheduling changes, explaining invoice line items, payment links, membership, warranty, service area and hours) and what goes to a supervisor (billing disputes, refunds, complaints).
- **Choice:** Rank call reasons by volume. For each of the real top three, the agent answers its knowledge questions through document search, including policy questions inside scheduling calls (cancellation fees, windows); bookings use the database. If a top-three reason has risky parts (a billing dispute, a refund), the agent answers the safe part (such as explaining invoice line items) and hands off the rest. Scheduling is handled whatever its rank. The findings document shows the observed top three and the agent's scope as two lists, and any gap goes to the PM.
- **Reason:** Meets the PRD's 'retrieval pipeline that lets the agent answer the top 3 call drivers accurately' word for word, while keeping the rule that risky requests go to a human. The replaced rule could leave a required top-three driver unanswered.

## D13: Are rescheduling, cancelling and confirming existing appointments part of the core scope?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Yes: all three in the core scheduling flow, kept narrow and never cut
  - Only if discovery shows they are common (the earlier design)
  - No: new bookings only, as the PRD's minimum bar
- **Research:**
  - [call_data/scheduling_db/SCHEMA.md](call_data/scheduling_db/SCHEMA.md): Lists 'Reschedule / cancel: update the existing appointment and free the old slot' and 'Confirm: look up scheduled appointments' as expected agent behavior.
  - [call_data/knowledge_base/policies/escalation_and_safety.md](call_data/knowledge_base/policies/escalation_and_safety.md): 'What agents can resolve directly: Scheduling, rescheduling, cancelling, and confirming appointments.'
  - [docs/DESIGN_PRD_REVIEW.md](docs/DESIGN_PRD_REVIEW.md): Codex: making these conditional turns required data behavior into an option; the reviewer can test the seeded appointment immediately.
- **Choice:** Confirm (look up scheduled appointments), cancel (free the old slot in the same database transaction; inside 24 hours state the $49 late fee from the current FAQ, and hand off any waiver request) and reschedule (book the new slot and free the old one together) are core and never cut.
- **Reason:** The data's schema and the company's own policy treat them as standard agent work, and the reviewer can test them with seeded customer Linda Foster's appointment. About half a day, reusing the booking steps. This adds scope beyond the PRD's minimum bar but does not depart from any requirement.

## D14: Who provides the independent ground-truth call-reason labels that the router and the discovery ranking are checked against?

- **Status:** replaced by "Who provides the independent ground-truth call-reason labels?" (D18)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - The author labels about 27 of an 80-transcript sample; an OpenAI frontier model run through the author's Codex subscription labels all 80; the author's labels check the frontier model
  - The author hand-labels all 80
  - Only the AI that produced the discovery labels (circular)
- **Research:**
  - [docs/DESIGN_PRD_REVIEW.md](docs/DESIGN_PRD_REVIEW.md): Codex: grading the router against Haiku's own held-out labels measures agreement between related model judgments, not accuracy against independent truth.
- **Choice:** Draw an 80-transcript sample (40 working set, 40 held-out) spread across call reasons. An OpenAI frontier model run through Codex (the author's subscription, no API cost; the author switches Codex to a frontier model when told labeling is starting) labels all 80 without seeing Haiku's labels. The author labels about 27 of them without seeing either AI's labels. Report author-versus-frontier agreement, frontier-versus-Haiku agreement, and router accuracy on the held-out 40 against the frontier labels, with the author's label winning where present. The README states that about two-thirds of ground-truth labels are model labels checked against the author's.
- **Reason:** Makes router and discovery accuracy independent of the model being measured, at no API cost, and fits the author's available time (about 25 minutes). The frontier model is from a different company than the Claude models used for discovery and routing.

## D15: How is the OpenAI grader run?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Through Codex under the author's subscription, offline, in batches, with the model name recorded and an API fallback setting
  - Through the OpenAI API at about $1 to $3 per full test run
- **Research:**
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Grading with a different company's model avoids the agent grading its own work.
- **Choice:** Grade test answers with an OpenAI model run through Codex on the author's laptop, about 20 answers per call, recording the model name with every result. An API setting stays as a fallback. The author is reminded to set Codex to a frontier model before each graded run. The OpenAI API key becomes optional.
- **Reason:** The author prefers no additional API cost and already has a Codex subscription. Grading is offline and never runs on the live site, so slower runs are acceptable. The grader is still from a different company than the agent, as the grading decision (D8) requires.

## D16: Should the suggested-question buttons use cached answers, and what is cut first if time runs short?

- **Status:** replaced by "What is simplified up front, and what is cut first if time runs short?" (D23)
- **Replaces:** "Should the chat offer common questions up front, combining the router approach with a menu of common questions?" (D11)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-16
- **Options:**
  - Keep the buttons without cached answers (a click sends the question through the live flow, skipping only the router), cut them first if time runs short, and protect a never-cut list of required evidence
  - Keep buttons with cached answers (the replaced decision)
  - Drop the buttons
- **Research:**
  - [docs/DESIGN_PRD_REVIEW.md](docs/DESIGN_PRD_REVIEW.md): Codex: cached button answers add a second answer path that no requirement needs, and the earlier cut order removed evidence before interface polish.
- **Choice:** Keep 4 to 6 suggested-question buttons that send their question through the live flow with the router skipped; no cached answers. Cut order if time runs short: the buttons, then the cost-per-conversation breakdown, the consistency runs, the extra measures beyond the core retrieval and answer set, the adversarial set down to 15 cases, then the threshold curve. Never cut: deployment, the top-driver findings, retrieval evaluation, booking with rescheduling, cancelling and confirming, emergency replies, handoff tickets, the PRD's required numbers, health checks, the README and the video.
- **Reason:** Keeps the one-click benefit for about 1 hour instead of 2 to 3, removes the second answer path, and makes sure evidence the reviewer judges is never traded for polish.

## D17: Does the agent answer questions about the caller's own account from the database?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Yes: three read-only lookups (open invoices with balance, due date and line items; membership tier and renewal date; system brand and install date); every action that changes money or membership hands off and is reported as an action gap
  - No: hand off every account question
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): Fresh review: by a rough count the top three call reasons are booking (31%), billing (18%) and membership (18%); most billing and membership calls are balance, renewal-date and install-date lookups or actions. Without lookups the rough containment ceiling is about 55%; with them about 65%.
  - [call_data/scheduling_db/SCHEMA.md](call_data/scheduling_db/SCHEMA.md): Seeded customer Omar Patel 'Has open invoice INV-204411 for $478.00'.
- **Choice:** Add three read-only lookups after the caller is identified: open invoices (balance, due date and line items, read exactly as recorded), membership tier and renewal date, and system brand and install date. Payment links, autopay, cancelling auto-renew, upgrades, enrolment and anything else that changes money or membership hand off with a ticket, and are reported in the containment ceiling as the action gap. This extends the top-three scope rule (D12): top-three reasons are answered from documents and these lookups.
- **Reason:** Matches what callers actually ask in the transcripts and lifts the rough ceiling into the PRD's 60 to 75 percent range with no added risk, because lookups only read. About half a day.

## D18: Who provides the independent ground-truth call-reason labels?

- **Status:** replaced by "Which frontier model provides the independent check labels for the call-reason templates?" (D37)
- **Replaces:** "Who provides the independent ground-truth call-reason labels that the router and the discovery ranking are checked against?" (D14)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Label the roughly 80 transcript templates: Codex (frontier model) labels all of them and the author labels about a third blind to check it
  - Label an 80-transcript sample three ways (the replaced decision)
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): The 420 calls come from about 80 templates (77 distinct opening requests after removing names, numbers and filler, checked by Claude). Labeling templates gives labels for all 420 calls; router accuracy on only 40 calls has a margin of error of about plus or minus 9 points.
- **Choice:** Group the 420 transcripts by template. Codex, set to an OpenAI frontier model on the author's subscription (the author is told before it runs), labels every template without seeing Haiku's labels. The author labels about a third of the templates without seeing either AI's labels. Report author-versus-Codex and Codex-versus-Haiku agreement; router accuracy is measured on every held-out call, scored on the caller's first substantive message, with the author's label winning where present.
- **Reason:** Labels all 420 calls at no API cost and about 25 minutes of the author's time, and makes the router-accuracy number meaningful.

## D19: How does the agent treat a burning smell that is not reported with tripped breakers?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Urgent: a fixed reply in code and a priority handoff, never a normal booking
  - Book a normal visit, as staff did in the transcripts
- **Research:**
  - [call_data/knowledge_base/policies/escalation_and_safety.md](call_data/knowledge_base/policies/escalation_and_safety.md): Immediate danger includes 'Electrical burning smell combined with tripped breakers'.
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): 16 calls say 'I smell something burning from the vents'; staff booked normal visits; the troubleshooting guide's 'reset any tripped breaker' advice would be dangerous with a burning smell.
- **Choice:** A burning smell on its own is urgent: a fixed reply written in code (turn the system off at the thermostat, do not reset breakers, leave the home if there is smoke) followed by a priority handoff; never booked as a normal visit, and breaker-reset advice is never given in the same conversation. All 16 such test cases are labeled this way. This also confirms that the fixed safety replies are written in code, an exception to the build decision's 'the AI writes every reply' (D10).
- **Reason:** A confident booking for a possible fire hazard is worse than a handoff. Costs about 4 points of containment, reported openly.

## D20: How are test cases built so the measured numbers mean something?

- **Status:** replaced by "How are test cases built so the measured numbers mean something (with the rehearsal on working-set cases)?" (D32)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Caller cards with real database customers, split by template, one weighted case per template, and a day-3 rehearsal
  - Simulated callers read the transcripts as written, split by call reason
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): 0 of 131 transcript account numbers, 0 of 130 phone numbers and 0 of 42 invoice numbers exist in the database (Claude checked the account numbers). Splitting by call reason puts copies of the same template in both sets.
- **Choice:** Each test case is tied to a real database customer matching the transcript's facts (zone, membership, brand, install age); the simulated caller gets a caller card with that customer's details, not the transcript's. Billing cases add their invoice to the fresh test database copy. Transcripts are grouped by template and split by template, so no template appears in both sets. The held-out run uses one case per template, weighted by its real call count; both calls and distinct scenarios are reported, with the margin of error on scenarios. A 10-case held-out rehearsal runs at the end of day 3, after which the agent is frozen.
- **Reason:** Without real customers most test calls fail at identification and measure nothing; without a template split the held-out set leaks. About 5 to 6 hours, and it shrinks the held-out run from about 120 to about 50 to 60 conversations.

## D21: Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity?

- **Status:** replaced by "Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity (with the narrow invoice rule)?" (D27)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Fixed rules in code, as listed in the choice
  - Leave these to the AI's judgment
- **Research:**
  - [call_data/knowledge_base/faq/customer_faq.md](call_data/knowledge_base/faq/customer_faq.md): 'Cancellations or reschedules more than 24 hours before the window are free. Inside 24 hours there is a $49 late-cancellation fee.'
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): North zone has no plumbing slots and central has no estimate slots (Claude checked); Omar Patel's invoice charges $144 after-hours against the published $149 and an $89 diagnostic fee on top of a repair (Claude checked); seeded appointments include zone mismatches and overlapping afternoon bookings.
- **Choice:** (1) 'Now' is one setting: 2026-10-16 09:00, Austin (US Central) time; windows that have started are never offered. (2) The $49 notice applies to both cancelling and rescheduling inside 24 hours; waiver requests hand off. (3) If no eligible slot exists in the three-week range for that zone and service, the agent says so plainly and hands off with a ticket, a clean decline. (4) A slot is refused if its technician is already booked in an overlapping window; existing appointments are left as recorded and the mismatches documented. (5) Invoice lines are read exactly as recorded and never called right or wrong; any questioned charge, or a fixed fee that differs from the current schedule, hands off as a billing dispute with the mismatch on the ticket. (6) The warranty-visit flag is set when the install date is within 2 years of now, or the caller reports a repeat failure of a part repaired within 1 year; otherwise 0. (7) Members are tiers standard or plus. (8) Callers are identified by account number, service address or phone together with their name, never by name alone. (9) Read-backs give date, window, service and technician only, never the stored issue text; new bookings record the fixed now. (10) No waitlist is promised.
- **Reason:** Each rule closes a trap found in the data that a reviewer can hit with the seeded customers, and code rules cannot be argued around. About 5 to 7 hours in total.

## D22: How does the agent deal with knowledge-base documents that are outdated, duplicated, placeholders, internal-only or contradictory?

- **Status:** settled
- **Replaces:** "How does the agent deal with knowledge-base documents that are outdated, duplicated, internal-only or contradictory?" (D7)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - An explicit document list and a conflict register decide what is searchable
  - Folder and file-name rules (the replaced decision)
- **Research:**
  - [docs/DESIGN_PRD_REVIEW.md](docs/DESIGN_PRD_REVIEW.md): The dated 2024 scheduling guide sits outside the archive folder and contradicts the current FAQ; an internal safety policy sits outside the internal folder.
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): The technician-delay document grants a fee waiver; the FAQ and the service-area document disagree on Dripping Springs and Manor; 'dated means current' is false for this knowledge base.
- **Choice:** An explicit document list records each file's status (current, stale or placeholder), audience (customers or internal), effective date and reason. Left out of search: the archive folder, the old FAQ copy, the 2024 scheduling guide and the empty duct-cleaning file. Internal, feeding code rules only: the agent discretion notes, the safety policy and the technician-delay document. A conflict register settles known disagreements (the later effective date wins, for example the April 2026 service area over the March FAQ); the agent hands off only conflicts the register does not settle. The PDF fee table keeps its row and column pairs. The internal rules are paraphrased for the model and replies are checked for verbatim internal text.
- **Reason:** Folder rules missed real traps; an explicit list makes every inclusion and exclusion testable and becomes evidence for 'Did you catch the traps?'.

## D23: What is simplified up front, and what is cut first if time runs short?

- **Status:** replaced by "What is simplified up front, what is cut first if time runs short, and how do the suggested-question buttons work?" (D24)
- **Replaces:** "Should the suggested-question buttons use cached answers, and what is cut first if time runs short?" (D16)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Simplify the evaluation and keep buttons without caching; new cut order naming the big items
  - Keep the earlier cut order (the replaced decision)
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): The earlier cut order held only small items; the knowledge base is under 3,000 tokens, so a 'whole knowledge base in the prompt' comparison answers 'why retrieve at all?'.
- **Choice:** Simplified now: the held-out run is one weighted case per template; retrieval compares keyword-only against combined search, plus one 'whole current knowledge base in the prompt' comparison on answer correctness; precision, mean reciprocal rank and a second chunking setting are dropped; the private reviewer budget is described, not built (the spend alert and the clean cap handoff stay). Suggested-question buttons stay, without cached answers. Cut order if time runs short: the buttons, the cost-per-conversation breakdown, the consistency runs, the flag export, the pre-deploy test run, the measures beyond the core set (recall and hit rate at five, stale-trap accuracy, answer correctness, faithfulness), the adversarial set down to 15 cases, then the threshold curve. Never cut: deployment, the top-driver findings, retrieval evaluation, booking with confirming, cancelling and rescheduling, the account lookups, the emergency replies, handoff tickets, flagging, the PRD's required numbers, health checks, the README and the video.
- **Reason:** Saves about 1 to 1.5 days, which pays for the account lookups, the test fixtures and the data rules, and keeps every number the reviewer judges.

## D24: What is simplified up front, what is cut first if time runs short, and how do the suggested-question buttons work?

- **Status:** settled
- **Replaces:** "What is simplified up front, and what is cut first if time runs short?" (D23)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Buttons only fill in the question text and go through exactly the same path as typing; simplifications and cut order unchanged
  - Buttons skip the router (the replaced decision)
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): The earlier cut order held only small items; the knowledge base is under 3,000 tokens, so a 'whole knowledge base in the prompt' comparison answers 'why retrieve at all?'.
  - [docs/SPEC.md](docs/SPEC.md): Codex second opinion on the screen plan: buttons that skip the router could look rigged to a reviewer and hide routing mistakes.
- **Choice:** Simplified now: the held-out run is one weighted case per template; retrieval compares keyword-only against combined search, plus one 'whole current knowledge base in the prompt' comparison on answer correctness; precision, mean reciprocal rank and a second chunking setting are dropped; the private reviewer budget is described, not built (the spend alert and the clean cap handoff stay). Suggested-question buttons stay, without cached answers, and only fill in the question text: a click goes through exactly the same path as typing, including the router. Cut order if time runs short: the buttons, the cost-per-conversation breakdown, the consistency runs, the flag export, the pre-deploy test run, the measures beyond the core set (recall and hit rate at five, stale-trap accuracy, answer correctness, faithfulness), the adversarial set down to 15 cases, then the threshold curve. Never cut: deployment, the top-driver findings, retrieval evaluation, booking with confirming, cancelling and rescheduling, the account lookups, the emergency replies, handoff tickets, flagging, the PRD's required numbers, health checks, the README and the video.
- **Reason:** Same savings as before. Buttons that use the normal path cannot look rigged, are measured like typed questions, and are simpler to build.

## D25: Which model sorts each caller message into a flow (the router)?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Claude Haiku 5.5 for routing, Claude Sonnet 5.5 for writing replies
  - Claude Sonnet 5.5 for both (as the models decision first said)
- **Research:**
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Haiku 5.5 scored 75.3% against Sonnet 5.5's 78.0% on the airline customer service benchmark at about a tenth of the cost per task; sorting a message into a few flows is a much simpler job than the benchmark.
- **Choice:** Claude Haiku 5.5 routes each message; Claude Sonnet 5.5 writes the replies. Routing accuracy is measured on the held-out set against the template labels, so a switch to Sonnet is a settings change if Haiku misroutes.
- **Reason:** Meets the reply-speed budget (about 1.2 seconds for routing, median first word under 2 seconds) at a fraction of the cost, and routing accuracy is measured rather than assumed. Amends the models decision (D5).

## D26: Exactly which call reasons does the agent handle, hand off, or answer and redirect?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Handle bookings (including estimates), existing appointments, billing and membership questions answerable from documents or lookups, and warranty questions and claims; hand off disputes, refunds, complaints, late technicians, account actions, emergencies and commercial work; answer and redirect hiring and wrong numbers
  - Handle only the top three plus scheduling, handing off warranty
- **Research:**
  - [docs/DATA_REVIEW.md](docs/DATA_REVIEW.md): Warranty is the fourth reason (45 calls, 11 percent) and needs only documents, the install-date lookup and booking, all already in scope.
  - [docs/SPEC.md](docs/SPEC.md): Builder check: held-out expected outcomes must be frozen before tuning, so the handled list must be fixed now.
- **Choice:** Handled: new bookings including replacement estimates; confirming, rescheduling and cancelling appointments; billing questions answered from documents or lookups (current balance, what an invoice is for, charged twice); membership questions (what it includes, price, renewal date); warranty questions and claims (coverage, registration, transfer, booking a warranty or repeat-repair visit with the warranty flag). Handed off: quote disputes and refunds, complaints and manager requests, late technicians, every account action (the action gap), safety emergencies (after the fixed safety reply), commercial work. Answered and redirected: hiring enquiries and wrong numbers, reported with and without.
- **Reason:** Uses only abilities already in the design, adds warranty (about 11 points of scope ceiling) at no new build cost, and fixes the expected outcomes before tuning. Extends the top-three scope rule (D12) and account lookups (D17).

## D27: Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity (with the narrow invoice rule)?

- **Status:** replaced by "Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity (with the narrow invoice rule, evidence-based warranty flag and duplicate-charge rule)?" (D29)
- **Replaces:** "Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity?" (D21)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Fixed rules in code with the narrow invoice rule: hand off only when the caller questions a charge; a fixed-fee amount mismatch silently creates a billing-review ticket
  - Fixed rules with the broad invoice rule: any line differing from the schedule hands off (the replaced decision)
- **Research:**
  - [call_data/knowledge_base/faq/customer_faq.md](call_data/knowledge_base/faq/customer_faq.md): 'Cancellations or reschedules more than 24 hours before the window are free. Inside 24 hours there is a $49 late-cancellation fee.'
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): North zone has no plumbing slots and central has no estimate slots (Claude checked); Omar Patel's invoice charges $144 after-hours against the published $149 and an $89 diagnostic fee on top of a repair (Claude checked); seeded appointments include zone mismatches and overlapping afternoon bookings.
  - [docs/SPEC.md](docs/SPEC.md): Builder check: 45 of 81 invoices charge the $89 diagnostic fee on top of a repair and 22 charge it to members; a broad rule would hand off nearly every billing call.
- **Choice:** (1) 'Now' is one setting: 2026-10-16 09:00, Austin (US Central) time; windows that have started are never offered. (2) The $49 notice applies to both cancelling and rescheduling inside 24 hours; waiver requests hand off. (3) If no eligible slot exists in the three-week range for that zone and service, the agent says so plainly and hands off with a ticket, a clean decline. (4) A slot is refused if its technician is already booked in an overlapping window; existing appointments are left as recorded and the mismatches documented. (5) Invoice lines are read exactly as recorded and never called right or wrong. The caller is handed off as a billing dispute only if they question a charge. A fixed-fee amount that differs from the current schedule (for example Omar Patel's $144 after-hours line against $149) silently creates a low-priority billing-review ticket for staff without interrupting the caller. The widespread pattern of a diagnostic fee charged alongside a repair or to a member goes in the findings document as an executive finding, with no per-call action. (6) The warranty-visit flag is set when the install date is within 2 years of now, or the caller reports a repeat failure of a part repaired within 1 year; otherwise 0. (7) Members are tiers standard or plus. (8) Callers are identified by account number, service address or phone together with their name, never by name alone. (9) Read-backs give date, window, service and technician only, never the stored issue text; new bookings record the fixed now. (10) No waitlist is promised.
- **Reason:** Each rule closes a data trap a reviewer can hit with the seeded customers. The narrow invoice rule keeps billing questions containable while still catching the planted mismatch and never defending a questionable charge.

## D28: How is AI spending capped so no visitor can use up the reviewer's budget?

- **Status:** replaced by "How is AI spending capped so no visitor, or group of visitors, can use up the reviewer's budget?" (D30)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - A per-visitor budget of about $0.40 a day plus a site-wide cap raised to $10 a day, with an alert at $5
  - Build a private reviewer link with a reserved budget
  - Keep a shared $5 cap and accept the risk
- **Research:**
  - [docs/SPEC.md](docs/SPEC.md): Builder check: with a shared $5 cap and 100 messages per visitor a day, two or three busy visitors can exhaust the budget before the reviewer arrives.
- **Choice:** Each visitor (browser session, with the network address as a backstop) may spend about $0.40 a day, roughly 10 conversations; the site-wide cap is $10 a day; the author is alerted when daily spend passes $5. Hitting either limit gives a clean handoff with a plain message. Test runs use a separate key and budget. Amends the spending cap in the models decision (D5).
- **Reason:** Stops any one visitor from starving the reviewer, for about an hour of work and a worst case of $10 a day during the review period.

## D29: Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity (with the narrow invoice rule, evidence-based warranty flag and duplicate-charge rule)?

- **Status:** settled
- **Replaces:** "Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity (with the narrow invoice rule)?" (D27)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - The rules in the choice, including the warranty flag set only on database evidence and the fixed 'now' limited to customer-facing rules
  - The earlier rules (the replaced decision)
- **Research:**
  - [call_data/knowledge_base/faq/customer_faq.md](call_data/knowledge_base/faq/customer_faq.md): 'Cancellations or reschedules more than 24 hours before the window are free. Inside 24 hours there is a $49 late-cancellation fee.'
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): North zone has no plumbing slots and central has no estimate slots (Claude checked); Omar Patel's invoice charges $144 after-hours against the published $149 and an $89 diagnostic fee on top of a repair (Claude checked); seeded appointments include zone mismatches and overlapping afternoon bookings.
  - [docs/SPEC.md](docs/SPEC.md): Builder check: 45 of 81 invoices charge the $89 diagnostic fee on top of a repair and 22 charge it to members; a broad rule would hand off nearly every billing call.
  - [docs/SPEC_REVIEW.md](docs/SPEC_REVIEW.md): Codex spec review findings, with the author's rulings.
- **Choice:** (1) 'Now' for customer-facing scheduling and policy rules is one setting: 2026-10-16 09:00, Austin (US Central) time; windows that have started are never offered. Operations (spending and rate limits, the nightly reset, alerts, reply timing) use real time. (2) The $49 notice applies to both cancelling and rescheduling inside 24 hours; waiver requests hand off. (3) If no eligible slot exists in the three-week range for that zone and service, the agent says so plainly and hands off with a ticket, a clean decline. (4) A slot is refused if its technician is already booked in an overlapping window; existing appointments are left as recorded and the mismatches documented. (5) Invoice lines are read exactly as recorded and never called right or wrong. The caller is handed off as a billing dispute only if they question a charge. A fixed-fee amount that differs from the current schedule (for example Omar Patel's $144 after-hours line against $149) silently creates a low-priority billing-review ticket for staff without interrupting the caller. The widespread pattern of a diagnostic fee charged alongside a repair or to a member goes in the findings document as an executive finding, with no per-call action. (6) The warranty-visit flag is set only when the database install date proves the 2-year installation labour warranty applies; repeat-repair and 5-year member-installation claims, which the database cannot verify, are booked as normal visits with a warranty-review note for staff, and the caller is told there is no diagnostic fee if the technician confirms coverage. (11) For 'charged twice', the agent first gives the FAQ's pending-authorisation explanation and hands off only if the caller says both charges posted. (12) Cancelling or rescheduling restores the freed slot's original status (open or members-only) from the seeded database copy. (7) Members are tiers standard or plus. (8) Callers are identified by account number, service address or phone together with their name, never by name alone. (9) Read-backs give date, window, service and technician only, never the stored issue text; new bookings record the fixed now. (10) No waitlist is promised.
- **Reason:** Each rule closes a data trap a reviewer can hit with the seeded customers. The narrow invoice rule keeps billing questions containable while still catching the planted mismatch and never defending a questionable charge. The warranty and duplicate-charge rules come from the spec review: the database has no repair history or membership-at-installation record, so fee waivers must rest on evidence.

## D30: How is AI spending capped so no visitor, or group of visitors, can use up the reviewer's budget?

- **Status:** settled
- **Replaces:** "How is AI spending capped so no visitor can use up the reviewer's budget?" (D28)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Per-visitor $0.40 a day, site-wide $10 a day, alert at $5, plus a secret reviewer link with its own $3-a-day reserve
  - Per-visitor and site-wide caps only (the replaced decision)
- **Research:**
  - [docs/SPEC.md](docs/SPEC.md): Builder check: with a shared $5 cap and 100 messages per visitor a day, two or three busy visitors can exhaust the budget before the reviewer arrives.
  - [docs/SPEC_REVIEW.md](docs/SPEC_REVIEW.md): Codex spec review findings, with the author's rulings.
- **Choice:** Each visitor (browser session, with the network address as a backstop) may spend about $0.40 a day, roughly 10 conversations; the site-wide cap is $10 a day; the author is alerted when daily spend passes $5. Hitting either limit gives a clean handoff with a plain message. Test runs use a separate key and budget. A secret reviewer link (its token stored as a Fly.io secret) draws on a separate $3-a-day reserve that other visitors cannot touch. Amends the spending cap in the models decision (D5).
- **Reason:** Per-visitor limits alone cannot stop many sessions together from exhausting the shared cap; the reserve guarantees the reviewer a working demo for about 2 to 3 hours of work.

## D31: What retention, masking and rollback protections does the live system have?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Purge conversation logs after 30 days, mask phone numbers, emails and street addresses, and keep a one-page rollback runbook practised once
  - None beyond masking phone numbers and emails
- **Research:**
  - [docs/SPEC_REVIEW.md](docs/SPEC_REVIEW.md): Codex spec review findings, with the author's rulings.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Personal data in logs (F26) and rollback and versioning (F30) were raised as missing requirements.
- **Choice:** Conversation logs are purged after 30 days; phone numbers, emails and street addresses are masked in logs and the staff view (names and account numbers, which are synthetic and needed on tickets, stay). A one-page rollback runbook in the README covers rolling back a Fly.io release (prompts and the search index ship inside the release) and restoring the disk from Fly's daily snapshot, and it is practised once before submission.
- **Reason:** Closes the personal-data and rollback gaps the PRD review raised, for about 3 to 4 hours in total; both are cuttable after the never-cut items.

## D32: How are test cases built so the measured numbers mean something (with the rehearsal on working-set cases)?

- **Status:** settled
- **Replaces:** "How are test cases built so the measured numbers mean something?" (D20)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - As before, but the day-3 rehearsal uses working-set cases, the first run of each case is the scored one, and synthetic customers may be added where none matches
  - Rehearse on held-out cases (the replaced decision)
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): 0 of 131 transcript account numbers, 0 of 130 phone numbers and 0 of 42 invoice numbers exist in the database (Claude checked the account numbers). Splitting by call reason puts copies of the same template in both sets.
  - [docs/SPEC_REVIEW.md](docs/SPEC_REVIEW.md): Codex spec review findings, with the author's rulings.
- **Choice:** Each test case is tied to a real database customer matching the transcript's facts (zone, membership, brand, install age); the simulated caller gets a caller card with that customer's details, not the transcript's. Billing cases add their invoice to the fresh test database copy. Transcripts are grouped by template and split by template, so no template appears in both sets. The held-out run uses one case per template, weighted by its real call count; both calls and distinct scenarios are reported, with the margin of error on scenarios. A 10-case rehearsal on working-set cases runs at the end of day 3, after which the agent is frozen. The first run of each held-out case is the scored result; a case that fails then passes on its one retry is reported as flaky. Where no real customer matches a transcript, the test copy may add a synthetic customer, marked as synthetic.
- **Reason:** Rehearsing on held-out cases would break their independence; scoring only the first run stops retries from inflating results.

## D33: What status does a freed slot get when the seed copy itself shows it as booked?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Restore the seed status when it was open or members-only; when the seed shows booked, free the slot to open, as the schema says freeing means
  - Guess the earlier status from other data
- **Research:**
  - [docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md): Codex architecture review with the author's rulings.
  - [call_data/scheduling_db/appointment_slots.csv](call_data/scheduling_db/appointment_slots.csv): Seeded customer Linda Foster's slot 159 is 'booked' in the seed, so the seed cannot say what it was before.
- **Choice:** When an appointment is cancelled or moved, its slot returns to the seed copy's status if that was open or members-only. If the seed copy shows the slot as booked (a seeded appointment), the slot is freed to open, which is what the schema's 'free the old slot (open)' rule says. Refines the freed-slot rule in the data rules (D29).
- **Reason:** The seed cannot record a pre-booking status for seeded appointments; the schema's own rule gives a defined answer instead of a guess.

## D34: Which protections are added to booking confirmations, the reviewer link and downtime alerts?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Confirmation IDs so a repeated yes returns the first result; a one-time reviewer token exchanged for a session and removed from the address; an outside uptime monitor on the health endpoint
  - None of these
- **Research:**
  - [docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md): Codex architecture review with the author's rulings.
- **Choice:** (1) Each read-back carries a confirmation ID; a repeated or retried confirmation returns the first result instead of changing the database again. (2) The secret reviewer link is used once to start a signed reviewer session, then redirects to a clean address, and the token is never logged. (3) A free outside uptime monitor checks the health endpoint and alerts the author when the site is down.
- **Reason:** Protects the never-cut 100 percent booking-correctness target, stops a screenshot or shared link from leaking the reviewer reserve, and makes the required downtime alert possible. About 4 to 7 hours in total.

## D35: Which technology stack does the system use?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Python 3.12, FastAPI with one worker, a normal request per message with its checked sentences streamed back by server-sent events, server-rendered pages, two SQLite files in write-ahead logging mode, a search index built offline and shipped in each release, an in-app scheduler behind an app-wide reset gate, a webhook for alerts
  - A separate front-end application and a server database
- **Research:**
  - [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Technology choices table and trade-offs.
  - [docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md): Codex architecture review with the author's rulings.
- **Choice:** Python 3.12; FastAPI with one worker process; each caller message is an ordinary request and its checked sentences stream back as server-sent events tied to that message; server-rendered HTML with a little plain JavaScript; the provided scheduling SQLite file plus a separate operations SQLite file, both in write-ahead logging mode on the attached disk; the search index built offline and shipped inside each release; an in-app scheduler with an app-wide gate that messages hold shared and the nightly reset holds exclusively; alerts through a webhook; Anthropic and Voyage SDKs pinned.
- **Reason:** The smallest stack that meets the spec on one Fly.io machine in four days; one worker keeps the reset gate and scheduler simple, and shipping the index in the release makes rollback complete.

## D36: Which architecture refinements does the plan review require?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Confirmation records in a small new table inside the scheduling database, typed engine events, saved messages with stream replay, call timeouts, hard limits on paid test runs, the reviewer token in the link's fragment, and a frozen-file list instead of a whole-repository freeze
  - Keep the architecture as approved
- **Research:**
  - [docs/PLAN_REVIEW.md](docs/PLAN_REVIEW.md): Codex plan review: idempotency split across two databases, an engine interface that cannot carry metadata, an unbounded stream lifecycle, no timeouts, no evaluation spending stop, and a freeze check that would reject the finished app.
- **Choice:** (1) Confirmation ids are stored in a new agent_confirmations table inside the scheduling database, written in the same transaction as the booking change; the provided tables are untouched and the nightly reset recreates the new table empty. (2) The engine yields typed events: one per checked sentence, then a done event with route, ticket, receipt, outcome and database actions. (3) Each message and its released sentences are saved; the stream replays saved sentences on reconnect, and a message left unfinished by a restart becomes a handoff. (4) Timeouts: Anthropic 20 seconds, Voyage 5 seconds, alert webhook 5 seconds, and a 15-second deadline per message after which it hands off. (5) Paid test runs are capped at 12 caller turns per conversation, fixed output-token limits, 60 seconds per conversation, one retry, a separate test key, and an $8 stop per run. (6) The reviewer token sits after a # in the link, which browsers never send to servers; the page sends it once and clears it. (7) The final-run freeze covers only the agent-behaviour files and the search index, recorded as a hash. (8) The keyword index is rebuilt at startup from the shipped chunks.
- **Reason:** Each closes a way the approved behaviour could fail in practice: double bookings after a crash, lost receipts, hung requests, runaway test spend, a leaked reviewer token, or a final run that cannot start.

## D37: Which frontier model provides the independent check labels for the call-reason templates?

- **Status:** replaced by "Who labels the blind third of the templates that checks the Codex labels?" (D38)
- **Replaces:** "Who provides the independent ground-truth call-reason labels?" (D18)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Claude Fable 5.1 (Anthropic's most capable model) labels every template, with the author's blind third as the independent check and the shared-company limitation disclosed
  - An OpenAI frontier model through Codex (the replaced decision)
- **Research:**
  - [docs/MODEL_RESEARCH.md](docs/MODEL_RESEARCH.md): Using a model from a different company avoids correlated mistakes when one model checks another.
  - [docs/DECISIONS.md](docs/DECISIONS.md): Template labeling (D18) chose Codex so the check labels came from a different company than the Haiku labels and router.
- **Choice:** Claude Fable 5.1 (model ID claude-fable-5-1) labels one sample call per template without seeing Haiku's labels, from code, with the model name saved; about $1. The author labels about a third of the templates blind, and the author-versus-Fable agreement is reported as the trust measure. The README states that the frontier labels and the router are both from Anthropic, so routing accuracy against those labels may be optimistic. Answer grading stays with OpenAI through Codex (grading through Codex (D15)).
- **Reason:** The author's preference: the strongest available labeler, repeatable from code, no Codex setup step. The independence lost by using the same company as the router is partly restored by the author's blind labels and stated openly.

## D38: Who labels the blind third of the templates that checks the Codex labels?

- **Status:** settled
- **Replaces:** "Which frontier model provides the independent check labels for the call-reason templates?" (D37)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Claude Fable 5.1 labels the blind third instead of the author; Codex still labels every template
  - The author labels the blind third by hand (the earlier decision)
- **Research:**
  - [docs/DECISIONS.md](docs/DECISIONS.md): Template labeling (D18): Codex labels every template and the author labels about a third blind as the check.
- **Choice:** Codex, set to an OpenAI frontier model on the author's subscription, labels every template without seeing Haiku's labels, as before. Claude Fable 5.1 (claude-fable-5-1) labels the same blind third of the templates, without seeing Haiku's or Codex's labels, in place of the author. Reported: Fable-versus-Codex agreement on that third (a cross-company check), Codex-versus-Haiku agreement, and routing accuracy against the Codex labels. The README states that no human labeled the templates. The author's blind grading of about 30 answers (D8) is unchanged.
- **Reason:** The author's preference, to save their labeling time. The check stays independent across companies (OpenAI and Anthropic), at a cost of about $0.30, but it is no longer a human check; that limitation is disclosed.

## D39: How are the nine waitlist templates treated, given that each is the matching booking call plus one fixed waitlist exchange?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - Keep all 52 templates, and link each waitlist template to its booking twin as a family that always lands on the same side of the test split
  - Merge each waitlist template into its booking twin (43 templates)
  - Keep 52 templates with no link
- **Research:**
  - [docs/reviews/template-grouping-check-REPORT-fable.md](docs/reviews/template-grouping-check-REPORT-fable.md): Claude Fable 5.1 read all 420 transcripts: no splits needed; merge the nine waitlist templates into their booking twins (43); 52 defensible if the waitlist offer counts as a distinct staff response.
  - [docs/reviews/template-grouping-check-REPORT-user-agent-codex-2.md](docs/reviews/template-grouping-check-REPORT-user-agent-codex-2.md): Codex: grouping correct at 52; the waitlist exchange is an additional request and staff branch worth keeping separate.
- **Choice:** Keep the 52 templates. data/templates.csv gains a family column: each waitlist template's family is its booking twin's template id, every other template is its own family. The test split (Task 7) assigns whole families, so twins are never on opposite sides. The plan's 70 to 120 template estimate is corrected.
- **Reason:** Keeps the waitlist variant as its own test scenario (the agent must not promise a waitlist, one of the seven staff error patterns) while preventing near-duplicate leakage between the tuning and held-out sets. About one column and a few lines plus a test.

## D40: The milestone 2 reviews found errors in the frozen test cases (caller scripts kept the transcript's identity, wrong planted invoices, two-request calls expecting only a handoff, evidence spans tied to the chunker). Fix them and refreeze the held-out set, or leave the frozen set alone?

- **Status:** replaced by "The review of the milestone 2 fixes found more errors in the rebuilt test cases (requests still unlisted, the cancel case on the wrong appointment, a Plus member asking to join, paid invoices shown as owed, evidence spans missing facts). Fix them and refreeze the held-out set again?" (D42)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - Fix the case builder, rebuild all 52 cases and refreeze the held-out set with a new hash, recording the old hash
  - Leave the frozen held-out set as it is and fix only the working set
  - Leave both sets and note the errors in the results
- **Research:**
  - [docs/gates/milestone-2.md](docs/gates/milestone-2.md): Codex and a fresh Claude agent reviewed the milestone; 32 of 52 scripts (9 held out) carried a different account, name or phone than the caller card, and the quote-dispute invoice was planted at the quoted amount.
- **Choice:** Fix the builder and refreeze. The split itself is unchanged (37 working and 15 held-out templates); the held-out hash moves from 7cdaec4bc6b1c44407e8fe2da8a9415899bf1cf4c759ad586c884cf0c9eec5f0 to 9ad6f6cdbaaa5788932714ff1691fa156cadf36c997b785a2862e0c8c2792b1c. Each case now lists every request the caller makes, each with its own expected outcome. Existing-appointment cases use a real customer's seeded appointment where one matches, so the freed-slot rule (R55, D33) already covers them; a slot planted only for a test (none at present) is freed to open.
- **Reason:** The spec forbids changes after the agent has been tuned on held-out results (R10); no agent exists yet, so refreezing now is allowed, and a held-out set with wrong identities or invoices would make every final measurement wrong.

## D41: How does combined search merge the keyword and meaning-based lists?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - Keep each list's top result (keyword only when some word matches), then fill by reciprocal-rank fusion over the top 10 of each list
  - Plain reciprocal-rank fusion
  - Meaning-based search only
- **Research:**
  - [data/results/retrieval/summary.json](data/results/retrieval/summary.json): On the working-set questions: plain fusion missed answers meaning search had first; keep-top fusion found every answer; meaning-only had the best recall at five; keyword-only was weakest.
- **Choice:** Keep each list's top result, then reciprocal-rank fusion. The spec leaves the fusion method to the builder (R28). The results report meaning-only beside it honestly, and the rule was chosen on the working set only.
- **Reason:** Plain fusion dropped meaning search's correct first answer whenever keyword search missed; keeping keyword search's top result protects exact-term questions (prices, place names) that meaning search can rank lower.

## D42: The review of the milestone 2 fixes found more errors in the rebuilt test cases (requests still unlisted, the cancel case on the wrong appointment, a Plus member asking to join, paid invoices shown as owed, evidence spans missing facts). Fix them and refreeze the held-out set again?

- **Status:** settled
- **Replaces:** "The milestone 2 reviews found errors in the frozen test cases (caller scripts kept the transcript's identity, wrong planted invoices, two-request calls expecting only a handoff, evidence spans tied to the chunker). Fix them and refreeze the held-out set, or leave the frozen set alone?" (D40)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - Fix them, rebuild all 52 cases and refreeze the held-out set with a new hash, recording both earlier hashes
  - Fix only the working set
  - Leave the cases and note the errors
- **Research:**
  - [docs/gates/milestone-2.md](docs/gates/milestone-2.md): Codex and a fresh Claude agent reviewed the fixes; held-out cases affected: charged twice (paid invoice), repeat repair (booking request), upgrade (mid-year question).
- **Choice:** Fix and refreeze. Every request beyond a call's labelled reason comes from a reviewed list (data/case_requests.csv) quoting the caller's words; seeded appointments are the customer's only upcoming one and match the service the caller describes; a caller asking to join is drawn as a non-member; charged-twice and refund invoices are planted paid; evidence spans cover every number in the reference, tested. The split is unchanged (37 working, 15 held out); the hash moves from 9ad6f6cdbaaa5788932714ff1691fa156cadf36c997b785a2862e0c8c2792b1c to 4423a9632bcd38f06b7945585c8bdf43bb005f5b038345d5a8b921cd303afa46. The nine waitlist calls also list "an earlier slot" as a request, handled when the agent offers the earliest eligible slots; a "wants an earlier slot" ticket is also correct but counts as a handoff (R44). New reference answers: upgrading mid-year (held out) and cancelling before renewal; the replacement-estimate answer no longer claims the advisor confirms the price, which no document says.
- **Reason:** No agent exists yet, so refreezing is still allowed (R10); held-out cases with wrong data would make the final measurements wrong.

## D43: How are money promises in replies and money or membership action requests detected, after three review rounds showed word patterns failing in both directions?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - A Haiku check on every reply sentence that touches money, plus fixed code rules, failing closed; the router decides action requests, with a code backstop only for unmistakable requests
  - Keep word patterns for both and fix each reported phrasing
  - Accept the known gaps and measure them in the evaluation milestone
- **Research:**
  - [docs/gates/milestone-3.md](docs/gates/milestone-3.md): Three review rounds (Codex and fresh Claude agents, about 160 probe phrasings) found pattern checks both missing promises ('we won't charge you', 'it's on us') and blocking published terms, with each round trading one set of errors for another.
  - [data/results/money_check/summary.json](data/results/money_check/summary.json): On 108 labelled reply sentences (61 promises, 47 published or ordinary), the full sentence check caught 61 of 61 promises and released 47 of 47 others; the instructions were tuned on this set, so it is a working-set result.
- **Choice:** Every reply sentence that mentions money (a fee, charge, cost, price, $, free, refund, credit, discount, waive, owe, bill or payment) is checked by Claude Haiku 5.5 against the published money terms and the sentence before it, after the fixed code rules (firm totals, waitlists, breaker advice, internal text, and promises worded as a personal favour). A refusal, error, timeout or unreadable answer blocks the sentence; a pipeline with no money check configured blocks every money sentence. The router decides money and membership action requests; a code backstop catches only requests that are never questions (payment links, autopay, cancelling the membership or auto-renew, refunds, fee waivers, paying a bill, signing up for the plan), on every route except a handoff. The labelled sets are kept in data/eval/ (money_sentences.jsonl, action_requests.jsonl) and measured in the evaluation milestone on fresh sentences and through the router.
- **Reason:** Promise and request wording is open-ended; a model reads paraphrase that patterns cannot, and failing closed keeps errors on the safe side. Only sentences about money pay the extra time (about half a second each, a fraction of a cent), so most replies keep their speed. The spec's reply-check rule (R42) still holds: code decides and acts on every check.
- **Revision (2026-10-21):** Quick runs showed the check blocking the company's own published member benefits (the Standard and Plus benefit lists and plan prices). The published terms given to the model now cover the whole Comfort Club overview and the 2026 fee schedule, and a code pre-check releases, without the model, a sentence whose every money mention is a published benefit or plan-price phrase, that names a plan and has no first- or second-person, favour, refund, late-fee, holiday or non-member wording; every other money sentence still goes to the model and fails closed. The blocked sentences were added to data/eval/money_sentences.jsonl as rows to release, with nearby promises that must still be blocked.

## D44: Who grades the grader-check sample blind in place of the author (R19)?

- **Status:** settled
- **Proposed by:** Lucy Chi (author), recorded by Claude (claude-opus-5-5) on 2026-10-18
- **Options:**
  - Claude Fable 5.1, given the rubric, each question, answer and reference, and the passages the answer was given, and no other grader's verdicts
  - The author grades the 30 answers
  - Report only the model-versus-model agreement
- **Research:**
  - [data/results/grader_check_fable.json](data/results/grader_check_fable.json): Fable agreed with Codex on 26 of 30 (87%); all four disagreements were Codex 'wrong', Fable 'right', and turn on how strict the rubric's 'partly correct fails' is.
  - [data/results/grader_check_claude.json](data/results/grader_check_claude.json): An earlier blind Claude grade without passages or rubric gave the same 26 of 30, and matched Fable on all 30.
- **Choice:** Claude Fable 5.1 stands in for the author in the grader check, as it did for the blind third of the labelling (D38). Its blind grades are the check's grades, and the published table (data/results/grader_check.json) compares them with Codex's, stating that Fable graded in the author's place.
- **Reason:** The author's choice ('let fable stand in for me'). Fable saw the same rubric and evidence as Codex, so the check compares two independent frontier graders under one rubric.

## D45: Should a knowledge answer fail for leaving out reference facts the caller's question did not ask about?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-18
- **Options:**
  - No: grade to the question; reference facts the question did not ask about do not fail an answer
  - Yes: every reference fact is required
  - Keep strict grading and lower the quick run's 80% knowledge bar
- **Research:**
  - [data/results/quick-3/summary.json](data/results/quick-3/summary.json): The third quick run failed only on knowledge accuracy (32%); three of the four failures gave correct answers but left out reference facts the question did not ask about (plan benefits on a price question, the free estimate on a discount question, annual billing on a renewal question).
- **Choice:** The grading rubric (eval/grader_prompt.md) adds that a reference may cover more than one question asked, since each was written for every caller with that kind of question, and facts the question did not ask about do not fail an answer that leaves them out. The references themselves are unchanged and frozen. Guessing still fails, and a required disclaimer is still a key fact.
- **Reason:** The author's choice. A caller would find those answers correct; the strict reading measured how closely an answer matched a template-wide reference rather than whether it answered the caller. The change is made before any held-out run, on working-set evidence only.

## D46: The grader saw the held-out requests and reference answers once by accident during testing: keep the held-out set or pick a new one?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-20
- **Options:**
  - Record it and keep the held-out set
  - Record it and pick a new held-out set
- **Research:**
  - [tests/eval/test_run_safety.py](tests/eval/test_run_safety.py): On 2026-10-20 a first version of the held-out guard test ran the real run command on the held-out set before the guard existed; with a fake key every agent call failed (no agent turns, $0), and the 15 empty conversations went once to Codex (gpt-5.6-sol, ephemeral), which saw the requests and reference answers; the untracked output was deleted and the test now cannot start a run.
- **Choice:** Keep the frozen held-out set (D42) and record the exposure here; the held-out guard now refuses a held-out run without the final flag and matching hashes.
- **Reason:** The author's choice. No agent results on held-out cases existed, so nothing was tuned on them (R10); Codex ran without memory and sees the same requests and reference answers at the final grading anyway.

## D47: What should the agent do with a message in a language other than English?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-20
- **Options:**
  - Reply in English that it helps only in English, and hand off with a ticket
  - Reply in English asking the caller to continue in English, with no ticket
- **Research:**
  - [docs/SPEC.md](docs/SPEC.md): Languages other than English are a non-goal; the adversarial set must cover another language (R20) and an unclear request goes to a handoff (R38). The saved adversarial run answered the Spanish case (a20) in Spanish without a handoff.
- **Choice:** The agent replies in English that it can only help in English and that a team member will follow up, and opens a handoff ticket; the other-language case (a20) checks the handoff.
- **Reason:** The author's choice. A caller who cannot continue in English still gets a person, and a reply in another language would go unchecked by the English-only reply checks.

## D48: One answer graded differently between two runs moved the threshold rule's pick from 0.25 to 0.45: how should the threshold be chosen?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-20
- **Options:**
  - Apply the same rule over every graded run of the current agent, pooled
  - Take the pick of the latest run alone
  - Keep 0.25 and record the noise
- **Research:**
  - [data/results/threshold.json](data/results/threshold.json): On 25 working-set questions, the first rerun gave 0.25 (76% contained, 2 wrong) and the second 0.45 (64%, 2 wrong against 72%, 3 wrong at 0.25), decided by one answer (the warranty registration question) that guessed in one run and not the other; pooled, 0.25 nets 0.49 against 0.44.
- **Choice:** The threshold script applies the same rule (0.25 floor, a wrong confident answer costs 2.5) over every graded combined-search run of the current agent, each answer counting once; each graded run is kept under the agent hash it measured.
- **Reason:** The author's choice. With 25 questions one answer's run-to-run swing decides the pick, and pooling runs measures the agent rather than one draw of the writer; the rule itself is unchanged and only working-set questions are used.

## D49: Should the quick run fail outright when a booking was missed because the simulated caller never chose a slot?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-20
- **Options:**
  - Fail outright only on real booking faults; a booking the caller never confirmed is a missed request
  - Keep any booking miss a hard failure and rerun
  - Keep it strict and tell the simulated caller to always pick a slot
- **Research:**
  - [data/results/quick-20261020-140337-run1/attempts.jsonl](data/results/quick-20261020-140337-run1/attempts.jsonl): The quick run on the frozen agent failed only on the retry of the join-the-plan-and-book case (T9e29febc): the simulated caller said "Book it" but never chose one of the three offered slots, and the agent correctly would not pick one; bookings were otherwise 100% correct, routing 100%, knowledge 91%, no wrong confident answers.
- **Choice:** The booking check records a booking fault for a wrong database change, an unexpected write, or a confirmed read-back left unbooked; fewer bookings than expected with none wrong and no confirmed read-back is a missed request, failing that conversation but not the quick run outright.
- **Reason:** The author's choice. The quick run's hard stop exists to catch the agent changing the database wrongly; a caller who never chooses a slot is a conversation the agent could not finish, which already counts against containment.

## D50: How should the deployed site protect the API spend, given that every chat message spends the key?

- **Status:** proposed
- **Proposed by:** Claude (claude-opus-5-5), chosen by the author on 2026-10-20
- **Options:**
  - A separate site-only key capped in the Anthropic console, and reviewer-only chat: the public budget is $0 and one reusable reviewer link
  - Public chat with the built-in caps only
  - A password to send chat messages
  - A password on the whole site
- **Research:**
  - [app/ops/spend.py](app/ops/spend.py): The spend check refuses a visitor whose day's spend has reached the cap, so a $0 public cap refuses every public message before the router or writer is called; the safety check runs first in code and costs nothing; reviewer sessions draw on the $3-a-day reserve (R61, R85).
- **Choice:** The site uses its own Anthropic key with a monthly limit set in the console. The public budget is set to $0 on Fly, so anyone can view the chat page, Results tab and test customers, but a public message gets a plain handoff with no model call. One reusable reviewer link, given with the submission, starts a 7-day reviewer session in any browser that opens it; all reviewer sessions share the $3-a-day reserve. This departs from the reviewer-link rule (R85), which said the token is used once.
- **Reason:** The author's choice. The provider's limit is a hard stop even if the site's own caps failed, the site stays at a public address as the spec asks, and only people with the link can spend. Measured on the quick run, the agent costs about $0.01 a conversation, so the reserve covers about 300 conversations a day and a week at the full reserve is about $21; a reusable link lets every grader and device in, and a leaked link is capped by the reserve and the console limit.

## Glossary

- **Action gap:** calls the agent understands but deliberately hands off because they need an action it is not allowed to take
- **Agent core:** the conversation logic, document search, booking and handoff, separate from the screen or phone line the caller uses
- **Agent scope:** the call reasons and parts of call reasons the agent answers itself
- **Agreement rate:** the share of answers where the AI grader and the human grader gave the same verdict
- **Attached disk (volume):** storage that stays when the server restarts
- **Batch:** a group of items sent together in one request
- **Benchmark:** a fixed public test used to compare models
- **Blind label:** a label given without seeing anyone else's label for the same item
- **Cached answer:** an answer prepared in advance and reused so it appears instantly
- **Call driver:** a reason customers call
- **Caller card:** the facts given to the AI playing the caller: name, account number, phone, address and request
- **Clean decline:** telling the caller plainly that no slot is available and handing off, counted as correct behaviour
- **Code-controlled flow:** a conversation path whose steps and rules are enforced by program code rather than left to the AI
- **Codex:** OpenAI's command-line coding agent, run here under the author's subscription
- **Cold start:** the delay while a sleeping app wakes up for its first visitor
- **Conflict register:** a written list of documents that disagree and which one wins, with the reason
- **Containment ceiling:** the highest containment possible, equal to the share of calls about reasons the agent handles
- **Containment rate:** the share of calls the AI finishes without passing them to a person
- **Correlated mistakes:** errors two models make in the same way because they were built similarly, so one cannot catch the other's
- **Cut order:** the agreed order in which optional work is dropped if time runs out
- **Database transaction:** a group of database changes that all happen together or not at all
- **Embedding:** a list of numbers representing a text's meaning, used to find similar text
- **Escalate:** hand the call to a human
- **Expected outcome:** the result a test case should have (contained, handed off or clean decline), fixed before tuning
- **Fail closed:** when a check cannot give an answer, treat it as a failure, so the sentence is blocked rather than shown
- **Fixture:** prepared test data loaded into a test copy of the database
- **Grader:** a model that scores whether the agent's answer was correct
- **Ground-truth label:** the label treated as correct when measuring accuracy
- **Handoff ticket:** a record of an escalated call with everything a human needs to continue it
- **Hidden rules:** instructions the agent follows but never reads out to the caller
- **Idempotent:** safe to repeat: doing it twice has the same effect as doing it once
- **Monitoring dashboard:** a screen showing how the agent is performing: calls, containment, handoffs, failures and speed
- **Observed top three:** the three most common call reasons in the transcripts, whatever the agent handles
- **Per-visitor budget:** a daily spending limit for one visitor, so others still have budget left
- **Priority handoff:** a handoff ticket marked to be picked up first
- **Read-only lookup:** reading a caller's record without changing it
- **Reciprocal-rank fusion:** merging ranked lists by adding up one over (60 plus rank) for each item across the lists
- **Reference answer:** the correct answer to a test question, written in advance to compare the agent against
- **Reply-speed budget:** the planned time each step may take so the whole reply arrives quickly
- **Retention:** how long stored data is kept before it is deleted
- **Retrieval confidence:** a score for how well the best document passage matches the question
- **Rollback:** returning a live system to its previous working version
- **Router:** the step that decides which flow a caller's message belongs to
- **Search index:** the prepared, searchable copy of the documents that the agent looks things up in
- **Seed copy:** the untouched original scheduling database shipped with each release
- **Seeded data:** the starting rows the database ships with, including the four test customers
- **Server-sent events:** a one-way stream of text from server to browser
- **Speech-to-text / text-to-speech:** turning spoken audio into written words, and written words into spoken audio
- **Suggested-question button:** a clickable common question shown in the chat so the caller need not type it
- **Template family:** a group of templates that are near-identical and must stay on the same side of the test split
- **Transcript template:** a call pattern that repeats across many transcripts with only names, numbers and filler words changed
- **Typed event:** a message with a fixed kind and fields, such as a sentence or a final summary
- **Uptime monitor:** an outside service that regularly checks a site and alerts when it stops answering
- **URL fragment:** the part of a web address after #, which the browser keeps to itself and never sends to the server
- **Whole-knowledge-base comparison:** giving the AI every current document at once instead of searching, to show whether search earns its place
- **Write-ahead logging:** a SQLite mode that lets reads continue during writes
