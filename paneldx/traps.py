"""Counter, leakage and persistence diagnostics."""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from .classify import baseline_status, counter_status, leakage_status
from .describe import baseline_verdict, leakage_verdict
from .keys import entity_key
from .policy import DEFAULT_TRAP_POLICY, TrapPolicy
from .status import INCONCLUSIVE, Status


def _drop_unattributable(df, key, time_col):
    # Rows without an entity or period cannot be placed; a fresh index keeps
    # label selection exact under a non-unique input index.
    cols = ([key] if isinstance(key, str) else list(key)) + [time_col]
    return df.dropna(subset=cols).reset_index(drop=True)


def _entity_series(df, key):
    return entity_key(df, (key,) if isinstance(key, str) else tuple(key))


@dataclass
class CounterReport:
    """Cumulative-counter detection results."""

    counters: list[str] = field(default_factory=list)
    autocorrelation: dict[str, float] = field(default_factory=dict)
    n_columns_tested: int = 0
    status: Status = INCONCLUSIVE

    def __str__(self) -> str:  # pragma: no cover
        if self.status == INCONCLUSIVE:
            return "not enough within-entity history to test for counters"
        if not self.counters:
            return "no cumulative counters detected"
        rows = [f"{len(self.counters)} cumulative counter(s) detected:"]
        for c in self.counters:
            rho = self.autocorrelation.get(c, float("nan"))
            rows.append(f"  {c:<34} lag-1 autocorrelation {rho:.4f}")
        rows.append("  -> rarely decrease within an entity; consider per-period changes")
        return "\n".join(rows)


def detect_counters(
    df: pd.DataFrame,
    key: str | Sequence[str],
    time_col: str,
    *,
    exclude: Sequence[str] | None = None,
    policy: TrapPolicy = DEFAULT_TRAP_POLICY,
) -> CounterReport:
    """Detect numeric columns that rarely decrease within entities."""
    df = _drop_unattributable(df, key, time_col)
    entity = _entity_series(df, key)
    time = df[time_col].to_numpy()
    order = np.lexsort((time, entity.to_numpy()))
    ent, tim = entity.to_numpy()[order], time[order]
    # Repeated observations of one period are not steps in time.
    same_entity = (ent[1:] == ent[:-1]) & (tim[1:] != tim[:-1])

    report = CounterReport()
    if not same_entity.any():
        return report

    skip = set((key,) if isinstance(key, str) else key) | {time_col}
    skip |= set(exclude or ())
    for col in df.columns:
        if col in skip or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        v = df[col].to_numpy(dtype="float64", na_value=np.nan)[order]
        if not np.isfinite(v).any() or np.nanmin(v) < 0:
            continue
        step = np.diff(v)
        valid = same_entity & np.isfinite(step)
        if valid.sum() < policy.minimum_steps:
            continue
        report.n_columns_tested += 1
        if (step[valid] != 0).mean() < 0.5:
            continue
        if (step[valid] < 0).mean() > policy.counter_decrease_rate:
            continue

        report.counters.append(col)
        prev, curr = v[:-1][valid], v[1:][valid]
        if prev.std() > 0 and curr.std() > 0:
            report.autocorrelation[col] = float(np.corrcoef(prev, curr)[0, 1])

    report.status = counter_status(report)
    return report


@dataclass
class LeakageReport:
    """Linear reconstruction of the target from its features."""

    r2: float = float("nan")
    n_features: int = 0
    top_contributors: list[tuple[str, float]] = field(default_factory=list)
    status: Status = INCONCLUSIVE
    verdict: str = "unknown"

    def __str__(self) -> str:  # pragma: no cover
        rows = [
            f"target reconstructed from features: R2 = {self.r2:.4f} "
            f"(held out, {self.n_features} numeric features)",
        ]
        if self.top_contributors:
            top = ", ".join(f"{n} ({w:+.2f})" for n, w in self.top_contributors[:5])
            rows.append(f"  largest standardised coefficients: {top}")
        rows.append(f"  VERDICT  {self.verdict}")
        return "\n".join(rows)


def _reconstruction(y, X, random_state):
    mu, sigma = X.mean(axis=0), X.std(axis=0)
    X = (X - mu) / np.where(sigma > 0, sigma, 1.0)
    X = np.column_stack([np.ones(len(X)), X])

    idx = np.random.default_rng(random_state).permutation(len(y))
    tr, te = idx[: len(y) // 2], idx[len(y) // 2 :]

    beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
    resid = y[te] - X[te] @ beta
    denom = ((y[te] - y[te].mean()) ** 2).sum()
    r2 = float(1 - (resid @ resid) / denom) if denom > 0 else float("nan")
    return r2, beta[1:]


def target_leakage(
    df: pd.DataFrame,
    target: str,
    features: Sequence[str] | None = None,
    *,
    random_state: int = 0,
    policy: TrapPolicy = DEFAULT_TRAP_POLICY,
) -> LeakageReport:
    """Screen a numeric target for linear reconstruction from its features."""
    if target not in df.columns:
        raise KeyError(f"target {target!r} not in frame")

    if not pd.api.types.is_numeric_dtype(df[target]):
        return LeakageReport(
            verdict=(
                f"target {target!r} is not numeric ({df[target].dtype}); this "
                "linear reconstruction test needs a numeric target. Use a "
                "classification-specific leakage check instead."
            )
        )

    if features is None:
        features = [c for c in df.columns if c != target and pd.api.types.is_numeric_dtype(df[c])]
    else:
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise KeyError(f"feature columns not in frame: {missing}")
        bad = [f for f in features if not pd.api.types.is_numeric_dtype(df[f])]
        if bad:
            raise ValueError(f"non-numeric feature columns: {bad}")
    features = [
        f for f in dict.fromkeys(features) if f != target and df[f].nunique(dropna=True) > 1
    ]
    if not features:
        return LeakageReport(verdict="no numeric features to test")

    sub = df[[target, *features]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < policy.rows_per_feature * len(features):
        return LeakageReport(
            n_features=len(features),
            verdict="too few complete rows to test reliably",
        )

    r2, coefficients = _reconstruction(
        sub[target].to_numpy(dtype="float64"),
        sub[list(features)].to_numpy(dtype="float64"),
        random_state,
    )
    report = LeakageReport(
        r2=r2,
        n_features=len(features),
        top_contributors=sorted(zip(features, coefficients), key=lambda kv: -abs(kv[1]))[:5],
    )
    if not np.isfinite(r2):
        report.verdict = (
            "target is constant on the tested rows; a reconstruction test "
            "needs variance in the target"
        )
        return report
    report.status = leakage_status(r2, policy)
    report.verdict = leakage_verdict(report.status)
    return report


@dataclass
class BaselineReport:
    """Carry-forward baseline results."""

    n_pairs: int = 0
    n_gapped_pairs: int = 0
    n_duplicate_cells: int = 0
    period_step: str = ""
    target_autocorrelation: float = float("nan")
    persistence_mae: float = float("nan")
    persistence_r2: float = float("nan")
    status: Status = INCONCLUSIVE
    verdict: str = "unknown"

    def __str__(self) -> str:  # pragma: no cover
        return "\n".join(
            [
                f"persistence baseline over {self.n_pairs:,} adjacent pairs, "
                f"one step of {self.period_step or '?'} apart "
                f"({self.n_gapped_pairs:,} gapped pairs excluded):",
                f"  target lag-1 autocorrelation  {self.target_autocorrelation:.4f}",
                f"  carry-forward MAE             {self.persistence_mae:.4f}",
                f"  carry-forward R2              {self.persistence_r2:.4f}",
                f"  VERDICT  {self.verdict}",
            ]
        )


def _resolve_period_step(time, time_col, period_step) -> tuple[Any, str] | BaselineReport:
    if pd.api.types.is_datetime64_any_dtype(time):
        if period_step is None:
            return BaselineReport(
                verdict=(
                    f"period column {time_col!r} is datetime; declare its cadence "
                    "with period_step (for example 'QS' for quarter starts, 'MS' "
                    "for month starts, '7D') so adjacency is not guessed from the data"
                )
            )
        bad = TypeError(
            f"period_step for a datetime period column must be a pandas "
            f"frequency string, Timedelta or DateOffset, not {period_step!r}"
        )
        try:
            offset = to_offset(period_step)
        except (TypeError, ValueError) as exc:
            raise bad from exc
        if offset is None:
            raise bad
        return offset, offset.freqstr

    if pd.api.types.is_numeric_dtype(time):
        if period_step is None:
            period_step = 1
        if (
            isinstance(period_step, bool)
            or not isinstance(period_step, numbers.Real)
            or not 0 < float(period_step) < math.inf
        ):
            raise TypeError(
                f"period_step for a numeric period column must be a positive "
                f"number, not {period_step!r}"
            )
        return period_step, str(period_step)

    return BaselineReport(
        verdict=(
            f"period column {time_col!r} is neither numeric nor datetime, so "
            "adjacency is undefined; map the periods onto an ordered numeric "
            "scale first"
        )
    )


def _adjacent(curr, prev, step, is_datetime):
    if is_datetime:
        return curr == (pd.DatetimeIndex(prev) + step).to_numpy()
    return np.isclose(curr - prev, step, rtol=1e-9, atol=0.0)


def persistence_baseline(
    df: pd.DataFrame,
    key: str | Sequence[str],
    time_col: str,
    target: str,
    *,
    period_step: object = None,
    policy: TrapPolicy = DEFAULT_TRAP_POLICY,
) -> BaselineReport:
    """Evaluate a carry-forward baseline over adjacent periods."""
    if target not in df.columns:
        raise KeyError(f"target {target!r} not in frame")

    df = _drop_unattributable(df, key, time_col)
    time = df[time_col]
    resolved = _resolve_period_step(time, time_col, period_step)
    if isinstance(resolved, BaselineReport):
        return resolved
    step, label = resolved

    work = (
        pd.DataFrame(
            {
                "entity": _entity_series(df, key),
                "time": time,
                "y": pd.to_numeric(df[target], errors="coerce"),
            }
        )
        .dropna()
        .sort_values(["entity", "time"])
    )
    report = BaselineReport(period_step=label)
    # Two observations of one period leave no single value to carry forward.
    duplicated = work.duplicated(["entity", "time"], keep=False)
    if duplicated.any():
        report.n_duplicate_cells = work[duplicated].groupby(["entity", "time"]).ngroups
        report.verdict = (
            f"{report.n_duplicate_cells} entity-period cell(s) hold more than one "
            "observation, so there is no single value to carry forward; resolve "
            "the duplicates before scoring"
        )
        return report

    work["prev"] = work.groupby("entity")["y"].shift(1)
    work["prev_time"] = work.groupby("entity")["time"].shift(1)
    pairs = work.dropna(subset=["prev", "prev_time"])
    if len(pairs):
        adjacent = _adjacent(
            pairs["time"].to_numpy(),
            pairs["prev_time"].to_numpy(),
            step,
            pd.api.types.is_datetime64_any_dtype(time),
        )
        report.n_gapped_pairs = int((~adjacent).sum())
        pairs = pairs[adjacent]

    report.n_pairs = len(pairs)
    if report.n_pairs < policy.minimum_pairs:
        report.verdict = (
            f"too few adjacent observation pairs to score at a period step "
            f"of {label} ({report.n_pairs} adjacent, {report.n_gapped_pairs} gapped)"
        )
        return report

    y, prev = pairs["y"].to_numpy(), pairs["prev"].to_numpy()
    if prev.std() > 0 and y.std() > 0:
        report.target_autocorrelation = float(np.corrcoef(prev, y)[0, 1])
    report.persistence_mae = float(np.abs(y - prev).mean())

    denom = ((y - y.mean()) ** 2).sum()
    if denom > 0:
        report.persistence_r2 = float(1 - ((y - prev) ** 2).sum() / denom)

    if not np.isfinite(report.persistence_r2):
        report.verdict = "target does not vary; nothing to forecast"
        return report
    report.status = baseline_status(report.persistence_r2, policy)
    report.verdict = baseline_verdict(report.persistence_r2, policy)
    return report
