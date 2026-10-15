"""01 — Setup and the token."""

from ._common import bootstrap_cells, header

CELLS = [
    ("md", header("01", "Setup and the token",
                  "Find the simulator, find your token, make one call.", "10 minutes")),
    *bootstrap_cells(),

    ("md", """\
## What you are talking to

A **MapRT appliance** is a server on the clinical network. It holds the patient surfaces acquired
in your CT room, the scanned geometry of each treatment room, and it computes clearance maps on
request. You talk to it over HTTPS.

For this workshop it is replaced by a simulator running on your own machine, which answers the
same seven requests in the same formats. Nothing you learn about the requests will be wrong when
you point your code at a real appliance.

Three things identify a call:

| | |
| --- | --- |
| **The base URL** | where the appliance is. Here, `http://127.0.0.1:8000`. |
| **The token** | a shared secret. Not a login — one long string, issued per appliance. |
| **The User-Agent** | who you are. The appliance expects a particular format. |

We will get all three in this notebook and use them to make exactly one call."""),

    ("md", """\
## 1. The base URL

The simulator printed this when it started. If you are following the local setup, look at the
other terminal — you will see a box with `Base URL` in it."""),
    ("code", '''\
import os

BASE_URL = os.environ.get("MAPRT_SIM_URL", "http://127.0.0.1:8000")
BASE_URL
'''),

    ("md", """\
## 2. The token

The simulator generates a **new token every time it starts**. That is deliberate: a workshop
credential should be disposable, so nobody ends up with a long-lived shared secret in their notes.

It gets to you two ways. It is printed in that same box in the terminal:

```
MAPRT_SIM_TOKEN=amIUvdlPP3AHAhx4dLH3vfW9sOjbK2KDM5E3pj-DahE
```

...and it is written to a file, `.maprt_sim/token`, in the repository. The file matters: on Colab
and Binder the simulator runs in the background and nobody ever sees its output, so a printed
banner would be useless there.

`find_token()` checks the `MAPRT_SIM_TOKEN` environment variable first, then walks up from this
notebook's directory looking for that file."""),
    ("code", '''\
from maprt_workshop import find_token

TOKEN = find_token()
print("found a token:", TOKEN is not None)
print("it looks like:", TOKEN[:8] + "..." if TOKEN else "nothing")
'''),

    ("md", """\
If that printed `False`, the simulator is not running or you are in a different directory from
it. Start it with `uv run maprt-sim` and re-run the cell. You can also paste the token in by hand:

```python
TOKEN = "paste-the-value-from-the-terminal-here"
```

**Notice what you just did, though.** You put a credential in a notebook cell. That is fine for a
throwaway token against a simulator, and it is a habit worth not carrying into anything real — a
notebook gets emailed, committed and screen-shared. Read it from the environment or a file."""),

    ("md", """\
## 3. The User-Agent

The specification asks for a `User-Agent` of the form:

```
VisionRT.Integration.Saturn/<api version>.<something identifying you>
```

So `VisionRT.Integration.Saturn/2.0.my-qa-script`. A real appliance may refuse a request without
it. Put something recognisable after the version — when someone is reading the appliance's logs
trying to work out which script is hammering it, that string is what they have to go on."""),
    ("code", '''\
USER_AGENT = "VisionRT.Integration.Saturn/2.0.workshop-notebook-00"
USER_AGENT
'''),

    ("md", """\
## 4. Make the call

`/integration/ping` is the cheapest request there is, and the one to reach for first when
anything is wrong: it proves the host is reachable, that it is speaking the protocol you expect,
and that your token is accepted — in one request.

Build it piece by piece. First the URL:"""),
    ("code", '''\
url = BASE_URL + "/integration/ping"
url
'''),

    ("md", "Then the headers. Three of them, every call, forever:"),
    ("code", '''\
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",   # the shared secret, with the word "Bearer" in front
    "User-Agent": USER_AGENT,
}
list(headers)          # just the names for now — never print the token itself
'''),

    ("md", """\
Now send it. We are using `httpx2` here; `requests`, `urllib`, or whatever your site already has
would do exactly as well. **The MapRT API is plain HTTPS and the client library is your choice,
not ours** — notebook 01 makes the same call three different ways to prove it."""),
    ("code", '''\
import httpx2

response = httpx2.get(url, headers=headers)
response
'''),

    ("md", """\
## 5. Look at what came back, before using it

This is a habit worth building: **describe the response before you reach into it.** Most of the
time it is obvious. The times it is not are the times you lose an afternoon."""),
    ("code", '''\
response.status_code
'''),
    ("md", "The appliance tells you what it is in a header. Useful when you are not sure which "
           "machine you are actually connected to:"),
    ("code", '''\
response.headers["Server"]
'''),
    ("md", "And the body is JSON. Look at its **keys** first:"),
    ("code", '''\
body = response.json()
list(body)
'''),

    ("md", """\
Five keys, and every MapRT response but one has exactly these:

| key | what it holds |
| --- | --- |
| `data` | the answer, when there is one |
| `success` | **whether the call actually worked** |
| `errorCode` | what went wrong, when something did |
| `errorCodeType` | which family of problem it was |
| `errorData` | extra detail, sometimes |

Now, and only now, reach in:"""),
    ("code", '''\
body
'''),
    ("md", "`data` is the **API** version the server implements — not its software version, which "
           "came back in that `Server` header. The specification is careful to keep the two apart."),
    ("code", '''\
body["data"]
'''),

    ("md", """\
## Your turn

Break it on purpose. Change one character in the token and send the same request again.

Before you run it, predict: **what status code comes back?**"""),
    ("code", '''\
# Your turn: send the ping with a deliberately wrong token.
# What status code do you expect?

broken = dict(headers, Authorization="Bearer definitely-not-the-token")
# ...
'''),
    ("md", "<details><summary>Answer</summary>\n\nRun the next cell.\n\n</details>"),
    ("code", '''\
broken = dict(headers, Authorization="Bearer definitely-not-the-token")
refused = httpx2.get(url, headers=broken)

print("status code:", refused.status_code)
print("success:    ", refused.json()["success"])
print("errorCode:  ", refused.json()["errorCode"])
'''),

    ("md", """\
**200 OK — and it did not work.**

If that surprised you, good. It is the single most important thing about this API, and notebook 01
is mostly about it.

## The short version

Everything above collapses into three lines, which is how the rest of the notebooks will start:

```python
from maprt_workshop import connect
maprt = connect()
```

Use that from here on. You have seen what it is doing."""),
    ("code", '''\
from maprt_workshop import connect

maprt = connect()
print(maprt.api_url, "->", maprt.get_api_version())
'''),

    ("md", """\
---

**Next:** [`02_connect_and_errors.ipynb`](02_connect_and_errors.ipynb) — why a `200` can mean failure, and the four kinds of
thing that go wrong."""),
]
