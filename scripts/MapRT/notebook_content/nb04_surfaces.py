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

Patient ids are DICOM patient ids, up to 64 characters. The emulator's catalog has three."""),
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

`ANON003` is in the emulator's catalog but has no surfaces. `NOBODY` is not in it at all.
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

> The error code there, `PatientNotFound`, is **invented by this emulator.** The REST
> specification names codes only for authentication, licensing and room administration — it says
> nothing about an unknown patient. Do not match on that string in production code. You can see
> everything the emulator made up at `/emulator/state` under `inventedErrorCodes`."""),

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
## Parsing the OBJ by hand

An **ASCII OBJ** file: one record per line, and the first word of each line says what kind of
record it is. Before parsing anything, find out which kinds this file actually contains."""),
    ("code", '''\
from collections import Counter

text = raw.decode("ascii")
lines = text.splitlines()

Counter(line.split()[0] if line.strip() else "(blank)" for line in lines)
'''),
    ("md", """\
| first word | what the line is |
| --- | --- |
| `#` | a comment — ignore it |
| `ps`, `fs` | vertex and face **counts**. Not standard OBJ, but what the appliance emits, so a reader has to tolerate them |
| `v` | one **vertex**: `x y z`, in millimetres |
| `f` | one triangular **face**: the numbers of its three vertices |

A real appliance export looks the same, only bigger, and OBJ files from other tools can carry
more kinds (`vn` normals, `vt` texture coordinates). Two pieces matter for a mesh: the `v` lines
and the `f` lines."""),

    ("md", """\
### Vertices

Every `v` line becomes one row of an `N × 3` array. Match `"v "` *with the space*, or a `vn`
normal line gets read as a vertex too."""),
    ("code", '''\
import numpy as np

vertices = np.array([line.split()[1:4] for line in lines if line.startswith("v ")],
                    dtype=float)

print(vertices.shape)
vertices[:3]
'''),

    ("md", """\
### Faces

Each `f` line names three vertices. A field can be written `7`, `7/2`, `7//3` or `7/2/3` (vertex,
texture, normal), and the vertex is always the part before the first `/`.

MapRT sends triangles only. Check that rather than assume it: a four-vertex face would otherwise
be silently cut down to three."""),
    ("code", '''\
face_rows = [[field.split("/")[0] for field in line.split()[1:]]
             for line in lines if line.startswith("f ")]

assert all(len(row) == 3 for row in face_rows), "not every face is a triangle"

faces_as_written = np.array(face_rows, dtype=int)
print("smallest vertex number:", faces_as_written.min())
print("largest vertex number: ", faces_as_written.max())
print("number of vertices:    ", len(vertices))
'''),
    ("md", """\
The numbers run from **1** to **N**. Python arrays run from **0** to **N − 1**.

**OBJ face numbers are 1-based**, and this is the mistake that catches everyone. Use them as
written and the largest one points past the end of the array. Worse, every *other* face quietly
uses the wrong three vertices. The result is a mesh that looks *almost* right, which is worse than
one that looks obviously broken. Subtract one:"""),
    ("code", '''\
faces = faces_as_written - 1

assert faces.min() == 0 and faces.max() == len(vertices) - 1
faces[:3]
'''),

    ("md", """\
### Check against what the file promised

The `ps` and `fs` lines say how many vertices and faces there should be. They are a free check
that nothing was skipped. (Not every OBJ has them, hence `.get`.)"""),
    ("code", '''\
declared = {line.split()[0]: int(line.split()[1])
            for line in lines if line.startswith(("ps ", "fs "))}

print(f"vertices: file says {declared.get('ps')}, parsed {len(vertices)}")
print(f"faces:    file says {declared.get('fs')}, parsed {len(faces)}")
'''),

    ("md", """\
### The library version

`maprt_workshop.obj.parse_obj` is these same steps in one function. It also reads `vn` normals
when present and splits a four-sided face into two triangles instead of refusing it. Use it from
here on. Writing it once by hand is how you know what it does."""),
    ("code", '''\
from maprt_workshop.obj import describe, parse_obj

library_vertices, library_faces, normals = parse_obj(raw)

print("same vertices:", np.array_equal(vertices, library_vertices))
print("same faces:   ", np.array_equal(faces, library_faces))
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
## Look at it, in 3D

The cheapest check that a mesh loaded correctly is to draw it. Plotly's `Mesh3d` takes exactly
the two arrays you just built, split into columns:

- `x`, `y`, `z`: one value per **vertex**
- `i`, `j`, `k`: one value per **face**, the 0-based row numbers of its three vertices

That is the second reason the subtraction mattered: `Mesh3d` counts from zero too."""),
    ("code", '''\
import plotly.graph_objects as go

x, y, z = vertices.T        # columns of the N × 3 vertex array
i, j, k = faces.T           # columns of the M × 3 face array

fig = go.Figure(go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, color="lightsteelblue"))
fig
'''),
    ("md", """\
Drag to rotate, scroll to zoom, hover for coordinates.

**It looks wrong, and it is wrong.** Plotly has stretched each axis to fill a cube, so a body
1.7 m long and 0.2 m deep has been drawn about as deep as it is long. Nothing errored, and you are
looking at a shape that does not exist. Tell it that a millimetre is the same length on every
axis:"""),
    ("code", '''\
fig.update_layout(
    title=f"{PATIENT_ID} · acquired {surfaces[0]['timeStamp']}",
    scene=dict(aspectmode="data",                  # 1 mm is 1 mm on every axis
               xaxis_title="x (mm)", yaxis_title="y (mm)", zaxis_title="z (mm)"),
    height=500, margin=dict(l=0, r=0, t=40, b=0),
)
fig
'''),
    ("md", """\
Now the long axis is superior-inferior, the way a person lies on a couch.

A single flat colour makes the shape hard to read. Colour by height instead, and make the hover
text say what the numbers are:"""),
    ("code", '''\
fig.update_traces(
    intensity=z, colorscale="Blues", showscale=False,          # colour by height above the couch
    lighting=dict(ambient=0.5, diffuse=0.8, specular=0.2),
    hovertemplate="x %{x:.0f} mm<br>y %{y:.0f} mm<br>z %{z:.0f} mm<extra></extra>",
)
fig.update_layout(scene_camera=dict(eye=dict(x=-1.2, y=-1.6, z=0.9)))
fig
'''),
    ("md", """\
These are still **couch coordinates**, as the section above said. The picture tells you the mesh
parsed. It does not tell you which way the patient was lying.

This mesh has about 19,000 faces and turns smoothly. A real appliance export can have half a
million, and any viewer that runs in a browser tab gets sluggish at that size. For those, thin the
mesh out first (decimation). Tools such as VTK or trimesh can do it.

For a report or a PDF, where an interactive figure cannot go,
`maprt_workshop.plotting.plot_surface` draws the same mesh as a static matplotlib image."""),

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
httpx2.post(maprt.api_url + "/emulator/scenario", json={"name": "unlicensed-surfaces"})

envelope = httpx2.get(maprt.api_url + f"/integration/surfaces/{SURFACE_ID}",
                      headers=headers).json()
print("fetching the mesh:", envelope["errorCode"], f"({envelope['errorCodeType']})")

# But listing them still works — it is the *mesh* that is licensed, not the metadata.
listing = httpx2.get(maprt.api_url + f"/integration/patients/{PATIENT_ID}/surfaces",
                     headers=headers).json()
print("listing surfaces :", "success" if listing["success"] else "refused",
      f"({len(listing['data'])} surfaces)")

httpx2.post(maprt.api_url + "/emulator/scenario", json={"name": "ok"})
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
