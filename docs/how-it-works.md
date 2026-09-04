# How it works

## The problem

A panel dataset asserts that each row belongs to an entity observed repeatedly
over time. Almost nothing verifies that assertion. When it is false, the failure
is silent: `groupby(entity).shift()` still returns a column, a GRU still trains,
grouped cross-validation still splits. The numbers are just meaningless.

Common ways the assertion breaks:

- Rows joined by position across exports that were sorted differently
- A sequence number reused between periods
- An ID that is stable in the source system but not in the extract
- A join that silently fanned out

## Key validation

A correct entity key reveals structure an incorrect one cannot.

**Invariants.** Some attributes cannot change for a real entity: a birth date,
an account opening timestamp, a species. Under the correct key they hold still
within an entity. Under a wrong key they flicker.

**Counters.** Some measures only accumulate: lifetime totals, visit counts.
Under the correct key their within-entity differences are non-negative. Under a
wrong key they wander up and down.

Neither property is known in advance, and asking users to declare them defeats
the purpose. So `paneldx` measures how much of this structure a candidate key
reveals, then compares it against a null.

### The null

Take the entity labels and permute them **within each period**. This preserves
the panel's shape exactly, the same number of entities and the same rows per
period, while destroying any true correspondence between rows. It is the
distribution a fabricated key is drawn from.

A column counts as evidence only if the key explains it *and* the null does not.
That second half matters: a column that barely varies looks invariant under any
labelling, and would otherwise inflate every key's score equally.

### Share, not count

The verdict uses the **share** of columns explained rather than the raw number.

This distinction decides the headline case. A key built from row position in a
table sorted by rank explains the two columns that drive the sort order, and
nothing else. A genuine key explains most of the table. Counting columns, both
look like they found something. Counting the share, the separation is 7% against
45%.

| `evidence_frac` | Verdict |
|-----------------|---------|
| ≥ 0.40 | `pass` — supported by the data |
| 0.15 to 0.40 | `warn` — weak, inspect the listed columns |
| < 0.15 | `inconclusive` — too little support to judge |

Note the last row. A low share is **not** a rejection: it means the panel did
not supply enough for the key to explain, which is a statement about the data
rather than about the key. Produc is the standing example — 48 named US states
observed over 17 years, unambiguously correct, and only one of nine columns
constant within a state.

### The invariance floor

One extra rule. A key that holds **nothing** still, whose invariance rate
matches the null, is `inconclusive` regardless of how many counters it explains
— the comparison carried no information, so the share it produced cannot be
trusted either.

Counters alone cannot support a key. Ranking rows by a column that grows over
time makes the *i*-th ranked row's value grow too, so the key inherits that
column's monotonicity from the sort order rather than from any entity. Real
entities always have something that persists.

### Getting to `fail`

`fail` means the data contradicts the key, and there are exactly three ways to
reach it:

1. **Duplicate entity-period cells** above `duplicate_cell_rate`. One entity
   cannot hold two values in one period.
2. **A declared invariant that changes.** Pass `invariant_cols=["birth_date"]`
   and a key under which birth dates move is contradicted.
3. **A declared counter that falls.** Pass `monotone_cols=["total_visits"]` and
   a key under which a lifetime total drops is contradicted.

Two and three are domain knowledge, and they are the reason the parameters
exist. Without them the tool can only say how much the data supports the key;
with them it can say the data rules the key out.

## Discovery

With no key supplied, `discover_keys` tries every combination of up to
`max_columns` columns.

Individual columns are not filtered by cardinality. Real keys often pair a coarse
column with a fine one, a four-valued specialty with a timestamp, and dropping
the coarse half loses the key. Only per-row-unique columns are excluded, since
they make every row its own entity.

Shape is screened before scoring, because screening is far cheaper: a candidate
must appear at most once per period and leave enough entities with enough
observations to measure a rate.

Ranking discounts explanatory power by coverage. A key specific enough to
fragment the panel into slivers is not useful even when every sliver looks
clean. Ties break toward the finer partition, since two keys can score alike
while one quietly merges entities that share a value.

## The three traps

Key validation answers whether within-entity arithmetic is meaningful. These
answer whether the resulting numbers will mislead you.

### Cumulative features

Lifetime totals barely move between periods, so a target built from them is
near-perfectly autocorrelated. A model fitted to it reports excellent R² for
restating its own inputs. `detect_counters` flags them along with their lag-1
autocorrelation. Difference them into per-period flows.

### Target composition

When the target is computed from columns that are also features, the model is
not predicting, it is recovering arithmetic.

`target_leakage` fits least squares on half the rows and scores the other half.
The model is deliberately linear: the point is not to predict the target well,
it is to show no prediction was ever required. A held-out R² above 0.99 means
the target is a deterministic function of its features; above 0.90 means it is
largely reconstructible and worth checking how it was built.

### Missing naive baseline

On autocorrelated panels, carrying the last value forward is often unbeatable.
`persistence_baseline` scores it so a model always has something honest to beat.

## Why order matters

These checks are not independent, and running one alone can mislead.

A broken key does not only corrupt features. It disarms the baseline. Under a
fabricated key the carry-forward forecast compares unrelated entities, so it
scores badly and looks useless. Nobody then thinks to compare a model against
it. Under a well-supported key the same baseline is close to unbeatable.

On the dataset that motivated this package:

| Key used | Persistence MAE | R² |
|----------|-----------------|-----|
| Positional key | 0.4717 | 0.191 |
| Best-supported candidate key | 0.0320 | 0.971 |

The published model scored 0.0942. Against the positional key's baseline it
looked strong. Against the candidate key's baseline it lost by a factor of 2.9.
These figures come from a paneldx audit carried out after the 2025 paper was
published; they were not reported in the paper.

This is why `audit()` establishes the key first and reports every other result
underneath it.

## Limits

The method is a consistency check, not a proof. A passing verdict says the data
is consistent with the key, not that the key is correct.

Tolerances exist because real keys collide, so a key that accidentally merges a
couple of entities can score like a clean one. Leakage detection is linear, so a
target built from its features by a non-linear rule can slip through. A high
leakage score is strong evidence; a low one is not a clearance.

## Policies

Every threshold lives in `paneldx.policy`. `KeyValidationPolicy` holds the
tolerances and minimum sizes for key validation and discovery;
`TrapPolicy` holds the counter, leakage and baseline cut-offs. Pass a modified
policy to `validate_key`, `discover_keys`, `detect_counters`,
`target_leakage`, `persistence_baseline`, or to `audit` as `key_policy` and
`trap_policy`. The defaults and their calibration status are described in
[limitations.md](limitations.md).

## Cadence

Two observations of an entity are adjacent when their periods are exactly one
`period_step` apart. The step is never inferred from the data: a panel observed
only at periods 1 and 100 has no adjacent pairs, not a step of 99. Numeric
periods default to a step of 1; datetime periods need a declared pandas
frequency such as `"QS"` or `"MS"`.
