#!/usr/bin/env python3
"""Check the projections to today of the population, the price index and inflation (batch 43.1), with no network.

Made-up series stand in for the sources, so every figure checked is worked out here:

* ``latest.project_series``: not with --projections off, on a chart ending before today, past 400 days, or for a
  series not projected; a month's series a figure for each month through the month after the End's, dated by its first
  day, on the straight line from the last figure at its pace; a series of moments one figure, on the End;
* the pace by the days between the two figures (``latest._per_day``), a missing month a year back taking the one before;
* where a projection takes over (``rates.projection_start``) and its points in each form (``projection_points``):
  through the months' middles, in steps held to each month's last instant, a run of its own after a gap, cut at the
  End on its line;
* inflation (``rates.projected_inflation``): each month after the index's last its rise over the year before,
  ``RateCurve.projected`` the index's last month, a curve lacking that month projected from its own first;
* --constant (``measures.in_constant_prices``): the base the last published month, an amount after it divided by its
  month's projected index;
* the drawing: the extra axis's curve split where its projection takes over (``plotting.extra_points``), drawn faint and
  marked projected on its own axis; inflation's projection faint, read day by day, its end label "≈";
* the box: greyed only while none of the smooth series is drawn (``options.idle_option_reasons``).

    python tools/check_projections.py

Exit status 0 only if every check passes.
"""
from __future__ import annotations

import contextlib
import io
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ratesplot import latest, plotting, rates  # noqa: E402
from ratesplot.config import DATE_COLUMN, PROJECTION_ALPHA, PlotConfig  # noqa: E402
from ratesplot.export import INDEX_AXIS, POPULATION_AXIS, series_of  # noqa: E402
from ratesplot.hover import _MARK_ATTR  # noqa: E402
from ratesplot.measures import PRICE_BASE_ATTR, in_constant_prices  # noqa: E402
from ratesplot.options import idle_option_reasons  # noqa: E402
from ratesplot.plotting import CDN  # noqa: E402

TODAY = pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()
SECOND = pd.Timedelta(seconds=1)


def _monthly(last: pd.Timestamp, months: int, first_value: float, step: float, missing: tuple[pd.Timestamp, ...] = ()) -> pd.Series:
    """A made-up monthly index: ``months`` months to ``last`` (first days), rising by ``step`` a month, ``missing`` left out."""
    dates = pd.date_range(end=last, periods=months, freq="MS")
    values = pd.Series(first_value + step * np.arange(months, dtype=float), index=dates)
    return values.drop(list(missing))


def _quietly(function, *args, **kwargs):
    """Call ``function`` with its message-log lines kept out of the report."""
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


def main() -> int:
    results: list[bool] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        results.append(bool(ok))
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f": {detail}"))

    end = TODAY
    config = PlotConfig(start=end - pd.DateOffset(years=2), end=end)
    last_month = (end - pd.DateOffset(months=2)).to_period("M").to_timestamp()  # two months behind, as a CPI is
    index = _monthly(last_month, 40, 100.0, 0.25)
    end_month = end.to_period("M").to_timestamp()

    # --- project_series: when it carries a series on, and when not --------------------------------------------------
    print("When a series is carried on (latest.project_series)")
    _same, none = _quietly(latest.project_series, index, replace(config, projections=False), "price_index", "x")
    check("--projections off: not carried on", none is None and _same is index)
    past = replace(config, end=end - pd.Timedelta(days=30))
    check("a chart ending before today: not carried on", _quietly(latest.project_series, index, past, "price_index", "x")[1] is None)
    old = _monthly(end - pd.DateOffset(months=15), 40, 100.0, 0.25)
    check("a last figure more than 400 days old: not carried on", _quietly(latest.project_series, old, config, "price_index", "x")[1] is None)
    check("a series not projected (a policy rate): not carried on", _quietly(latest.project_series, index, config, "policy", "x")[1] is None)

    projected, start = _quietly(latest.project_series, index, config, "price_index", "x")
    ahead = projected.loc[projected.index > last_month]
    expected_months = pd.date_range(last_month + pd.DateOffset(months=1), end_month + pd.DateOffset(months=1), freq="MS")
    check("monthly: from the last figure", start == last_month, start)
    check("monthly: a figure each month through the month after the End's, on its first day",
          ahead.index.equals(expected_months), list(ahead.index.strftime("%Y-%m-%d")))
    year_before = last_month - pd.DateOffset(years=1)
    per_day = (index.loc[last_month] - index.loc[year_before]) / (last_month - year_before).days
    straight = index.loc[last_month] + per_day * (ahead.index - last_month).days.to_numpy()
    check("monthly: on the straight line at the year's pace", np.allclose(ahead.to_numpy(), straight), ahead.to_numpy() - straight)
    check("monthly: the figures before kept", projected.loc[projected.index <= last_month].equals(index))

    population = pd.Series([1000.0, 1010.0, 1020.0, 1030.0, 1040.0],
                           index=pd.DatetimeIndex([last_month - pd.DateOffset(months=3 * k) for k in range(4, -1, -1)]))
    carried, population_from = _quietly(latest.project_series, population, config, "population", "x")
    pace = (1040.0 - 1000.0) / (last_month - (last_month - pd.DateOffset(months=12))).days
    check("moments: one figure, on the End", list(carried.index[-1:]) == [end] and len(carried) == len(population) + 1)
    check("moments: its value on the line", np.isclose(carried.iloc[-1], 1040.0 + pace * (end - last_month).days), carried.iloc[-1])
    check("moments: from the last estimate", population_from == last_month)

    # --- the pace by the days between the figures --------------------------------------------------------------------
    print("The pace (latest._per_day)")
    gap = _monthly(last_month, 40, 100.0, 0.25, missing=(year_before,))
    found = latest._year_before(gap, last_month)
    check("a month missing a year back: the one before it taken", found is not None and found[1][0] == year_before - pd.DateOffset(months=1), found)
    days = (last_month - (year_before - pd.DateOffset(months=1))).days
    check("divided by the days between the two (13 months' rise over their days)",
          np.isclose(latest._per_day(*found), 13 * 0.25 / days), latest._per_day(*found))
    check("a full year apart: the year's days", np.isclose(latest._per_day((pd.Timestamp("2026-06-30"), 112.0), (pd.Timestamp("2025-06-30"), 100.0)), 12.0 / 365))

    # --- where a projection takes over, and its points ---------------------------------------------------------------
    print("A projection's points (rates.projection_start, projection_points)")
    october = pd.Timestamp("2026-10-01")
    check("middles: the month's middle", rates.projection_start(october, "middles") == pd.Timestamp("2026-10-16"))
    check("steps: the month's last instant", rates.projection_start(october, "steps") == pd.Timestamp("2026-11-01") - SECOND)
    check("points: its own date", rates.projection_start(october, "points") == october)
    window = PlotConfig(start=pd.Timestamp("2026-01-01"), end=pd.Timestamp("2026-12-10"))
    figures = pd.Series([10.0, 11.0, 12.0], index=pd.DatetimeIndex(["2026-11-01", "2026-12-01", "2027-01-01"]))
    steps = rates.projection_points((rates.projection_start(october, "steps"), 9.0), figures, window, form="steps")
    check("steps: from the last figure's month's end, each month across its month, the riser in its last instant",
          list(steps.index[:4]) == [pd.Timestamp("2026-11-01") - SECOND, pd.Timestamp("2026-11-01"), pd.Timestamp("2026-12-01") - SECOND,
                                    pd.Timestamp("2026-12-01")]
          and list(steps.to_numpy()[:4]) == [9.0, 10.0, 10.0, 11.0], steps)
    check("steps: cut at the End, its month's figure there", steps.index[-1] == window.end and steps.iloc[-1] == 11.0, steps.tail(2))
    middles = rates.projection_points((rates.projection_start(october, "middles"), 9.0), figures, window, form="middles")
    on_line = 10.0 + (11.0 - 10.0) * (window.end - pd.Timestamp("2026-11-16")).days / (pd.Timestamp("2026-12-16") - pd.Timestamp("2026-11-16")).days
    check("middles: through the months' middles", list(middles.index[:3]) == [pd.Timestamp("2026-10-16"), pd.Timestamp("2026-11-16"), window.end], middles)
    check("middles: the End's value on the line", np.isclose(middles.iloc[-1], on_line), (middles.iloc[-1], on_line))
    run = rates.projection_points(None, figures, window, form="middles")
    check("after a gap: a run of its own from its first month's first day", run.index[0] == pd.Timestamp("2026-11-01") and run.iloc[0] == 10.0, run.head(2))
    late = PlotConfig(start=pd.Timestamp("2026-11-20"), end=pd.Timestamp("2026-12-10"))
    cut = rates.projection_points((rates.projection_start(october, "steps"), 9.0), figures, late, form="steps")
    check("a window starting inside it: from the Start, on its line", cut.index[0] == late.start and cut.iloc[0] == 10.0, cut.head(2))

    # --- inflation ---------------------------------------------------------------------------------------------------
    print("Inflation (rates.projected_inflation)")
    rise = rates.twelve_month_rise(index)
    curve = rates.RateCurve(rates.INFLATION_KEY, rates.INFLATION_LABEL, rise, rates.INFLATION_STYLE, title="Inflation",
                            holds=rates.holding(rise, rates.holds_of("inflation")))
    real_prices = rates.consumer_prices
    try:
        rates.consumer_prices = lambda country, adjusted=False: index
        carried_on = _quietly(rates.projected_inflation, curve, "cdn", config)
        rates.consumer_prices = lambda country, adjusted=False: gap
        lacking = rates.RateCurve(rates.INFLATION_KEY, rates.INFLATION_LABEL, rise.drop(last_month), rates.INFLATION_STYLE,
                                  holds=rates.holding(rise.drop(last_month), rates.holds_of("inflation")))
        from_gap = _quietly(rates.projected_inflation, lacking, "cdn", config)
        off = _quietly(rates.projected_inflation, curve, "cdn", replace(config, projections=False))
    finally:
        rates.consumer_prices = real_prices
    check("projections off: the curve as published", off is curve)
    check("RateCurve.projected: the index's last month", carried_on.projected == last_month, carried_on.projected)
    after = carried_on.values.loc[carried_on.values.index > last_month]
    expected = (projected.reindex(after.index) / index.reindex(after.index - pd.DateOffset(years=1)).to_numpy() - 1.0) * 100.0
    check("each projected month: the projected index's rise over the published one a year before",
          after.index.equals(expected_months) and np.allclose(after.to_numpy(), expected.to_numpy()), after - expected)
    check("its holds: one per value", carried_on.holds is not None and carried_on.holds.index.equals(carried_on.values.index))
    check("a curve lacking the index's last month: projected from the month after it",
          from_gap.projected == last_month and from_gap.values.loc[from_gap.values.index > last_month - pd.DateOffset(months=1)].index[0]
          == last_month + pd.DateOffset(months=1), from_gap.values.tail(4))

    # --- --constant --------------------------------------------------------------------------------------------------
    print("Inflation adjusted (measures.in_constant_prices)")
    macro = pd.DataFrame({DATE_COLUMN: pd.DatetimeIndex([last_month - pd.DateOffset(months=6), end]),
                          CDN.debt_column: [500.0, 520.0]})
    constant = _quietly(in_constant_prices, macro, CDN, projected, end, published=start)
    check("the base: the last month published", constant.attrs[PRICE_BASE_ATTR] == last_month, constant.attrs[PRICE_BASE_ATTR])
    divided = 520.0 / projected.loc[end_month] * index.loc[last_month]
    check("an amount after it: divided by its month's projected index", np.isclose(constant[CDN.debt_column].iloc[-1], divided),
          (constant[CDN.debt_column].iloc[-1], divided))
    held = _quietly(in_constant_prices, macro, CDN, index, end)
    check("without the projection: divided by the last published, as before", np.isclose(held[CDN.debt_column].iloc[-1], 520.0))

    # --- the drawing -------------------------------------------------------------------------------------------------
    print("The drawing (plotting.extra_points, add_macro_line, add_rate_lines)")
    for daily in (True, False):
        drawn_config = replace(config, daily=daily)
        extra = plotting.ExtraCurve(projected, label="Consumer price index", title="CPI", axis_label="CPI", style={"color": "deeppink", "linewidth": 2.5},
                                    value_format=lambda value: f"{value:.1f}", tick_format=lambda value: f"{value:.0f}",
                                    export_axis=INDEX_AXIS, kind="price_index", held_across_month=True, projected_from=start)
        frame, at = plotting.extra_points(extra, drawn_config)
        form = "middles" if daily else "steps"
        check(f"{form}: the projection takes over where the last figure's line ends", at == rates.projection_start(start, form), at)
        check(f"{form}: drawn to the End", frame[DATE_COLUMN].iloc[-1] == end, frame.tail(2))
        figure = Figure()
        ax = figure.add_subplot()
        line = plotting.add_macro_line(ax, frame, enabled=True, column=extra.label, label=extra.label, style=extra.style,
                                       value_format=extra.value_format, projected_from=at, axis=extra.export_axis, filled=daily)
        pieces = ax.get_lines()
        faint = [piece for piece in pieces if piece.get_alpha() == PROJECTION_ALPHA]
        check(f"{form}: its figures solid and its projection faint", line is not None and len(pieces) == 2 and len(faint) == 1)
        check(f"{form}: both pieces exported as the index, on its axis", all(series_of(piece) == (extra.label, INDEX_AXIS) for piece in pieces),
              [series_of(piece) for piece in pieces])
    moments = plotting.ExtraCurve(carried, label="Population", title="Population", axis_label="Persons", style={"color": "darkgoldenrod"},
                                  value_format=str, tick_format=str, export_axis=POPULATION_AXIS, kind="population", projected_from=population_from)
    frame, at = plotting.extra_points(moments, config)
    check("the population: from its last estimate, straight to the End",
          at == population_from and list(frame[DATE_COLUMN].iloc[-2:]) == [population_from, end], frame.tail(3))

    figure = Figure()
    ax = figure.add_subplot()
    pairs = plotting.add_rate_lines(ax, [carried_on], config)
    pieces = ax.get_lines()
    check("inflation: its figures and its projection, the projection faint",
          len(pieces) == 2 and pieces[0].get_alpha() is None and pieces[1].get_alpha() == PROJECTION_ALPHA, [piece.get_alpha() for piece in pieces])
    mark = getattr(pieces[1], _MARK_ATTR, None)
    check("inflation: the projection read day by day as a projection", mark is not None and mark.projected and not mark.daily, mark)
    check("inflation: its end label written with the approximate sign", plotting._end_label_format(pairs[0][1], config)(2.5).startswith("≈"))
    check("inflation: its end label read from the projection", plotting.last_piece(pairs[0][0]) is pieces[1])
    gone = plotting.add_rate_lines(Figure().add_subplot(), [carried_on], replace(config, end=last_month + pd.Timedelta(days=10)))
    check("a projection outside the window: the curve drawn as published, not projected", gone and gone[0][1].projected is None)

    # --- the box -----------------------------------------------------------------------------------------------------
    print("The box (options.idle_option_reasons)")
    check("greyed with no smooth series drawn", "projections" in idle_option_reasons(False, False, False))
    check("not greyed with the price index or the population alone", "projections" not in idle_option_reasons(False, False, False, extra_curve=True))
    check("not greyed with inflation alone", "projections" not in idle_option_reasons(False, False, False, inflation=True))
    check("not greyed with GDP", "projections" not in idle_option_reasons(False, True, False))

    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
