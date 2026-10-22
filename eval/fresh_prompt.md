# Write test calls for a home-services call center

You are writing realistic test conversations for a chat assistant that answers customers of **Meridian Home Comfort**,
a heating, cooling and plumbing company in the Austin, Texas area. You never see the assistant, its code or its
results, and you must not look for them: use only the files in this folder.

The files:

- `docs/`: the company's current customer documents (FAQ, fees, prices, membership, warranty, service area, hours).
  These are the only source of truth for any answer.
- `calls/<case id>.txt`: two real transcripts of calls with that case's reason, so you can hear how these customers
  talk. Staff in the transcripts sometimes break company policy; never treat what staff said as the right answer.
- The list of cases to write is at the end of this file.

The story's "now" is **Friday 16 October 2026, 9:00 a.m. in Austin**.

## What to write for each case

One scenario per case, for its call reason and sub-reason. Each must be a **new situation**: do not copy or lightly
reword a transcript. Change the problem, the details, the order things come up and the wording, as a different
customer with the same kind of need would.

- **The caller's messages only**, in order, as they would type them in a chat window: 3 to 8 short messages. The
  assistant's replies are not written; the caller simulator reacts to them. Write messages that still make sense
  whatever the assistant answers in between, such as giving details when asked.
- **Identity:** the assistant must identify a caller before an account question, a booking or a change. Use the
  placeholders `{name}`, `{account}` (an account number such as MHC-12345), `{phone}`, `{address}` (street only) and
  `{city}`; never invent real-looking values. Most callers give a name plus one of the others when asked; a few give
  them up front.
- **Variety across the set:** about a third of the cases also ask a second, related thing (see "Second requests").
  Some callers are vague at first, some correct a detail, some are short-tempered or chatty. Keep it realistic: no
  attempts to trick or break the assistant.
- **Booking calls** say what is wrong and, when asked, when they would like a visit.
- **Billing calls** about a specific invoice give its amount as `${amount}` and say whether they already paid.
- **Existing-appointment calls** are about the date given for that case in the list.

## Second requests

Each second request has a short description, one of these kinds, and the caller's exact message that asks it
(copied from your script):

- `knowledge`: a question answered from the documents (give a reference answer, below)
- `lookup`: a question about the caller's own account (balance, renewal date, system install date)
- `booking:hvac_repair`, `booking:hvac_tune_up`, `booking:plumbing` or `booking:estimate`: book a visit
- `earlier slot`: asks for an earlier time than the one offered
- `action:payment link`, `action:enrol`, `action:upgrade`, `action:autopay` or `action:cancel auto-renew`: asks the
  company to do something to their bill or membership

## Reference answers

If the caller asks anything the documents answer (in the main request or a second one), write the correct answer from
`docs/` only, in one to three plain sentences, and the evidence: for each supporting passage, the file name, the exact
section heading (without the `#` marks) and one to three short phrases copied **exactly** from lines in that section.
If the documents do not answer it, give no reference answer.

## Output

Reply with **only** a JSON array, one object per case, in the order listed:

```json
{
  "case_id": "F07",
  "sub_reason": "pay an invoice",
  "caller_script": ["...", "..."],
  "card_needs": {"city": null, "tier": null, "brand": null, "install_after": null, "install_before": null},
  "invoice": null,
  "appointment": null,
  "extra_requests": [],
  "knowledge": null
}
```

- `card_needs`: only what the story requires of the customer, else null. `city`: one of Round Rock, Cedar Park,
  Pflugerville, Georgetown, Leander, Hutto, Austin, Kyle, Buda (use `{city}` in the script, not the name). `tier`:
  `none`, `standard`, `plus` or `member` (either plan). `brand`: Trane, Carrier, Goodman, Rheem, Lennox or American
  Standard. `install_after` / `install_before`: dates (YYYY-MM-DD) when the system's age matters.
- `invoice`: for billing calls about an invoice, `{"amount_dollars": 245, "paid": false}`; otherwise null.
- `appointment`: for existing-appointment calls, `{"window": "08:00-12:00" or "12:00-16:00" or "13:00-17:00" or
  "16:00-19:00" or null, "service": "hvac_repair", "hvac_tune_up", "plumbing" or "estimate"}`; otherwise null.
- `extra_requests`: `[{"request": "...", "kind": "...", "caller_words": "..."}]`.
- `knowledge`: `{"reference_answer": "...", "evidence": [{"file": "...", "heading": "...", "phrases": ["..."]}]}`
  or null.
