# Getting started

## Install

```bash
pip install paneldx
```

Python 3.9 or newer. Runtime dependencies are `numpy` and `pandas`.

## Your first audit

Point it at a panel and tell it which column holds the period:

```bash
paneldx audit data.csv --time quarter
```

With no `--key`, it searches for one. On a table with many columns that search
is the slow part, so pass the key when you know it:

```bash
paneldx audit data.csv --time quarter --key patient_id
```

Add a target to test for leakage and score the naive baseline:

```bash
paneldx audit data.csv --time quarter --key patient_id --target risk_score
```

Add `--html report.html` for a self-contained page you can attach to a review.

If you know something about the panel, say so. Columns that cannot change
within an entity, and columns that can only rise, turn "could not judge" into a
definite answer:

```bash
paneldx audit data.csv --time quarter --key patient_id \
  --invariant birth_date enrolled_on --monotone total_visits
```

## Reading the output

Findings come out worst-first:

```
data.csv: 24,000 rows x 31 columns, 4 periods of 'quarter'

  [INCONCLUSIVE]  Entity key could not be judged (patient_id)
          Too little is explained to support the key (7% of usable columns);
          this is not evidence against it. Treat within-entity quantities as
          unverified rather than as wrong.

  [WARN]  4 cumulative counter(s) among the features
          Lifetime totals barely move between periods. Difference them into
          per-period flows before modelling.
```

| Severity       | Meaning |
|----------------|---------|
| `FAIL`         | The data contradicts the key, or a check found a defect. Fix before modelling. |
| `INCONCLUSIVE` | The data did not settle the question. No conclusion, favourable or otherwise. |
| `WARN`         | Something needs review before modelling; it may inflate apparent performance. |
| `PASS`         | Checked and clean. |

The command exits `1` if any finding is `FAIL` and `2` if the evidence was
insufficient to judge (`INCONCLUSIVE`), which is what makes it usable as
a gate:

```yaml
- name: Validate panel
  run: paneldx audit data/panel.parquet --time period --key subject_id
```

## As a library

```python
import pandas as pd
from paneldx import audit, to_html

df = pd.read_parquet("panel.parquet")
result = audit(df, time_col="period", key="subject_id", target="outcome")

if result.worst == "fail":
    raise SystemExit("panel is not safe to model")

with open("report.html", "w") as fh:
    fh.write(to_html(result))
```

Each check is also callable on its own. See [api.md](api.md).

## Supported formats

CSV, TSV, Excel (`.xlsx`), Parquet, Feather and JSON. Excel
files take `--sheet` for a sheet name or index.

## Next

- [How it works](how-it-works.md) for the method behind the verdicts.
- [Interpreting results](interpreting-results.md) for what to do about each one.
