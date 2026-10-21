# Walkthrough Video Outline

A 3 to 4 minute voiceover for the reviewer, covering the design choices the PRD asks for: how the call drivers were found, why this chunking and retrieval, how handoff works, and what the evaluation numbers say. It explains why each choice was made; it is not a feature tour. Three hard problems are told inside the sections they belong to.

**Status: final script.** Numbers come from `data/results/final/summary.json` (frozen agent `5b8f6899`, committed in `e507410`).

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

**On screen:** "I smell gas near my furnace" in the chat, then the handoff ticket in the Staff view.

> Handoff is decided in code, not in a prompt. A safety check runs first, so if someone mentions gas, a burning smell or flooding, they get a fixed reply and a priority handoff. When search isn't confident, or something fails, the agent says so plainly and opens a ticket with what the caller needs and what was tried.
>
> The hardest problem was money. "We won't charge you for that" is a promise the business can't take back. I spent three review rounds on word patterns, and every fix traded one mistake for another. Now Haiku checks every sentence that mentions money against the published terms, and if the check fails, the sentence doesn't go out. On my labelled set it caught all 69 promises and wrongly blocked just one of 68 fair sentences. That's the set I tuned it on, though, so it's not independent proof.

**Sources:** decision log, money checks (D43, with its 2026-10-21 revision); `data/results/money_check/summary.json` (137 labelled sentences on the frozen agent).

## 5. What the numbers say (2:34–3:33)

**On screen:** the testing frames, then the final numbers, then the Results tab.

> Now, the numbers. The final test runs one unseen case per pattern, weighted by how often that pattern really happens. Each starts on a clean copy of the database. Codex grades the conversation, and code checks every database change.
>
> Reviews caught that 32 of the 52 test scripts gave the caller the wrong identity, so I fixed the generator and rebuilt the locked test set, twice, before any tuning. And Claude Fable agreed with Codex on 25 of 30 grades, so this is model-checked, not human-checked.
>
> So here's where it landed. Across 15 patterns, standing for 122 real calls, the agent finished about 30 percent correctly without staff. That's below the 60 to 75 percent target, and I'm reporting it exactly as measured. But it never gave a confidently wrong answer, every knowledge answer was right, and every safety handoff was correct.
>
> The misses are bookings and routing, and 16 percent of calls need an action only staff can take, so even a perfect agent tops out at 48 percent here. With 15 patterns, the range is wide: 4 to 57 percent.

**Sources:** decision log, test-case fixes (D40, D42), honest containment (D1); `data/results/final/summary.json`; `data/results/grader_check.json` (Fable and Codex agreed on 25 of 30).


## 6. Running without me, and close (3:33–3:50)

**On screen:** the "Capacity imbalance by zone" table in `docs/FINDINGS.md`.

> It's built to run without me: spending caps, alerts, an outside uptime check and a nightly calendar reset. And the biggest win for this business isn't the agent. The north zone has 70 percent of the customers but only 31 percent of the bookable slots.

**Sources:** `docs/ARCHITECTURE.md` (monitoring); `docs/FINDINGS.md` (executive findings).

## Rebuilding the video

The finished video is `video/demo.mp4`; `video/` is not tracked by git. Everything needed to rebuild it is in `video/build/`:

1. `run_app.sh` starts the app on port 8790 with throwaway databases; `record.py booking|gas rec` records the two chat scenes.
2. `slides.html` holds the still frames; they are rendered to `frames/` at 1920 by 1080.
3. The voiceover clips in `video/voiceover/` are generated in the author's cloned ElevenLabs voice from the `>` lines above.
4. `assemble.py` lays each clip over its visuals, switching at paragraph breaks, and writes the video.
