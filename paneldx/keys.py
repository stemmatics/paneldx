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
from .status import (
    DECLARED_INVARIANT_BROKEN,
    DECLARED_MONOTONE_BROKEN,
    DUPLICATE_ENTITY_PERIOD,
    FAIL,
    INCONCLUSIVE,
    INSUFFICIENT_EVIDENCE,
    PASS,
    PRIORITY,
    Reason,
    Status,
)


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
    n_transitions: int = 0
    declared_invariant_cols: list[str] = field(default_factory=list)
    declared_monotone_cols: list[str] = field(default_factory=list)
    declared_violations: dict[str, float] = field(default_factory=dict)
    status: Status = INCONCLUSIVE
    reason: Reason = INSUFFICIENT_EVIDENCE
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
                f"  reason              {self.reason}",
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
        v = df[c].to_numpy(dtype="float64", na_value=np.nan)[order]
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


def _declared_monotone_rates(df, entity, time, cols):
    """Decrease rate for columns the caller asserted only ever rise.

    Unlike discovery, nothing is filtered out here. The caller has stated the
    column is a counter, so a column that barely moves, or that dips below
    zero, is still held to that claim.
    """
    order = np.lexsort((time.to_numpy(), entity.to_numpy()))
    ent, tim = entity.to_numpy()[order], time.to_numpy()[order]
    adjacent = (ent[1:] == ent[:-1]) & (tim[1:] != tim[:-1])

    rates = {}
    for c in cols:
        v = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64")[order]
        step = np.diff(v)
        valid = adjacent & np.isfinite(step)
        rates[c] = float((step[valid] < 0).mean()) if valid.any() else 0.0
    return rates


def _count_transitions(entity, time) -> int:
    """Adjacent within-entity observations in different periods."""
    if not len(entity):
        return 0
    order = np.lexsort((time.to_numpy(), entity.to_numpy()))
    ent, tim = entity.to_numpy()[order], time.to_numpy()[order]
    if len(ent) < 2:
        return 0
    return int(((ent[1:] == ent[:-1]) & (tim[1:] != tim[:-1])).sum())


def _declared(name, columns, key, time_col, df) -> list[str]:
    if columns is None:
        return []
    named: list[str] = [columns] if isinstance(columns, str) else [str(c) for c in columns]
    missing = [c for c in named if c not in df.columns]
    if missing:
        raise KeyError(f"{name} columns not in frame: {missing}")
    overlap = [c for c in named if c in {*key, time_col}]
    if overlap:
        raise ValueError(f"{name} columns cannot be part of the key or the time column: {overlap}")
    return named


def _declarations(df, key, time_col, invariant_cols, monotone_cols):
    """Normalise and check the caller's declared columns."""
    invariant = _declared("invariant", invariant_cols, key, time_col, df)
    monotone = _declared("monotone", monotone_cols, key, time_col, df)
    non_numeric = [c for c in monotone if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        raise ValueError(f"monotone columns must be numeric: {non_numeric}")
    return invariant, monotone


def _prepare(df, key, time_col, policy):
    """Drop unplaceable rows, then entities seen in too few periods.

    Returns the working frame, its entity codes and periods, the period count,
    the duplicate entity-period rate and the number of cells. Rows without an
    entity or period cannot be placed at all; a fresh index keeps label
    selection exact under a non-unique input index.
    """
    work = df.dropna(subset=[*key, time_col]).reset_index(drop=True)
    entity = entity_key(work, key)
    time = work[time_col]
    n_periods = int(time.nunique())

    per_period = work.groupby([entity, time], sort=False).size()
    duplicate_rate = float((per_period > 1).mean()) if len(per_period) else 1.0

    counts = entity.value_counts()
    mask = entity.isin(counts[counts >= policy.minimum_periods_per_entity].index)
    return work[mask], entity[mask], time[mask], n_periods, duplicate_rate, len(per_period)


def _insufficient(report, policy, time_col, n_periods) -> str | None:
    """Why there is not enough panel to judge, or None if there is."""
    if n_periods < 2:
        return (
            f"{n_periods} period(s) of {time_col!r}; entities can only be tracked across at least 2"
        )
    if report.n_entities < policy.minimum_entities:
        return (
            f"too few entities to judge: {report.n_entities} observed in at "
            f"least {policy.minimum_periods_per_entity} periods, "
            f"{policy.minimum_entities} needed"
        )
    if report.n_transitions < policy.minimum_steps:
        return (
            f"too few within-entity transitions to judge: {report.n_transitions} "
            f"observed, {policy.minimum_steps} needed"
        )
    return None


def _contradicted(report, work, entity, time, policy) -> bool:
    """Test the caller's declared columns. Returns True if the key is ruled out.

    Writes the status, reason and wording onto the report, because what
    contradicted the key is the useful half of the sentence.
    """
    if report.declared_invariant_cols:
        broken = {
            c: rate
            for c, rate in _invariance_rates(work, entity, report.declared_invariant_cols).items()
            if rate > policy.invariant_violation_rate
        }
        if broken:
            worst = max(broken, key=lambda c: broken[c])
            report.status, report.reason = FAIL, DECLARED_INVARIANT_BROKEN
            report.declared_violations = broken
            report.verdict = (
                f"contradicted - {worst!r} was declared invariant but changes "
                f"within {broken[worst]:.1%} of entities"
            )
            return True

    if report.declared_monotone_cols:
        rates = _declared_monotone_rates(work, entity, time, report.declared_monotone_cols)
        broken = {c: rate for c, rate in rates.items() if rate > policy.monotone_violation_rate}
        if broken:
            worst = max(broken, key=lambda c: broken[c])
            report.status, report.reason = FAIL, DECLARED_MONOTONE_BROKEN
            report.declared_violations = broken
            report.verdict = (
                f"contradicted - {worst!r} was declared monotone but falls "
                f"in {broken[worst]:.1%} of within-entity steps"
            )
            return True
    return False


def validate_key(
    df: pd.DataFrame,
    key: str | Sequence[str],
    time_col: str,
    *,
    invariant_cols: str | Sequence[str] | None = None,
    monotone_cols: str | Sequence[str] | None = None,
    policy: KeyValidationPolicy = DEFAULT_KEY_POLICY,
    n_shuffles: int = 3,
    random_state: int = 0,
) -> KeyReport:
    """Evaluate whether a candidate key supports longitudinal linkage.

    `invariant_cols` and `monotone_cols` are domain knowledge, not hints. A
    declared invariant that changes within an entity, or a declared counter
    that falls, contradicts the key outright, and those are the only routes to
    `fail` besides duplicate entity-period cells. Everything else measured here
    is positive evidence, and a shortage of it means the data could not decide.
    """
    key = (key,) if isinstance(key, str) else tuple(key)
    missing = [c for c in (*key, time_col) if c not in df.columns]
    if missing:
        raise KeyError(f"columns not in frame: {missing}")
    if n_shuffles < 1:
        raise ValueError("n_shuffles must be at least 1")

    declared_invariant, declared_monotone = _declarations(
        df, key, time_col, invariant_cols, monotone_cols
    )

    work, entity, time, n_periods, duplicate_rate, n_cells = _prepare(df, key, time_col, policy)

    report = KeyReport(
        key=key,
        n_entities=int(entity.nunique()),
        n_rows_covered=len(work),
        coverage=float(len(work) / max(len(df), 1)),
        duplicate_rate=duplicate_rate,
        n_transitions=_count_transitions(entity, time),
        declared_invariant_cols=list(declared_invariant),
        declared_monotone_cols=list(declared_monotone),
    )

    # A structural contradiction: one entity cannot hold two values in one period.
    if not n_cells:
        report.verdict = "no rows with a complete key"
        return report
    if duplicate_rate > policy.duplicate_cell_rate:
        report.status, report.reason = FAIL, DUPLICATE_ENTITY_PERIOD
        report.verdict = f"invalid - key repeats within a period ({duplicate_rate:.1%})"
        return report

    too_little = _insufficient(report, policy, time_col, n_periods)
    if too_little is not None:
        report.verdict = too_little
        return report

    if _contradicted(report, work, entity, time, policy):
        return report

    cols = _usable_columns(work, key, time_col)
    if not cols:
        report.verdict = (
            "no evidence-bearing columns: everything outside the key and time column is constant"
        )
        return report

    _measure(report, work, entity, time, cols, policy, n_shuffles, random_state)
    report.status, report.reason = key_status(report, policy)
    report.verdict = key_verdict(report, policy)
    return report


def _is_redundant_superset(combo, scored, n_entities):
    return any(
        set(r.key) < set(combo) and r.status == PASS and r.n_entities >= n_entities for r in scored
    )


def _candidate_pool(df, time_col, candidate_columns) -> list[str]:
    """Columns worth trying as key parts.

    A column with one distinct value per row identifies rows, not entities, so
    it is dropped before the search rather than rejected once per combination.
    """
    if candidate_columns is not None:
        missing = [c for c in candidate_columns if c not in df.columns]
        if missing:
            raise KeyError(f"candidate columns not in frame: {missing}")
        pool = [c for c in candidate_columns if c != time_col]
    else:
        pool = [c for c in df.columns if c != time_col]
    return [c for c in pool if df[c].nunique(dropna=False) < len(df)]


def _qualifying_entities(df, combo, time_col, policy) -> int | None:
    """Entities this combination would yield, or None if it cannot be a key.

    Cheap structural screening, so a combination that repeats within a period
    or covers too few entities never reaches the measurement.
    """
    sub = df.dropna(subset=[*combo, time_col]).reset_index(drop=True)
    if len(sub) < policy.minimum_entities * policy.minimum_periods_per_entity:
        return None

    ent = entity_key(sub, combo)
    per_period = sub.groupby([ent, sub[time_col]], sort=False).size()
    if not len(per_period) or float((per_period > 1).mean()) > policy.duplicate_cell_rate:
        return None

    counts = ent.value_counts()
    n = int((counts >= policy.minimum_periods_per_entity).sum())
    return n if n >= policy.minimum_entities else None


def _rank(reports: list[KeyReport]) -> None:
    """Sort best first, in place.

    PRIORITY orders statuses worst-to-best for `worst()`, so it is negated
    here: sorting on it directly ranked a rejected candidate above a supported
    one, and `audit` takes reports[0] as the chosen key.
    """
    reports.sort(
        key=lambda r: (
            -PRIORITY[r.status],
            -round(r.evidence_frac * np.sqrt(r.coverage), 6),
            len(r.key),
            -r.n_entities,
        )
    )


def discover_keys(
    df: pd.DataFrame,
    time_col: str,
    *,
    max_columns: int = 2,
    top_k: int = 5,
    candidate_columns: Sequence[str] | None = None,
    invariant_cols: str | Sequence[str] | None = None,
    monotone_cols: str | Sequence[str] | None = None,
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

    # Normalised once, here. Passed through per candidate, a bare string was
    # iterated character by character and every candidate was rejected for
    # columns named "b", "i", "r".
    declared_invariant = _declared("invariant", invariant_cols, (), time_col, df)
    declared_monotone = _declared("monotone", monotone_cols, (), time_col, df)
    pool = _candidate_pool(df, time_col, candidate_columns)

    reports: list[KeyReport] = []
    for size in range(1, max_columns + 1):
        for combo in combinations(pool, size):
            n_entities = _qualifying_entities(df, combo, time_col, policy)
            if n_entities is None or _is_redundant_superset(combo, reports, n_entities):
                continue
            try:
                reports.append(
                    validate_key(
                        df,
                        combo,
                        time_col,
                        invariant_cols=[c for c in declared_invariant if c not in combo] or None,
                        monotone_cols=[c for c in declared_monotone if c not in combo] or None,
                        policy=policy,
                        n_shuffles=n_shuffles,
                        random_state=random_state,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                if rejections is not None:
                    rejections.append((combo, f"{type(exc).__name__}: {exc}"))

    _rank(reports)
    return reports[:top_k]
