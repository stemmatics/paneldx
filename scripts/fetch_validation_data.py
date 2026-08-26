"""Download the public panels listed in tests/validation/panels.json.

The files are not committed; run this once before `pytest tests/validation`.

Two things are enforced here, both for the same reason: a validation suite is
only evidence if the thing it validated is the thing it says it validated.

  * The manifest is checked before anything is fetched. A malformed entry is a
    bug in the manifest, not a download to attempt.
  * Every panel carries a sha256. The upstream mirror can re-encode or revise a
    dataset without notice, and a suite that silently accepts a different file
    is measuring something other than what it reports.
"""

import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1] / "tests" / "validation"

REQUIRED_FIELDS = (
    "name",
    "file",
    "source_url",
    "sha256",
    "key",
    "time",
    "expected_status",
    "expected_entities",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ALLOWED_STATUS = frozenset({"pass", "warn", "fail", "inconclusive"})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest(cases: list[dict[str, Any]]) -> list[str]:
    """Return a list of problems. An empty list means the manifest is usable."""
    problems: list[str] = []
    seen_names: dict[str, int] = {}
    seen_files: dict[str, int] = {}

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            problems.append(f"entry {index}: expected an object, got {type(case).__name__}")
            continue

        where = f"entry {index} ({case.get('name', 'unnamed')})"

        missing = [field for field in REQUIRED_FIELDS if field not in case]
        if missing:
            problems.append(f"{where}: missing required field(s): {', '.join(missing)}")

        digest = case.get("sha256")
        if digest is not None and not (isinstance(digest, str) and SHA256_RE.match(digest)):
            problems.append(f"{where}: sha256 must be 64 lowercase hex characters, got {digest!r}")

        name = case.get("file")
        if name is not None:
            # Guards against a manifest entry writing outside tests/validation/data.
            if not isinstance(name, str) or not SAFE_FILENAME_RE.match(name):
                problems.append(f"{where}: unsafe file name {name!r}")
            elif name in {".", ".."} or Path(name).name != name:
                problems.append(f"{where}: file must be a bare name, got {name!r}")
            else:
                seen_files[name] = seen_files.get(name, 0) + 1

        url = case.get("source_url")
        if url is not None:
            parsed = urllib.parse.urlparse(url) if isinstance(url, str) else None
            if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                problems.append(f"{where}: source_url must be an absolute https URL, got {url!r}")

        status = case.get("expected_status")
        if status is not None and status not in ALLOWED_STATUS:
            problems.append(
                f"{where}: expected_status must be one of "
                f"{', '.join(sorted(ALLOWED_STATUS))}, got {status!r}"
            )

        entities = case.get("expected_entities")
        if entities is not None and not (isinstance(entities, int) and entities > 0):
            problems.append(
                f"{where}: expected_entities must be a positive integer, got {entities!r}"
            )

        key = case.get("key")
        if key is not None and not (
            isinstance(key, list) and key and all(isinstance(column, str) for column in key)
        ):
            problems.append(f"{where}: key must be a non-empty list of column names, got {key!r}")

        if case.get("name") is not None:
            seen_names[case["name"]] = seen_names.get(case["name"], 0) + 1

    problems.extend(f"duplicate name: {name}" for name, n in seen_names.items() if n > 1)
    problems.extend(f"duplicate file: {name}" for name, n in seen_files.items() if n > 1)
    return problems


def main() -> int:
    cases = json.loads((ROOT / "panels.json").read_text())

    if not isinstance(cases, list) or not cases:
        print("error   panels.json must be a non-empty list of panels")
        return 1

    problems = check_manifest(cases)
    if problems:
        print(f"error   panels.json failed validation ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"        {problem}")
        return 1

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    failed = False

    for case in cases:
        target = data / case["file"]
        expected = case["sha256"]

        if target.exists():
            print(f"have    {target.name}")
        else:
            print(f"fetch   {case['source_url']}")
            urlretrieve(case["source_url"], target)

        actual = sha256(target)
        if actual != expected:
            print(f"error   {target.name}: sha256 mismatch")
            print(f"        expected {expected}")
            print(f"        actual   {actual}")
            print("        delete the file to re-fetch, or update panels.json")
            print("        if the upstream change is intended and reviewed")
            failed = True
        else:
            print(f"ok      {target.name}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
