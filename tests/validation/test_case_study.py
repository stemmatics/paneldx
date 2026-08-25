"""The PopNet reanalysis, run only when the authorised workbook is available."""

import importlib.util
import os
from pathlib import Path

import pandas as pd
import pytest

DATA = os.environ.get("PANELDX_POPNET_DATA")
STUDY = Path(__file__).resolve().parents[2] / "case_studies" / "popnet_reanalysis"

pytestmark = pytest.mark.skipif(not DATA, reason="PANELDX_POPNET_DATA is not set")


def load(name):
    spec = importlib.util.spec_from_file_location(name, STUDY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_positional_key_fails_and_recovered_key_passes():
    prepare, audit_panel = load("prepare_data"), load("audit_panel")
    df = prepare.add_positional_id(pd.read_excel(DATA))
    results = audit_panel.audit(df, "time")
    assert results["positional_key"].status == "fail"
    assert results["recovered_key"].status == "pass"
