"""A key assigned by row position within each period links different entities.

See the README case study.
"""

from factories import make_panel

from paneldx import audit, persistence_baseline, validate_key
from paneldx.cli import main


def positionally_linked(df):
    out = df.sort_values(["period", "total_spend"], ascending=[True, False]).reset_index(drop=True)
    out["positional_id"] = out.groupby("period").cumcount()
    return out.drop(columns=["uid"])


def test_positional_key_is_rejected():
    rep = validate_key(positionally_linked(make_panel()), "positional_id", "period")
    assert rep.status == "fail"
    assert not rep.invariant_cols


def test_audit_reports_the_key_as_unsupported():
    res = audit(positionally_linked(make_panel()), "period", key="positional_id")
    assert res.worst == "fail"
    assert any(f.code == "key_unsupported" for f in res.findings)


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


def test_cli_exits_1(tmp_path, capsys):
    path = tmp_path / "panel.csv"
    positionally_linked(make_panel()).to_csv(path, index=False)
    code = main(["audit", str(path), "--time", "period", "--key", "positional_id"])
    assert code == 1
    assert "FAIL" in capsys.readouterr().out
