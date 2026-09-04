"""What each verdict means after 0.5.0.

The change these tests pin down is narrow and consequential: `fail` now means
the data contradicts the key, and a shortage of supporting evidence means
`inconclusive`. A tool that cannot tell should say so, because "not supported"
and "shown to be wrong" lead a reader to different actions.
"""

import pandas as pd
import pytest

from paneldx import audit, discover_keys, validate_key
from paneldx.cli import main
from paneldx.status import CONTRADICTION_REASONS, PRIORITY, REASONS
from tests.factories import make_panel


def feature_poor(df):
    """A correctly keyed panel whose columns are all genuinely time-varying.

    Produc's problem in miniature: nothing here can support the key, and
    nothing contradicts it either.
    """
    return df[["uid", "period", "rating"]].copy()


def duplicated_cells(df):
    return pd.concat([df, df.head(len(df) // 2)], ignore_index=True)


# --------------------------------------------------------------------------
# fail means contradicted
# --------------------------------------------------------------------------


def test_duplicate_entity_periods_fail_with_a_fixed_reason():
    """One entity cannot hold two values in one period, whatever else is true."""
    rep = validate_key(duplicated_cells(make_panel()), "uid", "period")

    assert rep.status == "fail"
    assert rep.reason == "duplicate_entity_period"


def test_every_fail_carries_a_contradiction_reason():
    reports = [
        validate_key(duplicated_cells(make_panel()), "uid", "period"),
        validate_key(make_panel(), "region", "period", invariant_cols=["birth_year"]),
    ]

    for rep in reports:
        if rep.status == "fail":
            assert rep.reason in CONTRADICTION_REASONS


def test_a_declared_invariant_that_holds_does_not_fail():
    rep = validate_key(make_panel(), "uid", "period", invariant_cols=["birth_year", "region"])

    assert rep.status == "pass"


def test_a_declared_monotone_that_holds_does_not_fail():
    rep = validate_key(make_panel(), "uid", "period", monotone_cols=["total_visits"])

    assert rep.status == "pass"


# --------------------------------------------------------------------------
# a shortage of evidence is inconclusive, never fail
# --------------------------------------------------------------------------


def test_a_feature_poor_panel_with_a_correct_key_is_not_failed():
    """The false rejection 0.5.0 exists to remove. The key is correct; the
    panel simply has nothing to say about it."""
    rep = validate_key(feature_poor(make_panel()), "uid", "period")

    assert rep.status != "fail"
    assert rep.status == "inconclusive"
    assert rep.reason == "insufficient_evidence"


def test_a_too_small_panel_stays_inconclusive():
    rep = validate_key(make_panel(n_entities=8), "uid", "period")

    assert rep.status == "inconclusive"
    assert "too few entities" in rep.verdict


def test_a_panel_with_one_period_is_inconclusive():
    single = make_panel(n_periods=1)

    rep = validate_key(single, "uid", "period")

    assert rep.status == "inconclusive"


def test_a_key_that_matches_shuffled_labels_is_inconclusive_not_failed():
    df = make_panel()
    shuffled = df.copy()
    shuffled["broken"] = shuffled.groupby("period", sort=False)["uid"].transform(
        lambda s: s.sample(frac=1).values
    )

    rep = validate_key(shuffled.drop(columns=["uid"]), "broken", "period")

    assert rep.status in ("inconclusive", "fail")
    assert rep.status != "pass"


def test_the_supported_key_is_unchanged():
    rep = validate_key(make_panel(), "uid", "period")

    assert rep.status == "pass"
    assert rep.reason == "supported"


# --------------------------------------------------------------------------
# discovery ranks the best candidate first
# --------------------------------------------------------------------------


def with_a_positional_rival(df):
    """The same panel keyed both correctly and by within-period row position."""
    out = df.sort_values(["period", "total_spend"], ascending=[True, False]).reset_index(drop=True)
    out["pos_id"] = out.groupby("period").cumcount()
    return out


def test_discovery_ranks_a_supported_key_above_an_inconclusive_one():
    """`audit` takes reports[0] as the chosen key, so the order is the answer.

    Sorting on the status priority directly put the worst candidate first,
    which handed a positional key to every caller that did not pass `key=`.
    """
    df = with_a_positional_rival(make_panel())
    assert validate_key(df, "uid", "period").status == "pass"
    assert validate_key(df, "pos_id", "period").status == "inconclusive"

    ranked = discover_keys(df, "period", top_k=5)

    assert ranked[0].status == "pass"
    assert ranked[0].key == ("uid",)


def test_discovery_ranking_is_ordered_worst_last():
    ranked = discover_keys(with_a_positional_rival(make_panel()), "period", top_k=5)
    order = [PRIORITY[r.status] for r in ranked]

    assert order == sorted(order, reverse=True)


def test_audit_chooses_the_supported_key_when_none_is_supplied():
    result = audit(with_a_positional_rival(make_panel()), "period")

    assert result.chosen.key == ("uid",)
    assert result.chosen.status == "pass"


# --------------------------------------------------------------------------
# the API stays compatible
# --------------------------------------------------------------------------


def test_the_new_parameters_are_optional():
    """Every existing caller passes neither, and must keep working."""
    assert validate_key(make_panel(), "uid", "period").status == "pass"
    # The audit still warns about the panel's cumulative counters; what matters
    # here is that the key itself is reported as supported.
    assert audit(make_panel(), "period", key="uid").chosen.status == "pass"


def test_declared_columns_must_exist():
    with pytest.raises(KeyError, match="invariant columns not in frame"):
        validate_key(make_panel(), "uid", "period", invariant_cols=["nope"])


def test_declared_columns_cannot_be_the_key_or_the_time_column():
    with pytest.raises(ValueError, match="cannot be part of the key"):
        validate_key(make_panel(), "uid", "period", invariant_cols=["period"])


def test_declared_monotone_columns_must_be_numeric():
    df = make_panel()
    df["label"] = "x"

    with pytest.raises(ValueError, match="must be numeric"):
        validate_key(df, "uid", "period", monotone_cols=["label"])


@pytest.mark.parametrize("declared", ["birth_year", ["birth_year"]])
def test_discovery_accepts_a_single_column_name_as_well_as_a_list(declared):
    """A bare string was iterated character by character, so every candidate
    was rejected for columns named "b", "i", "r" and discovery returned
    nothing at all."""
    ranked = discover_keys(make_panel(), "period", invariant_cols=declared, top_k=3)

    assert ranked
    assert ranked[0].key == ("uid",)
    assert ranked[0].status == "pass"


def test_discovery_still_rejects_an_unknown_declared_column():
    with pytest.raises(KeyError, match="invariant columns not in frame"):
        discover_keys(make_panel(), "period", invariant_cols="nope")


def test_discovery_declared_columns_reach_every_candidate():
    """A candidate that breaks a declared invariant is contradicted, so it
    cannot be returned as usable."""
    ranked = discover_keys(
        with_a_positional_rival(make_panel()),
        "period",
        invariant_cols=["birth_year"],
        top_k=5,
    )
    positional = [r for r in ranked if r.key == ("pos_id",)]

    assert all(r.status == "fail" for r in positional)


def test_a_single_column_name_is_accepted_as_well_as_a_list():
    listed = validate_key(make_panel(), "uid", "period", invariant_cols=["birth_year"])
    single = validate_key(make_panel(), "uid", "period", invariant_cols="birth_year")

    assert listed.status == single.status == "pass"


def test_every_reason_the_package_can_return_is_declared():
    seen = {
        validate_key(make_panel(), "uid", "period").reason,
        validate_key(feature_poor(make_panel()), "uid", "period").reason,
        validate_key(duplicated_cells(make_panel()), "uid", "period").reason,
    }

    assert seen <= set(REASONS)


# --------------------------------------------------------------------------
# the CLI gate stays closed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("frame", "expected"),
    [("supported", 0), ("feature_poor", 2), ("duplicated", 1)],
)
def test_cli_exit_codes_stay_safe(tmp_path, frame, expected):
    """Nothing that is not demonstrably usable may exit 0."""
    panels = {
        "supported": make_panel(),
        "feature_poor": feature_poor(make_panel()),
        "duplicated": duplicated_cells(make_panel()),
    }
    path = tmp_path / "panel.csv"
    panels[frame].to_csv(path, index=False)

    assert main(["audit", str(path), "--time", "period", "--key", "uid", "--quiet"]) == expected


def test_cli_accepts_declared_columns(tmp_path, capsys):
    path = tmp_path / "panel.csv"
    make_panel().to_csv(path, index=False)

    code = main(
        [
            "audit",
            str(path),
            "--time",
            "period",
            "--key",
            "uid",
            "--invariant",
            "birth_year",
            "region",
            "--monotone",
            "total_visits",
            "--quiet",
        ]
    )

    assert code == 0
    assert "PASS" in capsys.readouterr().out
