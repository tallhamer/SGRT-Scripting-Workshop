"""Authentication: the three headers, and how a rejected token is reported.

The split the emulator implements, and why:

* no credential presented  -> HTTP 401  (nothing reached the appliance's result logic)
* credential presented, wrong -> HTTP 200 + success:false + InvalidClientToken  (spec §5.3)

A client that trusts `raise_for_status()` sails straight through the second one.
"""



class TestValidToken:
    def test_a_good_token_is_accepted(self, client, envelope_of):
        response = client.get("/integration/ping")
        assert response.status_code == 200
        assert envelope_of(response)["success"] is True


class TestWrongToken:
    def test_is_reported_at_http_200_by_default(self, client_factory, envelope_of):
        # The headline lesson. 200 OK, and the call did not succeed.
        with client_factory(token="not-the-token") as client:
            response = client.get("/integration/ping")
        assert response.status_code == 200
        body = envelope_of(response)
        assert body["success"] is False
        assert body["errorCode"] == "InvalidClientToken"
        assert body["errorCodeType"] == "AuthErrorCodes"

    def test_auth_401_switches_to_an_http_status(self, client_factory, envelope_of):
        with client_factory(token="not-the-token", auth_401=True) as client:
            response = client.get("/integration/ping")
        assert response.status_code == 401
        assert envelope_of(response)["errorCode"] == "InvalidClientToken"


class TestMissingCredential:
    def test_no_authorization_header_is_a_401(self, client_factory, envelope_of):
        with client_factory(token=None) as client:
            response = client.get("/integration/ping")
        assert response.status_code == 401
        assert envelope_of(response)["errorCode"] == "InvalidClientToken"

    def test_the_401_body_is_still_the_envelope(self, client_factory, envelope_of):
        # So one parser handles every response, whatever the status.
        with client_factory(token=None) as client:
            body = envelope_of(client.get("/integration/ping"))
        assert body["success"] is False
        assert body["data"] is None

    def test_a_non_bearer_scheme_counts_as_missing(self, client_factory, token):
        with client_factory(token=None) as client:
            response = client.get("/integration/ping",
                                  headers={"Authorization": f"Basic {token}"})
        assert response.status_code == 401

    def test_an_empty_bearer_value_counts_as_missing(self, client_factory):
        with client_factory(token=None) as client:
            response = client.get("/integration/ping", headers={"Authorization": "Bearer   "})
        assert response.status_code == 401


class TestEveryEndpointIsProtected:
    def test_no_endpoint_answers_without_a_token(self, client_factory, envelope_of):
        # A route added without the dependency would otherwise be silently open.
        paths = ["/integration/ping", "/integration/rooms", "/integration/rooms/TrueBeam2",
                 "/integration/patients/ANON001/surfaces",
                 "/integration/surfaces/dad7394f-6893-4ce3-96ed-8bc3091cf4c3"]
        with client_factory(token="wrong") as client:
            for path in paths:
                body = envelope_of(client.get(path))
                assert body["success"] is False, f"{path} answered without a valid token"
                assert body["errorCode"] == "InvalidClientToken", path


class TestUserAgent:
    def test_is_not_enforced_by_default(self, client_factory, envelope_of):
        # Deliberate: a beginner's first bare GET should work, so the requirement can be
        # taught on purpose instead of being an opening roadblock.
        with client_factory(user_agent=None) as client:
            assert envelope_of(client.get("/integration/ping"))["success"] is True

    def test_strict_mode_rejects_a_missing_user_agent_with_a_4xx(self, client_factory, envelope_of):
        # A malformed request, which §5.3 puts at 4xx — not a negative result at 200.
        with client_factory(user_agent=None, strict_user_agent=True) as client:
            response = client.get("/integration/ping")
        assert response.status_code == 400
        assert envelope_of(response)["errorCode"] == "InvalidUserAgent"

    def test_strict_mode_rejects_a_wrong_user_agent(self, client_factory):
        with client_factory(user_agent="curl/8.0", strict_user_agent=True) as client:
            assert client.get("/integration/ping").status_code == 400

    def test_strict_mode_accepts_the_documented_prefix(self, client_factory, envelope_of):
        with client_factory(user_agent="VisionRT.Integration.Saturn/2.0.my-script",
                            strict_user_agent=True) as client:
            assert envelope_of(client.get("/integration/ping"))["success"] is True


class TestOpenPing:
    def test_serves_ping_without_a_token_when_asked(self, client_factory, envelope_of):
        with client_factory(token=None, open_ping=True) as client:
            assert envelope_of(client.get("/integration/ping"))["success"] is True

    def test_but_leaves_the_other_endpoints_protected(self, client_factory):
        with client_factory(token=None, open_ping=True) as client:
            assert client.get("/integration/rooms").status_code == 401
