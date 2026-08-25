# Roadmap

This roadmap shows the planned direction of `paneldx`. Version numbers are
checkpoints, not fixed deadlines. Plans may change when testing finds a more
important issue.

## Current release: 0.4.0

Version 0.4.0 is the baseline release. It includes key validation and discovery,
counter detection, leakage checks, persistence baselines and an HTML report.

## 0.4.x: validation foundation

- Write and freeze the validation protocol.
- Separate development, calibration, held-out and external datasets.
- Record dataset sources, licences, checksums and expected key columns.
- Add reproducible dataset preparation and corruption tests.
- Keep regression tests separate from scientific validation results.

## 0.5.x: evidence and thresholds

- Make `fail` mean there is evidence against a key.
- Use `inconclusive` when the data does not provide enough evidence.
- Allow users to declare invariant and monotone columns.
- Calibrate thresholds only on the calibration datasets.
- Report uncertainty, seed stability, sensitivity and ablation results.

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
