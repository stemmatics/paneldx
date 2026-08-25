"""Public panels with a documented entity key.

The expected values are what paneldx reports on each dataset today, recorded
so that a change in behaviour is visible. They are not claims that the tool
is right: Produc is a known false negative and is kept for that reason.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from paneldx import validate_key

HERE = Path(__file__).parent
CASES = json.loads((HERE / "panels.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_documented_key(case):
    path = HERE / "data" / case["file"]
    if not path.exists():
        pytest.skip("run scripts/fetch_validation_data.py first")
    df = pd.read_csv(path).drop(columns=case.get("drop_columns", []))
    rep = validate_key(df, case["key"], case["time"])
    assert rep.status == case["expected_status"]
    assert rep.n_entities == case["expected_entities"]
