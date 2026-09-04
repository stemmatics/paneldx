"""Aggregation and uncertainty for the corruption benchmark.

The rules under test are the ones that decide whether a published rate means
anything: no severity ranking, counts always beside rates, and the family as
the unit that intervals are computed over.
"""

from __future__ import annotations

import pytest

from validation.harness import metrics


def test_status_counts_covers_every_status():
    assert metrics.status_counts(["pass", "fail", "fail"]) == {
        "pass": 1,
        "warn": 0,
        "inconclusive": 0,
        "fail": 2,
    }


def test_status_counts_rejects_an_unknown_status():
    with pytest.raises(ValueError, match="unknown status"):
        metrics.status_counts(["pass", "probably"])


def test_rates_are_returned_beside_the_counts_that_produced_them():
    """A rate alone cannot tell a tool that rejected a broken key from one that
    declined to look at it."""
    summary = metrics.summarise(["pass", "warn", "inconclusive", "fail"])

    assert summary["pass"] == summary["warn"] == summary["inconclusive"] == summary["fail"] == 1
    assert summary["runs"] == 4
    assert summary["unsafe_acceptance_rate"] == 0.5
    assert summary["safe_stop_rate"] == 0.5


def test_the_two_rates_partition_the_statuses():
    summary = metrics.summarise(["pass", "pass", "inconclusive", "fail", "warn"])

    assert summary["unsafe_acceptance_rate"] + summary["safe_stop_rate"] == 1.0


def test_an_empty_run_reports_no_rate_rather_than_zero():
    summary = metrics.summarise([])

    assert summary["runs"] == 0
    assert summary["unsafe_acceptance_rate"] is None


def test_inconclusive_counts_as_a_safe_stop_not_an_acceptance():
    assert metrics.summarise(["inconclusive"] * 4)["unsafe_acceptance_rate"] == 0.0


def test_datasets_collapse_to_one_value_per_family():
    """Two panels from one survey are one observation, not two."""
    values = {"wages": 1.0, "laborsupply": 0.0, "cigar": 0.5}
    families = {"wages": "psid", "laborsupply": "psid", "cigar": "tobacco"}

    assert metrics.by_family(values, families) == {"psid": 0.5, "tobacco": 0.5}


def test_families_ignore_missing_values():
    values = {"a": None, "b": 0.4}

    assert metrics.by_family(values, {"a": "f", "b": "f"}) == {"f": 0.4}


def test_the_bootstrap_is_deterministic_under_a_seed():
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    first = metrics.bootstrap_interval(values, n_resamples=500, seed=1)
    second = metrics.bootstrap_interval(values, n_resamples=500, seed=1)

    assert first == second
    assert first["k"] == 6
    assert first["low"] <= first["point"] <= first["high"]


def test_one_family_gets_a_point_and_no_interval():
    """With a single family there is nothing to resample, and an interval
    printed anyway would be a fabrication."""
    interval = metrics.bootstrap_interval([0.25])

    assert interval == {"point": 0.25, "low": None, "high": None, "k": 1, "n_resamples": 0}


def test_no_families_gives_no_point():
    assert metrics.bootstrap_interval([])["point"] is None


def test_fewer_families_gives_a_wider_interval():
    narrow = metrics.bootstrap_interval([0.4, 0.5, 0.6] * 6, n_resamples=4000, seed=0)
    wide = metrics.bootstrap_interval([0.4, 0.5, 0.6], n_resamples=4000, seed=0)

    assert (wide["high"] - wide["low"]) > (narrow["high"] - narrow["low"])


def test_wilson_interval_brackets_the_point():
    interval = metrics.wilson_interval(1, 6)

    assert interval["point"] == pytest.approx(1 / 6)
    assert 0 < interval["low"] < interval["point"] < interval["high"] < 1
    assert interval["n"] == 6


def test_wilson_interval_stays_inside_zero_and_one():
    assert metrics.wilson_interval(0, 6)["low"] == 0.0
    assert metrics.wilson_interval(6, 6)["high"] == 1.0


def test_wilson_interval_on_nothing_reports_nothing():
    assert metrics.wilson_interval(0, 0)["point"] is None


def test_wilson_interval_rejects_impossible_counts():
    with pytest.raises(ValueError, match="7 successes out of 6"):
        metrics.wilson_interval(7, 6)


def test_wilson_interval_rejects_a_confidence_with_no_recorded_z():
    with pytest.raises(ValueError, match="no z value"):
        metrics.wilson_interval(1, 6, confidence=0.9)


def test_sensitivity_accepts_a_curve_that_falls():
    result = metrics.sensitivity({0.1: 0.8, 0.25: 0.4, 0.5: 0.0})

    assert result["monotone"] and result["moves"] and result["ok"]


def test_a_flat_curve_is_a_reported_failure_not_a_pass():
    """A diagnostic whose answer never changes as damage grows has not been
    shown to be sensitive to damage."""
    result = metrics.sensitivity({0.1: 0.0, 0.25: 0.0, 0.5: 0.0})

    assert result["monotone"] is True
    assert result["moves"] is False
    assert result["ok"] is False


def test_a_rising_curve_fails():
    result = metrics.sensitivity({0.1: 0.0, 0.25: 0.5})

    assert result["monotone"] is False
    assert result["ok"] is False


def test_a_single_level_cannot_be_judged():
    assert metrics.sensitivity({0.1: 0.5})["ok"] is None


def _measurement(expectation, corruption="partial_corruption", evidence_frac=0.5):
    from validation.harness import calibration

    return calibration.Measurement(
        dataset_id="d",
        family_id="f",
        corruption=corruption,
        level=0.1,
        seed=0,
        expectation=expectation,
        duplicate_rate=0.0,
        n_entities=40,
        n_transitions=40,
        n_invariant_cols=1,
        evidence_frac=evidence_frac,
        gap=0.4,
        measured=True,
    )


def test_calibration_counts_attempted_measured_and_excluded_separately():
    """Exercises the production helper the result is written from. Computing
    these at the call site is how the excluded count came to be taken from a
    list the exclusions had already been removed from."""
    from validation.harness import calibration
    from validation.harness.cases import KEY_CORRECT, NO_EFFECT

    counts = calibration.case_counts(
        [
            _measurement(KEY_CORRECT, "none"),
            _measurement(NO_EFFECT, "invariant_column_removal"),
            _measurement(NO_EFFECT, "invariant_column_removal"),
        ]
    )

    assert counts == {
        "cases_attempted": 3,
        "cases_measured": 1,
        "cases_excluded_no_effect": 2,
    }


def test_calibration_counts_are_zero_for_no_measurements():
    from validation.harness import calibration

    assert calibration.case_counts([]) == {
        "cases_attempted": 0,
        "cases_measured": 0,
        "cases_excluded_no_effect": 0,
    }


def test_the_saved_calibration_counts_are_consistent():
    """The committed record must satisfy attempted = measured + excluded."""
    import json

    from validation.manifest import ROOT

    path = ROOT / "validation" / "results" / "calibration" / "v0.5.0" / "calibration.json"
    if not path.exists():
        import pytest

        pytest.skip("no calibration result recorded yet")
    saved = json.loads(path.read_text())

    assert saved["cases_attempted"] == saved["cases_measured"] + saved["cases_excluded_no_effect"]
    assert saved["cases_excluded_no_effect"] > 0


def test_calibration_does_not_score_excluded_cases():
    from validation.harness import calibration
    from validation.harness.cases import BROKEN_KEY, NO_EFFECT

    grid = {
        "fixed": {"duplicate_cell_rate": 0.01, "minimum_steps": 20},
        "baseline_defaults": {
            "minimum_entities": 20,
            "minimum_null_gap": 0.05,
            "supported_evidence_fraction": 0.4,
            "weak_evidence_fraction": 0.15,
        },
    }
    thresholds = dict(grid["baseline_defaults"])

    # The excluded case would be accepted if it were scored, so its presence
    # must not move the rate.
    without = calibration.score([_measurement(BROKEN_KEY, evidence_frac=0.0)], thresholds, grid)
    with_excluded = calibration.score(
        [_measurement(BROKEN_KEY, evidence_frac=0.0), _measurement(NO_EFFECT, evidence_frac=0.9)],
        thresholds,
        grid,
    )

    assert without["unsafe_acceptance"] == with_excluded["unsafe_acceptance"] == 0.0


def test_the_headline_rate_does_not_move_when_one_procedure_gains_levels():
    """The point of procedure weighting: a procedure that declares more levels
    must not thereby count for more."""
    balanced = {"a": ["fail", "pass"], "b": ["fail", "fail"]}
    a_has_more_levels = {"a": ["fail", "pass"] * 5, "b": ["fail", "fail"]}

    assert metrics.unsafe_acceptance(balanced) == metrics.unsafe_acceptance(a_has_more_levels)
    assert metrics.unsafe_acceptance(balanced) == 0.25


def test_case_weighting_would_move_under_the_same_change():
    """The contrast that makes the previous test meaningful."""
    balanced = ["fail", "pass", "fail", "fail"]
    a_has_more_levels = ["fail", "pass"] * 5 + ["fail", "fail"]

    assert metrics.summarise(balanced)["unsafe_acceptance_rate"] == 0.25
    assert metrics.summarise(a_has_more_levels)["unsafe_acceptance_rate"] != 0.25


def test_the_inconclusive_rate_uses_the_same_weighting():
    balanced = {"a": ["inconclusive", "pass"], "b": ["inconclusive", "inconclusive"]}
    a_has_more_levels = {"a": ["inconclusive", "pass"] * 5, "b": ["inconclusive", "inconclusive"]}

    assert metrics.inconclusive_rate(balanced) == metrics.inconclusive_rate(a_has_more_levels)
    assert metrics.inconclusive_rate(balanced) == 0.75
