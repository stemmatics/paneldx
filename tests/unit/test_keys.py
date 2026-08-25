"""Key validation and discovery on panels with a known key."""

import numpy as np
import pandas as pd
import pytest

from paneldx import KeyValidationPolicy, discover_keys, entity_key, validate_key


def make_panel(n_entities=300, n_periods=4, seed=0):
    rng = np.random.default_rng(seed)
    birth_year = rng.integers(1950, 2000, n_entities)
    region = rng.integers(0, 5, n_entities)
    visits = rng.integers(0, 100, n_entities).astype(float)
    spend = rng.integers(0, 200, n_entities).astype(float)
    rows = []
    for t in range(n_periods):
        visits = visits + rng.integers(1, 20, n_entities)
        spend = spend + rng.integers(1, 30, n_entities)
        rows.append(
            pd.DataFrame(
                {
                    "uid": np.arange(n_entities),
                    "period": t,
                    "birth_year": birth_year,
                    "region": region,
                    "total_visits": visits,
                    "total_spend": spend,
                    "noise": rng.normal(size=n_entities),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


@pytest.mark.parametrize("seed", [0, 7, 19, 41])
def test_true_key_is_supported(seed):
    rep = validate_key(make_panel(seed=seed), "uid", "period")
    assert rep.status == "pass"
    assert {"birth_year", "region"} <= set(rep.invariant_cols)
    assert {"total_visits", "total_spend"} <= set(rep.monotone_cols)


def test_invariants_are_not_counted_as_counters():
    rep = validate_key(make_panel(), "uid", "period")
    assert not set(rep.invariant_cols) & set(rep.monotone_cols)
    assert "birth_year" not in rep.monotone_cols


def test_row_order_does_not_change_the_status():
    df = make_panel()
    shuffled = df.sample(frac=1.0, random_state=20).reset_index(drop=True)
    assert (
        validate_key(shuffled, "uid", "period").status == validate_key(df, "uid", "period").status
    )


def test_policy_thresholds_apply():
    strict = KeyValidationPolicy(supported_evidence_fraction=0.99)
    rep = validate_key(make_panel(), "uid", "period", policy=strict)
    assert rep.status == "warn"


def test_discover_finds_the_true_key():
    found = discover_keys(make_panel(), "period", max_columns=1, top_k=3)
    assert found and found[0].key == ("uid",)


def test_discover_finds_compound_key_with_coarse_column():
    """Neither column works alone; any column set inducing the true partition is correct."""
    df = make_panel(n_entities=150)
    df["site"] = df["uid"] % 3
    df["local_id"] = df["uid"] // 3
    truth = df["uid"]
    df = df.drop(columns=["uid"])

    found = discover_keys(df, "period", max_columns=2, top_k=5)
    assert found
    winner = df[list(found[0].key)].astype(str).agg("|".join, axis=1)
    assert winner.groupby(truth).nunique().max() == 1, "true entity split across keys"
    assert truth.groupby(winner).nunique().max() == 1, "distinct entities merged"


def test_coverage_is_preferred_over_a_fragmenting_key():
    df = make_panel(n_entities=200)
    df.loc[df.index % 7 == 0, "sparse"] = 1.0
    found = discover_keys(df, "period", max_columns=1, top_k=5)
    assert found[0].key == ("uid",)


def test_single_period_is_an_error():
    with pytest.raises(ValueError, match="at least 2"):
        discover_keys(make_panel(n_periods=1), "period")


def test_missing_columns_raise():
    df = make_panel()
    with pytest.raises(KeyError):
        validate_key(df, "nope", "period")
    with pytest.raises(KeyError, match="ghost"):
        discover_keys(df, "period", candidate_columns=["uid", "ghost"])


def test_empty_key_raises():
    with pytest.raises(ValueError, match="at least one column"):
        entity_key(make_panel(), ())


def test_control_parameters_are_validated():
    df = make_panel()
    with pytest.raises(ValueError, match="n_shuffles"):
        validate_key(df, "uid", "period", n_shuffles=0)
    with pytest.raises(ValueError, match="max_columns"):
        discover_keys(df, "period", max_columns=0)
    with pytest.raises(ValueError, match="top_k"):
        discover_keys(df, "period", top_k=0)
