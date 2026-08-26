"""Audit the dependencies paneldx actually ships.

Pointed at a development environment, pip-audit reports vulnerabilities in
pytest, pip and setuptools. None of those reach a user, and a gate that fails
for reasons unrelated to the code being pushed is a gate people learn to skip
with `--no-verify`.

This narrows the audit to the closure of paneldx's runtime dependencies plus
its declared extras, pinned to whatever is installed right now, so a finding
here is a finding about something a user installs.
"""

import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

DIST = "paneldx"

# Extras a user never installs to run paneldx. Auditing these is what makes
# pip-audit report pytest and pip, which is noise rather than signal.
DEV_ONLY_EXTRAS = frozenset({"dev", "test", "tests", "docs", "lint", "typing"})

try:
    from packaging.requirements import Requirement
except ModuleNotFoundError:  # pragma: no cover - environment problem, not logic
    print('error   packaging is not installed; run: pip install -e ".[dev]"')
    sys.exit(1)


def canonical(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def applies(req: Requirement, extras: set[str]) -> bool:
    """Whether a requirement is active for this platform and set of extras."""
    if req.marker is None:
        return True
    if req.marker.evaluate({"extra": ""}):
        return True
    return any(req.marker.evaluate({"extra": extra}) for extra in extras)


def shipped_closure(root: str) -> dict[str, str]:
    """Pinned {name: version} for root's runtime dependencies and extras."""
    root_dist = metadata.distribution(root)
    declared = {e.lower() for e in (root_dist.metadata.get_all("Provides-Extra") or [])}
    shipped_extras = declared - DEV_ONLY_EXTRAS

    pinned: dict[str, str] = {}
    seen: set[str] = set()
    queue: list[tuple[str, set[str]]] = [(root, shipped_extras)]

    while queue:
        name, extras = queue.pop()
        key = canonical(name)
        if key in seen:
            continue
        seen.add(key)

        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # A declared extra that is simply not installed here.
            print(f"skip    {name} is declared but not installed")
            continue

        if key != canonical(root):
            pinned[dist.metadata["Name"]] = dist.version

        for raw in dist.requires or []:
            req = Requirement(raw)
            if applies(req, extras):
                # Transitive dependencies do not inherit the extras.
                queue.append((req.name, set()))

    return pinned


def main() -> int:
    try:
        pinned = shipped_closure(DIST)
    except metadata.PackageNotFoundError:
        print(f'error   {DIST} is not installed; run: pip install -e ".[dev,excel,parquet]"')
        return 1

    if not pinned:
        print(f"error   resolved no dependencies for {DIST}; refusing to report a clean audit")
        return 1

    lines = [f"{name}=={version}" for name, version in sorted(pinned.items())]
    print("audit   " + ", ".join(lines), flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shipped-requirements.txt"
        path.write_text("\n".join(lines) + "\n")
        completed = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--disable-pip", "--no-deps", "-r", str(path)],
            check=False,
        )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
