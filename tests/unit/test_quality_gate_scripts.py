"""Regression tests for repository quality-gate helpers.

The validation-data manifest and downloader have their own suite in
tests/unit/test_validation_manifest.py.
"""

from __future__ import annotations

from scripts import audit_dependencies


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


def test_the_repository_has_no_unsuppressed_complexity_violations():
    """The same gate CI runs, so a new over-complex function fails here first."""
    from scripts import check_complexity

    assert check_complexity.main([]) == 0


def test_the_complexity_gate_reads_its_thresholds_from_the_config(tmp_path):
    from scripts import check_complexity

    config = tmp_path / ".slopconfig.yaml"
    config.write_text(
        "patterns:\n"
        "  god_function:\n"
        "    complexity_threshold: 5\n"
        "    lines_threshold: 10\n"
        "  god_function_suppressions:\n"
        "    - a/b.py::c\n"
    )

    assert check_complexity.read_config(config) == (5, 10, {"a/b.py::c"})


def test_the_complexity_gate_needs_thresholds(tmp_path):
    import pytest

    from scripts import check_complexity

    config = tmp_path / ".slopconfig.yaml"
    config.write_text("patterns: {}\n")

    with pytest.raises(SystemExit, match="declares no god_function thresholds"):
        check_complexity.read_config(config)
