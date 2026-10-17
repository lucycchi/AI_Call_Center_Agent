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

- **Status:** settled
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

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Caller cards with real database customers, split by template, one weighted case per template, and a day-3 rehearsal
  - Simulated callers read the transcripts as written, split by call reason
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): 0 of 131 transcript account numbers, 0 of 130 phone numbers and 0 of 42 invoice numbers exist in the database (Claude checked the account numbers). Splitting by call reason puts copies of the same template in both sets.
- **Choice:** Each test case is tied to a real database customer matching the transcript's facts (zone, membership, brand, install age); the simulated caller gets a caller card with that customer's details, not the transcript's. Billing cases add their invoice to the fresh test database copy. Transcripts are grouped by template and split by template, so no template appears in both sets. The held-out run uses one case per template, weighted by its real call count; both calls and distinct scenarios are reported, with the margin of error on scenarios. A 10-case held-out rehearsal runs at the end of day 3, after which the agent is frozen.
- **Reason:** Without real customers most test calls fail at identification and measure nothing; without a template split the held-out set leaks. About 5 to 6 hours, and it shrinks the held-out run from about 120 to about 50 to 60 conversations.

## D21: Which data rules does the code enforce for time, fees, slots, invoices, warranty and identity?

- **Status:** settled
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

- **Status:** settled
- **Replaces:** "Should the suggested-question buttons use cached answers, and what is cut first if time runs short?" (D16)
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-17
- **Options:**
  - Simplify the evaluation and keep buttons without caching; new cut order naming the big items
  - Keep the earlier cut order (the replaced decision)
- **Research:**
  - [docs/IDEAS_REVIEW.md](docs/IDEAS_REVIEW.md): The earlier cut order held only small items; the knowledge base is under 3,000 tokens, so a 'whole knowledge base in the prompt' comparison answers 'why retrieve at all?'.
- **Choice:** Simplified now: the held-out run is one weighted case per template; retrieval compares keyword-only against combined search, plus one 'whole current knowledge base in the prompt' comparison on answer correctness; precision, mean reciprocal rank and a second chunking setting are dropped; the private reviewer budget is described, not built (the spend alert and the clean cap handoff stay). Suggested-question buttons stay, without cached answers. Cut order if time runs short: the buttons, the cost-per-conversation breakdown, the consistency runs, the flag export, the pre-deploy test run, the measures beyond the core set (recall and hit rate at five, stale-trap accuracy, answer correctness, faithfulness), the adversarial set down to 15 cases, then the threshold curve. Never cut: deployment, the top-driver findings, retrieval evaluation, booking with confirming, cancelling and rescheduling, the account lookups, the emergency replies, handoff tickets, flagging, the PRD's required numbers, health checks, the README and the video.
- **Reason:** Saves about 1 to 1.5 days, which pays for the account lookups, the test fixtures and the data rules, and keeps every number the reviewer judges.

## Glossary

- **Action gap:** calls the agent understands but deliberately hands off because they need an action it is not allowed to take
- **Agent core:** the conversation logic, document search, booking and handoff, separate from the screen or phone line the caller uses
- **Agent scope:** the call reasons and parts of call reasons the agent answers itself
- **Agreement rate:** the share of answers where the AI grader and the human grader gave the same verdict
- **Attached disk (volume):** storage that stays when the server restarts
- **Batch:** a group of items sent together in one request
- **Benchmark:** a fixed public test used to compare models
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
- **Cut order:** the agreed order in which optional work is dropped if time runs out
- **Database transaction:** a group of database changes that all happen together or not at all
- **Embedding:** a list of numbers representing a text's meaning, used to find similar text
- **Escalate:** hand the call to a human
- **Fixture:** prepared test data loaded into a test copy of the database
- **Grader:** a model that scores whether the agent's answer was correct
- **Ground-truth label:** the label treated as correct when measuring accuracy
- **Handoff ticket:** a record of an escalated call with everything a human needs to continue it
- **Hidden rules:** instructions the agent follows but never reads out to the caller
- **Monitoring dashboard:** a screen showing how the agent is performing: calls, containment, handoffs, failures and speed
- **Observed top three:** the three most common call reasons in the transcripts, whatever the agent handles
- **Priority handoff:** a handoff ticket marked to be picked up first
- **Read-only lookup:** reading a caller's record without changing it
- **Reference answer:** the correct answer to a test question, written in advance to compare the agent against
- **Retrieval confidence:** a score for how well the best document passage matches the question
- **Router:** the step that decides which flow a caller's message belongs to
- **Search index:** the prepared, searchable copy of the documents that the agent looks things up in
- **Seeded data:** the starting rows the database ships with, including the four test customers
- **Speech-to-text / text-to-speech:** turning spoken audio into written words, and written words into spoken audio
- **Suggested-question button:** a clickable common question shown in the chat so the caller need not type it
- **Transcript template:** a call pattern that repeats across many transcripts with only names, numbers and filler words changed
- **Whole-knowledge-base comparison:** giving the AI every current document at once instead of searching, to show whether search earns its place
