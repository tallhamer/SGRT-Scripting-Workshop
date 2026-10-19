"""The envelope shape, and the two-ways-to-fail error model."""

from maprt_emulator import envelope


class TestOk:
    def test_has_the_five_keys_a_client_reads(self):
        assert set(envelope.ok("x")) == {"data", "errorData", "success", "errorCode",
                                        "errorCodeType"}

    def test_success_true_and_no_error_code(self):
        body = envelope.ok([1, 2])
        assert body["success"] is True
        assert body["data"] == [1, 2]
        assert body["errorCode"] is None
        assert body["errorCodeType"] == "NoErrorCodes"


class TestFail:
    def test_success_false_carries_the_code_and_no_data(self):
        body = envelope.fail(*envelope.INVALID_CLIENT_TOKEN)
        assert body["success"] is False
        assert body["data"] is None
        assert body["errorCode"] == "InvalidClientToken"
        assert body["errorCodeType"] == "AuthErrorCodes"


class TestMapRTFailure:
    def test_defaults_to_http_200_because_that_is_the_api_convention(self):
        # The headline fact about this API: a negative result is a 200. If this default ever
        # becomes 4xx, the emulator has stopped teaching the thing it exists to teach.
        assert envelope.MapRTFailure(envelope.FEATURE_NOT_LICENSED).status_code == 200

    def test_renders_to_an_envelope(self):
        exc = envelope.MapRTFailure(envelope.DUPLICATE_KEY, error_data="two rooms")
        body = exc.envelope()
        assert body["errorCode"] == "DuplicateKey"
        assert body["errorCodeType"] == "TreatmentRoomAdministrationErrorCodes"
        assert body["errorData"] == "two rooms"

    def test_a_4xx_can_be_asked_for_explicitly(self):
        assert envelope.MapRTFailure(envelope.INVALID_CLIENT_TOKEN, status_code=401).status_code == 401


class TestInventedCodesAreDeclared:
    def test_the_codes_this_project_made_up_are_listed(self):
        # So /emulator/state and the notebooks can say which codes are not real. A code added to
        # EMULATED without being listed here would quietly look authoritative — which is why
        # this test is written as an exact list and is *meant* to fail when a code is added.
        assert envelope.INVENTED_CODES == [
            "InternalError", "NoRecordedMap", "PatientNotFound", "SurfaceNotFound",
            "TreatmentRoomNotFound",
        ]

    def test_the_spec_quoted_codes_are_not_in_that_list(self):
        for code, _type in (envelope.INVALID_CLIENT_TOKEN, envelope.FEATURE_NOT_LICENSED,
                            envelope.DUPLICATE_KEY):
            assert code not in envelope.INVENTED_CODES
