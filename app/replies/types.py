"""The structured reply types the writer produces (R42), each with what the reply must do."""

REPLY_TYPES = {
    "price answer": "Quote the published price or range and name its source document; end by saying the technician "
                    "confirms the final price on site.",
    "policy answer": "Answer from the facts and name the source document.",
    "account answer": "Read the account facts exactly as given; never call a charge right or wrong.",
    "booking offer": "Offer the slots given, each with its date, window and service; ask which one suits.",
    "read-back": "Read back the date, window and service type and ask for a clear yes; mention a fee only if the facts "
                 "give one.",
    "confirmation": "Confirm what was done, with the technician's name and the window; mention a fee only if the facts "
                    "give one.",
    "decline": "Say plainly that no slot is available and that a team member will follow up.",
    "handoff": "Say a team member will follow up, give the ticket number if there is one, and what happens next.",
}
