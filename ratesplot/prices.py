"""Consumer prices (batch 13): each nation's consumer price index, and its 12-month rise for --inflation.

Terry asked on 2026-10-12 for inflation by country; the plan's batch 13 has
four uses sharing these sources, built in stages: 13.1, the inflation curve
on the yield axis, first (2026-11-03). The sources, measured 2026-11-03, each
the all-items index, not seasonally adjusted, monthly:

* the U.S.: FRED CPIAUCNS, the CPI for all urban consumers, from 1913-01
  (1982-84 = 100), with no value for 2025-10 (``us_data.US_CPI_SERIES_ID``);
* Canada: Statistics Canada's table 18-10-0004, vector v41690973, from
  1914-01 (2002 = 100; ``cdn_data.STATCAN_SERIES_READ``);
* Germany: the Bundesbank's BBDP1 series of the Federal Statistical
  Office's index, from 1991-01 (2020 = 100; ``de_data.DE_CPI_SERIES``);
  West Germany's older index is not read (Terry, 2026-11-03: a follow-up);
* the UK: the ONS's own 12-month rate, D7G7, from 1989-01, and before it the
  rise of the Bank of England's spliced monthly index in its millennium
  dataset, from 1914-07 (the ONS's CPI estimates from 1949, the cost-of-living
  index before; Terry chose it over the ONS's estimates alone, 2026-11-03).

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
from .config import DATE_COLUMN, STATCAN_CDN_CPI_TABLE, STATCAN_CDN_CPI_VECTOR
from .de_data import fetch_de_consumer_prices
from .uk_archive_data import EMBEDDED_UK_CPI_HISTORY
from .uk_data import UK_INFLATION_SERIES, ons_series
from .us_data import US_CPI_SERIES_ID, fred_series


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


def us_consumer_prices() -> pd.Series:
    """The U.S. CPI for all urban consumers (1982-84 = 100), monthly from 1913-01: FRED's baked history and recent part."""
    frame = fred_series(US_CPI_SERIES_ID, revised=False)
    return frame.set_index(DATE_COLUMN)[US_CPI_SERIES_ID]


def cdn_consumer_prices() -> pd.Series:
    """Canada's consumer price index (2002 = 100), monthly from 1914-01: Statistics Canada's baked history and recent part."""
    return statcan_table(STATCAN_CDN_CPI_TABLE)[STATCAN_CDN_CPI_VECTOR].rename(STATCAN_CDN_CPI_VECTOR)


def uk_inflation() -> pd.Series:
    """The UK's 12-month rise in consumer prices, in percent: the millennium index's rise from 1915-07, the ONS's own rate from its first month (1989-01).

    The ONS's rate is its baked history and its whole answer (``uk_data.ons_series``).
    """
    rows = EMBEDDED_UK_CPI_HISTORY
    history = twelve_month_rise(pd.Series([value for _date, value in rows], index=pd.DatetimeIndex([date for date, _value in rows])))
    live = _by_month(ons_series(UK_INFLATION_SERIES))
    return pd.concat([history.loc[history.index < live.index[0]], live]).rename(UK_INFLATION_SERIES)


def inflation(country: str) -> pd.Series:
    """Return one country's 12-month rise in consumer prices ("cdn", "us", "uk" or "de"), in percent, each month dated by its first day; raises if its source has nothing."""
    if country == "uk":
        return uk_inflation()
    index = {"us": us_consumer_prices, "cdn": cdn_consumer_prices, "de": fetch_de_consumer_prices}[country]()
    return twelve_month_rise(index)
