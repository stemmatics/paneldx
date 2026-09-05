"""README links have to survive leaving GitHub.

The README is the PyPI long description, PyPI renders it standalone, and a
released description cannot be edited. A link that is wrong at upload time is
wrong for the life of that release, so it is checked here rather than noticed
afterwards.
"""

from __future__ import annotations

import pytest

from scripts import check_readme_links as links
from scripts import check_release_metadata as metadata


def readme(tmp_path, body: str):
    path = tmp_path / "README.md"
    path.write_text(body)
    return path


# --------------------------------------------------------------------------
# the shipped README
# --------------------------------------------------------------------------


def test_the_repository_readme_passes():
    assert links.check() == []


def test_the_repository_metadata_agrees():
    assert metadata.check() == []


def test_the_repository_metadata_matches_its_own_tag():
    import paneldx

    assert metadata.check(f"v{paneldx.__version__}") == []


def test_a_different_tag_is_reported():
    problems = metadata.check("v9.9.9")

    assert any("the tag is v9.9.9" in problem for problem in problems)


# --------------------------------------------------------------------------
# what the link check rejects
# --------------------------------------------------------------------------


def test_a_relative_link_is_rejected(tmp_path):
    problems = links.check(readme(tmp_path, "[Limitations](docs/limitations.md)\n"), "0.5.1")

    assert len(problems) == 1
    assert "is relative" in problems[0]
    assert "blob/v0.5.1/docs/limitations.md" in problems[0]


def test_a_link_pinned_to_the_wrong_tag_is_rejected(tmp_path):
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/v0.4.0/docs/limitations.md)\n"

    problems = links.check(readme(tmp_path, body), "0.5.1")

    assert len(problems) == 1
    assert "pinned to 'v0.4.0'" in problems[0]


def test_a_link_to_a_branch_is_rejected(tmp_path):
    """`main` drifts, so an old release page would link to newer docs."""
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/main/docs/limitations.md)\n"

    problems = links.check(readme(tmp_path, body), "0.5.1")

    assert any("pinned to 'main'" in problem for problem in problems)


def test_a_pinned_link_to_a_missing_file_is_rejected(tmp_path):
    body = "[Ghost](https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/ghost.md)\n"

    problems = links.check(readme(tmp_path, body), "0.5.1")

    assert len(problems) == 1
    assert "not in the tree" in problems[0]


def test_a_repository_url_that_is_not_a_blob_link_is_rejected(tmp_path):
    body = "[Tree](https://github.com/stemmatics/paneldx/tree/v0.5.1/docs)\n"

    problems = links.check(readme(tmp_path, body), "0.5.1")

    assert any("is not a" in problem for problem in problems)


@pytest.mark.parametrize("target", ["", "   "])
def test_an_empty_target_is_rejected(tmp_path, target):
    problems = links.check(readme(tmp_path, f"[Nothing]({target})\n"), "0.5.1")

    assert any("empty target" in problem for problem in problems)


def test_a_plain_http_link_is_rejected(tmp_path):
    problems = links.check(readme(tmp_path, "[Insecure](http://example.test/x)\n"), "0.5.1")

    assert any("not https" in problem for problem in problems)


def test_a_relative_badge_destination_is_rejected(tmp_path):
    body = "[![License](https://img.shields.io/badge/license-green)](LICENSE)\n"

    problems = links.check(readme(tmp_path, body), "0.5.1")

    assert len(problems) == 1
    assert "is relative" in problems[0]


# --------------------------------------------------------------------------
# what it deliberately allows
# --------------------------------------------------------------------------


def test_a_correctly_pinned_link_passes(tmp_path):
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/limitations.md)\n"

    assert links.check(readme(tmp_path, body), "0.5.1") == []


@pytest.mark.parametrize(
    "target",
    [
        "https://img.shields.io/pypi/v/paneldx",
        "https://pypi.org/project/paneldx/",
        "https://www.python.org/downloads/",
        "https://github.com/stemmatics/paneldx/actions/workflows/ci.yml",
        "https://doi.org/10.5281/zenodo.1234567",
        "https://zenodo.org/badge/latestdoi/1234",
    ],
)
def test_live_badges_and_services_are_allowed(tmp_path, target):
    """These track the current project on purpose, not the released snapshot."""
    assert links.check(readme(tmp_path, f"[Badge]({target})\n"), "0.5.1") == []


def test_images_are_not_checked_as_links(tmp_path):
    body = "![CI](https://img.shields.io/badge/x-y-blue)\n"

    assert links.check(readme(tmp_path, body), "0.5.1") == []


def test_anchors_are_allowed(tmp_path):
    assert links.check(readme(tmp_path, "[Section](#declaring-what-you-know)\n"), "0.5.1") == []


def test_an_external_link_is_left_alone(tmp_path):
    body = "[Kapoor and Narayanan](https://doi.org/10.1016/j.patter.2023.100804)\n"

    assert links.check(readme(tmp_path, body), "0.5.1") == []


# --------------------------------------------------------------------------
# the remote check, which only makes sense after the tag is pushed
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_remote_check_accepts_urls_that_resolve(tmp_path, monkeypatch):
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/limitations.md)\n"
    monkeypatch.setattr(links.urllib.request, "urlopen", lambda *a, **k: FakeResponse(200))

    assert links.check_remote(readme(tmp_path, body)) == []


def test_the_remote_check_reports_a_missing_tag(tmp_path, monkeypatch):
    """Before the tag is pushed every pinned URL is a 404, which is why the
    tree check is the one that runs in a pull request."""
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/limitations.md)\n"

    def not_found(*args, **kwargs):
        raise links.urllib.error.HTTPError(args[0].full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(links.urllib.request, "urlopen", not_found)

    problems = links.check_remote(readme(tmp_path, body))

    assert len(problems) == 1
    assert "returned 404" in problems[0]


def test_the_remote_check_reports_an_unreachable_host(tmp_path, monkeypatch):
    body = "[Limitations](https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/limitations.md)\n"

    def offline(*args, **kwargs):
        raise links.urllib.error.URLError("no route to host")

    monkeypatch.setattr(links.urllib.request, "urlopen", offline)

    assert any("could not be reached" in p for p in links.check_remote(readme(tmp_path, body)))


def test_the_remote_check_visits_each_url_once(tmp_path, monkeypatch):
    """docs/limitations.md is linked twice; fetching it twice would be waste."""
    base = "https://github.com/stemmatics/paneldx/blob/v0.5.1/docs/limitations.md"
    body = f"[One]({base})\n[Two]({base})\n"
    visited = []
    monkeypatch.setattr(
        links.urllib.request,
        "urlopen",
        lambda request, **k: visited.append(request.full_url) or FakeResponse(200),
    )

    links.check_remote(readme(tmp_path, body))

    assert visited == [base]


def test_the_shipped_readme_has_pinned_urls_to_verify():
    urls = links.pinned_urls()

    assert len(urls) == 17
    assert len(set(urls)) == 13
    assert all("/blob/v" in url for url in urls)
    assert "https://github.com/stemmatics/paneldx/blob/v0.5.1/LICENSE" in urls
