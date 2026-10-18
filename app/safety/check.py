"""The safety check run on every caller message before anything else; a match overrides the router (R34)."""

from dataclasses import dataclass

from app.safety import patterns as p

SERIOUSNESS = ["danger", "burning", "urgent", "clear"]


@dataclass(frozen=True)
class SafetyResult:
    kind: str  # danger, burning, urgent or clear


def _burning_in(texts: list[str]) -> bool:
    return any(p.found(p.BURNING, p.normalise(t)) for t in texts)


def check(text: str, history: list[str], burning_before: bool = False) -> SafetyResult:
    said = p.normalise(text)
    kinds = set()
    if p.found(p.DANGER, said):
        kinds.add("danger")
    burning_now = p.found(p.BURNING, said)
    # An electrical burning smell with a tripped breaker is immediate danger, even across messages.
    if p.found(p.BREAKER, said) and (burning_now or burning_before or _burning_in(history)):
        kinds.add("danger")
    if burning_now:
        kinds.add("burning")
    if (p.found(p.LEAK, said) and p.found(p.LEAK_SERIOUS, said)) or (p.found(p.NO_HEAT, said) and p.found(p.COLD, said)) \
            or (p.found(p.NO_COOLING, said) and p.found(p.HOT, said)):
        kinds.add("urgent")
    # When more than one class matches, the more serious one wins.
    return SafetyResult(next((k for k in SERIOUSNESS if k in kinds), "clear"))


def breaker_advice_allowed(history: list[str]) -> bool:
    """Never advise resetting a breaker in a conversation that mentions a burning smell (R36, D19)."""
    return not _burning_in(history)
