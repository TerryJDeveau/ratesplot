#!/usr/bin/env python3
"""Check the date axis's labels kept apart (``axes._DateLocator``, batch 48), with no network.

A window with fewer than six month starts fell from months to days, whose longest interval, 14 days, gave up to 13
labels of ten characters ("2026-06-012026-06-15" on the default chart); on the page's phone canvas nearly every span
from one month to a year overlapped. Since batch 48 the major locator makes its choice again with fewer ticks where
two labels would stand less than an em apart. Checked here on bare Agg figures, each with an axes where a chart has
its date axis and the chart's locators and formatter (as ``apply_axes_formatting`` sets them), at four canvases (the
default 2048x1536; 1100x1100; 800x800, the least, at the font floor 0.5; 800x800 at the phone's 0.8), over windows
from 7 days to 120 years ending on four days, one a leap February, padded as ``apply_date_xlim`` pads them:

* the labels as the axis lays them out (``get_window_extent``, not the locator's own measure) at least an em apart;
* where 8.22's locator (kept here: matplotlib's choice, its warning silenced, month ends thinned) had its labels an em
  apart, the same major ticks; where it did not, fewer ticks, never more;
* the minor ticks matplotlib's own (AutoDateLocator, minticks 12, maxticks 24), every window;
* the locator with no axis (so no labels to keep apart) choosing as 8.22's did.

    python tools/check_date_labels.py [--quick]

``--quick``: one window in four. Exit status 0 only if every check passes.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ratesplot import axes  # noqa: E402
from ratesplot.config import CANVAS_DPI, DATE_PAD_FRACTION, MIN_DATE_PAD_DAYS, TICK_FS  # noqa: E402

# (width, height, font scale, the date axis's place in the figure as a chart of that size has it, measured
# 2026-11-17 on Canada's chart of 2026-06-01 to 2026-11-16).
CANVASES = (
    (2048, 1536, 1.0, (0.0477, 0.0497, 0.8762, 0.8955)),
    (1100, 1100, 1100 / 2048, (0.0524, 0.0461, 0.8679, 0.9116)),
    (800, 800, 0.5, (0.0701, 0.0608, 0.8222, 0.8864)),
    (800, 800, 0.8, (0.0701, 0.0608, 0.8222, 0.8864)),
)
ENDS = ("2026-11-16", "2026-09-01", "2024-02-29", "1999-12-31")
# The axis lays labels out on whole pixels; the locator measures them unsnapped.
TOLERANCE_PX = 0.5


def spans() -> list[int]:
    """Every whole day from 7 to 60, then a geometric scale to 120 years: 639 spans."""
    least, most, count = 61.0, 120 * 365.25, 645 - 54
    return sorted(set(range(7, 61)) | {round(least * (most / least) ** (i / (count - 1))) for i in range(count)})


class _Locator822(mdates.AutoDateLocator):
    """8.22's major locator, word for word in what it did: matplotlib's choice, its fallback's warning silenced, a tick
    closer than the regular spacing to a following month start dropped (``axes._DateLocator._thinned``, unchanged)."""

    def __init__(self) -> None:
        super().__init__(minticks=6, maxticks=12)
        self._thinner = axes._DateLocator(minticks=6, maxticks=12, thin_month_ends=True)

    def get_locator(self, dmin, dmax):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="AutoDateLocator was unable to pick an appropriate interval")
            return super().get_locator(dmin, dmax)

    def __call__(self):
        return self._thinner._thinned(super().__call__())


def _date_axes(width: int, height: int, scale: float, place, major):
    figure = Figure(figsize=(width / CANVAS_DPI, height / CANVAS_DPI), dpi=CANVAS_DPI)
    FigureCanvasAgg(figure)
    ax = figure.add_axes(place)
    ax.xaxis.set_major_locator(major)
    ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(major))
    ax.xaxis.set_minor_locator(axes._date_locator(minticks=12, maxticks=24))
    ax.tick_params(axis="x", which="major", labelsize=TICK_FS * scale)
    return ax


def _laid_out(ax) -> tuple[list[float], list[str], float]:
    """The major ticks, their labels and the least gap between neighbours, as the axis lays them out."""
    renderer = ax.figure.canvas.get_renderer()
    majors = set(ax.xaxis.get_major_ticks())
    boxes = [
        (tick.label1.get_window_extent(renderer), tick.label1.get_text())
        for tick in ax.xaxis._update_ticks()
        if tick in majors and tick.label1.get_visible() and tick.label1.get_text()
    ]
    labels = sorted((box.x0, box.x1, text) for box, text in boxes)
    gaps = [b[0] - a[1] for a, b in zip(labels, labels[1:])]
    return [float(v) for v in ax.xaxis.get_majorticklocs()], [label[2] for label in labels], min(gaps, default=float("inf"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="one window in four")
    args = parser.parse_args(argv)
    results: list[bool] = []
    failures: dict[str, int] = {}

    def check(name: str, ok: bool, detail: object = "") -> None:
        results.append(ok)
        if not ok:
            failures[name] = failures.get(name, 0) + 1
            if failures[name] <= 3:
                print(f"  FAIL {name}: {detail}")

    days = spans()[:: 4 if args.quick else 1]
    for width, height, scale, place in CANVASES:
        name = f"{width}x{height} at {scale:.2f}"
        em = TICK_FS * scale * CANVAS_DPI / 72.0
        ax = _date_axes(width, height, scale, place, axes._date_locator(minticks=6, maxticks=12, thin_month_ends=True))
        before = _date_axes(width, height, scale, place, _Locator822())
        plain_minor = mdates.AutoDateLocator(minticks=12, maxticks=24)
        plain_minor.set_axis(ax.xaxis)
        changed = close_before = 0
        changed_spans: list[int] = []
        for end in ENDS:
            for span in days:
                stop = pd.Timestamp(end)
                pad = pd.Timedelta(days=max(span * DATE_PAD_FRACTION, MIN_DATE_PAD_DAYS))
                limits = (stop - pd.Timedelta(days=span) - pad, stop + pad)
                ax.set_xlim(*limits)
                before.set_xlim(*limits)
                window = f"{name}, {span} days to {end}"
                ticks, labels, gap = _laid_out(ax)
                old_ticks, old_labels, old_gap = _laid_out(before)
                check("labels an em apart", gap >= em - TOLERANCE_PX, f"{window}: {gap:.1f} px, {labels}")
                if old_gap >= em + TOLERANCE_PX:
                    check("8.22's ticks where its labels stood apart", ticks == old_ticks, f"{window}: {old_labels} -> {labels}")
                elif old_gap < em - TOLERANCE_PX:
                    close_before += 1
                    check("fewer ticks where 8.22's labels stood close", len(ticks) < len(old_ticks),
                          f"{window}: {old_labels} -> {labels}")
                if ticks != old_ticks:
                    changed += 1
                    changed_spans.append(span)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="AutoDateLocator was unable to pick an appropriate interval")
                    expected_minor = [float(v) for v in plain_minor()]
                # The locator's own answer: the axis's get_minorticklocs() drops the minor ticks under major ones.
                check("the minor ticks matplotlib's", [float(v) for v in ax.xaxis.get_minor_locator()()] == expected_minor, window)
                # The same locator off the axis (no labels to keep apart) chooses as 8.22's did.
                free = axes._date_locator(minticks=6, maxticks=12, thin_month_ends=True)
                dmin, dmax = (mdates.num2date(v) for v in ax.get_xlim())
                check("off the axis, 8.22's choice", [float(v) for v in free.tick_values(dmin, dmax)] == old_ticks, window)
        print(f"[date labels] {name}: {len(ENDS) * len(days)} windows, {close_before} with 8.22's labels under an em, "
              f"{changed} changed" + (f" (spans {min(changed_spans)} to {max(changed_spans)} days)" if changed_spans else ""))
    for name, count in failures.items():
        print(f"[date labels] FAIL {name}: {count} window(s)")
    print(f"[date labels] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
