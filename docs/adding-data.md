# Adding data to the MapRT Emulator

Everything the emulator serves comes out of one folder, `data/MapRT/`. Adding data is a file
drop plus a line of JSON — no code change, and no restart flag beyond restarting the server.

(`data/` itself holds one folder per Vision RT product; this guide is about MapRT's. See
[`data/README.md`](../data/README.md).)

**Check your work at any point:**

```bash
uv run maprt-emulator --check-data
```

That loads everything the server would, reports what it found, and names the problems that are
*not* fatal but are almost always mistakes. It does not start a server.

---

## Where to put it: `data/MapRT/` or `data/MapRT/local/`

| | |
| --- | --- |
| **`data/MapRT/`** | Tracked by git. **Synthetic only.** This is what everyone who clones the repository gets. |
| **`data/MapRT/local/`** | **Git-ignored.** Real exported surfaces, real recorded maps, real plans. |

`data/MapRT/local/` **overlays** `data/MapRT/`:

- a `rooms.json` or `patients.json` there **replaces** the public one entirely
- a surface or map there **wins** over one of the same name in `data/MapRT/`

That is the mechanism that lets you demo real data without it ever becoming a commit candidate.
If the data came off a clinical system, it goes in `data/MapRT/local/`. There is no second judgement
call to make.

A third option: `--data-dir /somewhere/else` points the emulator at an entirely separate folder,
which is useful for keeping a per-site catalog outside the repository.

---

## Treatment rooms

Edit `data/MapRT/rooms.json`. It is a list.

```json
{
  "id": "4d1f6e02-7c3b-4a19-9f55-2b8e0c71a3d7",
  "machineName": "TrueBeam2",
  "name": "TB2 IEC 61217",
  "coordinateSystem": "IEC_61217"
}
```

| field | |
| --- | --- |
| `id` | A **GUID**, and it must be unique. This is what `GetMap` keys on. Generate one with `python -c "import uuid; print(uuid.uuid4())"`. |
| `machineName` | Max 16 characters. **Need not be unique** — see below. |
| `name` | The configuration's display name. |
| `coordinateSystem` | `IEC_61217`, `Native`, `IEC_60601_2_1`, `IEC_60601_NW`, `OBI_60601_1_5` or `OBI_60601_1_6`. |

**Sharing a `machineName` deliberately is useful.** Two rooms with the same machine name make
`GET /integration/rooms/{machineName}` return `DuplicateKey` — which is what a real site looks
like, and the reason production code keys on the GUID. The shipped data does this with
`TrueBeam`. `--check-data` reports it as a note, not a problem.

Sharing an **`id`** is an error: `GetMap` could then resolve to either room, arbitrarily.

---

## Patients and surfaces

Two steps: drop the mesh in, then list it.

**1. Put the `.obj` in `data/MapRT/surfaces/`, named for its surface id:**

```
data/MapRT/surfaces/dad7394f-6893-4ce3-96ed-8bc3091cf4c3.obj
```

**2. Reference it from `data/MapRT/patients.json`:**

```json
{
  "ANON001": [
    {"id": "dad7394f-6893-4ce3-96ed-8bc3091cf4c3",
     "timeStamp": "2026-04-24T16:57:35",
     "timeZone": "Mountain Standard Time"}
  ],
  "ANON003": []
}
```

| field | |
| --- | --- |
| `id` | Must match the filename stem exactly. |
| `timeStamp` | **UTC**, ISO 8601. The API sorts "newest first" on this. |
| `timeZone` | The zone it was acquired *in*, as a name — not an offset. |

A patient with **`[]`** is legitimate and worth keeping: the API returns an empty list at
`success: true`, which is a different answer from an unknown patient id, and a client has to
handle both. `ANON003` exists for exactly that.

### Making a synthetic surface

```bash
uv run python scripts/make_synthetic_surface.py \
    data/MapRT/surfaces/$(python -c "import uuid; print(uuid.uuid4())").obj --seed 42
```

`--seed` varies the body proportions, so each patient gets a distinguishable surface *and* a
distinguishable clearance map. `--stations` and `--around` control the mesh density; the default
is ~19,200 faces and about 550 KB.

### Using a real exported surface

A real MapRT export is ASCII OBJ with a comment banner and non-standard `ps`/`fs` count lines —
the reader handles all of that. But a real export is also **patient-derived and large** (the one
this project was built from is 19 MB, 265,857 vertices).

```bash
mkdir -p data/MapRT/local/surfaces
cp /path/to/export.obj data/MapRT/local/surfaces/<surface-guid>.obj
```

Then list it in `data/MapRT/local/patients.json`, which replaces the public one. Keep a copy of every
public patient you still want, because the overlay replaces rather than merges.

---

## Clearance maps

The emulator computes a plausible map for any request. A **recorded** map makes it serve real
bytes instead — which is the only way to show anyone a map that came off a linac.

### Recording from a real appliance

```bash
uv run python scripts/record_map.py \
    --from-url https://maprt.yoursite.local:5000 --token "$MAPRT_TOKEN" \
    --surface <surface-guid> --room <room-guid> \
    --isocenter 0 0 0 --couch-buffer 20 --patient-buffer 20 \
    --out data/MapRT/local/maps
```

The response body is written verbatim, so what the emulator later serves is exactly what the
appliance sent. **Use `--out data/MapRT/local/maps`** — a real recording is patient-derived.

### Snapshotting the model

For test data, or to exercise the recorded path without an appliance:

```bash
uv run python scripts/record_map.py --surface <guid> --room <guid> --name demo_hfs_lowres
```

These are labelled as snapshots in their `note` field, and the label is not decoration — a
student who cannot tell invented data from measured data has learnt the wrong thing.

### By hand

Write the raw body to `data/MapRT/maps/<name>.txt` and add an entry to `data/MapRT/maps/index.json`:

```json
{
  "file": "demo_hfs_lowres.txt",
  "surfaceId": "<must match a surface in patients.json>",
  "roomId": "<must match a room in rooms.json>",
  "patientPosition": "HFS",
  "couchBuffer": 20.0,
  "patientBuffer": 20.0,
  "isocenter": [0.0, 0.0, 0.0],
  "highResolution": false,
  "note": "where this came from"
}
```

The body must be the GetMap wire format — a `couch_samples,gantry_samples` header, one
`couch,gantry,isOK` line per pair, then `DONE`. `--check-data` verifies the triple count matches
the header and that the terminator is there.

### How a request finds it

| `X-Emulator-Map-Source` | |
| --- | --- |
| `recorded` | Surface, room, resolution, position, both buffers and isocenter (to 0.5 mm) all matched. |
| `recorded-nearest` | Same surface, room and resolution; **different isocenter**. The closest recording was served — so it is not an answer to the question asked. |
| `synthetic` | Nothing matched; the model computed one. |

`--map-source recorded` makes the emulator refuse to invent one, which is what you want for a
demo where every map must be real.

---

## RT Plans

Plans are not served by the API — the notebooks read them from disk. Put them in `data/MapRT/plans/`.

```bash
uv run python scripts/make_synthetic_plan.py data/MapRT/plans/ANON002_plan.dcm \
    --patient-id ANON002 --position HFS
```

For a real plan, use `data/MapRT/local/plans/` and point the notebook at it. Two things must line up or
a notebook will fail partway:

- the plan's **`PatientID`** must exist in `patients.json`
- each beam's **`TreatmentMachineName`** must match a `machineName` in `rooms.json`

`--check-data` warns about both.

---

## A worked example: adding a whole new patient

```bash
# 1. Make up ids.
SURFACE=$(python -c "import uuid; print(uuid.uuid4())")

# 2. Generate a surface.
uv run python scripts/make_synthetic_surface.py data/MapRT/surfaces/$SURFACE.obj --seed 7

# 3. List it. (Edit patients.json by hand, or:)
python - <<PY
import json, pathlib
p = pathlib.Path("data/MapRT/patients.json")
catalog = json.loads(p.read_text())
catalog["ANON004"] = [{"id": "$SURFACE",
                       "timeStamp": "2026-10-15T09:30:00",
                       "timeZone": "Mountain Standard Time"}]
p.write_text(json.dumps(catalog, indent=2) + "\n")
PY

# 4. Check it.
uv run maprt-emulator --check-data

# 5. Restart the emulator and try it.
uv run maprt-emulator
```

```python
maprt.get_patient_surfaces("ANON004")
```

---

## What `--check-data` looks for

**Errors** — these produce wrong behaviour. Some of them will not stop the emulator starting,
which makes them worse, not better:

- a data file missing, unreadable, or missing a required field
- two rooms sharing a GUID
- a surface that does not parse as an OBJ mesh
- a recorded map with no `DONE`, or whose triple count disagrees with its header

**Warnings** — it will run, but this is probably not what you meant:

- an `.obj` in `surfaces/` that no patient references, so it can never be served
- a recorded map whose `surfaceId` or `roomId` is not in the catalog, so it can never match
- a patient id over 64 characters, or a machine name over 16
- two surfaces for one patient with the same `timeStamp`
- an RT Plan whose patient or machine is not in the catalog
- a surface with implausibly few vertices

**Notes** — worth seeing, not a problem: shared machine names, patients with no surfaces.

---

## Two rules worth repeating

**Nothing patient-derived goes in `data/MapRT/`** — or anywhere in `data/` outside a `local/`
folder. It is a public repository. `data/MapRT/local/` is git-ignored and overlays it; that is
what it is for.

**Label invented data as invented.** The `note` field on a recorded map exists so nobody mistakes
a model snapshot for a measurement. The emulator reports its own invented error codes at
`/emulator/state` for the same reason.
