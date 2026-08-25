"""Wording for verdicts and findings."""

from __future__ import annotations

from dataclasses import dataclass

from .classify import lacks_stability
from .status import FAIL, INCONCLUSIVE, PASS, PRIORITY, WARN, Status


def key_verdict(report, policy):
    if report.status == PASS:
        return "supported by the data"
    if report.status == WARN:
        return "weak - inspect manually"
    if lacks_stability(report, policy):
        return (
            "NOT SUPPORTED - nothing stays constant within an entity "
            "(invariance matches shuffled labels)"
        )
    return "NOT SUPPORTED - within-entity quantities are unsafe"


def leakage_verdict(status):
    if status == FAIL:
        return "Target is nearly deterministic under linear reconstruction."
    if status == WARN:
        return "Target is strongly linearly reconstructible from the supplied features."
    return "Linear reconstruction remained below the warning threshold."


def baseline_verdict(r2, policy):
    if r2 >= policy.strong_persistence_r2:
        share = policy.strong_persistence_r2
        return f"Carry-forward explains at least {share:.0%} of target variance."
    if r2 >= policy.moderate_persistence_r2:
        share = policy.moderate_persistence_r2
        return f"Carry-forward explains at least {share:.0%} of target variance."
    share = policy.moderate_persistence_r2
    return f"Carry-forward explains less than {share:.0%} of target variance."


@dataclass(frozen=True)
class Finding:
    """One audit finding."""

    code: str
    status: Status
    headline: str
    detail: str


def _key_finding(key, discovery_blocked):
    if key is None:
        if discovery_blocked:
            return Finding(
                code="discovery_inconclusive",
                status=INCONCLUSIVE,
                headline="Key discovery could not run",
                detail=discovery_blocked,
            )
        return Finding(
            code="key_missing",
            status=FAIL,
            headline="No usable entity key",
            detail="Nothing in this table behaves like an entity tracked over time.",
        )

    name = " + ".join(key.key)
    if key.status == INCONCLUSIVE:
        return Finding(
            code="key_inconclusive",
            status=INCONCLUSIVE,
            headline=f"Entity key is inconclusive ({name})",
            detail=key.verdict,
        )
    if key.status == FAIL:
        return Finding(
            code="key_unsupported",
            status=FAIL,
            headline=f"Entity key is not supported by the data ({name})",
            detail="Lags, differences, trajectories and grouped splits built on "
            "this key are unreliable. " + key.verdict,
        )
    if key.status == WARN:
        return Finding(
            code="key_weak",
            status=WARN,
            headline=f"Entity key is only weakly supported ({name})",
            detail=f"Explains {key.evidence_frac:.0%} of columns. Inspect the "
            "listed invariants and counters before relying on it. "
            "Within-entity diagnostics are not run under a weak key "
            "unless allow_weak_key is set.",
        )
    if key.status == PASS:
        return Finding(
            code="key_supported",
            status=PASS,
            headline=f"Entity key supported ({name})",
            detail=f"Explains {key.evidence_frac:.0%} of columns across "
            f"{key.n_entities:,} entities.",
        )
    raise ValueError(f"unknown key status {key.status!r}")


def _leakage_finding(leakage, target):
    if leakage.status == FAIL:
        return Finding(
            code="leakage",
            status=FAIL,
            headline=f"Target '{target}' is reconstructible",
            detail=leakage.verdict,
        )
    if leakage.status == WARN:
        return Finding(
            code="leakage_suspect",
            status=WARN,
            headline=f"Target '{target}' is largely reconstructible",
            detail=leakage.verdict,
        )
    if leakage.status == INCONCLUSIVE:
        return Finding(
            code="leakage_inconclusive",
            status=INCONCLUSIVE,
            headline=f"Leakage test for '{target}' could not run",
            detail=leakage.verdict,
        )
    if leakage.status == PASS:
        return Finding(
            code="leakage_clean",
            status=PASS,
            headline=f"Target '{target}' is not linearly reconstructible",
            detail=leakage.verdict,
        )
    raise ValueError(f"unknown leakage status {leakage.status!r}")


def _baseline_finding(baseline, target):
    if baseline.status == INCONCLUSIVE:
        return Finding(
            code="baseline_inconclusive",
            status=INCONCLUSIVE,
            headline=f"Persistence baseline for '{target}' could not be scored",
            detail=baseline.verdict,
        )
    if baseline.status in (WARN, PASS):
        return Finding(
            code="baseline",
            status=baseline.status,
            headline=f"Carry-forward alone scores R2 {baseline.persistence_r2:.3f} on '{target}'",
            detail=baseline.verdict,
        )
    raise ValueError(f"unknown baseline status {baseline.status!r}")


def _counter_finding(counters):
    if counters.status == INCONCLUSIVE:
        return Finding(
            code="counters_inconclusive",
            status=INCONCLUSIVE,
            headline="Counter detection could not run",
            detail="No feature had enough within-entity history to test for cumulative behaviour.",
        )
    if counters.counters:
        return Finding(
            code="counters",
            status=WARN,
            headline=f"{len(counters.counters)} cumulative counter(s) among the features",
            detail="These columns rarely decrease within an entity, so targets "
            "derived from them can become strongly autocorrelated. Use "
            "per-period changes when the question concerns new activity.",
        )
    return None


def build_findings(result):
    out = [_key_finding(result.chosen, result.discovery_blocked)]
    if result.leakage is not None:
        out.append(_leakage_finding(result.leakage, result.target))
    if result.baseline is not None:
        out.append(_baseline_finding(result.baseline, result.target))
    if result.counters is not None:
        counter_finding = _counter_finding(result.counters)
        if counter_finding is not None:
            out.append(counter_finding)
    return tuple(sorted(out, key=lambda f: PRIORITY[f.status]))
