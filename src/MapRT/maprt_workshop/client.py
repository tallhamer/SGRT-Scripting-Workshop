"""A synchronous MapRT API client, plus :func:`connect` for the workshop.

:class:`MapRTClient` is ported from ``maprt_client.http`` in the surface_tools project — the same
endpoints, the same headers, the same disabled peer verification a real appliance's self-signed
certificate needs. It returns parsed values by feeding every response body through
:mod:`maprt_workshop.wire`.

**The HTTP library here is an implementation detail.** This one uses ``httpx2``, the
surface_tools desktop application uses Qt's ``QNetworkAccessManager``, and the specification's own
sample is C#. Nothing about MapRT requires any of them: the API is plain HTTPS, and any client
that can set three headers, send a JSON body and read a response will do — ``requests``,
``urllib.request``, ``curl``, whatever your site already has. Read ``self.headers`` and
``_request`` below and you have everything you need to rewrite this in your library of choice.

The notebooks build their first requests by hand for exactly that reason: you should see the three
headers and the JSON envelope before any class hides them from you. This one is what you graduate
to once you are tired of retyping them.
"""

import json
import logging
import os
from pathlib import Path

import httpx2

from maprt_workshop import wire

# Spec §5.1: "User-Agent header set to VisionRT.Integration.Saturn/a.b.x, where a.b stands for
# API version and x is replaced by a string identifying the calling client." A real appliance may
# refuse a request without it, so there is no sensible empty default.
DEFAULT_USER_AGENT = "VisionRT.Integration.Saturn/2.0.workshop"

# Where the emulator records itself at startup. Read rather than typed so the Binder and Colab
# paths work, where the startup banner is in a log file nobody reads.
STATE_DIR = Path(".maprt_emulator")
TOKEN_FILE = STATE_DIR / "token"
SERVER_FILE = STATE_DIR / "server.json"

DEFAULT_URL = "http://127.0.0.1:8000"


class MapRTClient:
    """Synchronous MapRT API client.

    ``api_url``, ``token`` and ``user_agent`` are read fresh on every request, so they can be
    changed between calls without rebuilding the client. Pass ``transport`` to inject an
    :class:`httpx2.MockTransport` in tests; when it is given, ``verify`` is ignored.
    """

    def __init__(self, api_url=None, token=None, user_agent=None, transport=None, timeout=180.0):
        self.logger = logging.getLogger('maprt_workshop.client.MapRTClient')

        self._api_url = (api_url or DEFAULT_URL).rstrip("/")
        self._token = token
        self._user_agent = user_agent or DEFAULT_USER_AGENT

        # verify=False because a real MapRT appliance presents a self-signed certificate. It is
        # the right call for an appliance on a clinical VLAN whose certificate you cannot replace,
        # and the wrong call for anything on the open internet — know which one you are doing.
        # The emulator speaks plain HTTP by default, where this has no effect. Every HTTP library
        # spells this differently (requests: verify=False; urllib: an ssl context; QNetwork:
        # PeerVerifyMode.VerifyNone) but it is the same decision whichever you use.
        #
        # timeout=180 s mirrors the SaturnSettings default (spec §4.3.3.1). GetMap genuinely can
        # take minutes on a real appliance; a 5-second default would make it look broken.
        self._client = httpx2.Client(verify=False, transport=transport, timeout=timeout)  # noqa: S501

    @property
    def api_url(self):
        return self._api_url

    @api_url.setter
    def api_url(self, value):
        self._api_url = str(value).rstrip("/")

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, value):
        # The token is a secret; log that it changed, never the value.
        self.logger.debug('Setting token in MapRTClient')
        self._token = str(value)

    @property
    def user_agent(self):
        return self._user_agent

    @user_agent.setter
    def user_agent(self, value):
        self._user_agent = str(value)

    @property
    def headers(self):
        """The three headers every MapRT API call carries."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._user_agent,
        }

    def _request(self, method, endpoint, body=None):
        # Single point where a request is built and sent. Every call shares the same headers; the
        # verb, path and (for POST) JSON body vary.
        url = self._api_url + endpoint
        self.logger.debug(f'{method} call made to the "{endpoint}" API endpoint')
        if body is None:
            response = self._client.request(method, url, headers=self.headers)
        else:
            response = self._client.request(method, url, headers=self.headers, json=body)
        # Turn an HTTP 4xx/5xx into a typed MapRTApiError here, so HTTP failures never reach the
        # parsers as if they were data. text is read only on the error path.
        if response.status_code >= 400:
            wire.raise_for_http_status(response.status_code, response.text)
        return response

    # -- the seven documented endpoints ------------------------------------------------------

    def get_status(self):
        """GET /integration/ping — the human-readable status line."""
        response = self._request("GET", "/integration/ping")
        return wire.ping_status(response.status_code)

    def get_api_version(self):
        """GET /integration/ping — the API version the server reports (``"2.0.0"``)."""
        response = self._request("GET", "/integration/ping")
        return wire.api_version(response.text)

    def get_treatment_rooms(self):
        """GET /integration/rooms — ``[(name, id, coordinate_system), …]``."""
        response = self._request("GET", "/integration/rooms")
        return wire.parse_rooms(response.text)

    def get_treatment_rooms_full(self):
        """GET /integration/rooms — every field, including the non-unique ``machineName``."""
        response = self._request("GET", "/integration/rooms")
        return wire.parse_rooms_full(response.text)

    def get_treatment_room(self, machine_name):
        """GET /integration/rooms/{machineName} — the envelope; ``data`` is the room GUID."""
        response = self._request("GET", f"/integration/rooms/{machine_name}")
        return wire.parse_treatment_room(response.text)

    def get_patient_surfaces(self, patient_id):
        """GET /integration/patients/{patientId}/surfaces — ``[(id, timestamp), …]``."""
        response = self._request("GET", f"/integration/patients/{patient_id}/surfaces")
        return wire.parse_surfaces(response.text)

    def get_surface(self, surface_id):
        """GET /integration/surfaces/{surfaceId} — the decoded ``.obj`` bytes."""
        response = self._request("GET", f"/integration/surfaces/{surface_id}")
        return wire.decode_surface(response.text)

    def get_map(self, body):
        """POST /integration/GetMap — ``(collision_map, x_ticks, y_ticks)``.

        One request, one map. ``body`` comes ready from
        :func:`maprt_workshop.request.build_map_request`, which returns a low- and a
        high-resolution body; asking for both and letting the high-resolution result supersede
        the low one is application orchestration, so it stays with the caller.
        """
        response = self._request("POST", "/integration/GetMap", body)
        return wire.parse_map_response(response.text)

    def get_beam_delivery_status(self, body):
        """POST /integration/GetBeamDeliveryStatus — ``[(beam_number, is_safe), …]``.

        A negative or unlicensed result surfaces as
        :class:`maprt_workshop.errors.BeamDeliveryStatusError`, not an HTTP error.
        """
        response = self._request("POST", "/integration/GetBeamDeliveryStatus", body)
        return wire.parse_beam_delivery_status(response.text)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# -- workshop convenience -------------------------------------------------------------------

def find_server(start=None):
    """What the running emulator recorded about itself, or ``{}``.

    Reads ``.maprt_emulator/server.json``, found by walking up from ``start`` (the working directory by
    default) — so it works whether a notebook runs from the repository root or from
    ``notebooks/MapRT/``. The file carries the **URL** as well as the token, which is what makes a
    non-default port work: a student whose port 8000 is busy starts the emulator elsewhere, and
    nothing they typed tells the notebook where it went.
    """
    here = Path(start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / SERVER_FILE
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError:
                return {}       # half-written while the server was starting; treat as absent
    return {}


def find_token(start=None):
    """The emulator's current token, or ``None``.

    Resolution order: ``MAPRT_EMULATOR_TOKEN`` in the environment (how Binder and Colab supply it),
    then ``.maprt_emulator/server.json``, then the plain ``.maprt_emulator/token`` beside it.
    """
    from_env = os.environ.get("MAPRT_EMULATOR_TOKEN")
    if from_env:
        return from_env.strip()

    recorded = find_server(start).get("token")
    if recorded:
        return str(recorded).strip()

    here = Path(start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / TOKEN_FILE
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return None


def find_url(start=None):
    """Where the emulator is: ``MAPRT_EMULATOR_URL``, then what the server recorded, then the default."""
    from_env = os.environ.get("MAPRT_EMULATOR_URL")
    if from_env:
        return from_env.strip()
    return find_server(start).get("url") or DEFAULT_URL


class EmulatorNotRunning(RuntimeError):
    """:func:`connect` could not reach an emulator, with a message naming the likely fix."""


def connect(api_url=None, token=None, user_agent=None, check=True):
    """A :class:`MapRTClient` pointed at the running emulator, verified with a ping.

    Resolves the base URL from ``api_url``, then ``MAPRT_EMULATOR_URL``, then whatever the running
    emulator recorded in ``.maprt_emulator/server.json``, then ``http://127.0.0.1:8000``; and the
    token the same way. One call that works unchanged in all three workshop environments — local,
    Binder and Colab — so a student whose session dies can switch without editing a cell.

    ``check=False`` skips the ping, for building a client you intend to break on purpose.
    """
    resolved_url = api_url or find_url()
    token = token or find_token()

    if token is None:
        raise EmulatorNotRunning(
            "No API token found.\n\n"
            "Start the emulator in another terminal:\n"
            "    uv run maprt-emulator\n\n"
            "It writes .maprt_emulator/server.json, which this cell finds by walking up from the "
            "notebook's directory. If you are running from somewhere else entirely, paste in "
            "the MAPRT_EMULATOR_TOKEN line the emulator printed:\n"
            "    import os; os.environ['MAPRT_EMULATOR_TOKEN'] = '...'"
        )

    client = MapRTClient(resolved_url, token, user_agent)
    if check:
        try:
            client.get_api_version()
        except httpx2.HTTPError as exc:
            client.close()
            raise EmulatorNotRunning(
                _unreachable_message(resolved_url, api_url, exc)) from exc
    return client


def _unreachable_message(resolved_url, explicit_url, exc):
    """Say which URL was tried and *where it came from*, which is usually the actual problem."""
    if explicit_url:
        source = "the api_url you passed in"
    elif os.environ.get("MAPRT_EMULATOR_URL"):
        source = "the MAPRT_EMULATOR_URL environment variable"
    elif find_server().get("url"):
        source = (".maprt_emulator/server.json, written by an emulator that has since stopped — so "
                  "this is probably a stale file from an earlier run")
    else:
        source = "the default, because no running emulator was found to ask"

    message = (
        f"Could not reach a MapRT emulator at {resolved_url} ({type(exc).__name__}).\n\n"
        f"That address came from: {source}.\n\n"
        "Is `uv run maprt-emulator` still running in the other terminal? If you started it on a "
        "different port it records that itself, so check you are running this notebook from "
        "inside the repository where .maprt_emulator/server.json can be found."
    )

    proxied = [name for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
               if os.environ.get(name)]
    if proxied and _is_loopback(resolved_url):
        # Very common on a hospital network, and the error it produces ("nodename nor servname
        # provided") looks like DNS rather than a proxy. Nothing proxies 127.0.0.1, but the
        # client does not know that unless NO_PROXY says so.
        message += (
            f"\n\n{' and '.join(proxied)} is set in your environment, and a proxy will try to "
            f"route even a loopback address through itself. Exclude it:\n"
            "    import os; os.environ['NO_PROXY'] = '127.0.0.1,localhost'\n"
            "...then re-run this cell."
        )
    return message


def _is_loopback(url):
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}
