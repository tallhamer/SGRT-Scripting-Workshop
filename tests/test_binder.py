"""The Binder configuration.

Binder cannot be tested from here — it needs Docker and a push to GitHub — so these check the
things that *can* be checked locally, which is most of what actually goes wrong: a requirements
file that has drifted from the lock, a start script that is not executable, a hard-coded path
that does not exist.

What was verified by hand (there is no way to assert it here, so it is recorded):

* `pip install -r binder/requirements.txt` into a clean venv with **plain pip**, no uv — all 129
  packages, no conflicts.
* `binder/postBuild` against that venv: the project installs, both packages import, and the
  `maprt-emulator` console script runs.
* `binder/start` launches the emulator, exports the environment a notebook needs, and
  `05_clearance_maps.ipynb` then executes all 58 cells in 10 seconds using only that venv.
* `/docs` answers HTTP 200, which is what jupyter-server-proxy serves through the Binder URL.
* repo2docker 2026.4.0 ships an environment for the Python version `runtime.txt` asks for.

What is **not** verified: the actual Binder build. That needs Docker, which is not available
here. The badge has to be clicked once after the first push — see the README.
"""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BINDER = ROOT / "binder"


class TestTheFilesExist:
    @pytest.mark.parametrize("name", ["requirements.txt", "runtime.txt", "postBuild", "start"])
    def test_present(self, name):
        assert (BINDER / name).is_file(), f"binder/{name} is missing"

    @pytest.mark.parametrize("name", ["postBuild", "start"])
    def test_executable(self, name):
        # repo2docker runs these directly. Without the execute bit the build fails late, with a
        # permission error that does not obviously point here. Git preserves the mode.
        mode = (BINDER / name).stat().st_mode
        assert mode & stat.S_IXUSR, f"binder/{name} is not executable (chmod +x it)"

    @pytest.mark.parametrize("name", ["postBuild", "start"])
    def test_is_valid_shell(self, name):
        result = subprocess.run(["bash", "-n", str(BINDER / name)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestRequirements:
    def test_in_sync_with_the_lockfile(self):
        """The whole point of generating it: Binder installs what `uv sync` installs.

        A hand-edited requirements.txt drifts, and then a Binder session runs different code from
        every local clone — which is the hardest kind of "works on my machine" to diagnose.
        """
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "common" / "export_requirements.py"), "--check"],
            capture_output=True, text=True, cwd=ROOT, env={**os.environ},
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_says_it_is_generated(self):
        assert "do not edit" in (BINDER / "requirements.txt").read_text().lower()

    def test_does_not_install_the_project_itself(self):
        # postBuild does that, from the checkout. Listing it here would try to resolve it from
        # PyPI, where it does not exist.
        text = (BINDER / "requirements.txt").read_text()
        assert not re.search(r"(?m)^maprt-scripting-workshop", text)

    def test_carries_the_notebook_dependencies(self):
        text = (BINDER / "requirements.txt").read_text()
        for package in ("jupyterlab", "matplotlib", "pandas", "pydicom", "plotly"):
            assert re.search(rf"(?m)^{package}==", text), f"{package} is missing"

    def test_carries_jupyter_server_proxy(self):
        # Binder-only, so it is not in pyproject.toml. Without it the emulator is reachable from
        # a notebook cell but /docs cannot be opened in a browser tab.
        assert "jupyter-server-proxy" in (BINDER / "requirements.txt").read_text()

    def test_it_does_not_pin_the_dev_tools(self):
        # Binder does not run the test suite; shipping pytest and ruff would slow every build.
        text = (BINDER / "requirements.txt").read_text()
        for package in ("pytest", "ruff"):
            assert not re.search(rf"(?m)^{package}==", text), f"{package} should not be here"

    def test_the_pins_work_on_both_supported_pythons(self):
        """Markers for 3.11 *and* 3.12, so the build survives repo2docker ignoring runtime.txt.

        `runtime.txt` asks for python-3.12. If repo2docker does not honour it, or drops support,
        the fallback must still resolve — and it does, because the export is universal: numpy and
        contourpy are each pinned twice with `python_full_version` markers.
        """
        text = (BINDER / "requirements.txt").read_text()
        assert "python_full_version < '3.12'" in text
        assert "python_full_version >= '3.12'" in text


class TestRuntime:
    def test_asks_for_a_python_the_project_supports(self):
        """And one repo2docker ships an environment for.

        Verified against repo2docker 2026.4.0, which has
        ``buildpacks/conda/environment.py-3.12-linux-64.lock`` — so ``python-3.12`` resolves. The
        range here is the overlap between what repo2docker ships (2.7 through 3.14) and what
        pyproject.toml allows (>=3.11,<3.14).
        """
        requested = (BINDER / "runtime.txt").read_text().strip()
        assert re.fullmatch(r"python-3\.(11|12|13)", requested), requested

    def test_it_matches_the_version_pinned_for_local_work(self):
        # Not a hard requirement — the pins are universal — but a gratuitous difference between
        # what students run locally and what Binder runs is worth catching.
        local = (ROOT / ".python-version").read_text().strip()
        assert (BINDER / "runtime.txt").read_text().strip() == f"python-{local}"


class TestStartScript:
    @staticmethod
    @pytest.fixture(scope="class")
    def start():
        return (BINDER / "start").read_text()

    def test_it_execs_the_command_it_was_given(self, start):
        # Without `exec "$@"` the notebook server never starts and the session is a blank stare.
        assert 'exec "$@"' in start

    def test_it_does_not_abort_on_error(self, start):
        """No `set -e`. A session whose first cell says "EmulatorNotRunning" explains itself;
        a container that refuses to start does not."""
        assert not re.search(r"(?m)^set -e", start)

    def test_it_exports_what_connect_reads(self, start):
        # On Binder the environment is the channel — the notebook server may start before the
        # emulator has written .maprt_emulator/server.json, so the file would be a race.
        assert "export MAPRT_EMULATOR_TOKEN" in start
        assert "export MAPRT_EMULATOR_URL" in start

    def test_the_url_and_the_port_it_starts_agree(self, start):
        url_port = re.search(r"MAPRT_EMULATOR_URL=\"http://127\.0\.0\.1:(\d+)\"", start)
        flag_port = re.search(r"--port (\d+)", start)
        assert url_port and flag_port
        assert url_port.group(1) == flag_port.group(1), "the exported URL names a different port"

    def test_it_passes_the_token_it_exported(self, start):
        assert '--token "$MAPRT_EMULATOR_TOKEN"' in start

    def test_it_points_at_a_data_directory_that_exists(self, start):
        assert '--data-dir "$REPO_DIR/data/MapRT"' in start
        assert (ROOT / "data" / "MapRT" / "rooms.json").is_file()

    def test_it_waits_and_reports_whether_the_emulator_came_up(self, start):
        # The failure this catches is silent: nohup returns happily even when the port is busy,
        # and the student-facing error then points nowhere near the cause.
        assert "WARNING" in start
        assert "/emulator/state" in start


class TestPostBuild:
    @staticmethod
    @pytest.fixture(scope="class")
    def post_build():
        return (BINDER / "postBuild").read_text()

    def test_it_installs_the_project_without_resolving_again(self, post_build):
        # --no-deps: requirements.txt already pinned everything from uv.lock. Letting pip resolve
        # here could install a different version than a local `uv sync` gets.
        assert "pip install --no-deps ." in post_build

    def test_it_verifies_the_install_rather_than_assuming_it(self, post_build):
        # Fail the build, not the student's first cell.
        assert "import sgrt_workshop, maprt_emulator, maprt_workshop" in post_build
        assert "maprt-emulator --help" in post_build
        assert "maprt-workshop --help" in post_build

    def test_it_aborts_on_failure(self, post_build):
        # Opposite of `start`: a broken image should not be published at all.
        assert re.search(r"(?m)^set -euo pipefail", post_build)
