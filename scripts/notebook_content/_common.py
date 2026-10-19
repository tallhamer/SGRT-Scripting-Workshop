"""Pieces shared by every notebook: the banner, the bootstrap, and the connect block."""

#: The published repository. The Colab bootstrap pip-installs from it and clones it, and the
#: Binder badge points at it — so this has to match the real remote, and the repository has
#: to be reachable without credentials for either path to work.
REPO_URL = "https://github.com/tallhamer/SGRT-Scripting-Workshop"

BANNER = """\
> **Not a medical device. Teaching use only.** Everything here talks to a *simulator* running on
> your own machine. The surfaces are synthetic, the clearance maps are plausible rather than
> physical, and nothing in this repository came from a patient. Not affiliated with or endorsed
> by Vision RT.
"""

BOOTSTRAP = f'''\
# Running on Google Colab? This installs the workshop and starts the simulator.
# Anywhere else it does nothing: locally you already started it in the other terminal, and on
# Binder it was started for you before this notebook opened.
import os, subprocess, sys, time, urllib.request

if "COLAB_RELEASE_TAG" in os.environ:
    REPO = "{REPO_URL}"
    CHECKOUT = "/content/workshop"

    subprocess.run([sys.executable, "-m", "pip", "-q", "install",
                    f"maprt-scripting-workshop[notebooks] @ git+{{REPO}}"], check=True)

    if not os.path.isdir(CHECKOUT):
        subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, CHECKOUT], check=True)

    # Work from the checkout's notebooks/ directory. Colab opens a notebook detached from its
    # repository, so every relative path would otherwise be wrong — the capstone reads
    # "../data/MapRT/plans/..." and would look in /data. One chdir makes Colab match a local clone
    # instead of special-casing paths in each notebook.
    os.chdir(f"{{CHECKOUT}}/notebooks")

    os.environ["MAPRT_EMULATOR_TOKEN"] = "workshop-colab-token"
    os.environ["MAPRT_EMULATOR_URL"] = "http://127.0.0.1:8000"

    # --token matters: without it the simulator mints a random token, while the environment
    # above advertises a different one, and every call fails with InvalidClientToken. The
    # simulator must be given the same secret this notebook is going to send.
    log = open("/content/maprt-emulator.log", "w")
    subprocess.Popen(["maprt-emulator", "--port", "8000",
                      "--token", os.environ["MAPRT_EMULATOR_TOKEN"],
                      "--data-dir", f"{{CHECKOUT}}/data/MapRT",
                      "--map-seconds", "1"],
                     stdout=log, stderr=subprocess.STDOUT)

    # Poll rather than sleep. A fixed wait is either too short on a slow runtime (the first cell
    # fails for no visible reason) or wasted time on a fast one.
    for _attempt in range(60):
        try:
            urllib.request.urlopen(os.environ["MAPRT_EMULATOR_URL"] + "/sim/state", timeout=1)
            print("simulator ready")
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("The simulator did not start. See /content/maprt-emulator.log")

print("Python", sys.version.split()[0])
'''

CONNECT = '''\
from maprt_workshop import connect

maprt = connect()          # finds the simulator and your token, and checks it answers
print(maprt.api_url)
'''


def header(number, title, subtitle, duration):
    """The opening markdown cell every notebook shares."""
    return f"""\
# {number} · {title}

*{subtitle}*

**About {duration}.**

{BANNER}"""


def bootstrap_cells():
    """The two cells every notebook opens with after its header."""
    return [
        ("md", "First, make sure the environment is ready. On your own machine this cell does "
               "nothing at all — it only matters on Colab and Binder, where the simulator has to "
               "be installed and started from inside the notebook."),
        ("code", BOOTSTRAP),
    ]
