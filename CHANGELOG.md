# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No changes yet.

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

[Unreleased]: https://github.com/stemmatics/paneldx/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/stemmatics/paneldx/releases/tag/v0.4.0
