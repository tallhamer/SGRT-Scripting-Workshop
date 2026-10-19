"""The workshops this repository holds, one per Vision RT product.

Every top-level folder is split the same way — ``data/<name>/``, ``notebooks/<name>/``,
``docs/<name>/``, ``scripts/<name>/``, ``src/<name>/``, ``tests/<name>/`` — so a product here is
mostly a name. Adding one is an entry in :data:`PRODUCTS`, a ``<command> = ...`` line under
``[project.scripts]``, and those folders. ``tests/common`` checks that every product listed here
has them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """One workshop.

    ``emulator`` names the package that emulates the product's API, run as ``python -m
    <emulator>`` while the workshop is open. Only MapRT has an API to emulate: the other
    products' notebooks work on example files in ``data/<name>/``, so for them it is ``None`` and
    the launcher opens Jupyter and nothing else.

    An emulator package must provide ``<emulator>.cli.address(argv, prog)``, returning the
    ``(host, port)`` the emulator will listen on for those arguments, so the launcher knows what
    to wait for — and so ``--help`` and a bad flag are reported before anything starts.
    """

    name: str
    command: str
    title: str
    emulator: str | None = None

    @property
    def folder(self):
        """The per-product folder name used under data/, notebooks/, docs/ and the rest."""
        return self.name


MAPRT = Product(
    name="MapRT",
    command="maprt-workshop",
    title="MapRT Scripting Workshop",
    emulator="maprt_emulator",
)

#: Every workshop, by name. AlignRT, SimRT and DoseRT join this as their workshops are written.
PRODUCTS = {product.name: product for product in (MAPRT,)}
