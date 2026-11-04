#!/usr/bin/env python3
"""Check the legend's fallback, where no shape fits without covering a line (batch 24.1).

* what a line counts (``occupancy._line_busy_points``): a change where it
  has moved a pixel on the way it last went, a reversal (also a change)
  where it has come back 2 px from the furthest it went; nothing for a line
  drawn flat, for jitter under a pixel or for a zigzag under 2 px;
* ``Raster.count_points``: points in one cell add up, points outside the
  axes are left out;
* the order of the tiers (``legend._least_busy_position``): the labels'
  cells, then reversals, then changes, then occupied cells, and the first
  position where all are alike;
* a made-up chart where no shape fits: a jagged half and a flat half with
  more ink. The legend goes over the flat half (before 24.1 it took the
  jagged half, which has fewer occupied cells), drawn on the twin axis so
  that no curve crosses it;
* the legend's background at 0.7 (36.2);
* room made for the legend (36.3): which limits may move; every axis moved by
  the same share of its height, on its own scale; a little of a line under
  the see-through legend taken as it is; a made-up chart where nothing fits:
  the limits move, or not where they are set, the legend then covers no line,
  and the zoom's geometry reads the moved limits; the labels placed again on
  the moved limits, none left behind, the pieces as fitted.

No network and no data: lines and rasters are made up.

Usage (from the project root)::

    python tools/check_legend_fallback.py

Exit code 1 on any FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import verify_charts  # noqa: E402,F401  (unused but first: it sets the Agg backend before pyplot is imported)

del verify_charts
from dataclasses import replace  # noqa: E402

import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import IdentityTransform  # noqa: E402

from ratesplot import export, hover, legend, occupancy  # noqa: E402
from ratesplot.config import PlotConfig  # noqa: E402
from ratesplot.frontend import ChartGeometry  # noqa: E402
from ratesplot.regression import RateLabel  # noqa: E402


def check_counting(check) -> None:
    """What a line counts: its visible changes and reversals of direction"""
    cases = [
        ("flat", [5, 5, 5, 5], [], []),
        ("jitter under a pixel", [5, 5.4, 4.7, 5.3, 4.8, 5.2], [], []),
        ("a slow rise adds up, a change a pixel", [0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4], [3, 6], []),
        ("one step, any height, one change", [0, 0, 30, 30, 30], [2], []),
        ("a zigzag of 2 px", [0, 2, 0, 2, 0], [1, 2, 3, 4], [2, 3, 4]),
        ("a zigzag of 1 px", [0, 1, 0, 1, 0], [1], []),
        ("a zigzag of 1.8 px", [0, 1, 1.9, 0.1, 1.9, 0.1], [1], []),
        ("a zigzag of 2.5 px", [0, 1, 2.5, 0, 2.5], [1, 2, 3, 4], [3, 4]),
        ("a turn of 1.1 px after an overshoot", [0, 1, 1.5, 0.4], [1], []),
        ("a turn short of 2 px, then on past it", [0, 1, 1.5, 0.6, -0.6], [1, 4], [4]),
        ("a gap (NaN) left out", [0, np.nan, 3, 0], [2, 3], [3]),
        ("one point", [1], [], []),
    ]
    for name, ys, changes_at, reversals_at in cases:
        line = Line2D(np.arange(len(ys), dtype=float), np.asarray(ys, dtype=float))
        changes, reversals = occupancy._line_busy_points(line, IdentityTransform())  # display = data
        got = (changes[:, 0].astype(int).tolist(), reversals[:, 0].astype(int).tolist())
        check(name, got == (changes_at, reversals_at), f"changes at {got[0]}, reversals at {got[1]}")


def check_count_points(check) -> None:
    """Raster.count_points: counts per cell"""
    raster = occupancy.Raster(0.0, 0.0, 2, 2, 1, np.zeros((4, 4), dtype=np.int32))
    raster.count_points(np.array([[1.0, 1.0], [2.0, 2.0], [5.0, 1.0], [-3.0, 1.0], [9.0, 9.0]]))
    expected = np.zeros((4, 4), dtype=np.int32)
    expected[1, 1] = 2  # two points in cell (0, 0), behind the one cell of padding
    expected[1, 2] = 1  # one in cell (0, 1); the two outside the axes left out
    check("two points in one cell count two, those outside none", (raster.cells == expected).all(), raster.cells.tolist())


def _tiers(*rows: list[int]) -> list[occupancy.OccupancyGrid]:
    """One-row grids, a cell per position for a 1 x 1 box."""
    return [
        occupancy.OccupancyGrid.from_raster(occupancy.Raster(0.0, 0.0, 1, len(row), 0, np.array([row], dtype=np.int32)))
        for row in rows
    ]


def check_tier_order(check) -> None:
    """The tiers compared in turn: labels, reversals, changes, occupied cells"""
    tiers = _tiers(
        [1, 0, 0, 0, 0],  # labels: not the first
        [0, 1, 0, 0, 0],  # reversals: not the second
        [0, 0, 5, 3, 3],  # changes: not the third
        [1, 1, 1, 1, 0],  # occupied: the fifth, not the fourth
    )
    counts, row, col = legend._least_busy_position(tiers, 1, 1, 0)
    check("the least of each tier in turn", (counts, row, col) == ((0, 0, 3, 0), 0, 4), (counts, row, col))
    tiers = _tiers([0, 0, 0], [9, 0, 9], [0, 7, 0], [1, 1, 1])
    counts, row, col = legend._least_busy_position(tiers, 1, 1, 0)
    check("fewer reversals before fewer changes", col == 1, (counts, row, col))
    tiers = _tiers([0, 0, 0], [2, 2, 2], [4, 4, 4], [1, 1, 1])
    counts, row, col = legend._least_busy_position(tiers, 1, 1, 0)
    check("where all are alike, the first position", col == 0, (counts, row, col))


def check_made_up_chart(check) -> None:
    """A made-up chart where no shape fits: the legend over the flat half, on the twin axis"""
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    twin = ax.twinx()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    twin.set_ylim(0, 100)
    handles = []
    for level in range(10, 100, 10):
        # The left half jagged (a zigzag of about 4 px, two cells high); the
        # right half flat, but three lines 1 unit (about 4.6 px) apart, three
        # cells high: more ink, nothing busy.
        x = np.arange(0.0, 50.0, 0.25)
        (jagged,) = ax.plot(x, level + 0.4 * (-1) ** np.arange(len(x)), color="C0", linewidth=1, label=f"Jagged {level}")
        for offset in (-1, 0, 1):
            twin.plot([50, 100], [level + offset] * 2, color="C1", linewidth=1)
        if level <= 40:
            handles.append(jagged)
    drawn = legend.auto_place_legend(ax, [handles], 1.0)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    box = drawn.get_window_extent(renderer)
    middle = ax.get_window_extent(renderer).intervalx.mean()
    # The line cells under the drawn legend, on the grid the placement uses.
    raster = occupancy.Raster.from_axes(ax, occupancy.collect_display_samples(ax))
    corners, _inside = raster.cells_at(np.array([[box.x0, box.y0], [box.x1, box.y1]]))
    (row0, col0), (row1, col1) = corners.tolist()
    covered = int(raster.cells[max(row0, 0) : row1 + 1, max(col0, 0) : col1 + 1].sum())
    check("the legend covers line cells: no shape fits without (the fallback)", covered > 0, covered)
    check("the legend over the flat half", box.x0 >= middle, f"legend from x {box.x0:.0f}, middle {middle:.0f}")
    check("on the twin axis, drawn after every curve", drawn.axes is twin and figure.axes[-1] is twin, drawn.axes)


def check_alpha(check) -> None:
    """The legend's background at 0.7 (36.2)"""
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    (line,) = ax.plot([0, 1], [0, 1], label="A line")
    drawn = legend.auto_place_legend(ax, [[line]], 1.0)
    check("framealpha 0.7", drawn.get_frame().get_alpha() == 0.7, drawn.get_frame().get_alpha())


def check_side_to_move(check) -> None:
    """Which limits may move: the upper if all are automatic, else the lower if all are (36.3)"""
    start, end = pd.Timestamp("2000-01-01"), pd.Timestamp("2020-01-01")
    both = {"start": start, "end": end}  # the defaults draw both axes
    cases = [
        ("all blank: the upper", {}, "top"),
        ("Max set: the lower", {"yield_ymax": 5.0}, "bottom"),
        ("Top set: the lower", {"macro_top": 1e12}, "bottom"),
        ("Min set: the upper", {"yield_ymin": 0.0}, "top"),
        ("Bottom set: the upper", {"macro_bottom": 1e9}, "top"),
        ("Max and Min set: neither", {"yield_ymax": 5.0, "yield_ymin": 0.0}, None),
        ("Top and Bottom set: neither", {"macro_top": 1e12, "macro_bottom": 1e9}, None),
        ("Max and Bottom set: neither", {"yield_ymax": 5.0, "macro_bottom": 1e9}, None),
        ("Max and Top set: the lower", {"yield_ymax": 5.0, "macro_top": 1e12}, "bottom"),
    ]
    for name, values, expected in cases:
        config = PlotConfig(**both, **values)
        got = legend._side_to_move(config)
        check(name, got == expected, got)
    # A limit counts only on an axis that takes it: no right-axis curve, so Top is idle.
    config = replace(PlotConfig(**both, macro_top=1e12), include_debt=False, include_gdp=False, include_interest=False)
    check("Top set with no right-axis curve: the upper", not config.has_macro_series and legend._side_to_move(config) == "top", legend._side_to_move(config))


def check_move_limits(check) -> None:
    """Every axis moved by the same share of its height, on its own scale"""
    for side, share in (("top", 0.25), ("bottom", 0.25), ("top", 1.0)):
        figure = Figure(figsize=(8, 6), dpi=100)
        FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        twin = ax.twinx()
        ax.set_ylim(2.0, 6.0)
        twin.set_yscale("log")
        twin.set_ylim(10.0, 1000.0)
        points = {axis: (axis.get_ylim()[0] * 1.5, axis.get_ylim()[1] * 0.9) for axis in (ax, twin)}
        box = ax.get_window_extent(figure.canvas.get_renderer())
        before = {axis: axis.transData.transform([(0.5, value) for value in values])[:, 1] for axis, values in points.items()}
        kept = {axis: axis.get_ylim()[0 if side == "top" else 1] for axis in (ax, twin)}
        legend._move_limits(figure, share, side)
        for axis, name in ((ax, "linear"), (twin, "log")):
            after = axis.transData.transform([(0.5, value) for value in points[axis]])[:, 1]
            expected = legend._squeezed(before[axis], box, share, side)
            check(f"{side} by {share}, {name}: as squeezed", np.allclose(after, expected, atol=1e-6), (after, expected))
            check(f"{side} by {share}, {name}: the far limit kept", axis.get_ylim()[0 if side == "top" else 1] == kept[axis], axis.get_ylim())


def _rising_chart(**values) -> tuple[Figure, object, object, list, PlotConfig]:
    """A chart whose curves leave no legend-sized gap: lines across the whole height, one more over the top."""
    start, end = pd.Timestamp("2000-01-01"), pd.Timestamp("2020-01-01")
    config = PlotConfig(start=start, end=end, **values)
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    twin = ax.twinx()
    twin.set_yscale("log")
    dates = pd.date_range(start, end, periods=120)
    handles = []
    for index, level in enumerate(np.linspace(1.0, 9.0, 14)):
        (line,) = ax.plot(dates, level + 0.3 * np.sin(np.arange(120) / 3 + index), color=f"C{index % 10}", linewidth=1, label=f"Yield {index}")
        handles.append(line)
    (amount,) = twin.plot(dates, 10 ** np.linspace(1.0, 3.0, 120), color="black", label="An amount")
    ax.set_ylim(0.5, 9.5)
    twin.set_ylim(8.0, 1200.0)
    ax.set_xlim(start, end)
    return figure, ax, twin, [handles, [amount]], config


def _line_cells_under(figure: Figure, ax, drawn) -> int:
    """The cells of lines under the drawn legend, on the grid the placement uses."""
    renderer = figure.canvas.get_renderer()
    box = drawn.get_window_extent(renderer)
    raster = occupancy.Raster.from_axes(ax, occupancy.collect_display_samples(ax))
    corners, _inside = raster.cells_at(np.array([[box.x0, box.y0], [box.x1, box.y1]]))
    (row0, col0), (row1, col1) = corners.tolist()
    return int(raster.cells[max(row0, 0) : row1 + 1, max(col0, 0) : col1 + 1].sum())


def check_room(check) -> None:
    """Room made for the legend: only as a last resort, free of the lines, on the side the limits allow"""
    figure, ax, twin, groups, config = _rising_chart()
    limits = (ax.get_ylim(), twin.get_ylim())
    drawn = legend.finish_legend_and_title(ax, groups, "A title", config, None) or ax.figure.axes[-1].get_legend()
    check("all blank: the upper limits rise", ax.get_ylim()[1] > limits[0][1] and twin.get_ylim()[1] > limits[1][1], (ax.get_ylim(), twin.get_ylim()))
    check("the lower limits stay", ax.get_ylim()[0] == limits[0][0] and twin.get_ylim()[0] == limits[1][0], (ax.get_ylim(), twin.get_ylim()))
    share_left = (ax.get_ylim()[1] - ax.get_ylim()[0]) / (limits[0][1] - limits[0][0]) - 1
    share_right = np.log(twin.get_ylim()[1] / twin.get_ylim()[0]) / np.log(limits[1][1] / limits[1][0]) - 1
    check("both by the same share of their height", np.isclose(share_left, share_right), (share_left, share_right))
    check("not more than the curves' half of the height", share_left <= 1.0 + 1e-9, share_left)
    figure.canvas.draw()
    check("the legend covers no line", _line_cells_under(figure, ax, drawn) == 0, _line_cells_under(figure, ax, drawn))

    geometry = ChartGeometry.from_figure(figure, config)
    check("the zoom reads the moved limits", geometry.left_ylim == tuple(ax.get_ylim()) and geometry.right_ylim == tuple(twin.get_ylim()), geometry)
    top = geometry.box[1]
    check("the value at the top of the picture is the new limit", np.isclose(geometry.value_at(top, "left"), ax.get_ylim()[1]), geometry.value_at(top, "left"))
    check("on the log axis too", np.isclose(geometry.value_at(top, "right"), twin.get_ylim()[1]), geometry.value_at(top, "right"))
    amount = groups[1][0]
    hover.mark(export.mark_series(amount, amount.get_label(), export.MACRO_AXIS), str)
    read = next((curve for curve in hover.chart_lines(figure).curves if curve.name == amount.get_label()), None)
    expected = figure.bbox.height - twin.transData.transform(amount.get_xydata()[-1])[1]
    check("the hover read-out's line is where the moved limits put it", read is not None and np.isclose(read.runs[-1].y[-1], expected, atol=0.1), read)

    figure, ax, twin, groups, config = _rising_chart()
    figure.canvas.draw()
    # At this canvas's size a legend at the chart's font scale takes more than the height allows.
    search = legend._search_shapes(ax, groups, 1.0, ())
    too_tall = legend._room_share(ax, search.crowded, (), "top", 1.0, 1.0 - legend._ROOM_CURVES_KEEP)
    check("a legend too tall to leave the curves half the height: no share", search.best is None and too_tall is None, too_tall)
    crowded = legend._search_shapes(ax, groups, 0.6, ()).crowded
    least = legend._room_share(ax, crowded, (), "top", 0.6, 1.0 - legend._ROOM_CURVES_KEEP)
    check("a smaller one: a share", least is not None and least > 0, least)
    freed = least / (1.0 + least)
    check("no share where less than that may be freed", legend._room_share(ax, crowded, (), "top", 0.6, freed - legend._ROOM_STEP) is None, freed)
    check("the same share where just that may be", np.isclose(legend._room_share(ax, crowded, (), "top", 0.6, freed), least), freed)

    figure, ax, twin, groups, config = _rising_chart(yield_ymax=9.5)
    limits = (ax.get_ylim(), twin.get_ylim())
    legend.finish_legend_and_title(ax, groups, "A title", config, None)
    check("Max set: the upper limits stay", ax.get_ylim()[1] == limits[0][1] and twin.get_ylim()[1] == limits[1][1], (ax.get_ylim(), twin.get_ylim()))
    check("and the lower ones move", ax.get_ylim()[0] < limits[0][0] and twin.get_ylim()[0] < limits[1][0], (ax.get_ylim(), twin.get_ylim()))

    figure, ax, twin, groups, config = _rising_chart(yield_ymax=9.5, yield_ymin=0.5)
    limits = (ax.get_ylim(), twin.get_ylim())
    drawn = legend.finish_legend_and_title(ax, groups, "A title", config, None) or ax.figure.axes[-1].get_legend()
    check("Max and Min set: no limit moves", (ax.get_ylim(), twin.get_ylim()) == limits, (ax.get_ylim(), twin.get_ylim()))
    check("and the legend goes over the lines, the least busy place", _line_cells_under(figure, ax, drawn) > 0, _line_cells_under(figure, ax, drawn))


def check_minor(check) -> None:
    """A little of a line under the see-through legend is taken as it is, and no room made"""
    # One row of five positions for a 1 x 1 box: labels, reversals, changes, occupied.
    tiers = _tiers([0, 0, 0, 1, 0], [5, 0, 0, 0, 0], [5, 0, 0, 0, 0], [3, 20, 13, 1, 12])
    shape = legend._Shape([], 2, 16.0, 1, 1)
    found = legend._minor_cover(tiers, [shape], 0)
    check("within the limit, no label, the least busy", found is not None and found.col == 4, found)
    tiers = _tiers([1, 1, 0], [0, 0, 0], [0, 0, 0], [3, 3, legend._MINOR_COVER_CELLS + 1])
    check("over a label or past the limit: none", legend._minor_cover(tiers, [shape], 0) is None)
    tiers = _tiers([0], [0], [0], [5])
    other = legend._Shape([], 3, 14.0, 1, 1)
    found = legend._minor_cover(tiers, [shape, other], 0)
    check("the first shape in preference order", found is not None and found.ncols == 2, found)

    # Room is asked for only where it is needed.
    asked = []

    def make(share: float) -> list:
        asked.append(share)
        return []

    room = legend._Room("top", make)
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    (line,) = ax.plot([0, 1], [0, 1], label="A line")
    legend.auto_place_legend(ax, [[line]], 1.0, (), room)
    check("none where the legend fits free", not asked, asked)

    # Lines closer together than the smallest legend is tall, each wider than the limit under it.
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    lines = [ax.plot([0, 100], [level, level], color="C0", linewidth=1, label=f"Line {level}")[0] for level in range(0, 100, 4)]
    legend.auto_place_legend(ax, [lines[:1]], 1.0, (), room)
    check("where every place covers a line: room is asked for", bool(asked), asked)


def check_labels_placed_again(check) -> None:
    """The labels placed once more on the moved limits, none left behind, the pieces unchanged"""
    figure, ax, twin, groups, config = _rising_chart()
    line = groups[1][0]
    end_labels = [(line, lambda value: f"${value:.0f}")]
    (piece,) = twin.plot(line.get_xdata()[[0, -1]], line.get_ydata()[[0, -1]], label="_regression", color="grey")
    rate_labels = [RateLabel(piece, "+10.0%/yr", "black")]
    fitted = np.asarray(piece.get_xydata(), dtype=float).copy()
    limits = twin.get_ylim()
    legend.finish_legend_and_title(ax, groups, "A title", config, None, end_labels, rate_labels=rate_labels)
    check("the limits moved", twin.get_ylim() != limits, twin.get_ylim())
    texts = [text.get_text() for axis in figure.axes for text in axis.texts]
    check("one end label and one rate label, none left behind", sorted(texts) == sorted(["$1000", "+10.0%/yr"]), texts)
    check("the piece's data are as fitted", np.array_equal(np.asarray(piece.get_xydata(), dtype=float), fitted))
    check("the piece is still on its axis", piece in twin.get_lines())
    renderer = figure.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    label = next(text for text in twin.texts if text.get_text() == "$1000")
    end = twin.transData.transform((mdates.date2num(line.get_xdata()[-1]), line.get_ydata()[-1]))
    box = label.get_window_extent(renderer)
    check("the end label stands by the curve's end, on the moved limits", abs((box.y0 + box.y1) / 2 - end[1]) < 2 * box.height and box.x0 >= end[0], (box, end))
    check("inside the frame", box.y1 <= frame.y1 and box.x1 <= frame.x1, (box, frame))


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    for group in (
        check_counting, check_count_points, check_tier_order, check_made_up_chart, check_alpha, check_side_to_move,
        check_move_limits, check_minor, check_room, check_labels_placed_again,
    ):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group(check)
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[legend fallback] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
