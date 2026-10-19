"""``POST /integration/GetMapAndBeamTransitions`` — **unofficial.**

``IClient.GetMapAndBeamTransitions`` is a documented method (spec §4.2.1.4): it returns the same
clearance map as GetMap and additionally assesses whether the machine can move safely *between*
consecutive beams of a plan. Appendix B lists seven REST requests and **this is not one of them**,
so a real appliance may expose it at a different path, in a different shape, or not at all.

Everything about this route is therefore this simulator's invention:

* the path;
* the response format — the map stream exactly as GetMap sends it, then a ``TRANSITIONS`` marker
  line, then the transitions as a JSON envelope;
* how a transition is assessed (see :func:`maprt_emulator.mapgen.transition_verdicts`).

It is here because beam transitions are a real planning concern and worth a workshop
conversation. It is labelled unofficial in the OpenAPI summary, in the ``X-Emulator-Unofficial``
response header and in the notebook, because **code written against this will not port**. If you
need transitions against a real appliance, use the NuGet client, or ask Vision RT.
"""

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from maprt_emulator import envelope, mapgen
from maprt_emulator.auth import require_token
from maprt_emulator.routes.beams import resolve_clearance_target
from maprt_emulator.routes.getmap import stream_map_body
from maprt_emulator.schemas import GetMapAndBeamTransitionsRequest

logger = logging.getLogger("maprt_emulator.routes.transitions")

router = APIRouter(prefix="/integration", tags=["integration"],
                   dependencies=[Depends(require_token)])

#: Separates the map stream from the transitions envelope. Invented, like the rest of the shape.
TRANSITIONS_MARKER = "TRANSITIONS"


@router.post("/GetMapAndBeamTransitions",
             summary="UNOFFICIAL — a clearance map plus beam-transition safety")
async def get_map_and_beam_transitions(body: GetMapAndBeamTransitionsRequest, request: Request):
    app = request.app
    surface = resolve_clearance_target(request, body, "map")

    # As in GetMap: everything that can fail is settled before the first byte, because a
    # streaming response has already sent its status code.
    text, source = await run_in_threadpool(app.state.map_cache.resolve_text, app, body)
    verdicts = await run_in_threadpool(
        mapgen.transition_verdicts, surface, body, 24, app.state.settings.seed)

    logger.info("GetMapAndBeamTransitions %d transition(s) -> %d safe, map %s",
                len(verdicts), sum(1 for *_u, safe in verdicts if safe), source)

    tail = envelope.ok({
        "statuses": [
            {"initialBeamNumber": initial, "finalBeamNumber": final, "isSafe": safe}
            for initial, final, safe in verdicts
        ],
    })

    async def body_stream():
        async for chunk in stream_map_body(text, app.state.settings, app.state.scenarios):
            yield chunk
        yield f"{TRANSITIONS_MARKER}\n"
        yield json.dumps(tail)

    return StreamingResponse(
        body_stream(),
        media_type="text/plain",
        headers={
            "X-Emulator-Map-Source": source,
            # Loudly, in the response itself: nothing about this route is specified.
            "X-Emulator-Unofficial": "GetMapAndBeamTransitions has no documented REST route; this "
                                "path and response shape are the simulator's invention",
        },
    )
