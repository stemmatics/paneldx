"""Rows without a key value or a period are excluded, not merged into one entity."""

import numpy as np
import pytest
from factories import make_panel

from paneldx import detect_counters, persistence_baseline, validate_key


def test_missing_key_rows_are_excluded_from_validation():
    df = make_panel()
    df["uid"] = df["uid"].astype(float)
    df.loc[df.index[:60], "uid"] = np.nan
    rep = validate_key(df, "uid", "period")
    assert rep.n_rows_covered == len(df) - 60
    assert rep.status == "pass"


def test_missing_time_rows_are_excluded_from_validation():
    df = make_panel()
    df["period"] = df["period"].astype(float)
    df.loc[df.index[:30], "period"] = np.nan
    rep = validate_key(df, "uid", "period")
    assert rep.n_rows_covered == len(df) - 30
    assert rep.status == "pass"


def test_missing_key_rows_are_excluded_from_trap_detectors():
    df = make_panel(n_entities=100)
    df["uid"] = df["uid"].astype(float)
    corrupted = df.copy()
    corrupted.loc[corrupted["uid"] < 30, "uid"] = np.nan
    kept = df[df["uid"] >= 30]

    clean = persistence_baseline(kept, "uid", "period", "total_visits")
    dirty = persistence_baseline(corrupted, "uid", "period", "total_visits")
    assert dirty.n_pairs == clean.n_pairs
    assert dirty.persistence_mae == pytest.approx(clean.persistence_mae)

    c_clean = detect_counters(kept, "uid", "period")
    c_dirty = detect_counters(corrupted, "uid", "period")
    assert c_dirty.counters == c_clean.counters
    assert c_dirty.autocorrelation == pytest.approx(c_clean.autocorrelation)
