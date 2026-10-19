"""The collision-map parser: the wire format, the display layout, and coarse-map upsampling.

This is the parser the whole workshop turns on, and the contract the emulator in `maprt_emulator` has
to satisfy. The builders here emit the GetMap wire format from scratch — a header line, triples,
then `DONE` — so these tests describe the format independently of any server.
"""

import numpy as np
import pytest

from maprt_workshop import wire

# The axes the parser lays the map out on: rows gantry 180..359 then 0..179 (360 of them),
# columns couch 270..359 then 0..90 (181 of them). Not the order the triples arrive in.
GANTRY_ROWS = np.hstack((np.arange(180, 360), np.arange(0, 180)))
COUCH_COLS = np.hstack((np.arange(270, 360), np.arange(0, 91)))


def map_stream(couch_angles, gantry_angles, is_safe=lambda couch, gantry: 1):
    """A GetMap response body for the given sampling.

    Header is ``couch_samples,gantry_samples``; then one ``couch,gantry,isOK`` triple per
    combination; then ``DONE``. Spec §5.2.6 orders the example with gantry fixed and couch
    descending, which is what this reproduces — though the spec also says the list is unordered.
    """
    lines = [f"{len(couch_angles)},{len(gantry_angles)}"]
    for gantry in gantry_angles:
        for couch in couch_angles:
            lines.append(f"{couch},{gantry},{is_safe(couch, gantry)}")
    lines.append("DONE")
    return "\n".join(lines)


def high_res_stream(is_safe=lambda couch, gantry: 1):
    """A 1-degree map: 181 couch angles x 360 gantry angles."""
    return map_stream(list(COUCH_COLS), list(GANTRY_ROWS), is_safe)


def coarse_stream(is_safe=lambda couch, gantry: 1):
    """The spec's own coarse sampling: 37 couch angles (5 deg) x 36 gantry angles (10 deg).

    The step sizes have to divide evenly, because the parser upsamples a coarse map to 1 degree
    by integer repetition: 360/36 = 10 and 180/(37-1) = 5.
    """
    couch = list(range(270, 360, 5)) + list(range(0, 91, 5))   # 18 + 19 = 37
    gantry = list(range(180, 360, 10)) + list(range(0, 180, 10))  # 18 + 18 = 36
    return map_stream(couch, gantry, is_safe)


class TestHighResolution:
    def test_shape_is_gantry_by_couch(self):
        image, _x, _y = wire.parse_collision_map(high_res_stream())
        assert image.shape == (360, 181)

    def test_an_all_safe_map_is_all_ones(self):
        image, _x, _y = wire.parse_collision_map(high_res_stream())
        assert image.min() == 1

    def test_a_single_blocked_angle_lands_at_the_display_index(self):
        def is_safe(couch, gantry):
            return 0 if (couch, gantry) == (300, 185) else 1

        image, _x, _y = wire.parse_collision_map(high_res_stream(is_safe))
        row = int(np.flatnonzero(GANTRY_ROWS == 185)[0])
        col = int(np.flatnonzero(COUCH_COLS == 300)[0])
        assert image[row, col] == 0
        assert image.sum() == image.size - 1   # exactly one cell blocked

    def test_gantry_rows_start_at_180_not_zero(self):
        # The display layout puts gantry 180 in row 0. Block gantry 0 and check it is NOT row 0.
        image, _x, _y = wire.parse_collision_map(
            high_res_stream(lambda couch, gantry: 0 if gantry == 0 else 1))
        assert image[0].min() == 1              # row 0 is gantry 180, untouched
        assert image[180].max() == 0            # gantry 0 is row 180, all blocked

    def test_couch_columns_run_270_then_0_to_90(self):
        image, _x, _y = wire.parse_collision_map(
            high_res_stream(lambda couch, gantry: 0 if couch == 270 else 1))
        assert image[:, 0].max() == 0           # couch 270 is column 0
        assert image[:, 90].min() == 1

    def test_triple_order_does_not_matter(self):
        # Spec §5.2.6: "The list is not ordered." Shuffle the body and the map must be identical.
        rng = np.random.default_rng(0)
        text = high_res_stream(lambda couch, gantry: 0 if gantry == 300 else 1)
        tokens = text.split()
        header, triples, done = tokens[0], tokens[1:-1], tokens[-1]
        rng.shuffle(triples)
        shuffled = " ".join([header, *triples, done])
        assert np.array_equal(wire.parse_collision_map(text)[0],
                              wire.parse_collision_map(shuffled)[0])


class TestCoarseResolution:
    def test_gantry_upsamples_to_exactly_360_rows(self):
        image, _x, _y = wire.parse_collision_map(coarse_stream())
        assert image.shape[0] == 360

    def test_the_couch_axis_overshoots_181_columns_and_that_is_expected(self):
        # A coarse map comes back WIDER than a high-resolution one: 37 couch samples repeated 5x
        # is 185 columns, where the 1-degree map has 181. This is not a sampling mistake, it is
        # arithmetic — the couch axis spans 180 degrees *inclusive*, so n samples at step s need
        # (n-1)*s == 180 to tile the axis but n*s == 181 to fill it, and no integer step above 1
        # satisfies both. Every coarse couch sampling therefore overshoots by exactly s-1 columns.
        #
        # So: do not assume a low-resolution and a high-resolution map have the same shape, and do
        # not read a couch angle out of a coarse map by slicing from the right-hand edge. The
        # extra columns are a trailing repeat of the last sample (couch 90).
        image, _x, _y = wire.parse_collision_map(coarse_stream())
        assert image.shape == (360, 185)

    def test_couch_columns_still_align_with_the_beam_check_index_space(self):
        # The overshoot is harmless where it matters, which is why it has survived in production:
        # repeating by s keeps every coarse block starting at a multiple of s, so couch angle
        # 270+k lands at column k for every k that is a multiple of s — exactly where
        # `check_beams` looks for it. The alignment, not the width, is the thing to protect.
        for couch_angle in (270, 300, 355, 0, 45, 90):
            image, _x, _y = wire.parse_collision_map(
                coarse_stream(lambda couch, gantry, t=couch_angle: 0 if couch == t else 1))
            expected = int(np.flatnonzero(COUCH_COLS == couch_angle)[0])
            assert image[:, expected].max() == 0, f"couch {couch_angle} is not at column {expected}"

    def test_a_blocked_coarse_cell_becomes_a_block_of_cells(self):
        # 10 degrees of gantry x 5 degrees of couch per coarse sample.
        image, _x, _y = wire.parse_collision_map(
            coarse_stream(lambda couch, gantry: 0 if (couch, gantry) == (300, 190) else 1))
        assert image.sum() == image.size - (10 * 5)

    def test_the_upsampled_block_starts_at_the_coarse_angle(self):
        image, _x, _y = wire.parse_collision_map(
            coarse_stream(lambda couch, gantry: 0 if (couch, gantry) == (300, 190) else 1))
        row = int(np.flatnonzero(GANTRY_ROWS == 190)[0])
        col = int(np.flatnonzero(COUCH_COLS == 300)[0])
        assert image[row:row + 10, col:col + 5].max() == 0
        assert image[row - 1, col] == 1


class TestTicks:
    @pytest.mark.parametrize("stream", [high_res_stream(), coarse_stream()])
    def test_tick_labels_are_index_label_pairs_every_ten_degrees(self, stream):
        _image, x_ticks, y_ticks = wire.parse_collision_map(stream)
        assert x_ticks[0][0] == (0, "270")       # couch axis starts at 270
        assert y_ticks[0][0] == (0, "180")       # gantry axis starts at 180
        assert x_ticks[0][1] == (10, "280")
