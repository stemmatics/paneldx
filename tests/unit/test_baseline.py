"""Carry-forward persistence baseline."""

import numpy as np
import pandas as pd
import pytest

from paneldx import persistence_baseline
from tests.factories import make_panel


def test_cumulative_target_is_dominated_by_persistence():
    rep = persistence_baseline(make_panel(), "uid", "period", "total_visits")
    assert rep.target_autocorrelation > 0.95
    assert rep.persistence_r2 >= 0.95
    assert rep.status == "warn"


def test_noise_target_is_not():
    df = make_panel()
    df["noise"] = np.random.default_rng(3).normal(size=len(df))
    rep = persistence_baseline(df, "uid", "period", "noise")
    assert rep.persistence_r2 < 0.70
    assert rep.status == "pass"


def test_constant_target_is_inconclusive():
    df = make_panel()
    df["const"] = 5.0
    assert persistence_baseline(df, "uid", "period", "const").status == "inconclusive"


def test_too_few_pairs_is_inconclusive():
    rep = persistence_baseline(
        make_panel(n_entities=5, n_periods=2), "uid", "period", "total_visits"
    )
    assert rep.status == "inconclusive"
    assert rep.n_pairs == 5


def test_numeric_cadence_is_explicit():
    rows = [(uid, t, float(uid + t)) for uid in range(30) for t in (0, 5, 10)]
    df = pd.DataFrame(rows, columns=["uid", "period", "y"])
    declared = persistence_baseline(df, "uid", "period", "y", period_step=5)
    assert declared.n_pairs == 60 and declared.n_gapped_pairs == 0
    assert declared.period_step == "5"
    default = persistence_baseline(df, "uid", "period", "y")
    assert default.n_pairs == 0 and default.n_gapped_pairs == 60


def test_string_periods_are_inconclusive():
    df = make_panel()
    df["period"] = df["period"].map({0: "Q1", 1: "Q2", 2: "Q3", 3: "Q4"})
    assert persistence_baseline(df, "uid", "period", "total_visits").status == "inconclusive"


@pytest.mark.parametrize("period_step", ["QS", 0])
def test_mismatched_period_step_raises(period_step):
    with pytest.raises(TypeError, match="positive number"):
        persistence_baseline(make_panel(), "uid", "period", "total_visits", period_step=period_step)
