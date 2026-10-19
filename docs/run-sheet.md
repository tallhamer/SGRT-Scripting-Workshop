# Facilitator run-sheet

*For whoever is running the room. Not for attendees — give them
[`handout.md`](handout.md) instead.*

---

## The day before — do these, they are not optional

- [ ] **Open the Binder badge once and let it finish.** The first launch after a push builds the
      image and takes **5–15 minutes**. Do it the day before and the room gets the warm image in
      under a minute. Skip this and your first fifteen minutes are a progress bar.
- [ ] **Click one Colab badge** and confirm the first cell completes (~20 s).
- [ ] **Run `uv sync` on the room's machine** if there is one, so the download is cached.
- [ ] Check the venue's wifi actually allows `github.com` and `pypi.org`. If it does not, Binder
      and Colab are both dead and **local-only is your workshop** — say so up front.
- [ ] Print or share the handout.

## Pre-flight, five minutes before

```bash
cd SGRT-Scripting-Workshop
git pull
uv sync
uv run maprt-emulator
```

You want the banner showing `3 patients · 3 surfaces · 4 rooms · 1 recorded map`. If the data
line is wrong, you are in the wrong directory.

---

## Timing — a three-hour session

The per-notebook times in the index are *working* times for someone following along. Add your
own talking. This plan assumes about 3 h 15 m with two breaks.

| | | Minutes | Running |
| --- | --- | --- | --- |
| | **Opening** — why script this at all | 10 | 0:10 |
| 01 | Setup and the token | 15 | 0:25 |
| 02 | Connecting, and what goes wrong | 25 | 0:50 |
| 03 | Treatment rooms | 15 | 1:05 |
| | **Break** | 10 | 1:15 |
| 04 | Patient surfaces | 25 | 1:40 |
| 05 | **Clearance maps** — the centrepiece | 40 | 2:20 |
| | **Break** | 10 | 2:30 |
| 06 | Beams and plans | 30 | 3:00 |
| 08 | Capstone — demo, do not make them type it | 15 | 3:15 |

**Notebook 07 (robustness) is the one to cut** if you are behind. It is the most valuable for
people writing production code and the least valuable for people seeing the API for the first
time. Tell them it is there and worth an hour on their own.

**If you have only 90 minutes:** 01, 02, 05, and demo 08. That is the spine — authenticate,
understand the error model, get a map, see it used.

---

## What to demo live rather than let them read

**The 200-that-means-no (notebook 02).** Do this one on the projector before they try it.
Change one character of the token, send the ping, and read the status code out loud: *"two
hundred, OK"*. Then show `success: false`. The pause before anyone reacts is the point of the
whole morning.

**The bow-tie appearing (notebook 05).** Run the plot cell live. It is the moment the API stops
being JSON and becomes a thing physicists recognise. Then ask the room *why* gantry 0 and 180 are
flat bands before you explain it — someone will work out that the couch cannot matter when the
beam is vertical, and that explanation lands better from them than from you.

**The arc disagreement (notebook 06).** Build it as a question: "the appliance says this arc is
safe, the map says it collides — which is wrong?" Let them argue. Neither is wrong, and that is
the lesson. This is the single most likely real bug in anything they go on to write.

**The truncated map (notebook 07, or lift it into 05 if you are cutting 07).** Arm
`truncate-map`, parse it, and print `.shape`. `(180, 185)` instead of `(360, 185)`, no exception.
Let it sit.

---

## Where people actually get stuck

In rough order of how often you will see it.

| | What they will say | What is happening | Fix |
| --- | --- | --- | --- |
| 1 | "Address already in use" | Something holds port 8000 — usually a simulator they started earlier and forgot | `uv run maprt-emulator --port 8001`. **Nothing else to change** — the simulator records its port and the notebooks find it. |
| 2 | "It says EmulatorNotRunning" | They closed terminal 1, or they are running Jupyter from outside the repo | Restart it. The error message names which address it tried and where that came from — read it to them rather than guessing. |
| 3 | "`nodename nor servname provided`" | **A hospital proxy** routing even 127.0.0.1 through itself. Reads like DNS, is not | `os.environ['NO_PROXY'] = '127.0.0.1,localhost'`. The error message says this too. |
| 4 | "My numbers are all wrong" | Buffers in cm where the API wants mm | Factor of ten. Ask what units they typed. |
| 5 | "Nothing happens / it's frozen" | GetMap streaming, which takes a few seconds by design | Wait. Over ~30 s, check terminal 1. |
| 6 | "Everything broke after notebook 07" | A scenario left armed | Last cell of 07, or restart the simulator. |
| 7 | "jupyter: command not found" | They ran `uv sync --no-group workshop`, or an old uv | Plain `uv sync`. |

**Have a spare laptop with it already running.** Someone's machine will not cooperate and you
cannot debug corporate IT in a workshop.

---

## Framing — the things worth saying out loud

**Say early:** everything here talks to a simulator on their own machine. The surfaces are
synthetic, the maps are plausible rather than physical, nothing came from a patient. Say it once,
properly, and nobody spends the session wondering.

**Say when the maps appear:** the model responds to the inputs the way a real one does — widen a
buffer and collision grows, kick the couch and the band pinches — so their *reasoning* about what
they see will be right. The absolute numbers are invented. Both halves matter.

**Say at the capstone:** sixty lines. That is the pitch. Ten minutes a plan by hand, or a script
that does it while you read the next one.

**Do not oversell it as a QA tool.** It is a teaching simulator. Anyone who goes back and points
this code at a real appliance is doing clinical work and needs their own validation. Being clear
about that costs you nothing and protects everyone.

---

## Questions you will get

**"Can I use `requests` instead?"** Yes — anything that sets three headers and reads a body.
Notebook 02 shows the same ping in three libraries, one of them standard-library only. The
desktop application this came from uses Qt; Vision RT's own sample is C#.

**"Does this work against our real appliance?"** The requests do; the parsers in
`maprt_workshop` are ported from a live integration. You change the URL, the token, and add
`verify=False` for the self-signed certificate. What you do *not* get is any validation — that is
on them.

**"Why is the map not just JSON?"** Because it streams as it computes, over minutes, so a client
can show progress. That is also why its errors are JSON and its successes are not.

**"How accurate is the simulated map?"** It is not. Say so plainly. It is geometry chosen to
behave correctly, not physics. Point at `data/MapRT/README.md`.

**"Can we get real maps in here?"** Yes — `scripts/record_map.py --from-url` captures a real
appliance's response verbatim into `data/MapRT/local/maps/`, which is git-ignored. That is the honest
way to demo real data without putting it in a public repository.

---

## Afterwards

Point them at:

- **Notebook 07** if they are going to write anything real.
- `data/MapRT/README.md` for what the model is and is not.
- The repository itself — the simulator is ~1,500 lines and reading it is a decent way to
  understand the API.

The repo is public and nothing in it is patient-derived, so there is no reason they cannot take
it home.
