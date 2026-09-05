"""Check that every README link works once the README leaves GitHub.

    python -m scripts.check_readme_links

README.md is the PyPI long description, and PyPI renders it standalone: a
relative target resolves against https://pypi.org/project/paneldx/ and 404s.
A released description cannot be edited afterwards, so a link that is wrong at
upload time stays wrong for the life of that release.

Every documentation link must therefore be an absolute GitHub URL pinned to the
release tag, and every pinned target must exist in the working tree. The tree
check is what makes this useful in a pull request, before the tag exists.

Live badge URLs are allowed through: they are meant to track the current
project rather than the released snapshot.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import paneldx

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
REPOSITORY = "https://github.com/stemmatics/paneldx"

# Links that should follow the project rather than the release: shields.io
# badges, the CI runs page, PyPI, python.org. Everything else pointing into the
# repository must be pinned.
LIVE_PREFIXES = (
    "https://img.shields.io/",
    "https://www.python.org/",
    "https://pypi.org/",
    f"{REPOSITORY}/actions",
    "https://doi.org/",
    "https://zenodo.org/",
)

LINK = re.compile(r"(!?)\[(?P<text>[^\]]*)\]\((?P<target>[^)]*)\)")
BADGE_LINK = re.compile(r"\[!\[(?P<text>[^\]]*)\]\((?P<image>[^)]*)\)\]\((?P<target>[^)]*)\)")
BLOB = re.compile(rf"^{re.escape(REPOSITORY)}/blob/(?P<ref>[^/]+)/(?P<path>.+)$")


def expected_tag(version: str | None = None) -> str:
    return f"v{version or paneldx.__version__}"


def _check_target(target: str, text: str, tag: str) -> list[str]:
    """One link's problems, or an empty list."""
    if not target.strip():
        return [f"[{text}] has an empty target"]
    if target.startswith("#"):
        return []
    if target.startswith(LIVE_PREFIXES):
        return []

    if not target.startswith(("http://", "https://")):
        return [
            f"[{text}]({target}) is relative; PyPI resolves it against the project page. "
            f"Use {REPOSITORY}/blob/{tag}/{target}"
        ]
    if target.startswith("http://"):
        return [f"[{text}]({target}) is not https"]
    if not target.startswith(REPOSITORY):
        return []  # a link to somewhere else entirely; nothing to pin

    blob = BLOB.match(target)
    if not blob:
        return [
            f"[{text}]({target}) points into the repository but is not a "
            f"{REPOSITORY}/blob/<tag>/<path> URL"
        ]
    if blob["ref"] != tag:
        return [
            f"[{text}]({target}) is pinned to {blob['ref']!r}, but this release is {tag}. "
            "A release page must link to the files that shipped with it."
        ]
    if not (ROOT / blob["path"]).exists():
        return [f"[{text}]({target}) points at {blob['path']}, which is not in the tree"]
    return []


def _link_targets(text: str):
    """Yield normal links plus the outer destinations of linked badges."""
    for match in LINK.finditer(text):
        yield bool(match.group(1)), match["text"], match["target"]
    for match in BADGE_LINK.finditer(text):
        yield False, match["text"], match["target"]


def pinned_urls(readme: Path = README) -> list[str]:
    return [
        target
        for is_image, _, target in _link_targets(readme.read_text())
        if not is_image and BLOB.match(target)
    ]


def check_remote(readme: Path = README, timeout: int = 20) -> list[str]:
    """Confirm each pinned URL resolves. Only meaningful once the tag exists.

    Run after tagging and before uploading: until the tag is pushed every
    pinned URL is a 404, which is why the tree check above is the one that
    belongs in a pull request.
    """
    problems = []
    for url in sorted(set(pinned_urls(readme))):
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    problems.append(f"{url} returned {response.status}")
        except urllib.error.HTTPError as error:
            problems.append(f"{url} returned {error.code}")
        except (urllib.error.URLError, OSError) as error:
            problems.append(f"{url} could not be reached: {error}")
    return problems


def check(readme: Path = README, version: str | None = None) -> list[str]:
    tag = expected_tag(version)
    text = readme.read_text()
    problems = []
    for is_image, label, target in _link_targets(text):
        if is_image:
            continue
        problems.extend(_check_target(target, label, tag))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument(
        "--version",
        help="tag to require, without the leading v (default: paneldx.__version__)",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="also fetch each pinned URL; only valid once the tag has been pushed",
    )
    args = parser.parse_args(argv)

    problems = check(args.readme, args.version)
    if args.remote and not problems:
        problems = check_remote(args.readme)
    tag = expected_tag(args.version)
    if problems:
        print(f"error   {args.readme.name}: {len(problems)} link problem(s) for {tag}")
        for problem in problems:
            print(f"        {problem}")
        return 1
    print(f"ok      {args.readme.name}: every documentation link is pinned to {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
