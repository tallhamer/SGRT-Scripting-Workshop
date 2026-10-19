"""Pure parsing of MapRT API responses — no network, no application state.

Given the text (and status) of an API response, this turns the response into plain Python and
numpy values. Ported from ``maprt_client.wire`` in the surface_tools project, where these
parsers are the clinically critical part of a live MapRT integration; the collision-map parser
most of all. Keeping them verbatim is deliberate: the simulator in :mod:`maprt_emulator` is written
to satisfy *these* parsers, so a notebook that works against the simulator is exercising the
same code that works against a real appliance.

Two response shapes to know about:

* Every endpoint but GetMap answers with the **JSON envelope** —
  ``{"data": …, "success": true, "errorCode": null, "errorCodeType": "NoErrorCodes"}``.
* **GetMap** answers with streaming plain text: a ``couch_samples,gantry_samples`` header,
  then ``couch,gantry,isOK`` triples, then ``DONE``. Its *error* case still arrives as the
  envelope, which is why :func:`parse_map_response` sniffs for JSON first.
"""

import base64
import json
from http.client import responses

import numpy as np

from maprt_workshop.errors import BeamDeliveryStatusError, MapRTApiError


def raise_for_maprt_error(envelope, error_cls=MapRTApiError):
    """Raise `error_cls` when a MapRT JSON envelope reports a negative result.

    Spec §5.3: a failed computation returns **HTTP 200** with ``success: false`` and an
    ``errorCode``/``errorCodeType``. Applied by every JSON-envelope parser so the actual code is
    surfaced instead of a blind ``data['data']`` failing later with a meaningless ``TypeError``.
    A missing ``success`` key is treated as success (the appliance always sends it on real calls).

    This is the single most important thing to learn about the MapRT API: a 200 status does not
    mean the call succeeded.
    """
    if not envelope.get("success", True):
        raise error_cls(envelope.get("errorCode"), envelope.get("errorCodeType"))


def raise_for_http_status(status_code, text):
    """Raise :class:`MapRTApiError` for an HTTP 4xx/5xx response; a no-op below 400.

    Spec §5.3: a malformed/rejected request returns an HTTP 4xx (and 5xx is an internal server
    error). When the error body is the JSON envelope its ``errorCode``/``errorCodeType`` are
    carried through (so a 4xx that also names a code classifies by it); a non-JSON body (HTML,
    empty) still yields a status-classified error.
    """
    if status_code < 400:
        return
    error_code = error_code_type = None
    try:
        envelope = json.loads(text)
        error_code = envelope.get("errorCode")
        error_code_type = envelope.get("errorCodeType")
    except (ValueError, AttributeError):
        pass  # non-JSON error body — classify by status alone
    raise MapRTApiError(error_code, error_code_type, http_status=status_code)


def ping_status(status_code):
    """The human-readable API status line shown after a ping."""
    return f'HTTP Status Code: {status_code} {responses[status_code]}'


def api_version(text):
    """The API version string a ping reports (``data`` is e.g. ``"2.0.0"``)."""
    data = json.loads(text)
    raise_for_maprt_error(data)
    return data['data']


def parse_rooms(text):
    """Treatment rooms from a Rooms response, as (name, id, coordinate_system) tuples.

    The three fields a planning application actually needs. Note what is *not* here:
    ``machineName``, which is the field a human recognizes but which is **not unique** on a
    real appliance — see :func:`parse_rooms_full`.
    """
    data = json.loads(text)
    raise_for_maprt_error(data)
    return [(room['name'], room['id'], room['coordinateSystem']) for room in data['data']]


def parse_rooms_full(text):
    """Every field the Rooms response carries, as a list of dicts.

    :func:`parse_rooms` drops ``machineName`` because the application it came from does not need
    it. The workshop does: ``machineName`` is what you look a room up by
    (``/integration/rooms/{machineName}``) and it is the field that can match more than one room,
    producing a ``DuplicateKey`` error. This parser keeps all four fields so a notebook can show
    the collision.
    """
    data = json.loads(text)
    raise_for_maprt_error(data)
    return [dict(room) for room in data['data']]


def parse_surfaces(text):
    """Patient surfaces from a Surfaces response, as (id, timestamp) tuples."""
    data = json.loads(text)
    raise_for_maprt_error(data)
    return [(surface['id'], surface['timeStamp']) for surface in data['data']]


def parse_treatment_room(text):
    """The GetSingleTreatmentRoom envelope, after checking it for a reported error.

    Returns the parsed envelope dict unchanged; its ``data`` is the matching room's GUID, or the
    all-zeros GUID ``"00000000-0000-0000-0000-000000000000"`` when no room matches. A name
    matching more than one room is an error, not an empty result — ``DuplicateKey`` at HTTP 200.
    """
    data = json.loads(text)
    raise_for_maprt_error(data)
    return data


def decode_surface(text):
    """The raw surface bytes from a Surface response: the base64 payload, decoded.

    The value is a data URI (``data:application/octet-stream;base64,…``), so the base64 is the
    part after the final comma. The bytes are an ASCII ``.obj`` mesh in **NATIVE (couch)
    coordinates** carrying no patient-position metadata — reorienting it to DICOM is the
    client's job.
    """
    data = json.loads(text)
    raise_for_maprt_error(data)
    base64_data = data['data'].split(',')[-1]
    return base64.b64decode(base64_data)


def parse_beam_delivery_status(text):
    """Beam-delivery verdicts from a GetBeamDeliveryStatus response, as (beam_number, is_safe).

    The response is a normal JSON envelope (unlike GetMap's streaming text): ``data.statuses``
    is a list of ``{"beamNumber": N, "isSafe": bool}``. A negative result comes back as
    ``success: false`` at HTTP 200 (§5.3) — raised as :class:`BeamDeliveryStatusError` so the
    licensed-feature case is distinguishable from an empty result.
    """
    data = json.loads(text)
    raise_for_maprt_error(data, BeamDeliveryStatusError)
    statuses = data['data']['statuses']
    return [(status['beamNumber'], status['isSafe']) for status in statuses]


def parse_collision_map(text):
    """The collision map from a GetMap response, as (array, x_ticks, y_ticks).

    The wire format is a whitespace-separated token stream: the first token is
    `couch_samples,gantry_samples`, the remaining tokens (bar a discarded trailing one) are
    `couch,gantry,isOK` triples. A coarse map is upsampled so the returned array is always
    at one-degree resolution, matching the index space the beam check works in.

    The returned array is (gantry, couch), with rows running gantry 180…359 then 0…179 and
    columns running couch 270…359 then 0…90 — the layout the MapRT collision-map display uses,
    not the order the triples arrive in.

    **A coarse map comes back wider than a high-resolution one.** A 1° map is (360, 181). The
    spec's own coarse example — 37 couch samples, 36 gantry — upsamples to (360, **185**),
    because the couch axis spans 180° *inclusive*: n samples at step s tile the axis when
    (n-1)*s == 180 but fill 181 columns only when n*s == 181, and no integer step above 1
    satisfies both. The overshoot is a trailing repeat of the last sample (couch 90).

    That is harmless where it matters — repeating by s keeps every block starting at a multiple
    of s, so couch angle 270+k still lands at column k for every k that is a multiple of s,
    which is exactly where :func:`maprt_workshop.beams.check_beams` looks. But do not assume the
    two resolutions share a shape, and do not index a coarse map from its right-hand edge.
    """
    lst = text.split()

    # Determine the sampling for the gantry and couch axes
    couch_samples, gantry_samples = lst[0].split(',')
    gantry_step_size = 360 / int(gantry_samples)
    couch_step_size = 180 / (int(couch_samples) - 1)

    # Construct csv string and read into array using numpy
    new_str = ','.join(lst[1:-1])
    a = np.fromstring(new_str, dtype=int, sep=',')
    a = a.reshape((int(len(a) / 3), 3))

    # Grab the couch and gantry position arrays along with the safe flag
    couch, gantry, isOK = a.T

    # Construct a unique set of gantry and couch positions used to construct the 2D image
    unique_couch = np.unique(couch)
    unique_gantry = np.unique(gantry)

    # Order them to match the MapRT collision map display settings
    gantry_idx = np.hstack((unique_gantry[np.where(unique_gantry >= 180)],
                            unique_gantry[np.where(unique_gantry < 180)]
                            )
                           )

    couch_idx = np.hstack((unique_couch[np.where(unique_couch >= 180)],
                           unique_couch[np.where(unique_couch <= 90)]
                           )
                          )

    # Construct mappings from gantry and couch readouts to array index positions
    x_map = dict([(str(couch_idx[i]), i) for i in range(len(couch_idx))])
    y_map = dict([(str(gantry_idx[i]), i) for i in range(len(gantry_idx))])

    # Construct the initial 2D collision map image and assign the values to each pixel
    _collision_map = np.zeros((len(gantry_idx), len(couch_idx)), dtype=int)
    for j in range(len(couch)):
        _collision_map[y_map[str(gantry[j])], x_map[str(couch[j])]] = isOK[j]

    collision_map = None

    # If the gantry and couch are low resolution upsample to get consistent indices
    if not gantry_step_size == 1 or not couch_step_size == 1:
        collision_map = np.repeat(np.repeat(_collision_map,
                                            int(gantry_step_size),
                                            axis=0
                                            ),
                                  int(couch_step_size),
                                  axis=1
                                  )
    else:
        collision_map = _collision_map

    # construct couch index positions for resampled map
    c0 = np.arange(270, 360, 1)
    c1 = np.arange(0, 91, 1)
    couch_values = np.hstack((c0, c1))

    # construct gantry index positions for resampled map
    g0 = np.arange(180, 360, 1)
    g1 = np.arange(0, 180, 1)
    gantry_values = np.hstack((g0, g1))

    # construct the mappings for the tick labels for the couch and gantry axes
    x_labels = [(int(x), str(couch_values[x])) for x in np.arange(0, len(couch_values), 10)]
    x_ticks = [x_labels]

    y_labels = [(int(y), str(gantry_values[y])) for y in np.arange(0, len(gantry_values), 10)]
    y_ticks = [y_labels]

    return collision_map, x_ticks, y_ticks


def parse_map_response(text):
    """Parse a GetMap response, tolerating the error case.

    GetMap is the one endpoint whose *success* body is streaming text (a ``couch,gantry`` header,
    ``couch,gantry,isOK`` triples, then ``DONE``) rather than the JSON envelope. An error still
    arrives as the envelope, so detect a JSON body first and run it through the shared
    ``success`` check (raising :class:`MapRTApiError`); otherwise parse the stream.
    """
    if text.lstrip().startswith("{"):
        raise_for_maprt_error(json.loads(text))
        # A JSON body with success:true is not a valid map; GetMap never sends that, so fall
        # through to parse_collision_map, which will fail loudly if it somehow happens.
    return parse_collision_map(text)
