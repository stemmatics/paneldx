"""The corruption generators behind the benchmark.

Two properties matter more than any individual transformation: a corruption
must never touch the panel it was given, and the same seed must produce the
same panel every time. Without the first, one case contaminates the next.
Without the second, a recorded result cannot be rebuilt.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from validation.harness import corruptions as C
from validation.harness.cases import EXPECTATION, PROFILES
from validation.harness.corruptions import CORRUPTIONS, Corrupted, rng_for
from validation.manifest import MANIFEST

KEY, TIME = ["uid"], "period"


def panel(n_entities: int = 40, n_periods: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    region = rng.integers(0, 4, n_entities)
    birth = rng.integers(1950, 2000, n_entities)
    total = rng.integers(100, 900, n_entities).astype(float)
    frames = []
    for t in range(n_periods):
        total = total + rng.integers(1, 40, n_entities)
        frames.append(
            pd.DataFrame(
                {
                    "uid": np.arange(n_entities),
                    "period": t,
                    "region": region,
                    "birth_year": birth,
                    "total": total,
                    "score": rng.normal(0, 1, n_entities),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


LEVELS = {
    "positional_rekey": 1.0,
    "within_period_shuffle": 1.0,
    "entity_merge": 0.10,
    "entity_split": 0.10,
    "partial_corruption": 0.20,
    "duplicate_entity_periods": 0.05,
    "missing_entity_keys": 0.05,
    "missing_time_values": 0.05,
    "panel_attrition": 0.10,
    "period_gaps": 0.10,
    "invariant_column_removal": 1,
    "feature_poor_panel": 2,
}


def apply(name: str, df=None, level=None, seed: int = 0) -> Corrupted:
    df = panel() if df is None else df
    level = LEVELS[name] if level is None else level
    return CORRUPTIONS[name](df, KEY, TIME, level, rng_for("fixture", name, level, seed))


# --------------------------------------------------------------------------
# the two invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_the_input_panel_is_never_modified(name):
    df = panel()
    before = df.to_csv(index=False)

    apply(name, df)

    assert df.to_csv(index=False) == before


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_the_same_seed_produces_the_same_panel(name):
    first, second = apply(name, seed=3), apply(name, seed=3)

    assert first.df.to_csv(index=False) == second.df.to_csv(index=False)
    assert first.key == second.key
    assert (first.entities_affected, first.rows_affected) == (
        second.entities_affected,
        second.rows_affected,
    )


@pytest.mark.parametrize("name", sorted(set(CORRUPTIONS) - C.DETERMINISTIC))
def test_a_different_seed_produces_a_different_panel(name):
    assert apply(name, seed=0).df.to_csv(index=False) != apply(name, seed=7).df.to_csv(index=False)


@pytest.mark.parametrize("name", sorted(C.DETERMINISTIC))
def test_deterministic_corruptions_ignore_the_seed(name):
    """These take no random choices, so running them under ten seeds would
    record ten identical rows and inflate every denominator."""
    assert apply(name, seed=0).df.to_csv(index=False) == apply(name, seed=9).df.to_csv(index=False)


def test_rng_is_derived_from_the_case_identity_not_the_process():
    """crc32, not hash(): Python salts string hashing per process, so a run
    seeded from it would not reproduce tomorrow."""
    same = rng_for("d", "c", 0.1, 0).integers(0, 2**32, 5)
    again = rng_for("d", "c", 0.1, 0).integers(0, 2**32, 5)
    other = rng_for("d", "c", 0.2, 0).integers(0, 2**32, 5)

    assert list(same) == list(again)
    assert list(same) != list(other)


# --------------------------------------------------------------------------
# what each corruption actually does
# --------------------------------------------------------------------------


def entities(df, key=KEY):
    return df.groupby(key, sort=False, dropna=False).ngroups


def test_positional_rekey_replaces_the_key_with_row_position():
    out = apply("positional_rekey")

    assert out.key == [C.POSITIONAL_KEY]
    assert "uid" not in out.df.columns
    assert out.df[C.POSITIONAL_KEY].max() == 39
    assert out.rows_affected == len(panel())


def test_positional_rekey_needs_a_numeric_column_to_sort_on():
    df = panel()[["uid", "period"]]

    with pytest.raises(ValueError, match="numeric column"):
        CORRUPTIONS["positional_rekey"](df, KEY, TIME, 1.0, rng_for("x", "y", 1.0, 0))


def test_within_period_shuffle_keeps_the_shape_and_breaks_the_link():
    out = apply("within_period_shuffle")

    assert len(out.df) == len(panel())
    assert entities(out.df) == entities(panel())
    assert not out.df.equals(panel())


def test_entity_merge_reduces_the_entity_count():
    out = apply("entity_merge", level=0.5)

    assert entities(out.df) < entities(panel())
    assert out.rows_affected > 0


def test_entity_split_increases_the_entity_count():
    out = apply("entity_split", level=0.5)

    assert entities(out.df) > entities(panel())
    assert out.df["uid"].astype(str).str.contains(C.SPLIT_SUFFIX).any()


def test_partial_corruption_touches_only_the_chosen_share():
    small, large = apply("partial_corruption", level=0.1), apply("partial_corruption", level=0.5)

    assert small.entities_affected < large.entities_affected
    assert small.rows_affected < large.rows_affected


def test_partial_corruption_at_zero_changes_nothing():
    out = apply("partial_corruption", level=0.0)

    assert out.entities_affected == 0
    assert out.df.to_csv(index=False) == panel().to_csv(index=False)


def test_duplicate_entity_periods_adds_rows():
    out = apply("duplicate_entity_periods", level=0.1)

    assert len(out.df) == len(panel()) + out.rows_affected
    assert out.df.duplicated([*KEY, TIME]).any()


def test_missing_entity_keys_blanks_the_key():
    out = apply("missing_entity_keys", level=0.1)

    assert out.df["uid"].isna().sum() == out.rows_affected
    assert len(out.df) == len(panel())


def test_missing_time_values_blanks_the_period():
    out = apply("missing_time_values", level=0.1)

    assert out.df["period"].isna().sum() == out.rows_affected


def test_panel_attrition_drops_later_rows_for_chosen_entities():
    out = apply("panel_attrition", level=0.5)

    assert len(out.df) == len(panel()) - out.rows_affected
    assert entities(out.df) == entities(panel())


def test_period_gaps_deletes_rows():
    out = apply("period_gaps", level=0.1)

    assert len(out.df) == len(panel()) - out.rows_affected


def test_invariant_column_removal_removes_invariants_and_keeps_the_key():
    out = apply("invariant_column_removal", level=2)

    assert out.key == KEY
    assert not {"region", "birth_year"} <= set(out.df.columns)
    assert {"uid", "period", "total", "score"} <= set(out.df.columns)


def test_feature_poor_panel_keeps_the_key_and_a_few_varying_columns():
    out = apply("feature_poor_panel", level=1)

    assert out.key == KEY
    assert set(out.df.columns) == {"uid", "period", "total"}
    assert "region" not in out.df.columns


# --------------------------------------------------------------------------
# a broken-key corruption has to break something
# --------------------------------------------------------------------------

BREAKS_THE_KEY = [
    "positional_rekey",
    "within_period_shuffle",
    "entity_merge",
    "entity_split",
    "partial_corruption",
]


@pytest.mark.parametrize("name", BREAKS_THE_KEY)
@pytest.mark.parametrize("seed", range(4))
def test_a_broken_key_corruption_changes_rows_at_its_smallest_level(name, seed):
    """A case that changed nothing is not a broken key, and scoring one as a
    miss or a catch corrupts the rate it feeds."""
    smallest = {"entity_merge": 0.01, "entity_split": 0.01, "partial_corruption": 0.01}
    out = apply(name, level=smallest.get(name, 1.0), seed=seed)

    assert out.rows_affected > 0
    assert out.changed_anything


@pytest.mark.parametrize("seed", range(4))
def test_a_small_partial_corruption_moves_every_row_it_selected(seed):
    """The labels are deranged, so a selected entity never keeps its own."""
    out = apply("partial_corruption", level=0.01, seed=seed)
    before, after = panel()["uid"].to_numpy(), out.df["uid"].to_numpy()

    assert out.entities_affected >= 2
    assert (before != after).sum() == out.rows_affected


def test_derangement_leaves_nothing_in_place():
    rng = rng_for("d", "c", 1.0, 0)
    block = np.arange(12).reshape(-1, 1)

    for _ in range(20):
        out = C._derange(block, rng)
        assert not (out == block).all(axis=1).any()


def test_derangement_of_a_single_row_is_impossible():
    assert C._derange(np.arange(1).reshape(-1, 1), rng_for("d", "c", 1.0, 0)) is None


def test_pick_respects_a_minimum():
    """Rounding 1% of a small panel gives one entity, and one entity cannot be
    shuffled or merged with anything."""
    values = np.arange(46)

    assert len(C._pick(values, 0.01, rng_for("d", "c", 0.01, 0), minimum=2)) == 2
    assert len(C._pick(values, 0.0, rng_for("d", "c", 0.0, 0), minimum=2)) == 0


@pytest.mark.parametrize("seed", range(4))
def test_entity_split_cuts_inside_each_entitys_own_history(seed):
    """A cut taken from the panel's periods can fall after everything a short
    entity was observed in, and then the split moves nothing."""
    out = apply("entity_split", level=0.05, seed=seed)

    assert out.entities_affected > 0
    assert out.rows_affected >= out.entities_affected


# --------------------------------------------------------------------------
# the corruption list and the protocol agree
# --------------------------------------------------------------------------


def protocol() -> dict:
    return json.loads((MANIFEST.parents[1] / "protocol" / "protocol.json").read_text())


def test_every_protocol_corruption_is_implemented():
    declared = {test["id"] for test in protocol()["corruption_tests"]}

    assert declared == set(CORRUPTIONS)


def test_every_corruption_has_a_recorded_expectation():
    assert set(EXPECTATION) == set(CORRUPTIONS)


def test_every_protocol_corruption_declares_levels():
    for test in protocol()["corruption_tests"]:
        assert test["levels"], f"{test['id']} declares no levels"


def test_no_profile_can_select_held_out_data():
    """The gate that matters most: a profile that named the held-out split
    would spend it on the first run."""
    for name, profile in PROFILES.items():
        assert "held_out" not in profile["roles"], name
