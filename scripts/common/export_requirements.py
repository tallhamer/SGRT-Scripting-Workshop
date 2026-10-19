"""Generate ``binder/requirements.txt`` from ``uv.lock``.

Binder builds with `repo2docker <https://repo2docker.readthedocs.io/>`_, which knows about
``requirements.txt`` and nothing about uv. Rather than maintaining a second dependency list that
will drift, this exports the **same locked versions** `uv sync` installs, so a Binder session and
a local clone run identical code.

    uv run python scripts/common/export_requirements.py
    uv run python scripts/common/export_requirements.py --check    # fail if it is out of date

What is exported: the project's runtime dependencies plus the ``notebooks`` extra, with the dev
group dropped (Binder does not run the test suite) and the project itself left out — ``postBuild``
installs that from the checkout.

Environment markers survive the export, so a wheel pinned for macOS carries
``; sys_platform == 'darwin'`` and is simply skipped on Binder's Linux.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "binder" / "requirements.txt"

UV_EXPORT = [
    "uv", "export",
    "--format", "requirements-txt",
    "--no-hashes",          # hashes would need --require-hashes and complicate the Binder build
    "--no-emit-project",    # postBuild installs the project itself from the checkout
    "--no-default-groups",  # drop `dev` (tests) and `workshop` (it just re-exports the extra)
    "--extra", "notebooks",
]

#: Needed on Binder and nowhere else, so they are not in pyproject.toml. jupyter-server-proxy is
#: what lets a student open the emulator's /docs page through the Binder URL — without it the
#: emulator is reachable from a notebook cell but not from a browser tab.
BINDER_ONLY = [
    ("jupyter-server-proxy>=4.1", "serves the emulator's /docs through the Binder URL"),
]

HEADER = """\
# ---------------------------------------------------------------------------------------------
# GENERATED — do not edit. Run: uv run python scripts/common/export_requirements.py
#
# Exported from uv.lock so a Binder session installs exactly what `uv sync` installs locally.
# Binder builds with repo2docker, which understands requirements.txt and not uv.
#
# The project itself is not listed here; binder/postBuild installs it from the checkout.
# ---------------------------------------------------------------------------------------------
"""


def export():
    """The requirements file contents, as text."""
    result = subprocess.run(UV_EXPORT, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"export_requirements: `uv export` failed\n{result.stderr}")

    # uv writes its own provenance header naming the exact command; keep it, it is useful, but put
    # ours first so the "do not edit" is the first thing anyone reads.
    body = result.stdout

    extra = "\n".join(
        f"{requirement}    # Binder only: {why}" for requirement, why in BINDER_ONLY)
    return (f"{HEADER}\n{body}\n"
            f"# -- Binder-only additions, not in pyproject.toml ------------------------------\n"
            f"{extra}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed file is out of date with uv.lock")
    args = parser.parse_args(argv)

    content = export()

    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != content:
            raise SystemExit(
                f"{TARGET.relative_to(ROOT)} is out of date with uv.lock.\n"
                f"Run: uv run python scripts/common/export_requirements.py"
            )
        print(f"{TARGET.relative_to(ROOT)} is up to date.")
        return

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    pinned = sum(1 for line in content.splitlines() if "==" in line and not line.startswith("#"))
    print(f"{TARGET.relative_to(ROOT)}: {pinned} pinned packages"
          f" + {len(BINDER_ONLY)} Binder-only")


if __name__ == "__main__":
    sys.exit(main())
