# Independent check of the template grouping: report (Claude Fable 5.1)

Checked against: `data/templates.csv` (420 rows, 52 templates), `data/template_merges.csv` (three brand merges), `pipeline/templates.py`, and all 420 files in `call_data/call_transcripts/`.

## 1. Verdict

**Mostly correct, with one class of fix: no template needs splitting, but the nine "waitlist" templates are the same call as their "booked" twins and should be merged into them, giving 43 templates by my count.** The earlier guess of 70 to 120 was far too high, and the first reviewer's two objections (grouping on a one-word outcome; not removing names) turn out to have had no effect on the result for this data. If the project decides that "staff offered the waitlist" counts as a different staff response, 52 is defensible; either way nothing in the 52 is wrongly mixed.

## 2. Templates that should be split

None. I opened every call in every template (see section 6) and found no template containing a call with a different request, a different staff action, an extra request, or a different ending.

Inside every template, the only things that vary are:

- the caller's name, account number, phone number or address;
- numbers: invoice numbers, dollar amounts, dates, days of the week, time windows, equipment brand, install age;
- filler ("Um", "uh");
- one of six interchangeable greetings (for example "Thanks for calling Meridian, this is Kayla. How may I help?" versus "Meridian Home Comfort, Denise speaking. What can I do for you?");
- one of three interchangeable identity checks ("Do you have your account number handy? ... Perfect, and can you confirm the name?", "Can I get your name and the phone number on the account?", "Let me verify the account. Name and service address?");
- one of five interchangeable lead-ins before a lookup ("One moment.", "Let me take a look.", "Let me pull that up.", "Bear with me one second.", "Okay, give me just a sec here.");
- one of four interchangeable closings ("Anything else today? / Nope, that covers it. / Alright, take care." and three others);
- randomly inserted line-noise exchanges that carry no content ("Sorry, you cut out for a second." / "I can hear you fine.", "Hold on, my dog is barking." / "No problem, take your time.", "Sorry, I'm driving, one sec.", "Can you hear me okay?").

For booking calls there are also four interchangeable ways the caller phrases the request wrapper ("I'm calling to book a repair, the furnace won't kick on." / "Yeah, I need to schedule a service call. The furnace won't kick on." / "Hi, the furnace won't kick on and I'd like to get someone out to look at it." / "Hey, so the furnace won't kick on. What's the soonest you can get a tech out?"), all of which the code strips correctly; for example, furnace booked (Tb456e16e) contains all four forms in the calls CALL-20260709-0103, CALL-20260810-0296, CALL-20260716-0020 and CALL-20260808-0159 and every one of them continues with the identical staff script "I'm sorry to hear that, let's get you taken care of." ... "You're booked. The diagnostic fee is $89 and that gets applied toward the repair if you go ahead with it. Is the unit still a Trane?" ... "Got it. You'll get a text the morning of with the tech's name and a 30 minute heads-up before arrival."

A few templates have a content slot that takes one of several values. I judged these to be "different details", not different calls, because the caller's request and every staff step are otherwise identical:

- Invoice differs from quote (T4ecda9c7): the explanation is "the after-hours rate" (CALL-20260714-0246), "the permit fee" (CALL-20260805-0214) or "the disposal fee" (CALL-20260811-0299), always inside the same line "I see the quote and the invoice. The difference is the ... which wasn't on the verbal quote." and always followed by "I understand. I'll flag this for a billing supervisor to review and they'll call you back within one business day."
- Unknown invoice (Tb9afdda4): the line item is "the refrigerant recharge", "the drain line clearing", "the blower motor", "the capacitor replacement" or "the contactor replacement", always inside "That's from the service visit on the Nth. It's the diagnostic fee plus the ..." (CALL-20260710-0373, CALL-20260728-0193, CALL-20260805-0244, CALL-20260905-0201, CALL-20260908-0257).
- Confirm Thursday appointment (T2d967470): "for a water heater inspection", "for a AC repair" or "for a tune-up" (CALL-20260710-0124, CALL-20260805-0154, CALL-20260911-0034).
- Compressor warranty (Tc36da844): brand (Trane, Goodman, Carrier, Rheem) and "installed 2 / 3 / 4 years ago" vary; the reviewed brand merge was right. All seven calls carry the same "... parts are covered 10 years if registered, which yours is. So the compressor part is covered. Labor is covered for 2 years through us, so labor would be billable." and "Typically $600 to $900 depending on the unit."
- Warranty transfer (T9f473de6): the brand found at the address varies ("I see a Carrier installed there." in CALL-20260722-0161, "I see a Rheem installed there." in CALL-20260730-0346).

## 3. Templates that should be merged

### 3a. The nine booked/waitlist pairs (recommended)

The code names the outcome "waitlist" whenever the staff script contains the word, but every "waitlist" call is a booking call in which the caller pushes back once and then books the same slot anyway. Compare the furnace booked call CALL-20260709-0103 with the furnace waitlist call CALL-20260825-0370 (template furnace waitlist, T1c979c8b). Both open with "I'm calling to book a repair, the furnace won't kick on." / "I'm sorry to hear that, let's get you taken care of.", verify the account, ask "What day works best for you?", offer a window ("I have a morning window tomorrow, 8 to 12. Would that work?"), and both end "You're booked. The diagnostic fee is $89 ..." / "Got it. You'll get a text the morning of ...". The only difference is one inserted exchange in the waitlist call:

> Customer: Um, can you do anything earlier?
> Agent: Unfortunately that's the earliest I have for a non-emergency. I can add you to the waitlist for cancellations.
> Customer: Okay, do that. And book the slot.

That exact three-line exchange, word for word, is the sole difference in all 34 waitlist calls I read. The caller's request is identical; the staff still books; the ending is identical. A person reading the two would say "same call, this caller asked for something sooner". It is a branch inside the booking script, exactly like the three interchangeable identity checks, and for the purpose templates serve (keeping near-identical calls off both sides of the tune/test split) a waitlist call and a booked call for the same issue are near-identical. The pairs:

| Issue | Booked template (calls) | Waitlist template (calls) | Merged size |
|---|---|---|---|
| Furnace won't kick on | Tb456e16e (16) | T1c979c8b (3): CALL-20260825-0370, CALL-20260830-0269, CALL-20260907-0232 | 19 |
| Kitchen sink backing up | T3baed8ff (12) | T1b970162 (6): CALL-20260709-0365, CALL-20260720-0216, CALL-20260802-0282, CALL-20260811-0369, CALL-20260812-0116, CALL-20260822-0383 | 18 |
| Burning smell from vents | T28588235 (11) | Teff9802d (5): CALL-20260706-0182, CALL-20260806-0377, CALL-20260906-0032, CALL-20260908-0029, CALL-20260916-0311 | 16 |
| Water pooling around indoor unit | Tf995585c (11) | T81429224 (5): CALL-20260819-0245, CALL-20260830-0130, CALL-20260908-0052, CALL-20260908-0205, CALL-20260912-0218 | 16 |
| Annual tune-up | Tfc7d7be8 (12) | Tf0d9c2f5 (4): CALL-20260721-0110, CALL-20260818-0184, CALL-20260828-0211, CALL-20260911-0179 | 16 |
| Thermostat blank | Td1e329a6 (10) | Td12bdf25 (3): CALL-20260723-0172, CALL-20260812-0302, CALL-20260913-0044 | 13 |
| AC runs but air is warm | T9bb3779a (9) | T391b9f20 (2): CALL-20260714-0178, CALL-20260726-0141 | 11 |
| AC making a loud grinding noise | T9f56ade3 (6) | T70425efa (3): CALL-20260721-0242, CALL-20260902-0027, CALL-20260919-0402 | 9 |
| Water heater pilot light keeps going out | T8f5cf73c (4) | T6f36e785 (3): CALL-20260802-0015, CALL-20260810-0088, CALL-20260830-0090 | 7 |

The tenth booking issue, "my AC isn't cooling" (T1dee0920, 7 calls), has no waitlist variant and needs no change.

If the project prefers to keep "offered the waitlist" as its own staff response, the 52 stands; but then the `outcome` column should not say "waitlist" alone, because every one of these calls is also booked.

### 3b. Looked at and rejected

- Three escalation complaints: rude technician (Taa2454c8), second opinion on a $4,000 replacement (Ta3b7b18f), three calls and no callback (T19162cee). The staff side is identical in all 16 calls ("I'm really sorry. I'm going to escalate this to our service manager. She'll call you back today." / "Today. Not next week." / "Today. I've marked it urgent."), but the caller's request is a different complaint in each, so by the project's definition they are three templates. Keep separate.
- Three safety calls: carbon monoxide detector (T1d504a74), gas smell (Tea4efe8a), sparks from outdoor unit (T85ab9f16). Identical staff script ("Okay, first thing: if you smell gas or your CO detector is going off, leave the house right now and call your gas utility or 911 from outside. Don't flip any switches."), different requests. Keep separate (see section 5 on the one-call template).
- "The AC runs but the air is warm" (T9bb3779a) versus "My AC isn't cooling" (T1dee0920): same staff script, but the requests are different sentences, not the same sentence with details changed. Keep separate; borderline if the project later wants coarser groups.
- "How much is the maintenance plan" (T0a995037) versus "What does the Comfort Club membership actually include" (Tbaf67f84): different questions and different staff answers. Keep separate.
- The ten booking issues all share one staff script and differ only in the issue phrase; by the definition they are ten templates because the caller's request differs. Keep separate, but note that the staff side of any one of them teaches a model the staff side of all ten, so a tune/test split by template will not isolate the booking script itself.

## 4. Names and personal details

Names and personal details did not split or join any template.

- The request is taken from the first content-bearing customer line, and in all 420 transcripts that line never contains a name, phone number or address. I checked every first customer line: the only ones with "I'm" are "I'm calling to book a repair", "I'm thinking about replacing it", "I'm driving, one sec", "I'm a member" and "I'm not sure what it's for". Names only ever appear in the identity-check reply (for example "Wei Garcia." in CALL-20260709-0103, "Sure, it's Priya Brown, 512-516-6351." in CALL-20260721-0258, "Tom Murphy, 1077 Maple St, Pflugerville." in CALL-20260825-0370) and in the warranty-transfer address line ("It's 4682 Maple St, Leander." in CALL-20260722-0161), none of which the grouping key reads.
- The same caller names recur in different templates, for example "Beth Patel" in the repeat-repair call CALL-20260712-0007 and the rude-technician call CALL-20260718-0062, and "David Garcia" in the AC-warm call CALL-20260906-0348 and the move-appointment call CALL-20260917-0395. Because the key ignores names, these did not join anything.
- Staff names (Denise, Kayla, Marcus, and so on) appear in the greeting and the header; the outcome regexes do not match on them, so they had no effect either. Every template contains calls from several different staff members.
- The three line-noise openers that sometimes precede the request ("Sorry, you cut out for a second.", "Sorry, I'm driving, one sec.", "Can you hear me okay?") are all on the code's skip list, and no template was created from one of them.

So the first reviewer's point that the code "does not remove names" is true of the code but harmless for this data. If a future transcript set has callers who give their name inside the request sentence, it would matter.

## 5. Small templates (one or two calls)

- Sparks from the outdoor unit, one call (T85ab9f16, CALL-20260717-0180): genuinely unique request ("There are sparks coming from the outdoor unit."). The staff response is the gas/CO script copied verbatim from the other two safety templates, which does not actually fit sparks; that is a generator quirk, not a grouping error. It should stay its own template, which means it can only ever sit on one side of the split.
- AC runs but air is warm, waitlist, two calls (T391b9f20, CALL-20260714-0178 and CALL-20260726-0141): not unique; merge into AC runs but air is warm, booked (T9bb3779a) per section 3a.

For completeness, the three-call templates: gas smell (Tea4efe8a) is genuine; the other four (grinding noise waitlist T70425efa, thermostat waitlist Td12bdf25, pilot light waitlist T6f36e785, furnace waitlist T1c979c8b) are waitlist twins to merge. Four-call templates: "two things" AC plus plan (T9e29febc), member discount on a new system (T2603f4e6) and pilot light booked (T8f5cf73c) are genuine; tune-up waitlist (Tf0d9c2f5) is a twin to merge. Five-call templates: burning-smell waitlist (Teff9802d) and water-pooling waitlist (T81429224) are twins to merge; second opinion (Ta3b7b18f), CO detector (T1d504a74), three calls no callback (T19162cee), commercial quote (Teba1e31f) and wrong number (Tc749ab58) are genuine.

## 6. Method

- Parsed `data/templates.csv` and listed the calls of every template (52 templates, 420 calls, sizes 1 to 16).
- Opened and read every transcript: 420 of 420, so all calls in all 52 templates, not just three per template. I read them grouped by template so that calls in the same template sat next to each other, and compared the caller's request, the identity check, each staff step, what was offered or done, and how the call ended.
- As a cross-check, ran a small read-only script in my scratchpad that lowercased each call, replaced numbers with "#", stripped filler, and counted how many calls in each template contain each distinct staff line; this confirmed that the lines that vary inside a template are only the greeting, identity check, lead-in, closing, noise exchanges, and the slot values listed in section 2.
- Surveyed the first customer line of all 420 files for names.
- Read `pipeline/templates.py` to understand the key (cleaned first request line plus a one-word staff outcome) and the merge list. I did not run any pipeline script or anything that calls an AI service, and I created no file in the project other than this report.

Observations outside the grouping question, for whoever uses the `outcome` column later: the label is only a grouping key and is fine for that, but it is not always an accurate description of the call. "waitlist" calls are also booked; "two things" (T9e29febc) is labelled "answered" although the agent adds the membership and books a visit ("Done. I have tomorrow 12 to 4." / "Book it."); the replacement quote (Tbc5df324) is "booked" by way of "I have an advisor available Saturday at 4pm."

## 7. Confidence

High that no template needs splitting and that the within-template variation is only names, numbers, filler and the interchangeable greeting/verification/closing/noise lines: I read all 420 calls, and the script count agrees.

High that the nine waitlist templates are the booked script plus one fixed three-line exchange: the exchange is word-for-word identical in all 34 waitlist calls. Medium on whether to count that as "the same call", because it is a definitional choice; my recommendation is to merge, which gives 43 templates. Under either reading, the first reviewer's conclusion that 52 is too low is not supported by the transcripts, and the second reviewer's reading is correct apart from the booked/waitlist duplication.
