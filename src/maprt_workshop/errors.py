"""The typed error a MapRT API call raises, and how it is classified.

Ported from the live-verified ``maprt_client.wire`` in the surface_tools project. The
classification is the part worth learning: the MapRT API reports failure two different ways
(see :mod:`maprt_workshop.wire`), and a client that treats them as one thing will either
swallow real errors or show a licensing message as a network outage.
"""


class MapRTApiError(Exception):
    """A MapRT API call that reported failure.

    Per spec §5.3 errors reach the client two ways: an HTTP 200 whose JSON envelope has
    ``success: false`` with an ``errorCode``/``errorCodeType``, and an HTTP 4xx/5xx status.
    `category` classifies the failure so an application can message each kind rather than
    surfacing a raw code:

    - ``auth`` — bad/expired token (``AuthErrorCodes``, e.g. ``InvalidClientToken``)
    - ``license`` — unlicensed feature (``LicenseErrorCodes``, e.g. ``FeatureNotLicensed``)
    - ``server`` — internal server error (HTTP 5xx)
    - ``client`` — rejected/malformed request (HTTP 4xx, or any other reported ``errorCode``)
    """

    _CATEGORY_BY_TYPE = {
        "AuthErrorCodes": "auth",
        "LicenseErrorCodes": "license",
    }

    def __init__(self, error_code, error_code_type, http_status=None):
        self.error_code = error_code
        self.error_code_type = error_code_type
        self.http_status = http_status
        message = f"{error_code_type}: {error_code}"
        if http_status is not None:
            message += f" (HTTP {http_status})"
        super().__init__(message)

    @property
    def category(self):
        by_type = self._CATEGORY_BY_TYPE.get(self.error_code_type)
        if by_type is not None:
            return by_type
        if self.http_status is not None:
            if self.http_status >= 500:
                return "server"
            if self.http_status >= 400:
                return "client"
        return "client"


class BeamDeliveryStatusError(MapRTApiError):
    """A GetBeamDeliveryStatus response reporting a negative result (``success: false``).

    A subclass of :class:`MapRTApiError` so general error routing still matches it, while
    letting an application tell "the server withheld a beam verdict" (typically
    ``FeatureNotLicensed``) apart from a failure of any other endpoint.
    """
