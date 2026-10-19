"""``/emulator/*`` — the simulator's own control surface. **No counterpart on a real appliance.**

Namespaced away from ``/integration`` so there is no chance of mistaking one for the other: if a
path starts with ``/emulator``, nothing you learn from it transfers.

These routes are **unauthenticated**, on purpose. The ``bad-token`` scenario makes the appliance
reject every token, so if disarming it required a valid token you would have to restart the
server to get out — and a control surface you can lock yourself out of is one nobody will risk
using.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from maprt_emulator import envelope, scenarios
from maprt_emulator.settings import API_VERSION, SERVER_VERSION

router = APIRouter(prefix="/emulator", tags=["emulator"])


class ArmScenario(BaseModel):
    name: str = Field(..., description="a name from GET /emulator/scenarios")


@router.get("/scenarios", summary="SIMULATOR ONLY — the faults you can arm")
async def list_scenarios():
    return {"scenarios": scenarios.catalogue()}


@router.post("/scenario", summary="SIMULATOR ONLY — arm a fault")
async def arm_scenario(body: ArmScenario, request: Request):
    try:
        scenario = request.app.state.scenarios.arm(body.name)
    except KeyError:
        raise envelope.MapRTFailure(
            ("UnknownScenario", envelope.SIMULATED),
            status_code=400,
            error_data=f"No scenario {body.name!r}. Available: {sorted(scenarios.SCENARIOS)}",
        ) from None
    return {"armed": scenario.name, "description": scenario.description,
            "teaches": scenario.teaches}


@router.get("/state", summary="SIMULATOR ONLY — what this server is serving and doing")
async def state(request: Request):
    app = request.app
    settings = app.state.settings
    catalog = app.state.catalog
    return {
        "apiVersion": API_VERSION,
        "serverHeader": SERVER_VERSION,
        "scenario": app.state.scenarios.describe(),
        "data": {
            "directory": str(settings.data_dir),
            "patients": sorted(catalog.known_patients),
            "surfaces": [s.id for s in catalog.surfaces],
            "rooms": catalog.rooms_json(),
            "recordedMaps": len(app.state.maps),
        },
        "settings": {
            "mapSource": settings.map_source,
            "mapSeconds": settings.map_seconds,
            "seed": settings.seed,
            "latencyMs": settings.latency_ms,
            "unlicensed": list(settings.unlicensed),
            "auth401": settings.auth_401,
            "strictUserAgent": settings.strict_user_agent,
            "openPing": settings.open_ping,
            "shuffleMap": settings.shuffle_map,
        },
        # Said out loud, in the API itself: these error codes are not real. The REST
        # specification documents codes only for auth, licensing and room administration, so
        # anything here was made up to fill a gap — do not match on it in production code.
        "inventedErrorCodes": envelope.INVENTED_CODES,
        "notAMedicalDevice": True,
    }
