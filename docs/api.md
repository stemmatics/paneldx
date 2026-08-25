# API reference

Everything is importable from the top level:

```python
from paneldx import (
    audit,
    AuditResult,
    Finding,
    to_html,
    validate_key,
    discover_keys,
    KeyReport,
    entity_key,
    detect_counters,
    CounterReport,
    target_leakage,
    LeakageReport,
    persistence_baseline,
    BaselineReport,
    Status,
    PASS,
    WARN,
    FAIL,
    INCONCLUSIVE,
)
```

## Statuses

Every check carries a structured `status`, one of four strings:

| Status | Meaning |
|--------|---------|
| `"pass"` | The check ran with sufficient evidence and found no issue |
| `"warn"` | The check ran and found a non-blocking concern |
| `"fail"` | The check ran and found a blocking structural defect |
| `"inconclusive"` | Preconditions were not met; no conclusion is allowed, favourable or otherwise |

Overall severity orders them `fail > inconclusive > warn > pass`: a proven
defect outranks a check that could not run, and an unmet precondition blocks
any overall claim.

---

## Policies

Thresholds are fields on two frozen dataclasses in `paneldx.policy`:
`KeyValidationPolicy` (tolerances and minimum sizes for key checks) and
`TrapPolicy` (counter, leakage and baseline cut-offs). Every check accepts a
`policy` argument; `audit` accepts `key_policy` and `trap_policy`. Defaults are
`DEFAULT_KEY_POLICY` and `DEFAULT_TRAP_POLICY`; see
[limitations.md](limitations.md) for their calibration status.

---

## `audit(df, time_col, *, key=None, target=None, features=None, max_columns=2, top_k=3, period_step=None, allow_weak_key=False, key_policy=DEFAULT_KEY_POLICY, trap_policy=DEFAULT_TRAP_POLICY, source=None)`

Run every check in one pass. Validates `key` if given, otherwise searches for one
and runs the rest under the best candidate.

Counters and the persistence baseline run only when the chosen key is
supported; `allow_weak_key=True` extends that to a weakly supported key. Under
a failed or unjudged key they are skipped and the findings say so. The leakage
test uses `features` when given; by default it uses every numeric column except
the key columns, the time column and the target, since identifiers and time
indexes are not predictors just because they are numeric. `period_step`
declares the cadence for the persistence baseline (see `persistence_baseline`).

Returns `AuditResult`. Raises `KeyError` if `time_col` is not in the frame.

### `AuditResult`

| Attribute | Type | Notes |
|-----------|------|-------|
| `n_rows`, `n_columns`, `n_periods` | `int` | Shape of the input |
| `time_col` | `str` | |
| `key_was_supplied` | `bool` | False when the key was discovered |
| `key_reports` | `list[KeyReport]` | Best first |
| `rejected_candidates` | `list[tuple[tuple[str, ...], str]]` | Discovery candidates that raised a data error, with the reason |
| `counters` | `CounterReport \| None` | |
| `leakage` | `LeakageReport \| None` | Only when `target` was given |
| `baseline` | `BaselineReport \| None` | Only when `target` was given |
| `chosen` | `KeyReport \| None` | The key the rest of the audit ran under |
| `findings` | `list[Finding]` | Worst first |
| `worst` | `str` | `"fail"`, `"inconclusive"`, `"warn"` or `"pass"` |
| `discovery_blocked` | `str \| None` | Why key discovery could not run, when it could not |

### `Finding`

Frozen dataclass with four fields. `code` is the stable machine-readable
identifier; headline and detail are prose and may change between releases.

| Field | Notes |
|-------|-------|
| `code` | One of `key_supported`, `key_weak`, `key_unsupported`, `key_inconclusive`, `key_missing`, `discovery_inconclusive`, `leakage`, `leakage_suspect`, `leakage_clean`, `leakage_inconclusive`, `baseline`, `baseline_inconclusive`, `counters`, `counters_inconclusive` |
| `status` | See [Statuses](#statuses) |
| `headline` | One-line summary |
| `detail` | Explanation, including what additional data an inconclusive check needs |

---

## `validate_key(df, key, time_col, *, policy=DEFAULT_KEY_POLICY, n_shuffles=3, random_state=0)`

Test whether `key` identifies entities tracked across `time_col`. `key` is a
column name or a sequence of them.

Returns `KeyReport`. Raises `KeyError` for missing columns.

### `KeyReport`

| Attribute | Type | Notes |
|-----------|------|-------|
| `key` | `tuple[str, ...]` | |
| `n_entities` | `int` | With at least two observations |
| `coverage` | `float` | Share of input rows covered |
| `duplicate_rate` | `float` | Share of (entity, period) cells appearing more than once |
| `invariant_cols` | `list[str]` | Constant within an entity, but not under the null |
| `monotone_cols` | `list[str]` | Never decreasing, but not under the null |
| `evidence` | `float` | Count of explained columns |
| `evidence_frac` | `float` | **The headline.** Share of columns explained |
| `n_usable_cols` | `int` | Denominator for `evidence_frac` |
| `invariance_violation` | `float` | Mean rate, with `null_invariance_violation` alongside |
| `monotonicity_violation` | `float` | Mean rate, with `null_monotonicity_violation` alongside |
| `status` | `str` | See [Statuses](#statuses) |
| `verdict` | `str` | Prose explanation; see [interpreting-results](interpreting-results.md) |

`print(report)` gives a readable summary.

---

## `discover_keys(df, time_col, *, max_columns=2, top_k=5, candidate_columns=None, policy=DEFAULT_KEY_POLICY, n_shuffles=2, random_state=0, rejections=None)`

Search column combinations for one that behaves like an entity key. Returns up to
`top_k` `KeyReport` objects, best first.

Cost is roughly O(n²) in columns at `max_columns=2`. Narrow it with
`candidate_columns` on wide tables. Raises `ValueError` if `time_col` has fewer
than two distinct values.

---

## `entity_key(df, key)`

Integer entity codes for the rows of `df` under `key`, as a `Series` aligned to
the frame. Codes are opaque: equal code means equal key values, nothing more.
Values are grouped as-is, never serialised to strings, so `1` and `"1"` stay
distinct and no character in the data can merge or split two entities. Useful
for building your own grouped operations on a validated key.

---

## `detect_counters(df, key, time_col, *, exclude=None)`

Find columns behaving as running totals. A counter is numeric, non-negative,
actually moves, and essentially never decreases within an entity. Columns in
`exclude` (typically the modelling target) are not examined.

Returns `CounterReport` with `counters: list[str]`,
`autocorrelation: dict[str, float]` (lag-1, within entity),
`n_columns_tested: int` and `status`.

---

## `target_leakage(df, target, features=None, *, random_state=0)`

Test whether the target is a linear restatement of its own features. With
`features=None`, every numeric column except the target is used; prefer passing
the model's actual predictor set. A non-numeric target returns an
`inconclusive` report rather than raising.

Returns `LeakageReport` with `r2` (held out), `n_features`,
`top_contributors: list[tuple[str, float]]` (standardised coefficients, largest
absolute first), `status` and `verdict`. Raises `KeyError` for a missing target
or feature column and `ValueError` for a non-numeric requested feature.

---

## `persistence_baseline(df, key, time_col, target, *, period_step=None)`

Score the carry-forward forecast, where next period equals this period, over
exactly-adjacent period pairs only. Two observations of an entity are adjacent
when their periods are exactly one `period_step` apart. The cadence is never
inferred from the data: a panel observed only at periods 1 and 100 has no
adjacent pairs, not a step of 99.

- Numeric period column: `period_step` is a positive number, default `1`.
- Datetime period column: `period_step` must be declared as a pandas frequency
  string (`"QS"`, `"MS"`, `"7D"`), `Timedelta` or `DateOffset`. Until it is,
  the report is `inconclusive`.
- Any other dtype: `inconclusive`; map the periods onto an ordered scale first.

Pairs spanning a gap are counted and excluded. If any entity has more than
one observation of a period, the report is `inconclusive`: there is no single
value to carry forward, and choosing one silently would be an undeclared
aggregation.

Returns `BaselineReport` with `period_step` (the cadence used, as text),
`n_pairs`, `n_gapped_pairs`, `n_duplicate_cells`, `target_autocorrelation`,
`persistence_mae`, `persistence_r2`, `status` and `verdict`. Needs at least 20
adjacent pairs, otherwise the report is `inconclusive` and the metrics are
`nan`. A mismatched `period_step` raises `TypeError`.

---

## `to_html(result, *, title="paneldx audit")`

Render an `AuditResult` as a self-contained HTML string. No external assets, and
all data-derived text is escaped.

---

## Command line

```
paneldx audit DATA --time COL [--key COL ...] [--target COL] [--html PATH]
                   [--sheet NAME] [--max-columns N] [--top-k N]
                   [--period-step STEP] [--quiet]
```

Exits `1` when any finding is `FAIL`, `2` when the worst finding is
`INCONCLUSIVE` (the evidence was insufficient to reach any verdict), and `0`
otherwise.
