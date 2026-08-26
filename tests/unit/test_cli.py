import sys

import pytest
from factories import make_panel

from paneldx.cli import main


def write(df, path, fmt):
    if fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "tsv":
        df.to_csv(path, sep="\t", index=False)
    elif fmt == "json":
        df.to_json(path)
    elif fmt == "parquet":
        pytest.importorskip("pyarrow")
        df.to_parquet(path, index=False)
    elif fmt == "feather":
        pytest.importorskip("pyarrow")
        df.to_feather(path)
    elif fmt == "xlsx":
        pytest.importorskip("openpyxl")
        df.to_excel(path, index=False)


@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "parquet", "feather", "xlsx"])
def test_each_loader_round_trips(tmp_path, fmt):
    if fmt in {"parquet", "feather"} and sys.version_info < (3, 10):
        pytest.skip("Parquet and Feather require Python 3.10+")
    path = tmp_path / f"panel.{fmt}"
    write(make_panel(), path, fmt)
    assert main(["audit", str(path), "--time", "period", "--key", "uid", "--quiet"]) == 0


@pytest.mark.skipif(sys.version_info >= (3, 10), reason="Python 3.10+ supports Parquet")
@pytest.mark.parametrize("suffix", [".parquet", ".feather"])
def test_parquet_and_feather_are_rejected_on_python_39(tmp_path, suffix):
    path = tmp_path / f"panel{suffix}"
    path.write_text("not a dataset")

    with pytest.raises(SystemExit, match="requires Python 3.10"):
        main(["audit", str(path), "--time", "period"])


def test_html_is_written(tmp_path):
    path = tmp_path / "panel.csv"
    make_panel().to_csv(path, index=False)
    out = tmp_path / "report.html"
    code = main(
        ["audit", str(path), "--time", "period", "--key", "uid", "--html", str(out), "--quiet"]
    )
    assert code == 0
    assert out.exists() and out.stat().st_size > 1000


def test_unreadable_format_is_rejected(tmp_path):
    path = tmp_path / "panel.xyz"
    path.write_text("nope")
    with pytest.raises(SystemExit, match="don't know how to read"):
        main(["audit", str(path), "--time", "period"])


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(SystemExit, match="no such file"):
        main(["audit", str(tmp_path / "ghost.csv"), "--time", "period"])


def test_bad_input_has_no_traceback(tmp_path):
    path = tmp_path / "panel.csv"
    make_panel(n_entities=30).to_csv(path, index=False)
    with pytest.raises(SystemExit) as exc:
        main(["audit", str(path), "--time", "nope"])
    assert "paneldx:" in str(exc.value)
    assert "Traceback" not in str(exc.value)
