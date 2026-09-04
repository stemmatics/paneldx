from collections.abc import Iterable
from typing import Literal

Status = Literal["pass", "warn", "fail", "inconclusive"]

PASS: Status = "pass"
WARN: Status = "warn"
FAIL: Status = "fail"
INCONCLUSIVE: Status = "inconclusive"

PRIORITY = {
    FAIL: 0,
    INCONCLUSIVE: 1,
    WARN: 2,
    PASS: 3,
}

# Why a key received its status. Fixed strings rather than prose: a caller
# should be able to branch on the reason without matching on wording, and a
# changed verdict should be traceable to a named cause.
Reason = Literal[
    "supported",
    "weak_support",
    "insufficient_evidence",
    "duplicate_entity_period",
    "declared_invariant_broken",
    "declared_monotone_broken",
]

SUPPORTED: Reason = "supported"
WEAK_SUPPORT: Reason = "weak_support"
INSUFFICIENT_EVIDENCE: Reason = "insufficient_evidence"
DUPLICATE_ENTITY_PERIOD: Reason = "duplicate_entity_period"
DECLARED_INVARIANT_BROKEN: Reason = "declared_invariant_broken"
DECLARED_MONOTONE_BROKEN: Reason = "declared_monotone_broken"

REASONS: tuple[Reason, ...] = (
    SUPPORTED,
    WEAK_SUPPORT,
    INSUFFICIENT_EVIDENCE,
    DUPLICATE_ENTITY_PERIOD,
    DECLARED_INVARIANT_BROKEN,
    DECLARED_MONOTONE_BROKEN,
)

# `fail` means a contradiction was found, never that evidence was missing.
CONTRADICTION_REASONS = frozenset(
    {DUPLICATE_ENTITY_PERIOD, DECLARED_INVARIANT_BROKEN, DECLARED_MONOTONE_BROKEN}
)


def worst(statuses: Iterable[Status]) -> Status:
    return min(statuses, key=PRIORITY.__getitem__, default=INCONCLUSIVE)
