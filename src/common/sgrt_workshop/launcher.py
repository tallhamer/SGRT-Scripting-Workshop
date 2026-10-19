"""``<product>-workshop`` — open one product's workshop in a single command.

``uv run maprt-workshop`` starts the MapRT emulator, waits for it, then opens Jupyter Lab in
``notebooks/MapRT/``. Ctrl+C stops both. A product with no emulator — every product except MapRT,
whose notebooks work on example files instead of an API — just opens Jupyter in its folder.

The two-terminal version (``uv run maprt-emulator`` in one, ``uv run jupyter lab notebooks/MapRT``
in the other) is what the MapRT workshop teaches, because that separation is what the real thing
looks like: an appliance somewhere, and your code somewhere else. This exists for anyone fighting
their terminal instead of learning the API.
"""

import argparse
import importlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from sgrt_workshop.products import PRODUCTS


def find_upwards(relative, start=None):
    """``<ancestor>/relative`` for the nearest ancestor of ``start`` (cwd) that has it, or None.

    Walking up rather than trusting the working directory means a command behaves the same
    whether it is run from the repository root or from somewhere inside it.
    """
    here = Path(start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / relative
        if candidate.is_dir():
            return candidate
    return None


def notebooks_dir(product, start=None):
    """``notebooks/<product>/``, found by walking up; the working directory if there is none.

    Falling back is better than failing: Jupyter opens, and the student can navigate.
    """
    return find_upwards(Path("notebooks") / product.folder, start) or Path(start or Path.cwd()).resolve()


def _wait_for_port(host, port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def launch(product, argv=None):
    """Open ``product``'s workshop. ``argv=None`` reads ``sys.argv``, as a console script must.

    An earlier version of this (``workshop-up``) wrote ``parse_args(argv or [])`` — so as a
    console script, where argv is None, it silently discarded the command line and
    ``workshop-up --port 8812`` started the emulator on 8000. Read sys.argv explicitly.
    """
    forwarded = list(sys.argv[1:] if argv is None else argv)

    if product.emulator is None:
        # Nothing to forward options to. Parsing anyway makes --help work and a stray flag fail
        # loudly instead of being ignored.
        argparse.ArgumentParser(
            prog=product.command,
            description=f"Open the {product.title} in Jupyter Lab.",
        ).parse_args(forwarded)
    else:
        emulator_cli = importlib.import_module(f"{product.emulator}.cli")
        # Before anything starts, so --help and a bad flag are reported at the prompt.
        host, port = emulator_cli.address(forwarded, prog=product.command)

    if shutil.which("jupyter") is None:
        raise SystemExit(
            f"{product.command}: `jupyter` is not installed. Run `uv sync` first (it installs "
            f"Jupyter), or start Jupyter yourself: `uv run jupyter lab notebooks/{product.folder}`."
        )

    notebooks = notebooks_dir(product)

    if product.emulator is None:
        _run_jupyter(notebooks)
        return

    # start_new_session puts the emulator in its own process group, so the terminal's Ctrl+C
    # does NOT reach it. Without that, one Ctrl+C kills the emulator immediately while Jupyter
    # survives (Jupyter asks you to confirm shutdown) — leaving a live notebook server talking
    # to a dead appliance, which is the most confusing possible state to be in. This way the
    # emulator outlives Ctrl+C and is stopped by the `finally` below, once Jupyter has exited.
    server = subprocess.Popen([sys.executable, "-m", product.emulator, *forwarded],
                              start_new_session=True)
    try:
        if not _wait_for_port(host, port):
            server.terminate()
            raise SystemExit(
                f"{product.command}: the emulator did not come up on {host}:{port}. "
                f"Something may already be using that port — try --port {port + 1}."
            )
        print(f"\nThe emulator is up on http://{host}:{port}. Starting Jupyter Lab...\n", flush=True)
        _run_jupyter(notebooks)
    except KeyboardInterrupt:
        # A Ctrl+C while waiting for the emulator to come up.
        print("\nShutting down.", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


def _run_jupyter(notebooks):
    try:
        subprocess.run(["jupyter", "lab", str(notebooks)], check=False)
    except KeyboardInterrupt:
        # Ctrl+C reaches Jupyter; swallow it here so the shutdown is the last word rather than a
        # traceback on top of it.
        print("\nShutting down.", flush=True)


# -- console scripts: one per product -----------------------------------------------------------

def maprt():
    """``maprt-workshop``."""
    launch(PRODUCTS["MapRT"])
