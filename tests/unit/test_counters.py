"""Cumulative-counter detection."""

from paneldx import detect_counters
from tests.factories import make_panel


def test_counters_are_found():
    rep = detect_counters(make_panel(), "uid", "period")
    assert set(rep.counters) == {"total_visits", "total_spend"}
    assert all(rep.autocorrelation[c] > 0.9 for c in rep.counters)


def test_noise_and_invariants_are_not_counters():
    rep = detect_counters(make_panel(), "uid", "period")
    assert "rating" not in rep.counters
    assert "region" not in rep.counters


def test_excluded_columns_are_not_examined():
    rep = detect_counters(make_panel(), "uid", "period", exclude=["total_visits"])
    assert "total_visits" not in rep.counters
    assert "total_spend" in rep.counters
