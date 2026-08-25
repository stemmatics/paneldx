"""Linear target-reconstruction screening."""

import numpy as np
import pandas as pd
import pytest
from factories import make_panel, standardize

from paneldx import target_leakage

FEATURES = ["total_visits", "total_spend", "rating"]


def test_composite_target_fails():
    df = make_panel()
    df["popularity"] = (standardize(df["total_visits"]) + standardize(df["total_spend"])) / 2
    rep = target_leakage(df, "popularity", FEATURES)
    assert rep.r2 >= 0.99
    assert rep.status == "fail"


def test_partially_composed_target_warns():
    df = make_panel()
    rng = np.random.default_rng(1)
    signal_share = 0.93
    exposed = standardize(standardize(df["total_visits"]) + standardize(df["total_spend"]))
    private = pd.Series(rng.normal(size=len(df)), index=df.index)
    df["popularity"] = np.sqrt(signal_share) * exposed + np.sqrt(1 - signal_share) * private

    rep = target_leakage(df, "popularity", FEATURES)
    assert 0.90 <= rep.r2 < 0.99, rep.r2
    assert rep.status == "warn"


def test_independent_target_passes():
    df = make_panel()
    df["outcome"] = np.random.default_rng(2).normal(size=len(df))
    rep = target_leakage(df, "outcome", FEATURES)
    assert rep.r2 < 0.90
    assert rep.status == "pass"


def test_missing_target_raises():
    with pytest.raises(KeyError):
        target_leakage(make_panel(), "nope")


@pytest.mark.parametrize("target", ["categorical", "coded", "empty"])
def test_unsupported_targets_are_inconclusive(target):
    df = make_panel()
    df["categorical"] = np.where(df["rating"] > 4, "high", "low")
    df["coded"] = df["total_visits"].astype(int).astype(str)
    df["empty"] = np.nan
    assert target_leakage(df, target).status == "inconclusive"


def test_bad_requested_features_raise():
    df = make_panel()
    df["label"] = "a"
    with pytest.raises(KeyError, match="ghost"):
        target_leakage(df, "rating", ["ghost"])
    with pytest.raises(ValueError, match="label"):
        target_leakage(df, "rating", ["label"])
