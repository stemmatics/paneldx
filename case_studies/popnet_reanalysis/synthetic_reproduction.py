"""Reproduce the linkage mechanism on synthetic data.

The real panel cannot be shared. This builds a panel with a known entity key,
sorts each period by a rank column, assigns the identifier exactly as the
original pipeline did, and audits both keys.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from paneldx import persistence_baseline, validate_key

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_data import add_positional_id


def synthetic_physicians(n=400, quarters=4, seed=0):
    rng = np.random.default_rng(seed)
    opening = rng.integers(2005, 2020, n)
    disease = rng.integers(0, 12, n)
    patients = rng.integers(500, 50_000, n).astype(float)
    visits = rng.integers(100, 20_000, n).astype(float)
    frames = []
    for q in range(quarters):
        patients = patients + rng.integers(10, 800, n)
        visits = visits + rng.integers(5, 400, n)
        frames.append(
            pd.DataFrame(
                {
                    "true_id": np.arange(n),
                    "time": q,
                    "Disease": disease,
                    "Opening time": opening,
                    "Total patients": patients,
                    "Total visits": visits,
                    "Gifts": rng.integers(0, 50, n),
                    "Score": rng.normal(4.0, 0.4, n),
                    "rank": rng.permutation(n) + 1,
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    # The original export was sorted by rank within each quarter and then
    # numbered serially.
    df = df.sort_values(["time", "rank"]).reset_index(drop=True)
    df["Serial number"] = np.arange(1, len(df) + 1)
    return df


def main() -> int:
    df = add_positional_id(synthetic_physicians())
    for label, key in (("positional", "positional_id"), ("true", "true_id")):
        rep = validate_key(df, key, "time")
        base = persistence_baseline(df, key, "time", "Total patients")
        print(
            f"{label:11} key: {rep.status:6} explains {rep.evidence_frac:.0%};"
            f" carry-forward R2 {base.persistence_r2:.3f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
