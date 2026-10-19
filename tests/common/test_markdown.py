"""Every Markdown file in the repository: its links resolve, and it names one repository.

Every folder moved at least once while this repository was split by product, and a relative link
is the thing that silently breaks when a file moves — GitHub renders it as a 404, not an error.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _markdown_files():
    """Every Markdown file a reader might follow a link from."""
    skip = {".venv", ".pytest_cache", ".ruff_cache", "node_modules"}
    return sorted(p for p in ROOT.rglob("*.md")
                  if not skip.intersection(p.relative_to(ROOT).parts)
                  and p.name != "WORKSHOP_PLAN.md")


@pytest.mark.parametrize("doc", _markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_relative_link_resolves(doc):
    for target in re.findall(r"\]\((?!https?://|#)([^)#]+)\)", doc.read_text()):
        assert (doc.parent / target).exists(), f"{doc.relative_to(ROOT)} links to a missing {target}"


def test_every_document_names_the_same_repository():
    """One stale URL on a handout sends a room to a 404."""
    urls = set()
    for doc in _markdown_files():
        urls.update(re.findall(r"github\.com/[\w.-]+/[\w.-]+", doc.read_text()))
    assert len(urls) == 1, f"the documents disagree about the repository: {sorted(urls)}"
    assert "REPLACE-ME" not in str(urls)
