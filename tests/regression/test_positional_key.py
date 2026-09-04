"""A key assigned by row position within each period links different entities.

See the README case study.
"""

from paneldx import audit, persistence_baseline, validate_key
from paneldx.cli import main
from tests.factories import make_panel


def positionally_linked(df):
    out = df.sort_values(["period", "total_spend"], ascending=[True, False]).reset_index(drop=True)
    out["positional_id"] = out.groupby("period").cumcount()
    return out.drop(columns=["uid"])


def test_positional_key_is_never_accepted():
    """A positional key is never returned as usable.

    With no declared domain knowledge the data shows an absence of evidence
    rather than a contradiction, so the status is `inconclusive`.
    """
    rep = validate_key(positionally_linked(make_panel()), "positional_id", "period")

    assert rep.status not in ("pass", "warn")
    assert rep.status == "inconclusive"
    assert rep.reason == "insufficient_evidence"
    assert not rep.invariant_cols


def test_a_declared_invariant_turns_the_positional_key_into_a_contradiction():
    """Domain knowledge is what upgrades "cannot tell" to "this is wrong".

    Nobody's birth year changes, so a key under which it does is contradicted
    by the data rather than merely unsupported by it.
    """
    rep = validate_key(
        positionally_linked(make_panel()),
        "positional_id",
        "period",
        invariant_cols=["birth_year"],
    )

    assert rep.status == "fail"
    assert rep.reason == "declared_invariant_broken"
    assert rep.declared_violations["birth_year"] > 0.9


def test_a_declared_counter_that_falls_is_a_contradiction():
    rep = validate_key(
        positionally_linked(make_panel()),
        "positional_id",
        "period",
        monotone_cols=["total_visits"],
    )

    assert rep.status == "fail"
    assert rep.reason == "declared_monotone_broken"


def test_the_correct_key_survives_the_same_declarations():
    rep = validate_key(
        make_panel(),
        "uid",
        "period",
        invariant_cols=["birth_year", "region"],
        monotone_cols=["total_visits", "total_spend"],
    )

    assert rep.status == "pass"
    assert rep.reason == "supported"
    assert rep.declared_violations == {}


def test_audit_reports_the_key_as_unjudgeable():
    res = audit(positionally_linked(make_panel()), "period", key="positional_id")

    assert res.worst == "inconclusive"
    assert any(f.code == "key_inconclusive" for f in res.findings)


def test_audit_reports_a_contradiction_when_an_invariant_is_declared():
    res = audit(
        positionally_linked(make_panel()),
        "period",
        key="positional_id",
        invariant_cols=["birth_year"],
    )

    assert res.worst == "fail"
    assert any(f.code == "key_contradicted" for f in res.findings)


def test_broken_key_deflates_the_baseline_so_the_audit_skips_it():
    df = make_panel()
    good = audit(df, "period", key="uid", target="total_visits")
    assert good.baseline.persistence_r2 > 0.95

    broken = positionally_linked(df)
    raw = persistence_baseline(broken, "positional_id", "period", "total_visits")
    assert raw.persistence_r2 < good.baseline.persistence_r2 - 0.3

    bad = audit(broken, "period", key="positional_id", target="total_visits")
    assert bad.baseline is None
    assert bad.counters is None


def test_cli_refuses_a_positional_key(tmp_path, capsys):
    """Exit 2, not 0: a pipeline gated on this command still refuses to train."""
    path = tmp_path / "panel.csv"
    positionally_linked(make_panel()).to_csv(path, index=False)

    code = main(["audit", str(path), "--time", "period", "--key", "positional_id"])

    assert code == 2
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_cli_exits_1_when_a_declared_invariant_is_broken(tmp_path, capsys):
    path = tmp_path / "panel.csv"
    positionally_linked(make_panel()).to_csv(path, index=False)

    code = main(
        [
            "audit",
            str(path),
            "--time",
            "period",
            "--key",
            "positional_id",
            "--invariant",
            "birth_year",
        ]
    )

    assert code == 1
    assert "FAIL" in capsys.readouterr().out
