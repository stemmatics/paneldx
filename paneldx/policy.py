"""Thresholds and evidence requirements.

Most defaults remain provisional: they were chosen while developing the rules
on synthetic panels. `minimum_null_gap` is the exception. It was fitted on the
calibration split alone, under the grid frozen in
validation/protocol/calibration_grid.json, and the result is in
validation/results/calibration/v0.5.0/calibration.json. See docs/limitations.md for what that
does and does not license.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyValidationPolicy:
    invariant_violation_rate: float = 0.02
    monotone_violation_rate: float = 0.05
    duplicate_cell_rate: float = 0.01
    # Calibrated 2026-09-04 on the calibration split (0.05 -> 0.10). Raising it
    # cut unsafe acceptance of broken keys from 0.211 to 0.196 across six
    # families, at the cost of 1.2 points more inconclusive. Every other
    # threshold in the grid was left at its developed value.
    minimum_null_gap: float = 0.10
    supported_evidence_fraction: float = 0.40
    weak_evidence_fraction: float = 0.15
    minimum_entities: int = 20
    minimum_periods_per_entity: int = 2
    minimum_steps: int = 20


@dataclass(frozen=True)
class TrapPolicy:
    counter_decrease_rate: float = 0.05
    minimum_steps: int = 20
    deterministic_r2: float = 0.99
    reconstructible_r2: float = 0.90
    rows_per_feature: int = 4
    strong_persistence_r2: float = 0.95
    moderate_persistence_r2: float = 0.70
    minimum_pairs: int = 20


DEFAULT_KEY_POLICY = KeyValidationPolicy()
DEFAULT_TRAP_POLICY = TrapPolicy()
