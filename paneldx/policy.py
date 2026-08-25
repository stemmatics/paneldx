"""Thresholds and evidence requirements.

Defaults are provisional; see docs/limitations.md for calibration status.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyValidationPolicy:
    invariant_violation_rate: float = 0.02
    monotone_violation_rate: float = 0.05
    duplicate_cell_rate: float = 0.01
    minimum_null_gap: float = 0.05
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
