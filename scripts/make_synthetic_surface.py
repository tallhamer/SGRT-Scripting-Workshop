"""Generate a synthetic patient surface as ASCII OBJ — no patient data involved.

A MapRT surface is a full-body triangle mesh in NATIVE (couch) coordinates. What matters for the
workshop is that it is *shaped like a person on a couch* at roughly the right scale, so that
plotting it looks right and its bounding box is believable. It does not need to be anatomy, and
deliberately is not: the repository must contain nothing patient-derived.

The body is a tube along +x (superior to inferior, matching the long axis of a real export) whose
cross-section is an ellipse whose semi-axes follow a head / neck / shoulders / torso / hips / legs
profile. Ends are capped. A seed varies the proportions so each "patient" has a distinguishable
surface and a distinguishable clearance map.

    uv run python scripts/make_synthetic_surface.py data/MapRT/surfaces/<guid>.obj --seed 1
"""

import argparse
from pathlib import Path

import numpy as np

# (fraction along the body, lateral semi-axis mm, vertical semi-axis mm). Lateral is the wide
# direction (shoulder to shoulder); vertical is couch-to-front. Reads top (head) to bottom (feet).
PROFILE = [
    (0.00, 70, 80),    # crown
    (0.05, 90, 105),   # head
    (0.09, 60, 70),    # neck
    (0.13, 200, 115),  # shoulders
    (0.22, 175, 120),  # chest
    (0.35, 150, 115),  # waist
    (0.45, 165, 120),  # hips
    (0.55, 115, 105),  # upper thighs (both legs as one mass)
    (0.75, 85, 85),    # knees
    (0.95, 55, 60),    # ankles
    (1.00, 45, 50),    # feet
]

BODY_LENGTH_MM = 1800.0


def semi_axes(t, lateral_scale=1.0, vertical_scale=1.0):
    """Interpolate the profile at fractions ``t`` along the body."""
    fractions = np.array([p[0] for p in PROFILE])
    lateral = np.array([p[1] for p in PROFILE], dtype=float)
    vertical = np.array([p[2] for p in PROFILE], dtype=float)
    return (np.interp(t, fractions, lateral) * lateral_scale,
            np.interp(t, fractions, vertical) * vertical_scale)


def build_mesh(stations=120, around=80, seed=0, length=BODY_LENGTH_MM):
    """Return ``(vertices, faces)`` for the surface. Faces are 0-based triangles."""
    rng = np.random.default_rng(seed)
    # Modest per-patient variation: habitus and height, not noise. Enough that the surfaces are
    # visibly different and their clearance maps differ, without producing anything implausible.
    lateral_scale = float(rng.uniform(0.88, 1.18))
    vertical_scale = float(rng.uniform(0.85, 1.20))
    length = length * float(rng.uniform(0.94, 1.06))

    t = np.linspace(0.0, 1.0, stations)
    a, b = semi_axes(t, lateral_scale, vertical_scale)

    # A full turn, open (no duplicate seam vertex) so the tube closes by index wrap-around.
    theta = np.linspace(0.0, 2.0 * np.pi, around, endpoint=False)

    x = (t * length)[:, None] * np.ones_like(theta)[None, :]
    y = a[:, None] * np.cos(theta)[None, :]
    # Flattened underside: a person lies on a couch, they are not a free-floating ellipse. Pulling
    # the lower half towards the couch plane is what makes the silhouette read as a patient.
    z_raw = np.sin(theta)[None, :]
    z = b[:, None] * np.where(z_raw < 0, z_raw * 0.45, z_raw)

    vertices = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)

    faces = []
    for i in range(stations - 1):
        for j in range(around):
            j_next = (j + 1) % around            # wrap closes the tube
            v00 = i * around + j
            v01 = i * around + j_next
            v10 = (i + 1) * around + j
            v11 = (i + 1) * around + j_next
            faces.append((v00, v10, v11))
            faces.append((v00, v11, v01))

    # Cap each end with a fan to a centre vertex, so the mesh is closed and a renderer does not
    # show a hollow tube.
    for station, flip in ((0, True), (stations - 1, False)):
        centre = len(vertices)
        ring = vertices[station * around:(station + 1) * around]
        vertices = np.vstack([vertices, ring.mean(axis=0)])
        for j in range(around):
            j_next = (j + 1) % around
            v0 = station * around + j
            v1 = station * around + j_next
            faces.append((centre, v1, v0) if flip else (centre, v0, v1))

    return vertices, np.asarray(faces, dtype=np.int64)


def write_obj(path, vertices, faces, label):
    """Write ASCII OBJ, with the ``ps``/``fs`` count header a MapRT export carries.

    The header lines and the comment banner are not standard OBJ — they are what the appliance
    emits, and the workshop's reader has to cope with them, so the synthetic files carry them too.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Synthetic surface for the MapRT scripting workshop.\n")
        handle.write("# Not patient data. Not a real acquisition. File type: ASCII OBJ\n")
        handle.write(f"# {label}\n")
        handle.write(f"ps {len(vertices)}\n")
        handle.write(f"fs {len(faces)}\n\n")
        for vx, vy, vz in vertices:
            handle.write(f"v {vx:.3f} {vy:.3f} {vz:.3f}\n")
        # OBJ face indices are 1-based.
        for f0, f1, f2 in faces + 1:
            handle.write(f"f {f0} {f1} {f2}\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", help="where to write the .obj")
    parser.add_argument("--seed", type=int, default=0, help="varies the body proportions")
    parser.add_argument("--stations", type=int, default=120, help="samples along the body")
    parser.add_argument("--around", type=int, default=80, help="samples around the body")
    parser.add_argument("--label", default="", help="a comment line written into the file")
    args = parser.parse_args(argv)

    vertices, faces = build_mesh(args.stations, args.around, args.seed)
    path = write_obj(args.output, vertices, faces, args.label or f"seed {args.seed}")
    size_kb = path.stat().st_size / 1024
    print(f"{path}: {len(vertices):,} vertices, {len(faces):,} faces, {size_kb:,.0f} KB")


if __name__ == "__main__":
    main()
