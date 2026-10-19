"""The Colab bootstrap cell carried by every notebook.

Colab cannot be driven from here, so this pins the things that were actually wrong when the cell
was first written and never run — each of which would have failed every session:

1. The emulator was started **without** ``--token`` while the environment advertised
   ``workshop-colab-token``, so it minted a random one and every call returned
   ``InvalidClientToken``.
2. A fixed ``time.sleep(4)`` instead of waiting for the server: too short on a slow runtime, and
   the failure looks like nothing in particular.
3. No ``chdir`` into the checkout, so the capstone's ``../data/MapRT/plans/...`` resolved to ``/data``
   and raised ``FileNotFoundError``.
4. The index notebook had no bootstrap cell at all — and it is the entry point.

Verified by hand in a simulated Colab runtime (a clean venv, ``COLAB_RELEASE_TAG`` set, a
``/content``-shaped directory, installing from the real GitHub repository): **all nine notebooks
execute top to bottom**, the capstone included, in 3–23 seconds each.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = ROOT / "notebooks"

nbformat = pytest.importorskip("nbformat")

NOTEBOOKS = sorted(NOTEBOOK_DIR.glob("*.ipynb"))


def bootstrap_of(path):
    notebook = nbformat.read(path, as_version=4)
    cells = [c.source for c in notebook.cells
             if c.cell_type == "code" and "COLAB_RELEASE_TAG" in c.source]
    return cells[0] if cells else None


class TestEveryNotebookCanStandAlone:
    @pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
    def test_it_carries_the_bootstrap(self, path):
        """Including the index.

        Colab opens one notebook at a time on its own machine, with no shared state — so a
        notebook without the bootstrap simply does not work there. The index was missing it,
        which is the worst one to miss: it is where people start.
        """
        assert bootstrap_of(path) is not None, f"{path.name} has no Colab bootstrap cell"

    @pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
    def test_the_bootstrap_is_the_first_code_cell(self, path):
        notebook = nbformat.read(path, as_version=4)
        first_code = next(c for c in notebook.cells if c.cell_type == "code")
        assert "COLAB_RELEASE_TAG" in first_code.source, (
            f"{path.name} runs code before installing anything")

    @pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
    def test_every_copy_is_identical(self, path):
        # They are generated from one constant; a hand-edit to one would diverge silently.
        assert bootstrap_of(path) == bootstrap_of(NOTEBOOKS[0])


class TestTheBootstrapIsCorrect:
    @pytest.fixture(scope="class")
    @staticmethod
    def source():
        return bootstrap_of(NOTEBOOKS[0])

    def test_it_only_fires_on_colab(self, source):
        # Locally the emulator is already running in the other terminal; on Binder, start did it.
        assert 'if "COLAB_RELEASE_TAG" in os.environ:' in source

    def test_it_gives_the_emulator_the_token_it_advertises(self, source):
        """**The bug that would have broken every session.**

        Setting MAPRT_EMULATOR_TOKEN tells the notebook what secret to send. Without passing the same
        value to the emulator, it mints a random one and rejects every call with
        InvalidClientToken — which reads as a configuration problem and is not.
        """
        assert '"--token", os.environ["MAPRT_EMULATOR_TOKEN"]' in source

    def test_it_sets_both_variables_connect_reads(self, source):
        assert 'os.environ["MAPRT_EMULATOR_TOKEN"]' in source
        assert 'os.environ["MAPRT_EMULATOR_URL"]' in source

    def test_the_url_and_the_port_agree(self, source):
        url_port = re.search(r'MAPRT_EMULATOR_URL"\] = "http://127\.0\.0\.1:(\d+)"', source)
        flag_port = re.search(r'"--port", "(\d+)"', source)
        assert url_port and flag_port and url_port.group(1) == flag_port.group(1)

    def test_it_waits_for_the_server_rather_than_sleeping(self, source):
        # A fixed sleep is either too short on a slow runtime or wasted on a fast one.
        assert "/emulator/state" in source
        assert not re.search(r"time\.sleep\(\d+\)\s*$", source, re.M)

    def test_it_moves_into_the_checkout(self, source):
        """Colab opens a notebook detached from its repository.

        Without this the capstone's `../data/MapRT/plans/...` resolves to `/data` and raises
        FileNotFoundError. One chdir makes every relative path behave as it does locally,
        instead of special-casing paths in each notebook.
        """
        assert 'os.chdir(f"{CHECKOUT}/notebooks")' in source

    def test_it_installs_the_package_with_the_notebook_extra(self, source):
        # The extra, not the dependency group: pip cannot install a dependency group.
        assert "maprt-scripting-workshop[notebooks] @ git+" in source

    def test_it_points_at_the_real_repository(self, source):
        assert "REPLACE-ME" not in source
        assert "github.com/tallhamer/SGRT-Scripting-Workshop" in source

    def test_it_serves_the_maprt_catalog(self, source):
        # data/ holds one folder per product; the emulator serves MapRT's, not data/ itself.
        assert '"--data-dir", f"{CHECKOUT}/data/MapRT"' in source
        assert (ROOT / "data" / "MapRT" / "rooms.json").is_file()

    def test_it_does_not_reclone_on_a_rerun(self, source):
        # Re-running the first cell is the standard "have you tried restarting it" move.
        assert "if not os.path.isdir(CHECKOUT)" in source

    def test_the_emulator_output_goes_to_a_file(self, source):
        # uvicorn logs asynchronously; left on stdout they interleave with notebook output.
        assert "maprt-emulator.log" in source
        assert "stdout=log" in source

    def test_it_says_so_when_the_emulator_does_not_start(self, source):
        assert "did not start" in source


class TestColabLinks:
    def test_the_index_links_every_notebook_to_colab(self):
        # The index's own relative links do not work on Colab — it has no shared file browser.
        index = nbformat.read(NOTEBOOK_DIR / "00_start_here.ipynb", as_version=4)
        text = "\n".join(c.source for c in index.cells)
        assert "colab.research.google.com/github/" in text
        for path in NOTEBOOKS:
            if path.name != "00_start_here.ipynb":
                assert path.name in text, f"the index has no Colab link for {path.name}"

    def test_the_readme_has_a_colab_badge_for_every_notebook(self):
        readme = (ROOT / "README.md").read_text()
        for path in NOTEBOOKS:
            assert f"/notebooks/{path.name}" in readme, f"no Colab link for {path.name}"
