"""03 — Treatment rooms."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("03", "Treatment rooms",
                  "Two ways to find a room, and why only one of them is safe.", "15 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## What a treatment room is here

Not a room — a **configuration**. The appliance holds a scan of a couch and a gantry, and that
scanned geometry is what a clearance map is computed against.

One physical linac often has several of them. A different couch top, an accessory mounted, a
different immobilisation setup: each needs its own scanned configuration, and each is a separate
"treatment room" as far as the API is concerned.

That single fact is the whole of this notebook."""),

    ("md", """\
## Listing them

`GET /integration/rooms`. No parameters."""),
    ("code", '''\
import httpx2

url = maprt.api_url + "/integration/rooms"
headers = dict(maprt.headers)

response = httpx2.get(url, headers=headers)
response.status_code
'''),
    ("md", "Same envelope as always. Check `success` before anything else:"),
    ("code", '''\
envelope = response.json()
envelope["success"]
'''),
    ("md", "`data` is a list. Look at **one** entry first, to learn the shape:"),
    ("code", '''\
rooms = envelope["data"]
rooms[0]
'''),
    ("md", """\
Four fields:

| field | what it is |
| --- | --- |
| `id` | a **GUID**. Unique. This is what `GetMap` wants. |
| `machineName` | the treatment machine, max 16 characters. **Not unique.** |
| `name` | the configuration's display name, as Vision RT's own interface shows it. |
| `coordinateSystem` | which couch coordinate convention this room's angles are reported in. |

Now the whole list:"""),
    ("code", '''\
import pandas as pd

table = pd.DataFrame(rooms)
table
'''),

    ("md", """\
## Look carefully at `machineName`

Two of those rows share one. That is not a mistake in the test data — it is what a real site looks
like, and it is the trap this notebook exists for."""),
    ("code", '''\
table["machineName"].value_counts()
'''),
    ("md", "And the GUIDs, by contrast:"),
    ("code", '''\
print("rooms          :", len(rooms))
print("unique names   :", table["machineName"].nunique())
print("unique GUIDs   :", table["id"].nunique())
'''),

    ("md", """\
## The other way to find a room

`GET /integration/rooms/{machineName}` resolves a *single* room by its machine name. It looks like
the convenient one. It is the one to be careful with.

Start with a name that matches exactly one room:"""),
    ("code", '''\
response = httpx2.get(maprt.api_url + "/integration/rooms/TrueBeam2", headers=headers)
response.json()
'''),
    ("md", "`data` is the GUID, as a bare string. Good. Now a name that matches **nothing**:"),
    ("code", '''\
response = httpx2.get(maprt.api_url + "/integration/rooms/NoSuchMachine", headers=headers)
response.json()
'''),

    ("md", """\
**Read that again.** `success` is `true`. There is no error. And `data` is:

```
00000000-0000-0000-0000-000000000000
```

An all-zeros GUID. "No match" is reported as a **successful call with a null answer**, not as a
failure. A client that only checks `success` will carry that GUID straight into a `GetMap`
request and spend a while wondering why nothing works.

So: check for it."""),
    ("code", '''\
EMPTY_GUID = "00000000-0000-0000-0000-000000000000"

def find_room(machine_name):
    envelope = httpx2.get(maprt.api_url + f"/integration/rooms/{machine_name}",
                          headers=headers).json()
    if not envelope["success"]:
        raise RuntimeError(f"{envelope['errorCodeType']}: {envelope['errorCode']}")
    room_id = envelope["data"]
    if room_id == EMPTY_GUID:
        raise LookupError(f"no treatment room is configured for machine {machine_name!r}")
    return room_id


find_room("TrueBeam2")
'''),
    ("code", '''\
try:
    find_room("NoSuchMachine")
except LookupError as problem:
    print("caught:", problem)
'''),

    ("md", """\
## And the third case

A name that matches *more than one* room. The appliance cannot pick for you, so it refuses."""),
    ("code", '''\
response = httpx2.get(maprt.api_url + "/integration/rooms/TrueBeam", headers=headers)

print("status:", response.status_code)
response.json()
'''),
    ("md", """\
`DuplicateKey`, at HTTP 200 — a negative result, exactly as notebook 02 described. The C# client
raises this as an `AmbiguousMatchException`; over REST it arrives as an error code.

So `GET /rooms/{machineName}` has **three** outcomes and they are all different:

| | `success` | `data` | meaning |
| --- | --- | --- | --- |
| one match | `true` | the GUID | what you wanted |
| no match | `true` | all-zeros GUID | not configured |
| several matches | `false` | `null` | `DuplicateKey` — ambiguous |

Our `find_room` above handles all three. That is three branches for what looks like a one-line
lookup, which is why production code generally does not use this endpoint at all."""),

    ("md", """\
## What production code does instead

List the rooms once. Let a human pick. Key on the GUID from then on.

The GUID is unique, it is stable, and it is what `GetMap` and `GetBeamDeliveryStatus` actually
take. The machine name is for showing people."""),
    ("code", '''\
rooms = maprt.get_treatment_rooms()          # [(name, id, coordinate_system), ...]

for index, (name, room_id, coordinate_system) in enumerate(rooms):
    print(f"  [{index}] {name:<20} {coordinate_system:<12} {room_id}")

# In an application this is a dropdown. Here, pick one.
chosen_name, ROOM_ID, _coordinate_system = rooms[0]
print(f"\\nusing: {chosen_name}  ->  {ROOM_ID}")
'''),

    ("md", """\
## One more field: `coordinateSystem`

Notice the rooms do not all agree. One of them reports `Native`."""),
    ("code", '''\
table[["name", "machineName", "coordinateSystem"]]
'''),
    ("md", """\
A room reports the couch coordinate convention Vision RT's own user interface displays it in. The
specification supports six:

| value | |
| --- | --- |
| `Native` | Vision RT's internal convention |
| `IEC_61217` | **what DICOM uses, and what the clearance map comes back in** |
| `IEC_60601_2_1`, `IEC_60601_NW` | other IEC conventions |
| `OBI_60601_1_5`, `OBI_60601_1_6` | vendor variants |

For this workshop everything is IEC 61217 and you can ignore the field. In the clinic you cannot:
the conversions are vendor-specific and live in a separate Vision RT document. If you are
comparing an angle from the API against an angle from a planning system or a console readout,
**check which convention each one is in before you trust the comparison.**

The emulator refuses angles in anything but IEC 61217 rather than silently converting them
wrongly — see notebook 06."""),

    ("md", """\
## Your turn

Write `resolve_room(machine_name)` that returns a GUID, and handles all three outcomes with a
*useful* message for each. Then call it for `TrueBeam2`, `Halcyon`, `TrueBeam`, and `Nope`.

What should happen for the ambiguous one? There is no single right answer — think about what a
planner could actually do about it."""),
    ("code", '''\
# Your turn.
def resolve_room(machine_name):
    ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
from maprt_workshop import MapRTApiError

def resolve_room(machine_name):
    """A room GUID, or a message a planner can act on."""
    try:
        envelope = maprt.get_treatment_room(machine_name)
    except MapRTApiError as problem:
        if problem.error_code == "DuplicateKey":
            # Ambiguous. Nobody can fix this from the name alone, so fall back to the list and
            # show the alternatives — the planner knows which configuration they meant.
            options = [name for name, _id, _cs in maprt.get_treatment_rooms()]
            raise LookupError(
                f"{machine_name!r} matches several room configurations. "
                f"Pick one by name: {options}") from problem
        raise

    if envelope["data"] == EMPTY_GUID:
        raise LookupError(f"no room is configured for machine {machine_name!r}. "
                          f"Check the name against /integration/rooms.")
    return envelope["data"]


for machine in ("TrueBeam2", "Halcyon", "TrueBeam", "Nope"):
    try:
        print(f"{machine:<12} -> {resolve_room(machine)}")
    except LookupError as problem:
        print(f"{machine:<12} -> {problem}")
'''),

    ("md", """\
---

**Keep `ROOM_ID`.** The next notebooks need it, along with a surface id.

**Next:** [`04_patient_surfaces.ipynb`](04_patient_surfaces.ipynb) — getting a patient's mesh, and
the trap in what the bytes do *not* tell you."""),
]
