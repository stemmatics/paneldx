"""Regression tests for repository quality-gate helpers."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import audit_dependencies
from scripts.fetch_validation_data import check_manifest


def valid_panel() -> dict[str, object]:
    return {
        "name": "example",
        "file": "example.csv",
        "source_url": "https://example.test/example.csv",
        "sha256": "a" * 64,
        "key": ["entity_id"],
        "time": "period",
        "expected_status": "pass",
        "expected_entities": 2,
    }


def test_manifest_accepts_a_complete_safe_panel():
    assert check_manifest([valid_panel()]) == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sha256", "not-a-digest", "sha256 must be"),
        ("file", "../../etc/passwd", "unsafe file name"),
        ("source_url", "http://example.test/data.csv", "absolute https URL"),
        ("key", [], "non-empty list"),
        ("expected_entities", 0, "positive integer"),
    ],
)
def test_manifest_rejects_unsafe_or_invalid_fields(field, value, message):
    panel = valid_panel()
    panel[field] = value

    assert any(message in problem for problem in check_manifest([panel]))


def test_manifest_rejects_duplicate_names_and_files():
    first = valid_panel()
    second = deepcopy(first)

    problems = check_manifest([first, second])

    assert "duplicate name: example" in problems
    assert "duplicate file: example.csv" in problems


class FakeMetadata(dict):
    def get_all(self, key: str):
        return self.get(key)


class FakeDistribution:
    def __init__(self, name: str, version: str, requires: list[str], extras: tuple[str, ...] = ()):
        self.metadata = FakeMetadata({"Name": name, "Provides-Extra": list(extras)})
        self.version = version
        self.requires = requires


def test_shipped_closure_excludes_dev_dependencies(monkeypatch):
    distributions = {
        "paneldx": FakeDistribution(
            "paneldx",
            "0.4.0",
            [
                "numpy>=1.21",
                "openpyxl; extra == 'excel'",
                "pyarrow>=23; extra == 'parquet'",
                "pytest; extra == 'dev'",
            ],
            extras=("excel", "parquet", "dev"),
        ),
        "numpy": FakeDistribution("numpy", "2.0.0", []),
        "openpyxl": FakeDistribution("openpyxl", "3.1.5", []),
        "pyarrow": FakeDistribution("pyarrow", "23.0.1", []),
        "pytest": FakeDistribution("pytest", "9.0.0", []),
    }

    monkeypatch.setattr(audit_dependencies.metadata, "distribution", distributions.__getitem__)

    assert audit_dependencies.shipped_closure("paneldx") == {
        "numpy": "2.0.0",
        "openpyxl": "3.1.5",
        "pyarrow": "23.0.1",
    }
