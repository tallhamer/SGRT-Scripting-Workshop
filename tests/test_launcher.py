"""``<product>-workshop``: one command that opens a product's workshop.

Ported from the ``workshop-up`` tests when the launcher became product-generic. The regressions
they pin are the same: flags silently dropped when run as a console script, Ctrl+C killing the
emulator before Jupyter, and an emulator left running after the session.
"""

import sys

import pytest

from sgrt_workshop import launcher
from sgrt_workshop.products import MAPRT, PRODUCTS, Product

#: A product shaped like AlignRT will be: example files, no API, so no emulator.
FILES_ONLY = Product(name="FilesOnly", command="filesonly-workshop", title="Files-only Workshop")


def _record(monkeypatch):
    """Stub out the processes and the port wait; record what `launch()` did."""
    recorded = {}

    class FakeProcess:
        def terminate(self):
            recorded["terminated"] = True

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, *args, **kwargs):
        recorded["command"] = command
        recorded["popen_kwargs"] = kwargs
        return FakeProcess()

    def fake_run(command, *args, **kwargs):
        recorded["jupyter"] = command

    def fake_wait(host, port, timeout=30.0):
        recorded["waited_port"] = port
        return True

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/jupyter")
    monkeypatch.setattr(launcher, "_wait_for_port", fake_wait)
    return recorded


class TestTheRegistry:
    def test_maprt_is_registered_with_its_emulator(self):
        assert PRODUCTS["MapRT"] is MAPRT
        assert MAPRT.emulator == "maprt_emulator"
        assert MAPRT.command == "maprt-workshop"

    def test_every_command_is_a_console_script(self):
        import tomllib
        from pathlib import Path
        scripts = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml")
                                .read_text())["project"]["scripts"]
        for product in PRODUCTS.values():
            assert product.command in scripts, f"{product.command} is not in pyproject.toml"
            assert scripts[product.command].startswith("sgrt_workshop.launcher:")


class TestFlagsReachTheEmulator:
    def test_it_forwards_sys_argv_when_invoked_as_a_console_script(self, monkeypatch):
        """**The original regression.** No argument, which is how a console script calls it.

        Passing argv explicitly works even with the old bug in place, because `argv or []` is
        then truthy. The failure only appears when argv is None and the flags are on sys.argv.
        """
        recorded = _record(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["maprt-workshop", "--port", "8812", "--seed", "7"])

        launcher.maprt()                     # <- exactly what the console script calls

        assert recorded["command"][1:3] == ["-m", "maprt_emulator"]
        assert "--port" in recorded["command"] and "8812" in recorded["command"]
        assert "--seed" in recorded["command"] and "7" in recorded["command"]
        assert recorded["waited_port"] == 8812, "it waited on the default port, not the given one"

    def test_it_forwards_every_flag(self, monkeypatch):
        recorded = _record(monkeypatch)
        launcher.launch(MAPRT, ["--port", "8812", "--map-source", "synthetic"])
        assert "--map-source" in recorded["command"] and "synthetic" in recorded["command"]

    def test_a_bad_flag_fails_before_anything_starts(self, monkeypatch):
        recorded = _record(monkeypatch)
        with pytest.raises(SystemExit):
            launcher.launch(MAPRT, ["--bogus"])
        assert "command" not in recorded, "the emulator was started despite a bad flag"

    def test_it_says_what_to_do_when_the_port_is_busy(self, monkeypatch):
        _record(monkeypatch)
        monkeypatch.setattr(launcher, "_wait_for_port", lambda host, port, timeout=30.0: False)
        with pytest.raises(SystemExit, match="--port 8001"):
            launcher.launch(MAPRT, [])

    def test_a_missing_jupyter_names_the_fix(self, monkeypatch):
        monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
        with pytest.raises(SystemExit, match="uv sync"):
            launcher.launch(MAPRT, [])


class TestShutdownOrder:
    def test_the_emulator_is_insulated_from_the_terminals_ctrl_c(self, monkeypatch):
        """`start_new_session=True`, so Ctrl+C does not kill the emulator first.

        Without it, one Ctrl+C stops the emulator immediately while Jupyter survives — Jupyter
        asks you to confirm shutdown — and the student is left with a live notebook server
        talking to a dead appliance.
        """
        recorded = _record(monkeypatch)
        launcher.launch(MAPRT, [])
        assert recorded["popen_kwargs"].get("start_new_session") is True

    def test_the_emulator_is_stopped_once_jupyter_exits(self, monkeypatch):
        recorded = _record(monkeypatch)
        launcher.launch(MAPRT, [])
        assert recorded["terminated"], "the emulator outlived the session"

    def test_a_ctrl_c_during_jupyter_still_stops_the_emulator(self, monkeypatch):
        recorded = _record(monkeypatch)

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(launcher.subprocess, "run", interrupted)
        launcher.launch(MAPRT, [])          # must not propagate as a traceback
        assert recorded["terminated"]

    def test_a_ctrl_c_while_waiting_still_stops_the_emulator(self, monkeypatch):
        recorded = _record(monkeypatch)

        def interrupted(host, port, timeout=30.0):
            raise KeyboardInterrupt

        monkeypatch.setattr(launcher, "_wait_for_port", interrupted)
        launcher.launch(MAPRT, [])
        assert recorded["terminated"]


class TestAProductWithNoEmulator:
    def test_it_opens_jupyter_and_starts_nothing_else(self, monkeypatch):
        recorded = _record(monkeypatch)
        launcher.launch(FILES_ONLY, [])
        assert "command" not in recorded, "a product with no API must not start an emulator"
        assert recorded["jupyter"][:2] == ["jupyter", "lab"]

    def test_it_refuses_options_it_cannot_use(self, monkeypatch):
        _record(monkeypatch)
        with pytest.raises(SystemExit):
            launcher.launch(FILES_ONLY, ["--port", "8001"])


class TestJupyterOpensInTheProductsFolder:
    @pytest.fixture
    def repo(self, tmp_path):
        (tmp_path / "notebooks" / "MapRT").mkdir(parents=True)
        (tmp_path / "src" / "thing").mkdir(parents=True)
        return tmp_path

    def test_from_the_repository_root(self, repo):
        assert launcher.notebooks_dir(MAPRT, repo) == (repo / "notebooks" / "MapRT").resolve()

    def test_from_a_subdirectory(self, repo):
        assert launcher.notebooks_dir(MAPRT, repo / "src" / "thing") == \
            (repo / "notebooks" / "MapRT").resolve()

    def test_falls_back_to_the_working_directory(self, tmp_path):
        # Better than failing: Jupyter opens and the student can navigate.
        assert launcher.notebooks_dir(MAPRT, tmp_path) == tmp_path.resolve()

    def test_jupyter_is_given_the_folder(self, monkeypatch, repo):
        recorded = _record(monkeypatch)
        monkeypatch.chdir(repo)
        launcher.launch(MAPRT, [])
        assert recorded["jupyter"][-1] == str((repo / "notebooks" / "MapRT").resolve())
