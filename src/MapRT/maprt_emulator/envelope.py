"""The MapRT JSON response envelope, and the error codes the appliance reports.

Every endpoint but GetMap answers with the same five-key envelope::

    {"data": …, "errorData": null, "success": true, "errorCode": null,
     "errorCodeType": "NoErrorCodes"}

The thing to understand — and the reason this module exists rather than returning bare dicts
from each route — is that the MapRT API fails in **two different ways** (spec §5.3):

* A **malformed or rejected request** gets an HTTP **4xx**. 5xx means the server broke.
* A **negative result** — the request was fine, the answer is no — comes back at HTTP **200**
  with ``success: false`` and an ``errorCode``. Bad token, unlicensed feature, ambiguous room
  name: all of these are 200s.

So ``response.status_code == 200`` does not mean the call succeeded, and
``raise_for_status()`` alone will happily let an auth failure through.
"""

NO_ERROR = "NoErrorCodes"


def ok(data):
    """A successful envelope carrying ``data``."""
    return {
        "data": data,
        "errorData": None,
        "success": True,
        "errorCode": None,
        "errorCodeType": NO_ERROR,
    }


def fail(error_code, error_code_type, error_data=None):
    """A negative-result envelope. Served at HTTP 200 unless a route says otherwise."""
    return {
        "data": None,
        "errorData": error_data,
        "success": False,
        "errorCode": error_code,
        "errorCodeType": error_code_type,
    }


# ---------------------------------------------------------------------------------------------
# Error codes.
#
# The first group is quoted from spec §5.3, which gives these three as its worked examples. The
# second group is INVENTED: the REST specification names no code for "I don't have that patient",
# it only says the C# client throws InvalidArgumentException. Rather than guess at a real code
# name, the emulator uses obviously-descriptive ones and labels them as its own invention here,
# in /emulator/state, and in the notebooks — so nobody writes production code matching on a string
# this project made up. If you have a real appliance response for these cases, replace them.
# ---------------------------------------------------------------------------------------------

AUTH = "AuthErrorCodes"
LICENSE = "LicenseErrorCodes"
ROOM_ADMIN = "TreatmentRoomAdministrationErrorCodes"
#: Not a real MapRT error-code type. See the note above.
EMULATED = "EmulatorErrorCodes"

INVALID_CLIENT_TOKEN = ("InvalidClientToken", AUTH)
FEATURE_NOT_LICENSED = ("FeatureNotLicensed", LICENSE)
DUPLICATE_KEY = ("DuplicateKey", ROOM_ADMIN)
#: Invented — the spec documents no code for an unknown patient id.
PATIENT_NOT_FOUND = ("PatientNotFound", EMULATED)
#: Invented — the spec documents no code for an unknown surface id.
SURFACE_NOT_FOUND = ("SurfaceNotFound", EMULATED)
#: Invented — the spec documents no code for an unknown treatment room id.
ROOM_NOT_FOUND = ("TreatmentRoomNotFound", EMULATED)
#: Invented — stands in for the server-side faults /emulator/scenario can arm.
INTERNAL_ERROR = ("InternalError", EMULATED)
#: Emulator-only: ``--map-source recorded`` is set and nothing matches. Has no analogue on a
#: real appliance, which always computes.
NO_RECORDED_MAP = ("NoRecordedMap", EMULATED)

#: Which of the above this project made up, for /emulator/state to report honestly.
INVENTED_CODES = sorted({PATIENT_NOT_FOUND[0], SURFACE_NOT_FOUND[0], ROOM_NOT_FOUND[0],
                         INTERNAL_ERROR[0], NO_RECORDED_MAP[0]})


class MapRTFailure(Exception):
    """A failure to render as a MapRT envelope.

    Raise it from anywhere in a route or dependency; the handler registered in
    :mod:`maprt_emulator.app` turns it into the envelope at ``status_code``. The default status is
    **200**, because that is how a real appliance reports a negative result — passing a 4xx is
    the deliberate exception, not the norm.
    """

    def __init__(self, code, status_code=200, error_data=None):
        self.error_code, self.error_code_type = code
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"{self.error_code_type}: {self.error_code} (HTTP {status_code})")

    def envelope(self):
        return fail(self.error_code, self.error_code_type, self.error_data)
