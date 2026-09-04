# PopNet reanalysis

The defect this package was built from. An earlier physician-analytics
pipeline keyed physicians by row position within each quarter, after each
quarter had been sorted by platform rank, so the identifier linked different
physicians together across quarters. See the "bug this was built from" section
of the top-level README for the reported numbers.

These checks were carried out after the PopNet paper was published in 2025.
They were not included in the paper and are not corrected PopNet results.

## What the audit found

`paneldx` on that dataset, given no hints:

```
key: physician_id                      key: Disease + Opening time
  columns explained  2 of 30  (7%)       columns explained  13 of 29  (45%)
  VERDICT  INCONCLUSIVE                  VERDICT  supported by the data
```

Those shares are what the audit measured. The verdict wording is from 0.5.0:
7% is too little to support the key, which is not the same as proving it wrong,
so the tool abstains. Declaring one column that cannot change within a
physician turns the same run into a `fail`; see "Declaring what you know"
in the top-level README.

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

## Data

The original workbook is not included in this repository. It contains
physician-level information, including values taken from profile images. Only
authorised researchers should use it.

This repository contains the audit scripts, summary results and a synthetic
example. It does not contain the original workbook or any physician-level
records.

Required columns, as used by the scripts (override with flags):

| Column | Role |
|---|---|
| `Serial number` | row serial in the original export, used to reconstruct the positional identifier |
| `time` | quarter |
| `Disease`, `Opening time` | the best-supported candidate compound key |
| target (optional) | the modelling target, for the leakage and persistence checks |

## Files

- `prepare_data.py` reconstructs `positional_id` with the original formula.
- `audit_panel.py` audits the panel under the positional key and the candidate
  key, runs blind discovery, and prints observed values beside
  `expected_results.json`.
- `expected_results.json` contains summary results from a paneldx 0.3.1 audit
  carried out after the PopNet paper was published. These results were not part
  of the paper. They are kept for comparison and should not be treated as
  corrected PopNet results.
- `synthetic_reproduction.py` applies the same mechanism to a synthetic panel
  with a known key, so the effect can be seen without the data.

```bash
python case_studies/popnet_reanalysis/audit_panel.py --data /path/to/workbook.xlsx --target risk
python case_studies/popnet_reanalysis/synthetic_reproduction.py
```

`tests/validation/test_case_study.py` runs the audit when the environment
variable `PANELDX_POPNET_DATA` points at the workbook, and is skipped otherwise.
