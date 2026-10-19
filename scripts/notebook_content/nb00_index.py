"""00 — Start here. The index every other notebook hangs off."""

from ._common import BANNER, REPO_URL, bootstrap_cells

CELLS = [
    ("md", f"""\
# MapRT Scripting Workshop

*Scripting against the Vision RT MapRT API 2.0 — without an appliance, without patient data, and
without a network.*

{BANNER}

This is the table of contents. Work through the notebooks in order; each one assumes the one
before it. **Start by making sure the simulator is running** — the cell below tells you."""),

    *bootstrap_cells(),

    ("md", """\
## Is everything running?

Run this cell. If it is happy, open notebook 01 and begin."""),
    ("code", '''\
from maprt_workshop import EmulatorNotRunning, connect

try:
    maprt = connect()
except EmulatorNotRunning as problem:
    print("NOT READY\\n")
    print(problem)
else:
    rooms = maprt.get_treatment_rooms()
    print("Ready.\\n")
    print(f"  Simulator   {maprt.api_url}")
    print(f"  API version {maprt.get_api_version()}")
    print(f"  Rooms       {len(rooms)}")
    print("\\n  Open 01_setup_and_token.ipynb to begin.")
'''),

    ("md", """\
## The notebooks

| | Notebook | What you will be able to do afterwards | Time |
| --- | --- | --- | --- |
| 01 | [**Setup and the token**](01_setup_and_token.ipynb) | Find the appliance, authenticate, and make one call by hand | 10 min |
| 02 | [**Connecting, and what goes wrong**](02_connect_and_errors.ipynb) | Tell the four kinds of failure apart — and know why a `200` can mean *no* | 20 min |
| 03 | [**Treatment rooms**](03_treatment_rooms.ipynb) | List rooms, resolve one by name, and know why production code uses the GUID | 15 min |
| 04 | [**Patient surfaces**](04_patient_surfaces.ipynb) | Fetch a patient's mesh, decode it, and plot it | 25 min |
| 05 | [**Clearance maps**](05_clearance_maps.ipynb) | Request a map, parse the streaming format, and read the picture | 35 min |
| 06 | [**Beams and plans**](06_beams_and_plans.ipynb) | Check beams two different ways, and know when they disagree | 30 min |
| 07 | [**When things go wrong**](07_robustness.ipynb) | Write a client that survives timeouts, throttling and truncated data | 25 min |
| 08 | [**Capstone: plan QA**](08_capstone_plan_qa.ipynb) | Read an RT Plan and check every beam, end to end, in about 60 lines | 30 min |

Roughly three hours end to end. Notebooks 01–05 are the core; 06–08 build on them.

> The links above open in JupyterLab and on Binder. On **Google Colab** they will not — Colab has
> no shared file browser — so use these instead, one per notebook:
>
> [01](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/01_setup_and_token.ipynb) ·
> [02](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/02_connect_and_errors.ipynb) ·
> [03](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/03_treatment_rooms.ipynb) ·
> [04](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/04_patient_surfaces.ipynb) ·
> [05](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/05_clearance_maps.ipynb) ·
> [06](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/06_beams_and_plans.ipynb) ·
> [07](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/07_robustness.ipynb) ·
> [08](https://colab.research.google.com/github/tallhamer/SGRT-Scripting-Workshop/blob/main/notebooks/08_capstone_plan_qa.ipynb)
>
> Each one installs the workshop and starts the simulator in its first cell, so they work
> independently — but **the first cell takes about 20 seconds**, every time, in every notebook.
> Colab gives each one a fresh machine."""),

    ("md", """\
## The seven requests, on one page

Everything in this workshop is these. Keep this table open while you work.

| | Request | What it gives you |
| --- | --- | --- |
| 1 | `GET /integration/ping` | The API version. Proves you are connected and authenticated. |
| 2 | `GET /integration/rooms` | Every treatment room configuration, each with a **GUID** and a machine name. |
| 3 | `GET /integration/rooms/{machineName}` | One room's GUID — *if* the name matches exactly one. |
| 4 | `GET /integration/patients/{patientId}/surfaces` | The surfaces acquired for a patient, with timestamps. |
| 5 | `GET /integration/surfaces/{surfaceId}` | One surface mesh, base64-encoded OBJ. |
| 6 | `POST /integration/GetMap` | A clearance map. **Streaming text, not JSON.** |
| 7 | `POST /integration/GetBeamDeliveryStatus` | Per-beam deliverable / not, for the control points you send. |

Every one of them except `GetMap` answers with the same five-key envelope:

```json
{"data": …, "errorData": null, "success": true, "errorCode": null, "errorCodeType": "NoErrorCodes"}
```

And every one of them carries the same three headers:

```python
{"Content-Type": "application/json",
 "Authorization": f"Bearer {token}",
 "User-Agent": "VisionRT.Integration.Saturn/2.0.your-script-name"}
```"""),

    ("md", """\
## The two things people get wrong

**A `200` does not mean it worked.** A bad token, an unlicensed feature and an ambiguous room
name all come back as `200 OK` with `success: false` in the body. Only a *malformed request* gets
a 4xx. `raise_for_status()` on its own will let every one of those through. → notebook 02

**`GetMap` is not JSON.** It streams plain text: a header line giving the sampling, then one
`couch,gantry,isOK` line per angle pair, then `DONE`. Its *errors* are JSON, which is why a client
has to look at the body before deciding how to parse it. → notebook 05"""),

    ("md", f"""\
## If something is broken

| Symptom | Fix |
| --- | --- |
| `EmulatorNotRunning` | Start it: `uv run maprt-emulator` in another terminal, and leave it running. |
| `No API token found` | Same — the token file appears when the simulator starts. |
| `Address already in use` | Something else holds port 8000. `uv run maprt-emulator --port 8001`, then set `MAPRT_EMULATOR_URL` to match. |
| A cell hangs | `GetMap` takes a few seconds by design. If it is longer than ~30 s, interrupt the kernel and check the simulator's terminal. |
| Everything fails after notebook 07 | You probably left a fault armed. Run `POST /sim/scenario` with `{{"name": "ok"}}`, or just restart the simulator. |

The simulator's own state is always readable at
[`{{BASE}}/sim/state`](http://127.0.0.1:8000/sim/state), and its interactive API docs are at
[`{{BASE}}/docs`](http://127.0.0.1:8000/docs). Neither of those exists on a real appliance — they
are the simulator's own, and notebook 02 explains why that matters.

Source and issues: {REPO_URL}"""),
]
