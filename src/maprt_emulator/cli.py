"""``maprt-emulator`` and ``workshop-up`` — starting the emulator, and the token banner.

The emulator mints a **fresh token every time it starts** and makes it available two ways:

* printed in a banner, for someone watching a terminal;
* written to ``.maprt_emulator/token``, for everyone else.

The file is not a convenience, it is the only thing that works on Binder and Colab, where the
server runs as a background process and nobody ever sees its output.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from maprt_emulator.app import create_app
from maprt_emulator.maps import MapLibrary, MapLibraryError
from maprt_emulator.settings import LICENSABLE, EmulatorSettings
from maprt_emulator.store import Catalog, CatalogError

BANNER_WIDTH = 74


def _box(lines):
    inner = BANNER_WIDTH - 2
    out = ["╭" + "─" * inner + "╮"]
    for line in lines:
        out.append("│" + line.ljust(inner)[:inner] + "│")
    out.append("╰" + "─" * inner + "╯")
    return "\n".join(out)


def _elide(path, width):
    """Shorten a path to ``width``, dropping leading components rather than trailing ones.

    Truncating from the right hides the part that matters — *which* data directory this is — and
    cuts mid-word, which reads like a bug in the banner rather than a deliberate shortening.
    """
    text = str(path)
    if len(text) <= width:
        return text
    parts = text.split("/")
    for start in range(1, len(parts)):
        candidate = ".../" + "/".join(parts[start:])
        if len(candidate) <= width:
            return candidate
    # A single component longer than the whole field: nothing to drop, so cut the front.
    return "..." + text[-(width - 3):]


def banner(settings, catalog, token_path, maps=None):
    """The startup box, plus the copy-paste line for a notebook."""
    warnings = []
    if settings.map_source != "auto":
        warnings.append(f"  Maps        --map-source {settings.map_source}")
    if settings.shuffle_map:
        warnings.append("  Maps        triples served in random order")
    if settings.unlicensed:
        warnings.append(f"  Unlicensed  {', '.join(settings.unlicensed)}")
    if settings.auth_401:
        warnings.append("  Auth        a wrong token returns HTTP 401 (not the spec's 200)")
    if settings.strict_user_agent:
        warnings.append("  User-Agent  required (VisionRT.Integration.Saturn/...)")
    if settings.open_ping:
        warnings.append("  Ping        served WITHOUT a token")

    lines = [
        "  MapRT Emulator  —  NOT a medical device. Teaching only.",
        "",
        f"  Base URL    {settings.base_url}",
        f"  Docs        {settings.base_url}/docs",
        f"  Data        {catalog.summary()}" + (f" · {maps.summary()}" if maps else ""),
        f"              {_elide(settings.data_dir, BANNER_WIDTH - 16)}",
        f"  Token file  {token_path}",
    ]
    if warnings:
        lines.extend(["", *warnings])

    return "\n".join([
        "",
        _box(lines),
        "",
        "Copy this line into your notebook (or let it read the token file):",
        "",
        f"    MAPRT_EMULATOR_TOKEN={settings.resolve_token()}",
        "",
        "Press Ctrl+C to stop the server.",
        "",
    ])


def _parser():
    parser = argparse.ArgumentParser(
        prog="maprt-emulator",
        description="Run a local emulator of the Vision RT MapRT API 2.0. Teaching use only.",
    )
    parser.add_argument("--host", default=None, help="interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="port to bind (default 8000)")
    parser.add_argument("--token", default=None,
                        help="use this API token instead of generating a fresh one")
    parser.add_argument("--data-dir", default=None,
                        help="the catalog to serve (default: the nearest data/MapRT/ directory)")
    parser.add_argument("--state-dir", default=None,
                        help="where to write the token file (default .maprt_emulator)")
    parser.add_argument("--unlicensed", default=None,
                        help=f"comma-separated features to report as unlicensed: "
                             f"{', '.join(LICENSABLE)}")
    parser.add_argument("--latency-ms", type=int, default=None,
                        help="artificial delay per request, so calls are visibly not free")
    parser.add_argument("--map-source", default=None, choices=("auto", "recorded", "synthetic"),
                        help="auto prefers a recorded map; recorded refuses to invent one; "
                             "synthetic ignores the recordings (default auto)")
    parser.add_argument("--seed", type=int, default=None,
                        help="varies the clearance model slightly; same seed, same maps")
    parser.add_argument("--map-seconds", type=float, default=None,
                        help="roughly how long GetMap takes to stream (default 3; a real "
                             "appliance takes minutes)")
    parser.add_argument("--shuffle-map", action="store_true",
                        help="randomise the order of the map's triples; the spec says the list "
                             "is unordered, so a client must not depend on it")
    parser.add_argument("--auth-401", action="store_true",
                        help="reject a wrong token with HTTP 401 instead of the spec's 200")
    parser.add_argument("--strict-user-agent", action="store_true",
                        help="refuse requests without a VisionRT.Integration.Saturn/ User-Agent")
    parser.add_argument("--open-ping", action="store_true",
                        help="serve /integration/ping without a token (debugging aid)")
    parser.add_argument("--check-data", action="store_true",
                        help="validate the data directory and exit, without starting a server")
    parser.add_argument("--reload", action="store_true", help="reload on code changes (developing)")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    return parser


def settings_from_args(args):
    """Turn parsed arguments into :class:`EmulatorSettings`, leaving unset flags to the environment."""
    overrides = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.token is not None:
        overrides["token"] = args.token
    if args.data_dir is not None:
        overrides["data_dir"] = Path(args.data_dir)
    if args.state_dir is not None:
        overrides["state_dir"] = Path(args.state_dir)
    if args.latency_ms is not None:
        overrides["latency_ms"] = args.latency_ms
    if args.map_source is not None:
        overrides["map_source"] = args.map_source
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.map_seconds is not None:
        overrides["map_seconds"] = args.map_seconds
    if args.unlicensed is not None:
        features = tuple(f.strip() for f in args.unlicensed.split(",") if f.strip())
        unknown = [f for f in features if f not in LICENSABLE]
        if unknown:
            raise SystemExit(f"maprt-emulator: unknown feature(s) {', '.join(unknown)}. "
                             f"Choose from: {', '.join(LICENSABLE)}")
        overrides["unlicensed"] = features
    # Store-true flags: only pass them when set, so the environment can still turn them on.
    for flag in ("auth_401", "strict_user_agent", "open_ping", "shuffle_map"):
        if getattr(args, flag):
            overrides[flag] = True
    return EmulatorSettings(**overrides)


def main(argv=None):
    args = _parser().parse_args(argv)
    settings = settings_from_args(args)

    if args.check_data:
        # Before the catalog load below, because that one raises on the first problem it meets.
        # The checker reports everything at once, which is what you want while editing data.
        from maprt_emulator.check import main as check_main
        raise SystemExit(check_main(settings.data_dir))

    # Load the catalog here, before uvicorn starts, so a data problem is a clear message at the
    # prompt rather than a traceback inside a worker during someone's first notebook cell.
    try:
        catalog = Catalog.load(settings.data_dir)
    except CatalogError as exc:
        raise SystemExit(f"maprt-emulator: {exc}") from exc

    try:
        maps = MapLibrary.load(settings.data_dir)
    except MapLibraryError as exc:
        raise SystemExit(f"maprt-emulator: {exc}") from exc

    token_path = settings.write_token()
    print(banner(settings, catalog, token_path, maps), flush=True)

    # Build the app HERE, from the settings we just parsed and just described in the banner, and
    # hand uvicorn the object. The alternative — giving uvicorn an import string and letting it
    # call create_app() itself — re-resolves EmulatorSettings from the environment in the server
    # process, so every command-line flag is silently dropped while the banner still claims it
    # is in effect. That is worse than not having the flags.
    #
    # --reload is the one case that cannot work this way: reloading means re-importing in a child
    # process, which needs an import string. There, the settings go through the environment
    # instead, which is why they all have to be environment-expressible.
    if args.reload:
        os.environ.update(settings.as_env())
        target, factory = "maprt_emulator.app:create_app", True
    else:
        target, factory = create_app(settings), False

    uvicorn.run(
        target,
        factory=factory,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        log_level=args.log_level,
        # uvicorn would otherwise advertise itself in the Server header; the middleware replaces
        # it with Saturn/... to match a real appliance.
        server_header=False,
    )


# -- workshop-up ------------------------------------------------------------------------------

def _wait_for_port(host, port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def up(argv=None):
    """Start the emulator in the background, wait for it, then launch Jupyter Lab.

    The two-terminal version (``maprt-emulator`` in one, ``jupyter lab`` in the other) is what the
    workshop teaches, because that separation is what the real thing looks like: an appliance
    somewhere, and your code somewhere else. This exists for anyone fighting their terminal
    instead of learning the API. Ctrl+C stops both.
    """
    # argv=None means "read sys.argv", which is what both of these need. An earlier version wrote
    # `parse_args(argv or [])` and passed `*(argv or [])` to the subprocess — so as a console
    # script, where argv is None, BOTH silently discarded the command line and
    # `workshop-up --port 8812` started the emulator on 8000. Exactly the bug Phase 2 fixed in
    # `main()`, reintroduced here because nothing ran this function until Phase 7.
    forwarded = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(forwarded)
    settings = settings_from_args(args)

    if shutil.which("jupyter") is None:
        raise SystemExit(
            "workshop-up: `jupyter` is not installed. Run `uv sync` first (it installs Jupyter), "
            "or start the two pieces yourself: `uv run maprt-emulator` and `uv run jupyter lab`."
        )

    notebooks = _notebooks_dir()

    # start_new_session puts the emulator in its own process group, so the terminal's Ctrl+C
    # does NOT reach it. Without that, one Ctrl+C kills the emulator immediately while Jupyter
    # survives (Jupyter asks you to confirm shutdown) — leaving a live notebook server talking
    # to a dead appliance, which is the most confusing possible state to be in. This way the
    # emulator outlives Ctrl+C and is stopped by the `finally` below, once Jupyter has actually
    # exited.
    server = subprocess.Popen([sys.executable, "-m", "maprt_emulator", *forwarded],
                              start_new_session=True)
    try:
        if not _wait_for_port(settings.host, settings.port):
            server.terminate()
            raise SystemExit(
                f"workshop-up: the emulator did not come up on {settings.host}:{settings.port}. "
                f"Something may already be using that port — try --port 8001."
            )
        print(f"\nEmulator is up on {settings.base_url}. Starting Jupyter Lab...\n", flush=True)
        subprocess.run(["jupyter", "lab", str(notebooks)], check=False)
    except KeyboardInterrupt:
        # Ctrl+C reaches both processes; swallow it here so the shutdown below is the last word
        # rather than a traceback on top of it.
        print("\nShutting down.", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


def _notebooks_dir():
    """The ``notebooks`` directory, found by walking up — so this works from anywhere in the repo.

    ``jupyter lab notebooks`` only works when the command happens to be run from the repository
    root. Falling back to the working directory is better than failing: Jupyter opens, and the
    student can navigate.
    """
    here = Path.cwd().resolve()
    for directory in [here, *here.parents]:
        candidate = directory / "notebooks"
        if candidate.is_dir():
            return candidate
    return here


if __name__ == "__main__":
    main()
