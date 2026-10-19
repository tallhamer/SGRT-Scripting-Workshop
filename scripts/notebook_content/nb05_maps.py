"""05 — Clearance maps."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("05", "Clearance maps",
                  "Build the request field by field, then read what streams back.", "35 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## What a clearance map is

For every combination of **gantry angle** and **couch angle**, the appliance rotates its scanned
gantry and couch around the isocenter, with the patient surface in place, and asks: does anything
overlap?

The answer is a grid of yes/no. Gantry runs 0–359°; couch runs ±90° (which in IEC 61217 is
270–359 and 0–90). That is about 65,000 answers at one-degree resolution, which is why the
specification warns the call *"may take up to a few minutes"*.

Before the check, the patient is **uniformly expanded** by a patient buffer and the couch and
gantry by a couch buffer. Those buffers are how you ask for clearance rather than mere
non-intersection."""),

    ("md", """\
## Building the request, one field at a time

`POST /integration/GetMap` takes a JSON body. We will add one field per cell, so you see what
each one is for — and, more importantly, what units it is in.

Start empty."""),
    ("code", '''\
body = {}
body
'''),

    ("md", """\
### Which surface, and which room

Both GUIDs, from notebooks 03 and 04. The room GUID — *not* the machine name."""),
    ("code", '''\
body["PatientSurfaceId"] = maprt.get_patient_surfaces("ANON001")[0][0]
body["TreatmentRoomId"] = maprt.get_treatment_rooms()[0][1]

body
'''),

    ("md", """\
### How the patient is lying

The DICOM patient position, from tag (0018,5100) in the RT Plan. `HFS` is head-first supine.

The mesh carries no patient position (notebook 04), so the appliance has to be told. Get this
wrong and the map is confidently incorrect.

> **A discrepancy worth knowing.** §5.2.6 of the specification says to send the *numeric*
> `PatientPosition` enum — `1` for HFS. The live-verified desktop client sends the **DICOM
> string** `"HFS"`, and the appliance accepts it. Both work; the simulator takes either. If you
> are writing against a real appliance, try the string and keep the number in your back pocket."""),
    ("code", '''\
body["PatientPosition"] = "HFS"          # or 1 — see above
body["PatientPosition"]
'''),

    ("md", """\
### The buffers — **in millimetres**

This is where people get bitten. A planner thinks in centimetres; the API wants millimetres.

`CouchBuffer` expands the couch and gantry; `PatientBuffer` expands the patient. 20 mm each is a
reasonable starting point."""),
    ("code", '''\
couch_buffer_cm = 2.0
patient_buffer_cm = 2.0

body["CouchBuffer"] = couch_buffer_cm * 10        # -> mm
body["PatientBuffer"] = patient_buffer_cm * 10    # -> mm

print(f"{couch_buffer_cm} cm -> {body['CouchBuffer']} mm")
'''),

    ("md", """\
### The isocenter — **also millimetres**

In the **DICOM patient coordinate system**, as written in RT Plan tag (300a,012c). Straight out of
the plan, no conversion."""),
    ("code", '''\
body["Isocenter"] = {"x": 0.0, "y": 0.0, "z": 0.0}
body["Isocenter"]
'''),

    ("md", """\
### Resolution

`false` samples coarsely and is fast. `true` is one degree and is slow — this is the flag that
turns seconds into minutes on a real appliance.

Start coarse while you are experimenting."""),
    ("code", '''\
body["HighResolution"] = False

body
'''),

    ("md", """\
## Send it

Same three headers as every other call. Note there is no `GET` here — this one is a `POST` with a
body."""),
    ("code", '''\
import httpx2

headers = dict(maprt.headers)

response = httpx2.post(maprt.api_url + "/integration/GetMap",
                       headers=headers, json=body, timeout=180)
response.status_code
'''),

    ("md", """\
## Look at what came back — it is not JSON

This is the one endpoint that breaks the pattern. Check the content type first:"""),
    ("code", '''\
response.headers["Content-Type"]
'''),
    ("md", "Plain text. So what is in it?"),
    ("code", '''\
print(response.text[:120])
'''),
    ("md", "And the end:"),
    ("code", '''\
print(response.text[-60:])
'''),

    ("md", """\
## The format

```
37,36            <- couch_samples , gantry_samples
90,180,1         <- couch , gantry , isOK
85,180,1
80,180,1
...
DONE
```

- **Line 1** is the sampling: how many couch angles by how many gantry angles. Multiply them and
  that is how many lines follow.
- **Every other line** is a triple: a couch angle, a gantry angle, and `1` for clear or `0` for
  collision. Angles are IEC 61217.
- **`DONE`** terminates it.

Two things follow from this, and both matter:

**The list is not ordered.** §5.2.6 says so explicitly. Each triple carries its own angles
precisely so that order cannot matter — never index by arrival position.

**`DONE` is not decoration.** It is how you know you got all of it. Notebook 07 shows what a
truncated map does, and it is nastier than you would guess."""),

    ("md", """\
## Parse it by hand, once

You will use the library parser afterwards. Do it once yourself so you know what it does."""),
    ("code", '''\
tokens = response.text.split()

header = tokens[0]
triples = tokens[1:-1]        # everything between the header and DONE
terminator = tokens[-1]

print("header    :", header)
print("triples   :", f"{len(triples):,}")
print("terminator:", terminator)
'''),
    ("code", '''\
couch_samples, gantry_samples = (int(value) for value in header.split(","))

print(f"{couch_samples} couch x {gantry_samples} gantry = {couch_samples * gantry_samples:,}")
print("triples received:", f"{len(triples):,}")
print("complete        :", couch_samples * gantry_samples == len(triples))
'''),
    ("md", "Now unpack a few triples:"),
    ("code", '''\
for token in triples[:5]:
    couch, gantry, is_ok = (int(value) for value in token.split(","))
    print(f"  couch {couch:>3}  gantry {gantry:>3}  {'clear' if is_ok else 'COLLISION'}")
'''),

    ("md", """\
## Into an array

A list of triples is awkward; a 2-D array is what you want. The library parser does this, puts the
axes in the order the MapRT display uses, and upsamples a coarse map to one degree."""),
    ("code", '''\
from maprt_workshop import wire

image, x_ticks, y_ticks = wire.parse_map_response(response.text)

print("shape:", image.shape, " (gantry rows, couch columns)")
print("clear:", f"{image.mean():.1%} of angles")
'''),

    ("md", """\
## The axes are not in the order you would guess

Rows run gantry **180 → 359, then 0 → 179**. Columns run couch **270 → 359, then 0 → 90**.

That is the layout MapRT's own display uses — it puts gantry 180 at the top and the couch's
negative range on the left, so the picture reads like the room. It means `image[0]` is gantry
**180**, not gantry 0."""),
    ("code", '''\
import numpy as np

GANTRY_VALUES = np.hstack((np.arange(180, 360), np.arange(0, 180)))
COUCH_VALUES = np.hstack((np.arange(270, 360), np.arange(0, 91)))

print("row 0   is gantry", GANTRY_VALUES[0])
print("row 180 is gantry", GANTRY_VALUES[180])
print("col 0   is couch ", COUCH_VALUES[0])
print("col 90  is couch ", COUCH_VALUES[90])
'''),
    ("md", "So looking up one angle means finding its index first:"),
    ("code", '''\
def is_clear(couch, gantry):
    row = int(np.flatnonzero(GANTRY_VALUES == gantry)[0])
    column = int(np.flatnonzero(COUCH_VALUES == couch)[0])
    return bool(image[row, column])


for couch, gantry in [(0, 0), (0, 90), (0, 180), (90, 90), (90, 270)]:
    print(f"  couch {couch:>3}  gantry {gantry:>3}  "
          f"{'clear' if is_clear(couch, gantry) else 'COLLISION'}")
'''),

    ("md", """\
## Draw it

A 65,000-cell array is not something to read as numbers."""),
    ("code", '''\
%matplotlib inline
from maprt_workshop.plotting import plot_collision_map

plot_collision_map((image, x_ticks, y_ticks),
                   title="ANON001 · buffers 20/20 mm · isocenter (0, 0, 0)");
'''),
    ("md", """\
That shape is what a clearance map looks like: two **bow-ties** centred on the lateral gantry
angles, pinching as the couch rotates away from zero.

The physics is in one line. With the gantry at angle *g* and the couch at angle *c*, the gantry
head sits — relative to the isocenter, in the patient's frame — at:

```
along the body   R · sin(g) · sin(c)
lateral          R · sin(g) · cos(c)
vertical         R · cos(g)
```

At gantry **0** and **180** the `sin(g)` terms vanish: the head is directly above or below the
isocenter, so **the couch angle cannot matter**. That is why the top and bottom bands are flat.
At gantry 90 with the couch kicked, the head swings a full *R* along the patient's axis — out over
the head or feet — which is exactly where real collisions happen.

> The map you are looking at came from a **model**, not a collision engine. It responds to the
> inputs the way a real one does, which is what makes it worth reasoning about; the absolute
> numbers are invented. See `data/MapRT/README.md`.

Check that claim about gantry 0 and 180 rather than taking it:"""),
    ("code", '''\
for gantry in (0, 180):
    row = image[int(np.flatnonzero(GANTRY_VALUES == gantry)[0])]
    print(f"gantry {gantry:>3}: {row.min()}..{row.max()} across all "
          f"{len(row)} couch angles -> {'constant' if row.min() == row.max() else 'VARIES'}")
'''),

    ("md", """\
## Where is the map actually from?

The simulator tells you, in a header of its own. Recorded means real bytes from a real response;
synthetic means the model computed it."""),
    ("code", '''\
response.headers["X-Sim-Map-Source"]
'''),
    ("md", "`recorded-nearest` is the one to watch for: it means a recording existed for the same "
           "surface and room but a **different isocenter**, and you were given that instead. "
           "Useful for keeping a notebook working; not an answer to the question you asked."),

    ("md", """\
## Low resolution vs high

Ask for the same map at one degree. On a real appliance this is the difference between seconds
and minutes."""),
    ("code", '''\
import time

started = time.monotonic()
high = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers, timeout=300,
                   json=dict(body, HighResolution=True))
elapsed = time.monotonic() - started

high_image, high_x, high_y = wire.parse_map_response(high.text)

print(f"header    : {high.text.splitlines()[0]}")
print(f"took      : {elapsed:.1f} s")
print(f"shape     : {high_image.shape}")
print(f"low-res   : {image.shape}")
'''),

    ("md", """\
## Read those two shapes again

```
high resolution : (360, 181)
coarse          : (360, 185)
```

**They are not the same width.** This surprises people, including the person who wrote this
notebook, so here is why.

The couch axis spans 180° **inclusive** — 270 through 90 is 181 whole-degree positions. A coarse
map is upsampled to one degree by repeating each sample *s* times. With *n* samples at step *s*:

- to tile the axis you need `(n-1) × s == 180`
- to fill 181 columns you need `n × s == 181`

No integer step above 1 satisfies both. So **every** coarse map overshoots by exactly `s-1`
columns, and those extra columns are a trailing repeat of couch 90.

It is harmless where it matters — each block still starts at a multiple of *s*, so couch `270+k`
still lands at column *k* — but:

- **do not assume the two resolutions have the same shape**, and
- **do not index a coarse map from its right-hand edge.**"""),
    ("code", '''\
print("coarse, last 6 columns are identical:",
      bool(np.all(image[:, 180:] == image[:, 180:181])))
print("couch 90 is at column", int(np.flatnonzero(COUCH_VALUES == 90)[0]),
      "in both — which is the part that matters")
'''),

    ("md", """\
## Sweeping the buffers

The reason to script this at all: ask a question you could not ask by hand. What does the buffer
actually cost you?"""),
    ("code", '''\
import matplotlib.pyplot as plt

buffers_mm = [0, 20, 40, 80]
figure, axes = plt.subplots(1, len(buffers_mm), figsize=(17, 5.2))

for axis, buffer_mm in zip(axes, buffers_mm, strict=True):
    swept = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers, timeout=300,
                        json=dict(body, CouchBuffer=buffer_mm, PatientBuffer=buffer_mm))
    swept_image, swept_x, swept_y = wire.parse_map_response(swept.text)
    plot_collision_map((swept_image, swept_x, swept_y), ax=axis, tick_every=90,
                       title=f"{buffer_mm} mm — {swept_image.mean():.0%} clear")
    if axis is not axes[-1]:
        axis.get_legend().remove()
figure.tight_layout()
'''),
    ("md", """\
Monotonic, as it must be: expanding the patient or the couch can only ever *create* collisions,
never remove them. If a buffer sweep ever opened an angle up, something would be wrong.

## Your turn

Write `safe_angles(couch)` that returns every gantry angle deliverable at a given couch angle,
then find the couch angle with the **most** freedom. Predict the answer before you run it."""),
    ("code", '''\
# Your turn.
def safe_angles(couch):
    ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
def safe_angles(couch, grid=None):
    """Every gantry angle clear at this couch angle, in ascending order."""
    grid = high_image if grid is None else grid
    column = int(np.flatnonzero(COUCH_VALUES == couch)[0])
    return sorted(GANTRY_VALUES[np.flatnonzero(grid[:, column])].tolist())


counts = {couch: len(safe_angles(couch)) for couch in COUCH_VALUES}
best = max(counts, key=counts.get)

print(f"most freedom at couch {best}: {counts[best]} of 360 gantry angles")
print(f"least        at couch {min(counts, key=counts.get)}: {min(counts.values())}")
print(f"\\nat couch 90, the first few clear gantry angles: {safe_angles(90)[:12]}")
'''),
    ("md", """\
Couch 0, naturally — the gantry has the most room when the patient is square to it, and every
degree of kick takes some away. That is the bow-tie, read as numbers."""),

    ("md", """\
## The epilogue: not retyping all this

You have built the body by hand, which was the point. `maprt_workshop` has a helper that does it —
including the isocenter-shift arithmetic for interface corrections, which is fiddly and easy to
get backwards."""),
    ("code", '''\
from maprt_workshop import build_map_request

metadata, (low_body, high_body) = build_map_request(
    isocenter=(0.0, 0.0, 0.0),
    couch_buffer=2.0,          # NOTE: centimetres here — the helper converts
    patient_buffer=2.0,
    surface_id=body["PatientSurfaceId"],
    room_id=body["TreatmentRoomId"],
    room_scale="IEC_61217",
    patient_orientation="HFS",
)

print("it returns two bodies, low- and high-resolution:")
print("  ", low_body)
'''),
    ("md", """\
Note the helper takes buffers in **centimetres** and converts, because that is what a planner
types. The raw API takes millimetres. Mixing those up by a factor of ten is the single most
likely mistake in this whole workshop — which is why you built the body by hand first.

---

**Next:** [`06_beams_and_plans.ipynb`](06_beams_and_plans.ipynb) — checking real beams against
this map, two different ways, and what happens when they disagree."""),
]
