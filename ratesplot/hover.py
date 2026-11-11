"""The hover read-out (batch 11.2): what a line says where the pointer rests on it.

Terry, 2026-10-08 (decision 21): a small window by the pointer naming the
series, with the date and the value, when the pointer rests on a line, which
follows the pointer along the line and goes once the pointer has been off
every line for a while. The plan's rules: shown after 0.5 s
(``SHOW_DELAY_MS``), hidden 2 s after the pointer has left every line
(``HIDE_DELAY_MS``), the pointer caught within 3 screen pixels of a line in
any direction (``REACH_PX``: a preview is usually shrunk, and the risers of
a step curve escape an up-or-down test); on a step curve, the value in force
on the date under the pointer and the date of its observation. Every line
within reach is read, the nearest first, in the one box (batch 11.6, Terry,
2026-10-27: lines crossing there "combined into one pop-up pane"; until
then the nearer line won). On by default, with a box and a switch of its own (decision
68, 2026-10-26: "a tick-box to turn off the hover read-out ..., as some
people won't like it"), ``--hover`` / ``--no-hover``. It draws nothing on
the chart: the PNG is the same with it on or off.

What is shared here, without a GUI toolkit:

* ``chart_lines``: with each drawing, where every line runs on the picture
  (image pixels, origin top left), each point's date, and its value as the
  read-out writes it. ``plotting`` marks each line with how its values are
  written (``mark``), as it marks each for Export chart; the time of an
  intraday quote is marked on the figure (``mark_quote``);
* ``ChartLines.reading``: the lines within reach of a point of the picture
  and what each says there (``Readings``). The window (``gui``) and the plain matplotlib windows
  (``attach``) ask it; the web page's browser asks the same of the same data
  (``payload``) in its own script (``web._CHART_JS``), which follows the rules
  of ``_nearest_line`` and ``_nearest_steps`` line for line;
* ``Controller``: when the read-out shows, follows the pointer and goes.

What a line says (``Reading``): its legend name; then its value and date;
then its change (batch 44, below). A line's points are its observations,
and the read-out gives the last one on or before the day under the pointer,
never a value between two and never one from a later day (decision 127: a
daily yield's Friday on the Saturday and the Sunday, its Monday from
Monday; until batch 44 it gave the nearer one). A step curve (a quarterly debt, a policy
rate held until changed) gives the value in force on the date under the
pointer, and the date of its observation where that differs ("2026-08-15
(observed 2026-06-30)"); a value carried unchanged on later rows is dated
by its first, where it was observed. A projection to today (``--projections``) is a
straight line, so it gives the value on the line on the day under the
pointer, as its end label does ("≈"), "(projected)". An intraday quote's day
gives the quote's time, as the subtitle does. Values are written as the end
labels write them (-l): a yield "4.12%", a spread "+36 pts", an amount
"$36.2T", under -r "120%". The regression segments are a fit, not a series,
and say nothing (as Export chart leaves them out).

The change (batch 44; Terry, 2026-11-10 and 11, decisions 127, 129 and
130), a third line under the value: a plain subtraction in the series' own
unit, and where that unit isn't percent the percentage change of the same
pair after it, where the earlier value is above zero. A line read day by day
(a series filled in, Daily values; a projection) gives its change from the
day before and that change's rate over a year, "+$4.97B, +1.4 bp a day
(≈ +5.11%/yr)"; a rate set by announcement (a policy rate, a prime rate)
its last change and that change's date, "−25 bp on 2026-10-29"; any other
its change from the observation before, with that one's date, "−3.0 bp
from 2026-11-06". A change in a rate is in bp below 1 point and pp from 1,
a percentage change in bp below 1 % and % from 1 (``_hundredths``). Every
figure the read-out writes, its values too, is rounded on its decimal
digits, half away from zero (``rounded``, ``for_writing``).

A long daily series has many points to a pixel. Each line keeps, for each
column of image pixels it crosses, its first and last points there and its
highest and lowest (``_decimated``): the line's drawn shape to the pixel,
and a few thousand points where there were tens of thousands, which keeps
the web page's data small. The read-out then gives one of those points, an
observation within a pixel of the pointer.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.text import Text
from matplotlib.transforms import IdentityTransform

from .export import series_of
from .legend import quote_time_text

# Decision 21 (2026-10-08): shown after the pointer has rested on a line this
# long, hidden this long after it has left every line.
SHOW_DELAY_MS = 500
HIDE_DELAY_MS = 2000
# How near a line the pointer is caught, in screen pixels, in any direction.
REACH_PX = 3.0
# A caught point counts as on the chart within this much of the axes' box
# (image pixels): a line is drawn only inside it.
_BOX_SLACK_PX = 0.5

# The marks plotting puts on what it draws: on each line, how its values are
# written (``_Mark``); on the figure, the intraday quotes' day and time.
_MARK_ATTR = "_ratesplot_hover"
_QUOTE_ATTR = "_ratesplot_hover_quote"
# Days are counted from here, so the browser reads them without matplotlib's epoch.
_EPOCH = mdates.date2num(np.datetime64("1970-01-01"))

# Decision 130 (Terry, 2026-11-11): every figure the read-out writes is rounded
# on its decimal digits, half away from zero (-1.235 to -1.24, 0.125 to 0.13),
# not by Python's rounding of the binary value stored (2.675 is stored as
# 2.67499999999999982, which Python writes 2.67; an exact tie such as 0.125 it
# takes to even, 0.12). The sources publish decimals, so the decimal digits
# decide. A figure is first moved away from zero by this fraction of itself:
# far more than the binary noise of a few subtractions and divisions (about
# 1e-16 of the figure each), far less than any digit written.
_NOISE = 1e-12
# A change's sign: a true minus (decision 129), and a plus.
_MINUS = "−"
# A change a day as a rate over a year (decision 129): a year's mean length, leap years counted.
_DAYS_A_YEAR = 365.25


@dataclass(frozen=True)
class _Mark:
    value_format: Callable[[float], str]
    projected: bool
    quoted: bool
    daily: bool = False
    # How a change in an amount is written (batch 44): a positive amount in the series' own unit, as its values are
    # ("$4.97B", "512K"); None for a series in percent, whose changes are in bp or pp.
    amount: Callable[[float], str] | None = None
    # A rate set by announcement (``config.SET_BY_ANNOUNCEMENT``): its last change and that change's date.
    set_rate: bool = False
    # Its whole series' changes, where its last change is looked up (a stretch drawn from the chart's start holds a
    # value set before it): each change's day (from 1970-01-01), the value it set and the value before it.
    history: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None


def mark(
    line: Line2D,
    value_format: Callable[[float], str],
    *,
    projected: bool = False,
    quoted: bool = False,
    daily: bool = False,
    amount: Callable[[float], str] | None = None,
    set_rate: bool = False,
    history: pd.Series | None = None,
) -> Line2D:
    """Record how the read-out writes ``line``'s values and their changes.

    ``projected``: a projection to today; ``quoted``: a yield or spread, which
    an intraday quote can end; ``daily``: a series filled in between its
    observations (Daily values, batch 42.2), read day by day. ``amount``: how
    a change of an amount is written (a positive amount, as the values are
    written: ``axes.format_currency`` with the chart's prefix, a count); None
    for a series in percent (a yield, a rate, a spread, inflation, an amount
    under -r), whose changes are written in bp or pp. ``set_rate``: a rate set
    by announcement, which reads its last change and that change's date,
    looked up in ``history``, its whole series (date-indexed), where given.
    """
    changes = None
    if history is not None:
        history = history.dropna().sort_index()
        days = pd.DatetimeIndex(history.index).to_numpy().astype("datetime64[D]").astype(np.int64)
        values = history.to_numpy(dtype=float)
        at = np.flatnonzero(values[1:] != values[:-1]) + 1  # each position where the value changes
        changes = (days[at], values[at], values[at - 1])
    setattr(line, _MARK_ATTR, _Mark(value_format, projected, quoted, daily, amount, set_rate, changes))
    return line


def mark_quote(figure: Figure, quote_time: pd.Timestamp, zone: str | None) -> None:
    """Record when ``figure``'s intraday quotes were taken (``latest``): their day (Toronto's, as they are dated) and their time in ``zone``."""
    day = quote_time.tz_localize(None).normalize()
    setattr(figure, _QUOTE_ATTR, (_day_of(day), quote_time_text(quote_time, day, zone)))


def _day_of(when: pd.Timestamp) -> int:
    """Whole days from 1970-01-01."""
    return int(math.floor(mdates.date2num(when.to_datetime64()) - _EPOCH))


def date_text(day: int) -> str:
    """A day (``Run.day``) as YYYY-MM-DD."""
    return str(np.datetime64(int(day), "D"))


# ---------------------------------------------------------------------------
# Figures as the read-out writes them (decisions 129 and 130, batch 44)
# ---------------------------------------------------------------------------


def rounded(value: float, decimals: int) -> float:
    """``value`` rounded to ``decimals`` places on its decimal digits, half away from zero (decision 130).

    Scaled, moved away from zero by ``_NOISE`` of itself (the binary noise
    nudged out), a half added and the fraction dropped, the sign put back:
    -1.235 to -1.24, +1.235 to +1.24, 0.125 to 0.13, 4.25 - 3.015
    (1.2349999999999999 stored) to 1.24. The result is the double nearest
    the decimal, so a format to ``decimals`` places writes it exactly. A
    figure that rounds to nothing is 0.0, never -0.0.
    """
    scale = 10.0 ** decimals
    whole = math.floor(abs(value) * scale * (1.0 + _NOISE) + 0.5)
    return math.copysign(whole / scale, value) if whole else 0.0


def for_writing(value: float) -> float:
    """``value`` made ready for a formatter that rounds it itself (``axes.format_yield``'s ``.3f``, ``format_currency``'s ``.3g``).

    Moved away from zero by ``_NOISE`` of itself, the same nudge as
    ``rounded``'s, so the formatter's own rounding of the binary value goes
    half away from zero on the decimal digits it writes (decision 130), at
    whatever places it chooses: a gilt's 4.1250 is written 4.125%, its 4.12505
    4.125%, and to two places 4.13 where Python alone wrote 4.12.
    """
    return value * (1.0 + _NOISE)


def _signed(text: str, figure: float) -> str:
    """``text`` (a figure's size) with its sign: "+" above zero, a true minus below (decision 129), none at zero."""
    if figure > 0:
        return "+" + text
    if figure < 0:
        return _MINUS + text
    return text


def _hundredths(value: float, unit: str) -> str:
    """A change in percentage points (``unit`` " pp") or a percentage change (``unit`` "%"), as decision 129 writes it.

    1 or more in ``unit``, to three places, two where the third is 0
    ("+1.25 pp", "+1.375 pp", "+2.30%"); below 1 in bp, hundredths of it, to a
    tenth below 10 and whole from 10 to 99 ("+3.5 bp", "-25 bp"). The unit
    and the places are chosen on the rounded figure: 9.96 bp is "10 bp", 99.6
    bp "1.00 pp". Signed (``_signed``), the sign by the rounded figure.
    """
    points = abs(value) * 100.0
    tenths = rounded(points, 1)
    if tenths < 10.0:
        text, figure = f"{tenths:.1f} bp", tenths
    else:
        whole = rounded(points, 0)
        if whole < 100.0:
            text, figure = f"{whole:.0f} bp", whole
        else:
            figure = rounded(abs(value), 3)
            places = f"{figure:,.3f}"
            text = (places[:-1] if places.endswith("0") else places) + unit
    return _signed(text, figure if value >= 0 else -figure)


def _amount_change(change: float, amount: Callable[[float], str]) -> str:
    """A change in an amount, in the series' own unit, signed: "+$4.97B", "−512K" (``amount`` writes its size)."""
    return _signed(amount(for_writing(abs(change))), change)


def _figures(how: _Mark, now: float, before: float) -> str:
    """The change from ``before`` to ``now``: in bp or pp for a series in percent; else in its own unit, then its percentage change where ``before`` is above zero."""
    change = now - before
    if how.amount is None:
        return _hundredths(change, " pp")
    text = _amount_change(change, how.amount)
    return f"{text}, {_hundredths(change / before * 100.0, '%')}" if before > 0 else text


def _change_a_day(how: _Mark, now: float, before: float) -> str:
    """A line read day by day: its change from the day before, then that change's rate over a year (decision 129).

    "+0.4 bp a day (≈ +1.46 pp/yr)" for a series in percent; for an amount
    "+$4.97B, +1.4 bp a day (≈ +5.11%/yr)", the rate over a year being its
    percentage change's (its own unit's where the day before is not above
    zero). A day with the value of the day before (a value held after its
    last figure): "no change from the day before".
    """
    change = now - before
    if change == 0:
        return "no change from the day before"
    if how.amount is None:
        return f"{_hundredths(change, ' pp')} a day (≈ {_hundredths(change * _DAYS_A_YEAR, ' pp')}/yr)"
    if before > 0:
        percent = change / before * 100.0
        return (f"{_amount_change(change, how.amount)}, {_hundredths(percent, '%')} a day "
                f"(≈ {_hundredths(percent * _DAYS_A_YEAR, '%')}/yr)")
    return f"{_amount_change(change, how.amount)} a day (≈ {_amount_change(change * _DAYS_A_YEAR, how.amount)}/yr)"


def _last_change(how: _Mark, day: int, value: float) -> tuple[float, int] | None:
    """A set rate's last change on or before ``day``, to ``value``, in its whole series (``_Mark.history``): (the value before it, its day); None if none is known.

    The change looked up is the last whose new value is ``value``: on the
    day of a change, the point held at the old value reads the change before.
    """
    if how.history is None:
        return None
    days, new, old = how.history
    position = int(np.searchsorted(days, day, "right")) - 1
    # A step back or two at most: a value held to the day another starts (``plotting._apart_at``).
    for candidate in range(position, max(position - 3, -1), -1):
        if new[candidate] == value:
            return float(old[candidate]), int(days[candidate])
    return None


@dataclass(frozen=True)
class Run:
    """An unbroken stretch of a drawn line: its points in image pixels, each one's day and the index of its value's text.

    ``x`` never decreases (a line runs forward in time). A step run's last
    value is held to ``until`` (image x, day) where the line had a point
    with no value next: matplotlib draws that step, then breaks the line.
    """

    x: np.ndarray
    y: np.ndarray
    day: np.ndarray
    text: np.ndarray
    until: tuple[float, int] | None = None
    # Each point's change (batch 44): the index of its figures in ``Curve.changes``, -1 where it has none (a line's
    # first point, with nothing before it on the chart); and how many days before the point's own day the date the
    # change names is (``Curve.dated``), 0 where it names none. Kept apart from the figures, so the figures repeat
    # and the page's data stay small: a daily yield's changes are a few dozen texts, its dates every day.
    change: np.ndarray | None = None
    back: np.ndarray | None = None


@dataclass(frozen=True)
class Curve:
    """One drawn line (a piece of a curve: Canada's monthly yields and its daily ones are two), as the read-out sees it."""

    name: str  # its legend name, as Export chart names the column
    color: str  # "#rrggbb"
    steps: bool
    projected: bool
    quoted: bool
    texts: tuple[str, ...]  # its values as written, each once
    runs: tuple[Run, ...]
    changes: tuple[str, ...] = ()  # its changes' figures as written, each once (batch 44)
    # The word before a change's date: "from" (the observation before), "on" (a set rate's last change), or None for a
    # line read day by day, whose change names no date ("... a day").
    dated: str | None = None

    def change_text(self, run: Run, index: int) -> str | None:
        """What run point ``index`` says of its change: "−3.0 bp from 2026-11-06"; None where it has none."""
        if run.change is None or run.change[index] < 0:
            return None
        figures = self.changes[int(run.change[index])]
        if self.dated is None:
            return figures
        return f"{figures} {self.dated} {date_text(int(run.day[index]) - int(run.back[index]))}"


@dataclass(frozen=True)
class Reading:
    """What the read-out says of one line: its name, colour, value, date and change, and the point read, in image pixels."""

    name: str
    color: str
    value: str
    when: str
    x: float
    y: float
    change: str | None = None  # batch 44: "−3.0 bp from 2026-11-06"; None where it has none

    @property
    def lines(self) -> tuple[str, ...]:
        """The line's lines in the read-out: "10-Year Yield", "4.12%  2026-10-27", then its change, "−3.0 bp from 2026-10-24"."""
        value = f"{self.value}  {self.when}"
        return (self.name, value) if self.change is None else (self.name, value, self.change)

    @property
    def shown(self) -> tuple[tuple[str, str], ...]:
        """Each of ``lines`` with its colour: the name in the line's, the rest in ``BOX_TEXT``."""
        return tuple(zip(self.lines, (self.color, BOX_TEXT, BOX_TEXT)))


@dataclass(frozen=True)
class Readings:
    """What the read-out says where the pointer rests: every line within reach, the nearest first (batch 11.6).

    Terry, 2026-10-27: lines that cross within 3 pixels of the pointer are
    "combined into one pop-up pane". One reading per curve (its legend name),
    so a curve drawn in pieces (a projection from its last observation,
    Canada's monthly yields then its daily ones) reads once where its pieces
    meet. The box is bordered in the nearest line's colour.
    """

    each: tuple[Reading, ...]

    @property
    def color(self) -> str:
        return self.each[0].color

    @property
    def lines(self) -> tuple[str, ...]:
        """Every line's lines (two, or three with a change), the nearest first."""
        return tuple(text for reading in self.each for text in reading.lines)


@dataclass(frozen=True)
class _Found:
    """The point of a run nearest the pointer: its distance, the point on the line, and what it reads."""

    distance: float
    x: float
    y: float
    index: int  # the point whose value is read
    day: int  # the date read: the observation's, or on a step or a projection the day under the pointer


def _nearest_line(run: Run, px: float, py: float, reach: float, box: tuple[float, float, float, float]) -> _Found | None:
    """The point of a run drawn as a line nearest (px, py), within ``reach``: the last observation on or before the day there.

    Each segment between two points is measured; the first of equally near
    segments wins. The point read is the segment's first, or its second where
    the nearest place on the segment is that point itself (batch 44, decision
    127: never a value from a later day; until then the nearer of the two). A
    run of one point draws nothing.
    """
    count = len(run.x)
    if count < 2:
        return None
    # Only the segments that reach within ``reach`` of px across (x never decreases).
    low = max(int(np.searchsorted(run.x, px - reach, "left")) - 1, 0)
    high = min(int(np.searchsorted(run.x, px + reach, "right")), count - 1)
    if high <= low:
        return None
    x0, y0, x1, y1 = run.x[low:high], run.y[low:high], run.x[low + 1:high + 1], run.y[low + 1:high + 1]
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    with np.errstate(invalid="ignore", divide="ignore"):
        along = np.where(length2 > 0, ((px - x0) * dx + (py - y0) * dy) / np.where(length2 > 0, length2, 1.0), 0.0)
    along = np.clip(along, 0.0, 1.0)
    cx, cy = x0 + along * dx, y0 + along * dy
    distance = np.where(_inside(cx, cy, box), np.hypot(px - cx, py - cy), np.inf)
    best = int(np.argmin(distance))
    if not distance[best] <= reach:
        return None
    index = low + best + (1 if along[best] >= 1.0 else 0)
    return _Found(float(distance[best]), float(run.x[index]), float(run.y[index]), index, int(run.day[index]))


def _nearest_steps(run: Run, px: float, py: float, reach: float, box: tuple[float, float, float, float]) -> _Found | None:
    """The point of a run drawn as steps ("steps-post") nearest (px, py), within ``reach``: the value in force there.

    The run is drawn as each value's flat stretch from its point to the
    next point (to ``until`` for the last), then the riser to the next value.
    On a flat stretch the value is that stretch's, the date the day under
    the point caught; on a riser the new value, from its own date. Equally
    near pieces: the first along the line wins.
    """
    count = len(run.x)
    ends_x = np.append(run.x[1:], run.until[0]) if run.until is not None else run.x[1:]
    ends_day = np.append(run.day[1:], run.until[1]) if run.until is not None else run.day[1:]
    flats = len(ends_x)
    first = int(np.searchsorted(run.x, px - reach, "left"))
    last = int(np.searchsorted(run.x, px + reach, "right"))
    candidates: list[tuple[float, int, float, float, int, int]] = []  # (distance, order, x, y, index, day)
    # Flat stretches i (from point i to its end) that reach within ``reach`` across.
    low, high = max(first - 1, 0), min(last, flats)
    if high > low:
        x0, x1, y = run.x[low:high], ends_x[low:high], run.y[low:high]
        cx = np.clip(px, x0, x1)
        distance = np.where(_inside(cx, y, box), np.hypot(px - cx, py - y), np.inf)
        best = int(np.argmin(distance))
        i = low + best
        span = float(ends_x[i] - run.x[i])
        share = (float(cx[best]) - float(run.x[i])) / span if span > 0 else 0.0
        day = int(math.floor(float(run.day[i]) + share * float(ends_day[i] - run.day[i])))
        candidates.append((float(distance[best]), 2 * i, float(cx[best]), float(y[best]), i, day))
    # Risers i (at point i, from the value before it to its own).
    low, high = max(first, 1), min(last, count)
    if high > low:
        x, before, after = run.x[low:high], run.y[low - 1:high - 1], run.y[low:high]
        cy = np.clip(py, np.minimum(before, after), np.maximum(before, after))
        distance = np.where(_inside(x, cy, box), np.hypot(px - x, py - cy), np.inf)
        best = int(np.argmin(distance))
        i = low + best
        candidates.append((float(distance[best]), 2 * i - 1, float(x[best]), float(cy[best]), i, int(run.day[i])))
    if not candidates:
        return None
    distance, _order, x, y, index, day = min(candidates)
    if not distance <= reach:
        return None
    return _Found(distance, x, y, index, day)


def _inside(x: np.ndarray, y: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    left, top, right, bottom = box
    return (x >= left - _BOX_SLACK_PX) & (x <= right + _BOX_SLACK_PX) & (y >= top - _BOX_SLACK_PX) & (y <= bottom + _BOX_SLACK_PX)


@dataclass(frozen=True)
class ChartLines:
    """Every marked line of a drawn chart, where it runs on the picture, and what it says (``reading``)."""

    box: tuple[float, float, float, float]  # the axes, (left, top, right, bottom) in image pixels
    curves: tuple[Curve, ...]  # in drawing order
    quote: tuple[int, str] | None  # the intraday quotes' day, and the words after it ("14:32 EDT (intraday, provisional)")
    # The date axis: image x = days_to_x[0] + day * days_to_x[1] (every point is on a whole day, ``payload``).
    days_to_x: tuple[float, float] = (0.0, 0.0)

    def reading(self, x: float, y: float, reach: float) -> Readings | None:
        """What every line within ``reach`` image pixels of image point (x, y) says there, the nearest first; None if none is that near.

        Each curve (by its legend name) once, at the point of its pieces
        nearest the pointer; of equally near pieces the first drawn (a
        projection's first day is its observation's last, which then reads
        as the observation). Equally near curves: the first drawn first.
        """
        left, top, right, bottom = self.box
        if not (left - reach <= x <= right + reach and top - reach <= y <= bottom + reach):
            return None
        best: dict[str, tuple[_Found, int, Curve, Run]] = {}
        for order, curve in enumerate(self.curves):
            nearest = _nearest_steps if curve.steps else _nearest_line
            for run in curve.runs:
                found = nearest(run, x, y, reach, self.box)
                kept = best.get(curve.name)
                if found is not None and (kept is None or found.distance < kept[0].distance):
                    best[curve.name] = (found, kept[1] if kept is not None else order, curve, run)
        if not best:
            return None
        ranked = sorted(best.values(), key=lambda item: (item[0].distance, item[1]))
        return Readings(tuple(
            Reading(curve.name, curve.color, curve.texts[int(run.text[found.index])], self._when(curve, run, found), found.x, found.y,
                    curve.change_text(run, found.index))
            for found, _order, curve, run in ranked
        ))

    def _when(self, curve: Curve, run: Run, found: _Found) -> str:
        day = date_text(found.day)
        if curve.projected:
            return f"{day} (projected)"
        observed = int(run.day[found.index])
        if curve.steps and found.day != observed:
            return f"{day} (observed {date_text(observed)})"
        if curve.quoted and self.quote is not None and observed == self.quote[0]:
            return f"{day}{self.quote[1]}"
        return day


def _decimated(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The indexes of the points kept: in each column of whole image pixels, the first, the last, the highest and the lowest."""
    if len(x) <= 4:
        return np.arange(len(x))
    column = np.floor(x).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, column[1:] != column[:-1]])
    ends = np.r_[starts[1:], len(x)] - 1
    group = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, len(x)]))
    by_value = np.lexsort((y, group))  # by column, then by y: each column's lowest y first, its highest last
    return np.unique(np.concatenate([starts, ends, by_value[starts], by_value[ends]]))


def _daily(days: np.ndarray, values: np.ndarray, log: bool) -> tuple[np.ndarray, np.ndarray]:
    """A projection's points, with a point on every day between two, on the straight line the axis draws (in the logarithm on a log axis)."""
    every = np.arange(int(days[0]), int(days[-1]) + 1)
    if log:
        with np.errstate(invalid="ignore", divide="ignore"):
            return every, np.exp(np.interp(every, days, np.log(values)))
    return every, np.interp(every, days, values)


def _daily_stretches(days: np.ndarray, values: np.ndarray, log: bool) -> tuple[np.ndarray, np.ndarray]:
    """``_daily`` for each stretch of a line between its breaks (a missing value), a missing value kept between two stretches; a lone point as it is.

    A point drawn a second before a day ends (a month's last value, held to
    its end, ``rates.filled_through``) falls on that day, as the steps' do.
    """
    order = np.argsort(days, kind="stable")
    days, values = days[order], values[order]
    valid = np.isfinite(days) & np.isfinite(values)
    pieces_days: list[np.ndarray] = []
    pieces_values: list[np.ndarray] = []
    for start, stop in _stretches(valid):
        stretch_days, stretch_values = np.floor(days[start:stop]), values[start:stop]
        # One point a day: the last on a day it has two (a value held to a second before midnight).
        last_of_day = np.r_[stretch_days[1:] != stretch_days[:-1], True]
        stretch_days, stretch_values = stretch_days[last_of_day], stretch_values[last_of_day]
        if len(stretch_days) > 1:
            stretch_days, stretch_values = _daily(stretch_days, stretch_values, log)
        if pieces_days:
            # A point with no value between the two stretches, on a day between them, so the sort that
            # follows (``_curve``) keeps it there and the line breaks there.
            pieces_days.append(np.array([(pieces_days[-1][-1] + stretch_days[0]) / 2]))
            pieces_values.append(np.array([np.nan]))
        pieces_days.append(stretch_days.astype(float))
        pieces_values.append(stretch_values)
    if not pieces_days:
        return np.array([]), np.array([])
    return np.concatenate(pieces_days), np.concatenate(pieces_values)


def _curve(line: Line2D, name: str, how: _Mark, height: float) -> Curve | None:
    """``line`` as the read-out sees it, or None if it draws nothing."""
    xy = np.asarray(line.get_xydata(), dtype=float)
    if not len(xy):
        return None
    days, values = xy[:, 0] - _EPOCH, xy[:, 1]
    # Drawn in steps as its series' kind says (batch 42.1, ``config.SeriesKind.in_steps``): read as the value in force.
    steps = line.get_drawstyle().startswith("steps")
    if how.projected:
        valid = np.isfinite(days) & np.isfinite(values)
        if valid.sum() < 2:
            return None
        days, values = _daily(days[valid], values[valid], line.axes.get_yscale() == "log")
    elif how.daily:
        # A series filled in (batch 42.2) is read day by day on its line, as a
        # projection is, within each stretch: a break stays a break.
        days, values = _daily_stretches(days, values, line.axes.get_yscale() == "log")
        if not len(days):
            return None
    order = np.argsort(days, kind="stable")
    days, values = days[order], values[order]
    transform = line.get_transform()
    # x from a value of 1 (finite on a log axis too): a point with no value still has its date, where a step
    # ends (``Run.until``), and the transform's 0 * NaN would lose it.
    x = transform.transform(np.column_stack([days + _EPOCH, np.ones_like(days)]))[:, 0]
    y = height - transform.transform(np.column_stack([days + _EPOCH, values]))[:, 1]
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    stretches = _stretches(valid)
    # Each stretch's observations: every point; on a step line the first row of each value.
    observed: list[np.ndarray] = []
    for start, stop in stretches:
        index = np.arange(start, stop)
        if steps:
            # A value repeated on the next rows (a quarterly figure carried on the dates of a daily series, as
            # the U.S. frame does) draws no riser: its first row is its observation, which the read-out dates.
            index = index[np.r_[True, values[index[1:]] != values[index[:-1]]]]
        observed.append(index)
    # The observations in order across the line's breaks: an observation's change is from the one before it,
    # wherever that is (a missing month between them, its date says so).
    in_order = np.concatenate(observed) if observed else np.array([], dtype=np.int64)
    whole_days = np.floor(days)
    # Python's own floats for the change's figures, point by point (a NumPy scalar costs more than the arithmetic).
    value_list, day_list = values.tolist(), whole_days.tolist()
    texts: dict[str, int] = {}
    changes: dict[str, int] = {}
    written: dict[object, str] = {}  # each change's figures, made once: a yield's repeat often
    runs: list[Run] = []
    for (start, stop), index in zip(stretches, observed):
        keep = index[_decimated(x[index], y[index])]
        until = None
        if steps and stop < len(x) and np.isfinite(x[stop]):
            until = (float(x[stop]), int(math.floor(days[stop])))
        elif steps and index[-1] < stop - 1:
            # The run ends on its last value repeated (a rate held to the chart's end): the step is drawn to there.
            until = (float(x[stop - 1]), int(math.floor(days[stop - 1])))
        indexes = np.array([texts.setdefault(how.value_format(for_writing(float(value))), len(texts)) for value in values[keep]],
                           dtype=np.int32)
        # The point before each in the line's order: the day before for a line read day by day, else the observation
        # before (``keep`` is among ``in_order``).
        position = np.searchsorted(in_order, keep)
        earlier = np.where(position > 0, in_order[np.maximum(position - 1, 0)], -1)
        change = [_change_of(how, value_list, day_list, point, before, written) for point, before in zip(keep.tolist(), earlier.tolist())]
        change_indexes = np.array([-1 if one is None else changes.setdefault(one[0], len(changes)) for one in change], dtype=np.int32)
        back = np.array([0 if one is None else one[1] for one in change], dtype=np.int64)
        runs.append(Run(x[keep], y[keep], whole_days[keep].astype(np.int64), indexes, until, change_indexes, back))
    if not runs:
        return None
    dated = None if how.daily or how.projected else "on" if how.set_rate else "from"
    return Curve(name, to_hex(line.get_color()), steps, how.projected, how.quoted, tuple(texts), tuple(runs), tuple(changes), dated)


def _change_of(
    how: _Mark, values: list[float], days: list[float], point: int, earlier: int, written: dict[object, str]
) -> tuple[str, int] | None:
    """What a line's ``point`` says of its change (batch 44): its figures, and how many days before the point the date it names is; None where nothing comes before it on the chart.

    ``days`` are whole; ``earlier`` the point before in the line's order
    (``_curve``: the observation before, across a break; -1 for none);
    ``written`` the figures already made, by what they depend on. A line read
    day by day (filled in, or a projection): from the day before, where the
    line has that day, a text naming no date (``Curve.dated`` None). A rate
    set by announcement: its last change, on that change's day, from its
    whole series where it has one (``_last_change``), else from the
    observation before, on its own day. Any other: from the observation
    before, on that one's day ("no change" where the two are equal).
    """
    now, day = values[point], int(days[point])
    if how.daily or how.projected:
        if earlier < 0 or days[earlier] != day - 1 or not math.isfinite(values[earlier]):
            return None
        before = values[earlier]
        if (now, before) not in written:
            written[now, before] = _change_a_day(how, now, before)
        return written[now, before], 0
    if how.set_rate:
        found = _last_change(how, day, now)
        if found is not None:
            return _figures(how, now, found[0]), day - found[1]
    if earlier < 0:
        return None
    before = values[earlier]
    back = 0 if how.set_rate else day - int(days[earlier])
    if now == before:
        return "no change", back
    # A change in percent depends on the difference alone (to well within a written digit); an amount's on the pair.
    key = round(now - before, 9) if how.amount is None else (now, before)
    if key not in written:
        written[key] = _figures(how, now, before)
    return written[key], back


def _stretches(valid: np.ndarray) -> list[tuple[int, int]]:
    """The (start, stop) of each stretch of True in ``valid``."""
    edges = np.diff(np.r_[0, valid.astype(np.int8), 0])
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def chart_lines(figure: Figure) -> ChartLines | None:
    """Where each marked line of ``figure`` runs on its picture, and what it says (``ChartLines``); None if it has no axes.

    Read once the figure is drawn (after ``savefig``, or a window's draw), so
    the axes are where the picture has them.
    """
    if not figure.axes:
        return None
    height = figure.bbox.height
    extent = figure.axes[0].get_window_extent()
    origin, next_day = figure.axes[0].transData.transform([(_EPOCH, 0.0), (_EPOCH + 1.0, 0.0)])[:, 0]
    curves: list[Curve] = []
    for ax in figure.axes:
        for line in ax.get_lines():
            series, how = series_of(line), getattr(line, _MARK_ATTR, None)
            if series is None or how is None:
                continue
            curve = _curve(line, series[0], how, height)
            if curve is not None:
                curves.append(curve)
    return ChartLines(
        box=(extent.x0, height - extent.y1, extent.x1, height - extent.y0),
        curves=tuple(curves),
        quote=getattr(figure, _QUOTE_ATTR, None),
        days_to_x=(float(origin), float(next_day - origin)),
    )


def _deltas(values: Sequence[int]) -> list[int]:
    """Each whole number less the one before it (the first less 0): small numbers, which pack well."""
    return np.diff(np.asarray(values, dtype=np.int64), prepend=0).tolist()


def payload(lines: ChartLines) -> dict:
    """``lines`` as the web page's browser reads them (JSON), small.

    A point's x is not sent: every point is on a whole day, and the date axis
    turns a day into x (``days_to_x``). Its day and its y, in tenths of a
    pixel, are each sent as the change from the point before (``_deltas``);
    its value as the index of its text. A chart's lines then take some 40 to
    70 KB once deflated (measured 2026-10-27: Canada's default chart 68 KB,
    its PNG 648 KB), where the points written out took 800 KB.
    """
    return {
        "box": [round(value, 2) for value in lines.box],
        "days_to_x": list(lines.days_to_x),
        "quote": list(lines.quote) if lines.quote is not None else None,
        "curves": [
            {
                "name": curve.name,
                "color": curve.color,
                "steps": curve.steps,
                "projected": curve.projected,
                "quoted": curve.quoted,
                "texts": list(curve.texts),
                # Batch 44: its changes' figures, and the word before their dates (None: they name none).
                "changes": list(curve.changes),
                "dated": curve.dated,
                "runs": [
                    {
                        "d": _deltas(run.day),
                        "y": _deltas(np.rint(run.y * 10).astype(np.int64)),
                        "t": run.text.tolist(),
                        # Each point's change: an index into the curve's changes (-1 for none), and the days back
                        # from the point's day to the date it names (``Curve.change_text``).
                        "c": run.change.tolist() if run.change is not None else [-1] * len(run.day),
                        "b": run.back.tolist() if run.back is not None else [0] * len(run.day),
                        "until": run.until[1] if run.until is not None else None,
                    }
                    for run in curve.runs
                ],
            }
            for curve in lines.curves
        ],
    }


# ---------------------------------------------------------------------------
# When the read-out shows, follows and goes
# ---------------------------------------------------------------------------


class Controller:
    """The read-out's timing, the same in each window: ``moved`` with each move of the pointer, ``stop`` to put it away.

    It shows once the pointer has stayed on lines for ``SHOW_DELAY_MS``
    (moving along them is staying), at what the pointer is on then; while
    shown it follows the pointer from line to line; once the pointer is off
    every line it stays as it was, and goes ``HIDE_DELAY_MS`` later unless the
    pointer is back on a line first. ``schedule(ms, callback)`` and
    ``cancel(handle)`` are the toolkit's timers; ``show(reading, x, y)`` puts
    the read-out by the pointer (x, y in the window's own coordinates),
    ``hide()`` takes it away.
    """

    def __init__(
        self,
        schedule: Callable[[int, Callable[[], None]], object],
        cancel: Callable[[object], None],
        show: Callable[[Readings, float, float], None],
        hide: Callable[[], None],
    ) -> None:
        self._schedule, self._cancel, self._show, self._hide = schedule, cancel, show, hide
        self.shown = False
        self._waiting: tuple[Readings, float, float] | None = None
        self._show_timer: object | None = None
        self._hide_timer: object | None = None

    def moved(self, reading: Readings | None, x: float, y: float) -> None:
        """The pointer is at (x, y), on the lines ``reading`` reads, or on none."""
        if reading is None:
            self._waiting = None
            self._stop_timer("_show_timer")
            if self.shown and self._hide_timer is None:
                self._hide_timer = self._schedule(HIDE_DELAY_MS, self._hide_now)
            return
        self._stop_timer("_hide_timer")
        if self.shown:
            self._show(reading, x, y)
            return
        self._waiting = (reading, x, y)
        if self._show_timer is None:
            self._show_timer = self._schedule(SHOW_DELAY_MS, self._show_waiting)

    def stop(self) -> None:
        """Put the read-out away now, and forget the pointer (a drag begins, a chart is drawn, the box is unticked)."""
        self._waiting = None
        self._stop_timer("_show_timer")
        self._stop_timer("_hide_timer")
        if self.shown:
            self.shown = False
            self._hide()

    def _stop_timer(self, name: str) -> None:
        timer = getattr(self, name)
        if timer is not None:
            self._cancel(timer)
            setattr(self, name, None)

    def _show_waiting(self) -> None:
        self._show_timer = None
        if self._waiting is not None:
            self.shown = True
            self._show(*self._waiting)
            self._waiting = None

    def _hide_now(self) -> None:
        self._hide_timer = None
        self.shown = False
        self._hide()


# ---------------------------------------------------------------------------
# The plain matplotlib windows (--no-gui)
# ---------------------------------------------------------------------------

# The read-out's look, here, in the window and on the page: a pale box bordered in the nearest line's colour, each
# line's name in its own colour and its value and date in this dark grey (batch 11.6).
BOX_FACE = "#fffff4"
BOX_TEXT = "#202020"
# Its corner, from the pointer (screen pixels): right of it and below, as a tooltip.
OFFSET_PX = 16
# A plain window's box: its margin inside the border, and the gap between its lines (screen pixels).
_BOX_PAD_PX = 5
_LINE_GAP_PX = 1


class _PlainWindow:
    """The read-out in one plain matplotlib window: its mouse events, its timers, a box of texts and a ring per line drawn over the chart.

    The lines are read again after every full drawing of the window (a
    resize, the toolbar's zoom), since the picture moves with them. The
    read-out is drawn by blitting where the canvas can, so a move of the
    pointer does not draw the whole chart again.
    """

    def __init__(self, figure: Figure) -> None:
        self.figure = figure
        self.canvas = figure.canvas
        self.lines: ChartLines | None = None
        self.background = None
        # The box, and as many texts (one to a line of the box: two or three to a line read, batch 44) and rings (one to
        # a line read) as the most shown yet (batch 11.6).
        self.box = FancyBboxPatch(
            (0, 0), 1, 1, boxstyle="round,pad=0", transform=IdentityTransform(), facecolor=BOX_FACE, edgecolor="#808080",
            linewidth=1.2, visible=False, animated=True, zorder=10,
        )
        figure.add_artist(self.box)
        self.texts: list[Text] = []
        self.rings: list[Line2D] = []
        self.controller = Controller(self._start_timer, lambda timer: timer.stop(), self._show, self._hide)
        self.connections = [
            self.canvas.mpl_connect("draw_event", self._drawn),
            self.canvas.mpl_connect("motion_notify_event", self._moved),
            self.canvas.mpl_connect("figure_leave_event", lambda _event: self.controller.moved(None, 0.0, 0.0)),
        ]

    def close(self) -> None:
        """Stop reading the pointer: its events disconnected, its timers stopped (``detach``)."""
        self.controller.stop()
        for connection in self.connections:
            self.canvas.mpl_disconnect(connection)

    def _start_timer(self, milliseconds: int, callback: Callable[[], None]):
        timer = self.canvas.new_timer(interval=milliseconds)
        timer.single_shot = True
        timer.add_callback(callback)
        timer.start()
        return timer

    def _drawn(self, _event) -> None:
        self.lines = chart_lines(self.figure)
        if self.canvas.supports_blit:
            self.background = self.canvas.copy_from_bbox(self.figure.bbox)
        if self.controller.shown:
            self._blit()

    def _moved(self, event) -> None:
        toolbar = getattr(self.canvas, "toolbar", None)
        if event.button is not None or (toolbar is not None and getattr(toolbar, "mode", "")):
            self.controller.stop()  # a drag, or the toolbar's zoom or pan, under way
            return
        height = self.figure.bbox.height
        reading = self.lines.reading(event.x, height - event.y, REACH_PX) if self.lines is not None else None
        self.controller.moved(reading, event.x, event.y)

    def _pooled(self, text_count: int, ring_count: int) -> tuple[list[Text], list[Line2D]]:
        """``text_count`` texts and ``ring_count`` rings, made as needed; the rest hidden."""
        identity = IdentityTransform()
        while len(self.texts) < text_count:
            self.texts.append(self.figure.text(
                0, 0, "", transform=identity, fontsize=9, va="bottom", visible=False, animated=True, zorder=11,
            ))
        while len(self.rings) < ring_count:
            ring = Line2D(
                [0], [0], transform=identity, marker="o", markersize=9, markerfacecolor="none", markeredgewidth=1.6,
                linestyle="none", visible=False, animated=True, zorder=10,
            )
            self.figure.add_artist(ring)
            self.rings.append(ring)
        for artist in (*self.texts[text_count:], *self.rings[ring_count:]):
            artist.set_visible(False)
        return self.texts[:text_count], self.rings[:ring_count]

    def _show(self, reading: Readings, x: float, y: float) -> None:
        height = self.figure.bbox.height
        shown = [line for one in reading.each for line in one.shown]
        texts, rings = self._pooled(len(shown), len(reading.each))
        for text, (content, color) in zip(texts, shown):
            text.set_text(content)
            text.set_color(color)
        for ring, one in zip(rings, reading.each):
            ring.set_data([one.x], [height - one.y])
            ring.set_markeredgecolor(one.color)
        # Each text a line of the box, the nearest line's name at the top. Measured shown: matplotlib measures a hidden
        # text as a box of one pixel (animated, a shown text is still drawn only by ``_blit``).
        renderer = self.canvas.get_renderer()
        for text in texts:
            text.set_position((0, 0))
            text.set_visible(True)
        sizes = [text.get_window_extent(renderer) for text in texts]
        step = max(size.height for size in sizes) + _LINE_GAP_PX
        width = max(size.width for size in sizes) + 2 * _BOX_PAD_PX
        tall = step * len(texts) - _LINE_GAP_PX + 2 * _BOX_PAD_PX
        # Right of the pointer and below it, turned back where that would leave the figure.
        left = x + OFFSET_PX if x + OFFSET_PX + width <= self.figure.bbox.width else x - OFFSET_PX - width
        bottom = y - OFFSET_PX - tall if y - OFFSET_PX - tall >= 0 else y + OFFSET_PX
        left, bottom = max(left, 0), max(bottom, 0)
        for index, text in enumerate(texts):
            text.set_position((left + _BOX_PAD_PX, bottom + tall - _BOX_PAD_PX - (index + 1) * step + _LINE_GAP_PX))
        self.box.set_bounds(left, bottom, width, tall)
        self.box.set_edgecolor(reading.color)
        for artist in (self.box, *texts, *rings):
            artist.set_visible(True)
        self._blit()

    def _hide(self) -> None:
        for artist in (self.box, *self.texts, *self.rings):
            artist.set_visible(False)
        self._blit()

    def _blit(self) -> None:
        if self.background is None:
            self.canvas.draw_idle()
            return
        self.canvas.restore_region(self.background)
        for artist in (*self.rings, self.box, *self.texts):
            if artist.get_visible():
                self.figure.draw_artist(artist)
        self.canvas.blit(self.figure.bbox)


def attach(figure: Figure) -> None:
    """Give a plain matplotlib window's chart the read-out (--no-gui): matplotlib's own mouse events and timers."""
    figure._ratesplot_hover_window = _PlainWindow(figure)  # kept with the figure, or its callbacks would be dropped


def detach(figure: Figure) -> None:
    """Take the read-out off a plain window's chart before it is drawn afresh (the automatic refresh, batch 11.3); ``attach`` gives it again."""
    window = getattr(figure, "_ratesplot_hover_window", None)
    if window is not None:
        window.close()
        del figure._ratesplot_hover_window


def reach_in_image(scale: float) -> float:
    """``REACH_PX`` screen pixels in image pixels, for a picture shown at ``scale`` screen pixels per image pixel."""
    return REACH_PX / scale if scale > 0 else REACH_PX
