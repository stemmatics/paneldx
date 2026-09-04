# Validation protocol

**Protocol version 2.0.0 — frozen 2026-09-04. Baseline: paneldx 0.4.0.**

Machine-readable form: [protocol.json](protocol.json). Dataset facts:
[datasets.json](../manifests/datasets.json).

This protocol was written before calibration and held-out evaluation. Existing
public and synthetic panels are classified as development data: they had
already been examined, and the current thresholds were chosen with them in
view, so nothing here can be read as an out-of-sample result about them. What
this document fixes in advance is the work that has not happened yet — which
data may be used to answer the validation question, what would count as a
wrong answer, and how a rate may be computed — so that future results cannot
be reshaped by whatever the tool happens to report.

**Status.** Version 1.0.0 was frozen on 2026-09-04 before calibration. Version
1.1.0 then populated the calibration and held-out splits. Calibration was run
against version 1.1.0. Versions 1.2.0 to 2.0.0 record amendments made after
calibration but before any held-out evaluation. The original freeze date is
retained, and all amendments are listed in section 9.

Release 0.4.1 altered no threshold, no status rule and no verdict. Release
0.5.0 changes what the verdicts mean and, on the strength of the calibration
recorded in section 6, one threshold. Every case whose verdict moved is listed
in `validation/results/development/v0.5.0/comparison.md`.

---

## 1. The validation question

> Given a longitudinal table and a proposed entity key, does `paneldx` reach
> the right conclusion about whether the rows under one key value describe one
> entity over time?

Three answers count as right, and they are not interchangeable:

- The key is correct and `paneldx` does not reject it.
- The key is broken and `paneldx` rejects it.
- The evidence is too thin to decide and `paneldx` says so.

Two answers count as wrong:

- **False rejection.** A key that is known to be correct is reported `fail`.
- **False acceptance.** A key that is known to be broken is reported `pass` or
  `warn`.

Declining to answer is a third outcome, not a success. A diagnostic can drive
both error rates to zero by returning `inconclusive` on everything, so the
inconclusive rate is reported next to the error rates every time either is
reported.

Out of scope for this protocol: whether the counter, leakage and persistence
checks are individually accurate. Those are diagnostics whose ground truth is
not available for public panels. They are exercised by the unit and regression
suites, not measured here.

---

## 2. What "the correct key is known" means

A dataset may only be used to measure an error rate if its correct entity key
is established **independently of anything `paneldx` reports**. Three bases are
recognised, recorded per dataset as `correct_key_evidence.basis` in
[datasets.json](../manifests/datasets.json):

| Basis | Meaning | May be used for error rates |
|---|---|---|
| `documented` | Upstream documentation names the entity column, and the file matches the documented shape: the stated number of entities and periods, and no duplicate entity-period rows. | Yes |
| `constructed` | The panel was generated with a known key, or corrupted from one by a recorded transformation. | Yes |
| `unknown` | The key is a candidate, however well supported. | No |

Two things are deliberately excluded from this definition. A key is not
"correct" because `paneldx` gave it a `pass`; that is the claim under test.
And a key is not "correct" because it looks plausible; `Disease + Opening time`
in the PopNet workbook is the best-supported candidate found by search and is
recorded as `unknown`.

For the four public panels the basis is `documented`: the `plm` reference
manual names the entity column, and each downloaded file was checked to match
its documented shape (see `shape` in the manifest, verified against the exact
bytes named by the recorded sha256).

---

## 3. Dataset splits

Every dataset carries exactly one `role` in [datasets.json](../manifests/datasets.json).

### development

Panels used while writing the rules and choosing the thresholds. **Results on
development data are not evidence of accuracy** and may not be reported as an
error rate.

**Grunfeld, EmplUK, Produc and Gasoline.** All four were in use before this
protocol was written, and all four informed the current thresholds. Earlier
documentation called them "external"; that was wrong, and 0.4.1 corrects it.

### calibration

The only split on which thresholds may be fitted. **Used once, on
2026-09-04**, under the grid in `calibration_grid.json`; the result is
`results/calibration/v0.5.0/calibration.json`.

That calibration is **exploratory, not preregistered**. The grid was written
before the run, and the 0.4.0 threshold values it is measured against are
frozen inside it rather than read from the running policy, so a later change to
a default cannot rewrite what was compared. But it was not registered anywhere
a third party could check beforehand, and the results have since been seen.
Preregistration applies to the held-out evaluation, which has not happened.

| Dataset | Family | Panel |
|---|---|---|
| `cigar` | `baltagi_us_state_cigarettes` | 46 US states x 30 years |
| `crime` | `cornwell_trumbull_nc_crime` | 90 North Carolina counties x 7 years |
| `laborsupply` | `psid` | 532 individuals x 10 years |
| `parity` | `coakley_fuertes_smith_parity` | 17 countries x 104 quarters |
| `snmesp` | `alonso_borrego_arellano_spain_firms` | 738 Spanish firms x 8 years |
| `sumhes` | `penn_world_table_mark5` | 125 countries x 26 years |

`parity` has 17 entities, below `minimum_entities`, so it can only ever return
`inconclusive`. It is kept deliberately: a calibration set made only of panels
large enough to judge would never exercise the rule that refuses to judge.

Three candidates were checked and rejected, recorded in
`datasets.json` under `excluded_candidates`:

- **`Wages`** (plm) — the distributed CSV has no entity column and no time
  column; the panel index is implicit in row order. A key rebuilt from row
  position is the exact defect this tool detects, so it cannot supply ground
  truth.
- **`RiceFarms`** (plm) — carries `id` but no time column.
- **`Fatalities`** (AER) — same family as the held-out `usseatbelts`; both are
  US state-year traffic-fatality panels derived from FARS.

### held_out

Registered, and evaluated exactly once after the method is frozen.

| Dataset | Family | Panel |
|---|---|---|
| `males` | `nlsy_young_men` | 545 young men x 8 years |
| `usseatbelts` | `us_traffic_fatalities` | 51 US states x 15 years |
| `municipalities` | `swedish_municipalities` | 265 Swedish municipalities x 9 years |
| `airfare` | `us_dot_airline_fares` | 1,149 airline routes x 4 years |
| `jtrain` | `michigan_training_firms` | 157 Michigan firms x 3 years |
| `murder` | `us_state_murder_rates` | 51 US states x 3 years |

The split is **registered and not evaluated**. It is not "untouched", and
saying so would be false: each file was downloaded once, its row, column,
entity and period counts recorded, its sha256 taken, and it was checked for
duplicate entity-period pairs. That is structural inspection, and it is what
makes the registration verifiable rather than a promise.

What has *not* happened: **`paneldx` has not been run on any of them, and no
verdict for any of them exists.** They are not fetched by default, and naming
one is not enough — `scripts/fetch_validation_data.py` refuses to touch the
split without `--include-held-out`, and no benchmark profile can select it.

Rules:

- Held-out data must not be used to choose or adjust any threshold, rule,
  status boundary, default or heuristic.
- Held-out **verdicts** must not be inspected before the freeze. Not to sanity
  check, not to debug, not "just to see". Structure — shape, checksum,
  duplicate pairs — may be recorded, and has been; that is what registration
  means here.
- The split is opened once. If a defect is found afterwards and the method
  changes, the split is spent: the results become development results, and a
  new held-out split is required.
- `protocol.json` records `held_out_opened_at`. It is `null` until the day the
  split is opened, and that date is never rewritten.

### external

Cross-domain panels from outside econometrics — clinical, operational,
administrative — to test whether the method generalises past the family of
datasets it was built on. **Empty at version 1.1.0.** Every dataset above is an
econometrics panel, which is itself a limitation on anything measured here.

### Families

Every dataset carries a `family_id` naming the source it was drawn from, and
**a family may never span two splits**. Two panels built from one survey are
not independent: calibrating on one would leak into a held-out result from the
other. The manifest check enforces this, and it is why `Fatalities` was dropped
rather than kept alongside `usseatbelts`. Families also decide how rates are
resampled — see section 5.

### case_study

Illustrative only, never counted in any metric. See section 7.

---

## 4. Corruption tests

Public panels supply correct keys. Broken keys have to be manufactured, and
the manufacturing has to be recorded, or a false-acceptance rate means nothing.
Each test takes a panel whose key is correct, applies one transformation with a
recorded seed, and asserts what should happen. The full list is in
`protocol.json` under `corruption_tests`; in summary:

A corrupted key has exactly two safe outcomes, and `warn` is not one of them:

- **Safe stop** — `fail` (the tool rejected it) or `inconclusive` (the tool
  declined to judge). Neither invites a user to model on the key.
- **Unsafe acceptance** — `pass` or `warn`. Both hand back a key the user may
  proceed with, and both count towards `false_acceptance_rate`. This matches
  section 1: `warn` means "weak, inspect by hand", which on a key that is known
  broken is an invitation to argue with the evidence.

| Corruption | What it does | Levels | Safe outcome |
|---|---|---|---|
| `positional_rekey` | Sorts each period by a value column and keys on row position — the PopNet defect | full | safe stop |
| `within_period_shuffle` | Permutes entity labels independently within each period | full | safe stop |
| `entity_merge` | Collapses pairs of distinct entities onto one label | 1, 5, 10% | safe stop |
| `entity_split` | Splits an entity's rows across two labels at a random period | 1, 5, 10% | safe stop |
| `partial_corruption` | Shuffles labels for a fraction of entities | 1, 2, 5, 10, 20, 50% | safe stop, plus the sensitivity requirement below |
| `duplicate_entity_periods` | Duplicates a share of entity-period rows | 0.5, 1, 2, 5, 10% | `fail` above the duplicate limit, unchanged below it |
| `missing_entity_keys` | Blanks the entity key on a share of rows | 0.5, 1, 2, 5, 10% | unchanged, or `inconclusive` once too little is left |
| `missing_time_values` | Blanks the time column on a share of rows | 0.5, 1, 2, 5, 10% | unchanged, or `inconclusive` once too little is left |
| `panel_attrition` | Drops entities out of the panel from a random period on | 5, 10, 20% | unchanged, or `inconclusive` once too few transitions remain |
| `period_gaps` | Deletes rows to open gaps in entity histories | 5, 10, 20% | unchanged, or `inconclusive` once too few transitions remain |
| `invariant_column_removal` | Drops invariant columns one at a time | 1, 2, 3 columns | **never `fail`** — only the evidence was removed, not the key |
| `feature_poor_panel` | Keeps the correct key, reduces the panel to a few time-varying columns | 1, 2, 3 columns | **never `fail`** — the key is correct, so a `fail` here is a false rejection |

Naming an exact status for a broken key would be stricter than the framework in
section 1, which asks whether the tool stopped, not which kind of stop it
reached. So the requirement on a broken key is a **safe stop** — `fail` or
`inconclusive` — and `pass` or `warn` is the miss.

The last two rows are not corruptions of the key at all; they corrupt the
*evidence* available about a correct key. `feature_poor_panel` is the Produc problem made
into a test: a panel can be perfectly well keyed and still offer almost nothing
for the key to explain, and a diagnostic that answers `fail` there is wrong.
`duplicate_entity_periods` is the opposite case: duplicate entity-period cells
are a structural contradiction, so `fail` is correct there.

**How a corruption level is reported.** Statuses are not ranked. `inconclusive`
is not a severity between `warn` and `fail`; it is a refusal to judge, and
placing it on a scale with the three verdicts invents an ordering the tool does
not have. Averaging such ranks would then produce numbers — a mean severity of
1.7 — that correspond to nothing.

So at each corruption level, for each dataset, the harness reports the
distribution and two rates derived from it:

| Reported | Meaning |
|---|---|
| `pass`, `warn`, `inconclusive`, `fail` | count and proportion of runs at that level |
| `unsafe_acceptance_rate` | (`pass` + `warn`) / runs |
| `safe_stop_rate` | (`fail` + `inconclusive`) / runs |

The two rates sum to 1 and are the only aggregates taken. The four counts are
published beside them, because the rates alone cannot distinguish a tool that
rejects a broken key from one that declines to judge it.

**The sensitivity requirement**, stated on those proportions rather than on a
rank: across the declared corrupted fractions in increasing order, a dataset's
`unsafe_acceptance_rate` must be non-increasing, and strictly lower at the
largest fraction than at the smallest. More damage must never make the tool
more willing to accept the key, and the curve must move at all. A flat curve is
a reported failure of sensitivity, not a pass. This is assessed on one panel at
a time and is never pooled into a rate across panels.

Two properties matter more than any single expectation. A corruption that is
undetectable in principle must not be counted as a miss: shuffling labels in a
panel whose columns are all time-varying removes nothing detectable, so
`inconclusive` is correct there, which is why it counts as a safe stop. And `partial_corruption` is the sensitivity curve — a diagnostic
that only catches total corruption is close to useless on real data, where a
broken join damages part of a panel.

The harness is `validation/harness/corruptions.py`. The runner records the
requested and achieved levels. Cases that do not achieve the requested
corruption are retained as `NO_EFFECT` and excluded from scoring.

---

## 5. Evaluation metrics

Defined formally in `protocol.json` under `primary_metrics`.

**Key validation (primary):**

- `false_rejection_rate` — known-correct keys reported `fail`.
- `false_acceptance_rate` — corrupted keys reported `pass` or `warn`.
- `inconclusive_rate` — reported whenever either error rate is reported.

**Key discovery (planned, 0.6.x):** `top_1_key_recovery`,
`top_3_key_recovery`, `equivalent_partition_recovery`.

`false_acceptance_rate` is the `unsafe_acceptance_rate` of section 4, and
`inconclusive_rate` is read off the same four counts. Neither is published
without them.

### The statistical unit is the dataset

This is the rule that decides whether a reported rate means anything.

Every corruption of a panel, and every seed used to produce one, is a rerun on
the same table: the same columns, the same entity count, the same invariant
structure for the key to explain. Ten corruptions of Produc are ten
observations about Produc, not ten observations about panel data. A denominator
that counts them as ten independent datasets reports an interval narrower than
the evidence supports.

So:

1. **Average each corruption procedure first.** Within a dataset, take the mean
   over one procedure's levels and seeds, then the mean over the procedures.
   Weighting every case equally makes the rate depend on how many levels a
   procedure happens to declare: `partial_corruption` has six and
   `positional_rekey` has one.
2. **Then the dataset is one number**, whatever the number of runs behind it.
   Never pool cases across datasets into one numerator and denominator.
3. **Combine by family, not by dataset.** A family contributes one value, the
   mean over its datasets. Two panels from one survey are one observation, not
   two.
4. **Intervals come from the family level.** Report a cluster or hierarchical
   bootstrap that resamples families. With *k* families the interval is
   governed by *k*, and it should look as wide as *k* deserves.
5. **Wilson intervals are for the one-per-family case only.** They apply when
   each family contributes a single independent binary outcome — "was the
   documented key rejected?" — and nowhere else.
6. **Report the denominators.** Every rate is published as a count over a
   denominator with *k* named, alongside the number of runs behind it, never as
   a bare percentage.

Every family currently holds exactly one dataset, so family and dataset
resampling coincide today. The rule is written on families because that is what
stays correct the moment a second panel from an existing source is added.

Two errors this rules out. Running 10 corruptions x 10 seeds on 6 panels and
reporting a rate over 600 with an interval computed as if *n* = 600: the real
*n* is the number of families, 6. And letting a procedure that declares six
levels count for six times as much as one that declares a single level.

---

## 6. Reproducibility

Fixed in `protocol.json`, under `seeds`, `shuffle_counts` and `environment`:

- **Seeds.** `validate_key`, `discover_keys` and `target_leakage` all run at
  `random_state=0`. Synthetic generators use seeds 0-4; corruptions use 0-9.
- **Shuffle counts.** The library defaults (3 for `validate_key`, 2 for
  `discover_keys`) are a cheap sanity reference, adequate for a CI gate.
  **Any number published as a validation result must be produced with
  `n_shuffles = 200`**, from the `publication` profile. That profile **has not
  been run.** Every result recorded under `results/` was produced at
  `n_shuffles = 3` and is a development diagnostic: a direction and a
  magnitude, not an estimate.
- **Environment.** Python 3.12 with the pinned versions in
  [requirements.txt](../requirements.txt).

Fixed in `calibration_grid.json`, written before any calibration result
existed:

- **The grid.** Four thresholds, 81 valid points, and the fixed values that were
  deliberately left out of it because they act on the measurement rather than on
  the decision.
- **The selection rule.** A strict lexicographic order — lowest unsafe
  acceptance, then lowest false rejection, then lowest inconclusive rate, then
  fewest departures from the developed defaults. No weighted score invented
  afterwards.
- **What it chose.** `minimum_null_gap` 0.05 → 0.10, which cut unsafe
  acceptance of broken keys from 0.211 to 0.196 over six families for 1.2 points
  more inconclusive. The other three thresholds stayed where they were.

Fixed in `datasets.json`, one entry per panel:

- **Data.** Every public dataset is pinned by sha256. A file whose digest does
  not match is refused, not used with a warning: a suite that silently accepts
  a different file is measuring something other than what it reports.

A fresh checkout is not ready to validate anything: the pinned packages are not
installed and the panels have not been fetched. Reproducing the environment
takes four commands, of which the last is the gate:

```bash
python3.12 -m venv .venv-validation
.venv-validation/bin/pip install -r validation/requirements.txt
.venv-validation/bin/python -m scripts.fetch_validation_data
.venv-validation/bin/python -m scripts.check_validation_setup
```

The checker creates nothing and installs nothing. It reports whether what is
already there matches what was recorded — the interpreter version, every
pinned package, the manifest, this document's agreement with `protocol.json`,
and the checksum of every dataset — and exits non-zero on any mismatch,
including a panel that was never fetched.

---

## 7. PopNet is a case study, not evidence

The PopNet reanalysis is the defect this package was built from, and it is the
reason the tool exists. It is not validation evidence, for four independent
reasons:

1. The true physician identifier is unknown. `Disease + Opening time` is the
   best-supported candidate found by search, not ground truth.
2. The data are restricted and cannot be redistributed, so no third party can
   reproduce the result.
3. The rules were developed against this dataset. It is development data by
   construction.
4. The checks were run after the 2025 paper was published. They were not part
   of the paper and are not corrected PopNet results.

No accuracy claim, error rate or verdict from PopNet enters any metric in this
protocol. `datasets.json` records it with `access: restricted` and no
`source_url`, and the manifest schema forbids a restricted dataset from
carrying one, so no script in this repository can fetch it even by mistake.

---

## 8. What can be claimed today

**Can be said:**

- `paneldx` reports a specific, recorded verdict on four public panels, and a
  change in those verdicts fails CI.
- Produc is a documented false rejection, retained as a marker.
- Thresholds are provisional and uncalibrated.

**Cannot be said, and must not appear in any documentation, README, abstract or
release note:**

- Any accuracy, precision, recall, false-positive or false-negative *rate*.
- That the four public panels are external, held-out or independent evidence.
- That the thresholds are calibrated.
- That `paneldx` validated the PopNet dataset, or corrected the PopNet paper.

---

## 9. Changing this protocol

The protocol is frozen, so these rules are in force. They are mirrored in
`protocol.json` under `versioning`.

`protocol_version` follows semantic versioning:

- **Patch** — wording, typos, clarifications that change no rule.
- **Minor** — additions that cannot invalidate an existing result: a new
  corruption test, a new dataset in an empty split, a new secondary metric.
- **Major** — anything that changes a split, a primary metric, a seed, the
  publication shuffle count, or the definition of a correct answer.

A major change after the held-out split has been opened invalidates the
held-out result. That is the cost, and it is deliberate.

Amendments are recorded in `CHANGELOG.md` with the reason, and in
`protocol.json` under `amendments`. This document is not edited to match
results that were already produced.

### Amendments

- **2.0.0, 2026-09-04 (major).** The primary unsafe-acceptance rate now averages
  each corruption procedure within a dataset before averaging datasets and
  families; the previous figure was a case-weighted mixture that measured the
  shape of the corruption list as much as the tool. Per-procedure and per-level
  breakdowns are published beside every aggregate. Recorded that no
  publication-profile run exists. Made before any held-out evaluation, so no
  held-out result is invalidated.
- **1.3.0, 2026-09-04 (minor).** Replaced "unopened" with "registered and not
  evaluated" for the held-out split, and recorded exactly what was done to
  those files. Marked the calibration exploratory rather than preregistered.
  Recorded that the 0.4.0 threshold values are frozen inside the grid. No claim
  is strengthened by any of this; two are weakened to match what happened.
- **1.2.0, 2026-09-04 (minor).** Recorded that the calibration split has been
  used, under a grid frozen before any result was computed, and that
  `minimum_null_gap` moved from 0.05 to 0.10 as a result. Updated the baseline
  description for the 0.5.0 semantics change. No split, metric, seed or
  definition of a correct answer changed, which is what keeps this minor. The
  held-out split remains unevaluated.
- **1.1.0, 2026-09-04 (minor).** Populated the calibration and held-out splits,
  both of which were empty; recorded `family_id` and made the resampling unit
  the family; expanded the corruption list from 8 to 12 with explicit levels;
  corrected the safe outcome for `duplicate_entity_periods` from `inconclusive`
  to `fail`, since duplicate cells are a structural contradiction rather than
  an absence of evidence. Nothing had been measured against 1.0.0.
