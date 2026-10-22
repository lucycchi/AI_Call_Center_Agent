# Final checks

Three checks ran on the finished project on 2026-10-21: a browser QA of the live site (gstack `/qa`), a security
audit (gstack `/cso`), and a whole-project review by Codex (`docs/FINAL_REVIEW.md`). This page says what each found,
what was fixed, and what the author chose to leave as a known limit. Fixes were made test-first; the full suite
(1,438 tests) passes after them.

## Browser QA of the live site

Run against https://ai-call-center-agent-bvgy9q.fly.dev as a public visitor, at desktop width (1280 px) and phone
width (375 px). The author allowed three public chat messages: a blank message, "How much is a tune-up?" and "I smell
gas". No password was typed on the site. The report and screenshots are kept locally (ignored by Git) in
`.gstack/qa-reports/qa-report-ai-call-center-agent-2026-10-21.md`.

Health score 99 out of 100. No console errors, no broken links. What worked:
- A blank message is not sent.
- "I smell gas" from a public visitor, who has no chat allowance, still got the full safety advice and an urgent
  ticket, and the staff view showed the ticket at once.
- The Results tab draws tables, not raw JSON, and its six "Try these" links open the chat with the question filled in.
- Neither page scrolls sideways at phone width.
- `/health` answers 200. Unknown paths answer 404, and the staff queue answers 403 without a staff session. The API
  documentation pages are off.

Found and fixed:
- **Results tables overlapped.** In the grader-check rows, long values were drawn on top of the "What it means"
  column. The style that lets a long value wrap lost to the more specific style that keeps values on one line. At
  phone width, measure names such as "Containment" also ran into their values. Fixed in the Results page styles
  (`app/web/templates/results.html`), with a test that the wrap rules win.
- **A public question was told the site had hit its usage limit.** Chat is reviewer-only, so "the site has reached its
  usage limit... try again tomorrow" was misleading: tomorrow changes nothing. The web layer now answers a public
  question with "Chat on this demo is open to project reviewers with a reviewer link", before the agent runs. A safety
  report still reaches the agent and gets its advice and ticket. The agent's code is unchanged (`app/web/main.py`).

Left as known limits:
- The grader-check note on the Results tab starts with a lower-case "fable". The text comes from the frozen results
  file, which is part of the measured record and is not edited.
- After an emergency, the agent tells every caller "You can keep asking me other questions here". A public visitor
  cannot, and if they then give their name, the agent's spending guard answers with its usage-limit message, so the
  name is not added to the ticket. Reviewers are not affected. Changing it would change the agent's text.

## Security audit

The gstack security audit ran in its static mode with a ten-minute budget. It finished as **partial**: its scanners
(Gitleaks for secrets, OSV for dependencies, Semgrep, Trivy) did not run, because this machine does not let the
helper isolate them (it needs control of CPU, memory and process limits, which WSL does not give it here). In the
code it read, chiefly the reviewer link, it found no supported findings. The reviewer token is compared in constant
time, is never stored or logged, and a wrong token gets a plain 404. The Codex review below also scanned the tree and
the Git history for committed keys and found none, and the repository's own test (`tests/test_repository.py`) scans
for secrets on every run.

Earlier milestone reviews covered the rest of the security surface: staff sign-in and its attempt limit, the signed
visitor cookie, the message and emergency limits, and masking of phone numbers, emails and streets.

## Codex whole-project review

Codex (`gpt-5.6-sol`, read-only) reviewed the whole project; its report is `docs/FINAL_REVIEW.md`. It listed seven
findings. Each was checked against the code: the mechanics are real in all seven, but six only matter while the
operations database is already failing or when several paid calls arrive at the same instant.

Fixed, as the author chose:
- **Unmasked backup ticket file (F2).** A ticket that could not be saved to the database went to a backup file
  without masking, so a phone number or street given with a warranty booking stayed on the disk in plain text. The
  backup file is now masked like the database.
- **Backup ticket file race (F7).** Saving to the backup file and retrying it had no lock, so a ticket written during
  a retry could be erased, or two retries could save the same ticket twice. Both now take one lock.
- **Lost message (F1).** An accepted message was saved as an empty placeholder and then, in a second write, its text.
  If the second write failed, the text was lost and a retry of the same message was ignored. Both are now written in
  one transaction.

Left as known limits, as the author chose:
- **Voyage calls are not counted (F3).** Search embedding calls are not added to the spending totals or the model-call
  log. They run on Voyage's free allowance, so the spend they leave out is $0.
- **Spending cap race (F5).** The cap is checked before a turn and charged after it, so up to four turns running at
  once could each pass the check on the same remaining amount. The overshoot is a few cents, and the site's Anthropic
  key has a $25-a-month limit in the console behind the app's own caps.
- **Finished reply replays as a failure (F4).** If saving a reply's end marker fails, a reconnect after a restart
  replays that finished reply as a failure and opens an extra error ticket. It needs a database failure at that moment
  and then a restart before the caller's page reconnects.
- **Weak searches leave no record (F6).** When a search finds nothing strong enough and the agent hands off, the
  passages it did find and their scores are not saved. The handoff and its reason ("not enough evidence") are saved.
  Recording them would change the agent's code.

## After the fixes

The fixes were committed, pushed and deployed with `scripts/deploy.sh`, which runs the paid quick run first. The quick
run failed twice before it passed, on the same case (T9e29febc, a repair booking with membership questions): the
simulated caller kept asking whether the membership pays for itself, and the call reached its 60-second limit just
after the booking read-back. Its retry passed both times, but the gate counts the first attempt. None of the fixes
change the agent; the author chose a third try, which passed and deployed.

The live site was then checked again, with two public messages:
- "How much is a tune-up?" now gets "Chat on this demo is open to project reviewers with a reviewer link, so I can't
  answer here", with no mention of a usage limit.
- "I smell gas" still gets the full safety advice and an urgent ticket.
- The grader-check rows on the Results tab wrap inside their column, and at phone width every measure name stays in
  its own column. No console errors on either page.

## Milestone 7: the checks run again

Milestone 7, added after the project was finished, let the agent take five money and membership actions, made a
handoff carry the whole interaction, fixed needless handoffs, and measured the result on 30 fresh test calls. The
checks were run again on the new code on 2026-10-22.

### Codex review of Milestone 7

Codex (`gpt-5.6-sol`, read-only) reviewed the Milestone 7 changes and how they work with the rest; its report is
`docs/MILESTONE7_REVIEW.md`. It listed eleven findings, several reproduced. All eleven were fixed, test-first
(`tests/flows/test_m7_review_fixes.py` and the evaluation tests), as the author chose:

- **A waiting action survived an emergency (I1):** an upgrade read back, then "I smell gas", then "yes" upgraded the
  membership. A safety reply now drops any waiting action.
- **A done action could be confirmed silently (I2):** if the writer's sentence was blocked, the caller saw nothing.
  Done actions are now confirmed in fixed, checked text.
- **Card and bank numbers slipped past the mask (S1):** dotted card numbers and bare bank numbers are now masked and
  get the security reply.
- **A membership change could commit without its record (D1):** both now commit together or not at all.
- **Auto-renew was write-only (I4):** the membership lookup now says when auto-renew is off, and the nightly reset
  clears the setting.
- **Links were recorded as already expired (I5):** a link now expires 24 hours after it is recorded, on one clock.
- **Action records escaped the 30-day purge (S2):** they now go with their conversation.
- **A ticket's "wants" could lose the problem (I6):** it now reads the whole conversation and keeps a problem said
  with an account number.
- **Two actions in one message collapsed into one (I3):** both are now offered, one after the other.
- **The grader accepted missing actions (E1):** it now requires each expected action and excuses only the membership
  columns of a changed customer record.
- **Partial fresh runs used up full-run slots (E2):** a fresh run must now be the whole set, graded.

One mistake was made and undone while fixing them: a new test, before its fix existed, started a real one-call run
(about $0.03 of test-key spend). The test can no longer reach a paid call, and that run was removed from the record.

### Security audit of Milestone 7

The gstack security audit ran in its static, diff-only mode on the Milestone 7 changes. It finished as **partial**
for the same reason as before: its scanners cannot run on this machine. It found one supported finding, low severity:

- **Account changes need only a name and one identifier.** Turning off auto-renew, enrolling or upgrading needs the
  caller's name with an account number, phone or street address, then a plain yes. Someone who knows another
  customer's name and street could change that customer's membership. The author chose to record it as a known limit:
  real identity verification is a declared non-goal, chat is reviewer-only, the customers are synthetic, payment always
  happens on the secure page, and the nightly reset restores membership data. A real deployment would send a one-time
  code to the phone on file before any change.

The audit also confirmed that card numbers never reach a model: the card check runs before the router, and stored
messages are masked.

### The fixed version, measured

The fixed version ran 3 times on the 30 fresh calls (review fixes decision (D59)):

| Measure (average, lowest to highest run) | After Milestone 7 | After the review fixes (live) |
| --- | --- | --- |
| Handed to a person, weighted by calls | 48.3% (46.0 to 51.2) | 53.9% (43.3 to 67.9) |
| Resolved by the agent, weighted by calls | 36.6% (35.5 to 38.8) | 27.1% (18.1 to 38.6) |
| Resolved by the agent, share of the 30 calls | 26.7% (23.3 to 30.0) | 25.6% (20.0 to 30.0) |

By share of calls the two are about level; weighted, the fixed version is lower and much less steady, because the
heaviest cases were missed more often. The review's stricter grader does not explain it: rescoring the earlier runs
with it changes nothing. Upgrades are now completed, but in 5 calls over three runs an action the caller asked for was
not carried out. Finding why would be done on the working set, never by opening the fresh calls.

### Deploy and the live site

The fixed version was deployed with `scripts/deploy.sh`. A first try was cut off when a session ended, and an earlier
one stopped when the quick run's booking-and-membership case (T9e29febc) reached its 60-second limit again; the next
try passed. The Results tab shows all three versions, with the fixed one marked as the live build.
