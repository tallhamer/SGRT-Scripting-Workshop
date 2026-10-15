"""02 — Connecting, and what goes wrong."""

from ._common import CONNECT, bootstrap_cells, header

CELLS = [
    ("md", header("02", "Connecting, and what goes wrong",
                  "Four kinds of failure, and why a 200 can mean no.", "20 minutes")),
    *bootstrap_cells(),
    ("code", CONNECT),

    ("md", """\
## The headline

In notebook 01 you sent a deliberately wrong token and got back:

```
status code: 200
success:     False
errorCode:   InvalidClientToken
```

**HTTP 200, and the call did not work.** This is not a quirk of the simulator. It is what the
specification says the appliance does, and it is the single most common way people get MapRT
integrations wrong.

Here is the rule, from §5.3 of the specification:

> When the request is malformed or some other client error occurs, the HTTP status **4xx** is
> returned, e.g. "400 Bad Request".
>
> When the result of request processing is **negative**, the HTTP status is still **"200 OK"** and
> the `success` flag returned in JSON is set to `false`.

So the status code answers *"was your request well-formed?"* — not *"did you get what you
wanted?"* Those are different questions and the API answers them in different places."""),

    ("md", """\
## What that means for your code

The idiom almost everyone reaches for first:

```python
response = httpx2.get(url, headers=headers)
response.raise_for_status()      # <- lets every negative result straight through
data = response.json()["data"]   # <- None, and you find out 50 lines later
```

A bad token, an unlicensed feature and an ambiguous room name all sail past `raise_for_status()`.
You then index into `data`, get `None`, and the traceback appears somewhere unrelated.

**Check both.** Let us see it happen."""),
    ("code", '''\
import httpx2

url = maprt.api_url + "/integration/rooms"
headers = dict(maprt.headers)                    # the three headers from notebook 01

bad = dict(headers, Authorization="Bearer wrong-token")
response = httpx2.get(url, headers=bad)

print("status_code      :", response.status_code)
print("raise_for_status :", response.raise_for_status() and "did not raise")
'''),
    ("md", "It did not raise. Now look at the body:"),
    ("code", '''\
response.json()
'''),
    ("md", """\
`data` is `None`. If your code had gone straight to `response.json()["data"]` and started
iterating, you would get `TypeError: 'NoneType' object is not iterable` — a message that tells you
nothing about the actual problem, which is that your token is wrong."""),

    ("md", """\
## Checking it properly

Two lines, both necessary:"""),
    ("code", '''\
def call(method, endpoint, body=None):
    """Make a MapRT call and return `data`, raising on either kind of failure."""
    response = httpx2.request(method, maprt.api_url + endpoint, headers=headers, json=body)

    # 1. Was the request well-formed, and is the server alive? (4xx / 5xx)
    response.raise_for_status()

    # 2. Was the answer yes? (200 + success:false)
    envelope = response.json()
    if not envelope.get("success", True):
        raise RuntimeError(f"{envelope['errorCodeType']}: {envelope['errorCode']}")

    return envelope["data"]


len(call("GET", "/integration/rooms"))
'''),
    ("md", """\
That is the whole idea. `maprt_workshop` does exactly this and raises a typed `MapRTApiError`
instead of a `RuntimeError` — but now you know what it is doing and could write it yourself."""),

    ("md", """\
## The four kinds of failure

An error code comes with a *type*, and the type is what you should branch on — not the code
string, which is more specific than your error handling usually needs to be.

| category | when | what to tell the user |
| --- | --- | --- |
| `auth` | `AuthErrorCodes` — bad or expired token | "Check the API token." A configuration problem. |
| `license` | `LicenseErrorCodes` — the feature is not licensed | **"We cannot answer that"** — *not* "the answer is no". |
| `server` | HTTP 5xx | "The appliance has a problem." Retry later. |
| `client` | HTTP 4xx, or any other reported code | "The request was wrong." Your bug, usually. |

The `license` row is the one worth dwelling on. Surfaces, clearance maps and beam-delivery status
are each separately licensed. If a map comes back `FeatureNotLicensed` and your UI shows "no safe
angles found", you have turned *"I don't know"* into *"the answer is no"* — in a tool whose whole
job is deciding whether a beam can be delivered safely."""),
    ("code", '''\
from maprt_workshop import MapRTApiError

try:
    maprt.get_surface("00000000-0000-0000-0000-000000000000")
except MapRTApiError as problem:
    print("code    :", problem.error_code)
    print("type    :", problem.error_code_type)
    print("category:", problem.category)       # <- branch on this
'''),

    ("md", """\
## Making the failures happen on purpose

You cannot test error handling you cannot trigger. An unlicensed appliance, a busy server, a
dropped connection — all real, none of them arrangeable at 4pm on a Tuesday. So error handling
gets written once, guessed at, and never exercised.

The simulator has a control surface for exactly this. **It is not part of the MapRT API** — it
lives under `/sim`, and nothing you learn from it transfers to a real appliance."""),
    ("code", '''\
scenarios = httpx2.get(maprt.api_url + "/sim/scenarios").json()["scenarios"]

for scenario in scenarios:
    print(f"{scenario['name']:<22} {scenario['description']}")
'''),
    ("md", "Arm one and watch it happen:"),
    ("code", '''\
httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "unlicensed-map"})

body = {"PatientSurfaceId": "dad7394f-6893-4ce3-96ed-8bc3091cf4c3",
        "TreatmentRoomId": "96bbc235-0da9-e983-0783-5973a7d11144",
        "PatientPosition": "HFS", "CouchBuffer": 20.0, "PatientBuffer": 20.0,
        "HighResolution": False, "Isocenter": {"x": 0.0, "y": 0.0, "z": 0.0}}

response = httpx2.post(maprt.api_url + "/integration/GetMap", headers=headers, json=body)
print("status:", response.status_code)
print("body  :", response.text[:120])
'''),
    ("md", "**Always disarm when you are done.** Every notebook that arms a scenario puts this at "
           "the end; forgetting is the most common way to confuse yourself later."),
    ("code", '''\
httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "ok"})
print("armed:", httpx2.get(maprt.api_url + "/sim/state").json()["scenario"]["name"])
'''),

    ("md", """\
## The library does not matter

The MapRT API is plain HTTPS. Any client that can set three headers and read a body will do.
Here is the same ping three ways — pick whichever your site already has."""),
    ("code", '''\
# 1. httpx2, what this workshop uses
print("httpx2  :", httpx2.get(maprt.api_url + "/integration/ping", headers=headers).json()["data"])
'''),
    ("code", '''\
# 2. requests, probably the most widely known
import requests
print("requests:", requests.get(maprt.api_url + "/integration/ping", headers=headers).json()["data"])
'''),
    ("code", '''\
# 3. urllib, from the standard library — no third-party package at all
import json, urllib.request

request = urllib.request.Request(maprt.api_url + "/integration/ping", headers=headers)
with urllib.request.urlopen(request) as raw:
    print("urllib  :", json.loads(raw.read())["data"])
'''),
    ("md", """\
The desktop application these parsers came from uses Qt's `QNetworkAccessManager`, and Vision RT's
own sample is C#. None of that changes the request.

**One thing does change with the library, though: TLS.** A real appliance presents a *self-signed*
certificate, so every client has to be told to accept it — `verify=False` in httpx and requests,
an `ssl` context in urllib, `PeerVerifyMode.VerifyNone` in Qt. That is the right call for an
appliance on a clinical VLAN whose certificate you cannot replace, and the wrong call for
anything on the open internet. Know which one you are doing. (The simulator speaks plain HTTP, so
it does not arise here.)"""),

    ("md", """\
## Your turn

The `server-error` scenario makes every `/integration` request return HTTP 500.

Write a call that tells a 500 apart from a `success: false` — and prints a different message for
each. Think about which one is worth retrying."""),
    ("code", '''\
# Your turn.
# httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "server-error"})
# ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "server-error"})

response = httpx2.get(maprt.api_url + "/integration/rooms", headers=headers)

if response.status_code >= 500:
    # The appliance broke. Nothing wrong with your request — worth retrying.
    print(f"server problem (HTTP {response.status_code}) — retry in a moment")
elif response.status_code >= 400:
    # Your request was wrong. Retrying it unchanged will fail identically.
    print(f"bad request (HTTP {response.status_code}) — fix the request")
elif not response.json()["success"]:
    # Well-formed request, and the answer is no. Retrying changes nothing.
    print(f"refused: {response.json()['errorCode']} — do not retry")
else:
    print("fine")

httpx2.post(maprt.api_url + "/sim/scenario", json={"name": "ok"})
'''),
    ("md", """\
The retry distinction matters. A 5xx is worth retrying; a 4xx and a `success: false` are not —
retrying them unchanged just makes the same mistake faster. Notebook 07 builds this into a proper
client.

---

**Next:** [`03_treatment_rooms.ipynb`](03_treatment_rooms.ipynb) — and the first place a real
appliance will surprise you."""),
]
