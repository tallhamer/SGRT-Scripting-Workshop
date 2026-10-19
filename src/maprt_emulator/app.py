"""The FastAPI application: wiring, the ``Server`` header, and envelope error rendering."""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from maprt_emulator import envelope
from maprt_emulator.maps import MapLibrary
from maprt_emulator.routes import beams, getmap, ping, rooms, sim, surfaces, transitions
from maprt_emulator.routes.getmap import MapCache
from maprt_emulator.scenarios import ScenarioState
from maprt_emulator.settings import SERVER_VERSION, EmulatorSettings
from maprt_emulator.store import Catalog

logger = logging.getLogger("maprt_emulator")

DESCRIPTION = """
A **simulator** of the Vision RT MapRT API 2.0, for teaching and practice.

> **Not a medical device. Teaching use only.** Surfaces are synthetic and clearance maps are
> plausible rather than physical. Not affiliated with or endorsed by Vision RT.

Endpoints under `/integration` mirror the documented REST API. Endpoints under `/sim` are this
simulator's own and have no counterpart on a real appliance.

**A real MapRT appliance does not publish an OpenAPI document, so this page does not exist
there.** It is here because it is a useful way to read the API's shape — but you cannot discover
a real appliance's endpoints this way. The specification is the source of truth.

Two things to remember when reading responses:

* Every endpoint but `GetMap` answers with the envelope
  `{"data", "errorData", "success", "errorCode", "errorCodeType"}`.
* **A `200` status does not mean the call succeeded.** A negative result — bad token, unlicensed
  feature, ambiguous room name — comes back at `200` with `success: false`. Only a malformed or
  rejected *request* gets a 4xx.
"""


def create_app(settings=None):
    """Build the application. ``settings`` defaults to one resolved from the environment."""
    settings = settings or EmulatorSettings()

    app = FastAPI(
        title="MapRT API Simulator",
        version="2.0.0",
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "integration", "description": "The documented MapRT REST API."},
            {"name": "sim", "description": "Simulator-only. No counterpart on a real appliance."},
        ],
    )

    app.state.settings = settings
    app.state.token = settings.resolve_token()
    app.state.catalog = Catalog.load(settings.data_dir)
    app.state.maps = MapLibrary.load(settings.data_dir)
    app.state.map_cache = MapCache(app.state.catalog)
    app.state.scenarios = ScenarioState(settings)

    @app.exception_handler(envelope.MapRTFailure)
    async def _render_failure(_request, exc: envelope.MapRTFailure):
        """Render a reported failure as the MapRT envelope at the status the raiser chose.

        Note the status is usually **200**: that is the API's own convention for a negative
        result, not an oversight here.
        """
        return JSONResponse(exc.envelope(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _render_validation_error(_request, exc: RequestValidationError):
        """Render a malformed request body as the MapRT envelope at HTTP 400.

        FastAPI's own answer would be ``422`` with ``{"detail": [...]}``, which is a perfectly
        good REST convention and the wrong one here twice over: the status is not what spec §5.3
        names ("the HTTP status 4xx is returned, e.g. 400 Bad Request"), and the body is not the
        envelope, so a MapRT client that has one parser for every response cannot read it.

        The validation detail is kept, in ``errorData`` — it is genuinely useful when a body is
        wrong, and a real appliance's rejection is far less helpful than this.
        """
        return JSONResponse(
            envelope.fail("InvalidArgument", envelope.SIMULATED,
                          error_data=[_readable(error) for error in exc.errors()]),
            status_code=400,
        )

    @app.middleware("http")
    async def _appliance_behaviour(request, call_next):
        """Latency, armed transport-level faults, and the ``Server`` header.

        The faults are applied only to ``/integration`` paths. ``/sim`` has to keep working while
        a fault is armed, or there would be no way to disarm one.
        """
        scenarios_state = app.state.scenarios
        is_api = request.url.path.startswith("/integration")

        if settings.latency_ms:
            await asyncio.sleep(settings.latency_ms / 1000)

        if is_api and scenarios_state.extra_delay:
            await asyncio.sleep(scenarios_state.extra_delay)

        if is_api and scenarios_state.take_throttle_slot():
            # Spec §2.2.1.3: the server "may have throttling mechanisms implemented and report to
            # the client if it cannot process immediately and the request should be repeated".
            # Retry-After tells a client how long to wait instead of hammering.
            response = JSONResponse(
                envelope.fail("ServerBusy", envelope.SIMULATED,
                              error_data="Throttled. Retry after the interval in Retry-After."),
                status_code=503,
            )
            response.headers["Retry-After"] = "1"
            response.headers["server"] = SERVER_VERSION
            return response

        if is_api and scenarios_state.forced_status:
            # A 5xx has no envelope to read on a real appliance, and a client that assumes it can
            # always parse JSON fails inside its own error handler. One is sent anyway here, so
            # the status is the thing being exercised rather than the body.
            response = JSONResponse(
                envelope.fail(*envelope.INTERNAL_ERROR,
                              error_data="The 'server-error' scenario is armed."),
                status_code=scenarios_state.forced_status,
            )
            response.headers["server"] = SERVER_VERSION
            return response

        response = await call_next(request)
        # Spec §5.1: "The response from MapRT always carries the Server header set to
        # Saturn/version." Worth reproducing — it is how a client can tell what it is talking to,
        # and a notebook reads it to confirm the connection landed where it thinks.
        response.headers["server"] = SERVER_VERSION
        return response

    app.include_router(ping.router)
    app.include_router(rooms.router)
    app.include_router(surfaces.router)
    app.include_router(getmap.router)
    app.include_router(beams.router)
    app.include_router(transitions.router)
    app.include_router(sim.router)

    return app


def _readable(error):
    """One pydantic validation error as a short string, without its internal bookkeeping."""
    location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
    return f"{location or 'body'}: {error.get('msg', 'invalid')}"
