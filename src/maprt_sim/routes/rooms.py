"""Treatment-room endpoints — spec §5.2.5 and §5.2.4.

Two ways to ask about rooms, and the difference between them is a lesson:

* ``GET /integration/rooms`` lists every room configuration, each with a GUID **and** a machine
  name.
* ``GET /integration/rooms/{machineName}`` resolves *one* room by its machine name.

The second one looks more convenient and is the one to be careful with. A machine name is not
unique — a site commonly has several room configurations on one machine — so the lookup can
match nothing (an all-zeros GUID, **not** an error) or match several (a ``DuplicateKey`` error at
HTTP 200). Production code lists the rooms once and keys on the GUID thereafter, which is what
GetMap and GetBeamDeliveryStatus want anyway.
"""

from fastapi import APIRouter, Depends, Request

from maprt_sim import envelope
from maprt_sim.auth import require_token
from maprt_sim.store import EMPTY_GUID

router = APIRouter(prefix="/integration", tags=["integration"],
                   dependencies=[Depends(require_token)])


@router.get("/rooms", summary="List every treatment room configuration")
async def all_rooms(request: Request):
    return envelope.ok(request.app.state.catalog.rooms_json())


@router.get("/rooms/{machine_name}", summary="Resolve one treatment room by machine name")
async def single_room(machine_name: str, request: Request):
    # Spec §5.2.4 caps machine names at 16 characters. Over-long is a malformed request (4xx),
    # not a negative result — the appliance was never asked a question it could answer.
    if len(machine_name) > 16:
        raise envelope.MapRTFailure(
            ("InvalidArgument", envelope.SIMULATED),
            status_code=400,
            error_data=f"machineName is limited to 16 characters; got {len(machine_name)}.",
        )

    matches = request.app.state.catalog.rooms_by_machine_name(machine_name)

    if len(matches) > 1:
        # More than one match is the AmbiguousMatchException of the C# client (§4.2.1.5), which
        # over REST is the DuplicateKey error of §5.3 — at HTTP 200, like every negative result.
        raise envelope.MapRTFailure(
            envelope.DUPLICATE_KEY,
            error_data=f"{len(matches)} rooms share the machine name {machine_name!r}.",
        )

    if not matches:
        # No match is NOT an error: success, with the all-zeros GUID as the answer. A client that
        # only checks `success` will carry this straight into a GetMap call and get nowhere.
        return envelope.ok(EMPTY_GUID)

    return envelope.ok(matches[0].id)
