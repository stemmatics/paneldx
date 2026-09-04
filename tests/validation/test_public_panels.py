"""Public panels run through `validate_key` on their documented entity key.

Two files meet here, and they record different things:

  * `validation/manifests/datasets.json` records what is true about each dataset — its
    source, licence, documented entity key, and how that key is known to be
    correct, all established without reference to anything paneldx reports.
  * `tests/validation/expected_results.json` records what paneldx says today.

These are regression expectations, not scientific truth. Produc is a known
false rejection and is kept for exactly that reason; see the protocol in
`validation/protocol/protocol.md`.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from paneldx import validate_key
from validation.manifest import ROOT, load_manifest

HERE = Path(__file__).parent
MANIFEST = load_manifest()
DATA = ROOT / MANIFEST["download_directory"]
EXPECTED = json.loads((HERE / "expected_results.json").read_text())["results"]

# Development panels only. Calibration verdicts belong to the benchmark, not to
# a regression file, and the held-out split is not touched by any test.
PANELS = [
    dataset
    for dataset in MANIFEST["datasets"]
    if dataset["access"] == "public" and dataset["role"] == "development"
]


def test_every_development_panel_has_a_recorded_expectation():
    development = {d["id"] for d in PANELS}
    assert development == set(EXPECTED), "datasets.json and expected_results.json disagree"


def test_no_test_touches_the_held_out_split():
    held_out = {d["id"] for d in MANIFEST["datasets"] if d["role"] == "held_out"}
    assert held_out, "the held-out split should be registered by now"
    assert not held_out & set(EXPECTED)
    assert not held_out & {d["id"] for d in PANELS}


@pytest.mark.parametrize("dataset", PANELS, ids=[d["id"] for d in PANELS])
def test_documented_key(dataset):
    path = DATA / dataset["file"]
    if not path.exists():
        pytest.skip("run python -m scripts.fetch_validation_data first")

    df = pd.read_csv(path).drop(columns=dataset.get("drop_columns", []))
    report = validate_key(df, dataset["entity_key"], dataset["time_column"])
    expected = EXPECTED[dataset["id"]]

    assert report.status == expected["status"]
    assert report.n_entities == expected["n_entities"]


@pytest.mark.parametrize("dataset", PANELS, ids=[d["id"] for d in PANELS])
def test_file_matches_the_documented_shape(dataset):
    """The documented key is only 'known correct' while the file still matches
    the shape the upstream documentation describes."""
    path = DATA / dataset["file"]
    if not path.exists():
        pytest.skip("run python -m scripts.fetch_validation_data first")

    df = pd.read_csv(path).drop(columns=dataset.get("drop_columns", []))
    shape = dataset["shape"]
    key, time = dataset["entity_key"], dataset["time_column"]

    assert len(df) == shape["rows"]
    assert df.shape[1] == shape["columns_after_drop"]
    assert df.groupby(key, sort=False).ngroups == shape["entities"]
    assert df[time].nunique() == shape["periods"]
    assert not df.duplicated([*key, time]).any()
