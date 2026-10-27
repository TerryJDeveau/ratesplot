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
  that no curve crosses it.

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
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.transforms import IdentityTransform  # noqa: E402

from ratesplot import legend, occupancy  # noqa: E402


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


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    for group in (check_counting, check_count_points, check_tier_order, check_made_up_chart):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group(check)
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[legend fallback] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
