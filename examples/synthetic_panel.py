"""Runnable demo: a clean panel, then the same panel with a fabricated key.

    python examples/synthetic_panel.py

Builds a small panel where the true entity id is known, then reproduces the
failure mode that motivated this package (re-sorting each period, then linking
rows by position) and shows what paneldx says about each.
"""

import numpy as np
import pandas as pd

from paneldx import discover_keys, validate_key

RNG = np.random.default_rng(0)
N_ENTITIES, N_PERIODS = 400, 4


def build_panel() -> pd.DataFrame:
    birth_year = RNG.integers(1950, 2000, N_ENTITIES)  # invariant
    region = RNG.integers(0, 6, N_ENTITIES)  # invariant
    visits = RNG.integers(0, 100, N_ENTITIES).astype(float)
    spend = RNG.integers(0, 200, N_ENTITIES).astype(float)

    frames = []
    for period in range(N_PERIODS):
        visits = visits + RNG.integers(1, 20, N_ENTITIES)  # cumulative
        spend = spend + RNG.integers(1, 30, N_ENTITIES)  # cumulative
        frames.append(
            pd.DataFrame(
                {
                    "customer_id": np.arange(N_ENTITIES),
                    "period": period,
                    "birth_year": birth_year,
                    "region": region,
                    "total_visits": visits,
                    "total_spend": spend,
                    "satisfaction": RNG.normal(4.2, 0.4, N_ENTITIES).round(2),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def fabricate_positional_key(df: pd.DataFrame) -> pd.DataFrame:
    """Rank rows within each period, then link by position across periods.

    This is what a leaderboard export looks like: position `i` is whoever placed
    `i`-th that period, which is a different entity each time.
    """
    ranked = df.sort_values(["period", "total_spend"], ascending=[True, False]).reset_index(
        drop=True
    )
    per_period = len(ranked) // ranked["period"].nunique()
    ranked["positional_id"] = ranked.index % per_period
    return ranked.drop(columns=["customer_id"])


def main() -> None:
    df = build_panel()

    print("=" * 70)
    print("1. THE TRUE KEY")
    print("=" * 70)
    print(validate_key(df, "customer_id", "period"))

    print()
    print("=" * 70)
    print("2. A KEY BUILT FROM ROW POSITION")
    print("=" * 70)
    print(validate_key(fabricate_positional_key(df), "positional_id", "period"))

    print()
    print("=" * 70)
    print("3. BLIND SEARCH (no hints)")
    print("=" * 70)
    for i, rep in enumerate(discover_keys(df, "period", max_columns=1, top_k=3), 1):
        print(
            f"#{i}  {' + '.join(rep.key):<16} explains {rep.evidence_frac:.0%}  ->  {rep.verdict}"
        )


if __name__ == "__main__":
    main()
