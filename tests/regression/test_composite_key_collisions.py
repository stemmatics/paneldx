"""Compound key values are grouped as they are, never joined as strings."""

import pandas as pd

from paneldx import entity_key, validate_key
from tests.factories import make_panel


def test_separator_and_type_collisions_stay_distinct():
    df = pd.DataFrame({"a": ["x\x1fy", "x", 1, "1"], "b": ["z", "y\x1fz", 2, 2]})
    assert entity_key(df, ("a", "b")).nunique() == 4


def test_null_components_stay_distinct():
    df = pd.DataFrame({"a": [None, "x", "x"], "b": ["x", None, "x"]})
    assert entity_key(df, ("a", "b")).nunique() == 3


def test_nonunique_index_matches_reset_index():
    df = make_panel(n_entities=40)
    dup_index = df.set_axis([7] * len(df))
    a = validate_key(dup_index, "uid", "period")
    b = validate_key(df, "uid", "period")
    assert (a.status, a.n_entities, a.invariant_cols) == (b.status, b.n_entities, b.invariant_cols)
