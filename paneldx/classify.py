"""Map measurements to statuses."""

import numpy as np

from .status import (
    FAIL,
    INCONCLUSIVE,
    INSUFFICIENT_EVIDENCE,
    PASS,
    SUPPORTED,
    WARN,
    WEAK_SUPPORT,
)


def lacks_stability(report, policy):
    gap = report.null_invariance_violation - report.invariance_violation
    return not report.invariant_cols and (not np.isfinite(gap) or gap < policy.minimum_null_gap)


def key_status(report, policy):
    """Status and reason for a key that reached the measurement stage.

    Nothing here returns `fail`: contradictions are caught earlier by the
    structural checks. What is measured here is positive evidence, and too
    little of it is an absence of evidence rather than evidence of absence. A
    key indistinguishable from shuffled labels is the extreme case — the
    comparison carried no information, so its evidence fraction cannot be
    trusted either way.
    """
    if lacks_stability(report, policy):
        return INCONCLUSIVE, INSUFFICIENT_EVIDENCE
    if report.evidence_frac >= policy.supported_evidence_fraction:
        return PASS, SUPPORTED
    if report.evidence_frac >= policy.weak_evidence_fraction:
        return WARN, WEAK_SUPPORT
    return INCONCLUSIVE, INSUFFICIENT_EVIDENCE


def counter_status(report):
    if report.counters:
        return WARN
    if report.n_columns_tested:
        return PASS
    return INCONCLUSIVE


def leakage_status(r2, policy):
    if r2 >= policy.deterministic_r2:
        return FAIL
    if r2 >= policy.reconstructible_r2:
        return WARN
    return PASS


def baseline_status(r2, policy):
    if r2 >= policy.moderate_persistence_r2:
        return WARN
    return PASS
