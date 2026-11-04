#!/usr/bin/env python3
"""Check how the regression pieces cover a curve (batch 36.1): they share the observation where they meet.

* every covering runs from the first observation to the last, each piece
  starting at the observation the one before it ended on, on made-up curves
  of every kind, and within the tolerance of all its observations;
* the small cases: two observations, three on a line, three off it;
* a kink: the break falls on the observation at the kink, both lines exact;
* a jump: a short, steep piece of its own, between the observations either
  side of it, with the rates either side unchanged;
* the circuit breaker (``loosen_short_runs``) keeps its rule and the sharing,
  at both ends of a stretch it fits again;
* drawing: each piece begins on the date the one before it ends, the
  tolerance read from the axis as drawn.

No network and no data: the curves are made up.

Usage (from the project root)::

    python tools/check_regression.py

Exit code 1 on any FAIL.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import verify_charts  # noqa: E402,F401  (unused but first: it sets the Agg backend before pyplot is imported)

del verify_charts
import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from ratesplot import regression  # noqa: E402
from ratesplot.config import DATE_COLUMN, PlotConfig  # noqa: E402

_TOLERANCE = math.log(1.01)


def _quarters(count: int) -> np.ndarray:
    """``count`` quarterly dates, in years from the first."""
    return np.arange(count) / 4.0


def _fit(z: np.ndarray, tolerance: float = _TOLERANCE, x: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, list[regression.Piece]]:
    x = _quarters(len(z)) if x is None else x
    weights = regression.time_weights(x)
    return x, weights, regression.fit_pieces(x, z, weights, tolerance)


def _shared(pieces: list[regression.Piece], count: int) -> bool:
    """The pieces run from the first observation to the last, each from where the one before it ended."""
    return (
        bool(pieces)
        and pieces[0].first == 0
        and pieces[-1].last == count - 1
        and all(before.last == after.first for before, after in zip(pieces, pieces[1:]))
        and all(piece.first < piece.last for piece in pieces)
    )


def _worst(x: np.ndarray, z: np.ndarray, pieces: list[regression.Piece]) -> float:
    """The largest distance of any observation from its piece's line."""
    return max(
        float(np.abs(z[piece.first : piece.last + 1] - (piece.intercept + piece.slope * x[piece.first : piece.last + 1])).max())
        for piece in pieces
    )


def _curves() -> dict[str, np.ndarray]:
    """Made-up ln(value) series, from smooth to all noise; the random ones seeded, so a run is repeatable."""
    random = np.random.default_rng(36)
    steady = 0.05 * _quarters(120)
    wander = np.cumsum(random.normal(0.012, 0.01, 200))
    return {
        "steady growth": steady,
        "steady, with a little noise": steady + random.normal(0, 0.002, 120),
        "a random walk with drift": wander,
        "seasons on a trend": 0.04 * _quarters(160) + 0.03 * np.sin(np.arange(160) * math.pi / 2),
        "all noise": random.normal(0, 0.05, 80),
        "a fall, a jump and a rise": np.concatenate([1 - 0.02 * _quarters(40), 1.6 + 0.03 * _quarters(40)]),
    }


def check_coverings(check) -> None:
    """Every covering shares its ends, within the tolerance"""
    for name, z in _curves().items():
        x, _weights, pieces = _fit(z)
        check(f"{name}: first to last, each from where the last ended", _shared(pieces, len(z)), [(p.first, p.last) for p in pieces][:8])
        worst = _worst(x, z, pieces)
        check(f"{name}: within the tolerance", worst <= _TOLERANCE + 1e-9, f"{worst:.5f} against {_TOLERANCE:.5f}, {len(pieces)} pieces")


def check_small(check) -> None:
    """The small cases: two observations, three on a line, three off it"""
    check("one observation: no piece", regression.fit_pieces(np.array([0.0]), np.array([1.0]), np.array([1.0]), _TOLERANCE) == [])
    _x, _w, pieces = _fit(np.array([1.0, 1.3]))
    check("two: one piece, exact", [(p.first, p.last) for p in pieces] == [(0, 1)], pieces)
    _x, _w, pieces = _fit(np.array([1.0, 1.1, 1.2]))
    check("three on a line: one piece", [(p.first, p.last) for p in pieces] == [(0, 2)], pieces)
    _x, _w, pieces = _fit(np.array([1.0, 1.5, 1.0]))
    check(
        "three off a line: two pieces meeting at the middle, none allowed beyond the tolerance",
        [(p.first, p.last) for p in pieces] == [(0, 1), (1, 2)],
        pieces,
    )


def check_kink(check) -> None:
    """A kink: the break falls on the observation at the kink"""
    kink = 30
    z = np.concatenate([0.08 * _quarters(kink + 1), 0.08 * kink / 4 + 0.01 * _quarters(50)[1:]])
    x, _weights, pieces = _fit(z)
    check("two pieces, meeting at the kink", [(p.first, p.last) for p in pieces] == [(0, kink), (kink, len(z) - 1)], [(p.first, p.last) for p in pieces])
    check("the first line's slope exact", math.isclose(pieces[0].slope, 0.08, abs_tol=1e-9), pieces[0].slope)
    check("the second line's slope exact", math.isclose(pieces[-1].slope, 0.01, abs_tol=1e-9), pieces[-1].slope)
    check("both lines exact at the kink", _worst(x, z, pieces) < 1e-9, _worst(x, z, pieces))


def check_jump(check) -> None:
    """A jump: a short, steep piece of its own"""
    before, after = 20, 30
    z = np.concatenate([0.04 * _quarters(before), 0.5 + 0.04 * _quarters(before + after)[before:]])
    _x, _weights, pieces = _fit(z)
    runs = [(p.first, p.last) for p in pieces]
    check("three pieces, the middle one across the jump", runs == [(0, before - 1), (before - 1, before), (before, len(z) - 1)], runs)
    check("the rates either side are the curve's own", all(math.isclose(p.slope, 0.04, abs_tol=1e-9) for p in (pieces[0], pieces[-1])), [p.slope for p in pieces])
    check("the piece across the jump is the steepest", pieces[1].slope == max(p.slope for p in pieces), [p.slope for p in pieces])


def check_circuit_breaker(check) -> None:
    """The circuit breaker: its rule kept, and the sharing, at both ends of a stretch"""
    # A long steady stretch, monthly seasons that cut into short pieces, another steady stretch.
    months = 12 * 30
    x = np.arange(months) / 12.0
    z = 0.03 * x
    seasons = (x >= 10) & (x < 20)
    z = z + np.where(seasons, 0.03 * np.sin(np.arange(months) * math.pi / 3), 0.0)
    weights = regression.time_weights(x)
    tolerance = math.log(1.012)
    tight = regression.fit_pieces(x, z, weights, tolerance)
    min_days = regression._MIN_PIECE_DAYS
    days = np.rint(x * regression._DAYS_PER_YEAR)
    short = [days[p.last] - days[p.first] < min_days for p in tight]
    longest = run = 0
    for flag in short:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    check("the seasons cut the curve into a run of short pieces", longest >= regression._SHORT_RUN, longest)
    pieces, loosened = regression.loosen_short_runs(x, z, weights, tight, tolerance, min_days)
    check("the stretch is loosened", len(loosened) == 1, loosened)
    check("fewer pieces", len(pieces) < len(tight), (len(tight), len(pieces)))
    check("the pieces still share their ends, into and out of the stretch", _shared(pieces, months), [(p.first, p.last) for p in pieces][:8])
    if loosened:
        stretch = loosened[0]
        check("within three times the tolerance", tolerance < stretch.tolerance <= regression._MAX_LOOSENING * tolerance, stretch)
        check("the stretch starts where the piece before it ended", any(p.last == stretch.first for p in pieces), stretch)
        check("and ends where the piece after it starts", any(p.first == stretch.last for p in pieces), stretch)


def check_drawing(check) -> None:
    """Drawing: each piece begins on the date the one before it ends"""
    dates = pd.date_range("2000-03-31", periods=100, freq="QE")
    values = np.concatenate([np.exp(0.08 * _quarters(50)), np.exp(0.08 * 49 / 4) * np.exp(-0.02 * _quarters(50))])
    # The first row is the value carried to the window's start, not an observation (``regression.observations``).
    macro = pd.DataFrame({DATE_COLUMN: [pd.Timestamp("2000-01-01"), *dates], "curve": [values[0] * 0.99, *values]})
    figure = Figure(figsize=(8, 6), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    ax.set_yscale("log")
    (line,) = ax.plot(dates, values, label="A curve", color="C3")
    ax.set_ylim(0.5, 100)
    config = PlotConfig(start=pd.Timestamp("2000-01-01"), end=pd.Timestamp("2025-01-01"))
    labels = regression.add_regression_segments(ax, macro, [(line, "curve")], {}, config)
    drawn = [np.asarray(label.piece.get_xydata(), dtype=float) for label in labels]
    check("more than one piece", len(drawn) >= 2, len(drawn))
    check("each begins on the date the one before it ends", all(a[1, 0] == b[0, 0] for a, b in zip(drawn, drawn[1:])), drawn)
    check("the first from the first observation", drawn and mdates.num2date(drawn[0][0, 0]).date() == dates[0].date(), drawn[:1])
    check("the last to the last observation", drawn and mdates.num2date(drawn[-1][1, 0]).date() == dates[-1].date(), drawn[-1:])


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    for group in (check_coverings, check_small, check_kink, check_jump, check_circuit_breaker, check_drawing):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group(check)
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[regression] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
