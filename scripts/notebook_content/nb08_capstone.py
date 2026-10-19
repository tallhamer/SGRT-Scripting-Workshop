"""08 — Capstone: plan QA."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("08", "Capstone: plan QA",
                  "An RT Plan in, a pass/fail table out. About sixty lines.", "30 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## The thing you came for

A plan arrives. You want to know, before anyone wheels a patient in, whether every beam in it can
actually be delivered.

By hand that is: open the plan, read the isocenter, note every gantry and couch angle, find the
patient's surface, load the right room, run a map, and check each beam against it. Ten minutes a
plan, and it is the kind of ten minutes nobody does twice.

Scripted, it is one function. Here it is, built in six steps."""),

    ("md", """\
## Step 1 — read the plan

`pydicom` reads an RT Plan. The four things a clearance check needs:

| | DICOM tag | where |
| --- | --- | --- |
| Patient ID | (0010,0020) | top level |
| Patient position | (0018,5100) | `PatientSetupSequence` |
| Isocenter | (300a,012c) | first control point of each beam |
| Gantry & couch angles | (300a,011e), (300a,0122) | `ControlPointSequence` |"""),
    ("code", '''\
import pydicom

PLAN_PATH = "../data/MapRT/plans/ANON001_plan.dcm"

plan = pydicom.dcmread(PLAN_PATH)

print("Plan        :", plan.RTPlanLabel)
print("Patient ID  :", plan.PatientID)
print("Position    :", plan.PatientSetupSequence[0].PatientPosition)
print("Machine     :", plan.BeamSequence[0].TreatmentMachineName)
print("Beams       :", len(plan.BeamSequence))
'''),
    ("md", """\
The isocenter lives on a control point, not at the top level — a plan *can* have different
isocenters per beam, though usually does not."""),
    ("code", '''\
first_control_point = plan.BeamSequence[0].ControlPointSequence[0]
isocenter = [float(value) for value in first_control_point.IsocenterPosition]

print("isocenter (mm, DICOM patient coordinates):", isocenter)
'''),

    ("md", """\
## Step 2 — pull out the beams

A planning system writes the full geometry on **control point 0** and only what *changes* on the
rest. So a reader has to carry values forward rather than expecting every field on every point.

For a collision check, each beam reduces to five things."""),
    ("code", '''\
from dataclasses import dataclass


@dataclass
class Beam:
    number: int
    name: str
    couch: str
    gantry_start: str
    gantry_stop: str
    gantry_rotation: str       # "NONE", "CW" or "CC"
    delivery_type: str         # "TREATMENT" or "SETUP"
    status: object = None      # the verdict lands here


def read_beams(plan):
    beams = []
    for dicom_beam in plan.BeamSequence:
        points = dicom_beam.ControlPointSequence
        beams.append(Beam(
            number=int(dicom_beam.BeamNumber),
            name=str(dicom_beam.BeamName),
            couch=str(points[0].PatientSupportAngle),
            gantry_start=str(points[0].GantryAngle),
            gantry_stop=str(points[-1].GantryAngle),
            gantry_rotation=str(points[0].GantryRotationDirection),
            delivery_type=str(dicom_beam.TreatmentDeliveryType),
        ))
    return beams


beams = read_beams(plan)
for beam in beams:
    span = (beam.gantry_start if beam.gantry_rotation == "NONE"
            else f"{beam.gantry_start}->{beam.gantry_stop} {beam.gantry_rotation}")
    print(f"  {beam.number}  {beam.name:<14} couch {beam.couch:>5}  gantry {span}")
'''),

    ("md", """\
## Step 3 — find the room

By machine name, with all three outcomes handled — notebook 03."""),
    ("code", '''\
from maprt_workshop import MapRTApiError

EMPTY_GUID = "00000000-0000-0000-0000-000000000000"


def resolve_room(machine_name):
    try:
        room_id = maprt.get_treatment_room(machine_name)["data"]
    except MapRTApiError as problem:
        if problem.error_code == "DuplicateKey":
            options = [name for name, _id, _cs in maprt.get_treatment_rooms()]
            raise LookupError(f"{machine_name!r} matches several room configurations: "
                              f"{options}") from problem
        raise
    if room_id == EMPTY_GUID:
        raise LookupError(f"no room configured for machine {machine_name!r}")
    return room_id


ROOM_ID = resolve_room(plan.BeamSequence[0].TreatmentMachineName)
ROOM_ID
'''),

    ("md", """\
## Step 4 — find the surface

Newest first, distinguishing "no such patient" from "no surface yet" — notebook 04."""),
    ("code", '''\
def newest_surface(patient_id):
    try:
        surfaces = maprt.get_patient_surfaces(patient_id)
    except MapRTApiError as problem:
        raise LookupError(f"{patient_id}: no such patient on this appliance") from problem
    if not surfaces:
        raise LookupError(f"{patient_id}: no surface acquired yet — send them for a scan")
    return max(surfaces, key=lambda entry: entry[1])        # (id, timestamp)


SURFACE_ID, acquired = newest_surface(plan.PatientID)
print(f"surface {SURFACE_ID}  acquired {acquired}")
'''),

    ("md", """\
## Step 5 — get the map

Buffers in **millimetres**. Isocenter straight from the plan."""),
    ("code", '''\
import httpx2

from maprt_workshop import wire

headers = dict(maprt.headers)

request_body = {
    "PatientSurfaceId": SURFACE_ID,
    "TreatmentRoomId": ROOM_ID,
    "PatientPosition": plan.PatientSetupSequence[0].PatientPosition,
    "CouchBuffer": 20.0,
    "PatientBuffer": 20.0,
    "HighResolution": True,
    "Isocenter": {"x": isocenter[0], "y": isocenter[1], "z": isocenter[2]},
}

response = httpx2.post(maprt.api_url + "/integration/GetMap",
                       headers=headers, json=request_body, timeout=600)

if not response.text.strip().endswith("DONE"):      # notebook 07
    raise ValueError("truncated map — do not use it")

map_data = wire.parse_map_response(response.text)
print("map:", map_data[0].shape, f"{map_data[0].mean():.1%} of angles clear")
'''),

    ("md", """\
## Step 6 — check every beam

Both ways, because they answer different questions — notebook 06."""),
    ("code", '''\
from maprt_workshop import check_beams

checked, arc_plots, static_plots = check_beams(beams, map_data, arc_check_resolution=1)

for beam in checked:
    print(f"  {beam.number}  {beam.name:<14} {'PASS' if beam.status else 'FAIL'}")
'''),
    ("md", "And the appliance's own verdict, sending each beam's start control point:"),
    ("code", '''\
beam_list = [{"beamNumber": beam.number,
              "controlPoints": [{"gantryAngle": float(beam.gantry_start),
                                 "couchAngle": float(beam.couch),
                                 "coordinateSystem": "IEC_61217"}]}
             for beam in checked]

status_body = {key: value for key, value in request_body.items() if key != "HighResolution"}
server = dict(wire.parse_beam_delivery_status(
    httpx2.post(maprt.api_url + "/integration/GetBeamDeliveryStatus", headers=headers,
                json=dict(status_body, BeamList=beam_list), timeout=300).text))

server
'''),

    ("md", """\
## The report"""),
    ("code", '''\
import pandas as pd

report = pd.DataFrame([{
    "beam": beam.number,
    "name": beam.name,
    "type": beam.delivery_type,
    "couch": beam.couch,
    "gantry": (beam.gantry_start if beam.gantry_rotation == "NONE"
               else f"{beam.gantry_start}->{beam.gantry_stop} {beam.gantry_rotation}"),
    "map sweep": "PASS" if beam.status else "FAIL",
    "appliance": "PASS" if server[beam.number] else "FAIL",
} for beam in checked])

report
'''),

    ("md", """\
## Look at the disagreement

One row does not match. Find it before reading on."""),
    ("code", '''\
disagreements = report[report["map sweep"] != report["appliance"]]
disagreements
'''),
    ("md", """\
It is an **arc**, and this is notebook 06's lesson arriving in a real plan.

The appliance was sent that beam's **start control point** — one angle, which is clear. The map
sweep checked **every degree the arc passes through**, and some of them are not.

Both answers are correct answers to the questions asked. Only one of them is the question you
meant.

**In a real QA script, this is the bug that signs off a colliding arc.** Either send every control
point the beam occupies, or sweep the map yourself. Do not send two angles and believe the
result."""),

    ("md", """\
## The picture"""),
    ("code", '''\
%matplotlib inline
from maprt_workshop.plotting import overlay_beams, plot_collision_map

ax = plot_collision_map(
    map_data,
    title=f"{plan.RTPlanLabel} · {plan.PatientID} · {plan.BeamSequence[0].TreatmentMachineName} "
          f"· buffers 20/20 mm")
overlay_beams(ax, arc_plots, static_plots, checked)
ax.figure.savefig("plan_qa_report.png", dpi=120, bbox_inches="tight",
                  facecolor=ax.figure.get_facecolor())
print("saved plan_qa_report.png")
'''),
    ("md", """\
You can see the failing arc running straight through a collision lobe, and the failing static beam
sitting inside one. The picture is the part a planner will actually look at."""),

    ("md", """\
## All of it, as one function

Everything above, assembled. This is the deliverable."""),
    ("code", '''\
def check_plan(plan_path, couch_buffer_mm=20.0, patient_buffer_mm=20.0):
    """Check every beam in an RT Plan against a MapRT clearance map.

    Returns (report DataFrame, map_data, checked beams).
    """
    plan = pydicom.dcmread(plan_path)
    beams = read_beams(plan)
    isocenter = [float(v) for v in plan.BeamSequence[0].ControlPointSequence[0].IsocenterPosition]

    room_id = resolve_room(plan.BeamSequence[0].TreatmentMachineName)
    surface_id, _acquired = newest_surface(plan.PatientID)

    body = {
        "PatientSurfaceId": surface_id,
        "TreatmentRoomId": room_id,
        "PatientPosition": plan.PatientSetupSequence[0].PatientPosition,
        "CouchBuffer": couch_buffer_mm,
        "PatientBuffer": patient_buffer_mm,
        "HighResolution": True,
        "Isocenter": dict(zip("xyz", isocenter, strict=True)),
    }

    response = httpx2.post(maprt.api_url + "/integration/GetMap",
                           headers=headers, json=body, timeout=600)
    if response.text.lstrip().startswith("{"):
        envelope = response.json()
        raise MapRTApiError(envelope["errorCode"], envelope["errorCodeType"])
    if not response.text.strip().endswith("DONE"):
        raise ValueError("truncated map")

    map_data = wire.parse_map_response(response.text)
    checked, arc_plots, static_plots = check_beams(beams, map_data, 1)

    report = pd.DataFrame([{
        "beam": beam.number, "name": beam.name, "type": beam.delivery_type,
        "couch": beam.couch,
        "gantry": (beam.gantry_start if beam.gantry_rotation == "NONE"
                   else f"{beam.gantry_start}->{beam.gantry_stop} {beam.gantry_rotation}"),
        "verdict": "PASS" if beam.status else "FAIL",
    } for beam in checked])

    return report, map_data, checked


result, _map_data, _checked = check_plan(PLAN_PATH)
result
'''),

    ("md", """\
Sixty lines, give or take. That is the whole of it.

## What to change for your own site

| | |
| --- | --- |
| **The base URL and token** | from your appliance, not `connect()` |
| **`verify=False`** | a real appliance has a self-signed certificate — notebook 02 |
| **Buffers** | 20 mm is a starting point, not a policy |
| **Arcs** | send every control point, or sweep the map. Not two angles. |
| **Patient position** | from the plan, every time. The surface does not carry it — notebook 04 |
| **Error handling** | notebook 07. Especially the `DONE` check and the licence categories. |

## Your turn

Pick one:

1. **Buffer sensitivity.** Run `check_plan` at 10, 20, 30 and 40 mm. At what buffer does each beam
   start to fail? That is a more useful number than a single pass/fail.
2. **Fix the arcs.** Change the appliance check to send every control point an arc occupies, and
   confirm the two columns agree.
3. **Rescue the failures.** For each failing beam, find the nearest couch angle that would work."""),
    ("code", '''\
# Your turn.
'''),
    ("md", "<details><summary>One answer — buffer sensitivity</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
sensitivity = {}
for buffer_mm in (10.0, 20.0, 30.0, 40.0):
    report, _map, _checked = check_plan(PLAN_PATH, buffer_mm, buffer_mm)
    sensitivity[f"{buffer_mm:.0f} mm"] = report.set_index("name")["verdict"]

pd.DataFrame(sensitivity)
'''),
    ("md", """\
A beam that fails at 20 mm but passes at 10 mm is a different conversation from one that fails at
every buffer. The first is a margin discussion; the second is a replan.

---

## That is the workshop

You can now: authenticate against a MapRT appliance, tell its four kinds of failure apart, list
rooms and surfaces, request and parse a clearance map, check beams two ways, survive the things
that go wrong, and put it together into something that reads a plan and produces a report.

All of it with no library between you and the API, which was the point.

← [Back to the index](00_start_here.ipynb)"""),
]
