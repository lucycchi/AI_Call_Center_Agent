## Top five by impact

- **Accepted messages can be permanently emptied (F1) — impact rank 1.** [`accept_message()`](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:126) commits the blank placeholder and then separately writes the text-bearing event: `message_id = self.log_message(...)` followed by `self._write("insert into events ...")`. If the second write fails, [`/api/message`](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:365) removes the in-memory reply and re-raises, producing an HTTP failure. A retry is then discarded because [`store.request_reply(*key)`](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:341) finds the blank placeholder; restart recovery reconstructs it with `... or ""` at [app/web/main.py:264](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:264). The caller’s text is lost, and the operations-database failure behavior (R59) returns an error response instead of the required phone-office message. **DEFINITELY WRONG.**

- **Warranty fallback persists unmasked caller data (F2) — impact rank 2.** A warranty ticket includes the original issue text—`wants=f"{claim} claim: {flow.get('issue', '')}"`—at [app/flows/scheduling.py:285](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/scheduling.py:285), while the database-failure path writes the entire unmasked dictionary with `handle.write(json.dumps(ticket) + "\n")` at [app/ops/store.py:209](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:209). Phone numbers, emails, or addresses supplied with the booking therefore remain in plaintext on the attached disk, bypassing the masking-and-retention requirement (R73). **DEFINITELY WRONG.**

- **Voyage calls bypass cost and audit accounting (F3) — impact rank 3.** [app/knowledge/embedder.py:18](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/knowledge/embedder.py:18) calls `self._client.embed(...)` directly. Only Anthropic calls enter `_before()` and `_report()` at [app/core/model_log.py:106](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/model_log.py:106), and the live spend recorder is wired only through those model-call context sinks at [app/web/main.py:289](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:289). Consequently, paid Voyage queries are absent from both the live AI spending caps (R61) and the model-cost audit requirement (R73). **DEFINITELY WRONG.**

- **A successful reply can become a failure after restart (F4) — impact rank 4.** [app/web/main.py:178](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:178) executes `quietly(store.save_reply_end, ...)` and sets `reply.done` even when persistence failed. After restart, the absence of that marker makes [app/web/main.py:250](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:250) classify the completed reply as unfinished and call `fall_back(...)`. A completed booking or answer can therefore replay with an additional false error handoff and ticket, contradicting the conversation restart-survival requirement (R82). **DEFINITELY WRONG.**

- **Concurrent calls can pass the spending cap together (F5) — impact rank 5.** [`refusal()`](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/spend.py:41) checks totals without holding the lock; the lock is acquired only later in [`record()`](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/spend.py:59), after the paid call completed. The production app supplies four reply threads at [app/web/main.py:135](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:135). Calls from parallel conversations can all observe room under the visitor, reviewer, or site cap and all spend, defeating the live AI spending caps (R61). **DEFINITELY WRONG.**

## Security

### Warranty fallback persists unmasked caller data (F2)

- Evidence: [app/flows/scheduling.py:239](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/scheduling.py:239) stores raw input with `flow.setdefault("issue", text)`, later copied into the ticket at [app/flows/scheduling.py:285](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/scheduling.py:285).
- The normal ticket path masks fields—`mask(who), mask(wants), mask(tried), mask(constraints)`—at [app/ops/store.py:195](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:195), but the fallback instead writes `json.dumps(ticket)` directly at [app/ops/store.py:209](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:209).
- Why it matters: caller contact information can persist outside the masked operations database and outside its purge transaction.
- Classification: **DEFINITELY WRONG.**

No committed key, password, token, or webhook credential was found in the current tree or Git history. The history scan excluded the requested HTML, video, frames, and `data/results/` paths.

## Parts working together

### Accepted messages can be permanently emptied (F1)

- Evidence: [app/ops/store.py:126](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:126) first calls `self.log_message(..., "", request_id)`, whose transaction commits at [app/ops/store.py:112](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:112), and only afterward records the masked text in an event at [app/ops/store.py:128](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:128).
- The web error path removes the in-memory reply and re-raises at [app/web/main.py:371](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:371). Its duplicate path later treats the surviving placeholder as a completed acceptance at [app/web/main.py:341](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:341), without submitting work.
- Why it matters: one failed operations write both loses the caller’s text and poisons idempotent retries. It also violates the operations-database failure behavior (R59).
- Classification: **DEFINITELY WRONG.**

### A successful reply can become a failure after restart (F4)

- Evidence: `quietly(store.save_reply_end, ...)` is followed unconditionally by `reply.done = payload` at [app/web/main.py:178](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:178).
- Recovery interprets any request without that saved marker as unfinished and executes `fall_back(...)` at [app/web/main.py:250](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:250).
- Why it matters: the live stream reports success, while durable state says failure. Reconnecting after a restart can create a false error ticket after an action already committed, contradicting the conversation restart-survival requirement (R82).
- Classification: **DEFINITELY WRONG.**

## Requirements end to end

### Voyage calls bypass cost and audit accounting (F3)

- Evidence: the direct paid request is `self._client.embed(...)` at [app/knowledge/embedder.py:18](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/knowledge/embedder.py:18). The cost recorder’s `_before()` and `_report()` calls cover only `messages.create` and `messages.stream` at [app/core/model_log.py:106](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/model_log.py:106).
- The production wiring constructs `Searcher(..., VoyageEmbedder(...))` separately from `RecordingClient` at [app/web/main.py:485](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:485).
- Why it matters: the displayed spend totals and alerts omit a paid service, while the live AI spending caps (R61) and model-cost audit requirement (R73) describe all live AI calls.
- Classification: **DEFINITELY WRONG.**

### Weak retrievals leave no audit record (F6)

- Evidence: [app/flows/knowledge.py:81](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/flows/knowledge.py:81) obtains search results, but when the score is weak it returns `FlowResult([], "handoff", ...)` at line 85, discarding the searched passages and scores.
- The receipt is built only from results placed in `written`—`"passages": [p for r in written ...]`—at [app/core/pipeline.py:585](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:585). A weak-search handoff is not in that collection.
- Why it matters: operators cannot determine what search returned or why the threshold caused a handoff. This contradicts the requirement to log every retrieval (R73) and leaves the Staff receipt requirement (R71) without the relevant evidence.
- Classification: **DEFINITELY WRONG.**

## Data loss and cost

### Concurrent calls can pass the spending cap together (F5)

- Evidence: the cap is read at [app/ops/spend.py:41](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/spend.py:41), but synchronization begins only in `record()` at [app/ops/spend.py:62](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/spend.py:62), after usage exists.
- Four concurrent reply workers are created at [app/web/main.py:135](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/web/main.py:135).
- Why it matters: several paid calls can be admitted against the same remaining balance. Charging is serialized, but admission is not, so the live AI spending caps (R61) are bypassable.
- Classification: **DEFINITELY WRONG.**

### Pending-ticket retry can lose or duplicate tickets (F7)

- Evidence: failure handling appends without synchronization at [app/ops/store.py:209](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:209). Retry independently reads the whole file at line 216, creates tickets, then rewrites or unlinks it at [app/ops/store.py:224](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/ops/store.py:224).
- Every message invokes `retry_pending` at [app/core/pipeline.py:245](/home/lucyc/gauntlet/AI_Call_Center_Agent/app/core/pipeline.py:245), while the web layer permits four concurrent reply threads.
- Why it matters: an append occurring after another thread reads the file can be erased by its later rewrite or unlink; two retry threads can also create the same ticket twice. This can lose the warranty-review ticket required after unverifiable warranty bookings (R53).
- Classification: **DEFINITELY WRONG.**

Test execution did not begin: pytest failed before collection because the review environment had no writable temporary directory. No paid API, live chat, or held-out workflow was invoked, and no project file was modified.