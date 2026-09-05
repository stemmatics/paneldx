"""Check that everything naming the release version agrees.

    python -m scripts.check_release_metadata
    python -m scripts.check_release_metadata --tag v0.5.2

Five places carry the version: the package, the README's pinned links,
CITATION.cff, .zenodo.json and the changelog. A release where they disagree
publishes a citation for one version and a wheel for another, and neither PyPI
nor Zenodo will let it be corrected afterwards.

Without --tag this checks that the five agree with each other, which is what a
pull request can verify. With --tag it also checks they match the tag being
cut, which is what the release workflow verifies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import paneldx
from scripts.check_readme_links import REPOSITORY

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CITATION = ROOT / "CITATION.cff"
ZENODO = ROOT / ".zenodo.json"
CHANGELOG = ROOT / "CHANGELOG.md"
CONCEPT_DOI = "10.5281/zenodo.22339487"


def readme_tags(readme: Path = README) -> set[str]:
    pattern = rf"{re.escape(REPOSITORY)}/blob/([^/]+)/"
    return set(re.findall(pattern, readme.read_text()))


def citation_version(path: Path = CITATION) -> str | None:
    match = re.search(r"^version:\s*(\S+)", path.read_text(), re.M)
    return match.group(1) if match else None


def zenodo_version(path: Path = ZENODO) -> str | None:
    version = json.loads(path.read_text()).get("version")
    return str(version) if version is not None else None


def changelog_versions(path: Path = CHANGELOG) -> list[str]:
    return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", path.read_text(), re.M)


def concept_doi_problems(readme: Path = README, citation: Path = CITATION) -> list[str]:
    problems = []
    for name, path in (("README", readme), ("CITATION.cff", citation)):
        if CONCEPT_DOI not in path.read_text():
            problems.append(f"{name} does not contain the current concept DOI {CONCEPT_DOI}")
    return problems


def check(tag: str | None = None) -> list[str]:
    version = paneldx.__version__
    problems = []

    tags = readme_tags()
    if tags != {f"v{version}"}:
        problems.append(f"README pins {sorted(tags) or ['nothing']}, but the package is {version}")

    for name, found in (("CITATION.cff", citation_version()), (".zenodo.json", zenodo_version())):
        if found != version:
            problems.append(f"{name} says {found!r}, but the package is {version}")

    released = changelog_versions()
    if not released or released[0] != version:
        newest = released[0] if released else "nothing"
        problems.append(f"CHANGELOG's newest release is {newest}, but the package is {version}")

    problems.extend(concept_doi_problems())

    if tag is not None and tag != f"v{version}":
        problems.append(f"the tag is {tag}, but the package is {version}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="the tag being released, for example v0.5.2")
    args = parser.parse_args(argv)

    problems = check(args.tag)
    if problems:
        print(f"error   release metadata disagrees ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"        {problem}")
        return 1

    print(
        f"ok      package, README, CITATION.cff, .zenodo.json and CHANGELOG all say "
        f"{paneldx.__version__}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
