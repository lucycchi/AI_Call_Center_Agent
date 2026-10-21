# Walkthrough Video Outline

A 3 to 4 minute voiceover for the reviewer, covering the design choices the PRD asks for: how the call drivers were found, why this chunking and retrieval, how handoff works, and what the evaluation numbers say. It explains why each choice was made; it is not a feature tour. Three hard problems are told inside the sections they belong to.

**Status: draft.** Numbers marked **[FINAL]** are placeholders until the final held-out run (Task 27) writes `data/results/final/summary.json`. Lines marked **[NOT BUILT YET]** describe the website and deployment tasks (Tasks 22 to 26) and must be checked against what ships.

Target: about 630 spoken words, roughly 3 minutes 50 seconds. Timings are measured from the generated voiceover, which runs at about 165 words a minute.

**Voiceover:** generated in the author's cloned ElevenLabs voice (eleven_multilingual_v2) into `video/voiceover/`. Done: sections 1 to 4 and the first two paragraphs of section 5 (3 minutes 8 seconds). Still to generate: the final-numbers paragraph of section 5 and section 6.

| Time | Section | Hard problem told here |
|---|---|---|
| 0:00–0:15 | Opening | |
| 0:15–0:50 | How the call drivers were found | |
| 0:50–1:41 | Documents, chunking and retrieval | The knowledge base contradicts itself |
| 1:41–2:34 | How handoff works | Stopping the agent from promising money |
| 2:34–3:33 | What the numbers say | Making the containment number trustworthy (the threshold story, D48, was cut for time) |
| 3:33–3:50 | Running without me, and close | |

## 1. Opening (0:00–0:15)

**On screen:** the live chat page, with one booking going through.

> Meridian Home Comfort's phone lines handle bookings, bills and memberships. I built an agent that takes those conversations in chat. In the next three and a half minutes: what I chose to automate, how I kept it honest, and whether it works.

## 2. How the call drivers were found (0:15–0:50)

**On screen:** the "Top call reasons" table in `docs/FINDINGS.md`.

> So, the first thing I noticed: the 420 transcripts are templated. Strip out the names and numbers and they collapse into just 52 patterns. Haiku labelled every call, Codex checked every pattern blind, and Claude Fable checked a third of them. They agreed a hundred percent, which says more about how clean this data is than about real calls.
>
> Bookings, billing and membership make up 68 percent of calls, so that's where I focused. I drew the line at authority and risk: disputes, refunds, payments, membership changes and safety go to a person, including a burning smell, which staff booked as an ordinary visit 16 times.

**Sources:** `docs/FINDINGS.md` (method, top call reasons, agent scope, staff policy errors).

## 3. Documents, chunking and retrieval (0:50–1:41)

**On screen:** `data/document_list.csv` and `data/conflict_register.csv`, then the retrieval comparison.

> The documents were the real trap. A 2024 scheduling guide sits right next to the current docs and contradicts the FAQ, and two current pages disagree about which towns are served. So folders and dates weren't enough.
>
> Instead, an explicit list decides which documents are searchable, and a conflict register settles each known disagreement. Internal policies become rules in code, never text the model can quote. Chunks follow each document's own sections, and the fee table stays intact so every price keeps its label.
>
> I tested search on its own first. The standard merge of keyword and meaning search sometimes buried the right answer, so I keep each method's top hit before merging. On 25 practice questions, combined search had a correct source in the top five every time, including every question built around a stale document.

**Sources:** decision log, documents (D22) and combined search (D41); `data/results/retrieval/summary.json` (working set, 25 questions).

## 4. How handoff works (1:41–2:34)

**On screen:** "I smell gas near my furnace" in the chat, then the handoff ticket in the Staff view **[NOT BUILT YET]**.

> Handoff is decided in code, not in a prompt. A safety check runs first, so if someone mentions gas, a burning smell or flooding, they get a fixed reply and a priority handoff. When search isn't confident, or something fails, the agent says so plainly and opens a ticket with what the caller needs and what was tried.
>
> The hardest problem was money. "We won't charge you for that" is a promise the business can't take back. I spent three review rounds on word patterns, and every fix traded one mistake for another. Now Haiku checks every sentence that mentions money against the published terms, and if the check fails, the sentence doesn't go out. On my labelled set it caught all 61 promises and didn't block any of the 47 fair sentences. That's the set I tuned it on, though, so it's not independent proof.

**Sources:** decision log, money checks (D43); `data/results/money_check/summary.json`.

## 5. What the numbers say (2:34–3:33)

**On screen:** the Results tab **[NOT BUILT YET]**, or `data/results/final/summary.json`.

> Now, the numbers. The final test runs one unseen case per pattern, weighted by how often that pattern really happens. Each starts on a clean copy of the database. Codex grades the conversation, and code checks every database change.
>
> Reviews caught that 32 of the 52 test scripts gave the caller the wrong identity, so I fixed the generator and rebuilt the locked test set, twice, before any tuning. And Claude Fable agreed with Codex on 25 of 30 grades, so this is model-checked, not human-checked.
>
> So here's where it landed. Across **[FINAL: scenarios]** patterns, standing for **[FINAL: weighted calls]** real calls, the agent finished **[FINAL: containment]** percent correctly without staff. Its scope caps that at **[FINAL: scope ceiling]**, or **[FINAL: adjusted ceiling]** without actions only staff can take, and staff resolve 73 percent. **[FINAL: wrong confident]** percent were confidently wrong, and the range is **[FINAL: interval low]** to **[FINAL: interval high]**. That's **[below / within]** the 60 to 75 percent target, reported exactly as measured.

**Sources:** decision log, test-case fixes (D40, D42), honest containment (D1); `data/results/final/summary.json`; `data/results/grader_check.json` (Fable and Codex agreed on 25 of 30).

**Working-set reference, not for the video:** the last quick run (`data/results/quick-final-run1/summary.json`, 20 working-set scenarios) gave 43 percent containment, a 70 percent scope ceiling and 10 percent wrong confident answers.

## 6. Running without me, and close (3:33–3:50)

**On screen:** the "Capacity imbalance by zone" table in `docs/FINDINGS.md`.

> It's built to run without me: spending caps, alerts, an outside uptime check and a nightly calendar reset **[NOT BUILT YET]**. And the biggest win for this business isn't the agent. The north zone has 70 percent of the customers but only 31 percent of the bookable slots.

**Sources:** `docs/ARCHITECTURE.md` (monitoring); `docs/FINDINGS.md` (executive findings).

## Before recording

1. Run the final held-out evaluation (Task 27) and fill every **[FINAL]** value from `data/results/final/summary.json`, choosing "below" or "within" in section 5.
2. Check each **[NOT BUILT YET]** line against the deployed site and cut anything that didn't ship.
3. Read the script aloud with a timer. If it runs over 4 minutes, shorten section 3's second paragraph first, then section 2's labelling sentences.
4. Have the six "try these" scenarios from the Results tab ready in the browser for the on-screen shots.
