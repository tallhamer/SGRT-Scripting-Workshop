"""Build the workshop notebooks from the content modules in ``scripts/notebook_content``.

**The ``.ipynb`` files are generated.** Edit the content modules and rebuild; a change made in
Jupyter and not mirrored there will be overwritten the next time anyone runs this.

Why generate them at all, when the notebook is the thing students open:

* **No committed outputs.** A notebook with outputs is a binary-ish blob whose diffs are
  unreadable and whose size grows with every rendered plot. These commit clean.
* **Prose is editable.** Fixing a sentence in eight notebooks is eight edits in readable Python,
  not eight hunts through JSON.
* **Drift is detectable.** ``--check`` rebuilds in memory and compares, so CI fails if the
  committed notebooks no longer match their source.

    uv run python scripts/build_notebooks.py           # write notebooks/
    uv run python scripts/build_notebooks.py --check   # verify they are up to date
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from notebook_content import NOTEBOOKS  # noqa: E402

NOTEBOOK_DIR = Path(__file__).resolve().parent.parent / "notebooks"


def markdown_cell(text, index):
    return {"id": _cell_id(index), "cell_type": "markdown", "metadata": {},
            "source": _lines(text)}


def code_cell(text, index):
    return {"id": _cell_id(index), "cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [], "source": _lines(text)}


def _cell_id(index):
    """A stable cell id.

    nbformat 4.5 requires one and warns that the absence will become a hard error. Sequential and
    deterministic rather than random, so rebuilding an unchanged notebook produces an identical
    file — otherwise every build would show as a diff and ``--check`` could never pass.
    """
    return f"cell-{index:03d}"


def _lines(text):
    """nbformat stores source as a list of lines, each keeping its trailing newline but the last.

    Writing it this way rather than as one blob is what makes a notebook diff readable — a
    one-line prose fix shows up as a one-line diff.
    """
    stripped = text.strip("\n")
    lines = stripped.splitlines(keepends=True)
    return [line if line.endswith("\n") else line for line in lines] or [""]


def build(cells):
    """A notebook document from ``(kind, text)`` pairs."""
    return {
        "cells": [markdown_cell(text, index) if kind == "md" else code_cell(text, index)
                  for index, (kind, text) in enumerate(cells)],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def render(cells):
    # A trailing newline so the file ends like every other text file in the repo.
    return json.dumps(build(cells), indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed notebooks differ from their source")
    args = parser.parse_args(argv)

    NOTEBOOK_DIR.mkdir(exist_ok=True)
    stale = []
    for name, cells in NOTEBOOKS:
        path = NOTEBOOK_DIR / name
        content = render(cells)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != content:
                stale.append(name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"{path.relative_to(NOTEBOOK_DIR.parent)}: {len(cells)} cells")

    if args.check:
        if stale:
            raise SystemExit(
                "These notebooks are out of date with scripts/notebook_content:\n  "
                + "\n  ".join(stale)
                + "\n\nRun: uv run python scripts/build_notebooks.py"
            )
        print(f"{len(NOTEBOOKS)} notebooks are up to date.")


if __name__ == "__main__":
    main()
