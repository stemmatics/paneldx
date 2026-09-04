"""Choose thresholds on the calibration split, under a grid frozen in advance.

    python -m validation.harness.calibration

The grid, metrics and selection rule live in
validation/protocol/calibration_grid.json and were written before the run. This
module applies the recorded lexicographic order and reports what it picked,
with the runners-up, so a reader can see how close the decision was. It does
not compute any other score.

Measurement runs once per case under a deliberately permissive policy, and each
grid point then re-reads that measurement. The thresholds in the grid all act on
the decision rather than on the measurement, so re-reading is exact — and it is
what makes 81 grid points affordable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np

from paneldx import (
    KeyReport,
    KeyValidationPolicy,
    validate_key,
)
from paneldx import (
    __version__ as paneldx_version,
)
from paneldx.status import (
    FAIL,
    INCONCLUSIVE,
    PASS,
    WARN,
)
from validation.harness import metrics
from validation.harness.cases import (
    BROKEN_KEY,
    KEY_CORRECT,
    NO_EFFECT,
    achieved_what_was_asked,
    expectation_for,
    load_panel,
)
from validation.harness.corruptions import CORRUPTIONS, DETERMINISTIC, rng_for
from validation.manifest import ROOT, load_manifest

GRID = ROOT / "validation" / "protocol" / "calibration_grid.json"
PROTOCOL = ROOT / "validation" / "protocol" / "protocol.json"
OUT = ROOT / "validation" / "results" / "calibration" / "current" / "calibration.json"


@dataclass
class Measurement:
    """Everything a grid point needs, measured once."""

    dataset_id: str
    family_id: str
    corruption: str
    level: float | int | None
    seed: int | None
    expectation: str
    duplicate_rate: float
    n_entities: int
    n_transitions: int
    n_invariant_cols: int
    evidence_frac: float
    gap: float
    measured: bool


def measure(df, key, time_column, policy) -> tuple[KeyReport, float]:
    report = validate_key(df, key, time_column, policy=policy)
    gap = report.null_invariance_violation - report.invariance_violation
    return report, float(gap)


def classify(m: Measurement, thresholds: dict, fixed: dict) -> str:
    """Re-read one measurement under one grid point.

    Mirrors validate_key's decision order. No declared invariants exist in the
    benchmark, so the only route to `fail` is a duplicate entity-period cell.
    `fixed` comes from the grid file rather than from the running policy: a
    later change to a default must not silently rewrite this calibration.
    """
    if m.duplicate_rate > fixed["duplicate_cell_rate"]:
        return FAIL
    if m.n_entities < thresholds["minimum_entities"]:
        return INCONCLUSIVE
    if m.n_transitions < fixed["minimum_steps"]:
        return INCONCLUSIVE
    if not m.measured:
        return INCONCLUSIVE
    if m.n_invariant_cols == 0 and (
        not np.isfinite(m.gap) or m.gap < thresholds["minimum_null_gap"]
    ):
        return INCONCLUSIVE
    if m.evidence_frac >= thresholds["supported_evidence_fraction"]:
        return PASS
    if m.evidence_frac >= thresholds["weak_evidence_fraction"]:
        return WARN
    return INCONCLUSIVE


def _measurement(
    dataset, frame, frame_key, time_column, policy, corruption, level, seed, fixed, achieved=True
) -> Measurement:
    report, gap = measure(frame, frame_key, time_column, policy)
    if corruption == "none":
        expectation = KEY_CORRECT
    else:
        expectation = expectation_for(
            corruption, report.duplicate_rate, fixed["duplicate_cell_rate"]
        )
        if not achieved:
            expectation = NO_EFFECT
    return Measurement(
        dataset_id=dataset["id"],
        family_id=dataset["family_id"],
        corruption=corruption,
        level=level,
        seed=seed,
        expectation=expectation,
        duplicate_rate=report.duplicate_rate,
        n_entities=report.n_entities,
        n_transitions=report.n_transitions,
        n_invariant_cols=len(report.invariant_cols),
        evidence_frac=report.evidence_frac,
        gap=gap,
        measured=report.n_usable_cols > 0,
    )


def _dataset_measurements(dataset, specs, grid, policy, data_dir) -> list[Measurement]:
    fixed = grid["fixed"]
    df, _ = load_panel(dataset, data_dir)
    key, time_column = list(dataset["entity_key"]), dataset["time_column"]

    out = [_measurement(dataset, df, key, time_column, policy, "none", None, None, fixed)]
    for name, spec in specs.items():
        seeds = [0] if name in DETERMINISTIC else grid["seeds"]
        for level in spec["levels"]:
            for seed in seeds:
                rng = rng_for(dataset["id"], name, level, seed)
                try:
                    corrupted = CORRUPTIONS[name](df, key, time_column, level, rng)
                except ValueError:
                    continue
                out.append(
                    _measurement(
                        dataset,
                        corrupted.df,
                        corrupted.key,
                        time_column,
                        policy,
                        name,
                        level,
                        seed,
                        fixed,
                        achieved_what_was_asked(corrupted, level),
                    )
                )
    return out


def collect(datasets, protocol, grid, data_dir, progress=True) -> list[Measurement]:
    """One measurement per case, under a policy that judges nothing.

    The fixed values come from the grid file, so the measurement is the one the
    grid describes rather than the one today's defaults would produce.
    """
    fixed = grid["fixed"]
    permissive = KeyValidationPolicy(
        minimum_entities=1,
        minimum_null_gap=-1.0,
        invariant_violation_rate=fixed["invariant_violation_rate"],
        monotone_violation_rate=fixed["monotone_violation_rate"],
        minimum_periods_per_entity=fixed["minimum_periods_per_entity"],
        minimum_steps=fixed["minimum_steps"],
    )
    specs = {spec["id"]: spec for spec in protocol["corruption_tests"]}

    out: list[Measurement] = []
    for dataset in datasets:
        produced = _dataset_measurements(dataset, specs, grid, permissive, data_dir)
        out.extend(produced)
        if progress:
            print(f"  measured {dataset['id']}: {len(produced)}")
    return out


def _family_mean(pairs, families, predicate) -> float | None:
    """Average within each dataset, then across families."""
    per_dataset: dict[str, float] = {}
    for dataset_id in {m.dataset_id for m, _ in pairs}:
        rows = [status for m, status in pairs if m.dataset_id == dataset_id]
        if rows:
            per_dataset[dataset_id] = float(np.mean([predicate(s) for s in rows]))
    values = metrics.by_family(per_dataset, families)
    return float(np.mean(list(values.values()))) if values else None


def score(measurements: list[Measurement], thresholds: dict, grid: dict) -> dict:
    """Three family-level rates for one grid point.

    Cases that did not achieve the level they asked for are carried through
    `collect` so they can be counted, and dropped here so they cannot be
    scored: a corruption that changed nothing is evidence about neither a
    broken key nor a correct one.
    """
    fixed, baseline = grid["fixed"], grid["baseline_defaults"]
    scored = [m for m in measurements if m.expectation != NO_EFFECT]
    statuses = [(m, classify(m, thresholds, fixed)) for m in scored]
    families = {m.dataset_id: m.family_id for m in scored}

    broken = [(m, s) for m, s in statuses if m.expectation == BROKEN_KEY]
    correct = [(m, s) for m, s in statuses if m.expectation == KEY_CORRECT]
    documented = [(m, s) for m, s in statuses if m.corruption == "none"]

    return {
        "thresholds": dict(thresholds),
        "unsafe_acceptance": _family_mean(
            broken, families, lambda s: s in metrics.UNSAFE_ACCEPTANCE
        ),
        "false_rejection": _family_mean(correct, families, lambda s: s == FAIL),
        "inconclusive": _family_mean(statuses, families, lambda s: s == INCONCLUSIVE),
        "documented_keys_supported": sum(1 for _, s in documented if s in (PASS, WARN)),
        "documented_keys_failed": sum(1 for _, s in documented if s == FAIL),
        "thresholds_changed_from_baseline": sum(
            1 for field, value in thresholds.items() if baseline[field] != value
        ),
    }


def grid_points(grid: dict) -> list[dict]:
    fields = sorted(grid["grid"])
    points = []
    for values in product(*(grid["grid"][field] for field in fields)):
        candidate = dict(zip(fields, values))
        if candidate["weak_evidence_fraction"] >= candidate["supported_evidence_fraction"]:
            continue
        points.append(candidate)
    return points


def rank(scores: list[dict]) -> list[dict]:
    """The recorded lexicographic order, applied literally."""
    return sorted(
        scores,
        key=lambda s: (
            s["unsafe_acceptance"],
            s["false_rejection"],
            s["inconclusive"],
            s["thresholds_changed_from_baseline"],
            tuple(s["thresholds"][field] for field in sorted(s["thresholds"])),
        ),
    )


def case_counts(measurements: list[Measurement]) -> dict[str, int]:
    """What was attempted, what was scored, and what was set aside.

    A single source for the three numbers. Computing them at the call site is
    how the excluded count came to be taken from a list the exclusions had
    already been removed from, and it always read zero.
    """
    excluded = sum(1 for m in measurements if m.expectation == NO_EFFECT)
    return {
        "cases_attempted": len(measurements),
        "cases_measured": len(measurements) - excluded,
        "cases_excluded_no_effect": excluded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    grid = json.loads(GRID.read_text())
    protocol = json.loads(PROTOCOL.read_text())
    manifest = load_manifest()
    data_dir = ROOT / manifest["download_directory"]

    datasets = [d for d in manifest["datasets"] if d["role"] == "calibration"]
    if {d["id"] for d in datasets} != set(grid["datasets"]):
        raise SystemExit("the calibration split does not match the frozen grid")

    if not args.quiet:
        print(f"calibration split: {len(datasets)} datasets")
    measurements = collect(datasets, protocol, grid, data_dir, progress=not args.quiet)

    points = grid_points(grid)
    scores = [score(measurements, point, grid) for point in points]
    ranked = rank(scores)
    chosen = ranked[0]

    result = {
        "grid": grid,
        "paneldx_version": paneldx_version,
        "protocol_version_at_calibration": grid["protocol_version_at_calibration"],
        "current_protocol_version": protocol["protocol_version"],
        **case_counts(measurements),
        "grid_points": len(points),
        "families": len({m.family_id for m in measurements}),
        "selected": chosen,
        "baseline_defaults": {f: grid["baseline_defaults"][f] for f in sorted(grid["grid"])},
        "selected_equals_baseline": chosen["thresholds"]
        == {f: grid["baseline_defaults"][f] for f in sorted(grid["grid"])},
        "runners_up": ranked[1:6],
        "all_points": ranked,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=float) + "\n")

    if not args.quiet:
        print(f"\n{len(points)} grid points over {result['families']} families")
        print(f"selected: {chosen['thresholds']}")
        print(
            f"  unsafe acceptance {chosen['unsafe_acceptance']:.4f}"
            f"  false rejection {chosen['false_rejection']:.4f}"
            f"  inconclusive {chosen['inconclusive']:.4f}"
        )
        print(f"  equals the frozen 0.4.0 baseline: {result['selected_equals_baseline']}")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
