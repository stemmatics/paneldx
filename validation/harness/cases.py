"""Run the corruption benchmark.

    python -m validation.harness.cases --profile development

Profiles set how much is run, not what it means: `smoke` for CI, `development`
for the full run, `publication` at 200 shuffles. No profile can select the
held-out split.

Writes run.json, cases.csv.gz, dataset_summary.csv, dataset_summary.json,
overall_summary.json, environment.json and failures.json to the output
directory.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from paneldx import (
    KeyValidationPolicy,
    validate_key,
)
from paneldx import (
    __version__ as paneldx_version,
)
from validation.harness import metrics
from validation.harness.corruptions import (
    CORRUPTIONS,
    DETERMINISTIC,
    Corrupted,
    rng_for,
)
from validation.manifest import ROOT, load_manifest, sha256_file

PROTOCOL = ROOT / "validation" / "protocol" / "protocol.json"
RESULTS = ROOT / "validation" / "results" / "development" / "current"

FORBIDDEN_ROLES = frozenset({"held_out"})

CASES_FILE = "cases.csv.gz"

# What a corruption is allowed to produce. Categories, not statuses: the
# protocol judges safety, and `fail` versus `inconclusive` is a question about
# which kind of safe stop was reached, not about whether the tool was right.
BROKEN_KEY = "broken_key"  # a safe stop is required; pass/warn is a miss
STRUCTURAL = "structural"  # a contradiction exists; `fail` is the right answer
KEY_CORRECT = "key_correct"  # the key still holds; `fail` is a false rejection
# A corruption that moved no rows. The key was never broken, so scoring the
# case as a broken key would credit or blame the tool for a panel it was right
# about. Recorded and excluded from every metric.
NO_EFFECT = "no_effect"

EXPECTATION = {
    "positional_rekey": BROKEN_KEY,
    "within_period_shuffle": BROKEN_KEY,
    "entity_merge": BROKEN_KEY,
    "entity_split": BROKEN_KEY,
    "partial_corruption": BROKEN_KEY,
    "duplicate_entity_periods": STRUCTURAL,
    "missing_entity_keys": KEY_CORRECT,
    "missing_time_values": KEY_CORRECT,
    "panel_attrition": KEY_CORRECT,
    "period_gaps": KEY_CORRECT,
    "invariant_column_removal": KEY_CORRECT,
    "feature_poor_panel": KEY_CORRECT,
}

PROFILES: dict[str, dict[str, Any]] = {
    "smoke": {"roles": ["development"], "seeds": [0], "n_shuffles": 3, "ends_only": True},
    "development": {
        "roles": ["development", "calibration"],
        "seeds": list(range(10)),
        "n_shuffles": 3,
        "ends_only": False,
    },
    "publication": {
        "roles": ["development", "calibration"],
        "seeds": list(range(10)),
        "n_shuffles": 200,
        "ends_only": False,
    },
}


@dataclass
class Case:
    """One benchmark case, carrying enough provenance to rebuild it exactly."""

    dataset_id: str
    family_id: str
    role: str
    corruption: str
    level: float | int | None
    seed: int | None
    expectation: str
    correct_key: str
    time_column: str
    source_sha256: str
    generated_sha256: str
    duplicate_rate: float
    columns_changed: int
    achieved_level: int | float | None
    entities_affected: int
    rows_affected: int
    rows: int
    status: str
    reason: str
    n_entities: int
    evidence_frac: float
    runtime_seconds: float
    outcome: str


def frame_sha256(df: pd.DataFrame) -> str:
    """Digest of the exact bytes a corruption produced.

    Written through the CSV writer rather than hashing pandas internals so the
    value is reproducible from the file anyone else would export.
    """
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


def expectation_for(corruption: str, duplicate_rate: float, limit: float) -> str:
    """What this case is allowed to report.

    `duplicate_entity_periods` is the one corruption whose category depends on
    the result rather than the recipe. Duplicating half a percent of rows
    leaves the duplicate rate under the tolerance, so the key is still correct
    and a `fail` would be a false rejection. Above the tolerance the same
    corruption is a contradiction and `fail` is the right answer.
    """
    if corruption == "duplicate_entity_periods":
        return STRUCTURAL if duplicate_rate > limit else KEY_CORRECT
    return EXPECTATION[corruption]


def achieved_what_was_asked(corrupted: Corrupted, level: float | int) -> bool:
    """Whether the corruption did what the level asked for.

    Two ways it may not have. A row corruption can move nothing, and a column
    corruption can be asked for more columns than the panel has, in which case
    it returns the frame a lower level already produced. Either way the case is
    a duplicate or a no-op, and counting it would weight the panel twice.
    """
    if corrupted.achieved_level is not None:
        return corrupted.achieved_level == level
    return corrupted.changed_anything


def outcome_of(expectation: str, status: str) -> str:
    if expectation == NO_EFFECT:
        return "no_effect"
    if expectation == BROKEN_KEY:
        return "unsafe_acceptance" if status in metrics.UNSAFE_ACCEPTANCE else "safe_stop"
    if expectation == STRUCTURAL:
        return "detected" if status == "fail" else "missed_contradiction"
    return "false_rejection" if status == "fail" else "no_false_rejection"


def levels_for(spec: dict, ends_only: bool) -> list[float | int]:
    levels = list(spec["levels"])
    if ends_only and len(levels) > 2:
        return [levels[0], levels[-1]]
    return levels


def load_panel(dataset: dict, data_dir: Path) -> tuple[pd.DataFrame, str]:
    path = data_dir / dataset["file"]
    if not path.exists():
        raise SystemExit(
            f"{dataset['file']} has not been fetched. Run scripts/fetch_validation_data.py first."
        )
    digest = sha256_file(path)
    if digest != dataset["sha256"]:
        raise SystemExit(f"{dataset['file']} does not match its recorded sha256; refusing to run.")
    df = pd.read_csv(path, low_memory=False).drop(columns=dataset.get("drop_columns", []))
    return df, digest


def run_case(df, key, time_column, policy, n_shuffles) -> tuple[Any, float]:
    started = time.perf_counter()
    report = validate_key(df, key, time_column, policy=policy, n_shuffles=n_shuffles)
    return report, time.perf_counter() - started


def reason_of(report) -> str:
    # 0.4.0 has no reason codes; the field exists so the 0.5.0 comparison is a
    # column change rather than a schema change.
    return getattr(report, "reason", "")


def _baseline_case(dataset, df, digest, common, policy, n_shuffles) -> Case:
    """The documented key, uncorrupted. A `fail` here is a false rejection."""
    report, seconds = run_case(
        df, list(dataset["entity_key"]), dataset["time_column"], policy, n_shuffles
    )
    return Case(
        **common,
        corruption="none",
        level=None,
        seed=None,
        expectation=KEY_CORRECT,
        generated_sha256=digest,
        duplicate_rate=round(report.duplicate_rate, 6),
        columns_changed=0,
        achieved_level=None,
        entities_affected=0,
        rows_affected=0,
        rows=len(df),
        status=report.status,
        reason=reason_of(report),
        n_entities=report.n_entities,
        evidence_frac=round(report.evidence_frac, 6),
        runtime_seconds=round(seconds, 4),
        outcome=outcome_of(KEY_CORRECT, report.status),
    )


def _corrupted_case(corrupted, name, level, seed, common, policy, n_shuffles) -> Case:
    report, seconds = run_case(
        corrupted.df, corrupted.key, corrupted.time_column, policy, n_shuffles
    )
    expectation = expectation_for(name, report.duplicate_rate, policy.duplicate_cell_rate)
    if not achieved_what_was_asked(corrupted, level):
        expectation = NO_EFFECT
    return Case(
        **common,
        corruption=name,
        level=level,
        seed=seed,
        expectation=expectation,
        generated_sha256=frame_sha256(corrupted.df),
        duplicate_rate=round(report.duplicate_rate, 6),
        columns_changed=corrupted.columns_changed,
        achieved_level=corrupted.achieved_level,
        entities_affected=corrupted.entities_affected,
        rows_affected=corrupted.rows_affected,
        rows=len(corrupted.df),
        status=report.status,
        reason=reason_of(report),
        n_entities=report.n_entities,
        evidence_frac=round(report.evidence_frac, 6),
        runtime_seconds=round(seconds, 4),
        outcome=outcome_of(expectation, report.status),
    )


def _corruption_plan(dataset_id, specs, profile):
    """Yield (name, level, seed, rng) for every case a profile asks for.

    Flattening the three nested loops here keeps `_dataset_cases` to one level
    of iteration, and puts the seed rule — deterministic procedures run once —
    in one place.
    """
    for name, spec in specs.items():
        seeds = [0] if name in DETERMINISTIC else profile["seeds"]
        for level in levels_for(spec, profile["ends_only"]):
            for seed in seeds:
                yield name, level, seed, rng_for(dataset_id, name, level, seed)


def _dataset_cases(dataset, specs, profile, policy, data_dir, progress) -> list[Case]:
    df, digest = load_panel(dataset, data_dir)
    key, time_column = list(dataset["entity_key"]), dataset["time_column"]
    common = dict(
        dataset_id=dataset["id"],
        family_id=dataset["family_id"],
        role=dataset["role"],
        correct_key="+".join(key),
        time_column=time_column,
        source_sha256=digest,
    )

    cases = [_baseline_case(dataset, df, digest, common, policy, profile["n_shuffles"])]
    for name, level, seed, rng in _corruption_plan(dataset["id"], specs, profile):
        try:
            corrupted = CORRUPTIONS[name](df, key, time_column, level, rng)
        except ValueError as error:  # a corruption this panel cannot express
            if progress:
                print(f"  skip {dataset['id']}/{name}@{level}: {error}")
            continue
        cases.append(
            _corrupted_case(corrupted, name, level, seed, common, policy, profile["n_shuffles"])
        )
    return cases


def build_cases(datasets, protocol, profile, policy, data_dir, progress=True) -> list[Case]:
    specs = {spec["id"]: spec for spec in protocol["corruption_tests"]}
    missing = set(specs) - set(EXPECTATION)
    if missing:
        raise SystemExit(f"protocol.json lists corruptions with no expectation: {sorted(missing)}")

    cases: list[Case] = []
    for dataset in datasets:
        produced = _dataset_cases(dataset, specs, profile, policy, data_dir, progress)
        cases.extend(produced)
        if progress:
            print(f"  {dataset['id']}: {len(produced)} cases")
    return cases


def _broken_key_breakdown(broken: list[Case]) -> tuple[dict, dict, dict]:
    """Statuses grouped by procedure, and by procedure and level."""
    by_corruption: dict[str, list[str]] = {}
    by_level: dict[str, dict[str, list[str]]] = {}
    for case in broken:
        by_corruption.setdefault(case.corruption, []).append(case.status)
        label = "full" if case.level is None else str(case.level)
        by_level.setdefault(case.corruption, {}).setdefault(label, []).append(case.status)

    per_corruption = {
        corruption: metrics.summarise(statuses)
        for corruption, statuses in sorted(by_corruption.items())
    }
    per_level = {
        corruption: {label: metrics.summarise(statuses) for label, statuses in levels.items()}
        for corruption, levels in by_level.items()
    }
    return by_corruption, per_corruption, per_level


def _sensitivity_curve(rows: list[Case]) -> dict:
    """Unsafe acceptance against corrupted fraction, for one dataset."""
    partial = [c for c in rows if c.corruption == "partial_corruption"]
    curve: dict[float, float] = {}
    for value in sorted({float(c.level) for c in partial if c.level is not None}):
        rate = metrics.summarise(c.status for c in partial if c.level == value)[
            "unsafe_acceptance_rate"
        ]
        if rate is not None:
            curve[value] = float(rate)
    return metrics.sensitivity(curve)


def _procedure_groups(cases: list[Case]) -> dict[str, list[str]]:
    """Statuses grouped by corruption procedure, with the uncorrupted case as
    its own group so it counts once rather than not at all."""
    groups: dict[str, list[str]] = {}
    for case in cases:
        groups.setdefault(case.corruption, []).append(case.status)
    return groups


def _dataset_outcomes(broken, correct, structural) -> dict:
    """Counts of the three ways a case can go wrong, for one dataset."""
    return {
        "false_rejections_when_key_correct": sum(
            1 for c in correct if c.outcome == "false_rejection"
        ),
        "unsafe_acceptances_when_key_broken": sum(
            1 for c in broken if c.outcome == "unsafe_acceptance"
        ),
        "missed_contradictions": sum(1 for c in structural if c.outcome == "missed_contradiction"),
    }


def _dataset_summary(dataset_id: str, rows: list[Case]) -> dict:
    broken = [c for c in rows if c.expectation == BROKEN_KEY]
    correct = [c for c in rows if c.expectation == KEY_CORRECT]
    structural = [c for c in rows if c.expectation == STRUCTURAL]
    scored = [c for c in rows if c.expectation != NO_EFFECT]
    baseline = next(c for c in rows if c.corruption == "none")
    by_corruption, per_corruption, per_level = _broken_key_breakdown(broken)

    return {
        "dataset_id": dataset_id,
        "family_id": rows[0].family_id,
        "role": rows[0].role,
        "documented_key_status": baseline.status,
        "documented_key_reason": baseline.reason,
        "false_rejection_on_documented_key": baseline.status == "fail",
        # The primary figures weight each corruption procedure equally. The
        # case-weighted mixtures are kept beside them to reconcile with counts.
        "broken_key_unsafe_acceptance": metrics.unsafe_acceptance(by_corruption),
        "inconclusive_rate": metrics.inconclusive_rate(_procedure_groups(scored)),
        "broken_key": metrics.summarise(c.status for c in broken),
        "broken_key_by_corruption": per_corruption,
        "broken_key_by_level": per_level,
        "correct_key_degraded": metrics.summarise(c.status for c in correct),
        "structural": metrics.summarise(c.status for c in structural),
        **_dataset_outcomes(broken, correct, structural),
        "partial_corruption_sensitivity": _sensitivity_curve(rows),
        "median_runtime_seconds": float(np.median([c.runtime_seconds for c in rows])),
        "cases": len(rows),
    }


def dataset_summaries(cases: list[Case]) -> list[dict]:
    by_dataset: dict[str, list[Case]] = {}
    for case in cases:
        by_dataset.setdefault(case.dataset_id, []).append(case)
    return [_dataset_summary(name, rows) for name, rows in sorted(by_dataset.items())]


def _false_rejection(summaries: list[dict], families: dict[str, str], seed: int) -> dict:
    """Wilson where each family gives one binary outcome, bootstrap otherwise.

    A family holding two datasets averages to 0.5, and there is no such thing
    as half a success, so the count cannot simply be rounded into shape.
    """
    per_family = metrics.by_family(
        {s["dataset_id"]: float(s["false_rejection_on_documented_key"]) for s in summaries},
        families,
    )
    if all(value in (0.0, 1.0) for value in per_family.values()):
        return {
            **metrics.wilson_interval(int(sum(per_family.values())), len(per_family)),
            "method": "wilson",
            "note": "one binary outcome per family, so Wilson applies here and nowhere else",
        }
    return {
        **metrics.bootstrap_interval(list(per_family.values()), seed=seed),
        "method": "bootstrap",
        "note": "a family holds more than one dataset, so its value is not binary",
    }


def _status_mixes(cases: list[Case]) -> dict:
    return {
        "correct_key_degraded_status_mix": metrics.summarise(
            c.status for c in cases if c.expectation == KEY_CORRECT
        ),
        "broken_key_status_mix": metrics.summarise(
            c.status for c in cases if c.expectation == BROKEN_KEY
        ),
        "structural_status_mix": metrics.summarise(
            c.status for c in cases if c.expectation == STRUCTURAL
        ),
        "broken_key_by_corruption": {
            corruption: metrics.summarise(
                c.status
                for c in cases
                if c.expectation == BROKEN_KEY and c.corruption == corruption
            )
            for corruption in sorted({c.corruption for c in cases if c.expectation == BROKEN_KEY})
        },
    }


def overall(summaries: list[dict], cases: list[Case], seed: int = 0) -> dict:
    families = {s["dataset_id"]: s["family_id"] for s in summaries}
    per_dataset = {s["dataset_id"]: s["broken_key_unsafe_acceptance"] for s in summaries}
    case_weighted = metrics.summarise(c.status for c in cases if c.expectation == BROKEN_KEY)

    return {
        "datasets": len(summaries),
        "families": len(set(families.values())),
        "cases": len(cases),
        "statistical_unit": "family, over corruption-procedure means",
        "cases_excluded_no_effect": sum(1 for c in cases if c.expectation == NO_EFFECT),
        "documented_key_false_rejection": {
            **_false_rejection(summaries, families, seed),
            "datasets": sorted(
                s["dataset_id"] for s in summaries if s["false_rejection_on_documented_key"]
            ),
        },
        "broken_key_unsafe_acceptance": {
            **metrics.bootstrap_interval(
                list(metrics.by_family(per_dataset, families).values()), seed=seed
            ),
            "weighting": "corruption procedure, then dataset, then family",
            "note": (
                "Each corruption procedure contributes equally within a dataset, so the rate "
                "does not depend on how many levels a procedure declares."
            ),
        },
        "inconclusive_rate": {
            **metrics.bootstrap_interval(
                list(
                    metrics.by_family(
                        {s["dataset_id"]: s["inconclusive_rate"] for s in summaries}, families
                    ).values()
                ),
                seed=seed,
            ),
            "weighting": "corruption procedure, then dataset, then family",
            "note": (
                "Reported whenever an error rate is: both rates fall when the tool declines to "
                "judge, and only one of them looks like an improvement."
            ),
        },
        "broken_key_unsafe_acceptance_case_weighted": {
            "rate": case_weighted["unsafe_acceptance_rate"],
            "note": (
                "Every case weighted equally, so procedures with more levels dominate. "
                "Reported for reconciliation with the raw counts, not for quoting."
            ),
        },
        **_status_mixes(cases),
    }


def environment(profile_name: str, profile: dict) -> dict:
    return {
        "paneldx_version": paneldx_version,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "platform": platform.platform(),
        "profile": profile_name,
        "n_shuffles": profile["n_shuffles"],
        "seeds": profile["seeds"],
        "roles": profile["roles"],
    }


def write_results(out_dir: Path, run: dict, cases, summaries, summary, env, failures) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    (out_dir / "dataset_summary.csv").write_text(_summary_csv(summaries))
    # The CSV is a flat view for reading; the JSON keeps the per-procedure and
    # per-level breakdowns the protocol says are published.
    (out_dir / "dataset_summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    (out_dir / "overall_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    (out_dir / "failures.json").write_text(json.dumps(failures, indent=2) + "\n")
    if not cases:
        return
    # Gzipped because it is the one file that grows with the run: several
    # thousand rows, and it is committed. pandas and the csv module both read
    # it directly, so nothing downstream has to know.
    with gzip.open(out_dir / CASES_FILE, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(cases[0])))
        writer.writeheader()
        writer.writerows(asdict(case) for case in cases)


def _summary_csv(summaries: list[dict]) -> str:
    """One row per dataset, carrying the primary rates rather than the raw mix.

    `broken_key_unsafe_acceptance` and `inconclusive_rate` are the
    procedure-weighted figures the protocol defines. The four counts beside
    them are case counts, and the case-weighted rate they imply is not the same
    number; publishing that one here made the CSV disagree with
    overall_summary.json.
    """
    fields = [
        "dataset_id",
        "family_id",
        "role",
        "documented_key_status",
        "false_rejection_on_documented_key",
        "broken_key_pass",
        "broken_key_warn",
        "broken_key_inconclusive",
        "broken_key_fail",
        "broken_key_unsafe_acceptance_rate",
        "inconclusive_rate",
        "correct_key_false_rejections",
        "missed_contradictions",
        "sensitivity_ok",
        "median_runtime_seconds",
        "cases",
    ]
    lines = [",".join(fields)]
    for s in summaries:
        broken = s["broken_key"]
        lines.append(
            ",".join(
                str(value)
                for value in [
                    s["dataset_id"],
                    s["family_id"],
                    s["role"],
                    s["documented_key_status"],
                    s["false_rejection_on_documented_key"],
                    broken["pass"],
                    broken["warn"],
                    broken["inconclusive"],
                    broken["fail"],
                    s["broken_key_unsafe_acceptance"],
                    s["inconclusive_rate"],
                    s["false_rejections_when_key_correct"],
                    s["missed_contradictions"],
                    s["partial_corruption_sensitivity"]["ok"],
                    round(s["median_runtime_seconds"], 4),
                    s["cases"],
                ]
            )
        )
    return "\n".join(lines) + "\n"


def collect_failures(cases: list[Case], summaries: list[dict]) -> dict:
    """Everything that went wrong, kept rather than filtered out."""
    return {
        "note": "Every miss from the run, recorded rather than filtered out.",
        "false_rejections_on_documented_keys": [
            s["dataset_id"] for s in summaries if s["false_rejection_on_documented_key"]
        ],
        "unsafe_acceptances": [
            {
                "dataset_id": c.dataset_id,
                "corruption": c.corruption,
                "level": c.level,
                "seed": c.seed,
                "status": c.status,
            }
            for c in cases
            if c.outcome == "unsafe_acceptance"
        ],
        "false_rejections_when_key_correct": [
            {
                "dataset_id": c.dataset_id,
                "corruption": c.corruption,
                "level": c.level,
                "seed": c.seed,
            }
            for c in cases
            if c.outcome == "false_rejection"
        ],
        "missed_contradictions": [
            {
                "dataset_id": c.dataset_id,
                "corruption": c.corruption,
                "level": c.level,
                "seed": c.seed,
                "status": c.status,
            }
            for c in cases
            if c.outcome == "missed_contradiction"
        ],
        "excluded_no_effect": [
            {
                "dataset_id": c.dataset_id,
                "corruption": c.corruption,
                "level": c.level,
                "seed": c.seed,
            }
            for c in cases
            if c.expectation == NO_EFFECT
        ],
        "sensitivity_failures": [
            {"dataset_id": s["dataset_id"], "curve": s["partial_corruption_sensitivity"]}
            for s in summaries
            if s["partial_corruption_sensitivity"]["ok"] is False
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=sorted(PROFILES), default="development")
    parser.add_argument("--out", type=Path, default=RESULTS)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    profile = PROFILES[args.profile]
    protocol = json.loads(PROTOCOL.read_text())
    manifest = load_manifest()
    data_dir = ROOT / manifest["download_directory"]

    datasets = [d for d in manifest["datasets"] if d["role"] in profile["roles"]]
    opened = [d["id"] for d in datasets if d["role"] in FORBIDDEN_ROLES]
    if opened:  # pragma: no cover - the profiles cannot select these
        raise SystemExit(f"refusing to run on held-out data: {', '.join(opened)}")

    policy = KeyValidationPolicy()
    if not args.quiet:
        print(
            f"profile {args.profile}: {len(datasets)} datasets, n_shuffles={profile['n_shuffles']}"
        )

    started = time.time()
    cases = build_cases(datasets, protocol, profile, policy, data_dir, progress=not args.quiet)
    summaries = dataset_summaries(cases)
    summary = overall(summaries, cases)
    env = environment(args.profile, profile)
    failures = collect_failures(cases, summaries)

    run = {
        "profile": args.profile,
        "protocol_version": protocol["protocol_version"],
        "manifest_version": manifest["manifest_version"],
        "paneldx_version": paneldx_version,
        "policy": {f: getattr(policy, f) for f in policy.__dataclass_fields__},
        "held_out_excluded": sorted(
            d["id"] for d in manifest["datasets"] if d["role"] in FORBIDDEN_ROLES
        ),
        "datasets": [d["id"] for d in datasets],
        "cases": len(cases),
        "cases_excluded_no_effect": sum(1 for c in cases if c.expectation == NO_EFFECT),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    write_results(args.out, run, cases, summaries, summary, env, failures)

    if not args.quiet:
        print(f"\n{len(cases)} cases in {run['elapsed_seconds']}s -> {args.out}")
        print(f"documented keys failed: {failures['false_rejections_on_documented_keys']}")
        print(f"unsafe acceptances: {len(failures['unsafe_acceptances'])}")
        rejections = len(failures["false_rejections_when_key_correct"])
        print(f"false rejections on correct keys: {rejections}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
