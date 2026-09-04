"""Download and verify the public validation panels.

    python -m scripts.fetch_validation_data              # development + calibration
    python -m scripts.fetch_validation_data --check      # verify only, never fetch
    python -m scripts.fetch_validation_data --dataset produc
    python -m scripts.fetch_validation_data --role held_out --include-held-out

The files are not committed; run this once before `pytest tests/validation`.

Every public panel carries a sha256, verified twice: on the bytes that arrive,
before they are given a name inside the repository, and again on any file
already on disk. Restricted datasets are never fetched, and held-out panels are
not selected without --include-held-out.

The manifest schema and its checks live in validation/manifest.py.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from validation.manifest import (
    CHUNK,
    DEFAULT_FETCH_ROLES,
    MANIFEST,
    ROOT,
    ManifestError,
    load_manifest,
    select,
    sha256_file,
)

# A validation panel is a small CSV. Anything larger is a mirror serving
# something other than the panel this manifest describes.
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def download(url: str, destination: Path) -> None:
    """Stream `url` into `destination`, refusing an implausibly large response."""
    if not url.startswith("https://"):  # already enforced by check_manifest
        raise ValueError(f"refusing a non-https URL: {url!r}")

    total = 0
    with urlopen(url) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"response exceeded {MAX_DOWNLOAD_BYTES} bytes")
            handle.write(chunk)


def _mismatch(name: str, expected: str, actual: str, source: str) -> list[str]:
    return [
        f"error   {name}: sha256 mismatch ({source})",
        f"        expected {expected}",
        f"        actual   {actual}",
        "        Delete the file to re-fetch, or update the manifest only if the",
        "        upstream change has been reviewed and the protocol amended.",
    ]


def _fetch(dataset: dict[str, Any], data_dir: Path, name: str, expected: str) -> tuple[bool, list]:
    """Download into a temporary file and name it only once it verifies."""
    lines = [f"fetch   {dataset['source_url']}"]
    data_dir.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(data_dir), prefix=f".{name}.", suffix=".part")
    os.close(handle)
    temp = Path(temp_name)
    try:
        try:
            download(dataset["source_url"], temp)
        except (URLError, OSError, ValueError) as error:
            return False, [
                *lines,
                f"error   {name}: download failed",
                f"        {dataset['source_url']}",
                f"        {type(error).__name__}: {error}",
            ]

        actual = sha256_file(temp)
        if actual != expected:
            return False, [*lines, *_mismatch(name, expected, actual, "freshly downloaded file")]

        temp.chmod(0o644)  # mkstemp creates 0600; these are public datasets
        shutil.move(str(temp), str(data_dir / name))
        return True, [*lines, f"ok      {name} (downloaded and verified)"]
    finally:
        if temp.exists():
            temp.unlink()


def process(dataset: dict[str, Any], data_dir: Path, check_only: bool) -> tuple[bool, list[str]]:
    """Verify, and if allowed fetch, one dataset. Returns (ok, lines to print)."""
    name, expected = dataset["file"], dataset["sha256"]
    target = data_dir / name

    if target.exists():
        actual = sha256_file(target)
        if actual != expected:
            return False, _mismatch(name, expected, actual, "file already on disk")
        return True, [f"ok      {name} (verified on disk)"]

    if check_only:
        return False, [
            f"error   {name}: missing",
            "        run python -m scripts.fetch_validation_data to fetch it",
        ]
    return _fetch(dataset, data_dir, name, expected)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the manifest and the files already present; never download",
    )
    parser.add_argument(
        "--dataset", action="append", metavar="ID", help="restrict to one dataset id; repeatable"
    )
    parser.add_argument(
        "--role",
        action="append",
        metavar="SPLIT",
        help=f"restrict to one split; repeatable. Default: {', '.join(DEFAULT_FETCH_ROLES)}",
    )
    parser.add_argument(
        "--include-held-out",
        action="store_true",
        help="required before anything in the held-out split may be selected",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        datasets = select(manifest["datasets"], args.dataset, args.role, args.include_held_out)
    except ManifestError as error:
        print(f"error   {error}")
        return 1

    data_dir = ROOT / manifest["download_directory"]
    failed = False
    for dataset in datasets:
        if dataset["access"] != "public":
            print(f"skip    {dataset['id']}: {dataset['access']} data are never downloaded")
            continue
        ok, lines = process(dataset, data_dir, args.check)
        for line in lines:
            print(line)
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
