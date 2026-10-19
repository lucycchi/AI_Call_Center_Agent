Do not read or change any files. You are grading a customer-service assistant for Meridian Home Comfort, a heating,
cooling and plumbing company. Each item below is graded on its own, pass or fail, with this rubric. A partly correct
answer fails.

For a "knowledge answer" (a question, the assistant's answer, a reference answer written from the current company
documents, and the passages the assistant was given):
- correct: the answer states every key fact of the reference answer and contradicts none of them. If the reference
  answer is empty, the question cannot be answered from the documents: correct means the assistant passed it to a team
  member without stating facts it was not given. Three rules settle the close cases:
  - a guess beyond the documents ("it likely would", "probably yes") fails, even when a caveat follows it;
  - a disclaimer the reference includes, such as "the technician confirms the final price on site", is a key fact;
  - the answer is graded against the reference whatever its passages contained: a fact the passages lacked is still
    missing, and the answer fails;
  - a reference may cover more than this question asked, because it was written for every caller with this kind of
    question: facts in the reference that the question did not ask about do not fail an answer that leaves them out.
- faithful: every factual claim in the answer is supported by the passages (or, for a "whole_kb" answer, by the
  knowledge base it was given). Saying a team member will follow up is not a factual claim.
- citation_ok: if the answer names a source document, that document contains the fact; null if it names none.
- refusal_ok: only for questions the documents cannot answer (empty reference): true if the assistant handed off
  without stating unsupported facts; otherwise null.

For a "conversation" (the caller's requests with their expected outcomes, what the database showed, the transcript,
and the tickets the assistant opened):
- grade each request in "requests": correct if the assistant did what was expected (answered from the facts given,
  read account details exactly as recorded, booked or changed only after a clear yes, handed off when a handoff was
  expected, offered the earliest slots for an earlier-slot request). A request the assistant dropped is not correct.
- knowledge_correct: the knowledge parts match the reference answer (null if none); lookup_correct: account details
  match the database facts given (null if none). A fact found in "passages", "retrieved_passages" (what the assistant
  was given) or "account_facts" is supported; a fact in none of them is not.
- correct: every request was handled correctly and nothing the caller asked was dropped.
- ticket_actionable: for each ticket, true if a staff member could act without asking the caller to repeat anything
  (who the caller is, what they want, what was tried, constraints, mood); null if no ticket was opened.

For a "ticket": ticket_actionable as above.

Reply with only a JSON list, one object per item, in the same order:
[{"id": "...", "correct": true|false|"partial"|null, "faithful": true|false|null, "citation_ok": true|false|null,
  "refusal_ok": true|false|null, "ticket_actionable": true|false|null, "requests": [{"request": "...", "correct": true|false}],
  "knowledge_correct": true|false|null, "lookup_correct": true|false|null, "why": "one short sentence",
  "model": "<your model name>"}]
