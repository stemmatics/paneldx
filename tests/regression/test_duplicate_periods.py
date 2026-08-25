"""Repeated observations of one entity-period are not steps in time."""

import pandas as pd
import pytest
from factories import make_panel

from paneldx import detect_counters, persistence_baseline, validate_key


def test_duplicate_entity_periods_invalidate_the_key():
    df = make_panel()
    dup = pd.concat([df, df.iloc[:20]], ignore_index=True)
    rep = validate_key(dup, "uid", "period")
    assert rep.status == "fail"
    assert rep.verdict.startswith("invalid")


def test_duplicate_rows_do_not_create_counter_steps():
    df = make_panel()
    dup = pd.concat([df, df.iloc[:40]], ignore_index=True)
    base = detect_counters(df, "uid", "period")
    rep = detect_counters(dup, "uid", "period")
    assert rep.counters == base.counters
    assert rep.autocorrelation == pytest.approx(base.autocorrelation)


def test_duplicate_periods_make_the_baseline_inconclusive():
    df = make_panel()
    dup = pd.concat([df, df.iloc[:40]], ignore_index=True)
    rep = persistence_baseline(dup, "uid", "period", "total_visits")
    assert rep.status == "inconclusive"
    assert rep.n_duplicate_cells == 40
    assert rep.n_pairs == 0
