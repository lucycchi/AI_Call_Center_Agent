# Independent check: are the 420 calls grouped into the right templates?

You are checking one piece of a data pipeline for an AI call-center project. You have not seen this project before. Work only in the project folder `/home/lucyc/gauntlet/AI_Call_Center_Agent`. Do not change, create or delete any file in the project except your report (see the end). Do not run any script that calls an AI service.

## Background you need

- `call_data/call_transcripts/` holds 420 transcripts of customer calls to a heating, cooling and plumbing company (ignore any file ending in `:Zone.Identifier`; those are Windows copy leftovers). Each file has a short header (Call ID, Date, Agent, Duration, Direction), then lines starting `Agent:` (the staff member) and `Customer:` (the caller).
- The calls look synthetic and repetitive: the same caller request and the same staff handling recur with only names, account numbers, dates, prices and filler words ("um", "uh") changed.
- A **template** is meant to be a group of calls that share **the same caller request and the same staff response pattern**, once names, numbers and filler words are ignored. Two calls belong in the same template only if a person reading them would say "this is the same call with different details". Templates are used later to split calls into a tuning set and a held-out test set, so that near-identical calls never end up on both sides; a template that wrongly mixes different calls, or wrongly splits identical ones, makes the test numbers unreliable.
- The project's code (`pipeline/templates.py`) grouped the calls into **52 templates**. The result is in `data/templates.csv`, one row per call, with columns `call_id`, `template_id`, `template_calls` (how many calls share that template), `request` (the caller's request after cleaning) and `outcome` (a one-word summary of what staff did, such as `booked`, `moved`, `waitlist`, `callback`, `action`, `answered`). A reviewed merge list, `data/template_merges.csv`, joined four templates that differed only by equipment brand.
- Two earlier code reviewers disagreed. One said the grouping is wrong because it groups on a one-word staff outcome rather than the staff's actual responses, and does not remove names, so the count of 52 is too low (an earlier plan had guessed 70 to 120). The other read the groups and said they are correct, and the guess was simply too high. Your job is to decide, from the transcripts themselves, which is right.

## What to do

1. Read `data/templates.csv`. For every template, list its calls.
2. For **every** template with more than one call, open at least three of its calls (all of them if it has five or fewer), and compare them. Ask:
   - Is the caller asking for the same thing, in the same way, apart from names, numbers and filler?
   - Did staff respond the same way: the same steps (how they identified the caller, what they asked, what they offered or did, how the call ended), apart from names, numbers, dates and times?
   - If any call in the template differs in a way that matters (a different request, a different staff action or outcome, an extra request, a different ending), name it.
3. Look for templates that should be **merged**: two templates whose calls are, by the definition above, the same call with different details. Compare templates with similar `request` text or the same `outcome`.
4. Check whether **names or other personal details** ever split or join templates wrongly (for example, a caller who says their name inside the request).
5. Check the **one-call and two-call templates** especially; say whether each is genuinely unique or should belong to a larger template.

## What to report

Write your report to `docs/reviews/template-grouping-check-REPORT-<your name or model>.md` (for example `...-REPORT-fable.md`). Use plain English and include:

1. **Verdict:** one line: the grouping is correct, mostly correct with listed fixes, or wrong, and what the right number of templates is by your count.
2. **Templates that should be split:** for each, the template id, which calls belong apart (by call id), and the difference in one sentence quoted from the transcripts.
3. **Templates that should be merged:** for each pair or group, the template ids and why they are the same call.
4. **Names and personal details:** whether they affected any grouping, with call ids.
5. **Small templates:** your view on each template with one or two calls.
6. **Your method:** how many calls you opened per template and in total.
7. **Confidence:** high, medium or low, and why.

Quote the transcript lines you rely on, with their call ids. Do not guess: if you did not open a call, do not make claims about it.
