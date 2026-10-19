"""GetBeamDeliveryStatus and the unofficial GetMapAndBeamTransitions: bodies, errors, edges.

The agreement with a client-side map check lives in `test_beam_agreement.py`.
"""

import json

import pytest

SURFACE = "a6f3fbee-6714-4f92-80c1-f5aadda4cbeb"
ROOM = "96bbc235-0da9-e983-0783-5973a7d11144"


def body(beam_list=None, **overrides):
    out = {"PatientSurfaceId": SURFACE, "TreatmentRoomId": ROOM, "PatientPosition": "HFS",
           "CouchBuffer": 20.0, "PatientBuffer": 20.0,
           "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0},
           "BeamList": beam_list if beam_list is not None else [
               {"beamNumber": 1,
                "controlPoints": [{"gantryAngle": 0, "couchAngle": 0,
                                   "coordinateSystem": "IEC_61217"}]}]}
    out.update(overrides)
    return out


@pytest.fixture
def api(shared_client):
    """One app for the module — these tests only read. The cases that need different settings
    (unlicensed features) build their own client from `client_factory` instead."""
    return shared_client


class TestTheSpecExample:
    def test_the_body_from_section_5_2_7_is_accepted_verbatim(self, api, envelope_of):
        # Lifted from the specification, numeric PatientPosition and all.
        spec_body = {
            "PatientPosition": 1, "CouchBuffer": 20, "PatientBuffer": 20,
            "PatientSurfaceId": SURFACE, "TreatmentRoomId": ROOM,
            "Isocenter": {"x": "38.8129272460938", "y": "-142.63232421875",
                          "z": "153.504974365234"},
            "BeamList": [
                {"beamNumber": 1, "controlPoints": [
                    {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]},
                {"beamNumber": 2, "controlPoints": [
                    {"gantryAngle": 1, "couchAngle": 0, "coordinateSystem": "IEC_61217"},
                    {"gantryAngle": 2, "couchAngle": 0, "coordinateSystem": "IEC_61217"},
                    {"gantryAngle": 3, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]},
            ],
        }
        statuses = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                        json=spec_body))["data"]["statuses"]
        assert [s["beamNumber"] for s in statuses] == [1, 2]


class TestVerdictLogic:
    def test_a_beam_is_unsafe_if_any_control_point_collides(self, api, envelope_of):
        # One bad angle among good ones condemns the beam — "checks clearance for individual
        # control points" means all of them have to pass.
        clear = {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "IEC_61217"}
        blocked = {"gantryAngle": 90, "couchAngle": 90, "coordinateSystem": "IEC_61217"}
        only_clear = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                          json=body([{"beamNumber": 1,
                                                      "controlPoints": [clear, clear]}])))
        mixed = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                     json=body([{"beamNumber": 1,
                                                 "controlPoints": [clear, blocked, clear]}])))
        assert only_clear["data"]["statuses"][0]["isSafe"] is True
        assert mixed["data"]["statuses"][0]["isSafe"] is False

    def test_a_beam_with_no_control_points_is_not_safe(self, api, envelope_of):
        # No evidence of safety is not evidence of safety. Reporting True for an empty beam
        # would be the most dangerous available default.
        statuses = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                        json=body([{"beamNumber": 1,
                                                    "controlPoints": []}])))["data"]["statuses"]
        assert statuses[0]["isSafe"] is False

    def test_an_empty_beam_list_gives_an_empty_statuses_list(self, api, envelope_of):
        # A success carrying nothing, not an error: you asked about no beams.
        result = envelope_of(api.post("/integration/GetBeamDeliveryStatus", json=body([])))
        assert result["success"] is True
        assert result["data"]["statuses"] == []

    def test_every_beam_gets_exactly_one_status(self, api, envelope_of):
        beams = [{"beamNumber": n, "controlPoints": [
            {"gantryAngle": n * 30, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]}
            for n in range(1, 8)]
        statuses = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                        json=body(beams)))["data"]["statuses"]
        assert [s["beamNumber"] for s in statuses] == list(range(1, 8))


class TestErrors:
    def test_an_unknown_surface_is_an_error_at_http_200(self, api, envelope_of):
        response = api.post("/integration/GetBeamDeliveryStatus",
                            json=body(PatientSurfaceId="nope"))
        assert response.status_code == 200
        assert envelope_of(response)["errorCode"] == "SurfaceNotFound"

    def test_an_unknown_room_is_an_error(self, api, envelope_of):
        response = api.post("/integration/GetBeamDeliveryStatus", json=body(TreatmentRoomId="x"))
        assert envelope_of(response)["errorCode"] == "TreatmentRoomNotFound"

    def test_an_unlicensed_server_withholds_the_verdicts(self, client_factory, envelope_of):
        # Separately licensed (§2.3.3). "I am not licensed to tell you" must be distinguishable
        # from "these beams are unsafe".
        with client_factory(map_seconds=0.0, unlicensed=("beams",)) as client:
            response = client.post("/integration/GetBeamDeliveryStatus", json=body())
        assert envelope_of(response)["errorCode"] == "FeatureNotLicensed"

    def test_the_client_parser_raises_the_beam_specific_error(self, client_factory):
        # maprt_workshop raises BeamDeliveryStatusError here, a subclass, so an application can
        # route the withheld-verdict case separately while generic handling still matches.
        from maprt_workshop.errors import BeamDeliveryStatusError, MapRTApiError
        from maprt_workshop.wire import parse_beam_delivery_status
        with client_factory(map_seconds=0.0, unlicensed=("beams",)) as client:
            text = client.post("/integration/GetBeamDeliveryStatus", json=body()).text
        with pytest.raises(BeamDeliveryStatusError) as exc:
            parse_beam_delivery_status(text)
        assert isinstance(exc.value, MapRTApiError)
        assert exc.value.category == "license"

    def test_a_non_iec_coordinate_system_is_refused_rather_than_guessed(self, api, envelope_of):
        # The API supports six couch coordinate systems; the conversions are vendor-specific and
        # are not implemented here. Treating a Native angle as IEC would give a confident wrong
        # answer about whether a beam is deliverable.
        response = api.post("/integration/GetBeamDeliveryStatus", json=body([
            {"beamNumber": 1, "controlPoints": [
                {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "Native"}]}]))
        assert response.status_code == 400
        assert "IEC_61217" in str(envelope_of(response)["errorData"])

    def test_a_missing_control_point_angle_is_a_400(self, api):
        response = api.post("/integration/GetBeamDeliveryStatus", json=body([
            {"beamNumber": 1, "controlPoints": [{"gantryAngle": 0}]}]))
        assert response.status_code == 400

    def test_there_is_no_high_resolution_flag_to_set(self, api, envelope_of):
        # Spec §4.6.2: GetBeamDeliveryStatus has no HighResolution — nothing is being sampled.
        # An extra key is ignored rather than rejected, as the appliance ignores extras.
        result = envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                      json=body(HighResolution=True)))
        assert result["success"] is True


class TestTheUnofficialTransitionsRoute:
    def test_it_says_it_is_unofficial_in_a_response_header(self, api):
        # Code written against this route will not port: it has no documented REST shape. The
        # header's name carries the label; its value has to carry the reason, so someone reading
        # raw headers learns why rather than just that.
        response = api.post("/integration/GetMapAndBeamTransitions", json=body())
        warning = response.headers["X-Emulator-Unofficial"]
        assert "no documented REST route" in warning
        assert "invention" in warning

    def test_the_body_is_the_map_then_a_marker_then_the_transitions(self, api):
        beams = [{"beamNumber": n, "controlPoints": [
            {"gantryAngle": g, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]}
            for n, g in ((1, 0), (2, 90), (3, 180))]
        text = api.post("/integration/GetMapAndBeamTransitions", json=body(beams)).text
        map_part, _, tail = text.partition("TRANSITIONS\n")
        assert map_part.rstrip().endswith("DONE")
        statuses = json.loads(tail)["data"]["statuses"]
        assert [(s["initialBeamNumber"], s["finalBeamNumber"]) for s in statuses] == [(1, 2), (2, 3)]

    def test_the_map_half_parses_as_a_normal_map(self, api):
        from maprt_workshop import wire
        text = api.post("/integration/GetMapAndBeamTransitions", json=body()).text
        image, _x, _y = wire.parse_map_response(text.partition("TRANSITIONS\n")[0])
        assert image.shape == (360, 185)

    def test_n_beams_give_n_minus_one_transitions(self, api):
        for count in (1, 2, 5):
            beams = [{"beamNumber": n, "controlPoints": [
                {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]}
                for n in range(1, count + 1)]
            text = api.post("/integration/GetMapAndBeamTransitions", json=body(beams)).text
            statuses = json.loads(text.partition("TRANSITIONS\n")[2])["data"]["statuses"]
            assert len(statuses) == max(0, count - 1)

    def test_a_transition_through_a_collision_is_unsafe(self, api):
        # Beam 1 and beam 2 are both anterior and clear, but getting from one to the other the
        # short way round goes through the lateral collision band at a kicked couch.
        beams = [
            {"beamNumber": 1, "controlPoints": [
                {"gantryAngle": 0, "couchAngle": 90, "coordinateSystem": "IEC_61217"}]},
            {"beamNumber": 2, "controlPoints": [
                {"gantryAngle": 180, "couchAngle": 90, "coordinateSystem": "IEC_61217"}]},
        ]
        text = api.post("/integration/GetMapAndBeamTransitions", json=body(beams)).text
        statuses = json.loads(text.partition("TRANSITIONS\n")[2])["data"]["statuses"]
        assert statuses[0]["isSafe"] is False

    def test_it_is_licensed_with_the_map_not_separately(self, client_factory, envelope_of):
        with client_factory(map_seconds=0.0, unlicensed=("map",)) as client:
            response = client.post("/integration/GetMapAndBeamTransitions", json=body())
        assert envelope_of(response)["errorCode"] == "FeatureNotLicensed"
