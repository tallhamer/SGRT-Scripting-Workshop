"""Patient and surface endpoints — spec §5.2.2 and §5.2.3.

Getting a mesh takes two calls: list the patient's surfaces, then fetch one by its id.

Three things about the payload that catch people out:

* The mesh arrives as a **base64 data URI** in a JSON string, not as a binary body. You split on
  the last comma and decode the tail.
* It is in **NATIVE (couch) coordinates** and carries **no patient-position metadata** (§3.2.1).
  The bytes do not tell you whether this person was head-first or feet-first; you have to know.
* Surface data is **separately licensed** (§2.3.3), so ``FeatureNotLicensed`` is a normal thing
  to handle here, not an exotic failure.

An unknown *patient* and a known patient with *no surfaces* are different answers, and a client
has to treat them differently — see the handler below.
"""

from fastapi import APIRouter, Depends, Request

from maprt_emulator import envelope
from maprt_emulator.auth import require_token

router = APIRouter(prefix="/integration", tags=["integration"],
                   dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/surfaces", summary="List a patient's acquired surfaces")
async def patient_surfaces(patient_id: str, request: Request):
    # Spec §5.2.2: patient ids are DICOM ids, maximum 64 characters.
    if len(patient_id) > 64:
        raise envelope.MapRTFailure(
            ("InvalidArgument", envelope.SIMULATED),
            status_code=400,
            error_data=f"patientId is limited to 64 characters; got {len(patient_id)}.",
        )

    catalog = request.app.state.catalog

    if not catalog.knows_patient(patient_id):
        # An unknown patient is an error (the C# client throws InvalidArgumentException, §4.2.1.8).
        # The code name here is this simulator's invention — the REST spec documents none for
        # this case. Do not match on it in production code; see maprt_emulator.envelope.
        raise envelope.MapRTFailure(
            envelope.PATIENT_NOT_FOUND,
            error_data=f"No patient {patient_id!r} in this server's database.",
        )

    # A known patient with nothing acquired is a SUCCESS carrying an empty list. Distinguishing
    # the two is the whole point of handling them separately: "we have never seen this person"
    # and "this person has no surface yet" lead to different conversations with a planner.
    return envelope.ok([surface.to_json() for surface in catalog.surfaces_for(patient_id)])


@router.get("/surfaces/{surface_id}", summary="Fetch one surface mesh as base64 OBJ")
async def surface(surface_id: str, request: Request):
    # Through the scenario state, not settings, so both --unlicensed surfaces and the
    # `unlicensed-surfaces` scenario reach here. Checking settings directly would arm a fault
    # that never fires.
    if not request.app.state.scenarios.is_licensed("surfaces"):
        raise envelope.MapRTFailure(
            envelope.FEATURE_NOT_LICENSED,
            error_data="Surface retrieval is not licensed on this server.",
        )

    data_uri = request.app.state.catalog.surface_data_uri(surface_id)
    if data_uri is None:
        raise envelope.MapRTFailure(
            envelope.SURFACE_NOT_FOUND,
            error_data=f"No surface {surface_id!r} in this server's database.",
        )

    return envelope.ok(data_uri)
