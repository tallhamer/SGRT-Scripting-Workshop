"""Build every workshop's notebooks from its content modules in ``scripts/<Product>/notebook_content``.

**The ``.ipynb`` files are generated.** Edit the content modules and rebuild; a change made in
Jupyter and not mirrored there will be overwritten the next time anyone runs this.

Why generate them at all, when the notebook is the thing students open:

* **No committed outputs.** A notebook with outputs is a binary-ish blob whose diffs are
  unreadable and whose size grows with every rendered plot. These commit clean.
* **Prose is editable.** Fixing a sentence in eight notebooks is eight edits in readable Python,
  not eight hunts through JSON.
* **Drift is detectable.** ``--check`` rebuilds in memory and compares, so CI fails if the
  committed notebooks no longer match their source.

    uv run python scripts/common/build_notebooks.py           # write notebooks/<Product>/
    uv run python scripts/common/build_notebooks.py --check   # verify they are up to date

Every product in :data:`sgrt_workshop.products.PRODUCTS` is built, so a product whose content
package is missing fails here rather than in front of a room.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from sgrt_workshop.products import PRODUCTS

ROOT = Path(__file__).resolve().parents[2]


def load_content(product):
    """``scripts/<Product>/notebook_content`` → its ``NOTEBOOKS`` list.

    Every product's content package is called ``notebook_content``, so they cannot all be imported
    by that name. Each is loaded under a name of its own instead; inside, the modules import each
    other relatively, which is why they work under any name.
    """
    package_dir = ROOT / "scripts" / product.folder / "notebook_content"
    if not (package_dir / "__init__.py").is_file():
        raise SystemExit(f"{product.name} is registered in sgrt_workshop.products but has no "
                         f"{package_dir.relative_to(ROOT)}/ — every workshop needs its notebooks.")
    spec = importlib.util.spec_from_file_location(
        f"{product.folder.lower()}_notebook_content", package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # before exec_module, or relative imports cannot resolve
    spec.loader.exec_module(module)
    return module.NOTEBOOKS


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

    stale, total = [], 0
    for product in PRODUCTS.values():
        notebook_dir = ROOT / "notebooks" / product.folder
        notebook_dir.mkdir(parents=True, exist_ok=True)
        for name, cells in load_content(product):
            total += 1
            path = notebook_dir / name
            content = render(cells)
            if args.check:
                current = path.read_text(encoding="utf-8") if path.is_file() else ""
                if current != content:
                    stale.append(str(path.relative_to(ROOT)))
            else:
                path.write_text(content, encoding="utf-8")
                print(f"{path.relative_to(ROOT)}: {len(cells)} cells")

    if args.check:
        if stale:
            raise SystemExit(
                "These notebooks are out of date with their scripts/<Product>/notebook_content:\n  "
                + "\n  ".join(stale)
                + "\n\nRun: uv run python scripts/common/build_notebooks.py"
            )
        print(f"{total} notebooks are up to date.")


if __name__ == "__main__":
    main()
