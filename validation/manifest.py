"""The validation dataset manifest: schema, validation and selection.

Reading and checking the manifest lives here rather than in the script that
downloads from it, so the same rules apply to the fetcher, the setup check, the
benchmark and the tests.

A manifest is usable only if every dataset carries the fields the protocol
depends on, no family straddles two splits, and no restricted dataset describes
a way to download itself.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "validation" / "manifests" / "datasets.json"

# Fields every dataset must carry, whatever its access level.
REQUIRED_FIELDS = (
    "id",
    "role",
    "access",
    "family_id",
    "source",
    "citation",
    "license",
    "entity_key",
    "time_column",
    "correct_key_evidence",
)
# Fields that only a downloadable dataset can have, and must.
PUBLIC_ONLY_FIELDS = ("file", "sha256", "source_url", "bytes", "shape")

ALLOWED_ROLES = frozenset({"development", "calibration", "held_out", "external", "case_study"})
# Fetched when no role is asked for. held_out is not here, and adding it needs
# --include-held-out as well.
DEFAULT_FETCH_ROLES = ("development", "calibration")
GATED_ROLES = frozenset({"held_out"})
# Roles whose results may enter an evaluation metric. A case study may not, so
# it is the only role allowed to carry an unknown key.
EVALUATED_ROLES = ALLOWED_ROLES - {"case_study"}
ALLOWED_ACCESS = frozenset({"public", "restricted"})
ALLOWED_EVIDENCE_BASIS = frozenset({"documented", "constructed", "unknown"})
# A key whose correctness rests on paneldx's own verdict cannot test paneldx.
EVALUABLE_EVIDENCE_BASIS = frozenset({"documented", "constructed"})
# Every count the documentation quotes, and that the suite asserts against.
SHAPE_COUNTS = ("rows", "columns_after_drop", "entities", "periods")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CHUNK = 64 * 1024


class ManifestError(Exception):
    """The manifest cannot be used. Raised before anything is fetched."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identifier(value: Any, field: str, where: str) -> list[str]:
    if isinstance(value, str) and SAFE_ID_RE.match(value):
        return []
    return [f"{where}: {field} must be a plain identifier, got {value!r}"]


def _one_of(value: Any, allowed: frozenset[str], field: str, where: str) -> list[str]:
    if value in allowed:
        return []
    return [f"{where}: {field} must be one of {', '.join(sorted(allowed))}, got {value!r}"]


def _non_empty_text(value: Any, field: str, where: str, expected: str = "non-empty") -> list[str]:
    if isinstance(value, str) and value.strip():
        return []
    return [f"{where}: {field} must be {expected}, got {value!r}"]


def _digest(value: Any, where: str) -> list[str]:
    if isinstance(value, str) and SHA256_RE.match(value):
        return []
    return [f"{where}: sha256 must be 64 lowercase hex characters, got {value!r}"]


def _bare_filename(value: Any, where: str) -> list[str]:
    """Guards against a manifest entry writing outside the data directory."""
    if not isinstance(value, str) or not SAFE_FILENAME_RE.match(value):
        return [f"{where}: unsafe file name {value!r}"]
    if value in {".", ".."} or Path(value).name != value:
        return [f"{where}: file must be a bare name, got {value!r}"]
    return []


def _https_url(value: Any, field: str, where: str) -> list[str]:
    parsed = urllib.parse.urlparse(value) if isinstance(value, str) else None
    if parsed is not None and parsed.scheme == "https" and parsed.netloc:
        return []
    return [f"{where}: {field} must be an absolute https URL, got {value!r}"]


def _positive_int(value: Any, field: str, where: str) -> list[str]:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return []
    return [f"{where}: {field} must be a positive integer, got {value!r}"]


def _column_list(value: Any, field: str, where: str, *, allow_empty: bool) -> list[str]:
    named = isinstance(value, list) and all(isinstance(c, str) for c in value)
    if named and (value or allow_empty):
        return []
    article = "a list" if allow_empty else "a non-empty list"
    return [f"{where}: {field} must be {article} of column names, got {value!r}"]


def _check_identity(dataset: dict, where: str) -> list[str]:
    """id, role, access and family_id.

    Present-but-null is a manifest bug rather than an omission, so these test
    for the key rather than for a non-None value.
    """
    problems = []
    if "id" in dataset:
        problems += _identifier(dataset["id"], "id", where)
    if "family_id" in dataset:
        problems += _identifier(dataset["family_id"], "family_id", where)
    if "role" in dataset:
        problems += _one_of(dataset["role"], ALLOWED_ROLES, "role", where)
    if "access" in dataset:
        problems += _one_of(dataset["access"], ALLOWED_ACCESS, "access", where)
    return problems


def _check_restricted(dataset: dict, where: str) -> list[str]:
    """A restricted dataset must not describe a way to download itself."""
    present = [field for field in PUBLIC_ONLY_FIELDS if dataset.get(field) is not None]
    if not present:
        return []
    return [
        f"{where}: a restricted dataset must not carry {', '.join(present)}; "
        "restricted data are never downloaded"
    ]


def _check_public(dataset: dict, where: str) -> list[str]:
    """The fields a downloadable dataset needs, and the shape of each."""
    missing = [field for field in PUBLIC_ONLY_FIELDS if dataset.get(field) is None]
    problems = [f"{where}: a public dataset needs {', '.join(missing)}"] if missing else []

    checks = [
        ("sha256", lambda v: _digest(v, where)),
        ("file", lambda v: _bare_filename(v, where)),
        ("source_url", lambda v: _https_url(v, "source_url", where)),
        ("bytes", lambda v: _positive_int(v, "bytes", where)),
    ]
    for field, check in checks:
        value = dataset.get(field)
        if value is not None:
            problems += check(value)

    problems += _check_shape(dataset.get("shape"), where)
    return problems


def _check_panel(dataset: dict, where: str) -> list[str]:
    """The columns that make the panel readable, and what describes it."""
    problems = []
    if "entity_key" in dataset:
        problems += _column_list(dataset["entity_key"], "entity_key", where, allow_empty=False)
    if "time_column" in dataset:
        problems += _non_empty_text(dataset["time_column"], "time_column", where, "a column name")
    problems += _column_list(
        dataset.get("drop_columns", []), "drop_columns", where, allow_empty=True
    )
    if "source" in dataset:
        problems += _non_empty_text(dataset["source"], "source", where, "a non-empty description")
    return problems


def _check_dataset(dataset: Any, index: int) -> list[str]:
    if not isinstance(dataset, dict):
        return [f"dataset {index}: expected an object, got {type(dataset).__name__}"]

    where = f"dataset {index} ({dataset.get('id', 'unnamed')})"
    problems = []

    missing = [field for field in REQUIRED_FIELDS if field not in dataset]
    if missing:
        problems.append(f"{where}: missing required field(s): {', '.join(missing)}")

    problems.extend(_check_identity(dataset, where))

    access = dataset.get("access")
    if access == "restricted":
        problems.extend(_check_restricted(dataset, where))
    elif access == "public":
        problems.extend(_check_public(dataset, where))

    problems.extend(_check_panel(dataset, where))
    if "correct_key_evidence" in dataset:
        problems.extend(
            _check_evidence(dataset["correct_key_evidence"], dataset.get("role"), where)
        )
    if "license" in dataset:
        problems.extend(_check_license(dataset["license"], access, where))
    return problems


def _check_shape(shape: Any, where: str) -> list[str]:
    """The documented shape is what makes a documented key checkable, so it has
    to be complete rather than merely present."""
    if shape is None:
        return [f"{where}: a public dataset needs shape"]
    if not isinstance(shape, dict):
        return [f"{where}: shape must be an object, got {type(shape).__name__}"]

    problems = []
    for field in SHAPE_COUNTS:
        if field not in shape:
            problems.append(f"{where}: shape is missing {field}")
            continue
        value = shape[field]
        if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
            problems.append(f"{where}: shape.{field} must be a positive integer, got {value!r}")
    return problems


def _check_evidence(evidence: Any, role: Any, where: str) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{where}: correct_key_evidence must be an object"]

    problems = []
    basis = evidence.get("basis")
    if basis not in ALLOWED_EVIDENCE_BASIS:
        problems.append(
            f"{where}: correct_key_evidence.basis must be one of "
            f"{', '.join(sorted(ALLOWED_EVIDENCE_BASIS))}, got {basis!r}"
        )
    elif basis not in EVALUABLE_EVIDENCE_BASIS and role in EVALUATED_ROLES:
        # Otherwise a dataset whose key is only a candidate could quietly end up
        # in a numerator, and the metric would be scoring paneldx against itself.
        problems.append(
            f"{where}: role {role!r} enters evaluation, so correct_key_evidence.basis must be "
            f"one of {', '.join(sorted(EVALUABLE_EVIDENCE_BASIS))}, got {basis!r}. "
            "Move it to role 'case_study' if the key is only a candidate."
        )

    detail = evidence.get("detail")
    if not (isinstance(detail, str) and detail.strip()):
        problems.append(
            f"{where}: correct_key_evidence.detail must say how the key is known, got {detail!r}"
        )
    return problems


def _license_names(licence: dict, where: str) -> list[str]:
    problems = []
    data_license = licence.get("data_license")
    if not (isinstance(data_license, str) and data_license.strip()):
        problems.append(
            f"{where}: license.data_license must name the licence of the data itself, or "
            f"'NOASSERTION' where none is established, got {data_license!r}"
        )
    upstream = licence.get("upstream_package_license")
    if upstream is not None and not (isinstance(upstream, str) and upstream.strip()):
        problems.append(
            f"{where}: license.upstream_package_license must be a licence name or null, "
            f"got {upstream!r}"
        )
    return problems


def _license_redistribution(licence: dict, access: Any, where: str) -> list[str]:
    allowed = licence.get("redistribution_allowed")
    if not isinstance(allowed, bool):
        return [f"{where}: license.redistribution_allowed must be true or false"]
    if allowed and access == "restricted":
        return [f"{where}: a restricted dataset cannot be marked redistributable"]
    return []


def _license_provenance(licence: dict, access: Any, where: str) -> list[str]:
    """When and where the licence statements were read."""
    problems = []
    verified_on = licence.get("verified_on")
    if not (isinstance(verified_on, str) and ISO_DATE_RE.match(verified_on)):
        problems.append(
            f"{where}: license.verified_on must be an ISO date (YYYY-MM-DD), got {verified_on!r}"
        )

    sources = licence.get("verified_from")
    if not isinstance(sources, list) or not all(
        isinstance(url, str) and url.startswith("https://") for url in sources
    ):
        problems.append(
            f"{where}: license.verified_from must be a list of https URLs, got {sources!r}"
        )
    elif access == "public" and not sources:
        problems.append(
            f"{where}: license.verified_from must name where the licensing information "
            "for a public dataset was read"
        )
    return problems


def _check_license(licence: Any, access: Any, where: str) -> list[str]:
    if not isinstance(licence, dict):
        return [f"{where}: license must be an object"]
    return (
        _license_names(licence, where)
        + _license_redistribution(licence, access, where)
        + _license_provenance(licence, access, where)
    )


def _index(datasets: list) -> tuple[dict[str, int], dict[str, int], dict[str, dict[str, list]]]:
    """Count ids and files, and group dataset ids by family and role."""
    ids: dict[str, int] = {}
    files: dict[str, int] = {}
    families: dict[str, dict[str, list[str]]] = {}

    for index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            continue
        dataset_id = dataset.get("id")
        if isinstance(dataset_id, str):
            ids[dataset_id] = ids.get(dataset_id, 0) + 1
        name = dataset.get("file")
        if isinstance(name, str):
            files[name] = files.get(name, 0) + 1
        family, role = dataset.get("family_id"), dataset.get("role")
        if isinstance(family, str) and isinstance(role, str):
            label = dataset_id if isinstance(dataset_id, str) else f"entry {index}"
            families.setdefault(family, {}).setdefault(role, []).append(label)
    return ids, files, families


def _split_conflicts(families: dict[str, dict[str, list[str]]]) -> list[str]:
    """Two panels built from one survey are not independent. In different
    splits, calibration leaks into the held-out result."""
    problems = []
    for family, roles in sorted(families.items()):
        if len(roles) > 1:
            spread = "; ".join(f"{role}: {', '.join(ids)}" for role, ids in sorted(roles.items()))
            problems.append(
                f"family {family!r} spans more than one split ({spread}); "
                "related datasets must share a split"
            )
    return problems


def _check_download_directory(directory: Any) -> list[str]:
    if not isinstance(directory, str) or not directory:
        return ["download_directory must be a repository-relative path"]
    if Path(directory).is_absolute() or ".." in Path(directory).parts:
        return [f"download_directory must stay inside the repository, got {directory!r}"]
    return []


def check_manifest(manifest: Any) -> list[str]:
    """Return a list of problems. An empty list means the manifest is usable."""
    if not isinstance(manifest, dict):
        return [f"manifest must be an object, got {type(manifest).__name__}"]

    problems = _check_download_directory(manifest.get("download_directory"))

    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        return [*problems, "datasets must be a non-empty list"]

    for index, dataset in enumerate(datasets):
        problems.extend(_check_dataset(dataset, index))

    ids, files, families = _index(datasets)
    problems.extend(f"duplicate dataset id: {i}" for i, n in ids.items() if n > 1)
    problems.extend(f"duplicate file: {name}" for name, n in files.items() if n > 1)
    problems.extend(_split_conflicts(families))
    return problems


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    """Read and validate the manifest, or raise ManifestError."""
    try:
        raw = path.read_text()
    except OSError as error:
        raise ManifestError(f"cannot read {path}: {error}") from error

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path} is not valid JSON: {error}") from error

    problems = check_manifest(manifest)
    if problems:
        detail = "\n".join(f"        {problem}" for problem in problems)
        raise ManifestError(
            f"{path.name} failed validation ({len(problems)} problem(s)):\n{detail}"
        )
    checked: dict[str, Any] = manifest
    return checked


def _by_ids(datasets: list[dict[str, Any]], ids: list[str]) -> list[dict[str, Any]]:
    known = {dataset["id"] for dataset in datasets}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ManifestError(
            f"unknown dataset id(s): {', '.join(unknown)}\n"
            f"        known ids: {', '.join(sorted(known))}"
        )
    return [dataset for dataset in datasets if dataset["id"] in set(ids)]


def _check_gate(chosen: list[dict[str, Any]], include_held_out: bool) -> None:
    gated = sorted(d["id"] for d in chosen if d["role"] in GATED_ROLES)
    if gated and not include_held_out:
        raise ManifestError(
            f"refusing to touch held-out data without --include-held-out: {', '.join(gated)}\n"
            "        The held-out split is opened once, after the method is frozen.\n"
            "        See validation/protocol/protocol.md section 3."
        )


def select(
    datasets: list[dict[str, Any]],
    ids: list[str] | None,
    roles: list[str] | None,
    include_held_out: bool,
) -> list[dict[str, Any]]:
    """Pick the datasets to act on, refusing a gated split unless it was asked
    for explicitly. The gate is on selection rather than on downloading."""
    if roles:
        unknown = sorted(set(roles) - ALLOWED_ROLES)
        if unknown:
            raise ManifestError(
                f"unknown split(s): {', '.join(unknown)}\n"
                f"        known splits: {', '.join(sorted(ALLOWED_ROLES))}"
            )

    if ids:
        chosen = _by_ids(datasets, ids)
        if roles:
            chosen = [dataset for dataset in chosen if dataset["role"] in set(roles)]
    else:
        wanted = set(roles) if roles else set(DEFAULT_FETCH_ROLES)
        chosen = [dataset for dataset in datasets if dataset["role"] in wanted]

    _check_gate(chosen, include_held_out)
    return chosen
