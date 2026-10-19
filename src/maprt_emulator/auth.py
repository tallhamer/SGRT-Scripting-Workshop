"""Bearer-token auth and the User-Agent requirement, as spec §5.1 describes them.

Three headers go on every MapRT API call::

    Content-Type:  application/json
    Authorization: Bearer <API_access_token>
    User-Agent:    VisionRT.Integration.Saturn/<api version>.<your client>

The token is a **shared secret** issued per appliance — not a login, not a session, nothing to
refresh. It is the whole of the authentication story, which is why a real deployment puts the
appliance behind TLS on a controlled network and treats the token like a password.

How a rejected token is reported is worth reading closely, because the emulator can do it both
ways and real clients have to cope with both:

* **No credential at all** (no ``Authorization`` header, or not a ``Bearer`` one) → HTTP **401**.
  Nothing was presented, so this never reaches the appliance's result logic.
* **A credential that is wrong** → HTTP **200** with ``success: false`` and
  ``InvalidClientToken``, which is what spec §5.3 documents as its auth example. Pass
  ``--auth-401`` to return 401 here too.

The default is the spec's behaviour, and it is the one that catches people out: a client that
trusts the status code reads an auth failure as a success.
"""

from fastapi import Request

from maprt_emulator import envelope
from maprt_emulator.settings import USER_AGENT_PREFIX


def bearer_token(request):
    """The token from the ``Authorization`` header, or ``None`` if none was presented."""
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def check_user_agent(request, settings):
    """Enforce the ``User-Agent`` requirement when ``--strict-user-agent`` is on.

    A real appliance expects ``VisionRT.Integration.Saturn/a.b.x``. The emulator only warns by
    default, because making a beginner's first bare GET fail on a header nobody
    mentioned yet is a bad first lesson — the notebooks turn this on deliberately instead.
    """
    agent = request.headers.get("user-agent", "")
    if agent.startswith(USER_AGENT_PREFIX):
        return
    if settings.strict_user_agent:
        # A malformed request, which §5.3 puts at 4xx — not a negative result at 200.
        raise envelope.MapRTFailure(
            ("InvalidUserAgent", envelope.EMULATED),
            status_code=400,
            error_data=(f"User-Agent must start with {USER_AGENT_PREFIX!r}; "
                        f"got {agent or '(none)'!r}."),
        )


async def require_token(request: Request):
    """FastAPI dependency: authenticate the request, or raise :class:`envelope.MapRTFailure`.

    Also the one place the ``User-Agent`` policy is applied, so it covers every authenticated
    endpoint without each route remembering to ask.
    """
    settings = request.app.state.settings
    check_user_agent(request, settings)

    presented = bearer_token(request)

    if presented is None:
        # Nothing presented. A 401 with the envelope as its body: the status is the HTTP-level
        # answer, and the body keeps the shape a MapRT client already knows how to read.
        raise envelope.MapRTFailure(
            envelope.INVALID_CLIENT_TOKEN,
            status_code=401,
            error_data="No Authorization: Bearer <token> header was sent.",
        )

    rejected = presented != request.app.state.token

    # The `bad-token` scenario refuses a correct token too — what an expired or rotated secret
    # looks like from the client side, which is otherwise impossible to arrange on demand.
    if request.app.state.scenarios.rejects_token:
        rejected = True

    if rejected:
        status = 401 if settings.auth_401 else 200
        raise envelope.MapRTFailure(envelope.INVALID_CLIENT_TOKEN, status_code=status)

    return presented
