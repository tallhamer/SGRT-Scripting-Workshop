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
# Running on Google Colab or Binder? This installs the workshop and starts the simulator.
# On your own machine it does nothing — you already started the simulator in the other terminal.
import os, subprocess, sys, time

if "COLAB_RELEASE_TAG" in os.environ:
    subprocess.run([sys.executable, "-m", "pip", "-q", "install",
                    "maprt-scripting-workshop[notebooks] @ git+{REPO_URL}"], check=True)
    if not os.path.isdir("/content/workshop"):
        subprocess.run(["git", "clone", "-q", "--depth", "1",
                        "{REPO_URL}", "/content/workshop"], check=True)
    os.environ.setdefault("MAPRT_SIM_TOKEN", "workshop-colab-token")
    subprocess.Popen(["maprt-sim", "--port", "8000", "--data-dir", "/content/workshop/data"])
    time.sleep(4)

print(sys.version.split()[0])
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
