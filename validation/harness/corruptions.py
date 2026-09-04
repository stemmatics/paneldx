"""Reproducible corruption procedures for a correctly keyed panel.

Most of these use seeded randomness rather than a fixed transformation, so they
are reproducible rather than deterministic: the same (dataset, corruption,
level, seed) gives the same panel, and a different seed gives a different one.

Two rules hold throughout:

  * **The input is never modified**, so one case cannot contaminate the next.
  * **Randomness comes only from the passed generator**, which `rng_for`
    derives from the case identity, so a run rebuilds from its record.

A corruption returns the frame, the key to validate it under, and a count of
what it touched. Provenance is recorded by the runner.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

# Column names the corruptions introduce. Leading underscores keep them out of
# the way of real panel columns.
POSITIONAL_KEY = "_paneldx_positional_id"
SPLIT_SUFFIX = "__split"


@dataclass(frozen=True)
class Corrupted:
    """One corrupted panel, with what it took to make it."""

    df: pd.DataFrame
    key: list[str]
    time_column: str
    entities_affected: int
    rows_affected: int
    # What a column-based corruption actually managed, against what was asked.
    # A panel with two invariant columns cannot express "remove three", and the
    # frame it returns is identical to the level below.
    columns_changed: int = 0
    achieved_level: int | float | None = None

    @property
    def changed_anything(self) -> bool:
        return self.rows_affected > 0 or self.columns_changed > 0


def rng_for(dataset: str, corruption: str, level: float, seed: int) -> np.random.Generator:
    """A generator determined entirely by the case identity.

    crc32 rather than hash(): Python's string hashing is salted per process, so
    a run seeded from it would not reproduce tomorrow.
    """
    tag = f"{dataset}|{corruption}|{level}".encode()
    return np.random.default_rng(np.random.SeedSequence([seed, zlib.crc32(tag)]))


def _entities(df: pd.DataFrame, key: list[str]) -> pd.Series:
    return df.groupby(key, sort=False, dropna=False).ngroup()


def _pick(
    values: np.ndarray, level: float, rng: np.random.Generator, minimum: int = 1
) -> np.ndarray:
    """Choose round(level * n) distinct items, never fewer than `minimum`.

    `minimum` exists because rounding a small fraction of a small panel gives
    zero or one, and a corruption that touches one entity often changes
    nothing: a single label cannot be shuffled with itself, and a single entity
    cannot be merged with anything.
    """
    n = len(values)
    take = int(round(level * n))
    if level > 0:
        take = max(take, minimum)
    take = min(take, n)
    return rng.choice(values, size=take, replace=False) if take else np.empty(0, values.dtype)


def _derange(block: np.ndarray, rng: np.random.Generator, attempts: int = 32) -> np.ndarray | None:
    """Permute rows so that none keeps its original position.

    A plain shuffle can return the identity, or leave most labels in place, and
    the case is then recorded as a broken key that was never broken. A
    derangement makes the corruption's effect equal to its stated size.
    """
    n = len(block)
    if n < 2:
        return None
    positions = np.arange(n)
    for _ in range(attempts):
        order = rng.permutation(n)
        if not np.any(order == positions):
            return np.asarray(block[order])
    # A single rotation is a derangement for any n >= 2, so this terminates.
    return np.asarray(block[np.roll(positions, 1)])


def _sortable_column(df: pd.DataFrame, key: list[str], time_column: str) -> str | None:
    for column in df.columns:
        if column in key or column == time_column:
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            return column
    return None


def positional_rekey(df, key, time_column, level, rng) -> Corrupted:
    """Sort each period by a value column, then key on within-period position.

    This is the PopNet defect: position *i* is a different entity each period.
    """
    column = _sortable_column(df, key, time_column)
    if column is None:
        raise ValueError("positional_rekey needs a numeric column to sort within a period")
    out = df.sort_values([time_column, column], ascending=[True, False]).reset_index(drop=True)
    out[POSITIONAL_KEY] = out.groupby(time_column, sort=False).cumcount()
    out = out.drop(columns=key)
    return Corrupted(out, [POSITIONAL_KEY], time_column, _entities(df, key).nunique(), len(df))


def within_period_shuffle(df, key, time_column, level, rng) -> Corrupted:
    """Permute entity labels independently within each period."""
    return partial_corruption(df, key, time_column, 1.0, rng)


def partial_corruption(df, key, time_column, level, rng) -> Corrupted:
    """Deranged labels within each period, for a fraction of the entities.

    Unaffected entities keep their rows, so the panel degrades smoothly rather
    than jumping from intact to destroyed. At least two entities are always
    chosen: one cannot be shuffled with itself.
    """
    out = df.copy()
    labels = out[key].drop_duplicates()
    chosen = set(map(tuple, _pick(labels.to_numpy(), level, rng, minimum=2)))
    if not chosen:
        return Corrupted(out, list(key), time_column, 0, 0)

    affected = out[key].apply(tuple, axis=1).isin(chosen)
    rows = 0
    for _, index in out.loc[affected].groupby(time_column, sort=False).groups.items():
        # copy=True: pandas can hand back a read-only view, and the generator
        # refuses to shuffle one.
        block = out.loc[index, key].to_numpy(dtype=object, copy=True)
        deranged = _derange(block, rng)
        if deranged is None:
            continue
        out.loc[index, key] = deranged
        rows += len(index)
    return Corrupted(out, list(key), time_column, len(chosen), rows)


def entity_merge(df, key, time_column, level, rng) -> Corrupted:
    """Collapse pairs of distinct entities onto one label.

    A merge is what a join on a non-unique column does: two entities' histories
    become one, and every within-entity quantity mixes them.
    """
    out = df.copy()
    labels = out[key].drop_duplicates().to_numpy()
    chosen = _pick(labels, level, rng, minimum=2)
    if len(chosen) < 2:
        return Corrupted(out, list(key), time_column, 0, 0)

    as_tuple = out[key].apply(tuple, axis=1)
    rows = 0
    pairs = [(chosen[i], chosen[i + 1]) for i in range(0, len(chosen) - 1, 2)]
    for keep, absorb in pairs:
        mask = as_tuple == tuple(absorb)
        out.loc[mask, key] = list(keep)
        rows += int(mask.sum())
    return Corrupted(out, list(key), time_column, len(pairs) * 2, rows)


def entity_split(df, key, time_column, level, rng) -> Corrupted:
    """Split an entity's rows across two labels at a random period.

    This is a re-identification pass losing continuity halfway through: one
    entity becomes two shorter ones.
    """
    out = df.copy()
    for column in key:
        out[column] = out[column].astype(object)
    labels = out[key].drop_duplicates().to_numpy()
    chosen = _pick(labels, level, rng)
    if not len(chosen):
        return Corrupted(out, list(key), time_column, 0, 0)

    as_tuple = out[key].apply(tuple, axis=1)
    rows = 0
    split = 0
    for label in chosen:
        mask = as_tuple == tuple(label)
        # The cut comes from this entity's own periods, not the panel's: a
        # global cut can fall after everything the entity was observed in, and
        # then the split moves no rows at all.
        own = np.sort(out.loc[mask, time_column].dropna().unique())
        if len(own) < 2:
            continue
        cut = own[rng.integers(1, len(own))]
        late = mask & (out[time_column] >= cut)
        out.loc[late, key[0]] = f"{label[0]}{SPLIT_SUFFIX}"
        rows += int(late.sum())
        split += 1
    return Corrupted(out, list(key), time_column, split, rows)


def duplicate_entity_periods(df, key, time_column, level, rng) -> Corrupted:
    """Duplicate a share of entity-period rows.

    A structural contradiction rather than a shortage of evidence: one entity
    cannot have two values in one period.
    """
    out = df.copy()
    picked = _pick(np.arange(len(out)), level, rng)
    if not len(picked):
        return Corrupted(out, list(key), time_column, 0, 0)
    duplicated = out.iloc[np.sort(picked)]
    out = pd.concat([out, duplicated], ignore_index=True)
    return Corrupted(
        out, list(key), time_column, int(_entities(duplicated, key).nunique()), len(picked)
    )


def _blank(df, key, time_column, columns, level, rng) -> Corrupted:
    out = df.copy()
    for column in columns:
        out[column] = out[column].astype(object)
    picked = _pick(np.arange(len(out)), level, rng)
    if not len(picked):
        return Corrupted(out, list(key), time_column, 0, 0)
    touched = out.iloc[picked]
    entities = int(_entities(touched, key).nunique())
    out.iloc[picked, [out.columns.get_loc(c) for c in columns]] = np.nan
    return Corrupted(out, list(key), time_column, entities, len(picked))


def missing_entity_keys(df, key, time_column, level, rng) -> Corrupted:
    """Blank the entity key on a share of rows: those rows cannot be placed."""
    return _blank(df, key, time_column, list(key), level, rng)


def missing_time_values(df, key, time_column, level, rng) -> Corrupted:
    """Blank the time column on a share of rows."""
    return _blank(df, key, time_column, [time_column], level, rng)


def panel_attrition(df, key, time_column, level, rng) -> Corrupted:
    """Drop a share of entities out of the panel from a random period onwards."""
    out = df.copy()
    labels = out[key].drop_duplicates().to_numpy()
    chosen = _pick(labels, level, rng)
    if not len(chosen):
        return Corrupted(out, list(key), time_column, 0, 0)

    as_tuple = out[key].apply(tuple, axis=1)
    periods = np.sort(out[time_column].dropna().unique())
    drop = pd.Series(False, index=out.index)
    for label in chosen:
        cut = periods[rng.integers(1, len(periods))] if len(periods) > 1 else periods[0]
        drop |= (as_tuple == tuple(label)) & (out[time_column] >= cut)
    return Corrupted(
        out[~drop].reset_index(drop=True), list(key), time_column, len(chosen), int(drop.sum())
    )


def period_gaps(df, key, time_column, level, rng) -> Corrupted:
    """Delete rows at random, opening gaps in entity histories."""
    out = df.copy()
    picked = _pick(np.arange(len(out)), level, rng)
    if not len(picked):
        return Corrupted(out, list(key), time_column, 0, 0)
    dropped = out.iloc[picked]
    entities = int(_entities(dropped, key).nunique())
    keep = np.setdiff1d(np.arange(len(out)), picked)
    return Corrupted(
        out.iloc[keep].reset_index(drop=True), list(key), time_column, entities, len(picked)
    )


def _invariant_columns(df, key, time_column) -> list[str]:
    entity = _entities(df, key)
    grouped = df.groupby(entity, sort=False)
    return [
        column
        for column in df.columns
        if column not in key
        and column != time_column
        and float((grouped[column].nunique(dropna=False) > 1).mean()) <= 0.02
    ]


def invariant_column_removal(df, key, time_column, level, rng) -> Corrupted:
    """Drop the columns that are invariant within an entity, one at a time.

    The key stays correct; what is removed is the evidence for it. A panel with
    fewer invariant columns than the level asks for returns the frame the level
    below already produced, so the achieved count is reported and the runner
    drops the case rather than counting the same panel twice.
    """
    invariant = _invariant_columns(df, key, time_column)[: int(level)]
    return Corrupted(
        df.drop(columns=invariant),
        list(key),
        time_column,
        0,
        0,
        columns_changed=len(invariant),
        achieved_level=len(invariant),
    )


def feature_poor_panel(df, key, time_column, level, rng) -> Corrupted:
    """Keep the correct key and reduce the panel to a few time-varying columns.

    Produc's problem, made reproducible: a well-keyed panel that offers almost
    nothing for the key to explain. A `fail` here is a false rejection.
    """
    invariant = set(_invariant_columns(df, key, time_column))
    varying = [c for c in df.columns if c not in key and c != time_column and c not in invariant]
    kept = varying[: int(level)]
    dropped = len(df.columns) - len([*key, time_column, *kept])
    return Corrupted(
        df[[*key, time_column, *kept]].copy(),
        list(key),
        time_column,
        0,
        0,
        columns_changed=dropped,
        achieved_level=len(kept),
    )


Corruption = Callable[..., Corrupted]

CORRUPTIONS: dict[str, Corruption] = {
    "positional_rekey": positional_rekey,
    "within_period_shuffle": within_period_shuffle,
    "entity_merge": entity_merge,
    "entity_split": entity_split,
    "partial_corruption": partial_corruption,
    "duplicate_entity_periods": duplicate_entity_periods,
    "missing_entity_keys": missing_entity_keys,
    "missing_time_values": missing_time_values,
    "panel_attrition": panel_attrition,
    "period_gaps": period_gaps,
    "invariant_column_removal": invariant_column_removal,
    "feature_poor_panel": feature_poor_panel,
}

# Corruptions whose output does not depend on the generator. Running them under
# ten seeds would record ten identical rows and inflate every denominator.
DETERMINISTIC = frozenset({"invariant_column_removal", "feature_poor_panel", "positional_rekey"})

# Corruptions that leave the key correct: a `fail` on these is a false
# rejection, not a catch.
KEY_STAYS_CORRECT = frozenset(
    {
        "missing_entity_keys",
        "missing_time_values",
        "panel_attrition",
        "period_gaps",
        "invariant_column_removal",
        "feature_poor_panel",
    }
)
