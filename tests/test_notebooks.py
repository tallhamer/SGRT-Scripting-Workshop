"""Run every notebook against a live emulator.

A notebook that does not execute is worse than no notebook: it fails in front of a room. So each
one is run top to bottom with `nbclient`, against a real `maprt-emulator` subprocess, exactly as a
student would.

This is the slowest file in the suite by a long way. `-m "not slow"` skips it when you are
iterating on something else; CI runs everything.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = ROOT / "notebooks"

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")

NOTEBOOKS = sorted(NOTEBOOK_DIR.glob("*.ipynb"))


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def emulator(tmp_path_factory):
    """A real `maprt-emulator` process the notebooks talk to.

    `--map-seconds 0` removes the deliberate streaming delay: the notebooks request several maps
    each and three seconds apiece would make this unbearable. Nothing else is changed, so the
    notebooks run against the behaviour they describe.
    """
    port = _free_port()
    workdir = tmp_path_factory.mktemp("notebooks")
    token = "notebook-test-token"

    process = subprocess.Popen(
        [sys.executable, "-m", "maprt_emulator", "--port", str(port), "--token", token,
         "--state-dir", str(workdir / ".maprt_emulator"), "--map-seconds", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"maprt-emulator exited early:\n{process.stdout.read()}")
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.2)
    else:
        process.terminate()
        pytest.fail("maprt-emulator did not start")

    yield {"MAPRT_EMULATOR_URL": f"http://127.0.0.1:{port}", "MAPRT_EMULATOR_TOKEN": token}

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.mark.slow
@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_the_notebook_runs_top_to_bottom(path, emulator, monkeypatch):
    for key, value in emulator.items():
        monkeypatch.setenv(key, value)

    notebook = nbformat.read(path, as_version=4)
    client = nbclient.NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        # Run from notebooks/, as a student would — notebook 08 opens ../data/MapRT/plans/ relatively.
        resources={"metadata": {"path": str(NOTEBOOK_DIR)}},
    )
    client.execute()


class TestTheNotebooksAreWellFormed:
    """Cheap checks that do not need a kernel, so a broken notebook fails fast.

    Not marked slow — only the execution test is. A class-level ``pytestmark`` would *add* to a
    module-level one rather than replace it, so the mark goes on the one test that earns it.
    """

    def test_there_are_nine_of_them(self):
        assert len(NOTEBOOKS) == 9

    @pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
    def test_no_outputs_are_committed(self, path):
        # Generated notebooks commit clean: readable diffs, and the repo does not grow by a
        # rendered plot every time someone runs a cell.
        notebook = nbformat.read(path, as_version=4)
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == "code":
                assert not cell.get("outputs"), f"{path.name} cell {index} has outputs"
                assert cell.get("execution_count") is None, f"{path.name} cell {index} has a count"

    @pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
    def test_it_opens_with_the_not_a_medical_device_notice(self, path):
        first = nbformat.read(path, as_version=4).cells[0]
        assert "Not a medical device" in first.source

    def test_the_index_links_to_every_other_notebook(self):
        index = nbformat.read(NOTEBOOK_DIR / "00_start_here.ipynb", as_version=4)
        text = "\n".join(cell.source for cell in index.cells)
        for path in NOTEBOOKS:
            if path.name != "00_start_here.ipynb":
                assert f"]({path.name})" in text, f"the index does not link to {path.name}"

    def test_every_notebook_links_onwards_or_back(self):
        # So nobody reaches the end of one and has to go hunting for the next.
        for path in NOTEBOOKS:
            text = "\n".join(c.source for c in nbformat.read(path, as_version=4).cells)
            assert ".ipynb)" in text, f"{path.name} links nowhere"

    def test_they_are_up_to_date_with_their_source(self):
        # The .ipynb files are generated from scripts/notebook_content. If someone edits a
        # notebook in Jupyter and does not mirror it there, the next build silently reverts them.
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_notebooks.py"), "--check"],
            capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")},
        )
        assert result.returncode == 0, result.stdout + result.stderr
