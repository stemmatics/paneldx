"""The one command that says whether a checkout can reproduce the validation run.

It has to be trustworthy in both directions: silent when the environment really
is the recorded one, and specific about which part is wrong when it is not.
"""

from __future__ import annotations

import hashlib
import json
import sys
from importlib import metadata

import pytest

from scripts import check_validation_setup as setup
from tests.unit.test_validation_manifest import (
    CONTENT,
    manifest_of,
    public_dataset,
    restricted_dataset,
)

RUNNING_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
PYTEST_VERSION = metadata.version("pytest")


def protocol_of(**overrides) -> dict:
    protocol = {
        "protocol_version": "1.1.0",
        "status": "frozen",
        "frozen_on": "2026-09-04",
        "baseline": {"release": "0.4.0"},
        "splits": {"development": ["example"], "case_study": ["restricted-example"]},
        "environment": {"python": RUNNING_PYTHON},
    }
    protocol.update(overrides)
    return protocol


def document_of(protocol: dict) -> str:
    """The parts of protocol.md that check_documents reads."""
    status = protocol.get("status")
    state = f"frozen {protocol.get('frozen_on')}" if status == "frozen" else "DRAFT"
    return (
        f"# Validation protocol\n\n"
        f"**Protocol version {protocol['protocol_version']} — {state}. "
        f"Baseline: paneldx {protocol['baseline']['release']}.**\n"
    )


@pytest.fixture
def document(tmp_path, monkeypatch):
    """Write a protocol.md matching whatever protocol is passed to it."""

    def write(protocol: dict, text: str | None = None):
        path = tmp_path / "protocol.md"
        path.write_text(document_of(protocol) if text is None else text)
        monkeypatch.setattr(setup, "PROTOCOL_DOCUMENT", path)
        return path

    return write


# --------------------------------------------------------------------------
# protocol.md and protocol.json agreement
# --------------------------------------------------------------------------


def test_the_repository_protocol_documents_agree():
    """The shipped pair has to satisfy the rule the tests below enforce."""
    protocol = json.loads(setup.PROTOCOL.read_text())

    assert setup.check_documents(protocol) == []


def test_matching_documents_agree(document):
    protocol = protocol_of()
    document(protocol)

    assert setup.check_documents(protocol) == []


def test_a_matching_draft_pair_agrees(document):
    protocol = protocol_of(status="draft", frozen_on=None)
    document(protocol)

    assert setup.check_documents(protocol) == []


def test_a_version_mismatch_is_reported(document):
    document(protocol_of())

    problems = setup.check_documents(protocol_of(protocol_version="2.0.0"))

    assert any("does not state protocol version 2.0.0" in problem for problem in problems)


def test_a_freeze_date_mismatch_is_reported(document):
    document(protocol_of())

    problems = setup.check_documents(protocol_of(frozen_on="2027-01-01"))

    assert any("does not state the freeze date 2027-01-01" in problem for problem in problems)


def test_a_frozen_protocol_with_no_date_is_reported(document):
    protocol = protocol_of(frozen_on=None)
    document(protocol_of())

    problems = setup.check_documents(protocol)

    assert "protocol.json is frozen but records no frozen_on date" in problems


def test_a_document_still_marked_draft_is_reported(document):
    protocol = protocol_of()
    document(protocol, text=document_of(protocol_of(status="draft", frozen_on=None)))

    problems = setup.check_documents(protocol)

    assert any("still says DRAFT" in problem for problem in problems)


def test_a_draft_that_records_a_freeze_date_is_reported(document):
    protocol = protocol_of(status="draft")
    document(protocol_of(status="draft", frozen_on=None))

    problems = setup.check_documents(protocol)

    assert any("is a draft but records frozen_on" in problem for problem in problems)


def test_a_draft_whose_document_does_not_say_so_is_reported(document):
    protocol = protocol_of(status="draft", frozen_on=None)
    document(protocol, text=document_of(protocol_of()))

    problems = setup.check_documents(protocol)

    assert any("is a draft but" in problem and "does not say so" in problem for problem in problems)


@pytest.mark.parametrize("status", [None, "final", "", "FROZEN"])
def test_an_unknown_status_is_reported(document, status):
    protocol = protocol_of(status=status)
    document(protocol_of())

    problems = setup.check_documents(protocol)

    assert any("status must be 'draft' or 'frozen'" in problem for problem in problems)


def test_a_baseline_mismatch_is_reported(document):
    document(protocol_of())

    problems = setup.check_documents(protocol_of(baseline={"release": "0.9.9"}))

    assert any("does not state the baseline release 0.9.9" in problem for problem in problems)


def test_a_missing_document_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "PROTOCOL_DOCUMENT", tmp_path / "gone.md")

    problems = setup.check_documents(protocol_of())

    assert len(problems) == 1
    assert problems[0].startswith("cannot read gone.md")


# --------------------------------------------------------------------------
# the interpreter
# --------------------------------------------------------------------------


def test_the_running_interpreter_is_accepted():
    assert setup.check_python(protocol_of()) == []


def test_a_different_interpreter_is_rejected():
    protocol = protocol_of(environment={"python": "2.7"})

    problems = setup.check_python(protocol)

    assert len(problems) == 1
    assert "the protocol pins 2.7" in problems[0]


# --------------------------------------------------------------------------
# pinned packages
# --------------------------------------------------------------------------


def test_a_matching_pin_is_accepted():
    assert setup.check_packages({"pytest": PYTEST_VERSION}) == []


def test_a_missing_package_is_reported():
    problems = setup.check_packages({"not-a-real-package-9e1f": "1.0.0"})

    assert problems == ["not-a-real-package-9e1f is pinned at 1.0.0 but is not installed"]


def test_a_wrong_package_version_is_reported():
    problems = setup.check_packages({"pytest": "0.0.1"})

    assert problems == [f"pytest is pinned at 0.0.1 but {PYTEST_VERSION} is installed"]


def test_pins_are_read_and_normalised(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text(
        "# a comment\n"
        "\n"
        "NumPy==2.5.2\n"
        "python_dateutil==2.9.0.post0\n"
        "pytest==9.1.1  # trailing comment\n"
        "-e .\n"
    )

    assert setup.read_pins(path) == {
        "numpy": "2.5.2",
        "python-dateutil": "2.9.0.post0",
        "pytest": "9.1.1",
    }


def test_the_repository_pins_are_readable():
    assert setup.read_pins(setup.REQUIREMENTS), "validation/requirements.txt pins nothing"


# --------------------------------------------------------------------------
# protocol and manifest agreement
# --------------------------------------------------------------------------


@pytest.fixture
def expected_results(tmp_path, monkeypatch):
    path = tmp_path / "expected_results.json"
    path.write_text(json.dumps({"results": {"example": {"status": "pass"}}}))
    monkeypatch.setattr(setup, "EXPECTED_RESULTS", path)
    return path


def test_a_consistent_protocol_and_manifest_agree(expected_results):
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"

    assert setup.check_protocol(protocol_of(), manifest) == []


def test_a_split_naming_an_unknown_dataset_is_reported(expected_results):
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"
    protocol = protocol_of(
        splits={"development": ["example", "ghost"], "case_study": ["restricted-example"]}
    )

    problems = setup.check_protocol(protocol, manifest)

    assert problems == ["protocol split 'development' names unknown dataset 'ghost'"]


def test_a_role_that_contradicts_its_split_is_reported(expected_results):
    manifest = manifest_of(public_dataset(role="held_out"), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"

    problems = setup.check_protocol(protocol_of(), manifest)

    assert any("but datasets.json gives it role 'held_out'" in problem for problem in problems)


def test_a_dataset_in_no_split_is_reported(expected_results):
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"
    protocol = protocol_of(splits={"development": ["example"]})

    problems = setup.check_protocol(protocol, manifest)

    assert problems == ["restricted-example is in datasets.json but in no protocol split"]


def test_a_protocol_version_mismatch_is_reported(expected_results):
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "0.9.0"

    problems = setup.check_protocol(protocol_of(), manifest)

    assert any("was written for 0.9.0" in problem for problem in problems)


def test_an_expectation_for_a_non_development_panel_is_reported(tmp_path, monkeypatch):
    path = tmp_path / "expected_results.json"
    path.write_text(json.dumps({"results": {"example": {}, "restricted-example": {}}}))
    monkeypatch.setattr(setup, "EXPECTED_RESULTS", path)
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"

    problems = setup.check_protocol(protocol_of(), manifest)

    assert any("which is not a development panel" in problem for problem in problems)


def test_a_calibration_panel_needs_no_regression_expectation(tmp_path, monkeypatch):
    """Freezing a calibration verdict in a regression file would fix the very
    number the calibration is supposed to choose."""
    path = tmp_path / "expected_results.json"
    path.write_text(json.dumps({"results": {"example": {"status": "pass"}}}))
    monkeypatch.setattr(setup, "EXPECTED_RESULTS", path)
    calibration = public_dataset(id="cal", file="cal.csv", role="calibration", family_id="f_cal")
    manifest = manifest_of(public_dataset(), calibration, restricted_dataset())
    manifest["protocol_version"] = "1.1.0"
    protocol = protocol_of(
        splits={
            "development": ["example"],
            "calibration": ["cal"],
            "case_study": ["restricted-example"],
        }
    )

    assert setup.check_protocol(protocol, manifest) == []


def test_a_development_panel_with_no_expectation_is_reported(tmp_path, monkeypatch):
    path = tmp_path / "expected_results.json"
    path.write_text(json.dumps({"results": {}}))
    monkeypatch.setattr(setup, "EXPECTED_RESULTS", path)
    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"

    problems = setup.check_protocol(protocol_of(), manifest)

    assert problems == ["example is a development panel with no recorded regression expectation"]


# --------------------------------------------------------------------------
# dataset checksums
# --------------------------------------------------------------------------


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    directory = tmp_path / "tests" / "validation" / "data"
    directory.mkdir(parents=True)
    return directory


def test_a_present_and_matching_dataset_passes(data_root):
    (data_root / "example.csv").write_bytes(CONTENT)

    assert setup.check_data(manifest_of(public_dataset(), restricted_dataset())) == []


def test_a_missing_dataset_is_reported(data_root):
    problems = setup.check_data(manifest_of(public_dataset()))

    assert any("has not been fetched" in problem for problem in problems)


def test_a_dataset_with_the_wrong_checksum_is_reported(data_root):
    (data_root / "example.csv").write_bytes(b"different,bytes\n")

    problems = setup.check_data(manifest_of(public_dataset()))

    assert problems == ["example.csv does not match its recorded sha256"]


def test_restricted_datasets_are_not_checked_for_files(data_root):
    assert setup.check_data(manifest_of(restricted_dataset())) == []


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A complete, self-consistent checkout: every check should pass on it."""
    monkeypatch.setattr(setup, "ROOT", tmp_path)

    data = tmp_path / "tests" / "validation" / "data"
    data.mkdir(parents=True)
    (data / "example.csv").write_bytes(CONTENT)

    validation = tmp_path / "validation"
    validation.mkdir()

    manifest = manifest_of(public_dataset(), restricted_dataset())
    manifest["protocol_version"] = "1.1.0"
    (validation / "datasets.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(setup, "MANIFEST", validation / "datasets.json")

    (validation / "protocol.json").write_text(json.dumps(protocol_of()))
    monkeypatch.setattr(setup, "PROTOCOL", validation / "protocol.json")

    (validation / "protocol.md").write_text(document_of(protocol_of()))
    monkeypatch.setattr(setup, "PROTOCOL_DOCUMENT", validation / "protocol.md")

    (validation / "requirements.txt").write_text(f"pytest=={PYTEST_VERSION}\n")
    monkeypatch.setattr(setup, "REQUIREMENTS", validation / "requirements.txt")

    expected = tmp_path / "expected_results.json"
    expected.write_text(json.dumps({"results": {"example": {"status": "pass"}}}))
    monkeypatch.setattr(setup, "EXPECTED_RESULTS", expected)

    return tmp_path


def test_a_complete_setup_passes(sandbox, capsys):
    assert setup.main([]) == 0

    out = capsys.readouterr().out
    assert out.count("ok    ") == 5
    assert "FAIL" not in out
    assert "Ready: protocol 1.1.0 (frozen), baseline paneldx 0.4.0." in out


def test_every_failing_section_is_reported_not_just_the_first(sandbox, capsys):
    (sandbox / "validation" / "requirements.txt").write_text("pytest==0.0.1\n")
    (sandbox / "validation" / "protocol.md").write_text("# Validation protocol\n")
    (sandbox / "tests" / "validation" / "data" / "example.csv").write_bytes(b"tampered\n")

    assert setup.main([]) == 1

    out = capsys.readouterr().out
    assert "FAIL  pinned packages" in out
    assert "FAIL  protocol document and protocol.json agree" in out
    assert "FAIL  dataset checksums" in out
    assert "not reproducible as recorded" in out


def test_an_unusable_manifest_stops_the_run(sandbox, capsys):
    (sandbox / "validation" / "datasets.json").write_text(
        json.dumps(manifest_of(public_dataset(sha256="not-a-digest")))
    )

    assert setup.main([]) == 1

    out = capsys.readouterr().out
    assert out.startswith("FAIL  manifest")
    assert "sha256 must be" in out


def test_the_content_digest_used_by_these_tests_matches_the_fixture():
    """Guards the fixture itself: if CONTENT and its digest drift apart, the
    checksum tests above would pass for the wrong reason."""
    assert hashlib.sha256(CONTENT).hexdigest() == public_dataset()["sha256"]
