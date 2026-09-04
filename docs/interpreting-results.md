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

### `INCONCLUSIVE - too little is explained to support the key`

Below 15%. The data did not supply enough for the key to explain.

This is **not** a rejection, and reading it as one is the mistake 0.5.0 was
written to prevent. A correct key on a panel of purely time-varying
measurements lands here, and so does a broken one. What it tells you is that
within-entity quantities are *unverified*, not that they are wrong.

What to do: run `discover_keys` and see whether anything scores better. Declare
what you know with `invariant_cols` and `monotone_cols` — a single column that
should not move is often enough to settle the question in either direction. If
nothing in the table can ever support a key, the data may be repeated
cross-sections rather than a panel, in which case within-entity analysis was
never available.

### `INCONCLUSIVE - the key cannot be told apart from shuffled labels`

The key explains no invariants at all, and its invariance rate matches what you
get by shuffling the labels within each period.

This is the signature of a key built from row position or rank. Any monotonicity
it shows comes from the sort order rather than from entities. It is also what a
panel with no stable attributes looks like under a perfectly good key, which is
why the verdict abstains rather than rejects. Declare an invariant column to
tell the two apart: if one exists and the key breaks it, the verdict becomes
`fail`.

### `contradicted - <column> was declared invariant but changes`

The key is ruled out. You said a column cannot change within an entity, and
under this key it does. Reported as `fail`, with reason
`declared_invariant_broken`.

### `contradicted - <column> was declared monotone but falls`

As above for a declared counter. Reason `declared_monotone_broken`.

### `invalid - key repeats within a period`

The key appears more than once in the same period, so it does not identify a
single observation. Usually a missing column in a compound key, or a join that
fanned out. Reported as `fail`, with reason `duplicate_entity_period`.

### `too few entities to judge`

Fewer than 20 entities with at least two observations. Not a verdict, an
abstention.

### Reason codes

Every report carries a `reason` alongside its status, so a caller can branch on
the cause without matching on wording:

| Reason | Status |
|---|---|
| `supported` | `pass` |
| `weak_support` | `warn` |
| `insufficient_evidence` | `inconclusive` |
| `duplicate_entity_period` | `fail` |
| `declared_invariant_broken` | `fail` |
| `declared_monotone_broken` | `fail` |

The three `fail` reasons are the complete list. If a report says `fail`, one of
them holds.

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
