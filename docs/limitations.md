# Limitations

`paneldx` is a heuristic diagnostic. It reports whether the available evidence
supports, contradicts, or cannot evaluate a proposed panel structure. It never
establishes that a key is correct.

## No accuracy rate has been measured

This is the limitation that governs all the others. There is no measured
accuracy figure for `paneldx` that may be quoted as one, and none is claimed
anywhere in this project.

Every panel the tool has been run against is **development or calibration
data**: the synthetic generator the rules were written on, four public panels
in use before the thresholds were chosen, six calibration panels one threshold
was fitted on, and one restricted workbook whose true entity key is unknown.
Results on data used to build or tune a method are not evidence about that
method.

The [held-out split](../validation/protocol/protocol.md) — `males`,
`usseatbelts`, `municipalities`, `airfare`, `jtrain`, `murder` — is
**registered and not evaluated**. Each file was downloaded once and its shape
and checksum recorded, which is what makes the registration checkable;
`paneldx` has not been run on any of them and no verdict for any of them
exists. The downloader refuses to fetch them without an explicit flag, and no
benchmark profile can select them.

The calibration is exploratory rather than preregistered: the grid preceded the
run, but it was not registered where a third party could check it, and the
results have been seen. Preregistration applies to the held-out evaluation,
which has not happened.

## What the benchmark shows, and what it is not

`python -m validation.harness.cases --profile development` runs 3,480 cases:
ten public panels, twelve corruption procedures, ten seeds, and the documented
key of each panel uncorrupted. Every case that claims to break a key is checked
to have changed rows; levels a panel cannot express are recorded and excluded.
The full output is in [`validation/results/`](../validation/results/), failures
included.

**These are development diagnostics, not validation estimates.** Every recorded
run used `n_shuffles = 3`, the cheap library default. The protocol requires
`n_shuffles = 200` for any number published as a validation result, and that
profile has not been run. Read the figures below as a direction and a rough
magnitude, and do not quote them as rates.

| Measure | 0.4.0 | 0.5.0 |
|---|---|---|
| Documented keys reported `fail` | 4 of 10 | 0 of 10 |
| Correct keys with degraded evidence reported `fail` | 741 of 1,827 | 0 of 1,827 |
| Duplicate entity-period cells above tolerance detected | 320 of 320 | 320 of 320 |
| Broken keys accepted as `pass` or `warn` | 13.3% | 12.9% |
| **Procedure-weighted inconclusive rate** | **25.6%** | **69.9%** |

Read the last two rows together. Acceptance of broken keys barely moved; what
changed is that the procedure-weighted inconclusive rate increased from 25.6%
to 69.9%. A diagnostic can drive its error rate to zero by declining to answer,
so that rate is published beside the error rates, under the same weighting and
with the same interval — 0.53 to 0.87 over ten families.

It is not a raw share of cases. Weighting every case equally, 2,139 of 3,457
scored cases are `inconclusive`, or 61.9%. The two differ because procedures
declare different numbers of levels, and the weighted figure is the one the
protocol defines.

Both rates average each corruption procedure within a dataset before averaging
datasets and families. Weighting cases equally instead gives 15.8% acceptance,
which mostly reflects that `partial_corruption` declares six levels and
`positional_rekey` declares one. Both are recorded; only the first is a rate.

It is also not one number:

| Corruption procedure | Runs | Accepted |
|---|---:|---:|
| `within_period_shuffle` | 100 | 0.0% |
| `entity_merge` | 300 | 10.0% |
| `positional_rekey` | 10 | 10.0% |
| `partial_corruption` | 600 | 14.3% |
| `entity_split` | 300 | 30.0% |

Splitting one entity into two is the weakest case, and it is the one a
re-identification pass produces. Both halves keep a coherent history, so the
panel still looks well keyed; what is lost is that they are the same entity.

Most of the acceptance comes from the smallest corruptions — merging 1% of
entities, shuffling 1% of labels — which leave a panel's evidence almost
intact. A diagnostic that caught those would also reject correct keys.

[`validation/results/development/v0.5.0/comparison.md`](../validation/results/development/v0.5.0/comparison.md)
records what changed against 0.4.0 on the same 3,480 cases: 741 false
rejections of correct keys became zero, four documented keys stopped being
rejected, and acceptance of broken keys fell from 219 cases to 207. 1,313
verdicts changed in all, every one of them `fail` or `warn` becoming
`inconclusive`.

## Thresholds are provisional

Every verdict depends on the values in `paneldx.policy`:

| Policy field | Default | Used for |
|---|---|---|
| `invariant_violation_rate` | 0.02 | share of entities allowed to vary in an "invariant" column |
| `monotone_violation_rate` | 0.05 | share of within-entity steps allowed to decrease in a "counter" |
| `duplicate_cell_rate` | 0.01 | share of entity-period cells with more than one row before the key is invalid |
| `minimum_null_gap` | 0.10 | how far invariance must beat the shuffled reference (**calibrated**) |
| `supported_evidence_fraction` | 0.40 | share of usable columns explained for `pass` |
| `weak_evidence_fraction` | 0.15 | share of usable columns explained for `warn` |
| `minimum_entities` | 20 | below this every key check is `inconclusive` |
| `deterministic_r2` / `reconstructible_r2` | 0.99 / 0.90 | leakage `fail` / `warn` |
| `strong_persistence_r2` / `moderate_persistence_r2` | 0.95 / 0.70 | baseline `warn` levels |

One of these is calibrated and the rest are not. `minimum_null_gap` was fitted
on the calibration split alone, over the 81-point grid frozen in
[`validation/protocol/calibration_grid.json`](../validation/protocol/calibration_grid.json)
before the calibration ran; it moved from 0.05 to 0.10, cutting acceptance of
broken keys from 0.211 to 0.196 across six families in exchange for 1.2 points
more `inconclusive`. The 0.4.0 values are frozen inside the grid rather than
read from the running policy, so a later change to a default cannot rewrite
what this was measured against. The full ranking is in
[`validation/results/calibration/v0.5.0/calibration.json`](../validation/results/calibration/v0.5.0/calibration.json).

Every other threshold was chosen while developing the rules on synthetic
panels, and the grid left them where they were. Treat a verdict near one of
those as a prompt to look, not as a decision.

### What the public panels show

`tests/validation` runs the documented key of four public panels through
`validate_key` and records what the tool reports. The datasets are described in
[`validation/manifests/datasets.json`](../validation/manifests/datasets.json); the recorded
verdicts are in `tests/validation/expected_results.json`, and they are
regression expectations, not scientific truth.

**These four panels are development data, not external validation.** Earlier
versions of this page called them external. That was wrong: all four were in
use while the rules and thresholds were being chosen, so agreement with them is
expected and proves little, and disagreement is the more informative half. They
are here to make a change in behaviour visible, not to score the tool.

As of this version:

- **Grunfeld** (10 firms) and **Gasoline** (18 countries): `inconclusive`.
  Both sit below the 20-entity minimum. Many classic econometrics panels do.
- **EmplUK** (140 firms): `warn`. One invariant column (`sector`) out of five.
- **Produc** (48 US states, 17 years): `inconclusive`. Only `region` is constant
  within a state, 1 of 9 usable columns, under the weak threshold. The key is
  correct — the entity column holds state names, and the panel is a clean
  48 x 17. Under 0.4.0 this was `fail`, a false rejection; 0.5.0 reports the
  absence of evidence as an absence of evidence. It was not fixed by lowering a
  threshold, and it is deliberately not `pass`: nothing in the panel supports
  the key either.

Produc illustrates the main weakness of evidence-share scoring: a panel whose
columns are all genuinely time-varying offers little for the key to explain,
and a correct key can score like a broken one. The number of columns a key
explains is evidence *for* a key; a low share is not equally strong evidence
against it. Since 0.5.0 the verdicts say so — which removes the false
rejection, and replaces it with an honest inability to decide. Declaring an
invariant or a counter is how a caller resolves that.

### Sensitivity

[threshold-selection.md](threshold-selection.md) is generated by
`scripts/threshold_sensitivity.py` and shows how each panel's verdict moves as
one threshold at a time is varied. Every case in it is development data, so it
is a sensitivity record and not a calibration. Two results stand out. Lowering
`minimum_entities` to 10 does not rescue Grunfeld or Gasoline: both then
report `fail`, because their columns are all time-varying. And lowering
`minimum_null_gap` to 0.02 lets every positional key through as `warn`, so the
stability rule is doing most of the work in rejecting broken keys.

## The shuffled reference is a heuristic

Key validation compares each column's within-entity behaviour against the same
column after entity labels are shuffled within each period. With two or three
shuffles this is a sanity reference, not a permutation test: there are no
p-values, no confidence intervals, and no controlled error rate. The defaults
are deliberate — the check has to be cheap enough to run before training — but
the protocol requires 200 shuffles for any number published as a validation
result, because a single draw is not an estimate.

## The leakage screen is linear and row-random

`target_leakage` fits ordinary least squares on a random half of the rows and
scores the other half. It detects arithmetic composition of the target from its
features. It does not detect non-linear composition, it is not entity-grouped
predictive validation, and repeated measurements of one entity can land on both
sides of the split. With `features=None` it screens every numeric column, which
may include columns no model used. Coefficient rankings are unstable under
correlated features.

## Cadence must be declared

The persistence baseline scores only pairs exactly one `period_step` apart.
Numeric periods default to a step of 1; datetime periods are `inconclusive`
until a pandas frequency is declared; string periods are unsupported. An entity
observed twice in one period makes the baseline `inconclusive`, because there
is no single value to carry forward and choosing one would be an undeclared
aggregation.

## Counters

A "counter" is a non-negative numeric column that moves in at least half of
its within-entity steps and decreases in at most 5% of them. That describes
accumulation, not size of movement: a counter may double every period.

## `inconclusive` is now common

The 0.5.0 semantics move a large share of verdicts from `fail` to
`inconclusive`: 1,313 of 3,480 benchmark cases, taking the procedure-weighted
inconclusive rate from 25.6% to 69.9%. That is the intended direction,
and it has a cost. A tool that abstains often is less useful than one that
decides, and a reader who treats `inconclusive` as "probably fine" has
misunderstood it exactly as badly as one who treated the old `fail` as "proven
broken".

Two things reduce it. Declaring `invariant_cols` or `monotone_cols` gives the
check something it can contradict. And a panel with more stable attributes —
more of the columns that describe the entity rather than the period — gives the
key more to explain.

## Weak keys

Counters and the persistence baseline run only under a key with `pass`
status. `allow_weak_key=True` extends this to `warn`; the key's own warning
still stands in the findings.
