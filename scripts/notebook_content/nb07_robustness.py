"""07 — When things go wrong."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("07", "When things go wrong",
                  "Arm each failure on purpose, then write code that survives it.", "25 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## Why this notebook exists

Error handling is the part of a client that never gets tested, because the failures it exists for
are the ones you cannot arrange. An unlicensed appliance needs an appliance without the licence; a
throttled server needs a busy one; a timeout needs patience.

So it gets written once, guessed at, and never exercised — and then it is what fails during
treatment planning on a Friday afternoon.

The emulator can be *told* to fail. Everything below is armed deliberately."""),
    ("code", '''\
import httpx2

headers = dict(maprt.headers)
SIM = maprt.api_url + "/emulator"


def arm(name):
    """Arm a fault. Returns what it is meant to teach."""
    response = httpx2.post(SIM + "/scenario", json={"name": name})
    response.raise_for_status()
    return response.json()


def disarm():
    return arm("ok")


for scenario in httpx2.get(SIM + "/scenarios").json()["scenarios"]:
    print(f"{scenario['name']:<22} {scenario['description']}")
'''),
    ("md", """\
> `/emulator` is **not part of the MapRT API.** It is the emulator's own control surface, and it is
> deliberately unauthenticated — the `bad-token` scenario rejects every token, so if disarming it
> needed a working one you would have to restart the server to get out."""),

    ("md", """\
## 1. The licensed features

Surfaces, clearance maps and beam-delivery status are each separately licensed."""),
    ("code", '''\
print(arm("unlicensed-map")["teaches"])
'''),
    ("code", '''\
body = {"PatientSurfaceId": maprt.get_patient_surfaces("ANON001")[0][0],
        "TreatmentRoomId": maprt.get_treatment_rooms()[0][1],
        "PatientPosition": "HFS", "CouchBuffer": 20.0, "PatientBuffer": 20.0,
        "HighResolution": False, "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}

response = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers, json=body)

print("status      :", response.status_code)
print("content-type:", response.headers["Content-Type"])
print("body        :", response.text[:90])
'''),
    ("md", """\
**Look at the content type.** A successful `GetMap` is `text/plain`; this one is JSON. That is why
`parse_map_response` sniffs the body before deciding how to read it — a parser that assumed text
would try to read `{"data": null, ...}` as a clearance map and produce nonsense."""),
    ("code", '''\
from maprt_workshop import MapRTApiError, wire

try:
    wire.parse_map_response(response.text)
except MapRTApiError as problem:
    print("raised:", problem)
    print("category:", problem.category)
'''),
    ("md", """\
And the thing to actually do about it: **`license` is not `no`.**

```python
except MapRTApiError as problem:
    if problem.category == "license":
        show("This appliance is not licensed for clearance maps.")   # we cannot answer
    else:
        show("Could not compute a clearance map.")                   # something broke
```

If an unlicensed map renders as "no safe angles found", you have turned *"I don't know"* into
*"the answer is no"*, in a tool whose job is deciding whether a beam can be delivered."""),
    ("code", '''\
disarm();
'''),

    ("md", """\
## 2. Timeouts

A real `GetMap` takes **minutes**. The documented client default is **180 seconds** — not five."""),
    ("code", '''\
print(arm("slow")["teaches"])
'''),
    ("code", '''\
import time

started = time.monotonic()
try:
    httpx2.get(maprt.api_url + "/integration/ping", headers=headers, timeout=2.0)
except httpx2.TimeoutException as problem:
    print(f"gave up after {time.monotonic() - started:.1f}s: {type(problem).__name__}")
'''),
    ("md", """\
Nothing was wrong with the appliance. Your client decided it was broken.

Note the exception type: a timeout is **not** a `MapRTApiError`. It never reached the appliance,
so there is no envelope and no error code — it is a transport failure, and your handling has to
cover both kinds."""),
    ("code", '''\
started = time.monotonic()
response = httpx2.get(maprt.api_url + "/integration/ping", headers=headers, timeout=30.0)
print(f"with a sensible timeout: {response.json()['data']} after "
      f"{time.monotonic() - started:.1f}s")
disarm();
'''),
    ("md", """\
Pick timeouts per endpoint. `ping` should answer instantly and a 10-second wait means something
is wrong. `GetMap` legitimately takes minutes."""),
    ("code", '''\
TIMEOUTS = {
    "ping": 10.0,
    "rooms": 30.0,
    "surfaces": 120.0,       # meshes are large
    "GetMap": 600.0,         # "may take up to a few minutes"
}
TIMEOUTS
'''),

    ("md", """\
## 3. Throttling

From §2.2.1.3: the server *"may have throttling mechanisms implemented and report to the client if
it cannot process immediately and the request should be repeated."*"""),
    ("code", '''\
print(arm("throttle")["teaches"])
'''),
    ("code", '''\
response = httpx2.get(maprt.api_url + "/integration/ping", headers=headers)

print("status     :", response.status_code)
print("Retry-After:", response.headers.get("Retry-After"), "seconds")
'''),
    ("md", """\
**503 with a `Retry-After` header.** The server is telling you exactly how long to wait. Use it
rather than guessing — and *do* back off, because a tight retry loop against a struggling
appliance makes it worse.

Here is a retry that handles it properly. Note what it does **not** retry:"""),
    ("code", '''\
def call_with_retry(method, endpoint, body=None, attempts=5, timeout=60.0):
    """A MapRT call that survives throttling and transient server trouble."""
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            response = httpx2.request(method, maprt.api_url + endpoint,
                                      headers=headers, json=body, timeout=timeout)
        except httpx2.TimeoutException:
            if attempt == attempts:
                raise
            wait = delay
        else:
            if response.status_code == 503:
                # The server said "later" and told us how long.
                wait = float(response.headers.get("Retry-After", delay))
            elif response.status_code >= 500:
                wait = delay                      # transient: worth another go
            elif response.status_code >= 400:
                # OUR request is wrong. Retrying it unchanged fails identically, faster.
                response.raise_for_status()
            else:
                envelope = response.json()
                if not envelope.get("success", True):
                    # A refusal, not a failure. Retrying changes nothing.
                    raise MapRTApiError(envelope["errorCode"], envelope["errorCodeType"])
                return envelope["data"]

        print(f"  attempt {attempt} failed; waiting {wait:.0f}s")
        time.sleep(wait)
        delay = min(delay * 2, 30.0)              # exponential, capped

    raise RuntimeError(f"{endpoint} failed after {attempts} attempts")


arm("throttle")
print("result:", call_with_retry("GET", "/integration/ping"))
'''),
    ("md", """\
Three categories, three behaviours, and the distinction is the whole point:

| | retry? | why |
| --- | --- | --- |
| 503 / 5xx / timeout | **yes** | the appliance is busy or broken; it may not be in a moment |
| 4xx | **no** | your request is malformed; it will be just as malformed next time |
| `success: false` | **no** | the request was fine and the answer is no |

A retry loop that retries everything will hammer an appliance for five attempts over a typo."""),
    ("code", '''\
disarm();
'''),

    ("md", """\
## 4. Truncated data — the nasty one

What happens if a connection drops mid-map? Guess first: you probably expect a short map, or an
exception.

It is worse than that."""),
    ("code", '''\
print(arm("truncate-map")["teaches"])
'''),
    ("code", '''\
truncated = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers,
                        json=body, timeout=120)

print("status      :", truncated.status_code)
print("has DONE    :", "DONE" in truncated.text)
print("last line   :", truncated.text.strip().splitlines()[-1])
'''),
    ("md", "No error. The status is 200 and the body is *plausible*. Now parse it:"),
    ("code", '''\
image, x_ticks, y_ticks = wire.parse_map_response(truncated.text)
print("parsed shape:", image.shape)
'''),
    ("code", '''\
disarm()
complete, _x, _y = wire.parse_map_response(
    httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers,
                json=body, timeout=120).text)
print("complete shape:", complete.shape)
'''),
    ("md", """\
## Read those two shapes

```
truncated : (180, 185)
complete  : (360, 185)
```

**Half the map. No exception. Nothing in the data says anything is wrong.**

The parser works out the gantry axis from the values it actually sees. Half the triples means half
the gantry angles, so it builds a half-height array — perfectly consistent, entirely wrong.

What happens next is the dangerous part. Your code indexes by gantry row:

```python
image[row_for(200), column_for(0)]
```

and gets the data for **a completely different angle**, or an `IndexError` far from the cause. You
would be checking beam deliverability against a map that silently is not the map you asked for.

**This is what `DONE` is for.** Check it. Every time."""),
    ("code", '''\
def parse_map_safely(text, expect_gantry_rows=360):
    """Parse a GetMap body, refusing anything that did not arrive complete."""
    if not text.strip().endswith("DONE"):
        raise ValueError("the map response is truncated — no DONE terminator. "
                         "Do not use it: it will parse into a wrong-shaped array.")

    tokens = text.split()
    couch_samples, gantry_samples = (int(v) for v in tokens[0].split(","))
    expected = couch_samples * gantry_samples
    received = len(tokens) - 2                  # minus header, minus DONE
    if received != expected:
        raise ValueError(f"the map header promised {expected:,} triples but {received:,} arrived")

    image, x_ticks, y_ticks = wire.parse_map_response(text)
    if image.shape[0] != expect_gantry_rows:
        raise ValueError(f"the map parsed to {image.shape[0]} gantry rows, not "
                         f"{expect_gantry_rows}")
    return image, x_ticks, y_ticks


arm("truncate-map")
try:
    parse_map_safely(httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers,
                                 json=body, timeout=120).text)
except ValueError as problem:
    print("caught:", problem)
disarm();
'''),
    ("md", """\
Three checks, any one of which would have caught it. The terminator is the cheapest."""),

    ("md", """\
## 5. Order is not guaranteed

§5.2.6 says *"the list is not ordered."* It means it. Each triple carries its own couch and gantry
angle precisely so that arrival position cannot matter."""),
    ("code", '''\
print(arm("shuffle-map")["teaches"])
'''),
    ("code", '''\
import numpy as np

shuffled = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers,
                       json=body, timeout=120).text
disarm()
ordered = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers,
                      json=body, timeout=120).text

print("the bytes differ      :", shuffled != ordered)
print("the first triple was  :", shuffled.splitlines()[1], "vs", ordered.splitlines()[1])
print("they parse identically:",
      bool(np.array_equal(wire.parse_map_response(shuffled)[0],
                          wire.parse_map_response(ordered)[0])))
'''),
    ("md", """\
Identical maps. Any code that did `triples[0]` expecting couch 90 / gantry 180 would be quietly
wrong here and nowhere else — the worst kind of bug to find."""),

    ("md", """\
## 6. A dead token

Tokens get rotated. Appliances get replaced."""),
    ("code", '''\
print(arm("bad-token")["teaches"])
'''),
    ("code", '''\
response = httpx2.get(maprt.api_url + "/integration/rooms", headers=headers)
print("status   :", response.status_code)
print("errorCode:", response.json()["errorCode"])
disarm();
'''),
    ("md", """\
Still a 200. Notebook 02's lesson, in the form you will actually meet it: a credential that worked
yesterday, failing today, with a status code that says everything is fine.

An `auth` category error means *check the configuration* — not *retry*, and not *the patient has
no surfaces*."""),

    ("md", """\
## Your turn

Write `robust_get_map(body)` that handles all of it: sensible timeout, retry on 503 and 5xx with
backoff, no retry on 4xx or `success: false`, and a truncation check.

Then prove it by arming `throttle` and calling it."""),
    ("code", '''\
# Your turn.
def robust_get_map(body):
    ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
def robust_get_map(body, attempts=4, timeout=600.0):
    """Fetch a clearance map, surviving everything this notebook armed."""
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            response = httpx2.post(maprt.api_url + "/integration/GetMap",
                                   headers=headers, json=body, timeout=timeout)
        except httpx2.TimeoutException:
            if attempt == attempts:
                raise
            wait = delay
        else:
            if response.status_code == 503:
                wait = float(response.headers.get("Retry-After", delay))
            elif response.status_code >= 500:
                wait = delay
            elif response.status_code >= 400:
                response.raise_for_status()          # our bug; do not retry
            else:
                # 200 — but GetMap answers failure as JSON and success as text, so look.
                if response.text.lstrip().startswith("{"):
                    envelope = response.json()
                    raise MapRTApiError(envelope["errorCode"], envelope["errorCodeType"])
                return parse_map_safely(response.text)

        print(f"  attempt {attempt}: retrying in {wait:.0f}s")
        time.sleep(wait)
        delay = min(delay * 2, 30.0)

    raise RuntimeError("GetMap failed after every attempt")


arm("throttle")
image, x_ticks, y_ticks = robust_get_map(body)
print("got a map:", image.shape, f"{image.mean():.1%} clear")
disarm();
'''),

    ("md", """\
## Before you leave

**Always disarm.** A scenario left armed will confuse you an hour later in a different notebook."""),
    ("code", '''\
state = httpx2.get(SIM + "/state").json()
print("armed scenario:", state["scenario"]["name"])
assert state["scenario"]["name"] == "ok", "something is still armed — run disarm()"
print("clean.")
'''),
    ("md", """\
---

**Next:** [`08_capstone_plan_qa.ipynb`](08_capstone_plan_qa.ipynb) — all of it at once, on a real
RT Plan."""),
]
