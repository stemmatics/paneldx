"""The benchmark runner: provenance, determinism and what it refuses to run.

The properties tested here are the ones a recorded result depends on: the same
inputs give the same digests, every case carries its provenance, and the
held-out split cannot be selected.
"""

from __future__ import annotations

import csv
import io
import json

import pandas as pd
import pytest

from validation.harness import cases as runner
from validation.harness.cases import (
    BROKEN_KEY,
    KEY_CORRECT,
    NO_EFFECT,
    PROFILES,
    STRUCTURAL,
    expectation_for,
    frame_sha256,
    outcome_of,
)
from validation.manifest import load_manifest

MANIFEST = load_manifest()
DATA = runner.ROOT / MANIFEST["download_directory"]
PROTOCOL = json.loads(runner.PROTOCOL.read_text())


def dataset(dataset_id: str) -> dict:
    return next(d for d in MANIFEST["datasets"] if d["id"] == dataset_id)


def smoke_profile() -> dict:
    return {**PROFILES["smoke"], "seeds": [0]}


needs_data = pytest.mark.skipif(
    not (DATA / "Grunfeld.csv").exists(), reason="run python -m scripts.fetch_validation_data first"
)


# --------------------------------------------------------------------------
# determinism and provenance
# --------------------------------------------------------------------------


@needs_data
def test_the_same_seed_rebuilds_the_same_cases():
    """The completion gate for the benchmark: identical inputs, identical
    output, down to the digest of every generated panel."""
    args = ([dataset("grunfeld")], PROTOCOL, smoke_profile(), runner.KeyValidationPolicy(), DATA)

    first = runner.build_cases(*args, progress=False)
    second = runner.build_cases(*args, progress=False)

    assert [c.generated_sha256 for c in first] == [c.generated_sha256 for c in second]
    assert [c.status for c in first] == [c.status for c in second]


@needs_data
def test_every_case_records_where_it_came_from():
    cases = runner.build_cases(
        [dataset("grunfeld")],
        PROTOCOL,
        smoke_profile(),
        runner.KeyValidationPolicy(),
        DATA,
        progress=False,
    )

    assert cases, "the smoke profile produced no cases"
    for case in cases:
        assert case.dataset_id == "grunfeld"
        assert case.family_id and case.role
        assert case.correct_key == "firm"
        assert len(case.source_sha256) == 64
        assert len(case.generated_sha256) == 64
        assert case.expectation in (BROKEN_KEY, STRUCTURAL, KEY_CORRECT, NO_EFFECT)


@needs_data
def test_the_uncorrupted_case_is_the_file_itself():
    cases = runner.build_cases(
        [dataset("grunfeld")],
        PROTOCOL,
        smoke_profile(),
        runner.KeyValidationPolicy(),
        DATA,
        progress=False,
    )
    baseline = next(c for c in cases if c.corruption == "none")

    assert baseline.generated_sha256 == baseline.source_sha256
    assert baseline.entities_affected == 0
    assert baseline.rows_affected == 0


@needs_data
def test_a_level_the_panel_cannot_express_is_recorded_as_no_effect():
    """Grunfeld has no invariant column, so removing one returns the panel
    unchanged. Counting that as a case would weight the panel twice."""
    cases = runner.build_cases(
        [dataset("grunfeld")],
        PROTOCOL,
        smoke_profile(),
        runner.KeyValidationPolicy(),
        DATA,
        progress=False,
    )
    removals = [c for c in cases if c.corruption == "invariant_column_removal"]

    assert removals
    assert all(c.expectation == NO_EFFECT for c in removals)
    assert all(c.columns_changed == 0 for c in removals)


@needs_data
def test_column_corruptions_that_repeat_a_lower_level_are_dropped():
    """Two levels that produce the same frame are one case, not two."""
    cases = runner.build_cases(
        [dataset("produc")],
        PROTOCOL,
        {**PROFILES["development"], "seeds": [0]},
        runner.KeyValidationPolicy(),
        DATA,
        progress=False,
    )
    for corruption in ("invariant_column_removal", "feature_poor_panel"):
        counted = [c for c in cases if c.corruption == corruption and c.expectation != NO_EFFECT]
        digests = [c.generated_sha256 for c in counted]
        assert len(digests) == len(set(digests)), corruption


def test_the_frame_digest_is_stable_and_content_dependent():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})

    assert frame_sha256(df) == frame_sha256(df.copy())
    assert frame_sha256(df) != frame_sha256(df.assign(a=[1, 3]))


# --------------------------------------------------------------------------
# what each case is allowed to report
# --------------------------------------------------------------------------


def test_duplicates_below_the_tolerance_leave_the_key_correct():
    """Duplicating half a percent of rows does not contradict anything, so a
    `fail` there would be a false rejection rather than a catch."""
    assert expectation_for("duplicate_entity_periods", 0.004, 0.01) == KEY_CORRECT


def test_duplicates_above_the_tolerance_are_a_contradiction():
    assert expectation_for("duplicate_entity_periods", 0.05, 0.01) == STRUCTURAL


def test_other_corruptions_keep_their_recorded_category():
    assert expectation_for("positional_rekey", 0.0, 0.01) == BROKEN_KEY
    assert expectation_for("feature_poor_panel", 0.0, 0.01) == KEY_CORRECT


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pass", "unsafe_acceptance"),
        ("warn", "unsafe_acceptance"),
        ("inconclusive", "safe_stop"),
        ("fail", "safe_stop"),
    ],
)
def test_a_broken_key_is_judged_on_safety_not_on_which_status(status, expected):
    assert outcome_of(BROKEN_KEY, status) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [("fail", "false_rejection"), ("pass", "no_false_rejection")],
)
def test_a_correct_key_may_be_anything_but_failed(status, expected):
    assert outcome_of(KEY_CORRECT, status) == expected


def test_a_contradiction_must_actually_be_detected():
    assert outcome_of(STRUCTURAL, "fail") == "detected"
    assert outcome_of(STRUCTURAL, "inconclusive") == "missed_contradiction"


# --------------------------------------------------------------------------
# the held-out split is unreachable
# --------------------------------------------------------------------------


def test_no_profile_selects_the_held_out_split():
    for name, profile in PROFILES.items():
        assert "held_out" not in profile["roles"], name


def test_the_runner_names_held_out_as_forbidden():
    assert "held_out" in runner.FORBIDDEN_ROLES


def test_the_recorded_run_shows_the_held_out_split_was_excluded():
    """The claim is only worth anything if the run itself records it."""
    path = runner.RESULTS / "run.json"
    if not path.exists():
        pytest.skip("no benchmark run recorded yet")

    excluded = json.loads(path.read_text())["held_out_excluded"]

    assert set(excluded) == {d["id"] for d in MANIFEST["datasets"] if d["role"] == "held_out"}


# --------------------------------------------------------------------------
# what the saved files actually contain
# --------------------------------------------------------------------------


def summary_fixture() -> list[dict]:
    """One dataset whose procedure-weighted rate differs from its case mix.

    Two procedures: one accepted 3 of 4, the other 0 of 4. Weighting the
    procedures equally gives 0.375; weighting the eight cases equally gives the
    same here, so a third procedure with a single accepted case pulls them
    apart: procedures 0.583, cases 0.444.
    """
    return [
        {
            "dataset_id": "example",
            "family_id": "example_family",
            "role": "development",
            "documented_key_status": "pass",
            "documented_key_reason": "supported",
            "false_rejection_on_documented_key": False,
            "broken_key_unsafe_acceptance": 0.5833333333333334,
            "inconclusive_rate": 0.25,
            "broken_key": {
                "pass": 2,
                "warn": 2,
                "inconclusive": 4,
                "fail": 1,
                "runs": 9,
                "unsafe_acceptance_rate": 0.4444444444444444,
                "safe_stop_rate": 0.5555555555555556,
            },
            "broken_key_by_corruption": {"entity_merge": {"runs": 4}},
            "broken_key_by_level": {"entity_merge": {"0.1": {"runs": 4}}},
            "correct_key_degraded": {},
            "structural": {},
            "false_rejections_when_key_correct": 0,
            "unsafe_acceptances_when_key_broken": 4,
            "missed_contradictions": 0,
            "partial_corruption_sensitivity": {"ok": True},
            "median_runtime_seconds": 0.01,
            "cases": 10,
        }
    ]


def test_the_csv_publishes_the_procedure_weighted_rates():
    """The CSV used to carry the case-weighted rate, so it disagreed with
    overall_summary.json for every dataset where the two differ."""
    rows = list(csv.DictReader(io.StringIO(runner._summary_csv(summary_fixture()))))

    assert len(rows) == 1
    assert float(rows[0]["broken_key_unsafe_acceptance_rate"]) == pytest.approx(0.5833333)
    assert float(rows[0]["inconclusive_rate"]) == pytest.approx(0.25)
    # The case-weighted figure the counts imply is a different number, and is
    # not what this column reports.
    assert float(rows[0]["broken_key_unsafe_acceptance_rate"]) != pytest.approx(0.4444444)


def test_the_csv_keeps_the_counts_beside_the_rates():
    rows = list(csv.DictReader(io.StringIO(runner._summary_csv(summary_fixture()))))

    assert [int(rows[0][f]) for f in ("broken_key_pass", "broken_key_warn")] == [2, 2]
    assert int(rows[0]["broken_key_inconclusive"]) == 4
    assert int(rows[0]["broken_key_fail"]) == 1


def test_the_saved_json_keeps_the_nested_breakdowns(tmp_path):
    """The CSV is flat; the per-procedure and per-level detail the protocol
    publishes only survives in the JSON."""
    summaries = summary_fixture()
    runner.write_results(
        tmp_path,
        run={"profile": "smoke"},
        cases=[],
        summaries=summaries,
        summary={},
        env={},
        failures={},
    )
    saved = json.loads((tmp_path / "dataset_summary.json").read_text())

    assert saved == summaries
    assert saved[0]["broken_key_by_corruption"]
    assert saved[0]["broken_key_by_level"]
    assert "inconclusive_rate" in saved[0]
    assert "broken_key_unsafe_acceptance" in saved[0]


def test_the_committed_summary_csv_matches_the_committed_json():
    """A drift between the two is how the wrong rate went unnoticed."""
    directory = runner.RESULTS.parent / "v0.5.0"
    if not (directory / "dataset_summary.json").exists():
        pytest.skip("no benchmark run recorded yet")

    saved = json.loads((directory / "dataset_summary.json").read_text())
    rows = list(csv.DictReader((directory / "dataset_summary.csv").open()))
    by_id = {s["dataset_id"]: s for s in saved}

    assert len(rows) == len(saved)
    for row in rows:
        expected = by_id[row["dataset_id"]]
        assert float(row["broken_key_unsafe_acceptance_rate"]) == pytest.approx(
            expected["broken_key_unsafe_acceptance"]
        )
        assert float(row["inconclusive_rate"]) == pytest.approx(expected["inconclusive_rate"])
