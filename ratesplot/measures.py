"""How the right-axis (macro) curves are measured: in dollars, as a percentage of GDP (-r), or per person (-p); at constant prices (--constant); and in which currency (--master).

The data layers always produce dollar amounts, with each series forward-filled
onto the chart's dates. ``express`` converts that prepared frame (a ``DATE``
column plus one column per series) into the measure the configuration asks
for, just before drawing. The fetchers, the archive joins and the TTM
conventions therefore never depend on the measure, and the column names stay
the same, so drawing code finds the curves where it always does.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from .config import COMPONENT_LETTERS, DATE_COLUMN, CountryMetadata, PlotConfig, component_column, nation_by_key


# The month whose consumer prices a chart's amounts are in (--constant),
# recorded on the frame ``express`` returns; None where they are in current
# prices (no index on or before the End). ``plotting.draw_country`` reads it.
PRICE_BASE_ATTR = "price_base"


def express(
    macro: pd.DataFrame,
    config: PlotConfig,
    metadata: CountryMetadata,
    population: pd.Series | None = None,
    prices: pd.Series | None = None,
    own_populations: Mapping[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Return ``macro`` in the measure ``config`` asks for (unchanged for plain dollars), in the master currency if its chart is converted.

    ``population`` (date-indexed, persons) and ``own_populations`` are needed only for -p, ``prices``
    (the nation's consumer price index by month, ``prices.consumer_prices``)
    only for --constant. Per person, then at constant prices (the order is
    immaterial: each divides each amount on its date), then in the master
    currency: the conversion comes after the measure (plan 30.1), so per
    capita it divides amounts already in the master currency by people, and
    at constant prices the nation's own prices are taken out before its
    amounts are converted at the End's rate (plan 13.2's note).
    """
    if config.relative:
        return as_percent_of_gdp(macro, metadata)
    measured = per_person(macro, metadata, population, own_populations) if config.per_capita else macro
    if config.constant_prices:
        measured = in_constant_prices(measured, metadata, prices, config.end)
    return in_master_currency(measured, config, metadata)


def in_constant_prices(
    macro: pd.DataFrame, metadata: CountryMetadata, prices: pd.Series | None, end: pd.Timestamp
) -> pd.DataFrame:
    """Return ``macro``'s amounts at the consumer prices of one month (--constant, batch 13.2), that month in ``attrs[PRICE_BASE_ATTR]``.

    The month is the last the index has on or before the chart's End (the
    latest published, on a chart ending today). Each amount is divided by
    the index of the month its date falls in, the latest month published
    if its own is not (a debt clock's days after it), taken when the amount
    is observed and held until the next (``ratio_at_observations``, as per
    capita), then multiplied by the index of that one month: so the curves
    end where they do in current prices, and only their history moves,
    raised by the rise in prices since. A flow over twelve months (TTM GDP,
    interest) is divided by the index of its last month, as a stock is,
    which keeps debt's distance from GDP on the log axis what it is in
    current prices (the alternative, the twelve months' average index,
    would raise the flows by about half a year's inflation). Before the
    index begins there is no price to divide by, and nothing is drawn
    there. With no index on or before the End, ``macro`` as it is, in
    current prices, with a warning, and None in the attribute.
    """
    columns = _debt_and_interest_columns(macro, metadata)
    if metadata.gdp_column in macro.columns:
        columns.append(metadata.gdp_column)
    known = pd.Series(dtype=float) if prices is None else prices.dropna().sort_index()
    known = known.loc[known.index <= end]
    if known.empty:
        nation = nation_by_key(metadata.key)
        print(
            f"  Warning: no {nation.adjective} consumer price index on or before {end:%Y-%m-%d}; "
            "the amounts are drawn in current prices."
        )
        result = macro.copy()
        result.attrs[PRICE_BASE_ATTR] = None
        return result
    base_month, base_index = known.index[-1], float(known.iloc[-1])
    result = macro.copy()
    result.attrs[PRICE_BASE_ATTR] = base_month
    if macro.empty or not columns:
        return result
    index = index_on(result[DATE_COLUMN], known)
    for column in columns:
        result[column] = ratio_at_observations(result[column], index) * base_index
    return result


def index_on(dates: pd.Series, index: pd.Series) -> pd.Series:
    """Return a monthly price index (dated by each month's first day) on each of ``dates``: its month's value, or the latest before it; missing before its first month."""
    return held_on(dates, index.dropna())


def held_on(dates: pd.Series, values: pd.Series) -> pd.Series:
    """Return ``values`` on each of ``dates``: the latest on or before it, which may itself be missing; missing before the first."""
    when = pd.DatetimeIndex(pd.to_datetime(dates))
    known = values.sort_index()
    at = known.index.searchsorted(when, side="right") - 1
    held = np.where(at >= 0, known.to_numpy(dtype=float)[np.clip(at, 0, None)], np.nan)
    return pd.Series(held, index=dates.index)


def in_master_currency(macro: pd.DataFrame, config: PlotConfig, metadata: CountryMetadata) -> pd.DataFrame:
    """Return ``macro``'s amounts in the master currency at its chart's rate (--master, batch 30), or ``macro`` as it is.

    ``config.master_conversion`` is set on a chart converted
    (``plotting.chart_config``), never under -r. One rate for the whole
    chart, as Terry asked ("converted at the rate applicable for the
    “End” date"), multiplies every amount by the same number: on the log
    axis each curve moves by the same distance, so its shape and its --reg
    slopes stay as they were, and the curves of several nations read in one
    unit while each keeps its own growth.
    """
    master = config.master_conversion
    columns = _debt_and_interest_columns(macro, metadata)
    if metadata.gdp_column in macro.columns:
        columns.append(metadata.gdp_column)
    if master is None or config.relative or macro.empty or not columns:
        return macro
    result = macro.copy()
    result[columns] = result[columns] * master.rate
    return result


def _debt_and_interest_columns(macro: pd.DataFrame, metadata: CountryMetadata) -> list[str]:
    """The debt and interest columns present in ``macro``: the aggregates, federal debt alone, net debt, and each level."""
    candidates = [metadata.debt_column, metadata.federal_debt_column, metadata.net_debt_column, metadata.interest_column] + [
        component_column(kind, letter) for kind in ("debt", "interest") for letter in COMPONENT_LETTERS
    ]
    return [column for column in candidates if column is not None and column in macro.columns]


def as_percent_of_gdp(macro: pd.DataFrame, metadata: CountryMetadata) -> pd.DataFrame:
    """Divide debt and interest by TTM GDP, in percent (see ``ratio_at_observations``).

    Where GDP is missing (in Canada, before 1926, so the federal-only debt
    from 1867 shows only from 1926) the ratio is missing too. The GDP column
    itself is left as it was; it is not drawn.
    """
    columns = _debt_and_interest_columns(macro, metadata)
    if macro.empty or not columns:
        return macro
    result = macro.copy()
    if metadata.gdp_column not in result.columns or not result[metadata.gdp_column].notna().any():
        print("  Warning: GDP is unavailable, so debt and interest cannot be shown as a percentage of it.")
        for column in columns:
            result[column] = np.nan
        return result

    gdp = result[metadata.gdp_column]
    for column in columns:
        result[column] = ratio_at_observations(result[column], gdp.where(gdp > 0)) * 100.0
    return result


def ratio_at_observations(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return ``numerator / denominator``, taken when the numerator is observed and held until its next observation.

    Both series are already carried forward onto the chart's dates, so an
    observation shows as a change of value. Dividing on every date instead
    would mix dates: Canadian debt before 1990 is a year-end figure (every
    few years in 1933-1943), while TTM GDP changes each quarter, so a year's
    debt would sit over each newer GDP in turn, the ratio falling through
    the year and jumping at its end: a sawtooth that is not in the data.
    Taken at the observation, a year-end debt is divided by the TTM GDP to
    that year end. The ratio ends where the numerator does (federal debt
    alone stops when the aggregate begins).
    """
    observed = numerator.notna() & numerator.ne(numerator.shift())
    return (numerator / denominator).where(observed).ffill().where(numerator.notna())


def per_person(
    macro: pd.DataFrame, metadata: CountryMetadata, population: pd.Series | None, own_populations: Mapping[str, pd.Series] | None = None
) -> pd.DataFrame:
    """Divide GDP, debt and interest by the population, in dollars per person.

    Each ratio is taken when its series is observed (``ratio_at_observations``),
    with the population interpolated to that date (``population_on``), so the
    curves keep their steps rather than drifting between observations as the
    population grows. A column in ``own_populations`` covers another territory than the
    population drawn for a while (West Germany's GDP and debt, batch 16): its population,
    in persons, is each held until the next date, a date with none meaning the population
    drawn from there. It is the latest on or before each date, not interpolated: each is
    the population of a figure of that column, whichever chart date the figure first shows on.
    """
    columns = _debt_and_interest_columns(macro, metadata)
    if metadata.gdp_column in macro.columns:
        columns.append(metadata.gdp_column)
    if macro.empty or not columns:
        return macro
    result = macro.copy()
    if population is None or not population.notna().any():
        print("  Warning: population is unavailable, so the curves cannot be shown per person.")
        for column in columns:
            result[column] = np.nan
        return result

    people = population_on(result[DATE_COLUMN], population)
    for column in columns:
        divisor = people
        if own_populations is not None and column in own_populations:
            divisor = held_on(result[DATE_COLUMN], own_populations[column]).combine_first(people)
        result[column] = ratio_at_observations(result[column], divisor.where(divisor > 0))
    return result


def population_on(dates: pd.Series, population: pd.Series) -> pd.Series:
    """Return the population on each of ``dates`` (indexed like ``dates``).

    Log-linear between estimates (population grows roughly geometrically,
    and before 1946 the Canadian estimates are a year apart); the last
    estimate is held after it; missing before the first.
    """
    known = population.dropna().sort_index()
    when = pd.DatetimeIndex(pd.to_datetime(dates)).asi8
    known_when = pd.DatetimeIndex(known.index).asi8
    # np.interp holds the end values beyond the known range; before the first
    # estimate there is no population, so those dates are blanked.
    values = np.exp(np.interp(when, known_when, np.log(known.to_numpy(dtype=float))))
    values[when < known_when[0]] = np.nan
    return pd.Series(values, index=dates.index)
