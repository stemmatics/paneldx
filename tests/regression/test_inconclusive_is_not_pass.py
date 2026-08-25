"""Insufficient evidence is reported as inconclusive, never as a pass."""

import numpy as np
import pandas as pd

from paneldx import audit, target_leakage, to_html, validate_key
from paneldx.cli import main
from paneldx.status import worst


def tiny_panel(n_entities=2, n_periods=2):
    rng = np.random.default_rng(0)
    frames = []
    for t in range(n_periods):
        frames.append(
            pd.DataFrame(
                {
                    "id": np.arange(n_entities),
                    "t": t,
                    "attr": np.arange(n_entities) + 100,
                    "y": rng.normal(size=n_entities),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_worst_ordering():
    assert worst(["pass", "warn"]) == "warn"
    assert worst(["pass", "inconclusive", "warn"]) == "inconclusive"
    assert worst(["inconclusive", "fail"]) == "fail"
    # No checks having run is not the same as every check passing.
    assert worst([]) == "inconclusive"


def test_two_entities_is_inconclusive_not_pass():
    res = audit(tiny_panel(), "t", key="id")
    assert res.chosen.status == "inconclusive"
    assert res.worst == "inconclusive"
    assert not any(f.status == "pass" for f in res.findings)


def test_diagnostics_do_not_run_under_an_unjudged_key():
    res = audit(tiny_panel(), "t", key="id", target="y")
    assert res.counters is None
    assert res.baseline is None


def test_single_period_is_inconclusive():
    rep = validate_key(tiny_panel(n_entities=50, n_periods=1), "id", "t")
    assert rep.status == "inconclusive"
    assert "period" in rep.verdict


def test_no_evidence_columns_is_inconclusive():
    df = tiny_panel(n_entities=50)
    df["attr"] = 1
    df = df.drop(columns="y")
    rep = validate_key(df, "id", "t")
    assert rep.status == "inconclusive"


def test_leakage_with_too_few_rows_is_inconclusive():
    rep = target_leakage(tiny_panel(), "y")
    assert rep.status == "inconclusive"


def test_audit_leakage_without_usable_features_is_inconclusive():
    df = tiny_panel().drop(columns="attr")
    res = audit(df, "t", key="id", target="y")
    assert any(f.code == "leakage_inconclusive" for f in res.findings)
    assert not any(f.code == "leakage_clean" for f in res.findings)


def test_constant_target_leakage_is_inconclusive():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"a": rng.normal(size=100), "b": rng.normal(size=100)})
    df["y"] = 5.0
    rep = target_leakage(df, "y")
    assert rep.status == "inconclusive"
    assert "nothing to predict" not in rep.verdict


def test_cli_exits_2_on_inconclusive(tmp_path, capsys):
    path = tmp_path / "tiny.csv"
    tiny_panel().to_csv(path, index=False)
    code = main(["audit", str(path), "--time", "t", "--key", "id"])
    assert code == 2
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_html_does_not_show_pass_when_inconclusive():
    html = to_html(audit(tiny_panel(), "t", key="id"))
    assert "All completed checks passed" not in html
    assert "was inconclusive" in html


def test_discovery_on_a_tiny_panel_is_inconclusive():
    res = audit(tiny_panel(), "t")
    assert res.worst == "inconclusive"
    assert any(f.code == "discovery_inconclusive" for f in res.findings)


def test_single_period_discovery_is_inconclusive():
    res = audit(tiny_panel(n_entities=50, n_periods=1), "t")
    assert res.worst == "inconclusive"
    assert any(f.code == "discovery_inconclusive" for f in res.findings)


def test_cli_discovery_exits_2_on_a_tiny_panel(tmp_path, capsys):
    path = tmp_path / "tiny.csv"
    tiny_panel().to_csv(path, index=False)
    assert main(["audit", str(path), "--time", "t", "--quiet"]) == 2


def test_duplicates_fail_even_with_too_few_entities():
    df = tiny_panel()
    dup = pd.concat([df, df], ignore_index=True)
    assert validate_key(dup, "id", "t").status == "fail"


def test_untestable_counters_are_surfaced():
    rng = np.random.default_rng(3)
    frames = []
    for t in range(2):
        frames.append(
            pd.DataFrame(
                {
                    "id": np.arange(30),
                    "t": t,
                    "label": [f"L{i}" for i in range(30)],
                    "noise": rng.normal(size=30),
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    res = audit(df, "t", key="id")
    assert res.counters is not None
    assert res.counters.status == "inconclusive"
    assert any(f.code == "counters_inconclusive" for f in res.findings)
