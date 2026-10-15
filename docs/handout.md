# MapRT API 2.0 — one page

*Workshop handout. Keep this open while you work.*

> Not a medical device. The simulator's clearance maps are plausible, not physical.

## Every call carries these three headers

```python
{"Content-Type":  "application/json",
 "Authorization": f"Bearer {token}",          # a shared secret, issued per appliance
 "User-Agent":    "VisionRT.Integration.Saturn/2.0.your-script-name"}
```

A real appliance presents a **self-signed certificate**, so a real client sets `verify=False`
(httpx/requests), an `ssl` context (urllib), or `PeerVerifyMode.VerifyNone` (Qt). Right for an
appliance on a clinical VLAN. Wrong for anything on the open internet.

## The seven requests

| | Request | Returns |
| --- | --- | --- |
| 1 | `GET /integration/ping` | The API version. Proves reachable + authenticated. |
| 2 | `GET /integration/rooms` | Every room configuration: `id` (GUID), `machineName`, `name`, `coordinateSystem`. |
| 3 | `GET /integration/rooms/{machineName}` | One room's GUID — **three** possible outcomes, see below. |
| 4 | `GET /integration/patients/{patientId}/surfaces` | `[{id, timeStamp, timeZone}]`, UTC + a zone *name*. |
| 5 | `GET /integration/surfaces/{surfaceId}` | A base64 data URI of an ASCII **OBJ** mesh. |
| 6 | `POST /integration/GetMap` | A clearance map. **Streaming text, not JSON.** |
| 7 | `POST /integration/GetBeamDeliveryStatus` | `[{beamNumber, isSafe}]` for the control points you send. |

## The envelope — every endpoint except GetMap

```json
{"data": …, "errorData": null, "success": true,
 "errorCode": null, "errorCodeType": "NoErrorCodes"}
```

## ⚠ A 200 does not mean it worked

| | HTTP | Meaning |
| --- | --- | --- |
| Malformed request | **4xx** | Your bug. Do not retry unchanged. |
| Server broke | **5xx** | Worth retrying. |
| **Negative result** | **200** + `success: false` | The request was fine; the answer is no. Do not retry. |

Bad token, unlicensed feature and ambiguous room name are **all 200s**. `raise_for_status()`
alone lets every one of them through.

Branch on `errorCodeType`, not the code string:

| category | type | what to tell the user |
| --- | --- | --- |
| `auth` | `AuthErrorCodes` | "Check the API token." Configuration. |
| `license` | `LicenseErrorCodes` | **"We cannot answer"** — *not* "the answer is no". |
| `client` | 4xx or any other code | The request was wrong. |
| `server` | 5xx | The appliance has a problem. |

## GetMap request body — mind the units

```python
{"PatientSurfaceId": "<guid>",        # from request 4
 "TreatmentRoomId":  "<guid>",        # the GUID, never the machineName
 "PatientPosition":  "HFS",           # or 1 — see gotchas
 "CouchBuffer":      20.0,            # MILLIMETRES
 "PatientBuffer":    20.0,            # MILLIMETRES
 "HighResolution":   False,           # true = 1°, and minutes not seconds
 "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}   # mm, DICOM patient coords, tag (300a,012c)
```

## GetMap response — the one non-JSON body

```
37,36          ← couch_samples , gantry_samples
90,180,1       ← couch , gantry , isOK   (1 = clear, 0 = collision)
85,180,1
...
DONE           ← check for this. Always.
```

Gantry 0–359; couch 270–359 and 0–90 (IEC 61217, i.e. ±90). **The list is not ordered.**
Its *errors* still arrive as the JSON envelope, so sniff the body before parsing.

## Six things that catch people out

1. **A 200 can mean no.** Above. The big one.
2. **`machineName` is not unique.** `GET /rooms/{machineName}` returns a GUID, or the
   **all-zeros GUID** for no match (a *success*), or `DuplicateKey` for several. List rooms once,
   key on the GUID forever.
3. **Buffers are mm.** A planner thinks cm. Out by 10× is the most likely mistake you will make.
4. **The surface carries no patient position.** It is in couch coordinates with no HFS/FFP
   metadata. Get the position from the RT Plan; nothing warns you if you get it wrong.
5. **GetBeamDeliveryStatus only checks the control points you send.** An arc sent as start +
   stop is two angles checked, not the 358 between them. It will be called safe while sweeping
   through a collision.
6. **A truncated map parses silently into the wrong shape.** Missing triples mean missing gantry
   values, so you get a half-height array with no exception — and then index the wrong angle.
   That is what `DONE` is for.

## Two more worth knowing

- **Empty list ≠ unknown patient.** A known patient with no acquisition returns `[]` at
  `success: true`. One sends them for a scan; the other means you have the wrong ID.
- **GetMap takes minutes** on a real appliance. The documented client timeout is **180 s**, not 5.

## Cheat sheet

```python
response = httpx.post(url, headers=headers, json=body, timeout=180)
response.raise_for_status()                     # 1. was the request well-formed?
envelope = response.json()
if not envelope.get("success", True):           # 2. was the answer yes?
    raise MapRTError(envelope["errorCode"], envelope["errorCodeType"])
data = envelope["data"]
```

Workshop: https://github.com/tallhamer/SGRT-Scripting-Workshop
