"""The dataset manifest and the downloader that trusts it.

Nothing here reaches the network: `download` is replaced, so a failure means
the manifest or the fetch logic is wrong, never that a mirror was slow.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from scripts import fetch_validation_data as fetch
from validation import manifest as schema
from validation.manifest import ManifestError, check_manifest, load_manifest

CONTENT = b"entity,period,value\na,1,10\na,2,11\nb,1,20\nb,2,21\n"
DIGEST = hashlib.sha256(CONTENT).hexdigest()


def public_license(**overrides) -> dict:
    licence = {
        "data_license": "CC0-1.0",
        "upstream_package_license": None,
        "redistribution_allowed": True,
        "verified_on": "2026-09-04",
        "verified_from": ["https://example.test/license"],
    }
    licence.update(overrides)
    return licence


def public_dataset(**overrides) -> dict:
    dataset = {
        "id": "example",
        "role": "development",
        "access": "public",
        "family_id": "example_family",
        "file": "example.csv",
        "sha256": DIGEST,
        "bytes": len(CONTENT),
        "source_url": "https://example.test/example.csv",
        "source": "An example mirror",
        "citation": "Example, A. (2020). An example panel.",
        "license": public_license(),
        "entity_key": ["entity"],
        "time_column": "period",
        "drop_columns": [],
        "shape": {"rows": 4, "columns_after_drop": 3, "entities": 2, "periods": 2},
        "correct_key_evidence": {"basis": "documented", "detail": "documented upstream"},
    }
    dataset.update(overrides)
    return dataset


def restricted_dataset(**overrides) -> dict:
    dataset = {
        "id": "restricted-example",
        "role": "case_study",
        "access": "restricted",
        "family_id": "restricted_family",
        "source": "Held by authorised researchers only.",
        "citation": "Held by authorised researchers only.",
        "license": {
            "data_license": "NOASSERTION",
            "upstream_package_license": None,
            "redistribution_allowed": False,
            "verified_on": "2026-09-04",
            "verified_from": [],
        },
        "entity_key": ["subject"],
        "time_column": "visit",
        "correct_key_evidence": {"basis": "unknown", "detail": "candidate key only"},
    }
    dataset.update(overrides)
    return dataset


def manifest_of(*datasets) -> dict:
    return {
        "manifest_version": "1.0.0",
        "download_directory": "tests/validation/data",
        "datasets": list(datasets),
    }


# --------------------------------------------------------------------------
# manifest validation
# --------------------------------------------------------------------------


def test_the_repository_manifest_is_valid():
    """The shipped manifest has to satisfy the rules the tests below enforce."""
    assert check_manifest(json.loads(schema.MANIFEST.read_text())) == []


def test_accepts_a_complete_public_dataset():
    assert check_manifest(manifest_of(public_dataset())) == []


def test_accepts_a_restricted_dataset_with_no_download_fields():
    assert check_manifest(manifest_of(restricted_dataset())) == []


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "role",
        "access",
        "family_id",
        "source",
        "citation",
        "license",
        "entity_key",
        "time_column",
    ],
)
def test_rejects_a_missing_required_field(field):
    dataset = public_dataset()
    del dataset[field]

    problems = check_manifest(manifest_of(dataset))

    assert any("missing required field" in problem and field in problem for problem in problems)


@pytest.mark.parametrize(
    "field",
    ["file", "sha256", "source_url", "bytes", "shape"],
)
def test_rejects_a_public_dataset_missing_a_download_field(field):
    problems = check_manifest(manifest_of(public_dataset(**{field: None})))

    assert any(f"a public dataset needs {field}" in problem for problem in problems)


@pytest.mark.parametrize("digest", ["not-a-digest", "A" * 64, "abc", 1234, "a" * 63])
def test_rejects_an_invalid_sha256(digest):
    problems = check_manifest(manifest_of(public_dataset(sha256=digest)))

    assert any("sha256 must be 64 lowercase hex" in problem for problem in problems)


def test_rejects_duplicate_dataset_ids():
    first = public_dataset()
    second = public_dataset(file="other.csv")

    assert "duplicate dataset id: example" in check_manifest(manifest_of(first, second))


def test_rejects_duplicate_files():
    first = public_dataset()
    second = deepcopy(first)
    second["id"] = "example-two"

    assert "duplicate file: example.csv" in check_manifest(manifest_of(first, second))


@pytest.mark.parametrize("role", ["holdout", "training", "", None, 7, "DEVELOPMENT"])
def test_rejects_an_invalid_role(role):
    problems = check_manifest(manifest_of(public_dataset(role=role)))

    assert any("role must be one of" in problem for problem in problems)


@pytest.mark.parametrize("access", ["open", "private", "", 1])
def test_rejects_an_invalid_access_level(access):
    problems = check_manifest(manifest_of(public_dataset(access=access)))

    assert any("access must be one of" in problem for problem in problems)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("file", "../../etc/passwd", "unsafe file name"),
        ("file", "sub/dir.csv", "unsafe file name"),
        ("source_url", "http://example.test/data.csv", "absolute https URL"),
        ("source_url", "file:///etc/passwd", "absolute https URL"),
        ("entity_key", [], "non-empty list"),
        ("entity_key", "entity", "non-empty list"),
        ("time_column", "", "time_column must be a column name"),
        ("drop_columns", "rownames", "drop_columns must be a list"),
        ("correct_key_evidence", {"basis": "vibes"}, "correct_key_evidence.basis must be"),
        ("source", "   ", "source must be a non-empty description"),
        ("source", 7, "source must be a non-empty description"),
        ("bytes", 0, "bytes must be a positive integer"),
        ("bytes", -1, "bytes must be a positive integer"),
        ("bytes", "5591", "bytes must be a positive integer"),
        ("bytes", True, "bytes must be a positive integer"),
    ],
)
def test_rejects_unsafe_or_invalid_fields(field, value, message):
    problems = check_manifest(manifest_of(public_dataset(**{field: value})))

    assert any(message in problem for problem in problems)


@pytest.mark.parametrize("field", ["rows", "columns_after_drop", "entities", "periods"])
def test_rejects_an_incomplete_shape(field):
    """A documented key is only checkable against a complete documented shape."""
    shape = public_dataset()["shape"]
    del shape[field]

    problems = check_manifest(manifest_of(public_dataset(shape=shape)))

    assert any(f"shape is missing {field}" in problem for problem in problems)


@pytest.mark.parametrize("field", ["rows", "columns_after_drop", "entities", "periods"])
@pytest.mark.parametrize("value", [0, -3, 1.5, "4", None, True])
def test_rejects_a_non_positive_shape_count(field, value):
    shape = dict(public_dataset()["shape"], **{field: value})

    problems = check_manifest(manifest_of(public_dataset(shape=shape)))

    assert any(f"shape.{field} must be a positive integer" in problem for problem in problems)


def test_rejects_a_shape_that_is_not_an_object():
    problems = check_manifest(manifest_of(public_dataset(shape=[200, 5])))

    assert any("shape must be an object" in problem for problem in problems)


@pytest.mark.parametrize("detail", ["", "   ", None, 7])
def test_rejects_evidence_with_no_detail(detail):
    evidence = {"basis": "documented", "detail": detail}

    problems = check_manifest(manifest_of(public_dataset(correct_key_evidence=evidence)))

    assert any("correct_key_evidence.detail must say how" in problem for problem in problems)


def test_rejects_evidence_with_a_missing_detail_key():
    problems = check_manifest(
        manifest_of(public_dataset(correct_key_evidence={"basis": "documented"}))
    )

    assert any("correct_key_evidence.detail must say how" in problem for problem in problems)


@pytest.mark.parametrize("role", sorted(schema.EVALUATED_ROLES))
def test_an_evaluated_dataset_may_not_rest_on_an_unknown_key(role):
    """A key that is only a candidate cannot be used to score the tool that
    proposed it."""
    evidence = {"basis": "unknown", "detail": "best-supported candidate"}

    problems = check_manifest(manifest_of(public_dataset(role=role, correct_key_evidence=evidence)))

    assert any("enters evaluation" in problem for problem in problems)


@pytest.mark.parametrize("basis", ["documented", "constructed"])
def test_an_evaluated_dataset_accepts_documented_or_constructed_evidence(basis):
    evidence = {"basis": basis, "detail": "established independently of paneldx"}

    assert check_manifest(manifest_of(public_dataset(correct_key_evidence=evidence))) == []


def test_a_case_study_may_rest_on_an_unknown_key():
    assert check_manifest(manifest_of(restricted_dataset())) == []


@pytest.mark.parametrize("value", [None, "", "   ", 7])
def test_rejects_a_missing_data_license(value):
    problems = check_manifest(
        manifest_of(public_dataset(license=public_license(data_license=value)))
    )

    assert any("license.data_license must name" in problem for problem in problems)


def test_rejects_a_license_with_no_data_license_key():
    licence = public_license()
    del licence["data_license"]

    problems = check_manifest(manifest_of(public_dataset(license=licence)))

    assert any("license.data_license must name" in problem for problem in problems)


@pytest.mark.parametrize("value", ["", "  ", 3, []])
def test_rejects_an_invalid_upstream_package_license(value):
    problems = check_manifest(
        manifest_of(public_dataset(license=public_license(upstream_package_license=value)))
    )

    assert any("upstream_package_license must be" in problem for problem in problems)


@pytest.mark.parametrize("value", [None, "2026", "04-09-2026", "2026-9-4", 20260904])
def test_rejects_an_invalid_verified_on_date(value):
    problems = check_manifest(
        manifest_of(public_dataset(license=public_license(verified_on=value)))
    )

    assert any("license.verified_on must be an ISO date" in problem for problem in problems)


@pytest.mark.parametrize(
    "value",
    ["https://example.test/license", ["http://example.test/license"], [7], None],
)
def test_rejects_an_invalid_verified_from(value):
    problems = check_manifest(
        manifest_of(public_dataset(license=public_license(verified_from=value)))
    )

    assert any(
        "license.verified_from must be a list of https URLs" in problem for problem in problems
    )


def test_a_public_dataset_must_say_where_its_licensing_was_read():
    problems = check_manifest(manifest_of(public_dataset(license=public_license(verified_from=[]))))

    assert any("must name where the licensing information" in problem for problem in problems)


def test_a_restricted_dataset_may_not_be_marked_redistributable():
    licence = restricted_dataset()["license"]
    licence["redistribution_allowed"] = True

    problems = check_manifest(manifest_of(restricted_dataset(license=licence)))

    assert any("cannot be marked redistributable" in problem for problem in problems)


@pytest.mark.parametrize("value", [None, "yes", 1, "true"])
def test_rejects_a_non_boolean_redistribution_flag(value):
    problems = check_manifest(
        manifest_of(public_dataset(license=public_license(redistribution_allowed=value)))
    )

    assert any("redistribution_allowed must be true or false" in problem for problem in problems)


def test_rejects_a_license_that_is_not_an_object():
    problems = check_manifest(manifest_of(public_dataset(license="CC0-1.0")))

    assert any("license must be an object" in problem for problem in problems)


@pytest.mark.parametrize("family", ["", "  ", "a family", 7, None, "../escape"])
def test_rejects_an_invalid_family_id(family):
    problems = check_manifest(manifest_of(public_dataset(family_id=family)))

    assert any("family_id must be a plain identifier" in problem for problem in problems)


def test_rejects_a_family_that_spans_two_splits():
    """Two panels from one survey in different splits is how calibration leaks
    into a held-out result."""
    calibration = public_dataset(id="one", file="one.csv", role="calibration", family_id="psid")
    held_out = public_dataset(id="two", file="two.csv", role="held_out", family_id="psid")

    problems = check_manifest(manifest_of(calibration, held_out))

    assert any("family 'psid' spans more than one split" in problem for problem in problems)
    assert any("calibration: one" in problem and "held_out: two" in problem for problem in problems)


def test_accepts_a_family_shared_within_one_split():
    first = public_dataset(id="one", file="one.csv", role="calibration", family_id="psid")
    second = public_dataset(id="two", file="two.csv", role="calibration", family_id="psid")

    assert check_manifest(manifest_of(first, second)) == []


def test_the_repository_manifest_keeps_every_family_in_one_split():
    manifest = json.loads(schema.MANIFEST.read_text())
    families: dict = {}
    for dataset in manifest["datasets"]:
        families.setdefault(dataset["family_id"], set()).add(dataset["role"])

    assert all(len(roles) == 1 for roles in families.values())


# --------------------------------------------------------------------------
# split selection and the held-out gate
# --------------------------------------------------------------------------


def datasets_by_role() -> list[dict]:
    return [
        public_dataset(id="dev", file="dev.csv", role="development", family_id="f_dev"),
        public_dataset(id="cal", file="cal.csv", role="calibration", family_id="f_cal"),
        public_dataset(id="hold", file="hold.csv", role="held_out", family_id="f_hold"),
        restricted_dataset(),
    ]


def test_the_default_selection_is_development_and_calibration():
    chosen = schema.select(datasets_by_role(), None, None, include_held_out=False)

    assert [d["id"] for d in chosen] == ["dev", "cal"]


def test_a_role_can_be_selected():
    chosen = schema.select(datasets_by_role(), None, ["case_study"], include_held_out=False)

    assert [d["id"] for d in chosen] == ["restricted-example"]


def test_roles_can_be_combined():
    chosen = schema.select(datasets_by_role(), None, ["development", "case_study"], False)

    assert [d["id"] for d in chosen] == ["dev", "restricted-example"]


def test_selecting_the_held_out_role_is_refused_without_the_flag():
    with pytest.raises(ManifestError, match="refusing to touch held-out data"):
        schema.select(datasets_by_role(), None, ["held_out"], include_held_out=False)


def test_naming_a_held_out_dataset_is_refused_without_the_flag():
    """The gate is on selection, not on downloading: naming one by id is not an
    exemption."""
    with pytest.raises(ManifestError, match="hold"):
        schema.select(datasets_by_role(), ["hold"], None, include_held_out=False)


def test_the_default_selection_never_includes_held_out_data():
    chosen = schema.select(datasets_by_role(), None, None, include_held_out=True)

    assert "hold" not in [d["id"] for d in chosen]


def test_held_out_data_can_be_selected_with_the_flag():
    chosen = schema.select(datasets_by_role(), None, ["held_out"], include_held_out=True)

    assert [d["id"] for d in chosen] == ["hold"]


def test_check_is_refused_on_held_out_data_too(sandbox, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, []))
    held = public_dataset(id="hold", file="hold.csv", role="held_out", family_id="f_hold")
    args = write_manifest(sandbox, public_dataset(), held)

    assert fetch.main([*args, "--dataset", "hold", "--check"]) == 1
    assert "refusing to touch held-out data" in capsys.readouterr().out


def test_restricted_datasets_may_not_carry_a_source_url():
    """The schema itself has to forbid it; a runtime guard alone is one edit
    away from being removed."""
    dataset = restricted_dataset(source_url="https://example.test/private.xlsx")

    problems = check_manifest(manifest_of(dataset))

    assert any("must not carry source_url" in problem for problem in problems)


@pytest.mark.parametrize("directory", ["/etc", "../outside", "tests/../../elsewhere", "", 3])
def test_rejects_a_download_directory_outside_the_repository(directory):
    manifest = manifest_of(public_dataset())
    manifest["download_directory"] = directory

    problems = check_manifest(manifest)

    assert any("download_directory" in problem for problem in problems)


def test_rejects_a_manifest_that_is_not_an_object():
    assert check_manifest([public_dataset()]) == ["manifest must be an object, got list"]


def test_rejects_an_empty_dataset_list():
    assert "datasets must be a non-empty list" in check_manifest(manifest_of())


def test_load_manifest_raises_on_invalid_json(tmp_path):
    path = tmp_path / "datasets.json"
    path.write_text("{not json")

    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(path)


def test_load_manifest_raises_on_an_invalid_manifest(tmp_path):
    path = tmp_path / "datasets.json"
    path.write_text(json.dumps(manifest_of(public_dataset(sha256="nope"))))

    with pytest.raises(ManifestError, match="failed validation"):
        load_manifest(path)


# --------------------------------------------------------------------------
# the downloader
# --------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A throwaway repository root, so no test can touch the real data dir."""
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    (tmp_path / "validation").mkdir()
    (tmp_path / "tests" / "validation" / "data").mkdir(parents=True)
    return tmp_path


def write_manifest(sandbox, *datasets) -> list[str]:
    path = sandbox / "validation" / "datasets.json"
    path.write_text(json.dumps(manifest_of(*datasets)))
    return ["--manifest", str(path)]


def fake_download(payload: bytes, calls: list):
    def download(url, destination):
        calls.append(url)
        destination.write_bytes(payload)

    return download


def test_a_valid_download_is_kept(sandbox, monkeypatch, capsys):
    calls: list[str] = []
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, calls))
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main(args) == 0

    target = sandbox / "tests" / "validation" / "data" / "example.csv"
    assert target.read_bytes() == CONTENT
    assert calls == ["https://example.test/example.csv"]
    assert "downloaded and verified" in capsys.readouterr().out


def test_a_corrupted_download_is_refused_and_left_unnamed(sandbox, monkeypatch, capsys):
    """The file the test suite reads must never exist with the wrong bytes."""
    calls: list[str] = []
    monkeypatch.setattr(fetch, "download", fake_download(b"tampered,payload\n", calls))
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main(args) == 1

    data = sandbox / "tests" / "validation" / "data"
    assert not (data / "example.csv").exists()
    assert list(data.iterdir()) == []  # no half-written temporary left behind
    assert "sha256 mismatch" in capsys.readouterr().out


def test_a_failed_download_reports_the_url_and_the_error(sandbox, monkeypatch, capsys):
    def explode(url, destination):
        raise OSError("connection reset")

    monkeypatch.setattr(fetch, "download", explode)
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main(args) == 1

    out = capsys.readouterr().out
    assert "download failed" in out
    assert "https://example.test/example.csv" in out
    assert "connection reset" in out
    assert list((sandbox / "tests" / "validation" / "data").iterdir()) == []


def test_an_existing_file_is_verified_not_trusted(sandbox, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, []))
    (sandbox / "tests" / "validation" / "data" / "example.csv").write_bytes(b"stale,bytes\n")
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main(args) == 1
    assert "file already on disk" in capsys.readouterr().out


def test_an_existing_valid_file_is_not_re_downloaded(sandbox, monkeypatch, capsys):
    calls: list[str] = []
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, calls))
    (sandbox / "tests" / "validation" / "data" / "example.csv").write_bytes(CONTENT)
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main(args) == 0
    assert calls == []
    assert "verified on disk" in capsys.readouterr().out


def test_check_never_downloads_and_fails_on_a_missing_file(sandbox, monkeypatch, capsys):
    calls: list[str] = []
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, calls))
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main([*args, "--check"]) == 1
    assert calls == []
    assert "missing" in capsys.readouterr().out


def test_restricted_data_are_never_fetched(sandbox, monkeypatch, capsys):
    def explode(url, destination):  # pragma: no cover - must not run
        raise AssertionError("restricted data must never be downloaded")

    monkeypatch.setattr(fetch, "download", explode)
    args = write_manifest(sandbox, restricted_dataset())

    assert fetch.main([*args, "--role", "case_study"]) == 0
    assert "restricted data are never downloaded" in capsys.readouterr().out


def test_dataset_selects_a_single_dataset(sandbox, monkeypatch, capsys):
    calls: list[str] = []
    monkeypatch.setattr(fetch, "download", fake_download(CONTENT, calls))
    other = public_dataset(
        id="other", file="other.csv", source_url="https://example.test/other.csv"
    )
    args = write_manifest(sandbox, public_dataset(), other)

    assert fetch.main([*args, "--dataset", "other"]) == 0
    assert calls == ["https://example.test/other.csv"]
    assert not (sandbox / "tests" / "validation" / "data" / "example.csv").exists()


def test_an_unknown_dataset_id_is_an_error(sandbox, capsys):
    args = write_manifest(sandbox, public_dataset())

    assert fetch.main([*args, "--dataset", "nope"]) == 1
    assert "unknown dataset id(s): nope" in capsys.readouterr().out


def test_an_invalid_manifest_stops_before_any_download(sandbox, monkeypatch, capsys):
    def explode(url, destination):  # pragma: no cover - must not run
        raise AssertionError("a malformed manifest is not a download to attempt")

    monkeypatch.setattr(fetch, "download", explode)
    args = write_manifest(sandbox, public_dataset(sha256="not-a-digest"))

    assert fetch.main(args) == 1
    assert "failed validation" in capsys.readouterr().out


def test_download_refuses_a_non_https_url(tmp_path):
    with pytest.raises(ValueError, match="non-https"):
        fetch.download("http://example.test/data.csv", tmp_path / "out.csv")
