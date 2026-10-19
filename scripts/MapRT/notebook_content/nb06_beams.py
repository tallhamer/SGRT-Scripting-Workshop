"""06 — Beams and plans."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("06", "Beams and plans",
                  "Two ways to check a beam, and the gap between them.", "30 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## Two ways to ask

You have a plan. You want to know whether its beams can be delivered. There are two routes:

**Ask the appliance.** `POST /integration/GetBeamDeliveryStatus` takes a list of beams and
answers per beam. It is fast — the specification says *"usually much faster than the computation
of the full clearance map"* — because it checks a handful of angles instead of 65,000.

**Download the map and check yourself.** Free once you already hold the map, and it can answer
what-ifs your plan does not contain: *what couch angle would make this arc work?*

They agree. Until they don't — and the place they diverge is the point of this notebook."""),

    ("md", """\
## Set up

Surface, room, and the common part of the request body."""),
    ("code", '''\
SURFACE_ID = maprt.get_patient_surfaces("ANON001")[0][0]
ROOM_ID = maprt.get_treatment_rooms()[0][1]

setup = {
    "PatientSurfaceId": SURFACE_ID,
    "TreatmentRoomId": ROOM_ID,
    "PatientPosition": "HFS",
    "CouchBuffer": 20.0,        # mm
    "PatientBuffer": 20.0,      # mm
    "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0},
}
setup
'''),

    ("md", """\
## Describing a beam

A beam is a **list of control points**, each a gantry angle and a couch angle. One control point
is a static field; several describe a trajectory.

Build one by hand."""),
    ("code", '''\
control_point = {
    "gantryAngle": 0.0,
    "couchAngle": 0.0,
    "coordinateSystem": "IEC_61217",     # always, in DICOM-land
}
control_point
'''),
    ("code", '''\
beam = {
    "beamNumber": 1,                      # as numbered in the RT Plan
    "controlPoints": [control_point],
}
beam
'''),
    ("md", """\
`coordinateSystem` is on every control point because the API supports six couch conventions. In
practice, if your angles came from DICOM they are IEC 61217 and you say so.

The emulator **refuses** anything else rather than converting it, because the conversions are
vendor-specific and guessing would produce a confident wrong answer about whether a beam is
deliverable. Worth seeing:"""),
    ("code", '''\
import httpx2

headers = dict(maprt.headers)

refused = httpx2.post(maprt.api_url + "/integration/GetBeamDeliveryStatus", headers=headers,
                      json=dict(setup, BeamList=[{"beamNumber": 1, "controlPoints": [
                          {"gantryAngle": 0, "couchAngle": 0, "coordinateSystem": "Native"}]}]))
print("status:", refused.status_code)
print(refused.json()["errorData"][0][:110], "...")
'''),

    ("md", """\
## Ask the appliance

A plan's worth of static beams."""),
    ("code", '''\
def static_beam(number, couch, gantry):
    return {"beamNumber": number,
            "controlPoints": [{"gantryAngle": float(gantry), "couchAngle": float(couch),
                               "coordinateSystem": "IEC_61217"}]}


plan_beams = [
    static_beam(1, couch=0, gantry=0),      # AP
    static_beam(2, couch=0, gantry=90),     # left lateral
    static_beam(3, couch=0, gantry=180),    # PA
    static_beam(4, couch=90, gantry=90),    # lateral at a kicked couch
]

body = dict(setup, BeamList=plan_beams)
response = httpx2.post(maprt.api_url + "/integration/GetBeamDeliveryStatus",
                       headers=headers, json=body, timeout=120)
response.status_code
'''),
    ("md", "Envelope, as usual. Keys first:"),
    ("code", '''\
envelope = response.json()
print(list(envelope))
print("success:", envelope["success"])
envelope["data"]
'''),
    ("md", "`data.statuses` — one entry per beam, each a number and a boolean:"),
    ("code", '''\
for status in envelope["data"]["statuses"]:
    print(f"  beam {status['beamNumber']}: "
          f"{'deliverable' if status['isSafe'] else 'COLLISION'}")
'''),

    ("md", """\
## Now check the same beams against the map

Download the map once, then check locally."""),
    ("code", '''\
from maprt_workshop import wire

map_response = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers, timeout=300,
                           json=dict(setup, HighResolution=True))
map_data = wire.parse_map_response(map_response.text)

print("map:", map_data[0].shape, f"{map_data[0].mean():.1%} clear")
'''),
    ("md", """\
`check_beams` wants records with the fields a DICOM reader produces — couch, gantry start and
stop, rotation direction, delivery type — and writes its verdict into `status`."""),
    ("code", '''\
from dataclasses import dataclass

from maprt_workshop import check_beams


@dataclass
class Beam:
    number: int
    couch: str
    gantry_start: str
    gantry_stop: str
    gantry_rotation: str          # "NONE" for a static beam, "CW" or "CC" for an arc
    delivery_type: str            # "TREATMENT" or "SETUP"
    status: object = None


local_beams = [
    Beam(1, "0", "0", "0", "NONE", "TREATMENT"),
    Beam(2, "0", "90", "90", "NONE", "TREATMENT"),
    Beam(3, "0", "180", "180", "NONE", "TREATMENT"),
    Beam(4, "90", "90", "90", "NONE", "TREATMENT"),
]

checked, arcs, statics = check_beams(local_beams, map_data, 1)
[(beam.number, beam.status) for beam in checked]
'''),
    ("md", "Side by side:"),
    ("code", '''\
server = {s["beamNumber"]: s["isSafe"] for s in envelope["data"]["statuses"]}

print("  beam   appliance   map check")
for beam in checked:
    print(f"    {beam.number}    {str(server[beam.number]):<11} {beam.status}")

print("\\nagree:", all(server[b.number] == b.status for b in checked))
'''),
    ("md", """\
They agree, and not by luck: in this emulator both routes evaluate the same function, so the
same angle cannot get two answers. A real appliance computes them separately, and you should
expect agreement for the same reason — same geometry, same question."""),

    ("md", """\
## Arcs, where it gets interesting

An arc is not an angle, it is a **range** of angles. And here the two routes stop asking the same
question.

Take a full rotation at a kicked couch:"""),
    ("code", '''\
arc = Beam(5, couch="90", gantry_start="181", gantry_stop="179",
           gantry_rotation="CW", delivery_type="TREATMENT")

checked_arc, _arcs, _statics = check_beams([arc], map_data, 1)
print("map sweep says:", "deliverable" if checked_arc[0].status else "COLLISION")
'''),
    ("md", "Now ask the appliance — sending the arc as its **start and stop**, which is the obvious "
           "thing to do:"),
    ("code", '''\
endpoints = {"beamNumber": 5, "controlPoints": [
    {"gantryAngle": 181.0, "couchAngle": 90.0, "coordinateSystem": "IEC_61217"},
    {"gantryAngle": 179.0, "couchAngle": 90.0, "coordinateSystem": "IEC_61217"},
]}

answer = httpx2.post(maprt.api_url + "/integration/GetBeamDeliveryStatus", headers=headers,
                     json=dict(setup, BeamList=[endpoints]), timeout=120).json()
print("appliance says:", "deliverable" if answer["data"]["statuses"][0]["isSafe"] else "COLLISION")
'''),

    ("md", """\
## They disagree. Neither is wrong.

**GetBeamDeliveryStatus only checks the control points you send it.** Two control points are two
angles — not the 358 degrees between them. You described the arc's endpoints, so it checked the
endpoints, and both happen to be clear.

This is not a bug and it is not an emulator quirk. It is *why* the endpoint is fast. The
specification is explicit: it *"checks clearance for individual control points"*.

Send the whole sweep and it agrees:"""),
    ("code", '''\
swept = {"beamNumber": 5, "controlPoints": [
    {"gantryAngle": float((181 + step) % 360), "couchAngle": 90.0,
     "coordinateSystem": "IEC_61217"}
    for step in range(359)
]}

answer = httpx2.post(maprt.api_url + "/integration/GetBeamDeliveryStatus", headers=headers,
                     json=dict(setup, BeamList=[swept]), timeout=300).json()
print(f"sent {len(swept['controlPoints'])} control points")
print("appliance says:", "deliverable" if answer["data"]["statuses"][0]["isSafe"] else "COLLISION")
'''),
    ("md", """\
**The lesson:** if you are checking arcs with `GetBeamDeliveryStatus`, send every control point
the beam actually occupies — or get the map and sweep it yourself. Sending two and believing the
answer is how a colliding arc gets signed off.

Draw it and the reason is obvious:"""),
    ("code", '''\
%matplotlib inline
from maprt_workshop.plotting import overlay_beams, plot_collision_map

all_beams = local_beams + [Beam(5, "90", "181", "179", "CW", "TREATMENT")]
checked, arcs, statics = check_beams(all_beams, map_data, 1)

ax = plot_collision_map(map_data, title="The arc at couch 90 passes straight through a collision")
overlay_beams(ax, arcs, statics, checked)
'''),
    ("md", """\
The vertical line at couch 90 is the arc. It runs top to bottom — every gantry angle — and it
crosses the collision lobe on its way. Its two endpoints, at the very top and very bottom, are in
clear space."""),

    ("md", """\
## The wrap-around trap

While we are here: an arc crossing gantry 180 **wraps around the end of the array**, because the
rows run 180…359 then 0…179.

A naive implementation slices:

```python
image[start:stop, couch]      # if stop < start this is EMPTY
```

and `numpy.all()` of an empty selection is `True`. So a colliding arc gets reported safe — the
worst possible failure for this kind of check. `check_beams` steps indices modulo 360 instead."""),
    ("code", '''\
import numpy as np

print("np.all of an empty selection:", np.all(np.array([], dtype=bool)))
print("...which is why a wrapping arc must never be checked with a slice")
'''),

    ("md", """\
## Beam transitions

A plan is not just its beams — the machine has to **move between** them, and that movement can
collide even when both beams are clear.

The API has `GetMapAndBeamTransitions` for this. **But:** it is documented as a C# method and
Appendix B does not list a REST route for it. So the emulator's version is an invention — the
path, the response format, all of it."""),
    ("code", '''\
response = httpx2.post(maprt.api_url + "/integration/GetMapAndBeamTransitions", headers=headers,
                       timeout=300, json=dict(setup, HighResolution=False, BeamList=[
                           static_beam(1, couch=90, gantry=0),
                           static_beam(2, couch=90, gantry=180),
                       ]))

print(response.headers["X-Emulator-Unofficial"])
'''),
    ("code", '''\
import json

map_part, _marker, transitions = response.text.partition("TRANSITIONS\\n")

print("the map:", map_part.splitlines()[0], "...", map_part.rstrip()[-4:])
print()
for status in json.loads(transitions)["data"]["statuses"]:
    print(f"  beam {status['initialBeamNumber']} -> {status['finalBeamNumber']}: "
          f"{'safe' if status['isSafe'] else 'COLLISION ON THE WAY'}")
'''),
    ("md", """\
Both beams are clear; getting from one to the other is not. That is a real planning concern, and
it is invisible if you only check the beams.

**Code written against this route will not port.** If you need transitions against a real
appliance, use Vision RT's NuGet client or ask them. The concept is real; this particular HTTP
shape is not."""),

    ("md", """\
## Your turn

Beam 5 — the arc at couch 90 — collides. **Find a couch angle where the same 181→179 CW arc is
deliverable.** Use the map you already have; no more API calls needed."""),
    ("code", '''\
# Your turn.
# for couch in ...:
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
COUCH_VALUES = np.hstack((np.arange(270, 360), np.arange(0, 91)))

workable = []
for couch in COUCH_VALUES:
    candidate = Beam(99, str(couch), "181", "179", "CW", "TREATMENT")
    checked_one, _a, _s = check_beams([candidate], map_data, 1)
    if checked_one[0].status:
        workable.append(int(couch))

print(f"{len(workable)} couch angles allow a full CW arc")
print("they are:", workable)
'''),
    ("md", """\
A narrow band around couch 0 — which is exactly the waist of the bow-tie, and the reason full
arcs are planned at couch 0 unless there is a reason not to.

**This is the question you could not ask without scripting.** The appliance will tell you whether
*your* plan works. Only a map in your hands will tell you what *would*.

---

**Next:** [`07_robustness.ipynb`](07_robustness.ipynb) — making the failures happen, on purpose,
so your code survives them."""),
]
