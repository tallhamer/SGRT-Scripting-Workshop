"""The clearance-map plot: axis alignment, the two-state encoding, and the beam overlay.

A plot test cannot check that a chart looks good. It can check the things that make a chart
*wrong*: labels that do not match the data under them, a verdict carried by colour alone, and a
coarse map drawn against the wrong axis.
"""

from dataclasses import dataclass

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")           # no display in CI; must be set before pyplot is imported

import matplotlib.pyplot as plt  # noqa: E402

from maprt_workshop import check_beams, wire  # noqa: E402
from maprt_workshop.plotting import (  # noqa: E402
    COUCH_VALUES,
    GANTRY_VALUES,
    Theme,
    _statuses_for,
    overlay_beams,
    plot_collision_map,
    plot_surface,
)


@dataclass
class Beam:
    couch: str
    gantry_start: str
    gantry_stop: str
    gantry_rotation: str
    delivery_type: str
    status: object = None


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def map_stream(couch_angles, gantry_angles, is_safe=lambda c, g: 1):
    lines = [f"{len(couch_angles)},{len(gantry_angles)}"]
    for g in gantry_angles:
        for c in couch_angles:
            lines.append(f"{c},{g},{is_safe(c, g)}")
    lines.append("DONE")
    return "\n".join(lines)


def high_res(is_safe=lambda c, g: 1):
    return wire.parse_collision_map(map_stream(list(COUCH_VALUES), list(GANTRY_VALUES), is_safe))


def coarse(is_safe=lambda c, g: 1):
    couch = list(range(270, 360, 5)) + list(range(0, 91, 5))
    gantry = list(range(180, 360, 10)) + list(range(0, 180, 10))
    return wire.parse_collision_map(map_stream(couch, gantry, is_safe))


class TestAxisLabelsMatchTheData:
    """The failure mode that silently misreads a plot rather than looking broken."""

    def test_the_couch_axis_is_labelled_270_to_90(self):
        ax = plot_collision_map(high_res())
        labels = [t.get_text() for t in ax.get_xticklabels()]
        assert labels[0] == "270"
        assert labels[-1] == "90"

    def test_the_gantry_axis_starts_at_180(self):
        ax = plot_collision_map(high_res())
        assert [t.get_text() for t in ax.get_yticklabels()][0] == "180"

    def test_a_tick_sits_at_the_index_its_angle_occupies(self):
        ax = plot_collision_map(high_res(), tick_every=30)
        for position, label in zip(ax.get_xticks(), ax.get_xticklabels(), strict=True):
            assert str(COUCH_VALUES[int(position)]) == label.get_text()
        for position, label in zip(ax.get_yticks(), ax.get_yticklabels(), strict=True):
            assert str(GANTRY_VALUES[int(position)]) == label.get_text()

    def test_a_coarse_map_is_trimmed_to_the_labelled_width(self):
        # A coarse map parses to 185 columns, four of them a trailing repeat of couch 90. Drawn
        # at 185 against 181 labelled angles, every tick lands slightly wrong — a plot that
        # misleads instead of failing.
        image, _x, _y = coarse()
        assert image.shape[1] == 185
        ax = plot_collision_map(coarse())
        assert ax.images[0].get_array().shape[1] == len(COUCH_VALUES) == 181

    def test_a_blocked_angle_is_drawn_where_its_label_says(self):
        ax = plot_collision_map(high_res(lambda c, g: 0 if (c, g) == (300, 200) else 1))
        drawn = ax.images[0].get_array()
        column = int(np.flatnonzero(COUCH_VALUES == 300)[0])
        row = int(np.flatnonzero(GANTRY_VALUES == 200)[0])
        assert drawn[row, column] == 0
        assert drawn.sum() == drawn.size - 1


class TestEdgeMarkersAreNotClipped:
    def test_the_axes_extend_past_the_data(self):
        # A beam at couch 90 or gantry 180 sits on the very edge, and those extremes are exactly
        # where the interesting beams live — a marker sliced in half by the axis loses the ones
        # that matter.
        ax = plot_collision_map(high_res())
        left, right = ax.get_xlim()
        assert left < -0.5 and right > len(COUCH_VALUES) - 0.5
        bottom, top = ax.get_ylim()
        assert top < -0.5 and bottom > len(GANTRY_VALUES) - 0.5

    def test_the_gantry_axis_still_runs_downwards(self):
        # imshow's origin="upper" puts gantry 180 at the top; padding must not flip it.
        bottom, top = plot_collision_map(high_res()).get_ylim()
        assert bottom > top


class TestTheTwoStateEncoding:
    def test_collision_and_clear_are_the_only_two_colours(self):
        ax = plot_collision_map(high_res())
        assert ax.images[0].cmap.N == 2

    def test_clear_is_the_receding_colour_and_collision_the_strong_one(self):
        # The signal is the collision region; clear space should get out of the way. If these
        # ever swap, the plot shouts about the safe angles instead.
        theme = Theme()
        colours = ax_colours(plot_collision_map(high_res()))
        assert colours == [theme.collision, theme.clear]     # index 0 = collision, 1 = clear

    def test_it_is_not_red_green(self):
        # A red/green clearance map is the conventional look and the wrong choice for a tool that
        # decides deliverability: red-green CVD affects ~8% of men, which in a physics department
        # is not a hypothetical reader.
        for colour in ax_colours(plot_collision_map(high_res())):
            red, green, blue = matplotlib.colors.to_rgb(colour)
            assert not (green > red and green > blue), f"{colour} is a green state colour"

    def test_no_interpolation_between_cells(self):
        # Each cell is one computed angle pair. Smoothing between them would draw clearance that
        # was never evaluated.
        assert plot_collision_map(high_res()).images[0].get_interpolation() == "nearest"

    def test_both_states_are_named_in_a_legend(self):
        # So the meaning never rests on colour alone.
        ax = plot_collision_map(high_res())
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert "Clear" in labels and "Collision" in labels


def ax_colours(ax):
    return [matplotlib.colors.to_hex(c) for c in ax.images[0].cmap(range(2))]


class TestBeamOverlay:
    def build(self, beams):
        map_data = high_res(lambda c, g: 0 if 60 <= g <= 120 else 1)
        checked, arcs, statics = check_beams(beams, map_data, 1)
        ax = plot_collision_map(map_data)
        overlay_beams(ax, arcs, statics, checked)
        return ax, checked

    def test_a_static_beam_is_drawn_at_its_angle(self):
        ax, _ = self.build([Beam("0", "0", "0", "NONE", "TREATMENT")])
        marks = [line for line in ax.lines if line.get_linestyle() == "None"]
        assert len(marks) == 1
        assert marks[0].get_xdata()[0] == int(np.flatnonzero(COUCH_VALUES == 0)[0])

    def test_a_passing_beam_is_a_circle_and_a_failing_one_an_X(self):
        # Verdicts ride on SHAPE, not colour — so they survive any colour vision, greyscale
        # printing and a projector with the contrast turned down. All three happen at a workshop.
        ax, checked = self.build([Beam("0", "0", "0", "NONE", "TREATMENT"),
                                  Beam("0", "90", "90", "NONE", "TREATMENT")])
        assert [b.status for b in checked] == [True, False]
        markers = [line.get_marker() for line in ax.lines if line.get_linestyle() == "None"]
        assert markers == ["o", "X"]

    def test_an_arc_is_drawn_as_a_line(self):
        ax, _ = self.build([Beam("0", "181", "179", "CW", "TREATMENT")])
        assert any(line.get_linestyle() != "None" for line in ax.lines)

    @pytest.mark.parametrize("start,stop,direction", [
        ("170", "190", "CW"),      # crosses gantry 180
        ("90", "270", "CW"),
        ("190", "170", "CC"),
    ])
    def test_an_arc_wrapping_the_seam_is_drawn_as_two_segments(self, start, stop, direction):
        # One line from start to stop would run backwards through the rows the arc never visits.
        #
        # The seam is at **gantry 180**, not gantry 0. The display rows run 180...359 then
        # 0...179, so gantry 359 and gantry 0 are adjacent rows and an arc across them needs no
        # second segment — my first attempt at this test used 350->10 and asserted two.
        ax, _ = self.build([Beam("0", start, stop, direction, "TREATMENT")])
        lines = [line for line in ax.lines if line.get_linestyle() != "None"]
        assert len(lines) == 2

    def test_an_arc_crossing_gantry_zero_needs_only_one_segment(self):
        # The other half of the lesson above: gantry 0 is *not* the seam.
        ax, _ = self.build([Beam("0", "350", "10", "CW", "TREATMENT")])
        lines = [line for line in ax.lines if line.get_linestyle() != "None"]
        assert len(lines) == 1

    def test_the_legend_names_the_beam_kinds_present(self):
        ax, _ = self.build([Beam("0", "0", "0", "NONE", "TREATMENT"),
                            Beam("0", "90", "90", "NONE", "TREATMENT"),
                            Beam("0", "181", "179", "CW", "TREATMENT")])
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert {"Clear", "Collision", "Arc", "Beam: clear", "Beam: collision"} <= set(labels)

    def test_the_map_legend_is_not_lost_when_beams_are_added(self):
        ax, _ = self.build([Beam("0", "0", "0", "NONE", "TREATMENT")])
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert "Clear" in labels

    def test_beams_can_be_drawn_without_verdicts(self):
        map_data = high_res()
        _checked, arcs, statics = check_beams([Beam("0", "0", "0", "NONE", "TREATMENT")],
                                              map_data, 1)
        ax = plot_collision_map(map_data)
        overlay_beams(ax, arcs, statics)        # no beams argument
        assert len(ax.lines) == 1


class TestStatusPairing:
    """`_statuses_for` is the part that can silently mislabel a plot."""

    def test_arcs_are_excluded_so_statics_line_up(self):
        # Zipping the raw beam list against the static plots pairs a static marker with an arc's
        # verdict the moment a plan mixes the two — which every real plan does.
        beams = [Beam("0", "181", "179", "CW", "TREATMENT", status=False),
                 Beam("0", "0", "0", "NONE", "TREATMENT", status=True)]
        statics = [object()]        # one static beam, so one static plot
        assert _statuses_for(statics, beams) == [True]

    def test_no_beams_means_no_claims(self):
        assert _statuses_for([object(), object()], None) == [None, None]

    def test_a_count_mismatch_says_nothing_rather_than_mispairing(self):
        beams = [Beam("0", "0", "0", "NONE", "TREATMENT", status=True)]
        assert _statuses_for([object(), object()], beams) == [None, None]


class TestThemes:
    def test_dark_mode_has_its_own_steps_not_an_inversion(self):
        light, dark = Theme(dark=False), Theme(dark=True)
        assert light.surface != dark.surface
        assert light.clear != dark.clear
        # The collision colour is mode-invariant: it clears 3:1 on both surfaces, so there is no
        # reason to shift it and shifting it would weaken the one state that must not be missed.
        assert light.collision == dark.collision

    def test_a_dark_plot_uses_the_dark_surface(self):
        ax = plot_collision_map(high_res(), dark=True)
        assert matplotlib.colors.to_hex(ax.get_facecolor()) == Theme(dark=True).surface


class TestSurfacePlot:
    def test_draws_a_mesh_with_equal_aspect(self):
        from pathlib import Path

        from maprt_workshop.obj import parse_obj
        root = Path(__file__).resolve().parent.parent
        path = next((root / "data" / "surfaces").glob("*.obj"))
        vertices, faces, _normals = parse_obj(path.read_bytes())
        ax = plot_surface(vertices, faces, stride=40)
        # Equal aspect, or a 1.8 m body squashed into a cube reads as a different shape entirely.
        assert np.allclose(ax.get_box_aspect() / ax.get_box_aspect()[0],
                           np.ptp(vertices, axis=0) / np.ptp(vertices, axis=0)[0])
