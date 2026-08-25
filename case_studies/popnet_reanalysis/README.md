# PopNet reanalysis

The defect this package was built from. An earlier physician-analytics
pipeline keyed physicians by row position within each quarter, after each
quarter had been sorted by platform rank, so the identifier linked different
physicians together across quarters. See the "bug this was built from" section
of the top-level README for the reported numbers.

These checks were carried out after the PopNet paper was published in 2025.
They were not included in the paper and are not corrected PopNet results.

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
