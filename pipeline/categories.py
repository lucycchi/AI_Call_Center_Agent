"""The frozen call-reason list (R2), proposed from the data review and fixed before labeling."""

CATEGORIES: list[tuple[str, str]] = [
    ("new booking", "hvac repair"),
    ("new booking", "plumbing"),
    ("new booking", "tune-up"),
    ("new booking", "burning smell"),
    ("billing", "current balance"),
    ("billing", "pay an invoice"),
    ("billing", "what an invoice is for"),
    ("billing", "charged twice"),
    ("billing", "quote dispute"),
    ("billing", "refund"),
    ("membership", "what it includes or price"),
    ("membership", "renewal date"),
    ("membership", "autopay"),
    ("membership", "cancel"),
    ("membership", "upgrade"),
    ("membership", "member discount on a new system"),
    ("warranty", "claim"),
    ("warranty", "registration"),
    ("warranty", "transfer"),
    ("warranty", "repeat repair"),
    ("existing appointment", "reschedule"),
    ("existing appointment", "cancel"),
    ("existing appointment", "confirm"),
    ("existing appointment", "technician late"),
    ("complaint or manager", "complaint or manager"),
    ("replacement estimate", "replacement estimate"),
    ("safety emergency", "gas, carbon monoxide or sparks"),
    ("hiring", "hiring"),
    ("commercial", "commercial"),
    ("wrong number", "wrong number"),
]

REASONS: list[str] = list(dict.fromkeys(reason for reason, _ in CATEGORIES))


def category_text() -> str:
    return "\n".join(f"- {reason}: {sub}" for reason, sub in CATEGORIES)


def check(reason: str, sub_reason: str, where: str) -> tuple[str, str]:
    if (reason, sub_reason) not in CATEGORIES:
        raise ValueError(f"{where}: label ({reason!r}, {sub_reason!r}) is not in the frozen category list")
    return reason, sub_reason
