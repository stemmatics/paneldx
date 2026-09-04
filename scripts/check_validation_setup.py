"""Report whether this checkout can reproduce the validation run.

    python -m scripts.check_validation_setup

Checks the interpreter version, the pinned packages, that protocol.md and
protocol.json agree, that protocol.json agrees with the dataset manifest, and
that every dataset present matches its recorded sha256. Reports every problem
rather than stopping at the first, and exits non-zero on any of them.

It creates and installs nothing: build the environment and fetch the panels
first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path

from validation.manifest import (
    GATED_ROLES,
    ROOT,
    ManifestError,
    load_manifest,
    sha256_file,
)

MANIFEST = ROOT / "validation" / "manifests" / "datasets.json"
PROTOCOL = ROOT / "validation" / "protocol" / "protocol.json"
PROTOCOL_DOCUMENT = ROOT / "validation" / "protocol" / "protocol.md"
REQUIREMENTS = ROOT / "validation" / "requirements.txt"
EXPECTED_RESULTS = ROOT / "tests" / "validation" / "expected_results.json"

PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s#]+)")


def read_pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text().splitlines():
        match = PIN_RE.match(line.strip())
        if match:
            pins[match["name"].lower().replace("_", "-")] = match["version"]
    return pins


def check_python(protocol: dict) -> list[str]:
    wanted = str(protocol["environment"]["python"])
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    if running != wanted:
        return [
            f"python {running} is running, but the protocol pins {wanted}. "
            f"Results from another interpreter are not the frozen validation run."
        ]
    return []


def check_packages(pins: dict[str, str]) -> list[str]:
    problems = []
    for name, wanted in sorted(pins.items()):
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            problems.append(f"{name} is pinned at {wanted} but is not installed")
            continue
        if installed != wanted:
            problems.append(f"{name} is pinned at {wanted} but {installed} is installed")
    return problems


def check_documents(protocol: dict) -> list[str]:
    """protocol.md is read by people and protocol.json by tools. If they
    disagree about version, status, freeze date or baseline, one is wrong."""
    try:
        document = PROTOCOL_DOCUMENT.read_text()
    except OSError as error:
        return [f"cannot read {PROTOCOL_DOCUMENT.name}: {error}"]

    problems = []
    version = protocol["protocol_version"]
    if f"Protocol version {version}" not in document:
        problems.append(f"{PROTOCOL_DOCUMENT.name} does not state protocol version {version}")

    status = protocol.get("status")
    frozen_on = protocol.get("frozen_on")
    if status == "frozen":
        if not frozen_on:
            problems.append("protocol.json is frozen but records no frozen_on date")
        elif f"frozen {frozen_on}" not in document:
            problems.append(f"{PROTOCOL_DOCUMENT.name} does not state the freeze date {frozen_on}")
        if "DRAFT" in document:
            problems.append(
                f"protocol.json is frozen but {PROTOCOL_DOCUMENT.name} still says DRAFT"
            )
    elif status == "draft":
        if frozen_on:
            problems.append(f"protocol.json is a draft but records frozen_on {frozen_on!r}")
        if "DRAFT" not in document:
            problems.append(
                f"protocol.json is a draft but {PROTOCOL_DOCUMENT.name} does not say so"
            )
    else:
        problems.append(f"protocol.json status must be 'draft' or 'frozen', got {status!r}")

    release = protocol["baseline"]["release"]
    if f"Baseline: paneldx {release}" not in document:
        problems.append(f"{PROTOCOL_DOCUMENT.name} does not state the baseline release {release}")
    return problems


def _split_membership(protocol: dict, known: dict) -> list[str]:
    """Every split names a known dataset, and every dataset sits in a split."""
    problems = []
    for split, ids in protocol["splits"].items():
        for dataset_id in ids:
            dataset = known.get(dataset_id)
            if dataset is None:
                problems.append(f"protocol split {split!r} names unknown dataset {dataset_id!r}")
            elif dataset["role"] != split:
                problems.append(
                    f"{dataset_id} is in protocol split {split!r} "
                    f"but datasets.json gives it role {dataset['role']!r}"
                )

    placed = {i for ids in protocol["splits"].values() for i in ids}
    problems.extend(
        f"{dataset_id} is in datasets.json but in no protocol split"
        for dataset_id in sorted(set(known) - placed)
    )
    return problems


def _expectations_match(manifest: dict) -> list[str]:
    """Regression expectations exist for the development split only.

    One for a calibration panel would freeze a verdict the calibration is
    meant to choose; one for a held-out panel would open a split that must
    stay shut.
    """
    expected = json.loads(EXPECTED_RESULTS.read_text())["results"]
    development = {
        d["id"]
        for d in manifest["datasets"]
        if d["access"] == "public" and d["role"] == "development"
    }
    return [
        *(
            f"expected_results.json records {i!r}, which is not a development panel"
            for i in sorted(set(expected) - development)
        ),
        *(
            f"{i} is a development panel with no recorded regression expectation"
            for i in sorted(development - set(expected))
        ),
    ]


def check_protocol(protocol: dict, manifest: dict) -> list[str]:
    known = {dataset["id"]: dataset for dataset in manifest["datasets"]}
    problems = _split_membership(protocol, known)

    if protocol["protocol_version"] != manifest.get("protocol_version"):
        problems.append(
            f"protocol.json is version {protocol['protocol_version']} but datasets.json "
            f"was written for {manifest.get('protocol_version')}"
        )

    problems.extend(_expectations_match(manifest))
    return problems


def check_data(manifest: dict) -> list[str]:
    """Every dataset that should be present must match its digest.

    Held-out panels are registered rather than fetched, so their absence is the
    expected state and not a problem. One that is present is still verified:
    the checksum is what makes the registration worth anything.
    """
    problems = []
    data = ROOT / manifest["download_directory"]
    for dataset in manifest["datasets"]:
        if dataset["access"] != "public":
            continue
        path = data / dataset["file"]
        if not path.exists():
            if dataset["role"] not in GATED_ROLES:
                problems.append(
                    f"{dataset['file']} has not been fetched (run scripts/fetch_validation_data.py)"
                )
        elif sha256_file(path) != dataset["sha256"]:
            problems.append(f"{dataset['file']} does not match its recorded sha256")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    try:
        manifest = load_manifest(MANIFEST)
    except ManifestError as error:
        print(f"FAIL  manifest\n      {error}")
        return 1

    protocol = json.loads(PROTOCOL.read_text())
    pins = read_pins(REQUIREMENTS)

    sections = [
        ("interpreter", check_python(protocol)),
        (f"pinned packages ({len(pins)})", check_packages(pins)),
        ("protocol document and protocol.json agree", check_documents(protocol)),
        ("protocol and manifest agree", check_protocol(protocol, manifest)),
        ("dataset checksums", check_data(manifest)),
    ]

    failed = False
    for name, problems in sections:
        if problems:
            failed = True
            print(f"FAIL  {name}")
            for problem in problems:
                print(f"      {problem}")
        else:
            print(f"ok    {name}")

    if failed:
        print("\nThe validation environment is not reproducible as recorded.")
    else:
        print(
            f"\nReady: protocol {protocol['protocol_version']} "
            f"({protocol.get('status', 'unknown')}), baseline "
            f"paneldx {protocol['baseline']['release']}."
        )
        registered = sorted(d["id"] for d in manifest["datasets"] if d["role"] in GATED_ROLES)
        if registered:
            print(f"Held out, registered and not evaluated: {', '.join(registered)}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
