"""Synthetic panels shared across tests."""

import numpy as np
import pandas as pd


def make_panel(n_entities=250, n_periods=4, seed=0):
    """Balanced panel with invariants, cumulative counters and noise."""
    rng = np.random.default_rng(seed)
    birth_year = rng.integers(1950, 2000, n_entities)
    region = rng.integers(0, 5, n_entities)
    visits = rng.integers(5_000, 500_000, n_entities).astype(float)
    spend = rng.integers(1_000, 200_000, n_entities).astype(float)
    frames = []
    for t in range(n_periods):
        visits = visits + rng.integers(100, 8_000, n_entities)
        spend = spend + rng.integers(50, 4_000, n_entities)
        frames.append(
            pd.DataFrame(
                {
                    "uid": np.arange(n_entities),
                    "period": t,
                    "birth_year": birth_year,
                    "region": region,
                    "total_visits": visits,
                    "total_spend": spend,
                    "rating": rng.normal(4.0, 0.5, n_entities),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def standardize(series):
    return (series - series.mean()) / series.std()
