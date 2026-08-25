"""Entity-key validation and discovery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd

from .classify import key_status
from .describe import key_verdict
from .policy import DEFAULT_KEY_POLICY, KeyValidationPolicy
from .status import FAIL, INCONCLUSIVE, PASS, PRIORITY, Status


@dataclass
class KeyReport:
    """Evidence for one candidate key."""

    key: tuple[str, ...]
    n_entities: int
    n_rows_covered: int
    coverage: float
    duplicate_rate: float
    invariant_cols: list[str] = field(default_factory=list)
    monotone_cols: list[str] = field(default_factory=list)
    invariance_violation: float = np.nan
    monotonicity_violation: float = np.nan
    null_invariance_violation: float = np.nan
    null_monotonicity_violation: float = np.nan
    n_usable_cols: int = 0
    evidence: float = 0.0
    evidence_frac: float = 0.0
    status: Status = INCONCLUSIVE
    verdict: str = "unknown"

    def __str__(self) -> str:  # pragma: no cover
        return "\n".join(
            [
                f"key: {' + '.join(self.key)}",
                f"  entities            {self.n_entities:,}  "
                f"(covering {self.coverage:.1%} of rows)",
                f"  duplicate cells     {self.duplicate_rate:.2%} of (entity, period) cells",
                f"  invariant columns   {len(self.invariant_cols)}"
                + (f"  {self.invariant_cols[:4]}" if self.invariant_cols else ""),
                f"  monotone columns    {len(self.monotone_cols)}"
                + (f"  {self.monotone_cols[:4]}" if self.monotone_cols else ""),
                f"  invariance breach   {self.invariance_violation:.3f}"
                f"   (shuffled: {self.null_invariance_violation:.3f})",
                f"  monotonicity breach {self.monotonicity_violation:.3f}"
                f"   (shuffled: {self.null_monotonicity_violation:.3f})",
                f"  columns explained   {self.evidence:.0f} of {self.n_usable_cols}"
                f"  ({self.evidence_frac:.0%})",
                f"  VERDICT             {self.verdict}",
            ]
        )


def entity_key(df: pd.DataFrame, key: Sequence[str]) -> pd.Series:
    """Return integer codes for a compound entity key."""
    if not len(key):
        raise ValueError("entity key must name at least one column")
    return df.groupby(list(key), sort=False, dropna=False).ngroup()


def _usable_columns(df, key, time_col):
    skip = set(key) | {time_col}
    return [c for c in df.columns if c not in skip and df[c].nunique(dropna=False) > 1]


def _invariance_rates(df, entity, cols):
    grouped = df.groupby(entity, sort=False)
    return {c: float((grouped[c].nunique(dropna=False) > 1).mean()) for c in cols}


def _monotonicity_rates(df, entity, time, cols, min_steps):
    order = np.lexsort((time.to_numpy(), entity.to_numpy()))
    ent, tim = entity.to_numpy()[order], time.to_numpy()[order]
    # Repeated observations of one period are not steps in time.
    same_entity = (ent[1:] == ent[:-1]) & (tim[1:] != tim[:-1])
    if not same_entity.any():
        return {}

    rates = {}
    for c in cols:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        v = df[c].values[order].astype("float64")
        if np.nanmin(v) < 0:
            continue
        step = np.diff(v)
        valid = same_entity & np.isfinite(step)
        if valid.sum() < min_steps:
            continue
        if (step[valid] != 0).mean() < 0.5:
            continue
        rates[c] = float((step[valid] < 0).mean())
    return rates


def _shuffled_entity(entity, time, rng):
    # Shuffling within each period keeps the panel's shape and breaks row correspondence.
    out = entity.copy()
    for _, idx in time.groupby(time, sort=False).groups.items():
        vals = entity.loc[idx].to_numpy().copy()
        rng.shuffle(vals)
        out.loc[idx] = vals
    return out


def _mean_rate(dicts, col):
    vals = [d[col] for d in dicts if col in d]
    return float(np.mean(vals)) if vals else np.nan


def _measure(report, work, entity, time, cols, policy, n_shuffles, random_state):
    inv = _invariance_rates(work, entity, cols)
    mono = _monotonicity_rates(work, entity, time, cols, policy.minimum_steps)

    rng = np.random.default_rng(random_state)
    null_inv, null_mono = [], []
    for _ in range(n_shuffles):
        shuffled = _shuffled_entity(entity, time, rng)
        null_inv.append(_invariance_rates(work, shuffled, cols))
        null_mono.append(_monotonicity_rates(work, shuffled, time, cols, policy.minimum_steps))

    inv_tol, mono_tol = policy.invariant_violation_rate, policy.monotone_violation_rate
    report.invariant_cols = [
        c for c, rate in inv.items() if rate <= inv_tol and _mean_rate(null_inv, c) > inv_tol * 2
    ]
    report.monotone_cols = [
        c
        for c, rate in mono.items()
        if rate <= mono_tol and _mean_rate(null_mono, c) > mono_tol * 2
    ]

    null_inv_rates = [v for d in null_inv for v in d.values()]
    null_mono_rates = [v for d in null_mono for v in d.values()]
    report.invariance_violation = float(np.mean(list(inv.values()))) if inv else np.nan
    report.monotonicity_violation = float(np.mean(list(mono.values()))) if mono else np.nan
    report.null_invariance_violation = float(np.mean(null_inv_rates)) if null_inv_rates else np.nan
    report.null_monotonicity_violation = (
        float(np.mean(null_mono_rates)) if null_mono_rates else np.nan
    )

    report.n_usable_cols = len(cols)
    explained = set(report.invariant_cols) | set(report.monotone_cols)
    report.evidence = float(len(explained))
    report.evidence_frac = report.evidence / len(cols)


def validate_key(
    df: pd.DataFrame,
    key: str | Sequence[str],
    time_col: str,
    *,
    policy: KeyValidationPolicy = DEFAULT_KEY_POLICY,
    n_shuffles: int = 3,
    random_state: int = 0,
) -> KeyReport:
    """Evaluate whether a candidate key supports longitudinal linkage."""
    key = (key,) if isinstance(key, str) else tuple(key)
    missing = [c for c in (*key, time_col) if c not in df.columns]
    if missing:
        raise KeyError(f"columns not in frame: {missing}")
    if n_shuffles < 1:
        raise ValueError("n_shuffles must be at least 1")

    # Rows without an entity or period cannot be placed; a fresh index keeps
    # label selection exact under a non-unique input index.
    work = df.dropna(subset=[*key, time_col]).reset_index(drop=True)
    entity = entity_key(work, key)
    time = work[time_col]
    n_periods = int(time.nunique())

    per_period = work.groupby([entity, time], sort=False).size()
    duplicate_rate = float((per_period > 1).mean()) if len(per_period) else 1.0

    counts = entity.value_counts()
    mask = entity.isin(counts[counts >= policy.minimum_periods_per_entity].index)
    work, entity, time = work[mask], entity[mask], time[mask]

    report = KeyReport(
        key=key,
        n_entities=int(entity.nunique()),
        n_rows_covered=len(work),
        coverage=float(len(work) / max(len(df), 1)),
        duplicate_rate=duplicate_rate,
    )
    if not len(per_period):
        report.verdict = "no rows with a complete key"
        return report
    if duplicate_rate > policy.duplicate_cell_rate:
        report.status = FAIL
        report.verdict = f"invalid - key repeats within a period ({duplicate_rate:.1%})"
        return report
    if n_periods < 2:
        report.verdict = (
            f"{n_periods} period(s) of {time_col!r}; entities can only be tracked across at least 2"
        )
        return report
    if report.n_entities < policy.minimum_entities:
        report.verdict = (
            f"too few entities to judge: {report.n_entities} observed in at "
            f"least {policy.minimum_periods_per_entity} periods, "
            f"{policy.minimum_entities} needed"
        )
        return report
    cols = _usable_columns(work, key, time_col)
    if not cols:
        report.verdict = (
            "no evidence-bearing columns: everything outside the key and time column is constant"
        )
        return report

    _measure(report, work, entity, time, cols, policy, n_shuffles, random_state)
    report.status = key_status(report, policy)
    report.verdict = key_verdict(report, policy)
    return report


def _is_redundant_superset(combo, scored, n_entities):
    return any(
        set(r.key) < set(combo) and r.status == PASS and r.n_entities >= n_entities for r in scored
    )


def discover_keys(
    df: pd.DataFrame,
    time_col: str,
    *,
    max_columns: int = 2,
    top_k: int = 5,
    candidate_columns: Sequence[str] | None = None,
    policy: KeyValidationPolicy = DEFAULT_KEY_POLICY,
    n_shuffles: int = 2,
    random_state: int = 0,
    rejections: list[tuple[tuple[str, ...], str]] | None = None,
) -> list[KeyReport]:
    """Search column combinations for a plausible entity key."""
    if max_columns < 1:
        raise ValueError("max_columns must be at least 1")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    n_periods = df[time_col].nunique()
    if n_periods < 2:
        raise ValueError(f"{time_col!r} has {n_periods} period(s); need at least 2")

    if candidate_columns is not None:
        missing = [c for c in candidate_columns if c not in df.columns]
        if missing:
            raise KeyError(f"candidate columns not in frame: {missing}")
        pool = [c for c in candidate_columns if c != time_col]
    else:
        pool = [c for c in df.columns if c != time_col]
    pool = [c for c in pool if df[c].nunique(dropna=False) < len(df)]

    min_rows = policy.minimum_entities * policy.minimum_periods_per_entity

    def qualifying_entities(combo):
        sub = df.dropna(subset=[*combo, time_col]).reset_index(drop=True)
        if len(sub) < min_rows:
            return None
        ent = entity_key(sub, combo)
        per_period = sub.groupby([ent, sub[time_col]], sort=False).size()
        if not len(per_period) or float((per_period > 1).mean()) > policy.duplicate_cell_rate:
            return None
        counts = ent.value_counts()
        n = int((counts >= policy.minimum_periods_per_entity).sum())
        return n if n >= policy.minimum_entities else None

    reports: list[KeyReport] = []
    for size in range(1, max_columns + 1):
        for combo in combinations(pool, size):
            n_entities = qualifying_entities(combo)
            if n_entities is None:
                continue
            if _is_redundant_superset(combo, reports, n_entities):
                continue
            try:
                rep = validate_key(
                    df,
                    combo,
                    time_col,
                    policy=policy,
                    n_shuffles=n_shuffles,
                    random_state=random_state,
                )
            except (KeyError, TypeError, ValueError) as exc:
                if rejections is not None:
                    rejections.append((combo, f"{type(exc).__name__}: {exc}"))
                continue
            reports.append(rep)

    reports.sort(
        key=lambda r: (
            PRIORITY[r.status],
            -round(r.evidence_frac * np.sqrt(r.coverage), 6),
            len(r.key),
            -r.n_entities,
        )
    )
    return reports[:top_k]
