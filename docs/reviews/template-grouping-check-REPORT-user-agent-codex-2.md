# Independent template grouping check — user-agent-codex-2

## 1. Verdict

**The grouping is correct: 52 templates; 0 existing templates need splitting and 0 existing templates need merging.**

This is a judgment about the supplied calls under the stated “same call with different details” definition, not an endorsement of the grouping algorithm for arbitrary future calls. I compared the dialogue, including identity checks, later requests, staff actions, and endings. The earlier estimate of 70–120 is not evidence that this dataset needs that many groups.

I treat a template as a repeated caller scenario and staff handling sequence, rather than a verbatim script. Greetings, polite sign-offs, temporary interruptions, interchangeable ways to find the account, equipment brands, and account-specific invoice or appointment details do not independently create new scenarios. I retain distinctions in reported symptoms, additional requests, and staff handling branches. These interpretation choices are explicit below because the numerical answer depends on what counts as a meaningful change.

## 2. Templates that should be split

**None found.** No sampled call introduces a different substantive request, handling branch, or ending within its current group. The additional all-file dialogue-line screen did not expose a missing branch either. Important within-group variations are real, but remain the same response pattern:

- **Identity checks:** T0ad82d45 includes CALL-20260713-0314, where staff ask, “Let me verify the account. Name and service address?”, and CALL-20260806-0174, where staff ask, “Um, can I get your name and the phone number on the account?” Both then explain prorating, obtain consent, upgrade the plan, and send the payment link. CALL-20260904-0144 ends that business sequence with “You're upgraded. I'll send a payment link for the prorated amount.” In T148d6c30, CALL-20260825-0415 instead uses “Do you have your account number handy?” followed by “Perfect, and can you confirm the name?” This adds a verification turn, but does not change the caller's billing issue or its resolution. I count these as alternative implementations of the same identify-the-account step, not separate call scenarios. This is the principal interpretive boundary: a rule requiring identical identification fields and question counts would produce finer groups, but would separate otherwise near-identical calls for the proposed tuning/test split.
- **Quote/invoice discrepancy, T4ecda9c7:** CALL-20260816-0224 says, “The difference is the after-hours rate which wasn't on the verbal quote.” CALL-20260910-0387 says, “The difference is the permit fee which wasn't on the verbal quote.” A targeted check of all 16 explanation lines also found disposal fees. The pattern remains identify the account, compare quote and invoice, explain an omitted charge, hear the objection, and escalate. The shared substantive action is: “I understand. I'll flag this for a billing supervisor to review and they'll call you back within one business day.” Both quoted calls contain that line. The charge category fills a detail in the same explanation; it does not change the handling.
- **Invoice explanation, Tb9afdda4:** CALL-20260710-0373 says, “It's the diagnostic fee plus the refrigerant recharge.” CALL-20260825-0266 says, “It's the diagnostic fee plus the drain line clearing.” CALL-20260915-0303 says, “It's the diagnostic fee plus the contactor replacement.” All three callers then ask, “Oh okay. Can you email me an itemized copy?”, and staff respond, “Absolutely, sending that to the email on file now.” The service billed varies; the request and the lookup/explanation/email sequence do not. The all-13-line explanation check also found blower motor and capacitor replacement details, with the same itemized-copy action in the all-file screen.
- **Appointment confirmation, T2d967470:** CALL-20260710-0124 says, “Let me take a look. Yes, Thursday 12 to 4, for a water heater inspection.” CALL-20260911-0034 says, “Okay, give me just a sec here. Yes, Thursday 8 to 12, for a tune-up.” Both callers ask to confirm an existing appointment, receive its details, and end without changing it. The appointment's subject is an account detail here; a request to book a tune-up is separately grouped.
- **Endings and interruptions:** T19162cee CALL-20260730-0306 inserts “Sorry, you cut out for a second.” / “Sure, go ahead.” before returning to the same urgent callback exchange. CALL-20260724-0391 and CALL-20260831-0051 both reach “Today. I've marked it urgent.” Their different courtesy sign-offs do not represent different outcomes. I found no sampled unresolved-versus-resolved ending hidden by those sign-offs.

## 3. Templates that should be merged

**None among the 52 current templates.** I checked similar requests as well as templates sharing an outcome. The strongest candidates and reasons to retain them are:

### Booking versus booking plus a waitlist request

These are not booked-versus-unbooked calls. Both branches book. The latter contains an additional request and staff offer:

- T9bb3779a CALL-20260728-0050 accepts the offered slot: “That's fine.”
- T391b9f20 CALL-20260714-0178 asks, “Can you do anything earlier?” Staff answer, “Unfortunately that's the earliest I have for a non-emergency. I can add you to the waitlist for cancellations.” The caller says, “Okay, do that. And book the slot.”

That additional exchange is a meaningful difference even though both calls later say “You're booked.” The same distinction occurs in these pairs; complete calls from every pair were compared:

| Caller issue | Ordinary booking | Booking plus waitlist request |
| --- | --- | --- |
| Burning smell from vents | T28588235 | Teff9802d |
| Kitchen sink backing up | T3baed8ff | T1b970162 |
| Furnace will not start | Tb456e16e | T1c979c8b |
| AC runs but air is warm | T9bb3779a | T391b9f20 |
| AC grinding noise | T9f56ade3 | T70425efa |
| Water heater pilot goes out | T8f5cf73c | T6f36e785 |
| Water pooling at indoor unit | Tf995585c | T81429224 |
| Blank thermostat | Td1e329a6 | Td12bdf25 |
| Annual tune-up | Tfc7d7be8 | Tf0d9c2f5 |

For example, T6f36e785 CALL-20260802-0015 contains the same “Can you do anything earlier?” and waitlist offer; T8f5cf73c CALL-20260802-0016 simply accepts with “That's fine.” The CSV's one-word `waitlist` label incompletely describes those calls, but the resulting boundary is justified by their dialogue.

### Similar cooling requests

T1dee0920 CALL-20260716-0367 says, “Um, hey, so my AC isn't cooling. What's the soonest you can get a tech out?” T9bb3779a CALL-20260728-0050 says, “Hey, so the AC runs but the air is warm. What's the soonest you can get a tech out?” The booking sequence is the same, but the second request specifically reports a running unit producing warm air; the first does not establish whether it runs. I retain that symptom distinction rather than assume an unstated diagnosis. Likewise, grinding noise, a blank thermostat, and water pooling are different reported problems despite sharing the booking script. Under a broader AC-repair intent taxonomy some of these could share a label; that is a different granularity from preserving the supplied caller scenarios.

### Same outcome with different requests or actions

- **Multiple issues:** T9e29febc CALL-20260710-0081 asks, “Two things. My AC is blowing warm and I want to get someone out, and I want to know if joining the maintenance plan would save me money on this.” The caller later says, “Yeah, add it and book the visit.” Staff offer the membership benefit and an appointment. That additional membership request and enrollment distinguish it from T9bb3779a and from information-only membership calls. Its `answered` label misses the enrollment and booking, but does not combine it with those other scenarios.
- **Membership information:** Tbaf67f84 CALL-20260707-0148 asks, “What does the Comfort Club membership actually include?” and later “Does it cover plumbing?” T0a995037 CALL-20260712-0104 asks, “How much is the maintenance plan?” and challenges the price with “I thought it was $149?” The former explains benefits and coverage; the latter explains pricing changes and renewal protection. T2603f4e6 CALL-20260727-0300 instead asks, “I'm a member. Do I get a discount on a new system?” These are distinct requests and exchanges, despite all being `answered`.
- **Complaints:** T19162cee CALL-20260724-0391 says, “I've called three times about the same problem and nobody has called me back. I'm done.” Taa2454c8 CALL-20260718-0062 describes a rude technician, mud, and no explanation. Ta3b7b18f CALL-20260710-0335 disputes a replacement recommendation after a second opinion found a capacitor. They share a manager-callback script but present different complaints. T3c30d716 CALL-20260710-0136 asks, “I want a full refund on the repair. It didn't fix anything and I had to call another company.” Staff open a refund review case with “you'll hear back within two business days.” That differs from the urgent same-day service-manager callback and T4ecda9c7's one-business-day billing review.
- **Safety:** Tea4efe8a CALL-20260712-0046 reports, “I smell gas near my furnace.” T1d504a74 CALL-20260721-0093 reports, “My carbon monoxide detector is going off.” T85ab9f16 CALL-20260717-0180 reports, “There are sparks coming from the outdoor unit.” The staff safety script is repeated, including the incongruous gas/CO wording in the sparks call, but the callers report three different hazards. Do not merge solely on that shared response.
- **Redirects:** T8f924285 CALL-20260712-0067 asks about hiring HVAC technicians and receives “Applications go through the careers page on our website.” Tc749ab58 CALL-20260813-0031 asks, “Is this Meridian Dental?” and receives “No, this is Meridian Home Comfort, heating and air.” Different requests and different next steps justify separate `redirect` groups.
- **Warranty:** T7d8fb3e5 CALL-20260711-0248 receives “Since it's under a year, both parts and labor are covered. I'll book a warranty diagnostic at no charge. What day works?” T9919897a CALL-20260712-0007 asks about a repeat blower repair and receives “Yes, let me book that as a warranty recall so there's no fee.” The coverage basis and request differ. Compressor parts/labor eligibility, warranty transfer, and manufacturer registration are also separate questions with different responses; they are not interchangeable `answered` calls.

### Previously merged brands

The reviewed merge list has three mapping rows, combining four former brand-specific groups into the current Tc36da844. These are already merged, so they are **not** new merge recommendations and do not reduce 52 further.

I read all seven current members. The caller asks the same compressor-warranty question with Trane (CALL-20260709-0315), Goodman (CALL-20260719-0153), Carrier (CALL-20260720-0292 and CALL-20260803-0004), or Rheem (CALL-20260811-0085); the remaining two are Trane. CALL-20260709-0315 says, “Trane parts are covered 10 years if registered, which yours is. So the compressor part is covered. Labor is covered for 2 years through us, so labor would be billable.” CALL-20260719-0153 repeats that explanation for Goodman, CALL-20260720-0292 for Carrier, and CALL-20260811-0085 for Rheem. All ask “How much is labor on a compressor?” and receive the same quoted range and technician-quote step. No brand changes the coverage response or ending. Different stated installation ages are numeric details, including synthetic inconsistencies; they do not introduce a different handling branch in these calls.

## 4. Names and personal details

**No demonstrated grouping error caused by names, account numbers, phone numbers, or addresses.** All 420 CSV request fields and the all-file dialogue screen were checked; caller identity appears in the verification/contact-information exchange rather than creating a new substantive request.

- Different names stay together appropriately: T19162cee CALL-20260724-0391 supplies “Um, maria Singh.” CALL-20260831-0051 supplies “Wei Clark.” Both raise the same repeated-no-callback complaint and receive the same urgent escalation.
- The same name does not cause unrelated calls to join: CALL-20260712-0007 supplies Beth Patel's name while asking about a repeat blower repair (T9919897a); CALL-20260718-0062 supplies Beth Patel's name while complaining about technician conduct (Taa2454c8). CALL-20260909-0416 supplies “Carlos Martinez.” for appointment cancellation, while CALL-20260913-0012 supplies the same name for a water-heater booking; these also remain correctly separate.
- Address details in warranty-transfer requests vary without splitting T9f473de6: CALL-20260722-0161 gives “It's 4682 Maple St, Leander.” and CALL-20260830-0105 gives “It's 1706 Brookside Ct, Kyle.” Both receive the transfer-policy explanation and an emailed manufacturer form.
- The three identity-verification routes discussed above collect different fields, but lead back to the same handling sequence. I did not mistake differences in personal values for differences in caller intent.

`pipeline/templates.py` does not implement general name removal. That is a future-data limitation, not proof of a current misgrouping. The inspected requests do not contain a personal name that wrongly fragments or combines a template. The branded compressor requests are the explicit, already-reviewed exception handled by `data/template_merges.csv`.

## 5. One-call and two-call templates

These are the only two templates with one or two members:

- **T85ab9f16 — one call, CALL-20260717-0180:** genuinely unique as a caller scenario in this dataset. “There are sparks coming from the outdoor unit.” differs from the gas and CO requests even though staff reuse the same safety response. Keep it separate. The appropriateness of that response is outside this grouping check.
- **T391b9f20 — two calls, CALL-20260714-0178 and CALL-20260726-0141:** both belong together. Each reports that the AC runs but the air is warm, asks “Can you do anything earlier?”, receives the cancellation-waitlist offer, and says “Okay, do that. And book the slot.” Do not merge them into the larger ordinary warm-air booking group T9bb3779a, which lacks that additional exchange. Their phone-versus-address lookup difference is the routine verification variation explained above.

## 6. Method and complete call inventory

I read all 420 rows of `data/templates.csv`, checked all 52 membership counts, and read `data/template_merges.csv` and `pipeline/templates.py`. The CSV has one row for each of the 420 `.txt` transcript files; Windows `:Zone.Identifier` leftovers were excluded.

For each template of six or more calls, I read the **first, middle (index floor(n/2)), and last** members in CSV order, in full. For every template of five or fewer, I read **every member in full**, including the singleton. This initial full-dialogue sample was **171 distinct calls**. I then read the other four compressor-warranty calls in full, bringing the total to **175 complete transcripts across all 52 templates**. The list below records those exact calls per template.

Separately, read-only Python opened **all 420 transcript files** to screen their dialogue and identification routes. I inspected the resulting distinct dialogue-line inventory after narrowly removing recognized greetings, courtesy closings, filler/interruption exchanges and identity values, and substituting numbers, brands and appointment slots. Unknown lines were retained in that inventory. I also inspected the raw explanation/confirmation lines for all 16 quote discrepancies, all 13 invoice questions, and all 8 appointment confirmations. This broader screen supplements the full-dialogue comparisons; it is not a claim that I manually read all 420 original transcripts end to end. No inference about an unviewed complete call is presented as a full manual comparison.

I compared requests, account identification, questions, offers, confirmations, later requests and endings. I considered all shared-outcome families and the near-request candidates detailed above. A single outcome word was never sufficient evidence of equivalence. All commands were local and read-only until writing this report; no AI-service script was run and no other project file was changed.

In the inventory, “Full reads” means complete transcript reads, not just opening a file for the all-file screen. “Calls” enumerates every CSV member, including members outside that full-read sample.

### T0a995037 — 8 calls; 3 full reads

Request: how much is the maintenance plan. CSV outcome: `answered`.

Calls: `CALL-20260712-0104`, `CALL-20260716-0006`, `CALL-20260721-0108`, `CALL-20260831-0231`, `CALL-20260911-0235`, `CALL-20260912-0139`, `CALL-20260915-0385`, `CALL-20260916-0397`.

Full reads: `CALL-20260712-0104`, `CALL-20260911-0235`, `CALL-20260916-0397`.

### T0ad82d45 — 6 calls; 3 full reads

Request: can i upgrade from the regular plan to the plus plan mid year. CSV outcome: `action`.

Calls: `CALL-20260713-0314`, `CALL-20260714-0019`, `CALL-20260803-0056`, `CALL-20260806-0174`, `CALL-20260812-0405`, `CALL-20260904-0144`.

Full reads: `CALL-20260713-0314`, `CALL-20260806-0174`, `CALL-20260904-0144`.

### T148d6c30 — 11 calls; 3 full reads

Request: i think i got charged twice there are two # charges on my card from you guys. CSV outcome: `answered`.

Calls: `CALL-20260709-0129`, `CALL-20260725-0288`, `CALL-20260726-0331`, `CALL-20260806-0207`, `CALL-20260810-0219`, `CALL-20260825-0415`, `CALL-20260831-0362`, `CALL-20260901-0238`, `CALL-20260910-0358`, `CALL-20260912-0099`, `CALL-20260914-0381`.

Full reads: `CALL-20260709-0129`, `CALL-20260825-0415`, `CALL-20260914-0381`.

### T19162cee — 5 calls; 5 full reads

Request: i ve called three times about the same problem and nobody has called me back i m done. CSV outcome: `callback`.

Calls: `CALL-20260724-0391`, `CALL-20260730-0223`, `CALL-20260730-0306`, `CALL-20260819-0177`, `CALL-20260831-0051`.

Full reads: `CALL-20260724-0391`, `CALL-20260730-0223`, `CALL-20260730-0306`, `CALL-20260819-0177`, `CALL-20260831-0051`.

### T1b970162 — 6 calls; 3 full reads

Request: my kitchen sink is backing up. CSV outcome: `waitlist`.

Calls: `CALL-20260709-0365`, `CALL-20260720-0216`, `CALL-20260802-0282`, `CALL-20260811-0369`, `CALL-20260812-0116`, `CALL-20260822-0383`.

Full reads: `CALL-20260709-0365`, `CALL-20260811-0369`, `CALL-20260822-0383`.

### T1c979c8b — 3 calls; 3 full reads

Request: the furnace won t kick on. CSV outcome: `waitlist`.

Calls: `CALL-20260825-0370`, `CALL-20260830-0269`, `CALL-20260907-0232`.

Full reads: `CALL-20260825-0370`, `CALL-20260830-0269`, `CALL-20260907-0232`.

### T1d504a74 — 5 calls; 5 full reads

Request: my carbon monoxide detector is going off. CSV outcome: `safety`.

Calls: `CALL-20260721-0093`, `CALL-20260805-0290`, `CALL-20260816-0038`, `CALL-20260822-0341`, `CALL-20260905-0318`.

Full reads: `CALL-20260721-0093`, `CALL-20260805-0290`, `CALL-20260816-0038`, `CALL-20260822-0341`, `CALL-20260905-0318`.

### T1dee0920 — 7 calls; 3 full reads

Request: my ac isn t cooling. CSV outcome: `booked`.

Calls: `CALL-20260716-0367`, `CALL-20260720-0279`, `CALL-20260813-0398`, `CALL-20260814-0003`, `CALL-20260826-0095`, `CALL-20260907-0143`, `CALL-20260913-0273`.

Full reads: `CALL-20260716-0367`, `CALL-20260814-0003`, `CALL-20260913-0273`.

### T2603f4e6 — 4 calls; 4 full reads

Request: i m a member do i get a discount on a new system. CSV outcome: `answered`.

Calls: `CALL-20260713-0285`, `CALL-20260727-0300`, `CALL-20260730-0048`, `CALL-20260829-0404`.

Full reads: `CALL-20260713-0285`, `CALL-20260727-0300`, `CALL-20260730-0048`, `CALL-20260829-0404`.

### T28588235 — 11 calls; 3 full reads

Request: i smell something burning from the vents. CSV outcome: `booked`.

Calls: `CALL-20260706-0101`, `CALL-20260709-0082`, `CALL-20260710-0028`, `CALL-20260713-0075`, `CALL-20260714-0234`, `CALL-20260715-0289`, `CALL-20260725-0329`, `CALL-20260810-0239`, `CALL-20260820-0013`, `CALL-20260904-0418`, `CALL-20260915-0133`.

Full reads: `CALL-20260706-0101`, `CALL-20260715-0289`, `CALL-20260915-0133`.

### T2d967470 — 8 calls; 3 full reads

Request: just wanted to confirm i still have someone coming thursday. CSV outcome: `confirmed`.

Calls: `CALL-20260710-0124`, `CALL-20260730-0183`, `CALL-20260805-0154`, `CALL-20260806-0102`, `CALL-20260823-0412`, `CALL-20260830-0209`, `CALL-20260908-0158`, `CALL-20260911-0034`.

Full reads: `CALL-20260710-0124`, `CALL-20260823-0412`, `CALL-20260911-0034`.

### T33be9400 — 9 calls; 3 full reads

Request: my window was # to # and it s #:# nobody s here and nobody s called. CSV outcome: `late_tech`.

Calls: `CALL-20260721-0261`, `CALL-20260725-0355`, `CALL-20260806-0284`, `CALL-20260808-0271`, `CALL-20260813-0247`, `CALL-20260816-0097`, `CALL-20260818-0151`, `CALL-20260830-0388`, `CALL-20260916-0098`.

Full reads: `CALL-20260721-0261`, `CALL-20260813-0247`, `CALL-20260916-0098`.

### T391b9f20 — 2 calls; 2 full reads

Request: the ac runs but the air is warm. CSV outcome: `waitlist`.

Calls: `CALL-20260714-0178`, `CALL-20260726-0141`.

Full reads: `CALL-20260714-0178`, `CALL-20260726-0141`.

### T3baed8ff — 12 calls; 3 full reads

Request: my kitchen sink is backing up. CSV outcome: `booked`.

Calls: `CALL-20260718-0360`, `CALL-20260730-0054`, `CALL-20260801-0024`, `CALL-20260810-0025`, `CALL-20260814-0123`, `CALL-20260818-0206`, `CALL-20260822-0175`, `CALL-20260826-0390`, `CALL-20260827-0344`, `CALL-20260908-0352`, `CALL-20260917-0126`, `CALL-20260919-0037`.

Full reads: `CALL-20260718-0360`, `CALL-20260822-0175`, `CALL-20260919-0037`.

### T3c30d716 — 8 calls; 3 full reads

Request: i want a full refund on the repair it didn t fix anything and i had to call another company. CSV outcome: `callback`.

Calls: `CALL-20260710-0136`, `CALL-20260715-0100`, `CALL-20260812-0169`, `CALL-20260816-0191`, `CALL-20260818-0092`, `CALL-20260821-0353`, `CALL-20260823-0068`, `CALL-20260827-0065`.

Full reads: `CALL-20260710-0136`, `CALL-20260818-0092`, `CALL-20260827-0065`.

### T4ecda9c7 — 16 calls; 3 full reads

Request: the tech quoted me # and the invoice says # that s not what i agreed to. CSV outcome: `callback`.

Calls: `CALL-20260714-0246`, `CALL-20260718-0111`, `CALL-20260729-0278`, `CALL-20260805-0214`, `CALL-20260810-0078`, `CALL-20260810-0162`, `CALL-20260811-0299`, `CALL-20260815-0345`, `CALL-20260816-0224`, `CALL-20260817-0241`, `CALL-20260828-0267`, `CALL-20260901-0127`, `CALL-20260902-0168`, `CALL-20260906-0283`, `CALL-20260909-0119`, `CALL-20260910-0387`.

Full reads: `CALL-20260714-0246`, `CALL-20260816-0224`, `CALL-20260910-0387`.

### T5a0b5fd4 — 14 calls; 3 full reads

Request: i want to set up autopay for my membership. CSV outcome: `action`.

Calls: `CALL-20260709-0347`, `CALL-20260710-0254`, `CALL-20260713-0036`, `CALL-20260713-0263`, `CALL-20260715-0213`, `CALL-20260719-0059`, `CALL-20260719-0226`, `CALL-20260806-0077`, `CALL-20260807-0202`, `CALL-20260811-0275`, `CALL-20260825-0118`, `CALL-20260826-0304`, `CALL-20260906-0055`, `CALL-20260909-0137`.

Full reads: `CALL-20260709-0347`, `CALL-20260806-0077`, `CALL-20260909-0137`.

### T6f36e785 — 3 calls; 3 full reads

Request: the water heater pilot light keeps going out. CSV outcome: `waitlist`.

Calls: `CALL-20260802-0015`, `CALL-20260810-0088`, `CALL-20260830-0090`.

Full reads: `CALL-20260802-0015`, `CALL-20260810-0088`, `CALL-20260830-0090`.

### T70425efa — 3 calls; 3 full reads

Request: the ac is making a loud grinding noise. CSV outcome: `waitlist`.

Calls: `CALL-20260721-0242`, `CALL-20260902-0027`, `CALL-20260919-0402`.

Full reads: `CALL-20260721-0242`, `CALL-20260902-0027`, `CALL-20260919-0402`.

### T738adaab — 14 calls; 3 full reads

Request: i got an email saying my membership is renewing when does it actually charge. CSV outcome: `answered`.

Calls: `CALL-20260707-0096`, `CALL-20260707-0392`, `CALL-20260710-0135`, `CALL-20260713-0253`, `CALL-20260714-0200`, `CALL-20260726-0307`, `CALL-20260809-0128`, `CALL-20260816-0106`, `CALL-20260821-0181`, `CALL-20260830-0259`, `CALL-20260831-0167`, `CALL-20260908-0407`, `CALL-20260913-0342`, `CALL-20260913-0382`.

Full reads: `CALL-20260707-0096`, `CALL-20260816-0106`, `CALL-20260913-0382`.

### T7d8fb3e5 — 14 calls; 3 full reads

Request: i need to file a warranty claim the unit you installed last year stopped working. CSV outcome: `booked`.

Calls: `CALL-20260711-0248`, `CALL-20260712-0227`, `CALL-20260714-0326`, `CALL-20260723-0042`, `CALL-20260727-0215`, `CALL-20260813-0350`, `CALL-20260815-0114`, `CALL-20260823-0295`, `CALL-20260824-0033`, `CALL-20260826-0225`, `CALL-20260827-0084`, `CALL-20260902-0375`, `CALL-20260910-0291`, `CALL-20260914-0009`.

Full reads: `CALL-20260711-0248`, `CALL-20260823-0295`, `CALL-20260914-0009`.

### T81429224 — 5 calls; 5 full reads

Request: there s water pooling around the indoor unit. CSV outcome: `waitlist`.

Calls: `CALL-20260819-0245`, `CALL-20260830-0130`, `CALL-20260908-0052`, `CALL-20260908-0205`, `CALL-20260912-0218`.

Full reads: `CALL-20260819-0245`, `CALL-20260830-0130`, `CALL-20260908-0052`, `CALL-20260908-0205`, `CALL-20260912-0218`.

### T85ab9f16 — 1 calls; 1 full reads

Request: there are sparks coming from the outdoor unit. CSV outcome: `safety`.

Calls: `CALL-20260717-0180`.

Full reads: `CALL-20260717-0180`.

### T8f5cf73c — 4 calls; 4 full reads

Request: the water heater pilot light keeps going out. CSV outcome: `booked`.

Calls: `CALL-20260802-0016`, `CALL-20260810-0058`, `CALL-20260811-0305`, `CALL-20260913-0012`.

Full reads: `CALL-20260802-0016`, `CALL-20260810-0058`, `CALL-20260811-0305`, `CALL-20260913-0012`.

### T8f924285 — 6 calls; 3 full reads

Request: are you guys hiring hvac techs i saw a posting. CSV outcome: `redirect`.

Calls: `CALL-20260712-0067`, `CALL-20260714-0366`, `CALL-20260715-0351`, `CALL-20260716-0379`, `CALL-20260818-0298`, `CALL-20260828-0409`.

Full reads: `CALL-20260712-0067`, `CALL-20260716-0379`, `CALL-20260828-0409`.

### T9919897a — 6 calls; 3 full reads

Request: does the labor warranty cover a repeat repair you fixed my blower in march and it s doing the same thing. CSV outcome: `booked`.

Calls: `CALL-20260712-0007`, `CALL-20260716-0317`, `CALL-20260722-0064`, `CALL-20260729-0324`, `CALL-20260906-0132`, `CALL-20260909-0327`.

Full reads: `CALL-20260712-0007`, `CALL-20260729-0324`, `CALL-20260909-0327`.

### T9bb3779a — 9 calls; 3 full reads

Request: the ac runs but the air is warm. CSV outcome: `booked`.

Calls: `CALL-20260728-0050`, `CALL-20260728-0281`, `CALL-20260801-0334`, `CALL-20260817-0330`, `CALL-20260818-0072`, `CALL-20260904-0265`, `CALL-20260905-0357`, `CALL-20260906-0348`, `CALL-20260910-0400`.

Full reads: `CALL-20260728-0050`, `CALL-20260818-0072`, `CALL-20260910-0400`.

### T9e29febc — 4 calls; 4 full reads

Request: two things my ac is blowing warm and i want to get someone out and i want to know if joining the maintenance plan would save me money on this. CSV outcome: `answered`.

Calls: `CALL-20260710-0081`, `CALL-20260712-0328`, `CALL-20260724-0308`, `CALL-20260917-0332`.

Full reads: `CALL-20260710-0081`, `CALL-20260712-0328`, `CALL-20260724-0308`, `CALL-20260917-0332`.

### T9f473de6 — 8 calls; 3 full reads

Request: we just bought a house and the previous owner had a system installed by you does the warranty transfer. CSV outcome: `answered`.

Calls: `CALL-20260722-0161`, `CALL-20260730-0346`, `CALL-20260803-0086`, `CALL-20260809-0039`, `CALL-20260816-0389`, `CALL-20260823-0142`, `CALL-20260829-0057`, `CALL-20260830-0105`.

Full reads: `CALL-20260722-0161`, `CALL-20260816-0389`, `CALL-20260830-0105`.

### T9f56ade3 — 6 calls; 3 full reads

Request: the ac is making a loud grinding noise. CSV outcome: `booked`.

Calls: `CALL-20260713-0320`, `CALL-20260718-0319`, `CALL-20260720-0157`, `CALL-20260721-0333`, `CALL-20260910-0150`, `CALL-20260918-0294`.

Full reads: `CALL-20260713-0320`, `CALL-20260721-0333`, `CALL-20260918-0294`.

### Ta049acca — 6 calls; 3 full reads

Request: i need to cancel my appointment my brother in law ended up fixing it. CSV outcome: `cancelled`.

Calls: `CALL-20260707-0002`, `CALL-20260724-0325`, `CALL-20260726-0220`, `CALL-20260902-0152`, `CALL-20260904-0340`, `CALL-20260909-0416`.

Full reads: `CALL-20260707-0002`, `CALL-20260902-0152`, `CALL-20260909-0416`.

### Ta12ddc61 — 13 calls; 3 full reads

Request: i want to cancel my comfort club membership. CSV outcome: `action`.

Calls: `CALL-20260710-0364`, `CALL-20260713-0287`, `CALL-20260718-0349`, `CALL-20260719-0217`, `CALL-20260723-0251`, `CALL-20260804-0188`, `CALL-20260806-0230`, `CALL-20260809-0376`, `CALL-20260815-0270`, `CALL-20260828-0120`, `CALL-20260902-0386`, `CALL-20260906-0087`, `CALL-20260908-0017`.

Full reads: `CALL-20260710-0364`, `CALL-20260806-0230`, `CALL-20260908-0017`.

### Ta3b7b18f — 5 calls; 5 full reads

Request: your technician told my wife the system needed a # # replacement and i got a second opinion and it was a # capacitor i want to speak to someone in charge. CSV outcome: `callback`.

Calls: `CALL-20260710-0335`, `CALL-20260726-0189`, `CALL-20260830-0286`, `CALL-20260831-0339`, `CALL-20260906-0411`.

Full reads: `CALL-20260710-0335`, `CALL-20260726-0189`, `CALL-20260830-0286`, `CALL-20260831-0339`, `CALL-20260906-0411`.

### Taa2454c8 — 6 calls; 3 full reads

Request: i want to talk to a manager the tech who came out yesterday was rude tracked mud through my house and left without explaining anything. CSV outcome: `callback`.

Calls: `CALL-20260718-0062`, `CALL-20260722-0198`, `CALL-20260729-0041`, `CALL-20260729-0260`, `CALL-20260730-0222`, `CALL-20260802-0079`.

Full reads: `CALL-20260718-0062`, `CALL-20260729-0260`, `CALL-20260802-0079`.

### Taca6d958 — 14 calls; 3 full reads

Request: i need to pay invoice inv # can i do it over the phone. CSV outcome: `action`.

Calls: `CALL-20260708-0115`, `CALL-20260709-0356`, `CALL-20260717-0359`, `CALL-20260718-0262`, `CALL-20260719-0272`, `CALL-20260721-0125`, `CALL-20260723-0035`, `CALL-20260724-0040`, `CALL-20260727-0138`, `CALL-20260730-0233`, `CALL-20260809-0197`, `CALL-20260810-0008`, `CALL-20260819-0014`, `CALL-20260820-0043`.

Full reads: `CALL-20260708-0115`, `CALL-20260724-0040`, `CALL-20260820-0043`.

### Tb456e16e — 16 calls; 3 full reads

Request: the furnace won t kick on. CSV outcome: `booked`.

Calls: `CALL-20260709-0103`, `CALL-20260716-0020`, `CALL-20260716-0107`, `CALL-20260725-0293`, `CALL-20260808-0159`, `CALL-20260810-0210`, `CALL-20260810-0296`, `CALL-20260814-0122`, `CALL-20260822-0212`, `CALL-20260824-0408`, `CALL-20260906-0399`, `CALL-20260907-0221`, `CALL-20260913-0250`, `CALL-20260916-0336`, `CALL-20260916-0338`, `CALL-20260918-0071`.

Full reads: `CALL-20260709-0103`, `CALL-20260822-0212`, `CALL-20260918-0071`.

### Tb9afdda4 — 13 calls; 3 full reads

Request: i got an invoice inv # for # and i m not sure what it s for. CSV outcome: `action`.

Calls: `CALL-20260710-0373`, `CALL-20260728-0193`, `CALL-20260805-0244`, `CALL-20260821-0199`, `CALL-20260825-0066`, `CALL-20260825-0145`, `CALL-20260825-0266`, `CALL-20260830-0165`, `CALL-20260905-0201`, `CALL-20260905-0363`, `CALL-20260907-0204`, `CALL-20260908-0257`, `CALL-20260915-0303`.

Full reads: `CALL-20260710-0373`, `CALL-20260825-0266`, `CALL-20260915-0303`.

### Tbaf67f84 — 12 calls; 3 full reads

Request: what does the comfort club membership actually include. CSV outcome: `answered`.

Calls: `CALL-20260707-0148`, `CALL-20260718-0045`, `CALL-20260718-0060`, `CALL-20260719-0413`, `CALL-20260808-0146`, `CALL-20260813-0156`, `CALL-20260816-0268`, `CALL-20260819-0163`, `CALL-20260820-0252`, `CALL-20260826-0073`, `CALL-20260828-0316`, `CALL-20260912-0394`.

Full reads: `CALL-20260707-0148`, `CALL-20260816-0268`, `CALL-20260912-0394`.

### Tbc5df324 — 12 calls; 3 full reads

Request: my system is # years old and i m thinking about replacing it what would that cost. CSV outcome: `booked`.

Calls: `CALL-20260709-0134`, `CALL-20260711-0030`, `CALL-20260721-0321`, `CALL-20260724-0113`, `CALL-20260724-0337`, `CALL-20260727-0076`, `CALL-20260803-0155`, `CALL-20260810-0237`, `CALL-20260818-0243`, `CALL-20260831-0297`, `CALL-20260908-0160`, `CALL-20260911-0256`.

Full reads: `CALL-20260709-0134`, `CALL-20260803-0155`, `CALL-20260911-0256`.

### Tc36da844 — 7 calls; 7 full reads

Request: my trane compressor died and the system is only three years old is that under warranty. CSV outcome: `answered`.

Calls: `CALL-20260709-0315`, `CALL-20260719-0153`, `CALL-20260720-0292`, `CALL-20260723-0276`, `CALL-20260730-0274`, `CALL-20260803-0004`, `CALL-20260811-0085`.

Full reads: `CALL-20260709-0315`, `CALL-20260719-0153`, `CALL-20260720-0292`, `CALL-20260723-0276`, `CALL-20260730-0274`, `CALL-20260803-0004`, `CALL-20260811-0085`.

### Tc749ab58 — 5 calls; 5 full reads

Request: is this meridian dental. CSV outcome: `redirect`.

Calls: `CALL-20260813-0031`, `CALL-20260820-0374`, `CALL-20260904-0186`, `CALL-20260906-0280`, `CALL-20260918-0417`.

Full reads: `CALL-20260813-0031`, `CALL-20260820-0374`, `CALL-20260904-0186`, `CALL-20260906-0280`, `CALL-20260918-0417`.

### Td12bdf25 — 3 calls; 3 full reads

Request: my thermostat is blank. CSV outcome: `waitlist`.

Calls: `CALL-20260723-0172`, `CALL-20260812-0302`, `CALL-20260913-0044`.

Full reads: `CALL-20260723-0172`, `CALL-20260812-0302`, `CALL-20260913-0044`.

### Td1e329a6 — 10 calls; 3 full reads

Request: my thermostat is blank. CSV outcome: `booked`.

Calls: `CALL-20260707-0170`, `CALL-20260711-0380`, `CALL-20260716-0240`, `CALL-20260728-0094`, `CALL-20260807-0011`, `CALL-20260807-0401`, `CALL-20260813-0018`, `CALL-20260817-0354`, `CALL-20260819-0147`, `CALL-20260907-0393`.

Full reads: `CALL-20260707-0170`, `CALL-20260807-0401`, `CALL-20260907-0393`.

### Tdbe75aee — 15 calls; 3 full reads

Request: what s my current balance. CSV outcome: `answered`.

Calls: `CALL-20260708-0255`, `CALL-20260710-0121`, `CALL-20260715-0021`, `CALL-20260718-0419`, `CALL-20260727-0080`, `CALL-20260731-0301`, `CALL-20260803-0190`, `CALL-20260816-0313`, `CALL-20260819-0131`, `CALL-20260821-0310`, `CALL-20260901-0410`, `CALL-20260908-0164`, `CALL-20260910-0203`, `CALL-20260912-0083`, `CALL-20260914-0074`.

Full reads: `CALL-20260708-0255`, `CALL-20260816-0313`, `CALL-20260914-0074`.

### Te8bcef76 — 15 calls; 3 full reads

Request: i have a tech coming tomorrow but something came up can i move it. CSV outcome: `moved`.

Calls: `CALL-20260711-0063`, `CALL-20260721-0258`, `CALL-20260725-0112`, `CALL-20260801-0208`, `CALL-20260825-0192`, `CALL-20260826-0309`, `CALL-20260827-0091`, `CALL-20260827-0149`, `CALL-20260829-0049`, `CALL-20260902-0001`, `CALL-20260902-0229`, `CALL-20260903-0026`, `CALL-20260911-0171`, `CALL-20260917-0023`, `CALL-20260917-0395`.

Full reads: `CALL-20260711-0063`, `CALL-20260827-0149`, `CALL-20260917-0395`.

### Tea4efe8a — 3 calls; 3 full reads

Request: i smell gas near my furnace. CSV outcome: `safety`.

Calls: `CALL-20260712-0046`, `CALL-20260728-0264`, `CALL-20260822-0185`.

Full reads: `CALL-20260712-0046`, `CALL-20260728-0264`, `CALL-20260822-0185`.

### Teba1e31f — 5 calls; 5 full reads

Request: i manage a # unit strip center and i need a quote on replacing four rooftop units. CSV outcome: `callback`.

Calls: `CALL-20260728-0089`, `CALL-20260730-0396`, `CALL-20260819-0228`, `CALL-20260916-0403`, `CALL-20260917-0187`.

Full reads: `CALL-20260728-0089`, `CALL-20260730-0396`, `CALL-20260819-0228`, `CALL-20260916-0403`, `CALL-20260917-0187`.

### Teff9802d — 5 calls; 5 full reads

Request: i smell something burning from the vents. CSV outcome: `waitlist`.

Calls: `CALL-20260706-0182`, `CALL-20260806-0377`, `CALL-20260906-0032`, `CALL-20260908-0029`, `CALL-20260916-0311`.

Full reads: `CALL-20260706-0182`, `CALL-20260806-0377`, `CALL-20260906-0032`, `CALL-20260908-0029`, `CALL-20260916-0311`.

### Tf0d9c2f5 — 4 calls; 4 full reads

Request: i need my annual tune up. CSV outcome: `waitlist`.

Calls: `CALL-20260721-0110`, `CALL-20260818-0184`, `CALL-20260828-0211`, `CALL-20260911-0179`.

Full reads: `CALL-20260721-0110`, `CALL-20260818-0184`, `CALL-20260828-0211`, `CALL-20260911-0179`.

### Tf7d382d9 — 10 calls; 3 full reads

Request: did you guys register my new unit with the manufacturer i never got anything. CSV outcome: `answered`.

Calls: `CALL-20260707-0053`, `CALL-20260709-0010`, `CALL-20260712-0195`, `CALL-20260722-0249`, `CALL-20260728-0194`, `CALL-20260730-0323`, `CALL-20260805-0173`, `CALL-20260815-0406`, `CALL-20260822-0343`, `CALL-20260904-0069`.

Full reads: `CALL-20260707-0053`, `CALL-20260730-0323`, `CALL-20260904-0069`.

### Tf995585c — 11 calls; 3 full reads

Request: there s water pooling around the indoor unit. CSV outcome: `booked`.

Calls: `CALL-20260715-0061`, `CALL-20260725-0378`, `CALL-20260730-0372`, `CALL-20260731-0047`, `CALL-20260808-0322`, `CALL-20260809-0117`, `CALL-20260810-0414`, `CALL-20260814-0420`, `CALL-20260823-0022`, `CALL-20260825-0005`, `CALL-20260913-0196`.

Full reads: `CALL-20260715-0061`, `CALL-20260809-0117`, `CALL-20260913-0196`.

### Tfc7d7be8 — 12 calls; 3 full reads

Request: i need my annual tune up. CSV outcome: `booked`.

Calls: `CALL-20260711-0109`, `CALL-20260720-0371`, `CALL-20260801-0176`, `CALL-20260807-0312`, `CALL-20260816-0368`, `CALL-20260826-0277`, `CALL-20260907-0140`, `CALL-20260910-0166`, `CALL-20260910-0236`, `CALL-20260912-0361`, `CALL-20260914-0070`, `CALL-20260918-0384`.

Full reads: `CALL-20260711-0109`, `CALL-20260907-0140`, `CALL-20260918-0384`.

## 7. Confidence

**Medium.** Every template received the required full-transcript comparison, all small groups were read completely, all seven brand-merge members were read completely, and all 420 files received a supplementary dialogue-line screen. The observed business handling sequences support 52 without relying on the earlier numerical estimate or trusting the one-word outcomes.

The limits are the 175-call full-dialogue sample and the semantic boundary described at the start. In particular, the result groups alternative identity checks as the same account-identification step and retains the more specific running-but-warm AC symptom as a distinct caller scenario. Those are reasoned granularity choices, not differences erased by numeric normalization. The algorithm's literal request matching and coarse outcomes could fail on future calls with names inside requests or different later actions; this review establishes no such failure in the supplied evidence.

**Final counts: 0 templates to split; 0 current templates to merge; 52 templates retained.**
