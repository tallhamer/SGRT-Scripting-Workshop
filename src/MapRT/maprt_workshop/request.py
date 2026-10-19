"""Building the MapRT GetMap and GetBeamDeliveryStatus request bodies — no network, no state.

The mirror of :mod:`maprt_workshop.wire`: that module turns a response into plain values, this
one turns plain values into the request. Ported from ``maprt_client.request`` in the
surface_tools project, where it holds the clinically meaningful half of a map request — the
isocenter shift applied for an interface correction, and the buffers and ids the appliance keys
the collision map on.

Watch the units. The *appliance* wants millimetres for buffers and isocenter; these helpers take
buffers in **centimetres** (what a planner types) and convert. The surface shifts are in
centimetres too, and move the isocenter the opposite way.
"""


def build_map_request(isocenter, couch_buffer, patient_buffer, surface_id, room_id,
                      room_scale, patient_orientation, x_shift=0, y_shift=0, z_shift=0):
    """Return ``(metadata, [low_res_body, high_res_body])`` for a GetMap call.

    ``isocenter`` is the plan isocenter ``(x, y, z)`` in mm. The shifts are the interface
    surface corrections in cm; each is multiplied by -10 to convert to mm and reverse the
    direction (a surface shift moves the isocenter the opposite way), then added to the
    isocenter. The buffers are in cm and go to the appliance in mm.

    ``metadata`` is ``"[x, y, z];couch_mm;patient_mm;surface_id;room_id;room_scale"`` — the
    shifted isocenter rounded to 2 dp, then the values needed to label and locate the returned
    map. A real client tags the request with it so the same string comes back with the response
    and the map can be filed under a stable label. The two bodies differ only in
    ``HighResolution``; the appliance is asked for both, and the high-resolution map supersedes
    the low-resolution one under the same label.

    Note on ``patient_orientation``: spec §5.2.6 says to send the *numeric* ``PatientPosition``
    enum value (1 for HFS). This passes through whatever you give it, and the surface_tools
    application it came from sends the **DICOM string** (``"HFS"``) — which the real appliance
    accepts. :data:`PATIENT_POSITION` maps the strings to the spec's numbers if you want to send
    those instead.
    """
    x, y, z = isocenter

    # cm surface shift -> mm isocenter shift, direction reversed.
    x = x + x_shift * -10
    y = y + y_shift * -10
    z = z + z_shift * -10

    couch_mm = couch_buffer * 10
    patient_mm = patient_buffer * 10

    shifted_isocenter = [round(x, 2), round(y, 2), round(z, 2)]
    metadata = f"{shifted_isocenter};{couch_mm};{patient_mm};{surface_id};{room_id};{room_scale}"

    bodies = [
        {
            "CouchBuffer": couch_mm,
            "PatientBuffer": patient_mm,
            "HighResolution": high_resolution,
            "PatientPosition": patient_orientation,
            "PatientSurfaceId": f"{surface_id}",
            "TreatmentRoomId": f"{room_id}",
            "Isocenter": {
                "x": x,
                "y": y,
                "z": z,
                "CoordinateSystem": "IEC_61217",
            },
        }
        for high_resolution in (False, True)
    ]

    return metadata, bodies


def beam_entry(beam_number, gantry_couch_angles, coordinate_system="IEC_61217"):
    """One ``BeamList`` entry for a beam-delivery-status request.

    ``gantry_couch_angles`` is an iterable of ``(gantry, couch)`` pairs — one pair for a static
    beam, the swept control points for an arc. Keeps the control-point JSON shape in one place.
    """
    return {
        "beamNumber": beam_number,
        "controlPoints": [
            {"gantryAngle": gantry, "couchAngle": couch, "coordinateSystem": coordinate_system}
            for gantry, couch in gantry_couch_angles
        ],
    }


def build_beam_delivery_status_request(isocenter, couch_buffer, patient_buffer, surface_id,
                                       room_id, patient_orientation, beam_list,
                                       x_shift=0, y_shift=0, z_shift=0):
    """Return ``(metadata, body)`` for a GetBeamDeliveryStatus call.

    The setup half — the surface-shift-corrected isocenter, the cm→mm buffers, the ids and
    patient position — is computed exactly as :func:`build_map_request` computes it, so the two
    calls describe the same physical setup. The differences are GetBeamDeliveryStatus's: no
    ``HighResolution`` flag, a single body (not the low/high pair), and a ``BeamList``.
    ``beam_list`` is already-shaped entries (see :func:`beam_entry`).
    """
    x, y, z = isocenter

    # cm surface shift -> mm isocenter shift, direction reversed — identical to build_map_request.
    x = x + x_shift * -10
    y = y + y_shift * -10
    z = z + z_shift * -10

    couch_mm = couch_buffer * 10
    patient_mm = patient_buffer * 10

    shifted_isocenter = [round(x, 2), round(y, 2), round(z, 2)]
    metadata = f"{shifted_isocenter};{couch_mm};{patient_mm};{surface_id};{room_id}"

    body = {
        "CouchBuffer": couch_mm,
        "PatientBuffer": patient_mm,
        "PatientPosition": patient_orientation,
        "PatientSurfaceId": f"{surface_id}",
        "TreatmentRoomId": f"{room_id}",
        "Isocenter": {
            "x": x,
            "y": y,
            "z": z,
            "CoordinateSystem": "IEC_61217",
        },
        "BeamList": list(beam_list),
    }

    return metadata, body


# Spec §4.5.6: the PatientPosition enumeration, DICOM patient-position string to the numeric
# value §5.2.6 says to put in the request body. The surface_tools application sends the string
# and the appliance accepts it; this is here so a notebook can send either and compare.
PATIENT_POSITION = {
    "HFP": 0,
    "HFS": 1,
    "HFDR": 2,
    "HFDL": 3,
    "FFDR": 4,
    "FFDL": 5,
    "FFP": 6,
    "FFS": 7,
}

# Spec §4.3.1: the couch coordinate systems the software supports. A treatment room reports the
# one its Vision RT user interface displays in; IEC_61217 is what DICOM uses and what the
# collision map comes back in.
COORDINATE_SYSTEM = {
    "Native": 0,
    "IEC_61217": 1,
    "IEC_60601_2_1": 2,
    "IEC_60601_NW": 3,
    "OBI_60601_1_5": 4,
    "OBI_60601_1_6": 5,
}
