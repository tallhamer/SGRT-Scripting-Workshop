"""Drawing a clearance map, with the beams overlaid.

Needs matplotlib, which is a notebook dependency rather than a library one — so this module is
**not** imported by ``maprt_workshop/__init__.py``. Import it explicitly::

    from maprt_workshop.plotting import plot_collision_map

The map is a binary grid: 360 gantry rows by 181 couch columns, each cell clear or colliding. So
there are only two states to encode, and the choice of how is not cosmetic.

**Deliberately not red/green.** A red/green clearance map is the conventional look and it is the
wrong choice for a tool that decides whether a beam is deliverable: red-green colour vision
deficiency affects roughly 8% of men, and in a physics department that is not a hypothetical
reader. The two states here are a **receding near-surface grey for clear** and a single strong
**red for collision** — which is safe precisely *because* there is no second hue to confuse it
with. The signal is the collision region; clear space should get out of the way.

A beam's verdict is carried by **marker shape**, not colour: a filled circle passes, an X fails.
Shape survives any colour vision, greyscale printing and a projector with the contrast turned
down — all three of which happen at a workshop. Colour never carries meaning alone here; every
plot gets a legend.

Colours are from a validated palette (CVD separation ΔE 33 light / 42 dark against the mark ink,
both states clear 3:1 against their surface). ``dark=True`` switches to steps chosen for the dark
surface rather than inverting the light ones.
"""

import numpy as np

# The axis values the collision map is laid out on, in display order: rows run gantry 180…359 then
# 0…179; columns run couch 270…359 then 0…90. Same construction as
# maprt_workshop.wire.parse_collision_map and maprt_workshop.beams.check_beams, so an index means
# the same angle in all three.
GANTRY_VALUES = np.hstack((np.arange(180, 360), np.arange(0, 180)))
COUCH_VALUES = np.hstack((np.arange(270, 360), np.arange(0, 91)))


class Theme:
    """The colours one plot is drawn with. Two validated sets, light and dark."""

    def __init__(self, dark=False):
        if dark:
            self.surface = "#1a1a19"
            self.clear = "#383835"        # near-surface neutral: recedes
            self.collision = "#d03b3b"    # status critical, 3.62:1 on this surface
            self.ink = "#ffffff"
            self.muted = "#898781"
            self.grid = "#2c2c2a"
        else:
            self.surface = "#fcfcfb"
            self.clear = "#f0efec"        # near-surface neutral: recedes
            self.collision = "#d03b3b"    # status critical, 4.68:1 on this surface
            self.ink = "#0b0b0b"
            self.muted = "#898781"
            self.grid = "#e1e0d9"


def plot_collision_map(map_data, ax=None, title=None, dark=False, tick_every=30):
    """Draw a clearance map. Returns the matplotlib ``Axes``.

    ``map_data`` is the ``(image, x_ticks, y_ticks)`` tuple
    :func:`maprt_workshop.wire.parse_collision_map` returns. ``tick_every`` is the label spacing
    in degrees; the parser's own 10-degree ticks are too dense to read on a notebook-sized figure.

    Both resolutions are handled. A coarse map is 185 columns wide rather than 181 — see the
    parser's docstring — and the extra columns are trimmed here so the axis labels line up with
    the data instead of drifting four degrees out.
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    theme = Theme(dark)
    image = _trimmed(map_data[0])

    if ax is None:
        _figure, ax = plt.subplots(figsize=(7.5, 8.5))
    ax.figure.set_facecolor(theme.surface)
    ax.set_facecolor(theme.surface)

    # Two states, two colours, no interpolation — every cell is one angle pair and smoothing
    # between them would invent clearance that was never computed.
    ax.imshow(image, cmap=ListedColormap([theme.collision, theme.clear]), vmin=0, vmax=1,
              origin="upper", aspect="auto", interpolation="nearest")

    _label_axes(ax, theme, tick_every)

    if title:
        ax.set_title(title, color=theme.ink, fontsize=11, pad=10, loc="left")

    # A legend always, so the two states are named rather than inferred from colour.
    ax.legend(handles=[Patch(facecolor=theme.clear, label="Clear"),
                       Patch(facecolor=theme.collision, label="Collision")],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False,
              labelcolor=theme.ink, fontsize=9)
    return ax


def overlay_beams(ax, arc_plots, static_plots, beams=None, dark=False):
    """Draw beams on a clearance map, as :func:`maprt_workshop.check_beams` returns them.

    ``arc_plots`` and ``static_plots`` are its ``ArcSegment`` / ``StaticBeamPlot`` tuples, already
    in the map's index space. Pass ``beams`` — the checked beam records — to mark each static
    beam's verdict by shape.

    Verdicts are **shape, not colour**: a filled circle passes, an X fails. An arc that wraps the
    gantry-180 seam arrives as two segments and is drawn as two lines, because a single line from
    start to stop would run backwards through the rows the arc never visits.
    """
    from matplotlib.lines import Line2D

    theme = Theme(dark)

    for segment in arc_plots:
        ax.plot([segment.couch, segment.couch], [segment.start, segment.stop],
                color=theme.ink, linewidth=2, solid_capstyle="butt", zorder=3)

    statuses = _statuses_for(static_plots, beams)
    for plot, passed in zip(static_plots, statuses, strict=True):
        # markeredgecolor in the surface colour is the 2px ring that keeps a mark legible where it
        # crosses a line or another mark. A border for its own sake would just add ink.
        ax.plot(plot.couch, plot.gantry,
                marker="o" if passed is not False else "X",
                markersize=9, markerfacecolor=theme.ink if passed is not False else theme.surface,
                markeredgecolor=theme.ink, markeredgewidth=1.6, zorder=4,
                linestyle="none")

    handles = [Line2D([], [], color=theme.ink, linewidth=2, label="Arc")]
    if any(s is not False for s in statuses):
        handles.append(Line2D([], [], marker="o", linestyle="none", markersize=9,
                              markerfacecolor=theme.ink, markeredgecolor=theme.ink,
                              label="Beam: clear"))
    if any(s is False for s in statuses):
        handles.append(Line2D([], [], marker="X", linestyle="none", markersize=9,
                              markerfacecolor=theme.surface, markeredgecolor=theme.ink,
                              label="Beam: collision"))

    existing = ax.get_legend()
    previous = list(existing.legend_handles) if existing else []
    ax.legend(handles=previous + handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
              frameon=False, labelcolor=theme.ink, fontsize=9)
    return ax


def plot_surface(vertices, faces, ax=None, dark=False, stride=4, title=None):
    """A quick look at a patient surface mesh, for checking it loaded and is the right way up.

    Draws a decimated wireframe-free triangular surface. ``stride`` subsamples the faces, because
    a 19,200-face mesh takes a while to render and the shape is legible from a fraction of it.
    This is a sanity check, not a 3D viewer — use the real thing when the geometry matters.
    """
    import matplotlib.pyplot as plt

    theme = Theme(dark)
    if ax is None:
        _figure = plt.figure(figsize=(9, 4.5))
        ax = _figure.add_subplot(projection="3d")
    ax.figure.set_facecolor(theme.surface)

    ax.plot_trisurf(vertices[:, 0], vertices[:, 1], vertices[:, 2],
                    triangles=faces[::stride], color="#9ec5f4", edgecolor="none",
                    linewidth=0, antialiased=True, alpha=0.95)

    ax.set_xlabel("x (mm)", color=theme.muted, fontsize=9)
    ax.set_ylabel("y (mm)", color=theme.muted, fontsize=9)
    ax.set_zlabel("z (mm)", color=theme.muted, fontsize=9)
    ax.tick_params(colors=theme.muted, labelsize=8)
    # Equal aspect, or a 1.8 m body squashed into a cube reads as a completely different shape.
    ax.set_box_aspect(np.ptp(vertices, axis=0))
    if title:
        ax.set_title(title, color=theme.ink, fontsize=11, loc="left")
    return ax


# -- internals --------------------------------------------------------------------------------

def _statuses_for(static_plots, beams):
    """One verdict per static plot: ``True``, ``False``, or ``None`` when it is not known.

    ``check_beams`` returns static plots in the order it met the static beams, so the two line up
    positionally — but only after the arcs are filtered out of ``beams``. Zipping the raw beam
    list against the static plots would pair a static beam's marker with an arc's verdict as soon
    as a plan mixes the two, which every real plan does.

    ``None`` where a verdict is unavailable, drawn like a pass: a plot asked for without beams is
    showing geometry, and marking it all as failing would be a lie in the other direction.
    """
    if beams is None:
        return [None] * len(static_plots)
    static_beams = [b for b in beams if getattr(b, "gantry_rotation", "NONE") == "NONE"]
    if len(static_beams) != len(static_plots):
        # Rather than silently mispairing, say nothing about the verdicts.
        return [None] * len(static_plots)
    return [getattr(b, "status", None) for b in static_beams]


def _trimmed(image):
    """A map cropped to the 181 couch columns the axis labels describe.

    A coarse map upsamples to 185 columns, four of them a trailing repeat of couch 90 (see
    :func:`maprt_workshop.wire.parse_collision_map`). Drawing all 185 against 181 labelled angles
    would put every tick slightly in the wrong place — a small error that quietly misreads the
    plot rather than looking broken.
    """
    return image[:, :len(COUCH_VALUES)]


def _label_axes(ax, theme, tick_every):
    column_positions = [i for i, value in enumerate(COUCH_VALUES) if value % tick_every == 0]
    row_positions = [i for i, value in enumerate(GANTRY_VALUES) if value % tick_every == 0]

    ax.set_xticks(column_positions)
    ax.set_xticklabels([str(COUCH_VALUES[i]) for i in column_positions])
    ax.set_yticks(row_positions)
    ax.set_yticklabels([str(GANTRY_VALUES[i]) for i in row_positions])

    # A little air beyond the data, so a beam marker sitting on an extreme angle — couch 90,
    # gantry 180 — is drawn whole rather than sliced in half by the axis. Those extremes are
    # exactly where the interesting beams live, so clipping them loses the ones that matter.
    ax.set_xlim(-0.5 - len(COUCH_VALUES) * 0.015, len(COUCH_VALUES) - 0.5 + len(COUCH_VALUES) * 0.015)
    ax.set_ylim(len(GANTRY_VALUES) - 0.5 + len(GANTRY_VALUES) * 0.015,
                -0.5 - len(GANTRY_VALUES) * 0.015)

    ax.set_xlabel("Couch angle (deg, IEC 61217)", color=theme.muted, fontsize=9)
    ax.set_ylabel("Gantry angle (deg, IEC 61217)", color=theme.muted, fontsize=9)
    ax.tick_params(colors=theme.muted, labelsize=8, length=0)

    # Recessive chrome: hairline grid, no box. The data is the ink that matters.
    ax.grid(which="major", color=theme.grid, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
