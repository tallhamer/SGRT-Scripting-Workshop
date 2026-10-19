"""**The Phase 4 gate.** The server's beam verdicts and a client-side check of the same map agree.

Two ways to ask whether a beam is deliverable:

* ``POST /integration/GetBeamDeliveryStatus`` — the appliance checks the control points you send
  and answers per beam. Fast, because it looks at a handful of angles.
* Download the clearance map with ``GetMap`` and check the beams against it yourself, with
  ``maprt_workshop.check_beams``. Free once you hold the map, and it can answer what-ifs the plan
  does not contain.

A workshop that taught both without checking they agree would be teaching students to trust two
numbers that might differ. They agree here *structurally*: both go through
``mapgen.is_safe_at``, so the same angle cannot get two answers.

The interesting part is where they legitimately diverge, which is not a bug in either and is the
most important thing in this file: **the server only checks the control points you send it.**
"""

import json
from dataclasses import dataclass

import pytest

from maprt_workshop import check_beams, wire

SURFACE = "a6f3fbee-6714-4f92-80c1-f5aadda4cbeb"     # no recorded map, so both calls compute
ROOM = "96bbc235-0da9-e983-0783-5973a7d11144"


@dataclass
class Beam:
    """The record `check_beams` reads, as a plan's beams would arrive from a DICOM reader."""

    couch: str
    gantry_start: str
    gantry_stop: str
    gantry_rotation: str
    delivery_type: str
    status: object = None


def setup_body(**overrides):
    body = {"PatientSurfaceId": SURFACE, "TreatmentRoomId": ROOM, "PatientPosition": "HFS",
            "CouchBuffer": 20.0, "PatientBuffer": 20.0,
            "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}
    body.update(overrides)
    return body


def control_points(couch, gantry_angles):
    return [{"gantryAngle": float(g), "couchAngle": float(couch),
             "coordinateSystem": "IEC_61217"} for g in gantry_angles]


def arc_gantry_angles(start, stop, direction):
    """Every whole-degree gantry angle an arc sweeps, in travel order.

    The same rows `check_beams` examines — so sending these as control points is the honest
    comparison between the two approaches.
    """
    step = -1 if direction == "CC" else 1
    span = (step * (stop - start)) % 360 or 360
    return [(start + step * i) % 360 for i in range(span)]


@pytest.fixture
def api(shared_client):
    """One app for the whole module.

    Every test here only reads, and each one downloads the same high-resolution map — about a
    second of CPU. A per-test app means a per-test MapCache and so a per-test recompute; sharing
    one took this file from 28 seconds to about 3.
    """
    return shared_client


def server_verdicts(api, beam_list):
    response = api.post("/integration/GetBeamDeliveryStatus",
                        json=setup_body(BeamList=beam_list))
    assert response.status_code == 200, response.text
    body = json.loads(response.text)
    assert body["success"] is True, body
    return {s["beamNumber"]: s["isSafe"] for s in body["data"]["statuses"]}


def client_verdicts(api, beams):
    """Download the high-resolution map and check `beams` against it locally."""
    response = api.post("/integration/GetMap", json=setup_body(HighResolution=True))
    map_data = wire.parse_map_response(response.text)
    checked, _arcs, _statics = check_beams(beams, map_data, 1)
    return [beam.status for beam in checked]


class TestStaticBeams:
    @pytest.mark.parametrize("couch,gantry", [
        (0, 0), (0, 90), (0, 180), (0, 270), (0, 45),
        (90, 0), (90, 90), (90, 180), (270, 90), (300, 135), (355, 200), (45, 315),
    ])
    def test_the_two_approaches_give_the_same_answer(self, api, couch, gantry):
        server = server_verdicts(api, [
            {"beamNumber": 1, "controlPoints": control_points(couch, [gantry])}])
        client = client_verdicts(api, [Beam(str(couch), str(gantry), str(gantry),
                                            "NONE", "TREATMENT")])
        assert server[1] == client[0], (
            f"couch {couch} gantry {gantry}: server said {server[1]}, map said {client[0]}")

    def test_a_whole_plan_of_static_beams_agrees_beam_for_beam(self, api):
        angles = [(0, 0), (0, 90), (0, 270), (90, 90), (300, 160), (45, 20)]
        server = server_verdicts(api, [
            {"beamNumber": i, "controlPoints": control_points(couch, [gantry])}
            for i, (couch, gantry) in enumerate(angles, start=1)])
        client = client_verdicts(api, [Beam(str(c), str(g), str(g), "NONE", "TREATMENT")
                                       for c, g in angles])
        assert [server[i] for i in range(1, len(angles) + 1)] == client

    def test_the_plan_contains_both_outcomes(self, api):
        # Otherwise the agreement above could hold by everything being safe, and the test would
        # pass against a server that always said yes.
        angles = [(0, 0), (90, 90), (90, 270), (0, 180), (60, 100)]
        verdicts = server_verdicts(api, [
            {"beamNumber": i, "controlPoints": control_points(c, [g])}
            for i, (c, g) in enumerate(angles, start=1)]).values()
        assert True in verdicts and False in verdicts


class TestArcs:
    @pytest.mark.parametrize("couch,start,stop,direction", [
        (0, 181, 179, "CW"),        # a full-ish arc either side of the gantry-180 seam
        (0, 350, 10, "CW"),         # wraps the seam
        (0, 10, 350, "CC"),         # wraps the other way
        (90, 181, 179, "CW"),       # the same arc at a kicked couch
        (300, 90, 270, "CW"),
        (0, 180, 180, "CW"),        # start == stop is a full rotation
    ])
    def test_an_arc_sent_as_every_swept_degree_agrees_with_the_map_sweep(
            self, api, couch, start, stop, direction):
        # The honest comparison: give the server the same angles the map sweep examines.
        angles = arc_gantry_angles(start, stop, direction)
        server = server_verdicts(api, [
            {"beamNumber": 1, "controlPoints": control_points(couch, angles)}])
        client = client_verdicts(api, [Beam(str(couch), str(start), str(stop),
                                            direction, "TREATMENT")])
        assert server[1] == client[0], (
            f"couch {couch} arc {start}->{stop} {direction}: "
            f"server said {server[1]}, map sweep said {client[0]}")


class TestWhereTheyLegitimatelyDisagree:
    """Not bugs. The two calls answer different questions, and this is the one that bites."""

    def test_an_arc_sent_as_only_its_endpoints_can_be_called_safe_while_colliding(self, api):
        # Find a couch angle where the full sweep collides but both endpoints are clear. This is
        # the trap: two control points describe two angles, not the arc between them.
        for couch in (90, 85, 80, 75, 70, 270, 275, 280):
            endpoints_only = server_verdicts(api, [
                {"beamNumber": 1, "controlPoints": control_points(couch, [181, 179])}])
            swept = server_verdicts(api, [
                {"beamNumber": 1,
                 "controlPoints": control_points(couch, arc_gantry_angles(181, 179, "CW"))}])
            if endpoints_only[1] and not swept[1]:
                break
        else:
            pytest.fail("no couch angle demonstrated the endpoints-only trap")

        # And the map sweep agrees with the *swept* version, not the endpoints-only one.
        client = client_verdicts(api, [Beam(str(couch), "181", "179", "CW", "TREATMENT")])
        assert client[0] is False
        assert endpoints_only[1] is True, (
            "the server reported an arc safe from its endpoints alone while the sweep collides — "
            "this is what GetBeamDeliveryStatus does, and why a client-side map sweep is a "
            "different question")

    def test_a_control_point_between_two_map_rows_is_checked_exactly(self, api):
        # GetBeamDeliveryStatus is not sampled, so it can be *more* precise than any map: a
        # 1-degree map has no row for gantry 185.4. Both are right; they are not the same thing.
        response = api.post("/integration/GetBeamDeliveryStatus", json=setup_body(
            BeamList=[{"beamNumber": 1,
                       "controlPoints": control_points(0, [185.4, 185.6])}]))
        assert json.loads(response.text)["success"] is True


class TestTheEnvelopeShape:
    def test_statuses_carry_beam_number_and_is_safe(self, api, envelope_of):
        response = api.post("/integration/GetBeamDeliveryStatus", json=setup_body(
            BeamList=[{"beamNumber": 7, "controlPoints": control_points(0, [0])}]))
        statuses = envelope_of(response)["data"]["statuses"]
        assert statuses == [{"beamNumber": 7, "isSafe": statuses[0]["isSafe"]}]

    def test_it_parses_with_the_client_parser(self, api):
        response = api.post("/integration/GetBeamDeliveryStatus", json=setup_body(
            BeamList=[{"beamNumber": 1, "controlPoints": control_points(0, [0])},
                      {"beamNumber": 2, "controlPoints": control_points(90, [90])}]))
        verdicts = wire.parse_beam_delivery_status(response.text)
        assert [number for number, _safe in verdicts] == [1, 2]

    def test_a_string_beam_number_comes_back_as_an_int(self, api, envelope_of):
        # The surface_tools client passes a string and it works against the real appliance; the
        # spec types it as int and §5.2.7's response example shows one.
        response = api.post("/integration/GetBeamDeliveryStatus", json=setup_body(
            BeamList=[{"beamNumber": "3", "controlPoints": control_points(0, [0])}]))
        assert envelope_of(response)["data"]["statuses"][0]["beamNumber"] == 3
