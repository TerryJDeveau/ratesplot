"""Consumer prices (batch 13): each nation's consumer price index, its 12-month rise for --inflation, and the index itself for --constant.

Terry asked on 2026-10-12 for inflation by country; the plan's batch 13 has
four uses sharing these sources, built in stages: 13.1, the inflation curve
on the yield axis, first (2026-11-03); 13.2, the amounts at constant prices,
second (``consumer_prices``); 13.4, the index itself on the right axis,
unadjusted or seasonally adjusted. The sources, measured 2026-11-03, each the
all-items index, not seasonally adjusted, monthly:

* the U.S.: FRED CPIAUCNS, the CPI for all urban consumers, from 1913-01
  (1982-84 = 100), with no value for 2025-10 (``us_data.US_CPI_SERIES_ID``);
* Canada: Statistics Canada's table 18-10-0004, vector v41690973, from
  1914-01 (2002 = 100; ``cdn_data.STATCAN_SERIES_READ``);
* Germany: the Bundesbank's BBDP1 series of the Federal Statistical
  Office's index, from 1991-01 (2020 = 100; ``de_data.DE_CPI_SERIES``), and
  before it West Germany's, from 1948-06, scaled to it
  (``de_data.with_west_germany``, batch 16);
* the UK: the ONS's own 12-month rate, D7G7, from 1989-01, and before it the
  rise of the Bank of England's spliced monthly index in its millennium
  dataset, from 1914-07 (the ONS's CPI estimates from 1949, the cost-of-living
  index before; Terry chose it over the ONS's estimates alone, 2026-11-03);
  for the index itself (13.2), the ONS's D7BT from 1988-01 (2015 = 100, to
  a tenth) and the Bank's index before it, also 2015 = 100, laid end to end
  (they differ by 0.04 % at 1988-01, by at most 0.17 points in the 351
  months both have).

The seasonally adjusted indexes (13.4), on the same bases: FRED CPIAUCSL from
1947-01, Statistics Canada's 18-10-0006 (v41690914) from 1992-01 and the
Bundesbank's calendar and seasonally adjusted index from 1991-01; the ONS
publishes none. Each is revised as its seasonal factors are, so each is read
as a revised series.

A rise is each month's index over the same month's a year before, less one,
in percent, found by date: a month without an index (the U.S.' 2025-10) has
no rise, and neither has the month a year after it. The statistics offices
of the U.S. and Canada compute their published rates from the published
index, so these are theirs before rounding; the ONS computes from the
unrounded index, so the UK's rate is the ONS's own from 1989. Each source's
history is baked and kept current by the daily job, as every live source is
(batch 19.2).
"""

from __future__ import annotations

import pandas as pd

from .cdn_data import statcan_table
from .config import (
    DATE_COLUMN,
    SEASONALLY_ADJUSTED_NATIONS,
    STATCAN_CDN_CPI_SA_TABLE,
    STATCAN_CDN_CPI_SA_VECTOR,
    STATCAN_CDN_CPI_TABLE,
    STATCAN_CDN_CPI_VECTOR,
)
from .de_data import fetch_de_consumer_prices
from .uk_archive_data import EMBEDDED_UK_CPI_HISTORY
from .uk_data import UK_CPI_SERIES, UK_INFLATION_SERIES, ons_series
from .us_data import US_CPI_SA_SERIES_ID, US_CPI_SERIES_ID, fred_series


def _by_month(values: pd.Series) -> pd.Series:
    """Return a monthly series dated by each month's first day, numeric, sorted, without missing values; raises on a month given twice."""
    values = pd.to_numeric(values, errors="coerce").dropna()
    months = pd.DatetimeIndex(values.index).to_period("M").to_timestamp()
    if months.duplicated().any():
        raise ValueError(f"{values.name}: a month appears twice")
    return pd.Series(values.to_numpy(dtype=float), index=months.rename(DATE_COLUMN), name=values.name).sort_index()


def twelve_month_rise(index: pd.Series) -> pd.Series:
    """Return a monthly price index's rise over 12 months, in percent, each month dated by its first day.

    Found by date, not by position: a month whose index or whose index a
    year before is missing has no rise.
    """
    monthly = _by_month(index)
    year_before = monthly.reindex(monthly.index - pd.DateOffset(years=1)).to_numpy()
    rise = pd.Series((monthly.to_numpy() / year_before - 1.0) * 100.0, index=monthly.index, name=monthly.name)
    return rise.dropna()


def us_consumer_prices(*, adjusted: bool = False) -> pd.Series:
    """The U.S. CPI for all urban consumers (1982-84 = 100), monthly from 1913-01, or seasonally adjusted from 1947-01: FRED's baked history and recent part."""
    series_id = US_CPI_SA_SERIES_ID if adjusted else US_CPI_SERIES_ID
    frame = fred_series(series_id, revised=adjusted)
    return frame.set_index(DATE_COLUMN)[series_id]


def cdn_consumer_prices(*, adjusted: bool = False) -> pd.Series:
    """Canada's consumer price index (2002 = 100), monthly from 1914-01, or seasonally adjusted from 1992-01: Statistics Canada's baked history and recent part."""
    table, vector = (STATCAN_CDN_CPI_SA_TABLE, STATCAN_CDN_CPI_SA_VECTOR) if adjusted else (STATCAN_CDN_CPI_TABLE, STATCAN_CDN_CPI_VECTOR)
    return statcan_table(table)[vector].rename(vector)


def uk_consumer_prices() -> pd.Series:
    """The UK's consumer price index (2015 = 100), monthly from 1914-07: the millennium index, then the ONS's D7BT from its first month (1988-01).

    D7BT is its baked history and its whole answer (``uk_data.ons_series``).
    Both are 2015 = 100, so they are laid end to end, not scaled.
    """
    history = _millennium_index()
    live = _by_month(ons_series(UK_CPI_SERIES))
    return pd.concat([history.loc[history.index < live.index[0]], live]).rename(UK_CPI_SERIES)


def _millennium_index() -> pd.Series:
    """The Bank of England's spliced monthly CPI in its millennium dataset (2015 = 100), 1914-07 to 2017-03, each month dated by its first day."""
    rows = EMBEDDED_UK_CPI_HISTORY
    return _by_month(pd.Series([value for _date, value in rows], index=pd.DatetimeIndex([date for date, _value in rows])))


def consumer_prices(country: str, *, adjusted: bool = False) -> pd.Series:
    """Return one country's consumer price index ("cdn", "us", "uk" or "de"), each month dated by its first day; raises if its source has nothing.

    Each in its own base year: --constant divides by it and multiplies by
    its value in one month (``measures.in_constant_prices``), so the base
    year cancels. ``adjusted``: the seasonally adjusted index (13.4), for a
    nation of ``SEASONALLY_ADJUSTED_NATIONS`` only (a ValueError for the UK).
    """
    if not adjusted:
        reader = {"us": us_consumer_prices, "cdn": cdn_consumer_prices, "uk": uk_consumer_prices, "de": fetch_de_consumer_prices}
        return _by_month(reader[country]())
    if country not in SEASONALLY_ADJUSTED_NATIONS:
        raise ValueError(f"{country}: no seasonally adjusted consumer price index is published")
    reader = {"us": us_consumer_prices, "cdn": cdn_consumer_prices, "de": fetch_de_consumer_prices}
    return _by_month(reader[country](adjusted=True))


def uk_inflation() -> pd.Series:
    """The UK's 12-month rise in consumer prices, in percent: the millennium index's rise from 1915-07, the ONS's own rate from its first month (1989-01).

    The ONS's rate is its baked history and its whole answer (``uk_data.ons_series``).
    """
    history = twelve_month_rise(_millennium_index())
    live = _by_month(ons_series(UK_INFLATION_SERIES))
    return pd.concat([history.loc[history.index < live.index[0]], live]).rename(UK_INFLATION_SERIES)


def inflation(country: str) -> pd.Series:
    """Return one country's 12-month rise in consumer prices ("cdn", "us", "uk" or "de"), in percent, each month dated by its first day; raises if its source has nothing."""
    if country == "uk":
        return uk_inflation()
    index = {"us": us_consumer_prices, "cdn": cdn_consumer_prices, "de": fetch_de_consumer_prices}[country]()
    return twelve_month_rise(index)
