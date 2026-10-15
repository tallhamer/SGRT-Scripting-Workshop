# The simulator's data catalog

`maprt_sim` serves everything in here. Adding data is a file drop plus a line of JSON — no code
change, no restart flag beyond restarting the server.

> **Adding your own rooms, patients, surfaces, maps or plans?**
> → **[`docs/adding-data.md`](../docs/adding-data.md)** is the step-by-step guide.
> Then check it with `uv run maprt-sim --check-data`.

This file describes what is *here* and why.

| File | What it is |
| --- | --- |
| `rooms.json` | Treatment room configurations: `id` (GUID), `machineName`, `name`, `coordinateSystem` |
| `patients.json` | `{"<patientId>": [{"id", "timeStamp", "timeZone"}, …]}` — which surfaces each patient has |
| `surfaces/<id>.obj` | The mesh served for that surface id, as ASCII OBJ |
| `maps/` | Recorded `GetMap` response bodies plus `index.json` keyed by the setup each was recorded for |
| `plans/` | A synthetic DICOM RT Plan for the capstone notebook |

## What the shipped data is set up to teach

- **Two rooms share the machine name `TrueBeam`.** `GET /integration/rooms/TrueBeam` therefore
  cannot resolve to one room and returns `DuplicateKey` — which is exactly what a real site looks
  like, and why production code keys on the room GUID instead of the name.
- **`TrueBeam2` matches exactly one room**, so there is a working single-room lookup to compare.
- **`ANON003` has no surfaces.** The patient is known; nobody has acquired a surface. That comes
  back as an empty list at `success: true` — *not* an error — and a client has to tell it apart
  from an unknown patient id.
- **`ANON001` has two surfaces** at different dates, so "use the most recent one" has something
  to choose between.

The meshes here are **synthetic**. No patient data is in this repository.

## Clearance maps

`GetMap` resolves a request in three steps, and reports which one it took in the
`X-Sim-Map-Source` response header:

| Header value | Meaning |
| --- | --- |
| `recorded` | Every keyed field matched an entry in `maps/index.json`. These are real bytes from a real response. |
| `recorded-nearest` | Same surface, room and resolution, different isocenter — the closest recording was served. The answer is **not** for the setup you asked about. |
| `synthetic` | Nothing matched, so `maprt_sim.mapgen` computed one. |

The map shipped here is a **synthetic snapshot** — the simulator's own model, saved to a file so
the recorded code path is exercised out of the box. Its `note` field says so, and so does the
header it is served under. It is not a measurement.

To record a real one:

```bash
uv run python scripts/record_map.py --from-url https://maprt:5000 --token "$TOKEN"     --surface <guid> --room <guid> --out data/local/maps
```

`data/local/maps/` is git-ignored and is read *before* this directory, so a real recording takes
over from the snapshot without deleting it. Write real recordings there, never here.

## The synthetic RT Plan

`plans/ANON001_plan.dcm` is a real, parseable RT Plan whose contents are invented. The capstone
notebook reads it with `pydicom` the way a QA script would — patient id, isocenter, patient
position, and each beam's gantry and couch angles — because the point is practising against the
tag layout a planning system actually emits, not against a dictionary someone typed out.

Its beam list is chosen so the capstone's pass/fail table has something to say:

| # | Beam | What it is there for |
| --- | --- | --- |
| 1 | `SETUP AP` | A setup field, so the `TreatmentDeliveryType` distinction appears |
| 2-5 | `AP`, `LAO`, `LT LAT`, `PA` | Ordinary static beams that pass |
| 6 | `RT LAT KICK` | A lateral at couch 90 — **fails**, both ways |
| 7 | `VMAT CW` | A full arc that passes |
| 8 | `VMAT CC KICK` | An arc at couch 45 that **fails the map sweep but passes GetBeamDeliveryStatus**, because only its start control point is sent |

Beam 8 is the one to dwell on: the two ways of asking disagree, and both are right. See
`notebooks/05`.

Regenerate with `uv run python scripts/make_synthetic_plan.py data/plans/ANON001_plan.dcm`. It is
not a deliverable plan and no planning system should be asked to open it.

## What the synthetic model is and is not

`maprt_sim.mapgen` is **not a collision engine and its output is not physics.** It is a small
geometric model — gantry head as a sphere, couch as a board, the patient as their actual
decimated surface mesh — chosen so the map *responds to a request the way a real one does*:

- widen a buffer and the collision region grows, monotonically;
- kick the couch and the safe gantry band pinches into the bow-tie a planner recognises;
- gantry 0 and 180 are clear and **independent of the couch angle**, because the source offset
  carries `sin(gantry)` on both couch-dependent axes;
- two patients get different maps because their bodies are different shapes, not because of a
  hash of their id.

So you can reason about what you see and be right about the reasoning. Do not read anything into
the absolute numbers. Not modelled: the couch pedestal and support arm, which are a real source
of collisions at large couch kicks — the simulator is more optimistic than reality there.

## Using your own exported data

`data/local/` is git-ignored and overlays this directory:

- `data/local/rooms.json` or `patients.json` **replaces** the file here.
- `data/local/surfaces/<id>.obj` **wins over** a file of the same name here.

That is where real exported surfaces and recorded clearance maps go on a machine that has them,
so patient-derived data can never become a commit candidate. Point the server somewhere else
entirely with `--data-dir`.
