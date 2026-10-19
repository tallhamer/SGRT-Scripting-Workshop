"""How the emulator is configured, and how it finds its data and writes its token.

Every field can be set three ways, in increasing priority: a default here, a
``MAPRT_EMULATOR_``-prefixed environment variable (how the Binder and Colab bootstraps do it), or a
command-line flag (:mod:`maprt_emulator.cli`).
"""

import datetime as dt
import json
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Reported in the ``Server`` header, as a real appliance reports its build (spec §5.1).
SERVER_VERSION = "Saturn/1.2.288.1"

#: Reported by ``/integration/ping``. This is the *API* version, which the spec is careful to
#: keep separate from the product version above (§3.3).
API_VERSION = "2.0.0"

#: Spec §5.1: "User-Agent header set to VisionRT.Integration.Saturn/a.b.x".
USER_AGENT_PREFIX = "VisionRT.Integration.Saturn/"

#: Features a real appliance licenses separately (§2.3.3), and which ``--unlicensed`` can switch
#: off here so a notebook can see ``FeatureNotLicensed`` without one.
LICENSABLE = ("surfaces", "map", "beams")


#: Where this product's catalog lives, relative to the repository root. ``data/`` holds one
#: folder per Vision RT product (MapRT, and later AlignRT, SimRT, …), each with its own
#: git-ignored ``local/`` overlay — see ``data/README.md``.
DATA_SUBDIR = Path("data") / "MapRT"


def find_data_dir(start=None):
    """The ``data/MapRT/`` directory, found by walking up from ``start`` (cwd by default).

    Walking up rather than trusting the working directory means ``maprt-emulator`` behaves the same
    whether it is started from the repository root or from ``notebooks/``.
    """
    here = Path(start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / DATA_SUBDIR
        if (candidate / "rooms.json").is_file():
            return candidate
    # Nothing found: hand back the conventional location so the error names a real path.
    return Path.cwd() / DATA_SUBDIR


class EmulatorSettings(BaseSettings):
    """Emulator configuration."""

    model_config = SettingsConfigDict(env_prefix="MAPRT_EMULATOR_", extra="ignore")

    # -- network ------------------------------------------------------------------------------
    # 127.0.0.1, not 0.0.0.0: this thing has a printed token and fake clinical data, and has no
    # business being reachable from the rest of the network by default.
    host: str = "127.0.0.1"
    port: int = 8000

    # -- auth ---------------------------------------------------------------------------------
    # None means "generate a fresh one at startup". Set MAPRT_EMULATOR_TOKEN to pin it, which is what
    # Binder and Colab do because neither has a terminal banner anyone will read.
    token: str | None = None

    #: Reject a request whose token is wrong with HTTP 401 instead of the spec's 200 +
    #: ``success:false``. Both branches exist in the wild; this exercises the other one.
    auth_401: bool = False

    #: Refuse a request whose ``User-Agent`` is missing or not ``VisionRT.Integration.Saturn/…``.
    #: Off by default so a student's first bare GET works and the requirement can be
    #: taught deliberately rather than as an opening roadblock.
    strict_user_agent: bool = False

    #: Serve ``/integration/ping`` without a token, for debugging connectivity in isolation.
    open_ping: bool = False

    # -- data ---------------------------------------------------------------------------------
    data_dir: Path = Field(default_factory=find_data_dir)

    #: Where the generated token is written (``<state_dir>/token``). The client library finds it
    #: by walking up from the notebook's directory.
    state_dir: Path = Path(".maprt_emulator")

    # -- behaviour ----------------------------------------------------------------------------
    #: Features to report as unlicensed; any of :data:`LICENSABLE`.
    unlicensed: tuple[str, ...] = ()

    #: Artificial delay on envelope endpoints, so a notebook can see that calls are not free.
    latency_ms: int = 0

    # -- the collision map --------------------------------------------------------------------
    #: ``auto`` prefers a recorded map and falls back to the model; ``recorded`` refuses to
    #: invent one; ``synthetic`` ignores the recordings. Pin it for a demo so you know what you
    #: are showing.
    map_source: Literal["auto", "recorded", "synthetic"] = "auto"

    #: Varies the small per-surface margin in the clearance model. Same seed, same maps.
    seed: int = 0

    #: Roughly how long GetMap takes to stream its response. A real appliance takes minutes
    #: (§4.2.1.3); a few seconds is enough for a notebook to see that the body arrives
    #: progressively, without making the workshop tedious.
    map_seconds: float = 3.0

    #: Randomise the order of the map's triples. §5.2.6 says the list is not ordered, so this
    #: turns "you must not rely on the order" from an assertion into something demonstrable.
    shuffle_map: bool = False

    @property
    def token_path(self):
        return self.state_dir / "token"

    @property
    def server_path(self):
        return self.state_dir / "server.json"

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    def resolve_token(self):
        """The token to use, generating and recording one when none was supplied.

        A fresh ``secrets.token_urlsafe(32)`` per start is the point: a workshop token is
        disposable, and nobody should end up with a long-lived shared secret in their notes.
        """
        if self.token:
            return self.token
        self.token = secrets.token_urlsafe(32)
        return self.token

    def write_token(self):
        """Record where this server is and how to authenticate with it.

        Two files, both in :attr:`state_dir`:

        * ``token`` — the bare token, for ``cat``-ing or pasting.
        * ``server.json`` — the **URL as well**, which is what makes a non-default port work.
          Port 8000 is often taken, so a student starts the emulator with ``--port 8001`` and
          then every notebook fails against ``http://127.0.0.1:8000`` with nothing to suggest
          why. The server knows where it is; it should say so rather than leave the notebook
          guessing.

        0600 on both, because one of them is a credential. It is a throwaway credential for a
        fake appliance, but a workshop that handles the disposable one sloppily teaches handling
        the real one sloppily.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._write_private(self.token_path, self.resolve_token() + "\n")
        self._write_private(self.server_path, json.dumps({
            "url": self.base_url,
            "token": self.resolve_token(),
            "pid": os.getpid(),
            "started": dt.datetime.now().isoformat(timespec="seconds"),
        }, indent=2) + "\n")
        return self.token_path

    @staticmethod
    def _write_private(path, text):
        path.write_text(text, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows and some network filesystems; the write itself still succeeded.

    def is_licensed(self, feature):
        return feature not in self.unlicensed

    def as_env(self):
        """Every field as a ``{"MAPRT_EMULATOR_FIELD": "value"}`` mapping. **No side effects.**

        Only the ``--reload`` path needs this: reloading re-imports the app in a child process,
        so the settings have to survive the process boundary, and the environment is the only
        channel. Every field is therefore kept environment-expressible — scalars, or sequences
        that pydantic-settings reads back as JSON.

        It returns the mapping rather than writing it, so the caller decides when the process
        environment changes. An earlier version mutated ``os.environ`` directly and the test
        exercising it leaked settings into every later test and into subprocesses they started.
        A function whose whole job is to describe configuration should not reconfigure the
        process as a side effect of being asked.

        Not used on the normal path, where :func:`maprt_emulator.cli.main` builds the app itself and
        hands uvicorn the object. Going through the environment there would silently drop any
        field this method forgot, which is exactly the bug it exists to avoid.
        """
        exported = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                # str(False) is "False", which pydantic-settings reads as truthy. Be explicit.
                text = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                text = json.dumps(list(value))
            else:
                text = str(value)
            exported[f"MAPRT_EMULATOR_{name.upper()}"] = text
        return exported
