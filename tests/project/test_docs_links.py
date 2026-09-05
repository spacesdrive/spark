"""
Every documentation link in the dashboard must point at a page that exists.

The hover previews were added so the dashboard could show a number without the
paragraph explaining it. That only works if "Learn more" goes somewhere. A link
into the documentation site is easy to write and easy to leave behind when a
file is renamed, and nothing else would catch it: the dashboard builds fine
with a dead link in it.

This reads the links out of the frontend and checks each one against the pages
ops/site/build_docs.py actually generates from docs/.
"""

from __future__ import annotations

import re

import pytest

from tests.conftest import PROJECT_ROOT

ROOT = PROJECT_ROOT
DOCS_TS = ROOT / "web" / "src" / "config" / "docs.ts"
DOCS_DIR = ROOT / "docs"

#: The hostname the dashboard links to. A two level name such as
#: docs.spark.spacesdrive.cc is not covered by Cloudflare's Universal SSL and
#: fails TLS before it reaches the server, so it must never come back.
EXPECTED_HOST = "docs-spark.spacesdrive.cc"


def built_pages() -> set[str]:
    """
    The filenames ops/site/build_docs.py will produce, without building.

    Pages are grouped in folders under docs/, but the published URL comes from
    the file stem alone, which is what keeps the links stable when a page moves
    between groups.
    """
    return {
        p.name.replace(".md", "").lower() + ".html"
        for p in DOCS_DIR.glob("**/*.md")
        if p.name != "README.md"
    }


def links() -> list[str]:
    text = DOCS_TS.read_text(encoding="utf-8")
    base = re.search(r'const BASE = "([^"]+)"', text)
    assert base, "docs.ts should define BASE"
    found = re.findall(r"\$\{BASE\}(/[A-Za-z0-9_.-]+)", text)
    return [base.group(1) + path for path in found]


def test_the_dashboard_has_documentation_links():
    assert links(), "docs.ts should contain links"


def test_every_link_points_at_a_page_that_gets_built():
    pages = built_pages()
    missing = []
    for link in links():
        filename = link.rsplit("/", 1)[-1]
        if filename not in pages:
            missing.append(f"{link} (nothing under docs/ builds {filename})")
    assert not missing, "links with no page behind them: " + "; ".join(sorted(set(missing)))


def test_links_use_the_hostname_that_actually_serves_tls():
    wrong = [link for link in links() if EXPECTED_HOST not in link]
    assert not wrong, (
        f"these links do not use {EXPECTED_HOST}, so they will fail TLS: {wrong}"
    )


def test_every_definition_is_plain_enough_to_be_useful():
    """
    A hover definition exists to replace a paragraph, so it has to be short,
    and it has to say something. An empty or one word entry would leave the
    number on the dashboard unexplained.
    """
    text = DOCS_TS.read_text(encoding="utf-8")
    entries = re.findall(r"text:\s*\"([^\"]+)\"", text)
    assert len(entries) >= 8, "most headline metrics should have a definition"
    for entry in entries:
        assert len(entry) > 40, f"too short to explain anything: {entry!r}"
        assert len(entry) < 320, f"too long for a hover card: {entry[:60]!r}..."


@pytest.mark.parametrize("required", ["evaluation.html", "training.html", "model.html"])
def test_the_pages_the_dashboard_relies_on_exist(required):
    assert required in built_pages()
