"""maprt_workshop — the student-facing half of the MapRT scripting workshop.

Response parsing (:mod:`~maprt_workshop.wire`), request building
(:mod:`~maprt_workshop.request`), an HTTP client (:mod:`~maprt_workshop.client`), a numpy OBJ
reader (:mod:`~maprt_workshop.obj`) and client-side beam checking
(:mod:`~maprt_workshop.beams`).

The parsers and request builders are ported from the live-verified ``maprt_client`` package in
the surface_tools project, so what you learn here is what works against a real appliance. The
emulator in :mod:`maprt_emulator` is written to satisfy *these* parsers, not the other way round.

Not a medical device. Teaching use only. Not affiliated with or endorsed by Vision RT.
"""

from maprt_workshop import obj, request, wire
from maprt_workshop.beams import ArcSegment, StaticBeamPlot, check_beams
from maprt_workshop.client import (
    EmulatorNotRunning,
    MapRTClient,
    connect,
    find_server,
    find_token,
    find_url,
)
from maprt_workshop.errors import BeamDeliveryStatusError, MapRTApiError
from maprt_workshop.obj import ObjParseError, parse_obj
from maprt_workshop.request import (
    COORDINATE_SYSTEM,
    PATIENT_POSITION,
    beam_entry,
    build_beam_delivery_status_request,
    build_map_request,
)
from maprt_workshop.wire import raise_for_http_status, raise_for_maprt_error

__all__ = [
    "wire",
    "request",
    "obj",
    "MapRTClient",
    "connect",
    "find_token",
    "find_url",
    "find_server",
    "EmulatorNotRunning",
    "build_map_request",
    "build_beam_delivery_status_request",
    "beam_entry",
    "PATIENT_POSITION",
    "COORDINATE_SYSTEM",
    "MapRTApiError",
    "BeamDeliveryStatusError",
    "raise_for_maprt_error",
    "raise_for_http_status",
    "parse_obj",
    "ObjParseError",
    "check_beams",
    "ArcSegment",
    "StaticBeamPlot",
]
