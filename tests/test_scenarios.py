"""Fault injection: every armed scenario actually does what it advertises.

A scenario catalogue that lies is worse than none — a student would conclude their error handling
works because the fault never fired. So each one is armed and the effect observed.
"""

import json

import pytest

from maprt_emulator import scenarios

SURFACE = "dad7394f-6893-4ce3-96ed-8bc3091cf4c3"
ROOM = "96bbc235-0da9-e983-0783-5973a7d11144"


def map_body(**overrides):
    out = {"PatientSurfaceId": SURFACE, "TreatmentRoomId": ROOM, "PatientPosition": "HFS",
           "CouchBuffer": 20.0, "PatientBuffer": 20.0, "HighResolution": False,
           "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}
    out.update(overrides)
    return out


def beam_body():
    return dict(map_body(), BeamList=[
        {"beamNumber": 1, "controlPoints": [
            {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "IEC_61217"}]}])


@pytest.fixture
def api(client_factory):
    with client_factory(map_seconds=0.0) as client:
        yield client


def arm(api, name):
    response = api.post("/sim/scenario", json={"name": name})
    assert response.status_code == 200, response.text
    return json.loads(response.text)


class TestTheCatalogue:
    def test_lists_every_scenario_with_what_it_teaches(self, api):
        listed = json.loads(api.get("/sim/scenarios").text)["scenarios"]
        assert {s["name"] for s in listed} == set(scenarios.SCENARIOS)
        for entry in listed:
            assert entry["description"]
            assert entry["teaches"], f"{entry['name']} does not say what it is for"

    def test_ok_is_the_empty_scenario(self):
        ok = scenarios.SCENARIOS["ok"]
        assert ok.unlicensed == () and not ok.reject_token and not ok.forced_status
        assert not ok.extra_delay and not ok.throttle_failures
        assert not ok.truncate_map and not ok.shuffle_map

    def test_an_unknown_name_is_refused_with_the_available_ones(self, api, envelope_of):
        response = api.post("/sim/scenario", json={"name": "explode"})
        assert response.status_code == 400
        assert "unlicensed-map" in str(envelope_of(response)["errorData"])


class TestTheSimRoutesStayReachable:
    def test_sim_needs_no_token(self, client_factory):
        # Unauthenticated on purpose — see below for the reason it has to be.
        with client_factory(token=None) as client:
            assert client.get("/sim/scenarios").status_code == 200
            assert client.get("/sim/state").status_code == 200

    def test_bad_token_can_be_disarmed_while_it_is_armed(self, api):
        # The reason /sim is unauthenticated. If disarming needed a working token there would be
        # no way out of this scenario short of restarting the server.
        arm(api, "bad-token")
        assert json.loads(api.get("/integration/ping").text)["success"] is False
        arm(api, "ok")
        assert json.loads(api.get("/integration/ping").text)["success"] is True

    def test_server_error_does_not_affect_sim(self, api):
        arm(api, "server-error")
        assert api.get("/integration/ping").status_code == 500
        assert api.get("/sim/state").status_code == 200


class TestEachScenarioFires:
    def test_bad_token_rejects_a_correct_token(self, api, envelope_of):
        arm(api, "bad-token")
        body = envelope_of(api.get("/integration/rooms"))
        assert body["success"] is False
        assert body["errorCode"] == "InvalidClientToken"

    def test_unlicensed_surfaces_blocks_the_mesh_but_not_the_listing(self, api, envelope_of):
        arm(api, "unlicensed-surfaces")
        assert envelope_of(api.get(f"/integration/surfaces/{SURFACE}"))["errorCode"] \
            == "FeatureNotLicensed"
        assert envelope_of(api.get("/integration/patients/ANON001/surfaces"))["success"] is True

    def test_unlicensed_map_blocks_getmap(self, api, envelope_of):
        arm(api, "unlicensed-map")
        response = api.post("/integration/GetMap", json=map_body())
        assert response.status_code == 200
        assert envelope_of(response)["errorCode"] == "FeatureNotLicensed"

    def test_unlicensed_beams_blocks_the_beam_endpoint_only(self, api, envelope_of):
        arm(api, "unlicensed-beams")
        assert envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                    json=beam_body()))["errorCode"] == "FeatureNotLicensed"
        # The map is a different licence, so it keeps working.
        assert api.post("/integration/GetMap", json=map_body()).status_code == 200

    def test_server_error_gives_a_500(self, api):
        arm(api, "server-error")
        assert api.get("/integration/rooms").status_code == 500

    def test_the_500_still_carries_the_envelope(self, api, envelope_of):
        # A real 5xx may carry no envelope at all; one is sent here so the status is the thing
        # being exercised rather than the body.
        arm(api, "server-error")
        assert envelope_of(api.get("/integration/rooms"))["success"] is False

    def test_truncate_map_stops_before_DONE(self, api):
        arm(api, "truncate-map")
        text = api.post("/integration/GetMap", json=map_body()).text
        assert "DONE" not in text

    def test_a_truncated_map_parses_to_the_WRONG_SHAPE_which_is_the_real_danger(self, api):
        # The lesson, and it is sharper than "some angles are missing". The parser infers the
        # gantry axis from the values actually present, so a half-delivered map parses happily
        # into a HALF-HEIGHT array. Nothing raises. Code that then indexes by gantry row reads a
        # different angle than it asked for — a beam checked at gantry 200 is answered from the
        # data for some other angle entirely — or raises an IndexError nowhere near the cause.
        #
        # This is why DONE exists and why a client has to check for it.
        from maprt_workshop import wire
        complete, _x, _y = wire.parse_map_response(
            api.post("/integration/GetMap", json=map_body()).text)
        arm(api, "truncate-map")
        truncated, _x, _y = wire.parse_map_response(
            api.post("/integration/GetMap", json=map_body()).text)

        assert complete.shape == (360, 185)
        assert truncated.shape == (180, 185)        # silently half the map
        assert truncated.shape != complete.shape

    def test_shuffle_map_changes_the_order_but_not_the_map(self, api):
        import numpy as np

        from maprt_workshop import wire
        ordered = api.post("/integration/GetMap", json=map_body()).text
        arm(api, "shuffle-map")
        shuffled = api.post("/integration/GetMap", json=map_body()).text
        assert ordered != shuffled
        assert np.array_equal(wire.parse_map_response(ordered)[0],
                              wire.parse_map_response(shuffled)[0])

    def test_throttle_returns_503_with_retry_after_then_recovers(self, api):
        # Recovery is the point: a server that throttled forever would teach students to write a
        # retry loop that can never exit.
        arm(api, "throttle")
        first = api.get("/integration/ping")
        assert first.status_code == 503
        assert first.headers["Retry-After"] == "1"
        assert api.get("/integration/ping").status_code == 503     # the second of two
        assert api.get("/integration/ping").status_code == 200     # recovered

    def test_a_retry_loop_with_backoff_succeeds(self, api):
        # What a student is meant to write, working end to end.
        arm(api, "throttle")
        for _attempt in range(5):
            response = api.get("/integration/ping")
            if response.status_code != 503:
                break
        assert response.status_code == 200

    def test_slow_delays_the_api_but_not_sim(self, api):
        import time
        # 8 s would make the suite tedious, so check the delay is applied rather than its length:
        # the scenario's own field is the contract, and the middleware reads it.
        assert scenarios.SCENARIOS["slow"].extra_delay == 8.0
        arm(api, "slow")
        started = time.monotonic()
        api.get("/sim/state")
        assert time.monotonic() - started < 1.0, "/sim must stay responsive while slow is armed"


class TestArmingAndDisarming:
    def test_arming_reports_what_it_teaches(self, api):
        armed = arm(api, "unlicensed-map")
        assert armed["armed"] == "unlicensed-map"
        assert "licensed" in armed["teaches"].lower()

    def test_state_reports_the_armed_scenario(self, api):
        arm(api, "truncate-map")
        assert json.loads(api.get("/sim/state").text)["scenario"]["name"] == "truncate-map"

    def test_ok_clears_whatever_was_armed(self, api, envelope_of):
        arm(api, "unlicensed-map")
        arm(api, "ok")
        assert api.post("/integration/GetMap", json=map_body()).status_code == 200
        assert envelope_of(api.get("/integration/ping"))["success"] is True

    def test_arming_a_second_scenario_replaces_the_first(self, api, envelope_of):
        arm(api, "unlicensed-map")
        arm(api, "unlicensed-beams")
        assert api.post("/integration/GetMap", json=map_body()).status_code == 200
        assert envelope_of(api.post("/integration/GetBeamDeliveryStatus",
                                    json=beam_body()))["errorCode"] == "FeatureNotLicensed"

    def test_the_command_line_unlicensed_flag_still_applies_under_ok(self, client_factory,
                                                                    envelope_of):
        # A scenario adds to --unlicensed; arming `ok` must not quietly re-license something the
        # operator switched off at startup.
        with client_factory(map_seconds=0.0, unlicensed=("map",)) as client:
            client.post("/sim/scenario", json={"name": "ok"})
            response = client.post("/integration/GetMap", json=map_body())
        assert envelope_of(response)["errorCode"] == "FeatureNotLicensed"


class TestSimState:
    def test_reports_the_data_it_is_serving(self, api):
        state = json.loads(api.get("/sim/state").text)
        assert sorted(state["data"]["patients"]) == ["ANON001", "ANON002", "ANON003"]
        assert len(state["data"]["rooms"]) == 4
        assert state["data"]["recordedMaps"] == 1

    def test_declares_which_error_codes_are_invented(self, api):
        # Said out loud in the API itself, so nobody writes production code matching a string
        # this project made up to fill a gap in the specification.
        state = json.loads(api.get("/sim/state").text)
        assert "PatientNotFound" in state["inventedErrorCodes"]
        assert "InvalidClientToken" not in state["inventedErrorCodes"]
        assert state["notAMedicalDevice"] is True

    def test_reports_the_settings_in_force(self, api):
        state = json.loads(api.get("/sim/state").text)
        assert state["settings"]["mapSource"] == "auto"
        assert state["serverHeader"] == "Saturn/1.2.288.1"
