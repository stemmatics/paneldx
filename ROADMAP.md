# Roadmap

This roadmap shows the planned direction of `paneldx`. Version numbers are
checkpoints, not fixed deadlines. Plans may change when testing finds a more
important issue.

## Current release: 0.4.0

## Next release: 0.5.0

Version 0.4.0 is the behavioural baseline. Version 0.5.0 changes what the
verdicts mean: `fail` says the data contradicts the key, and a shortage of
supporting evidence says `inconclusive`. It also adds the validation
foundation, the dataset collection, the corruption benchmark and the first
calibrated threshold.

## 0.4.x: validation foundation

Delivered in 0.5.0:

- Drafted the validation protocol (`validation/protocol/protocol.md`) and its
  machine-readable form (`validation/protocol/protocol.json`).
- Separated development, calibration, held-out and external splits, with a
  family rule that stops related panels straddling two of them.
- Recorded dataset sources, citations, licences, checksums, shapes and key
  columns for seventeen datasets (`validation/manifests/datasets.json`).
- Kept regression expectations separate from scientific results
  (`tests/validation/expected_results.json`).
- Pinned the validation environment and added a single command that reports
  whether an installed environment matches it.
- Built the corruption benchmark: twelve reproducible corruption procedures, family-level
  metrics, one command, results committed.

## 0.5.x: evidence and thresholds

Delivered in 0.5.0:

- `fail` means there is evidence against a key.
- `inconclusive` when the data does not provide enough evidence.
- Users can declare invariant and monotone columns.
- One threshold calibrated, on the calibration split only.

Still open:

- Seed-stability and ablation reporting beyond the sensitivity curve.
- A second calibrated threshold, if the calibration split grows enough to
  support one.

## 0.6.x: key discovery validation

- Measure top-1, top-3 and equivalent-partition recovery.
- Check selection bias when many candidate keys are tested.
- Report incorrect acceptance and runtime across datasets.

## 0.7.x: publication candidate

- Freeze the method before opening held-out results.
- Run the final held-out and cross-domain external evaluation.
- Generate tables and figures from machine-readable results.
- Archive the tested code, protocol, results and environment details.

## 1.0

Version 1.0 will be considered when the public API, validation protocol and
supported scientific claims are stable.

## Working principles

- Correctness and reproducibility come before release dates.
- Public examples used during development are not held-out evidence.
- PopNet remains a motivating case study and is not validation ground truth.
- Results will include failures, inconclusive cases and known limitations.
- Claims will remain within what the benchmark results support.
