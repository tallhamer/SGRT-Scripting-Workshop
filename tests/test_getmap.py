"""``POST /integration/GetMap`` as a client meets it: the request body, the stream, the errors.

The format-level guarantees live in `test_map_wire_roundtrip.py`. This is about the endpoint —
what it accepts, what it refuses, when it refuses it, and the header that says whether the map
was recorded or computed.
"""

import json

import pytest

from maprt_workshop import wire

SURFACE = "dad7394f-6893-4ce3-96ed-8bc3091cf4c3"
OTHER_SURFACE = "a6f3fbee-6714-4f92-80c1-f5aadda4cbeb"
ROOM = "96bbc235-0da9-e983-0783-5973a7d11144"

# The setup the shipped recording in data/MapRT/maps/ was made for.
RECORDED = {"PatientSurfaceId": SURFACE, "TreatmentRoomId": ROOM, "PatientPosition": "HFS",
            "CouchBuffer": 20.0, "PatientBuffer": 20.0, "HighResolution": False,
            "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}


def body(**overrides):
    out = dict(RECORDED)
    out.update(overrides)
    return out


@pytest.fixture
def fast_client(client_factory):
    """A client whose server does not pace the stream — the tests do not need the 3s delay."""
    with client_factory(map_seconds=0.0) as c:
        yield c


class TestASuccessfulCall:
    def test_the_body_is_streaming_text_not_the_envelope(self, fast_client):
        response = fast_client.post("/integration/GetMap", json=body())
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert not response.text.lstrip().startswith("{")

    def test_the_response_parses_with_the_client_parser(self, fast_client):
        response = fast_client.post("/integration/GetMap", json=body())
        image, x_ticks, y_ticks = wire.parse_map_response(response.text)
        assert image.shape == (360, 185)      # coarse; see test_map_wire_roundtrip
        assert x_ticks[0][0] == (0, "270")

    def test_high_resolution_gives_the_one_degree_map(self, fast_client):
        response = fast_client.post("/integration/GetMap", json=body(HighResolution=True))
        image, _x, _y = wire.parse_map_response(response.text)
        assert image.shape == (360, 181)

    def test_asking_twice_gives_byte_identical_answers(self, fast_client):
        # Deterministic, so a notebook that re-runs a cell does not appear to get a new map.
        first = fast_client.post("/integration/GetMap", json=body(isocenter_unused=0)).text
        second = fast_client.post("/integration/GetMap", json=body(isocenter_unused=0)).text
        assert first == second


class TestTheMapSourceHeader:
    def test_the_shipped_recording_is_served_for_its_own_setup(self, fast_client):
        response = fast_client.post("/integration/GetMap", json=body())
        assert response.headers["X-Emulator-Map-Source"] == "recorded"

    def test_the_recorded_bytes_are_served_verbatim(self, fast_client, data_dir):
        response = fast_client.post("/integration/GetMap", json=body())
        recorded = (data_dir / "maps" / "demo_hfs_lowres.txt").read_text(encoding="utf-8")
        assert response.text == recorded

    def test_a_different_isocenter_falls_back_to_the_nearest_recording(self, fast_client):
        # Keeps a notebook working when a student types an arbitrary isocenter — but the answer
        # is not for the setup they asked about, so the header has to say so.
        response = fast_client.post("/integration/GetMap",
                                    json=body(Isocenter={"x": 10.0, "y": 0.0, "z": 50.0}))
        assert response.headers["X-Emulator-Map-Source"] == "recorded-nearest"

    def test_a_different_resolution_is_computed_not_nearest_matched(self, fast_client):
        # Resolution is part of what makes a recording applicable: a coarse recording is not a
        # near-enough answer to a high-resolution question.
        response = fast_client.post("/integration/GetMap", json=body(HighResolution=True))
        assert response.headers["X-Emulator-Map-Source"] == "synthetic"

    def test_a_surface_with_no_recording_is_computed(self, fast_client):
        response = fast_client.post("/integration/GetMap",
                                    json=body(PatientSurfaceId=OTHER_SURFACE))
        assert response.headers["X-Emulator-Map-Source"] == "synthetic"

    def test_map_source_synthetic_ignores_the_recordings(self, client_factory):
        with client_factory(map_seconds=0.0, map_source="synthetic") as client:
            response = client.post("/integration/GetMap", json=body())
        assert response.headers["X-Emulator-Map-Source"] == "synthetic"

    def test_map_source_recorded_refuses_to_invent_one(self, client_factory, envelope_of):
        # The point of --map-source recorded is "only ever show real data", so a missing
        # recording has to be loud rather than quietly filled in by the model.
        with client_factory(map_seconds=0.0, map_source="recorded") as client:
            response = client.post("/integration/GetMap",
                                   json=body(PatientSurfaceId=OTHER_SURFACE))
        assert envelope_of(response)["errorCode"] == "NoRecordedMap"

    def test_map_source_recorded_still_serves_a_recording_it_has(self, client_factory):
        with client_factory(map_seconds=0.0, map_source="recorded") as client:
            response = client.post("/integration/GetMap", json=body())
        assert response.headers["X-Emulator-Map-Source"] == "recorded"


class TestTheRequestBody:
    def test_the_numeric_patient_position_from_the_spec_is_accepted(self, fast_client):
        # Spec §5.2.6 asks for the enum value; 1 is HFS.
        response = fast_client.post("/integration/GetMap", json=body(PatientPosition=1))
        assert response.status_code == 200
        assert response.headers["X-Emulator-Map-Source"] == "recorded"   # same setup as "HFS"

    def test_the_dicom_string_the_real_client_sends_is_accepted(self, fast_client):
        response = fast_client.post("/integration/GetMap", json=body(PatientPosition="HFS"))
        assert response.status_code == 200

    def test_string_isocenter_components_are_accepted(self, fast_client):
        # The spec's own example quotes them: "38.8129272460938".
        response = fast_client.post("/integration/GetMap",
                                    json=body(Isocenter={"x": "0", "y": "0", "z": "0"}))
        assert response.status_code == 200

    def test_an_extra_coordinate_system_key_is_tolerated(self, fast_client):
        # What the surface_tools client actually sends, and not in the spec's example.
        response = fast_client.post("/integration/GetMap", json=body(
            Isocenter={"x": 0.0, "y": 0.0, "z": 0.0, "CoordinateSystem": "IEC_61217"}))
        assert response.status_code == 200


class TestMalformedRequests:
    def test_a_bad_patient_position_is_a_400_with_the_envelope(self, fast_client, envelope_of):
        # Spec §5.3 puts a rejected request at 4xx and names 400. FastAPI's own answer would be
        # 422 with {"detail": …}, which a MapRT client's single parser cannot read.
        response = fast_client.post("/integration/GetMap", json=body(PatientPosition="SIDEWAYS"))
        assert response.status_code == 400
        assert envelope_of(response)["errorCode"] == "InvalidArgument"

    def test_the_validation_detail_is_carried_in_error_data(self, fast_client, envelope_of):
        response = fast_client.post("/integration/GetMap", json=body(PatientPosition="SIDEWAYS"))
        detail = envelope_of(response)["errorData"]
        assert any("PatientPosition" in str(item) for item in detail)

    @pytest.mark.parametrize("missing", ["PatientSurfaceId", "TreatmentRoomId", "Isocenter"])
    def test_a_missing_required_field_is_a_400(self, fast_client, missing):
        incomplete = body()
        del incomplete[missing]
        assert fast_client.post("/integration/GetMap", json=incomplete).status_code == 400

    def test_a_negative_buffer_is_refused(self, fast_client, envelope_of):
        # It would shrink the patient and make the map more permissive than reality.
        response = fast_client.post("/integration/GetMap", json=body(PatientBuffer=-10))
        assert response.status_code == 400
        assert envelope_of(response)["errorCode"] == "InvalidArgument"

    def test_an_out_of_range_patient_position_enum_is_refused(self, fast_client):
        assert fast_client.post("/integration/GetMap", json=body(PatientPosition=99)).status_code == 400


class TestNegativeResults:
    def test_an_unknown_surface_is_an_error_at_http_200(self, fast_client, envelope_of):
        response = fast_client.post("/integration/GetMap",
                                    json=body(PatientSurfaceId="not-a-surface"))
        assert response.status_code == 200
        assert envelope_of(response)["errorCode"] == "SurfaceNotFound"

    def test_an_unknown_room_is_an_error(self, fast_client, envelope_of):
        response = fast_client.post("/integration/GetMap", json=body(TreatmentRoomId="not-a-room"))
        assert envelope_of(response)["errorCode"] == "TreatmentRoomNotFound"

    def test_passing_a_machine_name_instead_of_a_room_id_says_so(self, fast_client, envelope_of):
        # The mistake this invites, so the message names the fix.
        response = fast_client.post("/integration/GetMap", json=body(TreatmentRoomId="TrueBeam"))
        assert "machineName" in str(envelope_of(response)["errorData"])

    def test_an_unlicensed_map_is_feature_not_licensed(self, client_factory, envelope_of):
        with client_factory(map_seconds=0.0, unlicensed=("map",)) as client:
            response = client.post("/integration/GetMap", json=body())
        assert response.status_code == 200
        assert envelope_of(response)["errorCode"] == "FeatureNotLicensed"

    def test_errors_are_decided_before_streaming_starts(self, client_factory):
        # Once a response begins streaming its status is already sent and cannot be changed, so
        # every failure has to be settled up front. An error must therefore be a JSON body, never
        # a truncated map.
        with client_factory(map_seconds=0.0, unlicensed=("map",)) as client:
            response = client.post("/integration/GetMap", json=body())
        assert json.loads(response.text)["success"] is False

    def test_a_bad_token_is_refused_before_any_map_work(self, client_factory, envelope_of):
        with client_factory(token="wrong", map_seconds=0.0) as client:
            response = client.post("/integration/GetMap", json=body())
        assert envelope_of(response)["errorCode"] == "InvalidClientToken"


class TestTheStreamedBodyIsWellFormed:
    """What can be checked through the in-process test client.

    It cannot check *chunking*: its ASGI transport buffers the whole response before handing it
    over, so even ``iter_raw`` yields a single chunk no matter what the server does. Whether the
    body genuinely arrives progressively is therefore asserted in
    ``test_server_integration.py``, over a real socket. Asserting it here would have passed for
    the wrong reason or failed for one.
    """

    def test_the_header_line_comes_first(self, fast_client):
        # So a client can read the sampling, and size a progress bar, before the data lands.
        with fast_client.stream("POST", "/integration/GetMap", json=body()) as response:
            first = next(response.iter_lines())
        assert first.strip() == "37,36"

    def test_the_last_line_is_DONE(self, fast_client):
        with fast_client.stream("POST", "/integration/GetMap", json=body()) as response:
            lines = [line for line in response.iter_lines() if line.strip()]
        assert lines[-1].strip() == "DONE"

    def test_the_line_count_is_the_header_plus_the_triples_plus_DONE(self, fast_client):
        with fast_client.stream("POST", "/integration/GetMap",
                                json=body(HighResolution=True)) as response:
            lines = [line for line in response.iter_lines() if line.strip()]
        assert len(lines) == 1 + (181 * 360) + 1


class TestShuffle:
    def test_shuffled_triples_still_parse_to_the_same_map(self, client_factory):
        with client_factory(map_seconds=0.0, map_source="synthetic") as client:
            ordered = client.post("/integration/GetMap", json=body()).text
        with client_factory(map_seconds=0.0, map_source="synthetic", shuffle_map=True) as client:
            shuffled = client.post("/integration/GetMap", json=body()).text
        assert ordered != shuffled
        import numpy as np
        assert np.array_equal(wire.parse_map_response(ordered)[0],
                              wire.parse_map_response(shuffled)[0])
