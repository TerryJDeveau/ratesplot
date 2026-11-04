#!/usr/bin/env python3
"""Check a window kept on its monitor (``ratesplot/monitors.py``, batch 39), with no network.

* the rectangles: what two share, how far apart, the monitor holding most of a window;
* ``fitted``: a window that fits stays; one that passes an edge goes to the corner nearest its
  middle; one that cannot fit shrinks by one factor, its shape kept, the frame not shrunk;
* the window at its opening (``gui._remembered_geometry``): the monitors unchanged, any size and
  place kept while the title bar can be reached (Terry's window across two monitors, the ruling of
  2026-10-12), a taskbar's change and another order counting as unchanged; settings saved before
  batch 39; the monitors changed, a window that fits left as it is, one that does not moved,
  then shrunk, on the monitor holding most of it; the monitor gone (batch 15.4);
* every size and place on several sets of monitors: all of the window, frame and all, on one;
* the plain windows (``plotting._kept_on_its_monitor``, ``plot_country``): only the default
  size and Tk's windows; the chart drawn at the size that fits, and drawn again at it by a refresh.

    python tools/check_monitors.py
    python tools/check_monitors.py --live +988+-3000   # also a real plain window opened there

``--live`` opens a real matplotlib window at that place (on Buddug, Terry's monitor 2 is
"+988+-3000") and checks where it ends up and at what size; with the default canvas needing more
than that monitor has, it must be moved and shrunk.

Exit status 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

if "--live" not in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from ratesplot import gui, monitors, plotting  # noqa: E402
from ratesplot.config import DEFAULT_CANVAS_PX, PlotConfig  # noqa: E402

# Buddug's four monitors, as Tk's pixels (system DPI, 125 %), measured 2026-11-04: the primary and the three above it.
PRIMARY = (0, 0, 3840, 2100)
LEFT = (-1212, -3840, 948, -60)
MIDDLE = (948, -3840, 3108, -60)  # Terry's monitor 2
RIGHT = (3108, -3840, 5268, -60)
BUDDUG = [PRIMARY, LEFT, MIDDLE, RIGHT]
BUDDUG_BOUNDS = [(0, 0, 3840, 2160), (-1212, -3840, 948, 0), (948, -3840, 3108, 0), (3108, -3840, 5268, 0)]
FRAME = (9, 38, 9, 9)  # measured on Buddug at 125 % (gui._window_frame)
LAPTOP = (0, 0, 1920, 1040)
LAPTOP_BOUNDS = [(0, 0, 1920, 1080)]

STRETCHED = (3456, 1944, 1115, -2149)  # Terry's window across two of the three upper monitors, 2026-10-12
GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


def saved_on(bounds: list, **more) -> dict:
    """The remembered settings' monitors, as ``_remember`` writes them."""
    return {"monitors": [list(rect) for rect in bounds], **more}


def opened(window: tuple[int, int, int, int], state: dict, areas: list, bounds: list) -> str:
    """The geometry a window remembered as ``window`` (width, height, x, y) opens with."""
    return gui._remembered_geometry(*window, state, areas, bounds, FRAME)


def whole_on_one(geometry: str, areas: list) -> bool:
    """True when all of the window, frame and all, is on one work area."""
    width, height, x, y = map(int, GEOMETRY.match(geometry).groups())
    outer = gui._outer_rect(width, height, x, y, FRAME)
    return any(outer[0] >= a[0] and outer[1] >= a[1] and outer[2] <= a[2] and outer[3] <= a[3] for a in areas)


def check_rectangles(check) -> None:
    """What two rectangles share and how far apart they are; the monitor holding most of a window."""
    check("overlap: the area they share", monitors.overlap((0, 0, 10, 10), (5, 5, 20, 20)) == 25)
    check("overlap: none when apart", monitors.overlap((0, 0, 10, 10), (20, 20, 30, 30)) == 0)
    check("gap: none when touching", monitors.gap((0, 0, 10, 10), (10, 0, 20, 10)) == 0)
    check("gap: corner to corner", monitors.gap((0, 0, 10, 10), (13, 14, 20, 20)) == 5)
    check("monitor_of: the one holding most of it", monitors.monitor_of((900, -2000, 2000, -1000), BUDDUG) == MIDDLE)
    check("monitor_of: off them all, the nearest", monitors.monitor_of((6000, -2000, 6500, -1000), BUDDUG) == RIGHT)


def check_fitted(check) -> None:
    """A window that fits stays; moved to the corner that suits; shrunk by one factor only if it cannot fit."""
    area = (0, 0, 1000, 800)
    chrome = (20, 60)
    check("inside: nothing moves", monitors.fitted((500, 400), chrome, (100, 100), area) == (1.0, (100, 100)))
    check("filling it exactly: nothing moves", monitors.fitted((980, 740), chrome, (0, 0), area) == (1.0, (0, 0)))
    check("past the right edge, nearer the right: the right corner, not shrunk",
          monitors.fitted((500, 400), chrome, (600, 100), area) == (1.0, (480, 0)), monitors.fitted((500, 400), chrome, (600, 100), area))
    check("past the bottom, nearer the left and bottom: the bottom left corner",
          monitors.fitted((500, 400), chrome, (10, 500), area) == (1.0, (0, 340)), monitors.fitted((500, 400), chrome, (10, 500), area))
    check("left of the monitor: back on it, not shrunk",
          monitors.fitted((500, 400), chrome, (-50, 100), area) == (1.0, (0, 0)), monitors.fitted((500, 400), chrome, (-50, 100), area))
    scale, place = monitors.fitted((1960, 1480), chrome, (0, 0), area)
    check("too wide and too tall at its top left: stays there, one factor", place == (0, 0) and abs(scale - 0.5) < 1e-9, (scale, place))
    scale, place = monitors.fitted((1960, 740), chrome, (0, 0), area)
    check("too wide alone: the factor from the width, the height shrinks with it", abs(scale - 0.5) < 1e-9 and place == (0, 0), (scale, place))
    scale, place = monitors.fitted((1960, 740), chrome, (900, 700), area)
    check("too large near the bottom right: the bottom right corner", abs(scale - 0.5) < 1e-9 and place == (0, 370), (scale, place))
    scale, place = monitors.fitted((980, 2000), chrome, (500, 0), area)
    check("the frame does not shrink: the content takes the whole of the cut", abs(scale - 740 / 2000) < 1e-9, scale)
    # The default canvas at 125 % on Terry's monitor 2: 2560 px of content in 2160 px less the frame (NG_analysis's measurement, the plan's).
    scale, place = monitors.fitted((2560, 1920), (18, 100), (988, -3000), MIDDLE)
    check("the default canvas at 125 % on monitor 2: its top left corner, 0.84 of the size", abs(scale - (2160 - 18) / 2560) < 1e-9 and place == (948, -3840), (scale, place))


def check_unchanged(check) -> None:
    """The monitors those it was saved with: any size and place kept while the title bar can be reached."""
    state = saved_on(BUDDUG_BOUNDS)
    wanted = "3456x1944+1115+-2149"
    check("Terry's window across two monitors stays (2026-10-12)", opened(STRETCHED, state, BUDDUG, BUDDUG_BOUNDS) == wanted, opened(STRETCHED, state, BUDDUG, BUDDUG_BOUNDS))
    check("... with the monitors listed in another order", opened(STRETCHED, state, BUDDUG, list(reversed(BUDDUG_BOUNDS))) == wanted)
    shifted = [(a[0], a[1], a[2], a[3] - 40) for a in BUDDUG]
    check("... with a taskbar changed: a work area, not a monitor", opened(STRETCHED, state, shifted, BUDDUG_BOUNDS) == wanted)
    check("part of it off the screens: stays, its title bar on one", opened((3000, 1500, 3000, 1000), state, BUDDUG, BUDDUG_BOUNDS) == "3000x1500+3000+1000",
          opened((3000, 1500, 3000, 1000), state, BUDDUG, BUDDUG_BOUNDS))
    # No title bar to drag by, the monitors unchanged: put back where it can be reached, as before.
    lost = opened((1000, 800, 9000, 9000), state, BUDDUG, BUDDUG_BOUNDS)
    check("no title bar to reach, the monitors unchanged: moved onto one", whole_on_one(lost, BUDDUG), lost)


def check_old_settings(check) -> None:
    """Settings saved before batch 39, holding at most the one monitor."""
    wanted = "3456x1944+1115+-2149"
    check("no list, its monitor still there: as it was, not shrunk at the first start", opened(STRETCHED, {"monitor": list(MIDDLE)}, BUDDUG, BUDDUG_BOUNDS) == wanted)
    check("no list and no monitor: as it was", opened(STRETCHED, {}, BUDDUG, BUDDUG_BOUNDS) == wanted)
    moved = opened((3000, 1500, 100, 100), {"monitor": list(MIDDLE)}, [LAPTOP], LAPTOP_BOUNDS)
    check("no list, its monitor gone: moved and shrunk", whole_on_one(moved, [LAPTOP]), moved)
    check("a list that is no list: the old rule", opened(STRETCHED, {"monitors": "x", "monitor": list(MIDDLE)}, BUDDUG, BUDDUG_BOUNDS) == wanted)
    check("a list holding something else: the old rule", opened(STRETCHED, {"monitors": [[1, 2, 3]], "monitor": list(MIDDLE)}, BUDDUG, BUDDUG_BOUNDS) == wanted)
    check("an empty list: the old rule", opened(STRETCHED, {"monitors": [], "monitor": list(MIDDLE)}, BUDDUG, BUDDUG_BOUNDS) == wanted)
    check("_monitors_changed: the same", not gui._monitors_changed(saved_on(BUDDUG_BOUNDS), BUDDUG, BUDDUG_BOUNDS))
    check("_monitors_changed: one fewer", gui._monitors_changed(saved_on(BUDDUG_BOUNDS), BUDDUG[:3], BUDDUG_BOUNDS[:3]))
    check("_as_rect: a list of four whole numbers", gui._as_rect([1, 2, 3, 4]) == (1, 2, 3, 4))
    check("_as_rect: anything else is None", gui._as_rect([1, 2, 3]) is None and gui._as_rect("1,2,3,4") is None and gui._as_rect([1, 2, 3, 4.5]) is None)


def check_changed(check) -> None:
    """The monitors changed: a window that fits left as it is; one that does not moved, then shrunk, on the monitor holding most of it."""
    state = saved_on(BUDDUG_BOUNDS)
    # Fits as it stands: not touched, wherever it is on the monitor.
    check("fits as it stands: left as it is", opened((800, 600, 300, 200), state, [LAPTOP], LAPTOP_BOUNDS) == "800x600+300+200", opened((800, 600, 300, 200), state, [LAPTOP], LAPTOP_BOUNDS))
    # Passes an edge, fits once moved: its size kept.
    moved = opened((1200, 800, 800, 50), state, [LAPTOP], LAPTOP_BOUNDS)
    check("passes the right edge, fits once moved: its size kept, the right corner", moved == "1200x800+702+0", moved)
    # From a larger monitor: the case Terry raised.
    big = opened((3000, 1500, 100, 100), state, [LAPTOP], LAPTOP_BOUNDS)
    width, height, x, y = map(int, GEOMETRY.match(big).groups())
    check("from a larger monitor: all of it shows", whole_on_one(big, [LAPTOP]), big)
    check("... shrunk only as far as that: one side fills the monitor", width + 18 == 1920 or height + 47 == 1040, big)
    check("... its shape kept, within a pixel", abs(width / height - 2.0) < 2 / height, big)
    check("... at the corner nearest the middle it then has", (x, y) == (0, 42), big)
    # Stretched across two that remain, a third unplugged: onto the one holding most of it.
    two = [LEFT, MIDDLE]
    two_bounds = BUDDUG_BOUNDS[1:3]
    across = opened((3000, 1500, 500, -3000), state, two, two_bounds)
    check("stretched across two of those left: all of it on the one holding most of it", whole_on_one(across, [MIDDLE]), across)
    # A new, larger set: it fits, nothing to do.
    check("onto larger monitors: as it was", opened((800, 600, 100, 100), saved_on(LAPTOP_BOUNDS), BUDDUG, BUDDUG_BOUNDS) == "800x600+100+100",
          opened((800, 600, 100, 100), saved_on(LAPTOP_BOUNDS), BUDDUG, BUDDUG_BOUNDS))
    # The same monitors at another scale: another set of rectangles.
    scaled = [(0, 0, 3072, 1728)]
    check("the same monitor at another scale counts as changed", gui._monitors_changed(saved_on([(0, 0, 3840, 2160)]), [(0, 0, 3072, 1668)], scaled))


def check_gone(check) -> None:
    """Its monitor gone, no title bar to drag by: to the nearest monitor, at its place from the corner (batch 15.4), then the same rule."""
    state = saved_on(BUDDUG_BOUNDS, monitor=list(MIDDLE))
    moved = opened(STRETCHED, state, [PRIMARY], BUDDUG_BOUNDS[:1])
    check("Terry's window, the upper monitors unplugged: its size kept, all of it on the main screen", moved == "3456x1944+0+109", moved)
    small = opened((3000, 1500, 1500, -3000), state, [LAPTOP], LAPTOP_BOUNDS)
    check("onto a smaller one: all of it shows", whole_on_one(small, [LAPTOP]), small)
    width, height = map(int, GEOMETRY.match(small).groups()[:2])
    check("... its shape kept, within a pixel", abs(width / height - 2.0) < 2 / height, small)
    no_own = opened(STRETCHED, saved_on(BUDDUG_BOUNDS), [PRIMARY], BUDDUG_BOUNDS[:1])
    check("its monitor not said: all of it on the nearest", whole_on_one(no_own, [PRIMARY]), no_own)


def check_every_case(check) -> None:
    """Every size and place on several sets of monitors, the monitors changed: all of the window on one, never larger, its shape kept."""
    sets = [[LAPTOP], [PRIMARY], [LEFT, MIDDLE], [MIDDLE], [PRIMARY, RIGHT], [(0, 0, 1280, 680)], [(-1920, 0, 0, 1040), (0, 0, 1920, 1040)]]
    state = saved_on([(1, 2, 3, 4)], monitor=[1, 2, 3, 4])
    bad_whole, bad_larger, bad_shape, count = [], [], [], 0
    for areas in sets:
        for width, height in ((800, 600), (1728, 972), (2048, 1536), (3456, 1944), (1200, 3000), (5000, 900)):
            for x, y in ((0, 0), (40, 40), (-500, 200), (1000, -3000), (5000, 3000), (-3000, -5000), (300, 1900)):
                count += 1
                result = opened((width, height, x, y), state, areas, [(0, 0, 1, 1)])
                new_width, new_height = map(int, GEOMETRY.match(result).groups()[:2])
                if not whole_on_one(result, areas):
                    bad_whole.append(((width, height, x, y), areas, result))
                if new_width > width or new_height > height:
                    bad_larger.append(((width, height, x, y), areas, result))
                if abs(new_width / new_height - width / height) > 2 * max(width / height, 1) / min(new_width, new_height):
                    bad_shape.append(((width, height, x, y), areas, result))
    check(f"all of the window on one monitor, in {count} cases", not bad_whole, bad_whole[:3])
    check("never larger than it was", not bad_larger, bad_larger[:3])
    check("its shape kept, within a pixel", not bad_shape, bad_shape[:3])


def check_plain(check) -> None:
    """The plain windows: only the default size and Tk's windows; the chart drawn at the size that fits, and drawn again at it."""

    class Manager:
        def __init__(self) -> None:
            self.window = type("TkWindow", (), {"winfo_rootx": lambda self: 0})()
            self.shows = 0

        def show(self) -> None:
            self.shows += 1

    class Canvas:
        def __init__(self) -> None:
            self.manager = Manager()

        def get_tk_widget(self) -> object:
            return object()

    class Figure:
        def __init__(self) -> None:
            self.canvas = Canvas()
            self.sized: tuple | None = None

        def set_size_inches(self, width: float, height: float, forward: bool = False) -> None:
            self.sized = (round(width * 100), round(height * 100), forward)

    default = PlotConfig()
    real_fit = monitors.fit_window
    try:
        monitors.fit_window = lambda window, content: 1.0
        figure = Figure()
        check("fits: the config as it was, shown", plotting._kept_on_its_monitor(figure, default) is default and figure.canvas.manager.shows == 1 and figure.sized is None)
        monitors.fit_window = lambda window, content: 0.5
        figure = Figure()
        drawn = plotting._kept_on_its_monitor(figure, default)
        half = (DEFAULT_CANVAS_PX[0] // 2, DEFAULT_CANVAS_PX[1] // 2)
        check("too large: drawn at the size that fits", (drawn.width_px, drawn.height_px) == half, (drawn.width_px, drawn.height_px))
        check("... the figure given that size, the window following", figure.sized == (*half, True), figure.sized)
        figure = Figure()
        sized = replace(default, width_px=3000, height_px=2000)
        check("-dim: kept as asked for, not shown early", plotting._kept_on_its_monitor(figure, sized) is sized and figure.canvas.manager.shows == 0 and figure.sized is None)
        figure = Figure()
        figure.canvas.manager.window = None
        check("no Tk window (Agg): left as it comes", plotting._kept_on_its_monitor(figure, default) is default and figure.canvas.manager.shows == 0)
    finally:
        monitors.fit_window = real_fit
    # Agg's own figure, as the harnesses have one.
    agg_figure, _axes = plt.subplots(figsize=default.figsize_inches)
    if matplotlib.get_backend().lower() == "agg":
        check("a real Agg figure: left as it comes", plotting._kept_on_its_monitor(agg_figure, default) is default)
    plt.close(agg_figure)

    # plot_country: what it draws with, first and at a refresh, the drawing stood in for.
    seen: list[tuple[int, int]] = []
    keep = {name: getattr(plotting, name) for name in ("draw_country", "_kept_on_its_monitor", "attach_refresh")}
    shows = plt.show
    again: list = []
    try:
        plotting.draw_country = lambda axes, y, m, r, config, metadata, lines: seen.append((config.width_px, config.height_px))
        plotting._kept_on_its_monitor = lambda figure, config: replace(config, width_px=1024, height_px=768)
        plotting.attach_refresh = lambda figure, minutes, refreshed, draw_again: again.append(draw_again)
        plt.show = lambda *args, **kwargs: None
        config = replace(default, hover=False)
        plotting.plot_country(None, None, [], config, None, None, refreshed=lambda ticker: None)
        again[0]((None, None, [], config))
        check("the chart drawn at the size that fits", seen[0] == (1024, 768), seen)
        check("... and drawn again at it by a refresh, whose config comes from the command line", seen[1] == (1024, 768), seen)
    finally:
        for name, value in keep.items():
            setattr(plotting, name, value)
        plt.show = shows
        plt.close("all")


def check_live(check, place: str) -> None:
    """A real plain window opened at ``place``: where it ends up and at what size."""
    plt.switch_backend("TkAgg")
    default = PlotConfig()
    figure, _axes = plt.subplots(figsize=default.figsize_inches)
    manager = figure.canvas.manager
    window = manager.window
    window.geometry(place)
    window.update()
    began = (window.winfo_x(), window.winfo_y())
    drawn = plotting._kept_on_its_monitor(figure, default)
    for _ in range(20):
        window.update()
    x, y = window.winfo_x(), window.winfo_y()
    border = window.winfo_rootx() - x
    title = window.winfo_rooty() - y
    outer = (x, y, x + window.winfo_width() + 2 * border, y + window.winfo_height() + title + border)
    areas = monitors.monitor_work_areas()
    area = monitors.monitor_of(outer, areas)
    print(f"     placed at {began}, now {outer}, on {area}; drawn at {drawn.width_px}x{drawn.height_px}; canvas {figure.canvas.get_tk_widget().winfo_width()}x{figure.canvas.get_tk_widget().winfo_height()}")
    check("all of the window on its monitor (a pixel's rounding allowed)", outer[0] >= area[0] - 1 and outer[1] >= area[1] - 1 and outer[2] <= area[2] + 1 and outer[3] <= area[3] + 1, (outer, area))
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", metavar="+X+Y", help="also open a real plain window at this place")
    args = parser.parse_args()
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}")

    for group in (check_rectangles, check_fitted, check_unchanged, check_old_settings, check_changed, check_gone, check_every_case, check_plain):
        print(f"-- {group.__doc__.splitlines()[0]}")
        group(check)
    if args.live:
        print(f"-- {check_live.__doc__.splitlines()[0]}")
        check_live(check, args.live)
    print(f"[monitors] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
