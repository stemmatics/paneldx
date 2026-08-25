"""Persistence pairs must be exactly one period step apart."""

import pandas as pd

from paneldx import persistence_baseline


def test_integer_gaps_are_excluded():
    rows = []
    for uid in range(30):
        rows += [(uid, 1, float(uid)), (uid, 2, uid + 1.0)]
    rows += [(999, 1, 5.0), (999, 100, 6.0)]
    df = pd.DataFrame(rows, columns=["uid", "period", "y"])
    rep = persistence_baseline(df, "uid", "period", "y")
    assert rep.n_pairs == 30
    assert rep.n_gapped_pairs == 1


def test_sparse_periods_have_no_adjacent_pairs():
    rows = [(uid, t, float(t)) for uid in range(20) for t in (1, 100)]
    df = pd.DataFrame(rows, columns=["uid", "period", "y"])
    rep = persistence_baseline(df, "uid", "period", "y")
    assert rep.n_pairs == 0
    assert rep.n_gapped_pairs == 20
    assert rep.status == "inconclusive"


def test_mostly_gapped_panel_is_inconclusive():
    rows = []
    for uid in range(5):
        rows += [(uid, 1, 1.0), (uid, 2, 2.0)]
    for uid in range(5, 30):
        rows += [(uid, 1, 1.0), (uid, 3, 2.0)]
    df = pd.DataFrame(rows, columns=["uid", "period", "y"])
    rep = persistence_baseline(df, "uid", "period", "y")
    assert rep.status == "inconclusive"
    assert rep.n_gapped_pairs == 25


def test_missing_quarter_is_a_gap():
    dates = pd.to_datetime(["2021-01-01", "2021-04-01", "2021-10-01"])
    rows = [(uid, d, float(uid + i)) for uid in range(30) for i, d in enumerate(dates)]
    df = pd.DataFrame(rows, columns=["uid", "quarter", "y"])
    rep = persistence_baseline(df, "uid", "quarter", "y", period_step="QS")
    assert rep.n_pairs == 30
    assert rep.n_gapped_pairs == 30
    assert rep.period_step == "QS-JAN"


def test_datetime_periods_need_a_declared_cadence():
    dates = pd.to_datetime(["2021-01-01", "2021-04-01"])
    rows = [(uid, d, 1.0) for uid in range(30) for d in dates]
    df = pd.DataFrame(rows, columns=["uid", "quarter", "y"])
    rep = persistence_baseline(df, "uid", "quarter", "y")
    assert rep.status == "inconclusive"
    assert rep.n_pairs == 0
    assert "period_step" in rep.verdict
