# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-09-05

### Changed

- `fail` now means the data contradicts the key. Three things produce it:
  duplicate entity-period cells above tolerance, a declared invariant that
  changes within an entity, and a declared monotone column that falls.
- A low evidence share, or a key indistinguishable from shuffled labels, is now
  `inconclusive` rather than `fail`.
- Produc moves from `fail` to `inconclusive`. Across the benchmark, all 741
  correct-key cases that failed under 0.4.0 no longer fail. Documented-key
  failures fell from 4 of 10 to 0, with no loss in detection of duplicate
  entity-period contradictions.
- `discover_keys` ranks the best candidate first. It previously sorted on the
  status priority directly, which put a rejected candidate above a supported
  one, and `audit` takes the first report as the chosen key.
- `minimum_null_gap` 0.05 to 0.10, fitted on the calibration split under a grid
  written before the run. The only calibrated threshold in the package.
- The CLI exits 2 rather than 1 where a key can no longer be judged.
- Unit and regression tests run without network access; the public panels moved
  to a separate CI job.
- Parquet and Feather input requires Python 3.10+.

### Added

- `invariant_cols` and `monotone_cols` on `validate_key`, `discover_keys` and
  `audit`; `--invariant` and `--monotone` on `paneldx audit`.
- A `reason` on every `KeyReport`: `supported`, `weak_support`,
  `insufficient_evidence`, `duplicate_entity_period`,
  `declared_invariant_broken`, `declared_monotone_broken`.
- `validation/protocol/`: the validation protocol, its machine-readable copy
  and the calibration grid.
- `validation/manifests/datasets.json`: seventeen datasets with source,
  citation, reviewed licensing, entity and time columns, SHA-256, shape, family
  and key evidence. Three candidates were rejected, with reasons recorded.
- Calibration and held-out splits. A family may not span two splits. Held-out
  data needs `--include-held-out` even to be named.
- `validation/harness/`: twelve reproducible corruption procedures, family-level
  metrics, a benchmark runner, calibration and comparison.
- `validation/results/`, versioned per release, with the 0.4.0 baseline and a
  case-by-case comparison.
- `scripts.check_validation_setup` and a pinned environment in
  `validation/requirements.txt`.
- `--check`, `--dataset` and `--role` on the dataset downloader.

### Fixed

- The dataset downloader verifies a SHA-256 before a file is given the name the
  suite reads, and verifies files already on disk rather than trusting them.
- A broken sentence in the README limitations section.

### Removed

- `tests/validation/panels.json`, split between `validation/manifests/datasets.json`
  and `tests/validation/expected_results.json`.

### Documentation

- The four original public panels are development data, not external validation.
- `docs/limitations.md` reports what the benchmark measured, labelled as
  development diagnostics at three shuffles rather than validation estimates.
- `docs/interpreting-results.md` documents every reason code.
- The PopNet narrative moved to `case_studies/popnet_reanalysis/`.

## [0.4.0] - 2026-08-25

### Added

- Added an `inconclusive` result when there is not enough data for a decision.
- Added policy objects for changing validation thresholds.
- Added fixed finding codes to audit results.
- Added period-step support for checking time gaps.
- Added an option to run checks with a weak key.
- Added validation tests using four public panel datasets.
- Added threshold sensitivity results.
- Added a post-publication PopNet case study and a synthetic example.
- Split tests into unit, regression and validation folders.
- Added CI checks for tests, linting, formatting, typing and package builds.

### Changed

- Separated calculations, status decisions and report wording.
- Compound keys now keep their original values and data types.
- Leakage checks exclude the key, time and target columns by default.
- Persistence checks use only adjacent periods.
- Duplicate entity-period rows now make the check inconclusive.
- Within-entity checks run only when the key is supported.
- The package version is read from `paneldx/__init__.py`.
- File formats supported by the CLI are now tested.

### Fixed

- Small panels could previously be reported as passing.
- Checks with insufficient data could look favourable.
- Missing key or time values could create incorrect groups.
- Different compound-key values could become the same string.
- Duplicate periods could be counted as time movement.
- Key discovery could hide candidate errors.
- Persistence checks could include non-adjacent periods.

### Documentation

- Clarified that the PopNet findings were produced after the 2025 paper.
- Added documentation about thresholds, limitations and known false results.

[Unreleased]: https://github.com/stemmatics/paneldx/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/stemmatics/paneldx/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/stemmatics/paneldx/releases/tag/v0.4.0
