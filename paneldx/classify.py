"""Map measurements to statuses."""

import numpy as np

from .status import FAIL, INCONCLUSIVE, PASS, WARN


def lacks_stability(report, policy):
    gap = report.null_invariance_violation - report.invariance_violation
    return not report.invariant_cols and (not np.isfinite(gap) or gap < policy.minimum_null_gap)


def key_status(report, policy):
    if lacks_stability(report, policy):
        return FAIL
    if report.evidence_frac >= policy.supported_evidence_fraction:
        return PASS
    if report.evidence_frac >= policy.weak_evidence_fraction:
        return WARN
    return FAIL


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
