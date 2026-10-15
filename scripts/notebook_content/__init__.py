"""The workshop notebooks, as content rather than JSON.

Each module exports ``CELLS`` — a list of ``("md", text)`` and ``("code", text)`` pairs. House
style, settled with the maintainer and binding on every notebook here:

* **One idea per cell.** A call is never introduced as a finished line.
* **Build the request by hand first.** `url =`, then `headers = {...}` with each header
  explained, then `body = {}` one field at a time with its units stated, then send it. No helper
  function stands between a student and their first version of a call.
* **Describe the response before using it.** A cell printing the status code, a cell printing the
  envelope's *keys*, and only then a cell that reaches into `data`. Students should see the shape
  of a response before they see code that assumes it.
* Helpers (`maprt_workshop.build_map_request` and friends) appear only as an **epilogue** — "here
  is how you stop retyping this" — after the hand-built version works.

This is a workshop for people new to scripting. Someone who finishes should be able to write a
MapRT call from the specification with no library at all.
"""

from notebook_content import (
    nb00_index,
    nb01_setup,
    nb02_connect,
    nb03_rooms,
    nb04_surfaces,
    nb05_maps,
    nb06_beams,
    nb07_robustness,
    nb08_capstone,
)

#: The order they are meant to be worked through. ``nb00_index`` is the table of contents and
#: links to all the others, so a renumbering here means editing its table too.
NOTEBOOKS = [
    ("00_start_here.ipynb", nb00_index.CELLS),
    ("01_setup_and_token.ipynb", nb01_setup.CELLS),
    ("02_connect_and_errors.ipynb", nb02_connect.CELLS),
    ("03_treatment_rooms.ipynb", nb03_rooms.CELLS),
    ("04_patient_surfaces.ipynb", nb04_surfaces.CELLS),
    ("05_clearance_maps.ipynb", nb05_maps.CELLS),
    ("06_beams_and_plans.ipynb", nb06_beams.CELLS),
    ("07_robustness.ipynb", nb07_robustness.CELLS),
    ("08_capstone_plan_qa.ipynb", nb08_capstone.CELLS),
]
