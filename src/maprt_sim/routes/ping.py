"""``GET /integration/ping`` — spec §5.2.1, ``IClient.GetStatus``.

The cheapest possible call, and the one to reach for first when something is wrong: it proves the
host is reachable, TLS negotiated, and your token is accepted, in one request. ``data`` is the
**API** version as a string (``"2.0.0"``) — not the appliance's software version, which arrives
in the ``Server`` header instead.
"""

from fastapi import APIRouter, Request

from maprt_sim import envelope
from maprt_sim.auth import require_token
from maprt_sim.settings import API_VERSION

router = APIRouter(prefix="/integration", tags=["integration"])


@router.get("/ping", summary="Check the connection and get the API version")
async def ping(request: Request):
    # Auth is applied by hand rather than as a router dependency so --open-ping can waive it.
    # Serving ping unauthenticated is useful when you are trying to work out whether a problem is
    # the network or the token; it is not how the real appliance behaves, which is why it is a
    # flag and not the default.
    if not request.app.state.settings.open_ping:
        await require_token(request)
    return envelope.ok(API_VERSION)
