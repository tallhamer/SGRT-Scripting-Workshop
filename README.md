# MapRT Scripting Workshop

A **local simulator of the Vision RT MapRT API 2.0** plus a set of Jupyter notebooks that walk
you through scripting against it — the same calls, headers and wire formats you would use against
a real MapRT appliance, with no appliance, no patient data and no network.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/tallhamer/SGRT-Scripting-Workshop/HEAD?urlpath=lab/tree/notebooks/00_start_here.ipynb)

> **Not a medical device. Teaching use only.** The clearance maps this simulator returns are
> plausible, not physical. Not affiliated with or endorsed by Vision RT.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Nothing else — uv fetches the right Python itself.

```bash
git clone <this repo>
cd maprt-scripting-workshop
uv sync
```

Then **two terminals**, which is how the workshop is meant to be run — an appliance in one place,
your code in another, exactly like the real thing:

```bash
uv run maprt-sim        # terminal 1 — prints your API token. Leave it running.
uv run jupyter lab      # terminal 2
```

Open **[`notebooks/00_start_here.ipynb`](notebooks/00_start_here.ipynb)**. It checks your setup and
links to everything else.

### One terminal, if you would rather

```bash
uv run workshop-up      # starts the simulator, waits for it, then opens Jupyter Lab
```

Ctrl+C stops both. (Jupyter will ask you to confirm; the simulator shuts down once it exits.)

### About the token

The simulator generates a **new API token every time it starts** — a workshop credential should be
disposable. It reaches your notebook two ways, and you do not normally have to do anything:

- it is printed in the box the simulator shows at startup, and
- it is written to `.maprt_sim/server.json`, along with **the URL it is listening on**.

`connect()` finds that file by walking up from the notebook's directory, so a non-default port
works with no configuration. If you are running from outside the repository, paste the
`MAPRT_SIM_TOKEN=…` line the simulator printed.

## Running it without installing anything

If uv will not install, or you are on a locked-down machine, **Binder** runs the whole thing in
your browser — simulator included.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/tallhamer/SGRT-Scripting-Workshop/HEAD?urlpath=lab/tree/notebooks/00_start_here.ipynb)

Nothing to set up: the simulator starts with the session and the notebooks find it. You land on
the index.

What to know before relying on it:

- **The first launch after a push takes 5–15 minutes** while Binder builds the image. After that
  it is cached and starts in under a minute. **If you are teaching from this, open the badge once
  the day before** — then the room gets the warm image.
- Sessions **idle out after about 10 minutes** and are capped around 1–2 GB of memory.
- **Nothing is saved.** Close the tab and your edits are gone. Download anything you want to keep.
- Binder is free, shared infrastructure. It is occasionally slow or full. Have a fallback.

The simulator's API docs are reachable in a session at `<your-binder-url>/proxy/8000/docs`.

**Recommended order:** local first (it is the only one that matches a real site), Binder as the
no-install fallback, Google Colab if Binder is busy.

## Troubleshooting

Everything in this table is something that actually went wrong while the workshop was being
built and tested.

| Symptom | What is happening | Fix |
| --- | --- | --- |
| `Address already in use` when starting the simulator | Something else holds port 8000 — often another copy of this simulator. | `uv run maprt-sim --port 8001`. **You do not need to tell the notebooks** — the simulator records its port and they find it. |
| `SimulatorNotRunning: No API token found` | No `.maprt_sim/` anywhere above the notebook. The simulator is not running, or you are outside the repository. | Start it: `uv run maprt-sim`. If you are deliberately elsewhere, `os.environ['MAPRT_SIM_TOKEN'] = '…'`. |
| `SimulatorNotRunning: … came from .maprt_sim/server.json … stale file` | The simulator ran and has since stopped. | Restart it. The message tells you which address it tried and where that came from. |
| `ConnectError: nodename nor servname provided` | A corporate/hospital **proxy** is set, and it is trying to route even `127.0.0.1` through itself. The error reads like DNS and is not. | `os.environ['NO_PROXY'] = '127.0.0.1,localhost'`, then re-run. `connect()` spots this and says so. |
| macOS asks to allow incoming connections | The firewall prompt for a new listening process. | Allow it, or ignore it — the simulator binds `127.0.0.1` only and nothing outside your machine can reach it either way. |
| A `GetMap` cell seems to hang | It streams over a few seconds by design — a real appliance takes **minutes**. | Wait. Over ~30 s, interrupt the kernel and check terminal 1. `--map-seconds 0` removes the delay. |
| Everything fails after notebook 07 | You left a fault armed. | Run the last cell of notebook 07, or `POST /sim/scenario` with `{"name": "ok"}`, or restart the simulator. |
| `jupyter: command not found` from `workshop-up` | The notebook dependencies are not installed. | `uv sync` — it installs Jupyter. If you used `--no-group workshop`, that is why. |
| Notebook edits keep disappearing | **The notebooks are generated** — see *Development* below. | Edit `scripts/notebook_content/`, then `uv run python scripts/build_notebooks.py`. |
| Binder session died mid-workshop | Idle timeout, or the memory cap. | Relaunch from the badge. Nothing was saved, so start the notebook again. |
| Binder is building and building | First launch after a push rebuilds the image. | Wait it out, or work locally. Pre-warm by opening the badge a day early. |

The simulator's own state is readable at `/sim/state`, and its interactive API docs at `/docs`.
Neither exists on a real appliance.

## What's here

| Path | Contents |
| --- | --- |
| `src/maprt_sim` | The FastAPI simulator: the seven REST endpoints, Bearer auth, the streaming collision-map format, fault injection |
| `src/maprt_workshop` | The client side: response parsing, request building, an HTTP client, an OBJ reader, beam-vs-map checking, plotting |
| `data/` | The catalog the simulator serves — rooms, patients, surfaces, recorded maps, a synthetic RT Plan |
| `notebooks/` | The workshop, in order. Start at `00_start_here.ipynb`. |
| `scripts/` | Data generators, and the builders the notebooks and Binder requirements are generated from |
| `binder/` | The Binder configuration — generated requirements, and the build/start hooks |

`src/maprt_workshop`'s parsers and request builders are ported from a live-verified MapRT
integration, and the simulator is written to satisfy *those* parsers — so what you practice here is
what works against a real appliance.

## The workshop

| | Notebook | Covers |
| --- | --- | --- |
| 00 | **Start here** | The index, and a check that everything is running |
| 01 | Setup and the token | Finding the appliance, authenticating, one call by hand |
| 02 | Connecting, and what goes wrong | The four kinds of failure — and why a `200` can mean *no* |
| 03 | Treatment rooms | Why production code keys on the GUID, never the machine name |
| 04 | Patient surfaces | Fetching a mesh, decoding it, and the metadata it does *not* carry |
| 05 | Clearance maps | The streaming wire format, parsed by hand then plotted |
| 06 | Beams and plans | Two ways to check a beam, and where they legitimately disagree |
| 07 | When things go wrong | Timeouts, throttling, truncated data — armed on purpose |
| 08 | Capstone: plan QA | An RT Plan in, a pass/fail report out, in about 60 lines |

About three hours end to end.

## Development

```bash
uv run pytest                      # everything, including the notebooks
uv run pytest -m "not slow"        # skip the notebook execution while iterating
uv run ruff check
```

`binder/requirements.txt` is generated too — `uv run python scripts/export_requirements.py` —
so a Binder session installs the same locked versions `uv sync` does. CI checks both.

**The notebooks are generated.** Their content lives in `scripts/notebook_content/` as readable
Python; `uv run python scripts/build_notebooks.py` writes the `.ipynb` files. This keeps them free
of committed outputs and makes their diffs readable — but it means **an edit made in Jupyter and
not mirrored into the content module will be overwritten by the next build.** CI checks the two
are in sync.

`uv sync` installs the notebook dependencies (matplotlib, pandas, plotly, pydicom, Jupyter) as
well as the library, so the quickstart above is one command. `uv sync --no-group workshop` gives
the lean install for a deployment that only needs to serve the API.

## License

MIT — see [LICENSE](LICENSE).
