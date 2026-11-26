#!/usr/bin/env python3
"""Check the projections to today of the population, the price index and inflation (batches 43.1, 43.2), with no network.

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
* the formulas of batch 43.2: the seasonal swing carried on exactly for a steady rise with a fixed swing, one year's
  holding the twelve-month rise, a missing month filled from its neighbours, too little history giving none; growth,
  the quarter's pace and the damped trend; the index not seasonally adjusted carried on by the swing of the years
  ``latest.SEASONAL_SWING_YEARS``, the adjusted one and a short one on the straight line, and the message log saying so;
* its later stage (batch 43.2, 8.27): how often a series is figured (``latest._figure_period``); the seasonal swing, the
  quarter's pace and the damped trend on a quarterly series, a date within a quarter between two quarters' figures;
  the half year's pace (``latest.half_year``); the right axis's span by kind (``latest._pace_span``), and
  ``project_to_now`` carrying a sum over a trailing year at its half year's pace and debt at its year's, the message
  log saying which;
* batch 43.3's faster figures: the current account steered by trade (``latest._trade_steered``) on trade's last
  date, between its figures and past it, none where trade ends with the curve or is not known, through
  ``project_to_now`` with its words; ``payments.trade_for_projection`` none where it cannot serve; the ONS's sooner
  quarters (``uk_data._with_sooner_quarters``) and the U.S.' monthly trade (``payments._with_monthly_quarters``) with
  their sources stood in for; the legend's words (``config.projection_label``);
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

from ratesplot import latest, payments, plotting, rates, uk_data  # noqa: E402
from ratesplot.config import (  # noqa: E402
    DATE_COLUMN,
    PAYMENTS_CREDITS_COLUMN,
    PAYMENTS_DEBITS_COLUMN,
    PROJECTION_ALPHA,
    PROJECTION_LABEL,
    PROJECTION_LABEL_STEERED,
    PROJECTION_LABEL_TRADE,
    SERIES_KINDS,
    STATCAN_CDN_MONTHLY_TRADE_VECTORS,
    PlotConfig,
    projection_label,
)
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

    # --- the formulas (batch 43.2) ------------------------------------------------------------------------------------
    print("The formulas (latest.seasonal, growth, quarter, damped, _formula_for)")
    ten_years = pd.date_range(end=last_month, periods=12 * 10 + 1, freq="MS")
    swing = np.array([0.0, 0.4, 0.9, 1.1, 1.0, 0.8, 0.9, 1.0, 0.7, 0.5, 0.2, 0.3]) / 100  # by calendar month
    pace = 0.0025  # a month, in logarithms
    steady_logs = np.log(100.0) + pace * np.arange(len(ten_years)) + swing[ten_years.month - 1]
    swinging = pd.Series(np.exp(steady_logs), index=ten_years)
    later = pd.date_range(last_month + pd.DateOffset(months=1), periods=15, freq="MS")
    truth = np.exp(steady_logs[-1] + pace * np.arange(1, 16) + swing[later.month - 1] - swing[last_month.month - 1])
    for years in (1, 8):
        check(f"seasonal({years}): a steady rise with a fixed swing carried on exactly, past twelve months too",
              np.allclose(latest.seasonal(years)(swinging, later), truth), latest.seasonal(years)(swinging, later) - truth)
    noisy = swinging * np.exp(np.random.default_rng(43).normal(0.0, 0.003, len(swinging)))
    held = latest.seasonal(1)(noisy, later[:3])
    last_rise = noisy.iloc[-1] / noisy.iloc[-13]
    check("seasonal(1): the last twelve-month rise held", np.allclose(held / noisy.reindex(later[:3] - pd.DateOffset(years=1)).to_numpy(), last_rise))
    lacking_month = ten_years[-20]
    logs, _period = latest._period_logs(swinging.drop(lacking_month))
    month = lacking_month.to_period("M")
    check("a month missing within: the middle of its neighbours' logarithms",
          np.isclose(logs[month], (np.log(swinging.iloc[-21]) + np.log(swinging.iloc[-19])) / 2) and len(logs) == len(ten_years))
    check("seasonal(8): too little history (40 months) gives none", latest.seasonal(8)(index, later) is None)
    exponential = pd.Series(np.exp(np.log(100.0) + pace * np.arange(len(ten_years))), index=ten_years)
    steady = np.exp(np.log(exponential.iloc[-1]) + pace * np.arange(1, 4))
    for name, formula in (("growth", latest.growth), ("quarter", latest.quarter)):
        got = formula(exponential, later[:3])
        check(f"{name}: steady growth carried on exactly", np.allclose(got, steady, rtol=2e-4), got - steady)
    phi = 0.8
    damped_logs = np.log(exponential.iloc[-1]) + pace * phi * (1 - phi ** np.arange(1, 4)) / (1 - phi)
    check("damped(0.8): each month's rate 0.8 times the month's before", np.allclose(latest.damped(phi)(exponential, later[:3]), np.exp(damped_logs)))
    unadjusted, _from = _quietly(latest.project_series, swinging, config, "price_index", "x")
    months_ahead = unadjusted.index[unadjusted.index > last_month]
    check(f"the index not seasonally adjusted: by the seasonal swing of the {latest.SEASONAL_SWING_YEARS} years before",
          np.allclose(unadjusted.loc[months_ahead].to_numpy(), latest.seasonal(latest.SEASONAL_SWING_YEARS)(swinging, months_ahead)))
    adjusted, _from = _quietly(latest.project_series, swinging, config, "price_index", "x", adjusted=True)
    check("the index seasonally adjusted: on the straight line",
          np.allclose(adjusted.loc[months_ahead].to_numpy(), latest.straight(swinging, months_ahead)))
    check("too little history for the swing: on the straight line", np.allclose(ahead.to_numpy(), latest.straight(index, ahead.index)))
    words = io.StringIO()
    with contextlib.redirect_stdout(words):
        latest.project_series(swinging, config, "price_index", "the index")
    check("the message log names the swing", f"with the seasonal swing of the {latest.SEASONAL_SWING_YEARS} years before" in words.getvalue(),
          words.getvalue())

    # --- the later stage: quarterly series and the right axis's pace (batch 43.2, 8.27) -------------------------------
    print("Quarterly series and the right axis's pace (latest._figure_period, half_year, _pace_span, project_to_now)")
    check("monthly figures: counted by month", latest._figure_period(index) == "M")
    starts = pd.date_range(end=last_month.to_period("Q").start_time, periods=4 * 10 + 1, freq="QS")  # a quarter's first days
    check("quarterly figures: counted by quarter", latest._figure_period(pd.Series(1.0, index=starts)) == "Q")
    years = pd.date_range(end=last_month, periods=12, freq="YS")
    check("yearly figures: not counted", latest._figure_period(pd.Series(1.0, index=years)) is None
          and latest.seasonal(1)(pd.Series(1.0, index=years), years[-1:] + pd.DateOffset(years=1)) is None)
    quarter_swing = np.array([0.0, 0.6, 1.2, 0.4]) / 100  # by calendar quarter
    quarter_pace = 0.004  # a quarter, in logarithms
    quarter_logs = np.log(1000.0) + quarter_pace * np.arange(len(starts)) + quarter_swing[starts.quarter - 1]
    by_quarter = pd.Series(np.exp(quarter_logs), index=starts)
    next_quarters = pd.date_range(starts[-1] + pd.DateOffset(months=3), periods=6, freq="QS")
    quarter_truth = np.exp(quarter_logs[-1] + quarter_pace * np.arange(1, 7) + quarter_swing[next_quarters.quarter - 1]
                           - quarter_swing[starts[-1].quarter - 1])
    for years_back in (1, 8):
        got = latest.seasonal(years_back)(by_quarter, next_quarters)
        check(f"quarterly seasonal({years_back}): a steady rise with a fixed swing carried on exactly, past four quarters too",
              np.allclose(got, quarter_truth), got - quarter_truth)
    within = next_quarters[0] + pd.Timedelta(days=45)
    between = latest.seasonal(8)(by_quarter, pd.DatetimeIndex([within]))[0]
    fraction = 45 / (365.25 / 4)
    expected_between = np.exp((1 - fraction) * np.log(quarter_truth[0]) + fraction * np.log(quarter_truth[1]))
    check("quarterly seasonal: a date within a quarter between two quarters' figures", np.isclose(between, expected_between), (between, expected_between))
    steady_quarters = pd.Series(np.exp(np.log(1000.0) + quarter_pace * np.arange(len(starts))), index=starts)
    steady_ahead = np.exp(np.log(steady_quarters.iloc[-1]) + quarter_pace * np.arange(1, 4))
    got = latest.quarter(steady_quarters, next_quarters[:3])
    check("quarterly quarter: steady growth carried on exactly", np.allclose(got, steady_ahead), got - steady_ahead)
    damped_quarters = np.log(steady_quarters.iloc[-1]) + quarter_pace * phi * (1 - phi ** np.arange(1, 4)) / (1 - phi)
    check("quarterly damped(0.8): each quarter's rate 0.8 times the quarter's before",
          np.allclose(latest.damped(phi)(steady_quarters, next_quarters[:3]), np.exp(damped_quarters)))

    # A sum over a trailing year that turns: a quarter apiece for years, then three a quarter for two quarters.
    ends = pd.date_range(end=(end - pd.DateOffset(months=4)).to_period("Q").end_time.normalize(), periods=12, freq="QE")
    turning = pd.Series(100.0 + np.concatenate([np.arange(10.0), 9.0 + 3.0 * np.arange(1, 3)]), index=ends)
    half = latest.half_year(turning, pd.DatetimeIndex([end]))[0]
    half_pace = (turning.iloc[-1] - turning.iloc[-3]) / (ends[-1] - ends[-3]).days
    check("half_year: on the straight line at the pace since the figure two quarters before",
          np.isclose(half, turning.iloc[-1] + half_pace * (end - ends[-1]).days), (half, half_pace))
    check("half_year: steeper than the year's after a turn", half > latest.straight(turning, pd.DatetimeIndex([end]))[0])
    for key, days in (("gdp", 181), ("interest", 181), ("payments_credits", 181), ("payments_debits", 181), ("debt", 365), ("net_debt", 365)):
        check(f"_pace_span: {key} over {days} days", latest._pace_span(SERIES_KINDS[key])[0] == days, latest._pace_span(SERIES_KINDS[key]))
    debt = pd.Series(500.0 + 2.0 * np.arange(12), index=ends)
    history = pd.DataFrame({CDN.gdp_column: turning, CDN.debt_column: debt})
    rows = pd.DataFrame({DATE_COLUMN: list(ends) + [end]})
    rows[CDN.gdp_column] = list(turning) + [turning.iloc[-1]]
    rows[CDN.debt_column] = list(debt) + [debt.iloc[-1]]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        carried_rows = latest.project_to_now(rows, {CDN.gdp_column: ends[-1], CDN.debt_column: ends[-1]}, config, history)
    at_end = carried_rows.loc[carried_rows[DATE_COLUMN] == end].iloc[0]
    check("project_to_now: a sum over a trailing year at its half year's pace",
          np.isclose(at_end[CDN.gdp_column], turning.iloc[-1] + half_pace * (end - ends[-1]).days), at_end[CDN.gdp_column])
    year_pace = (debt.iloc[-1] - debt.iloc[-5]) / (ends[-1] - ends[-5]).days
    check("project_to_now: debt at its year's pace, as before",
          np.isclose(at_end[CDN.debt_column], debt.iloc[-1] + year_pace * (end - ends[-1]).days), at_end[CDN.debt_column])
    lines = printed.getvalue().splitlines()
    check("project_to_now: the message log says each curve's span",
          any(CDN.gdp_column in line and line.endswith("its pace over the half year before") for line in lines)
          and any(CDN.debt_column in line and line.endswith("its pace over the year before") for line in lines), lines)

    # --- faster figures (batch 43.3) ----------------------------------------------------------------------------------
    print("Faster figures (latest._trade_steered, payments.trade_for_projection, the sooner quarters, the legend's words)")
    trade = pd.Series(300.0 + 5.0 * np.arange(12), index=ends)
    trade.iloc[-1] += 40.0  # the quarter only trade has: off its line, so steering differs from the pace
    rest = pd.Series(200.0 + 1.0 * np.arange(12), index=ends)
    credits = (trade + rest).iloc[:-1]  # the current account a quarter behind trade
    start, earlier = ends[-2], ends[-4]
    steer_dates = pd.Series([ends[-2] + pd.Timedelta(days=46), ends[-1], end])
    steered, note = latest._trade_steered(steer_dates, start, float(credits.iloc[-1]), (earlier, float(credits.loc[earlier])), trade)
    rest_per_day = (rest.loc[start] - rest.loc[earlier]) / (start - earlier).days
    at_trade_end = credits.iloc[-1] + (trade.iloc[-1] - trade.loc[start]) + rest_per_day * (ends[-1] - start).days
    check("trade steering: on trade's last date, trade as observed and the rest at its own pace",
          np.isclose(steered.iloc[1], at_trade_end), (steered.iloc[1], at_trade_end))
    middle = steer_dates.iloc[0]
    trade_middle = trade.loc[start] + (trade.iloc[-1] - trade.loc[start]) * (middle - start).days / (ends[-1] - start).days
    check("trade steering: between two figures, trade straight between them",
          np.isclose(steered.iloc[0], credits.iloc[-1] + (trade_middle - trade.loc[start]) + rest_per_day * (middle - start).days), steered.iloc[0])
    trade_per_day = (trade.iloc[-1] - trade.iloc[-3]) / (ends[-1] - ends[-3]).days
    beyond = at_trade_end + (trade_per_day + rest_per_day) * (end - ends[-1]).days
    check("trade steering: past trade's last, trade at its own half year's pace", np.isclose(steered.iloc[2], beyond), (steered.iloc[2], beyond))
    check("trade steering: the note", note.startswith(f"trade as observed to {ends[-1]:%Y-%m-%d} (+0.0 billion since)"), note)
    check("trade steering: none where trade ends with the curve",
          latest._trade_steered(steer_dates, start, float(credits.iloc[-1]), (earlier, float(credits.loc[earlier])), trade.iloc[:-1]) is None)
    check("trade steering: none where trade is not known at the pace's start",
          latest._trade_steered(steer_dates, start, float(credits.iloc[-1]), (earlier, float(credits.loc[earlier])), trade.loc[ends[-3]:]) is None)
    pair = pd.DataFrame({PAYMENTS_CREDITS_COLUMN: trade})
    pay_rows = pd.DataFrame({DATE_COLUMN: list(ends[:-1]) + [end]})
    pay_rows[PAYMENTS_CREDITS_COLUMN] = list(credits) + [credits.iloc[-1]]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        steered_rows = latest.project_to_now(pay_rows, {PAYMENTS_CREDITS_COLUMN: start}, config, credits.to_frame(PAYMENTS_CREDITS_COLUMN), trade=pair)
    check("project_to_now: the current account steered by trade",
          np.isclose(steered_rows.loc[steered_rows[DATE_COLUMN] == end, PAYMENTS_CREDITS_COLUMN].iloc[0], beyond)
          and steered_rows.attrs[latest.STEERED_ATTR] == [PAYMENTS_CREDITS_COLUMN], steered_rows.tail(2))
    check("project_to_now: the message log says trade steers it", f"{PAYMENTS_CREDITS_COLUMN}: from {start:%Y-%m-%d}, trade as observed" in printed.getvalue(),
          printed.getvalue())
    for words, steered_set in ((PROJECTION_LABEL, set()), (PROJECTION_LABEL_STEERED, {CDN.debt_column}), (PROJECTION_LABEL_TRADE, {PAYMENTS_CREDITS_COLUMN}),
                               (f"{PROJECTION_LABEL_STEERED}, credits and debits trade", {CDN.debt_column, PAYMENTS_DEBITS_COLUMN})):
        check(f"the legend's words: {words!r}", projection_label(steered_set) == words, projection_label(steered_set))
    current = replace(config, payments=True)
    for why, key, asked in (("France (its months as far for both pairs)", "fr", current), ("Germany (monthly already)", "de", current),
                            ("trade drawn", "us", replace(current, payments_items=("trade",))), ("--payments off", "us", config),
                            ("--projections off", "uk", replace(current, projections=False)), ("a chart ending before today", "uk", replace(current, end=past.end))):
        check(f"trade_for_projection: none for {why}", payments.trade_for_projection(key, asked) is None)
    real_fetch = payments.fetch_payments
    try:
        payments.fetch_payments = lambda key, item: pd.DataFrame({DATE_COLUMN: [end], PAYMENTS_CREDITS_COLUMN: [1.0], PAYMENTS_DEBITS_COLUMN: [2.0]})
        served = payments.trade_for_projection("cdn", current)
        check("trade_for_projection: Canada's trade served (batch 43.3c)", served is not None and list(served.columns) == [PAYMENTS_CREDITS_COLUMN, PAYMENTS_DEBITS_COLUMN], served)
    finally:
        payments.fetch_payments = real_fetch

    # The sooner quarters, with the sources stood in for.
    class _Answer:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def ons_answer(quarters):
        return _Answer({"description": {"unit": "m"}, "quarters": [{"date": f"{q.year} Q{q.quarter}", "value": str(v)} for q, v in quarters.items()]})

    main_ons = pd.Series([12.0, 10.0, 11.0], index=pd.DatetimeIndex(["2025-12-31", "2026-03-31", "2026-06-30"]))
    sooner_ons = pd.Series([99.0, 11.0, 13.0], index=pd.DatetimeIndex(["2026-03-31", "2026-06-30", "2026-09-30"]))
    real_get = uk_data.uk_get
    try:
        uk_data.uk_get = lambda url, *a, **k: ons_answer(sooner_ons)
        joined = _quietly(uk_data._with_sooner_quarters, "YBHA", main_ons)
        check("ONS sooner: its quarters after the series' last added, the earlier ones the main dataset's",
              list(joined.index) == list(main_ons.index) + [pd.Timestamp("2026-09-30")] and joined.loc["2026-03-31"] == main_ons.loc["2026-03-31"]
              and joined.iloc[-1] == 13.0, joined)

        def refused(url, *a, **k):
            raise ValueError("refused")

        uk_data.uk_get = refused
        warned = io.StringIO()
        with contextlib.redirect_stdout(warned):
            kept = uk_data._with_sooner_quarters("YBHA", main_ons)
        check("ONS sooner: a failure leaves the series as it was, with a warning", kept is main_ons and "sooner release unavailable" in warned.getvalue(), warned.getvalue())
    finally:
        uk_data.uk_get = real_get
    months = pd.date_range("2026-01-01", "2026-11-01", freq="MS")
    monthly = pd.DataFrame({DATE_COLUMN: months, "BOPTEXP": np.arange(1.0, 12.0)})
    quarterly = pd.Series([100.0, 200.0], index=pd.DatetimeIndex(["2026-01-01", "2026-04-01"]))
    real_fred = payments.fred_series
    try:
        payments.fred_series = lambda series_id, **k: monthly
        joined = _quietly(payments._with_monthly_quarters, quarterly, "BOPTEXP")
        check("monthly trade: the whole quarters after the quarterly series' last, in dollars, not the quarter with two months",
              list(joined.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")]
              and joined.iloc[-1] == (7.0 + 8.0 + 9.0) * 1e6 and joined.iloc[0] == 100.0, joined)
    finally:
        payments.fred_series = real_fred
    # Canada's monthly trade (batch 43.3c): goods and services added up, asked from the last quarter's first month.
    (goods_x, services_x), (goods_m, services_m) = STATCAN_CDN_MONTHLY_TRADE_VECTORS
    cdn_months = pd.date_range("2026-04-01", "2026-11-01", freq="MS")
    cdn_monthly = pd.DataFrame({goods_x: np.arange(1.0, 9.0), services_x: np.arange(1.0, 9.0) / 10, goods_m: np.arange(11.0, 19.0),
                                services_m: np.arange(11.0, 19.0) / 10}, index=pd.DatetimeIndex(cdn_months, name=DATE_COLUMN))
    exports_q = pd.Series([100.0, 200.0], index=pd.DatetimeIndex(["2026-01-01", "2026-04-01"]), name="x")
    imports_q = pd.Series([300.0, 400.0], index=pd.DatetimeIndex(["2026-01-01", "2026-04-01"]), name="m")
    real_range = payments.statcan_wds_range_of
    asked_with = []
    try:
        def answered(vectors, start, *a):
            asked_with.append((list(vectors), start))
            return cdn_monthly
        payments.statcan_wds_range_of = answered
        x_joined, m_joined = _quietly(payments._with_cdn_monthly_quarters, exports_q, imports_q)
        check("Canada's monthly trade: asked of the WDS from the last quarter's first month, its four vectors",
              asked_with == [([goods_x, services_x, goods_m, services_m], pd.Timestamp("2026-04-01"))], asked_with)
        check("Canada's monthly trade: goods and services of each whole quarter after the last, in dollars, not the quarter with two months",
              list(x_joined.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")]
              and np.isclose(x_joined.iloc[-1], (4.0 + 5.0 + 6.0) * 1.1e6) and np.isclose(m_joined.iloc[-1], (14.0 + 15.0 + 16.0) * 1.1e6)
              and x_joined.iloc[1] == 200.0 and m_joined.iloc[0] == 300.0, (x_joined, m_joined))

        def refused(*a, **k):
            raise ValueError("refused")

        payments.statcan_wds_range_of = refused
        warned = io.StringIO()
        with contextlib.redirect_stdout(warned):
            kept = payments._with_cdn_monthly_quarters(exports_q, imports_q)
        check("Canada's monthly trade: a failure leaves both series as they were, with a warning naming where they end",
              kept[0] is exports_q and kept[1] is imports_q and "monthly trade unavailable" in warned.getvalue() and "2026-04" in warned.getvalue(),
              warned.getvalue())
    finally:
        payments.statcan_wds_range_of = real_range

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
