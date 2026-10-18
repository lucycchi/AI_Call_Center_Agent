"""Scoring a test run (R14 to R17): call-weighted containment and the measures beside it.

A case's first run is its scored result; a case that failed and then passed its one retry is flaky, never passed."""

import random
from dataclasses import asdict, dataclass, field

# The route the router should give each labelled sub-reason; some reasonably go either way.
ROUTES = {
    "hvac repair": {"scheduling"}, "plumbing": {"scheduling"}, "tune-up": {"scheduling"}, "replacement estimate": {"scheduling", "knowledge"},
    "reschedule": {"scheduling"}, "confirm": {"scheduling"}, "cancel appointment": {"scheduling"},
    "current balance": {"account"}, "what an invoice is for": {"account"}, "pay an invoice": {"account"},
    "charged twice": {"knowledge", "account"}, "what it includes or price": {"knowledge"}, "renewal date": {"account"},
    "member discount on a new system": {"knowledge"}, "autopay": {"account"}, "cancel": {"account"}, "upgrade": {"account", "knowledge"},
    "claim": {"scheduling", "knowledge"}, "repeat repair": {"scheduling", "knowledge"}, "registration": {"knowledge", "account"},
    "transfer": {"knowledge"}, "quote dispute": {"handoff"}, "refund": {"handoff"}, "technician late": {"handoff"},
    "complaint or manager": {"handoff"}, "commercial": {"handoff"}, "hiring": {"redirect"}, "wrong number": {"redirect"},
}
SAFETY_FIRST = {"gas, carbon monoxide or sparks", "burning smell"}  # the safety check answers before any routing
REDIRECT_ONLY = {"hiring", "wrong number"}
BOOKING_REASONS = {"new booking", "existing appointment"}


def expected_route(case: dict) -> set[str] | None:
    """The acceptable routes for the case's first substantive message; None when routing is not used."""
    if case["sub_reason"] in SAFETY_FIRST:
        return None
    return ROUTES.get(case["sub_reason"])


@dataclass
class Summary:
    containment: float
    containment_without_redirects: float
    scope_ceiling: float
    adjusted_ceiling: float
    action_gap: float
    wrong_confident: float
    knowledge_accuracy: float | None
    routing_accuracy: float | None
    handoff_correct_safety_and_booking: float | None
    handoff_correct_other: float | None
    booking_correct: float | None
    lookup_correct: float | None
    clean_declines: int
    flaky: list[str]
    interval_low: float
    interval_high: float
    scenarios: int
    weighted_calls: int
    human_baseline: float | None = None
    human_baseline_excluding_actions: float | None = None
    stopped_at_budget: bool = False
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


def _share(items: list[tuple[float, bool]]) -> float | None:
    total = sum(w for w, _ in items)
    return sum(w for w, ok in items if ok) / total if total else None


def _contained(a) -> bool:
    return not a.handed_off and not a.clean_decline and a.all_correct is True


def _weighted_containment(rows: list[tuple[dict, object]]) -> float:
    total = sum(c["calls_weight"] for c, _ in rows)
    return sum(c["calls_weight"] for c, a in rows if _contained(a)) / total if total else 0.0


def score(attempts: list, cases: list[dict], seed: int = 20261016, resamples: int = 2000, human: dict | None = None,
          stopped_at_budget: bool = False) -> Summary:
    by_case = {c["case_id"]: c for c in cases}
    first = {a.case_id: a for a in attempts if a.attempt == 1}
    retry = {a.case_id: a for a in attempts if a.attempt == 2}
    rows = [(by_case[cid], a) for cid, a in first.items() if cid in by_case]
    weight = lambda c: c["calls_weight"]  # noqa: E731
    # A case passes when its behaviour was graded correct (for a handoff case, handing off correctly).
    flaky = sorted(cid for cid, a in first.items() if a.all_correct is False and retry.get(cid) and retry[cid].all_correct)
    others = [(c, a) for c, a in rows if c["sub_reason"] not in REDIRECT_ONLY]
    handled = lambda c: c["requests"][0]["expected_outcome"] in ("contained", "clean_decline")  # noqa: E731
    action = lambda c: any(r.get("handoff_reason") == "action gap" for r in c["requests"])  # noqa: E731
    routed = [(weight(c), a.first_route in expected_route(c)) for c, a in rows if expected_route(c) is not None]
    safety_booking = [(weight(c), a.handed_off and a.grades.get("handoff_reason_correct", True)) for c, a in rows
                      if c["expected_outcome"] == "handed_off" and (c["sub_reason"] in SAFETY_FIRST or c["reason"] in BOOKING_REASONS)]
    other_handoffs = [(weight(c), a.handed_off and a.grades.get("handoff_reason_correct", True)) for c, a in rows
                      if c["expected_outcome"] == "handed_off" and not (c["sub_reason"] in SAFETY_FIRST or c["reason"] in BOOKING_REASONS)]
    graded = lambda key: [(weight(c), a.grades[key]) for c, a in rows if key in a.grades]  # noqa: E731
    rng = random.Random(seed)
    samples = sorted(_weighted_containment([rng.choice(rows) for _ in rows]) for _ in range(resamples)) if rows else [0.0]
    total = sum(weight(c) for c, _ in rows) or 1
    return Summary(
        containment=_weighted_containment(rows),
        containment_without_redirects=_weighted_containment(others),
        scope_ceiling=sum(weight(c) for c, _ in rows if handled(c)) / total,
        adjusted_ceiling=sum(weight(c) for c, _ in rows if c["expected_outcome"] == "contained") / total,
        action_gap=sum(weight(c) for c, _ in rows if action(c)) / total,
        wrong_confident=sum(weight(c) for c, a in rows if not a.handed_off and not a.clean_decline and a.all_correct is False) / total,
        knowledge_accuracy=_share(graded("knowledge_correct")),
        routing_accuracy=_share(routed),
        handoff_correct_safety_and_booking=_share(safety_booking),
        handoff_correct_other=_share(other_handoffs),
        booking_correct=_share(graded("booking_correct")),
        lookup_correct=_share(graded("lookup_correct")),
        clean_declines=sum(1 for c, a in rows if a.clean_decline and c["expected_outcome"] == "clean_decline"),
        flaky=flaky,
        interval_low=samples[int(0.025 * (len(samples) - 1))], interval_high=samples[int(0.975 * (len(samples) - 1))],
        scenarios=len(rows), weighted_calls=sum(weight(c) for c, _ in rows),
        human_baseline=human.get("resolved") if human else None,
        human_baseline_excluding_actions=human.get("resolved_excluding_actions") if human else None,
        stopped_at_budget=stopped_at_budget)
