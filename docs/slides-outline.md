# Slide outline

*One heading per slide. The bullets are what goes on it; the italics are what you say.*

Built for ~25 minutes of talking spread across a three-hour hands-on session — not a lecture.
Most slides exist to frame the notebook that follows. Cut anything that is already on the
handout.

---

## 1 — Title

**Scripting the MapRT API**
*A clearance map, from a plan file, in sixty lines*

*Your name, department, date.*

---

## 2 — What we are doing today

- A **simulator** of the MapRT API, running on your laptop
- Nine notebooks: authenticate → rooms → surfaces → **clearance maps** → beams → a plan QA script
- No appliance, no patient data, no network

> **Not a medical device. Teaching only.**

*Say the disclaimer properly, once, now. Then nobody spends the session wondering.*

---

## 3 — Why script this at all

Checking one plan by hand:

> open the plan · read the isocenter · note every gantry and couch angle · find the patient's
> surface · pick the room · run a map · check each beam

**Ten minutes. Nobody does it twice.**

*Pause there. Everyone in the room has either done this or avoided doing it.*

---

## 4 — The same thing, scripted

```python
report, map_data, beams = check_plan("plan.dcm")
```

- Every beam, every time
- Buffer sensitivity for free — *at what margin does this beam start to fail?*
- Questions you cannot ask by hand: **what couch angle would make this arc work?**

*That last one is the real pitch. The appliance tells you whether your plan works. Only a map in
your hands tells you what would.*

---

## 5 — What MapRT actually is

```
  CT room                MapRT appliance              you
 ─────────              ───────────────             ──────
 surface scan  ──────▶   patient surfaces
                         room geometry      ◀────── HTTPS + a token
                         clearance maps     ──────▶ gantry × couch, safe/collision
```

- A server on the clinical network
- Plain HTTPS. **Any client that can set three headers will do.**

---

## 6 — Three headers, every call

```python
{"Content-Type":  "application/json",
 "Authorization": f"Bearer {token}",
 "User-Agent":    "VisionRT.Integration.Saturn/2.0.my-script"}
```

- The token is a **shared secret**, issued per appliance. Not a login.
- Self-signed certificate → `verify=False`

*Right for an appliance on a clinical VLAN. Wrong for anything on the open internet. Know which
one you are doing.*

---

## 7 — Seven requests. That is the whole API.

| | |
| --- | --- |
| `GET /integration/ping` | are you there |
| `GET /integration/rooms` | which rooms |
| `GET /integration/rooms/{machineName}` | this one, by name |
| `GET /integration/patients/{patientId}/surfaces` | what has this patient got |
| `GET /integration/surfaces/{surfaceId}` | the mesh |
| `POST /integration/GetMap` | **the clearance map** |
| `POST /integration/GetBeamDeliveryStatus` | are these beams deliverable |

*Six of them are one line each. The sixth is the interesting one.*

---

## 8 — ⚠ The one thing to remember

# `200 OK`
# does not mean it worked

*Leave this slide up for a moment before the next one.*

---

## 9 — Two ways to fail

| | HTTP | |
| --- | --- | --- |
| Malformed request | **4xx** | your bug |
| Server broke | **5xx** | retry |
| **Answer is no** | **200** + `success: false` | *not* a transport failure |

Bad token · unlicensed feature · ambiguous room name — **all 200s**

```python
response.raise_for_status()          # lets every one of those through
```

*→ demo this live in notebook 02 before they try it.*

---

## 10 — Four kinds of "no"

| category | means | tell the user |
| --- | --- | --- |
| `auth` | bad/expired token | check the configuration |
| `license` | feature not licensed | **"we cannot answer"** |
| `client` | malformed request | your bug |
| `server` | appliance broke | try again |

*The licence row is the one that matters. If an unlicensed map renders as "no safe angles found",
you have turned "I don't know" into "the answer is no" — in a tool whose job is deciding whether
a beam can be delivered.*

---

## 11 — The map request

```python
{"PatientSurfaceId": "<guid>",
 "TreatmentRoomId":  "<guid>",      # the GUID, never the machine name
 "PatientPosition":  "HFS",
 "CouchBuffer":      20.0,          # ← MILLIMETRES
 "PatientBuffer":    20.0,          # ← MILLIMETRES
 "HighResolution":   False,
 "Isocenter": {"x": …, "y": …, "z": …}}   # mm, from the plan
```

*A planner thinks in centimetres. Out by ten is the most likely mistake anyone makes today.*

---

## 12 — The one response that is not JSON

```
37,36          ← couch samples, gantry samples
90,180,1       ← couch, gantry, isOK
85,180,1
...
DONE
```

- Streams as it computes — **minutes**, on a real appliance
- The list is **not ordered**
- Its *errors* are still JSON

*That is why GetMap streams: so a client can show progress instead of appearing to hang.*

---

## 13 — What a clearance map looks like

*[Screenshot: the bow-tie plot from notebook 05, beams overlaid]*

- Two lobes on the lateral gantry angles
- Pinching as the couch is kicked
- Anterior and posterior: flat, clear, **independent of couch angle**

*Ask why the top and bottom bands are flat before you explain it. Someone will get there.*

---

## 14 — Why, in one line

```
source offset from isocenter, in the patient's frame:

  along the body   R · sin(gantry) · sin(couch)
  lateral          R · sin(gantry) · cos(couch)
  vertical         R · cos(gantry)
```

At gantry **0** and **180**, `sin(g) = 0` → **the couch cannot matter.**

At gantry 90 with the couch kicked, the head swings a full *R* over the head or feet. *That is
where real collisions happen.*

---

## 15 — Two ways to check a beam

| | |
| --- | --- |
| **Ask the appliance** | `GetBeamDeliveryStatus` — fast, checks the control points you send |
| **Check the map yourself** | free once you hold it, and answers what-ifs |

They agree. **Until they don't.**

---

## 16 — The trap

An arc sent as **start and stop** is *two angles checked* — not the 358 between them.

```
appliance:  deliverable          ← both endpoints are clear
map sweep:  COLLISION            ← it passes through one
```

**Neither is wrong.** They answer different questions.

*This is the single most likely real bug in anything they go on to write. Let the room argue
about it before you resolve it.*

---

## 17 — The capstone

```
  #  name             verdict
  1  SETUP AP         PASS
  2  AP               PASS
  ...
  6  RT LAT KICK      FAIL
  8  VMAT CC KICK     FAIL        ← the arc trap, in a real plan
```

**Sixty lines**, plan file to report.

---

## 18 — Where to go from here

- **Notebook 07** — timeouts, throttling, truncated data. Do this before you write anything real.
- Point it at your own appliance: change the URL, the token, add `verify=False`
- `scripts/record_map.py --from-url` captures *real* appliance responses for your own demos

**github.com/tallhamer/SGRT-Scripting-Workshop**

---

## 19 — One last thing

This is a **teaching simulator**. The maps behave correctly; the numbers are invented.

Anyone pointing this at a real appliance for clinical work owns the validation.

*Say it. It costs nothing and it is true.*

---

## Spares — if you have time or get asked

**The room-name trap.** `machineName` is not unique. The lookup returns a GUID, or an all-zeros
GUID for no match (a *success*), or `DuplicateKey` for several. Three outcomes for a one-line
call, which is why production code lists rooms once and keys on the GUID.

**The surface carries no patient position.** Couch coordinates, no HFS/FFP metadata. You have to
know from the plan — and nothing warns you if you get it wrong.

**A truncated map parses into the wrong shape.** Missing triples mean missing gantry values, so
you get a half-height array with no exception, and then index the wrong angle. That is what
`DONE` is for.
