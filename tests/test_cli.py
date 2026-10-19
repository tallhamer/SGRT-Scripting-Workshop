"""The CLI: token generation and recording, flag plumbing, and the banner."""

import stat
import sys

import pytest

from maprt_emulator import cli
from maprt_emulator.cli import _elide, _parser, banner, settings_from_args
from maprt_emulator.settings import EmulatorSettings
from maprt_emulator.store import Catalog


def parse(*argv):
    return settings_from_args(_parser().parse_args(argv))


class TestToken:
    def test_a_fresh_token_is_generated_when_none_is_given(self, tmp_path):
        settings = EmulatorSettings(token=None, state_dir=tmp_path / "state")
        token = settings.resolve_token()
        assert token and len(token) > 20

    def test_two_starts_generate_different_tokens(self, tmp_path):
        # The point of generating one per start: a workshop credential is disposable, and nobody
        # should end up with a long-lived shared secret in their notes.
        first = EmulatorSettings(token=None, state_dir=tmp_path).resolve_token()
        second = EmulatorSettings(token=None, state_dir=tmp_path).resolve_token()
        assert first != second

    def test_an_explicit_token_is_respected(self, tmp_path):
        assert EmulatorSettings(token="pinned", state_dir=tmp_path).resolve_token() == "pinned"

    def test_is_written_to_the_state_directory(self, tmp_path):
        settings = EmulatorSettings(token="pinned", state_dir=tmp_path / "state")
        path = settings.write_token()
        assert path == tmp_path / "state" / "token"
        assert path.read_text(encoding="utf-8").strip() == "pinned"

    def test_the_token_file_is_owner_readable_only(self, tmp_path):
        # It is a throwaway credential for a fake appliance, but a workshop that handles the
        # disposable one sloppily teaches handling the real one sloppily.
        path = EmulatorSettings(token="pinned", state_dir=tmp_path / "state").write_token()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_the_client_library_finds_it_by_walking_up(self, tmp_path, monkeypatch):
        from maprt_workshop.client import find_token
        EmulatorSettings(token="written-here", state_dir=tmp_path / ".maprt_emulator").write_token()
        nested = tmp_path / "notebooks" / "deeper"
        nested.mkdir(parents=True)
        monkeypatch.delenv("MAPRT_EMULATOR_TOKEN", raising=False)
        assert find_token(nested) == "written-here"

    def test_the_environment_variable_wins_over_the_file(self, tmp_path, monkeypatch):
        # How Binder and Colab supply it, where no one reads the banner.
        from maprt_workshop.client import find_token
        EmulatorSettings(token="from-file", state_dir=tmp_path / ".maprt_emulator").write_token()
        monkeypatch.setenv("MAPRT_EMULATOR_TOKEN", "from-env")
        assert find_token(tmp_path) == "from-env"


class TestFlags:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("MAPRT_EMULATOR_TOKEN", raising=False)
        settings = parse()
        # 127.0.0.1, not 0.0.0.0: a printed token and fake clinical data have no business being
        # reachable from the rest of the network by default.
        assert settings.host == "127.0.0.1"
        assert settings.port == 8000
        assert settings.unlicensed == ()
        assert settings.auth_401 is False
        assert settings.strict_user_agent is False

    def test_host_and_port(self):
        settings = parse("--host", "0.0.0.0", "--port", "9001")
        assert (settings.host, settings.port) == ("0.0.0.0", 9001)

    def test_unlicensed_is_split_on_commas(self):
        assert parse("--unlicensed", "surfaces,map").unlicensed == ("surfaces", "map")

    def test_an_unknown_feature_is_rejected_with_the_valid_choices(self):
        with pytest.raises(SystemExit, match="surfaces"):
            parse("--unlicensed", "telepathy")

    def test_store_true_flags(self):
        settings = parse("--auth-401", "--strict-user-agent", "--open-ping")
        assert settings.auth_401 and settings.strict_user_agent and settings.open_ping

    def test_unset_flags_leave_the_environment_in_charge(self, monkeypatch):
        # So the Binder/Colab bootstraps can configure by env var without passing flags.
        monkeypatch.setenv("MAPRT_EMULATOR_PORT", "7777")
        assert parse().port == 7777

    def test_an_explicit_flag_beats_the_environment(self, monkeypatch):
        monkeypatch.setenv("MAPRT_EMULATOR_PORT", "7777")
        assert parse("--port", "8123").port == 8123


class TestBanner:
    def test_shows_the_url_token_and_data_summary(self, data_dir, tmp_path):
        settings = EmulatorSettings(token="shown-token", data_dir=data_dir, state_dir=tmp_path,
                               port=8123)
        text = banner(settings, Catalog.load(data_dir), tmp_path / "token")
        assert "http://127.0.0.1:8123" in text
        assert "MAPRT_EMULATOR_TOKEN=shown-token" in text
        assert "3 patients" in text
        assert "NOT a medical device" in text

    def test_warns_about_non_default_behaviour(self, data_dir, tmp_path):
        # Someone debugging a confusing response needs to know the server was told to be weird.
        settings = EmulatorSettings(token="t", data_dir=data_dir, state_dir=tmp_path,
                               unlicensed=("map",), auth_401=True, open_ping=True)
        text = banner(settings, Catalog.load(data_dir), tmp_path / "token")
        assert "Unlicensed" in text and "map" in text
        assert "401" in text
        assert "WITHOUT a token" in text

    def test_the_box_is_not_ragged(self, data_dir, tmp_path):
        settings = EmulatorSettings(token="t", data_dir=data_dir, state_dir=tmp_path)
        lines = [line for line in banner(settings, Catalog.load(data_dir), tmp_path).splitlines()
                 if line.startswith(("╭", "│", "╰"))]
        assert len({len(line) for line in lines}) == 1


class TestElide:
    def test_a_short_path_is_untouched(self):
        assert _elide("/short/data", 58) == "/short/data"

    def test_a_long_path_keeps_the_tail(self):
        # The tail is the informative part — which data directory this is.
        out = _elide("/Users/someone/very/deeply/nested/project/tree/here/data", 30)
        assert len(out) <= 30
        assert out.startswith("...")
        assert out.endswith("/data")

    def test_dropping_one_component_is_enough_for_a_deep_path(self):
        # A deep path with a short tail elides to almost nothing, which is fine — the directory
        # name is what the reader needs, and the full path is in the error messages if it matters.
        assert _elide("/" + "a" * 200 + "/data", 30) == ".../data"

    def test_a_path_with_no_separators_falls_back_to_a_front_cut(self):
        # Nothing to drop, so the fallback branch has to bound it some other way.
        out = _elide("a" * 200, 30)
        assert len(out) == 30
        assert out.startswith("...")

    def test_a_single_over_long_component_is_still_bounded(self):
        out = _elide("/home/" + "b" * 200, 30)
        assert len(out) == 30


class TestAsEnv:
    """The ``--reload`` path's only channel to the server process.

    Covered because the normal path deliberately does *not* use it: see the comment in
    ``cli.main``. If a field is ever added that cannot survive the environment, --reload would
    silently drop it, which is the bug class this whole area already produced once.
    """

    def test_every_field_round_trips(self, monkeypatch, data_dir, tmp_path):
        original = EmulatorSettings(token="t", data_dir=data_dir, state_dir=tmp_path / "s",
                               host="0.0.0.0", port=9100, unlicensed=("surfaces", "map"),
                               latency_ms=25, auth_401=True, strict_user_agent=True,
                               open_ping=True)
        # monkeypatch, not os.environ.update: as_env() is pure, so the test has to be the thing
        # that scopes the change. Writing straight to os.environ here once leaked these settings
        # into every later test and into the subprocesses they start.
        for key, value in original.as_env().items():
            monkeypatch.setenv(key, value)
        restored = EmulatorSettings()
        for field in type(original).model_fields:
            assert getattr(restored, field) == getattr(original, field), field

    def test_false_booleans_round_trip_as_false(self, monkeypatch, tmp_path):
        # "False" must not come back truthy, which a naive str() export would produce.
        for key, value in EmulatorSettings(token="t", state_dir=tmp_path,
                                      auth_401=False).as_env().items():
            monkeypatch.setenv(key, value)
        assert EmulatorSettings().auth_401 is False

    def test_an_empty_unlicensed_tuple_round_trips(self, monkeypatch, tmp_path):
        for key, value in EmulatorSettings(token="t", state_dir=tmp_path,
                                      unlicensed=()).as_env().items():
            monkeypatch.setenv(key, value)
        assert EmulatorSettings().unlicensed == ()


class TestWorkshopUpForwardsItsFlags:
    """`workshop-up --port N` must actually start the simulator on N.

    Phase 2 fixed "every command-line flag is silently dropped" in `main()`. The same bug was
    sitting in `up()` the whole time — `parse_args(argv or [])` discards sys.argv when argv is
    None, which is exactly how a console script is invoked — and nothing ran that function until
    someone tried it. These pin both halves: what `up()` parses, and what it forwards.
    """

    def test_it_reads_sys_argv_when_called_as_a_console_script(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["workshop-up", "--port", "8812"])
        forwarded = list(sys.argv[1:])
        assert settings_from_args(_parser().parse_args(forwarded)).port == 8812

    def test_it_forwards_sys_argv_when_invoked_as_a_console_script(self, monkeypatch):
        """**The actual regression.** `up()` with no argument, which is how the script runs.

        Passing argv explicitly — `up(["--port", "8812"])` — works even with the bug in place,
        because `argv or []` is then truthy. The failure only appears when argv is None and the
        flags are on sys.argv, which is every real invocation. A first version of this test
        passed against the broken code; testing the wrong entry point is worse than not testing.
        """
        recorded = _record_subprocess(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["workshop-up", "--port", "8812", "--seed", "7"])

        cli.up()                                   # <- no argument, as the console script calls it

        assert "--port" in recorded["command"] and "8812" in recorded["command"]
        assert "--seed" in recorded["command"] and "7" in recorded["command"]
        assert recorded["waited_port"] == 8812, "it waited on the default port, not the given one"

    def test_it_forwards_every_flag_to_the_simulator(self, monkeypatch, tmp_path):
        """The flags `up()` hands the subprocess must be the ones it was given."""
        recorded = {}

        class FakeProcess:
            def terminate(self):
                recorded["terminated"] = True

            def wait(self, timeout=None):
                return 0

        def fake_popen(command, *args, **kwargs):
            recorded["command"] = command
            return FakeProcess()

        monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)
        monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/jupyter")
        monkeypatch.setattr(cli, "_wait_for_port", lambda host, port, timeout=30.0: True)

        cli.up(["--port", "8812", "--map-source", "synthetic", "--seed", "7"])

        assert "--port" in recorded["command"]
        assert "8812" in recorded["command"]
        assert "--map-source" in recorded["command"]
        assert "synthetic" in recorded["command"]
        assert recorded["terminated"], "the simulator must be stopped when Jupyter exits"

    def test_it_waits_on_the_port_it_was_given(self, monkeypatch):
        waited = {}
        monkeypatch.setattr(cli.subprocess, "Popen",
                            lambda *a, **k: type("P", (), {"terminate": lambda s: None,
                                                           "wait": lambda s, timeout=None: 0})())
        monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)
        monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/jupyter")

        def fake_wait(host, port, timeout=30.0):
            waited["port"] = port
            return True

        monkeypatch.setattr(cli, "_wait_for_port", fake_wait)
        cli.up(["--port", "8813"])
        assert waited["port"] == 8813

    def test_it_says_what_to_do_when_the_port_is_busy(self, monkeypatch):
        monkeypatch.setattr(cli.subprocess, "Popen",
                            lambda *a, **k: type("P", (), {"terminate": lambda s: None,
                                                           "wait": lambda s, timeout=None: 0})())
        monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/jupyter")
        monkeypatch.setattr(cli, "_wait_for_port", lambda host, port, timeout=30.0: False)

        with pytest.raises(SystemExit, match="--port 8001"):
            cli.up([])

    def test_a_missing_jupyter_names_the_fix(self, monkeypatch):
        monkeypatch.setattr(cli.shutil, "which", lambda name: None)
        with pytest.raises(SystemExit, match="uv sync"):
            cli.up([])


def _record_subprocess(monkeypatch):
    """Stub out Popen/run/which/_wait_for_port and record what `up()` did."""
    recorded = {}

    class FakeProcess:
        def terminate(self):
            recorded["terminated"] = True

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, *args, **kwargs):
        recorded["command"] = command
        return FakeProcess()

    def fake_wait(host, port, timeout=30.0):
        recorded["waited_port"] = port
        return True

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/jupyter")
    monkeypatch.setattr(cli, "_wait_for_port", fake_wait)
    return recorded


class TestNotebooksDirIsFoundFromAnywhere:
    def test_found_from_the_repository_root(self, tmp_path, monkeypatch):
        (tmp_path / "notebooks").mkdir()
        monkeypatch.chdir(tmp_path)
        assert cli._notebooks_dir() == (tmp_path / "notebooks").resolve()

    def test_found_from_a_subdirectory(self, tmp_path, monkeypatch):
        # `jupyter lab notebooks` only works from the repository root. Walking up means
        # workshop-up behaves the same wherever it is run from.
        (tmp_path / "notebooks").mkdir()
        deeper = tmp_path / "src" / "thing"
        deeper.mkdir(parents=True)
        monkeypatch.chdir(deeper)
        assert cli._notebooks_dir() == (tmp_path / "notebooks").resolve()

    def test_falls_back_to_the_working_directory(self, tmp_path, monkeypatch):
        # Better than failing: Jupyter opens and the student can navigate.
        monkeypatch.chdir(tmp_path)
        assert cli._notebooks_dir() == tmp_path.resolve()


class TestWorkshopUpShutdownOrder:
    def test_the_simulator_is_insulated_from_the_terminals_ctrl_c(self, monkeypatch):
        """`start_new_session=True`, so Ctrl+C does not kill the simulator first.

        Without it, one Ctrl+C stops the simulator immediately while Jupyter survives — Jupyter
        asks you to confirm shutdown — and the student is left with a live notebook server
        talking to a dead appliance. Verified by hand before this test was written: the
        simulator's port closed while Jupyter kept running.
        """
        recorded = _record_subprocess(monkeypatch)
        captured = {}

        def fake_popen(command, *args, **kwargs):
            captured["kwargs"] = kwargs
            recorded["command"] = command
            return type("P", (), {"terminate": lambda s: recorded.__setitem__("terminated", True),
                                  "wait": lambda s, timeout=None: 0})()

        monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
        cli.up([])
        assert captured["kwargs"].get("start_new_session") is True

    def test_the_simulator_is_stopped_once_jupyter_exits(self, monkeypatch):
        recorded = _record_subprocess(monkeypatch)
        cli.up([])
        assert recorded["terminated"], "the simulator outlived the session"

    def test_a_ctrl_c_during_jupyter_still_stops_the_simulator(self, monkeypatch):
        recorded = _record_subprocess(monkeypatch)

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.subprocess, "run", interrupted)
        cli.up([])          # must not propagate the KeyboardInterrupt as a traceback
        assert recorded["terminated"]


class TestConnectDiagnosesAProxy:
    """A corporate proxy breaks loopback connections, and the error looks like DNS.

    Verified by hand: with HTTP_PROXY set, `httpx2.get("http://127.0.0.1:8821/...")` fails with
    "nodename nor servname provided, or not known" — which reads as a name-resolution problem and
    sends people hunting in the wrong place. Nothing proxies 127.0.0.1, but the client does not
    know that unless NO_PROXY says so.
    """

    def _message(self, monkeypatch, url="http://127.0.0.1:8000", **env):
        from maprt_workshop import client as workshop_client
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                     "MAPRT_EMULATOR_URL", "MAPRT_EMULATOR_TOKEN"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(workshop_client, "find_server", lambda start=None: {})
        return workshop_client._unreachable_message(url, None, OSError("boom"))

    def test_it_names_the_proxy_variable_and_the_fix(self, monkeypatch):
        message = self._message(monkeypatch, HTTP_PROXY="http://proxy.invalid:8080")
        assert "HTTP_PROXY" in message
        assert "NO_PROXY" in message

    def test_it_stays_quiet_when_no_proxy_is_set(self, monkeypatch):
        assert "NO_PROXY" not in self._message(monkeypatch)

    def test_it_stays_quiet_for_a_non_loopback_address(self, monkeypatch):
        # A real appliance on the clinical network might legitimately need the proxy settings.
        message = self._message(monkeypatch, url="https://maprt.hospital.local:5000",
                                HTTPS_PROXY="http://proxy.invalid:8080")
        assert "NO_PROXY" not in message

    def test_it_always_says_which_address_it_tried(self, monkeypatch):
        assert "http://127.0.0.1:8000" in self._message(monkeypatch)
