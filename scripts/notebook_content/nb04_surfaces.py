"""04 — Patient surfaces."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("04", "Patient surfaces",
                  "Two calls to get a mesh, and the metadata that is not in it.", "25 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## Two calls, not one

A surface is a full-body triangle mesh acquired by the Vision RT system in your CT room. Getting
one takes two requests:

1. `GET /integration/patients/{patientId}/surfaces` — what has been acquired for this patient
2. `GET /integration/surfaces/{surfaceId}` — the mesh itself

The split exists because a patient may have several surfaces (re-scans, different setups) and the
meshes are large. You look before you fetch."""),

    ("md", """\
## 1. What has this patient got?

Patient ids are DICOM patient ids, up to 64 characters. The simulator's catalog has three."""),
    ("code", '''\
import httpx2

PATIENT_ID = "ANON001"

url = maprt.api_url + f"/integration/patients/{PATIENT_ID}/surfaces"
headers = dict(maprt.headers)

response = httpx2.get(url, headers=headers)
print("status:", response.status_code)
'''),
    ("code", '''\
envelope = response.json()
print("success:", envelope["success"])
envelope["data"]
'''),
    ("md", """\
Three fields per surface:

| field | |
| --- | --- |
| `id` | a GUID — what call 2 wants |
| `timeStamp` | when it was acquired, in **UTC** |
| `timeZone` | the zone it was acquired *in*, as a name |

That pair is worth noticing. The API gives you UTC plus a zone **name**, not an offset — so
"2026-06-21T14:51:27" + "Central European Standard Time" rather than a single string with `+02:00`
in it. If you are displaying acquisition times to a planner, convert using the named zone;
offsets drift with daylight saving and the name does not."""),

    ("md", """\
## Newest first — and check

"Use the most recent surface" is the usual requirement, so the order matters. The API does not
promise one, so sort explicitly rather than trusting what arrived."""),
    ("code", '''\
surfaces = sorted(envelope["data"], key=lambda s: s["timeStamp"], reverse=True)

for surface in surfaces:
    print(f"  {surface['timeStamp']}  {surface['id']}")

SURFACE_ID = surfaces[0]["id"]
print(f"\\nnewest: {SURFACE_ID}")
'''),

    ("md", """\
## Two answers that look the same and are not

`ANON003` is in the simulator's catalog but has no surfaces. `NOBODY` is not in it at all.
These are *different situations* and the API reports them differently — a client that collapses
them will tell a planner the wrong thing."""),
    ("code", '''\
for patient in ("ANON003", "NOBODY"):
    envelope = httpx2.get(maprt.api_url + f"/integration/patients/{patient}/surfaces",
                          headers=headers).json()
    print(f"{patient:<10} success={str(envelope['success']):<6} "
          f"data={envelope['data']}  errorCode={envelope['errorCode']}")
'''),
    ("md", """\
- **`ANON003`** — `success: true`, `data: []`. We know this patient. **Nobody has acquired a
  surface for them yet.** Tell the planner to go and scan them.
- **`NOBODY`** — `success: false`. We have never heard of this patient id. Probably a typo, or
  the wrong patient id field from your planning system.

One sends someone to the CT room; the other sends them to check their code. "No surfaces found"
for both would be wrong twice.

> The error code there, `PatientNotFound`, is **invented by this simulator.** The REST
> specification names codes only for authentication, licensing and room administration — it says
> nothing about an unknown patient. Do not match on that string in production code. You can see
> everything the simulator made up at `/sim/state` under `inventedErrorCodes`."""),

    ("md", """\
## 2. Fetch the mesh

Now the second call. This one is **separately licensed** — surface data is a licensed feature, so
`FeatureNotLicensed` is a normal thing to handle here, not an exotic failure."""),
    ("code", '''\
response = httpx2.get(maprt.api_url + f"/integration/surfaces/{SURFACE_ID}", headers=headers)
envelope = response.json()

print("status :", response.status_code)
print("success:", envelope["success"])
print("type of data:", type(envelope["data"]).__name__)
print("length      :", f"{len(envelope['data']):,} characters")
'''),
    ("md", "A **string**, not a binary body. Look at the first few characters:"),
    ("code", '''\
envelope["data"][:60]
'''),

    ("md", """\
## Decoding it

That is a **data URI**: a little header, a comma, then base64. Split on the last comma and decode
the tail."""),
    ("code", '''\
import base64

data_uri = envelope["data"]
encoded = data_uri.split(",")[-1]        # everything after the LAST comma
raw = base64.b64decode(encoded)

print(f"{len(raw):,} bytes")
'''),
    ("md", "What are the bytes? Look before parsing:"),
    ("code", '''\
print(raw[:200].decode())
'''),

    ("md", """\
An **ASCII OBJ** file. `v` lines are vertices, `f` lines are triangular faces. (The `ps` and `fs`
lines are vertex and face counts — not standard OBJ, but what the appliance emits, so a reader
has to tolerate them.)

One thing that catches everyone: **OBJ face indices are 1-based.** An off-by-one here produces a
mesh that looks almost right, which is worse than one that looks obviously wrong."""),
    ("code", '''\
from maprt_workshop.obj import describe, parse_obj

vertices, faces, normals = parse_obj(raw)
print(describe(vertices, faces))
'''),

    ("md", """\
## The trap: what the bytes do *not* say

Read this twice. From §3.2.1 of the specification:

> The patient surface returned by the API always uses the **couch coordinate system** for the
> mesh. The surface does **not** contain any metadata indicating patient position (e.g. whether
> it is HFS or HFP).

So:

- These coordinates are **not** in the DICOM patient frame. They are in the scanner's own frame.
- Nothing in the file tells you whether this person was head-first or feet-first, supine or prone.

You have to know the patient position from somewhere else — the RT Plan, usually — and apply the
transform yourself. **Nothing will warn you if you get it wrong.** A feet-first patient treated as
head-first gives you a perfectly valid mesh, pointing the wrong way, and a clearance map that is
confidently incorrect.

(This is also why `GetMap` has a `PatientPosition` field: the appliance needs to be told too.)

One more caveat from the same section: the returned mesh *"may have lower resolution and is valid
for visualization only"*, depending on licensing. Do not measure things with it."""),

    ("md", """\
## Look at it

The cheapest check that a mesh loaded correctly is to draw it."""),
    ("code", '''\
%matplotlib inline
from maprt_workshop.plotting import plot_surface

ax = plot_surface(vertices, faces, stride=6,
                  title=f"{PATIENT_ID} · acquired {surfaces[0]['timeStamp']}")
ax.view_init(elev=22, azim=-60)
'''),
    ("md", """\
The long axis is superior-inferior. If that ever comes out as a cube, the aspect ratio is wrong
and you are looking at a shape that does not exist.

For anything more than a sanity check, use a real 3D viewer — this is matplotlib drawing 19,000
triangles and it is not trying to be good at it."""),

    ("md", """\
## The bounding box is the useful number

More often than plotting, what you want is the extent — to check the scale is plausible and the
mesh is not empty."""),
    ("code", '''\
from maprt_workshop.obj import bounding_box

low, high = bounding_box(vertices)
extent = high - low

print(f"  min    {low.round(1)}")
print(f"  max    {high.round(1)}")
print(f"  extent {extent.round(0)} mm")
print(f"\\n  that is {extent.max() / 1000:.2f} m along the longest axis")
'''),
    ("md", "All distances in this API are **millimetres**, everywhere, without exception. If a "
           "number looks a thousand times too big or small, that is the first thing to check."),

    ("md", """\
## When the feature is not licensed

Worth seeing once, so your code handles it."""),
    ("code", '''\
httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "unlicensed-surfaces"})

envelope = httpx2.get(maprt.api_url + f"/integration/surfaces/{SURFACE_ID}",
                      headers=headers).json()
print("fetching the mesh:", envelope["errorCode"], f"({envelope['errorCodeType']})")

# But listing them still works — it is the *mesh* that is licensed, not the metadata.
listing = httpx2.get(maprt.api_url + f"/integration/patients/{PATIENT_ID}/surfaces",
                     headers=headers).json()
print("listing surfaces :", "success" if listing["success"] else "refused",
      f"({len(listing['data'])} surfaces)")

httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "ok"})
'''),
    ("md", """\
So an unlicensed appliance will happily tell you a surface *exists* and then refuse to give it to
you. Your code should say "this site is not licensed for surface data", not "surface not found"."""),

    ("md", """\
## Your turn

Write `newest_surface(patient_id)` returning `(surface_id, vertices, faces)`, which:

- distinguishes the unknown patient from the patient with no surfaces,
- picks the most recent surface,
- handles `FeatureNotLicensed` with a message that says *licensing*, not *missing*.

Test it on `ANON001`, `ANON002`, `ANON003` and `NOBODY`."""),
    ("code", '''\
# Your turn.
def newest_surface(patient_id):
    ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
from maprt_workshop import MapRTApiError

def newest_surface(patient_id):
    try:
        listed = maprt.get_patient_surfaces(patient_id)       # [(id, timestamp), ...]
    except MapRTApiError as problem:
        raise LookupError(f"{patient_id}: no such patient on this appliance "
                          f"({problem.error_code})") from problem

    if not listed:
        raise LookupError(f"{patient_id}: known to the appliance, but no surface has been "
                          f"acquired yet — send them for a scan")

    surface_id, _timestamp = max(listed, key=lambda entry: entry[1])

    try:
        raw = maprt.get_surface(surface_id)
    except MapRTApiError as problem:
        if problem.category == "license":
            raise PermissionError(f"{patient_id}: this appliance is not licensed for surface "
                                  f"data — the surface exists but cannot be retrieved") from problem
        raise

    vertices, faces, _normals = parse_obj(raw)
    return surface_id, vertices, faces


for patient in ("ANON001", "ANON002", "ANON003", "NOBODY"):
    try:
        surface_id, vertices, faces = newest_surface(patient)
        print(f"{patient:<9} {surface_id[:8]}  {describe(vertices, faces)}")
    except (LookupError, PermissionError) as problem:
        print(f"{patient:<9} {problem}")
'''),

    ("md", """\
---

**Keep `SURFACE_ID` and `ROOM_ID`.** Together they are most of a clearance map request.

**Next:** [`05_clearance_maps.ipynb`](05_clearance_maps.ipynb) — the centrepiece, and the one
endpoint that does not answer with JSON."""),
]
