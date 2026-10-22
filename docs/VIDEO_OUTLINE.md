# Walkthrough Video Outline

A 3 to 4 minute voiceover for the reviewer, covering the design choices the PRD asks for: how the call drivers were found, why this chunking and retrieval, how handoff works, and what the evaluation numbers say. It explains why each choice was made; it is not a feature tour. Three hard problems are told inside the sections they belong to.

**Status: final script.** Numbers come from `data/results/final/summary.json` (the frozen held-out run, agent `5b8f6899`) and `data/results/fresh_report.json` (Milestone 7, three runs per agent version on the fresh test set).

Length: 3 minutes 47 seconds of voiceover. Timings are measured from the generated voiceover, which runs at about 165 words a minute.

**Voiceover:** generated in the author's cloned ElevenLabs voice (eleven_multilingual_v2) into `video/voiceover/`. All sections are generated.

| Time | Section | Hard problem told here |
|---|---|---|
| 0:00–0:10 | Opening | |
| 0:10–0:50 | How the call drivers were found | |
| 0:50–1:39 | Documents, chunking and retrieval | The knowledge base contradicts itself |
| 1:39–2:24 | How handoff works | Stopping the agent from promising money |
| 2:24–3:34 | What the numbers say | Making the containment number trustworthy (the threshold story, D48, was cut for time) |
| 3:34–3:47 | Running without me, and close | |

## 1. Opening (0:00–0:10)

**On screen:** the live chat page, with one booking going through.

> Hi, I'm Lucy. I built a chat agent for Meridian Home Comfort's call center. I'll walk you through what I decided to automate, how I kept it honest, and whether it actually works.

## 2. How the call drivers were found (0:10–0:50)

**On screen:** the "Top call reasons" table in `docs/FINDINGS.md`.

> So, the first thing I noticed: the 420 transcripts are templated. Strip out the names and numbers and they collapse into just 52 patterns. Haiku labelled every call, Codex checked every pattern blind, and Claude Fable checked a third of them. They agreed a hundred percent, which says more about how clean this data is than about real calls.
>
> Bookings, billing and membership make up 68 percent of calls, so that's where I focused. I drew the line at authority and risk. Disputes, refunds and safety go to a person, including a burning smell, which staff booked as an ordinary visit 16 times. Routine money actions it does itself, after a read-back and a clear yes.

**Sources:** `docs/FINDINGS.md` (method, top call reasons, agent scope, staff policy errors).

## 3. Documents, chunking and retrieval (0:50–1:39)

**On screen:** `data/document_list.csv` and `data/conflict_register.csv`, then the retrieval comparison.

> The documents were the real trap. A 2024 scheduling guide sits right next to the current docs and contradicts the FAQ, and two current pages disagree about which towns are served. So folders and dates weren't enough.
>
> Instead, an explicit list decides which documents are searchable, and a conflict register settles each known disagreement. Internal policies become rules in code, never text the model can quote. Chunks follow each document's own sections, and the fee table stays intact so every price keeps its label.
>
> I tested search on its own first. The standard merge of keyword and meaning search sometimes buried the right answer, so I keep each method's top hit before merging. On 25 practice questions, combined search had a correct source in the top five every time.

**Sources:** decision log, documents (D22) and combined search (D41); `data/results/retrieval/summary.json` (working set, 25 questions).

## 4. How handoff works (1:39–2:24)

**On screen:** "I smell gas near my furnace" in the chat, then the handoff ticket in the Staff view.

> Handoff is decided in code, not in a prompt. A safety check runs first, so if someone mentions gas, a burning smell or flooding, they get a fixed reply and a priority handoff. When search isn't confident, or something fails, the agent says so plainly and opens a ticket carrying the whole conversation.
>
> The hardest problem was money. "We won't charge you for that" is a promise the business can't take back. I spent three review rounds on word patterns, and every fix traded one mistake for another. Now Haiku checks every sentence that mentions money against the published terms, and if the check fails, the sentence doesn't go out. On my labelled set it caught all 69 promises and wrongly blocked just one of 68 fair sentences. But that's the set I tuned it on.

**Sources:** decision log, money checks (D43, with its 2026-10-21 revision); `data/results/money_check/summary.json` (137 labelled sentences on the frozen agent).

## 5. What the numbers say (2:24–3:34)

**On screen:** the testing frames, then the final numbers, then the Results tab.

> Now, the numbers. Each test call is unseen, weighted by how often it really happens, and starts on a clean copy of the database. Codex grades the conversation, and code checks every database change.
>
> Reviews caught 32 of 52 test scripts giving the caller the wrong identity, so I rebuilt the locked test set, twice, before any tuning. And Claude Fable agreed with Codex on 25 of 30 grades, so this is model-checked, not human-checked.
>
> So here's where it landed. On the held-out calls, the frozen agent finished about 30 percent correctly, against 64 percent on practice calls. That gap tells me my fixes fit the practice calls more than new ones. It never gave a confidently wrong answer, though. The misses were needless handoffs, bookings and routing.
>
> So Codex wrote 30 fresh test calls blind, before I changed anything, and I fixed only what the practice calls showed. Over three runs each, containment rose from 12 to 37 percent, and handoffs fell from 78 to 48. Still short of the 60 to 75 percent target, reported exactly as measured.

**Sources:** decision log, test-case fixes (D40, D42), honest containment (D1); `data/results/final/summary.json`; `data/results/grader_check.json` (Fable and Codex agreed on 25 of 30).


## 6. Running without me, and close (3:34–3:47)

**On screen:** the "Capacity imbalance by zone" table in `docs/FINDINGS.md`.

> It's built to run without me: spending caps, alerts, an outside uptime check and a nightly calendar reset. And the biggest win for this business isn't the agent. The north zone has 70 percent of the customers but only 31 percent of the bookable slots.

**Sources:** `docs/ARCHITECTURE.md` (monitoring); `docs/FINDINGS.md` (executive findings).

## Rebuilding the video

The finished video is `video/demo.mp4`; `video/` is not tracked by git. Everything needed to rebuild it is in `video/build/`:

1. `run_app.sh` starts the app on port 8790 with throwaway databases; `record.py booking|gas rec` records the two chat scenes.
2. `slides.html` holds the still frames; they are rendered to `frames/` at 1920 by 1080.
3. The voiceover clips in `video/voiceover/` are generated in the author's cloned ElevenLabs voice from the `>` lines above.
4. `assemble.py` lays each clip over its visuals, switching at paragraph breaks, and writes the video.
