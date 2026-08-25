# paneldx

[![CI](https://github.com/stemmatics/paneldx/actions/workflows/ci.yml/badge.svg)](https://github.com/stemmatics/paneldx/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/paneldx)](https://pypi.org/project/paneldx/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

**Check that your longitudinal dataset is what it claims to be, before you model it.**

```bash
pip install paneldx
paneldx audit data.csv --time quarter --target risk_score --html report.html
```

## What it does, plainly

Imagine a class attendance sheet where you assume "student #3" is the same child
every week. But the sheet is re-sorted by test score each week, so student #3 is
a different child every time. Now compute "student #3's progress over the term".
You get a number. It means nothing.

Data that tracks the same patients, customers or providers across time has this
failure mode constantly, and nothing warns you. Lags, differences, trajectories,
sequence models and grouped cross-validation all silently assume the identifier
points at one entity. When it does not, nothing errors. The numbers just stop
meaning anything.

`paneldx` tests that assumption against the data itself, and tells you when it
fails. It also catches three related problems that make a model look better than
it is.

## When you would use this

- **Before training on any panel dataset**, especially one assembled from
  exports, joins, or de-identification passes, where re-sorting can sever an ID
  from the entity it names.
- **When results look too good.** An R² of 0.95 on time-series data is more often
  a warning than an achievement. `paneldx` tells you what a naive baseline scores
  so you know whether your model beat anything.
- **When inheriting someone else's data** and the entity column arrived without
  documentation.
- **As a CI gate.** The command exits non-zero on a disqualifying defect, and
  also when there is too little evidence to judge, so a pipeline can refuse to
  train on a broken or unverifiable panel.
- **When reviewing a paper or a colleague's analysis** and you want to check the
  panel is sound before reading the results.

Not useful for cross-sectional data with no time dimension, or for panels of
fewer than two periods.

---

## The bug this was built from

An earlier physician-analytics pipeline of ours built its entity ID from row
position:

```python
physician_id = ((serial_number - 1) % rows_per_quarter) + 1
```

Each quarter was sorted by platform rank before this ran, so position *i* was a
different doctor every quarter. The ID linked strangers together, and that ID
then fed momentum features, a GRU over "trajectories", and the grouped CV splits.

`paneldx` on that dataset, given no hints:

```
key: physician_id                      key: Disease + Opening time
  columns explained  2 of 30  (7%)       columns explained  13 of 29  (45%)
  VERDICT  NOT SUPPORTED                 VERDICT  supported by the data
```

These checks were carried out after the PopNet paper was published in 2025.
They were not included in the paper and are not corrected PopNet results.

The search tested all one-column and two-column combinations. `Disease +
Opening time` received the strongest support from the available data. This does
not prove that it is the actual physician identifier, so it is treated as a
candidate key.

That was one of three defects. The other two turned up on the same dataset
without being told anything about it:

| Check | What it found |
|---|---|
| `detect_counters` | `Total patients` (lag-1 ρ = 0.962), `Total visits` (0.871), `Medical consultation records` (0.961). Lifetime totals that barely move, so a target built from them is autocorrelated by construction |
| `target_leakage` | R² = **0.923** reconstructing the target from its own features, naming `inv_rank`, `log_gifts` and `log_visits`, which were three of the four components the target was averaged from |
| `persistence_baseline` | Carry-forward MAE **0.0320** against that model's **0.0942**. Doing nothing was 2.9x better |

### The defects hide each other

A broken key does not only corrupt features. It disarms the check that would
have caught it:

| Key used | Persistence MAE | R² | What a researcher concludes |
|---|---|---|---|
| Positional key (as used) | 0.4717 | 0.191 | "carry-forward is useless, my 0.0942 is good" |
| Candidate (`Disease + Opening time`) | **0.0320** | **0.971** | carry-forward beats the model by 2.9x |

Under the positional key the naive forecast looks worthless, so nobody thinks to
compare against it. Under the best-supported candidate key it is close to
unbeatable. This is why `paneldx` establishes the key before it reports any
baseline, and why running the baseline alone would not have caught it.

---

## Install

```bash
pip install paneldx
```

Python 3.9+, `numpy` and `pandas`. Nothing else: no modelling framework, no
template engine.

---

## Usage

```python
from paneldx import audit, to_html
from paneldx import validate_key, discover_keys
from paneldx import detect_counters, target_leakage, persistence_baseline

# Is the entity key supported by the data?
print(validate_key(df, "patient_id", time_col="quarter"))
print(discover_keys(df, time_col="quarter")[0])  # no hints needed

# Are the numbers about to fool you?
print(detect_counters(df, "patient_id", "quarter"))  # lifetime totals
print(target_leakage(df, target="risk_score"))  # is y inside X?
print(
    persistence_baseline(df, "patient_id", "quarter", "risk_score", period_step="QS")
)  # declare the cadence

# Or all of it at once
result = audit(df, "quarter", key="patient_id", target="risk_score")
open("report.html", "w").write(to_html(result))
```

The CLI reads CSV, TSV, Excel, Parquet, Feather and JSON:

```bash
paneldx audit panel.xlsx --time t --key site_id patient_id --target outcome
```

---

## The three traps

**Cumulative features.** Lifetime totals barely move between periods, so a target
built from them is near-perfectly autocorrelated. Models trained on them report
excellent R² for restating what they were handed. Difference them into
per-period flows.

**Target composition.** When the target is computed from columns that are also
features, the model is not predicting, it is recovering arithmetic. The metrics
look superb and mean nothing. `target_leakage` fits a deliberately *linear*
model: the point is not to predict the target well, but to show no prediction was
ever required.

**Missing naive baseline.** On autocorrelated panels, carrying the last value
forward is often unbeatable. A model reported without it may be losing to a
one-line rule, and no reader could tell.

---

## How key validation works

A useful entity key should reveal consistent patterns across periods.

**Invariants.** Some attributes should not change for the same entity, such as
a birth date or account opening date. Under a valid entity key, these values
should normally remain stable. Under a broken key, they may change between
periods.

**Counters.** Some values only increase over time. Under a valid entity key,
their within-entity changes should normally be non-negative. Under a broken
key, they may move in both directions.

paneldx compares this structure with shuffled entity labels. A supported key
should perform better than the shuffled reference. A broken key may perform close to it.

The verdict uses the **share** of columns explained, not only the count. A key
created from row order may explain a few columns because those columns were used
for sorting. A supported entity key should explain a larger share of the data.

| `evidence_frac` | Verdict |
|---|---|
| ≥ 0.40 | supported by the data |
| 0.15 to 0.40 | weak, inspect the listed columns by hand |
| < 0.15 | not supported, within-entity quantities are unsafe |

---

## Limitations

- **Near-valid keys are hard to separate from perfect ones.** The tolerances
  exist because valid keys may also contain a small number of collisions
  of entities can score like a clean one. Ties break toward the finer partition,
  which mitigates but does not eliminate this.
- **Leakage detection is linear.** A target computed from its features by some
  non-linear rule can slip past `target_leakage`. A high score is strong
  evidence; a low one is not a clearance.
- **Two-column search is O(n²)** in columns. On a 24k x 31 table the full pair
  search takes about 23 seconds. Pass `--key` when you already know it.
- **A passing verdict is not a proof.** It says the data is consistent with the
  key, not that the key is correct. Domain knowledge still wins.
- Needs at least two periods, and enough entities to measure a rate against.

---

## Roadmap

The next work will focus on reproducible validation, clearer evidence rules,
key-discovery testing and an independently evaluated publication candidate.
See the [development roadmap](ROADMAP.md) for the planned stages.

---

## Documentation

- [Getting started](docs/getting-started.md)
- [How it works](docs/how-it-works.md)
- [Interpreting results](docs/interpreting-results.md)
- [API reference](docs/api.md)
- [Development roadmap](ROADMAP.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). False positives are bugs: if `paneldx`
rejects a key you know is correct, that is worth an issue.

Release notes are in [CHANGELOG.md](CHANGELOG.md).

## Citation

If you use `paneldx` in your research, please see [CITATION.cff](CITATION.cff).

The DOI for version 0.4.0 will be added after the release is archived on
Zenodo. The old DOI belongs to version 0.3.1 and does not refer to the current
code.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
