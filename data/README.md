# Workshop data, one folder per product

Each Vision RT product this repository has scripting examples for keeps its data in its own
folder here. A product's code and notebooks read only their own folder.

| Folder | Product | Status |
| --- | --- | --- |
| [`MapRT/`](MapRT/README.md) | MapRT, the collision-avoidance API the emulator in `src/MapRT/maprt_emulator` serves | **In use**: rooms, patients, surfaces, recorded clearance maps, a synthetic RT Plan |
| `AlignRT/` | AlignRT | Planned. The folder will be added with its first notebook project |
| `SimRT/` | SimRT | Planned |
| `DoseRT/` | DoseRT | Planned |

## The rules every product folder follows

- **Committed data is synthetic only.** This is a public repository. Nothing that came off a
  clinical system is ever committed, under any product.
- **Real data goes in that product's `local/` folder** (`data/MapRT/local/`, and later
  `data/AlignRT/local/`, and so on). `.gitignore` ignores `data/*/local/`, so every product
  gets one automatically and nothing in it can become a commit candidate.
- **`local/` overlays the folder it sits in.** For MapRT a file there replaces or wins over the
  public file of the same name. How each product applies its overlay is described in that
  product's own `README.md`.
- **Each product folder has a `README.md`** saying what is in it, what the shipped data is
  arranged to teach, and how to add more.

## Adding a product

A product is a workshop, and every top-level folder has a subfolder for it. For a product called
`<Product>` (folder names use the product's own capitalisation, e.g. `AlignRT`):

1. **`data/<Product>/`** with a `README.md` and the synthetic example data. Real data goes in
   `data/<Product>/local/`, which is already git-ignored.
2. **`src/common/sgrt_workshop/products.py`**: add a `Product` to `PRODUCTS`. Leave `emulator`
   as `None` unless the product has an API to emulate. Only MapRT does.
3. **`pyproject.toml`**: add `<product>-workshop = "sgrt_workshop.launcher:<product>"` under
   `[project.scripts]`, and a matching three-line function at the bottom of
   `src/common/sgrt_workshop/launcher.py`.
4. **`scripts/<Product>/notebook_content/`** with an `__init__.py` exporting `NOTEBOOKS`, then
   `uv run python scripts/common/build_notebooks.py` to write **`notebooks/<Product>/`**.
5. **`src/<Product>/`** for any Python package the notebooks need, added to the wheel's
   `packages` list and to ruff's `src` list in `pyproject.toml`.
6. **`docs/<Product>/`** with at least a handout and a run-sheet; add a row to
   [`docs/README.md`](../docs/README.md).
7. **`tests/<Product>/`** for its tests.
8. Update this table, the workshops table in the top-level `README.md`, and add a Binder/Colab
   badge for its `00_start_here.ipynb`.

`tests/common` fails if a registered product is missing its notebooks, data or docs folder, so a
half-added product shows up in CI rather than in front of a room.
