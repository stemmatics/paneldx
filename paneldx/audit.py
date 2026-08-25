"""Run every check in one pass and collect the findings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from .describe import Finding, build_findings
from .keys import KeyReport, discover_keys, validate_key
from .policy import DEFAULT_KEY_POLICY, DEFAULT_TRAP_POLICY, KeyValidationPolicy, TrapPolicy
from .status import PASS, WARN, Status, worst
from .traps import (
    BaselineReport,
    CounterReport,
    LeakageReport,
    detect_counters,
    persistence_baseline,
    target_leakage,
)


@dataclass
class AuditResult:
    """Result of a full audit."""

    n_rows: int
    n_columns: int
    time_col: str
    n_periods: int
    key_was_supplied: bool
    key_reports: list[KeyReport] = field(default_factory=list)
    rejected_candidates: list[tuple[tuple[str, ...], str]] = field(default_factory=list)
    counters: CounterReport | None = None
    leakage: LeakageReport | None = None
    baseline: BaselineReport | None = None
    target: str | None = None
    source: str | None = None
    discovery_blocked: str | None = None
    findings: tuple[Finding, ...] = ()

    @property
    def chosen(self) -> KeyReport | None:
        return self.key_reports[0] if self.key_reports else None

    @property
    def worst(self) -> Status:
        return worst(f.status for f in self.findings)


def _supports_within_entity_checks(key, allow_weak):
    # Longitudinal checks verify only with a functioning key.
    if key is None:
        return False
    return key.status == PASS or (allow_weak and key.status == WARN)


def audit(
    df: pd.DataFrame,
    time_col: str,
    *,
    key: str | Sequence[str] | None = None,
    target: str | None = None,
    features: Sequence[str] | None = None,
    max_columns: int = 2,
    top_k: int = 3,
    period_step: object = None,
    allow_weak_key: bool = False,
    key_policy: KeyValidationPolicy = DEFAULT_KEY_POLICY,
    trap_policy: TrapPolicy = DEFAULT_TRAP_POLICY,
    source: str | None = None,
) -> AuditResult:
    """Run key, counter, leakage and persistence checks.

    When omitted, the entity key is discovered from the data. Use `features`
    to restrict leakage screening and `period_step` to define temporal adjacency.
    """
    if time_col not in df.columns:
        raise KeyError(f"time column {time_col!r} not in frame")

    result = AuditResult(
        n_rows=len(df),
        n_columns=len(df.columns),
        time_col=time_col,
        n_periods=int(df[time_col].nunique()),
        key_was_supplied=key is not None,
        target=target,
        source=source,
    )

    min_rows = key_policy.minimum_entities * key_policy.minimum_periods_per_entity
    if key is not None:
        result.key_reports = [validate_key(df, key, time_col, policy=key_policy)]
    elif result.n_periods < 2:
        result.discovery_blocked = (
            f"{result.n_periods} period(s) of {time_col!r}; at least 2 are "
            "needed before any key can be searched for"
        )
    elif len(df) < min_rows:
        result.discovery_blocked = (
            f"{len(df)} rows cannot contain {key_policy.minimum_entities} entities observed "
            f"in {key_policy.minimum_periods_per_entity} or more periods, the minimum the "
            "search needs to judge a candidate"
        )
    else:
        result.key_reports = discover_keys(
            df,
            time_col,
            max_columns=max_columns,
            top_k=top_k,
            policy=key_policy,
            rejections=result.rejected_candidates,
        )

    chosen = result.chosen
    usable_key = chosen if _supports_within_entity_checks(chosen, allow_weak_key) else None
    if usable_key is not None:
        result.counters = detect_counters(
            df,
            list(usable_key.key),
            time_col,
            exclude=[target] if target else None,
            policy=trap_policy,
        )

    if target is not None:
        if features is None:
            skip = set(chosen.key if chosen else ()) | {time_col, target}
            features = [
                c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])
            ]
        result.leakage = target_leakage(df, target, features, policy=trap_policy)
        if usable_key is not None:
            result.baseline = persistence_baseline(
                df,
                list(usable_key.key),
                time_col,
                target,
                period_step=period_step,
                policy=trap_policy,
            )

    result.findings = build_findings(result)
    return result
