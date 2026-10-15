"""``POST /integration/GetBeamDeliveryStatus`` — spec §5.2.7, ``IClient.GetBeamDeliveryStatus``.

"Assesses if the beams specified in the request can be safely delivered" (§4.2.1.2), by checking
"clearance for individual control points" — and it is "usually much faster than the computation
of the full clearance map" (§2.3.2) because it looks at a handful of angles instead of tens of
thousands.

That speed has a price a client has to understand: **the server only checks what you send it.**
A beam carrying two control points is two angles checked, not the arc between them. Send a
360-degree arc as its start and stop and you will be told it is safe while it sweeps straight
through a collision. Nothing is wrong with the endpoint — that is what it does — but it is the
difference between this and a client-side sweep over a full clearance map, and it is the kind of
difference that matters.

Separately licensed (§2.3.3), so ``FeatureNotLicensed`` is a normal case to handle.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from maprt_sim import envelope, mapgen
from maprt_sim.auth import require_token
from maprt_sim.schemas import GetBeamDeliveryStatusRequest

logger = logging.getLogger("maprt_sim.routes.beams")

router = APIRouter(prefix="/integration", tags=["integration"],
                   dependencies=[Depends(require_token)])


def resolve_clearance_target(request, body, feature):
    """The surface model for a clearance request, or raise the right MapRT failure.

    Shared by this endpoint and the transitions one: both need the licence check, the surface and
    the room validated in the same way and with the same error codes.
    """
    app = request.app

    if not app.state.scenarios.is_licensed(feature):
        raise envelope.MapRTFailure(
            envelope.FEATURE_NOT_LICENSED,
            error_data=f"The {feature} feature is not licensed on this server.",
        )

    if app.state.catalog.surface(body.patient_surface_id) is None:
        raise envelope.MapRTFailure(
            envelope.SURFACE_NOT_FOUND,
            error_data=f"No surface {body.patient_surface_id!r} in this server's database.",
        )

    if app.state.catalog.room_by_id(body.treatment_room_id) is None:
        raise envelope.MapRTFailure(
            envelope.ROOM_NOT_FOUND,
            error_data=f"No treatment room {body.treatment_room_id!r} in this server's "
                       f"configuration. List /integration/rooms and use a room's id, not its "
                       f"machineName.",
        )

    return app.state.map_cache.surface_model(body.patient_surface_id)


@router.post("/GetBeamDeliveryStatus", summary="Assess whether each beam can be safely delivered")
async def get_beam_delivery_status(body: GetBeamDeliveryStatusRequest, request: Request):
    surface = resolve_clearance_target(request, body, "beams")
    seed = request.app.state.settings.seed

    # The verdicts come from mapgen.is_safe_at, the same function GetMap evaluates over its grid.
    # So a client that downloads the map and checks the same angles itself gets the same answers,
    # which is a property worth being able to rely on rather than a happy accident.
    verdicts = await run_in_threadpool(mapgen.beam_verdicts, surface, body, seed)

    logger.info("GetBeamDeliveryStatus %d beam(s) -> %d safe",
                len(verdicts), sum(1 for _n, safe in verdicts if safe))

    return envelope.ok({
        "statuses": [{"beamNumber": number, "isSafe": safe} for number, safe in verdicts],
    })
