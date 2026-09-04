import numpy as np
import pytest

from paneldx import audit
from tests.factories import make_panel, standardize


def test_clean_panel_has_no_failures():
    res = audit(make_panel(), "period", key="uid")
    assert res.worst == "warn"
    assert res.chosen.status == "pass"
    assert not [f for f in res.findings if f.status == "fail"]


def test_composite_target_is_reported_as_failure():
    df = make_panel()
    df["popularity"] = (standardize(df["total_visits"]) + standardize(df["total_spend"])) / 2
    res = audit(df, "period", key="uid", target="popularity")
    assert res.worst == "fail"
    assert any(f.code == "leakage" for f in res.findings)


def test_findings_are_ordered_worst_first():
    df = make_panel()
    df["popularity"] = (standardize(df["total_visits"]) + standardize(df["total_spend"])) / 2
    sev = [f.status for f in audit(df, "period", key="uid", target="popularity").findings]
    assert sev == sorted(sev, key=["fail", "inconclusive", "warn", "pass"].index)


def test_findings_are_computed_once():
    res = audit(make_panel(), "period", key="uid")
    assert isinstance(res.findings, tuple)
    assert res.findings is res.findings


def test_discovers_a_key_when_none_supplied():
    res = audit(make_panel(), "period", max_columns=1)
    assert res.chosen.key == ("uid",)
    assert res.key_was_supplied is False


def test_unknown_time_column_raises():
    with pytest.raises(KeyError):
        audit(make_panel(), "nope")


def test_leakage_features_exclude_key_and_time():
    res = audit(make_panel(), "period", key="uid", target="rating")
    assert res.leakage.n_features == 4  # birth_year, region, total_visits, total_spend


def weak_key_panel():
    df = make_panel()
    rng = np.random.default_rng(5)
    for i in range(7):
        df[f"noise_{i}"] = rng.normal(size=len(df))
    return df


def test_weak_key_blocks_within_entity_checks_by_default():
    res = audit(weak_key_panel(), "period", key="uid", target="total_visits")
    assert res.chosen.status == "warn"
    assert res.counters is None
    assert res.baseline is None


def test_weak_key_can_be_allowed_explicitly():
    res = audit(weak_key_panel(), "period", key="uid", target="total_visits", allow_weak_key=True)
    assert res.chosen.status == "warn"
    assert res.counters is not None
    assert res.baseline is not None
