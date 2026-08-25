# Interpreting results

What each verdict means and what to do about it.

## Key verdicts

### `supported by the data`

The key resolves 40% or more of the table into invariants or counters, well
above what shuffled labels achieve. Within-entity arithmetic is safe.

This is not a proof. If domain knowledge says the key is wrong, trust domain
knowledge.

### `weak - inspect manually`

Between 15% and 40% explained. Look at `invariant_cols` and `monotone_cols` on
the report and ask whether those columns *should* behave that way for a real
entity.

Common causes:

- The table is mostly volatile measurements with few stable attributes
- The key is correct but the extract dropped the columns that would prove it
- The key is nearly correct and merges a small number of entities

If the listed invariants are things like a birth date or a registration
timestamp, the key is probably fine and the table is just thin.

### `NOT SUPPORTED - within-entity quantities are unsafe`

Below 15%. Every lag, difference, trajectory and grouped split derived from this
key is unreliable.

Do not model on it. Run `discover_keys` and look at what comes back. If a
candidate scores well and makes sense, rebuild the panel on it. If nothing
scores well, the data may be repeated cross-sections rather than a panel, in
which case within-entity analysis was never available.

### `NOT SUPPORTED - nothing stays constant within an entity`

A stronger rejection. The key explains no invariants at all, and its invariance
rate is indistinguishable from shuffled labels.

This is the signature of a key built from row position or rank. Any monotonicity
it does show comes from the sort order, not from entities. Treat it as
fabricated.

### `invalid - key repeats within a period`

The key appears more than once in the same period, so it does not identify a
single observation. Usually a missing column in a compound key, or a join that
fanned out.

### `too few entities to judge`

Fewer than 20 entities with at least two observations. Not a verdict, an
abstention.

## Trap verdicts

### Cumulative counters detected

The listed columns are lifetime totals. Two consequences:

1. A target built from them is autocorrelated by construction, so a model will
   score well for restating its inputs.
2. As features they carry level information, not period information.

Difference them into flows before modelling:

```python
df["new_visits"] = df.groupby(entity)["total_visits"].diff().clip(lower=0)
```

Keep the level too if it is genuinely informative, but do not let it be the only
thing the model sees.

### Fail (R² ≥ 0.99)

The target is nearly deterministic under linear reconstruction. A model
fitted to it can score near-perfectly by restating its inputs.

Look at `top_contributors`. Usually the target is a composite index and the
named columns are its own components. Either drop those components from the
feature set, or use a target that is not computed from them.

### Warn (R² 0.90 to 0.99)

Strongly reconstructible. Sometimes legitimate, when features are genuinely
strong predictors. Often not, when the target shares components with them.

Check how the target was constructed. If any feature appears in its definition,
that is leakage regardless of the score.

Note the check is linear, so a low score does not clear you. A target built from
its features by a non-linear rule can pass.

### Persistence baseline

| R² | Meaning |
|----|---------|
| ≥ 0.95 | Carry-forward explains nearly all variance. Report your model against it, not against zero. |
| 0.70 to 0.95 | Strong baseline. Beating it is the bar. |
| < 0.70 | Real movement to predict. |

An R² of 0.97 does not mean the target is unpredictable. It means the naive
forecast already achieves 0.97, so a model at 0.98 has captured very little.
Report the improvement over persistence, not the raw score.

If the baseline looks weak, check the key verdict first. A broken key makes
carry-forward compare unrelated entities, which makes it look useless when it is
not.

## Working through a report

1. **Key first.** If it fails, nothing below it is trustworthy. Fix and rerun.
2. **Leakage next.** If the target is inside its features, no metric means
   anything until that is resolved.
3. **Counters.** Difference them, then rerun and see whether the persistence
   baseline changed.
4. **Baseline last.** Whatever it scores is the number your model has to beat.
