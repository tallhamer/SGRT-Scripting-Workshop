# Workshop data, one folder per product

Each Vision RT product this repository has scripting examples for keeps its data in its own
folder here. A product's code and notebooks read only their own folder.

| Folder | Product | Status |
| --- | --- | --- |
| [`MapRT/`](MapRT/README.md) | MapRT, the collision-avoidance API the emulator in `src/maprt_sim` serves | **In use**: rooms, patients, surfaces, recorded clearance maps, a synthetic RT Plan |
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

1. Create `data/<Product>/` with a `README.md`, and keep its synthetic data there.
2. Default the product's code to `data/<Product>/`, found by walking up from the working
   directory the way `maprt_sim.settings.find_data_dir` does. Then it works the same from the
   repository root and from `notebooks/`.
3. Add a row to the table above.
