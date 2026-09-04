"""Aggregation and uncertainty for benchmark results.

Enforces two rules from validation/protocol/protocol.md: statuses are never
ranked, and rates aggregate by corruption procedure, then dataset, then family
before any interval is computed.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

import numpy as np

STATUSES = ("pass", "warn", "inconclusive", "fail")
UNSAFE_ACCEPTANCE = ("pass", "warn")
SAFE_STOP = ("fail", "inconclusive")


def status_counts(statuses: Iterable[str]) -> dict[str, int]:
    counted = Counter(statuses)
    unknown = set(counted) - set(STATUSES)
    if unknown:
        raise ValueError(f"unknown status(es): {sorted(unknown)}")
    return {status: int(counted.get(status, 0)) for status in STATUSES}


def rates(counts: dict[str, int]) -> dict[str, float | int | None]:
    """The two rates, always returned beside the counts that produced them.

    A rate alone cannot tell a tool that rejected a broken key from one that
    declined to look at it, so nothing here ever returns a bare proportion.
    """
    runs = sum(counts[status] for status in STATUSES)
    if not runs:
        return {**counts, "runs": 0, "unsafe_acceptance_rate": None, "safe_stop_rate": None}
    unsafe = sum(counts[status] for status in UNSAFE_ACCEPTANCE)
    return {
        **counts,
        "runs": runs,
        "unsafe_acceptance_rate": unsafe / runs,
        "safe_stop_rate": sum(counts[status] for status in SAFE_STOP) / runs,
    }


def summarise(statuses: Iterable[str]) -> dict[str, float | int | None]:
    return rates(status_counts(statuses))


def mean_of_group_means(groups: dict[str, list[str]], predicate) -> float | None:
    """Average within each group, then across groups.

    Without this the aggregate is a case-weighted mixture: `partial_corruption`
    contributes six levels and `positional_rekey` one, so the headline rate
    mostly reflects how many levels each procedure happens to declare rather
    than how the tool behaves.
    """
    per_group = [
        float(np.mean([predicate(status) for status in statuses]))
        for statuses in groups.values()
        if statuses
    ]
    return float(np.mean(per_group)) if per_group else None


def unsafe_acceptance(groups: dict[str, list[str]]) -> float | None:
    """Unsafe acceptance, weighting each corruption procedure equally."""
    return mean_of_group_means(groups, lambda status: status in UNSAFE_ACCEPTANCE)


def inconclusive_rate(groups: dict[str, list[str]]) -> float | None:
    """Inconclusive, weighting each corruption procedure equally.

    Reported next to unsafe acceptance under the same weighting: a tool can
    drive acceptance to zero by declining to judge, and the two rates only mean
    something together.
    """
    return mean_of_group_means(groups, lambda status: status == "inconclusive")


def by_family(dataset_values: dict[str, float], families: dict[str, str]) -> dict[str, float]:
    """Collapse per-dataset values to one value per family."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for dataset, value in dataset_values.items():
        if value is None:
            continue
        grouped[families[dataset]].append(value)
    return {family: float(np.mean(values)) for family, values in sorted(grouped.items())}


def bootstrap_interval(
    values: Sequence[float],
    *,
    n_resamples: int = 10_000,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict[str, float | int | None]:
    """Percentile bootstrap over families.

    Families are resampled, not runs. With six families the interval is wide;
    that width is the result.
    """
    values = [float(v) for v in values if v is not None]
    k = len(values)
    if not k:
        return {"point": None, "low": None, "high": None, "k": 0, "n_resamples": 0}
    point = float(np.mean(values))
    if k == 1:
        return {"point": point, "low": None, "high": None, "k": 1, "n_resamples": 0}

    rng = np.random.default_rng(seed)
    draws = rng.choice(np.asarray(values), size=(n_resamples, k), replace=True).mean(axis=1)
    tail = (1 - confidence) / 2
    return {
        "point": point,
        "low": float(np.quantile(draws, tail)),
        "high": float(np.quantile(draws, 1 - tail)),
        "k": k,
        "n_resamples": n_resamples,
    }


def wilson_interval(successes: int, n: int, *, confidence: float = 0.95) -> dict:
    """Wilson score interval, valid only for one independent binary outcome per
    family. Anything averaged over runs must use the bootstrap instead."""
    if n <= 0:
        return {"point": None, "low": None, "high": None, "n": 0}
    if not 0 <= successes <= n:
        raise ValueError(f"{successes} successes out of {n}")
    # 1.959963985 is the two-sided normal quantile at 95%; kept explicit so the
    # confidence level cannot silently disagree with the constant.
    z = {0.95: 1.959963985, 0.99: 2.5758293035}.get(confidence)
    if z is None:
        raise ValueError(f"no z value recorded for confidence {confidence}")
    p = successes / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return {
        "point": p,
        "low": max(0.0, centre - half),
        "high": min(1.0, centre + half),
        "n": n,
        "successes": successes,
    }


def sensitivity(levels: dict[float, float]) -> dict:
    """Check that unsafe acceptance never rises as corruption rises.

    Stated on proportions, not on a rank: more damage must not make the tool
    more willing to accept the key, and a flat curve is a reported failure of
    sensitivity rather than a pass.
    """
    ordered = sorted(levels)
    series = [levels[level] for level in ordered]
    if len(series) < 2:
        return {"levels": ordered, "series": series, "monotone": None, "moves": None, "ok": None}
    monotone = all(later <= earlier + 1e-12 for earlier, later in zip(series, series[1:]))
    moves = series[-1] < series[0] - 1e-12
    return {
        "levels": ordered,
        "series": series,
        "monotone": monotone,
        "moves": moves,
        "ok": bool(monotone and moves),
    }
