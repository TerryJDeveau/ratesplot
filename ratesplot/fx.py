"""Exchange rates: an axis limit given in one currency, in another's (batch 18.3).

Terry, 2026-10-20 (decision 41): Top and Bottom may be written with a
currency (``--top:USD20t``), "written once with its currency and converted at
each drawing", at the rate of the chart's end date, the latest on or before
it: a chart with a pinned end draws the same every time, one ending today
follows the rate. ``plotting`` asks for a rate only when a limit is in
another currency than its chart's, so no other drawing asks for one.

Every rate goes through the U.S. dollar, as FRED quotes them
(``units_per_usd``):

* the Canadian dollar, FRED DEXCAUS (Canadian dollars per U.S. dollar,
  daily from 1971-01-04);
* the pound, FRED DEXUSUK (U.S. dollars per pound, daily from 1971-01-04);
* the euro, FRED DEXUSEU (U.S. dollars per euro, daily from 1999-01-04);
  before it the Deutsche mark at its fixed 1.95583 marks per euro, FRED
  EXGEUS (marks per U.S. dollar, monthly averages 1971-01 to 2001-12, the
  month dated by its first day; FRED has no daily series of the mark,
  measured 2026-10-23).

The four are baked with FRED's other series (``us_data.fred_series``,
``tools/bake_archives.py --only fred``): a drawing asks FRED only for their
recent part, and nothing for a chart that ended more than a year ago
(``baked.chart_ending``). Measured 2026-10-23: the daily rates' newest value
was a week old (2026-10-16), FRED publishing the Federal Reserve's H.10 on
Mondays; a chart ending today is converted at that rate.

Before FRED's, the older rates (batch 18.4, ``_OLDER``), baked with the
nations' history, so a chart before 1971 converts too. Each source is used
only before the next begins, and a cross rate is taken through the pound in
the same month:

* the pound: the Bank of England's millennium dataset, sheet M15 (U.S.
  dollars per pound, monthly from 1791-01; within 0.3 % of DEXUSUK averaged
  by month over 1971-2017, median 0.002 %);
* the Canadian dollar: from 1858-01, its first year, at the gold par of
  $4.86 2/3 per pound over M15 (its step to J562's 1913: 1.0034 to
  1.0001); 1913 to 1962
  *Historical Statistics of Canada* J562 (each year's average, dated
  1 January; its 1970 value misses the float of May 1970, so it is not read
  past 1962); 1963-01 to 1970-12 M14 (Canadian dollars per pound) over M15
  (within 0.5 % of J562's yearly means 1963-1969; M14 departs from FRED by
  up to 6.7 % in 1975-76, after it is read);
* the euro: the mark's official parities, 3.3333 marks per U.S. dollar from
  1948-06-21, 4.20 from 1949-09-19, 4.00 from 1961-03-06; 1963-01 to 1970-12
  M14 (marks per pound) over M15; each at 1.95583 marks per euro. No rate
  before 1948-06-21: a limit in euros is then left to the axis with a
  warning (``plotting.limits_in_own_currency``).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

import pandas as pd

from .cdn_archive_data import EMBEDDED_CDN_PER_USD_HISTORY
from .config import DATE_COLUMN
from .uk_archive_data import (
    EMBEDDED_UK_CAD_PER_GBP_HISTORY,
    EMBEDDED_UK_DEM_PER_GBP_HISTORY,
    EMBEDDED_UK_USD_PER_GBP_HISTORY,
)
from .us_data import fred_series

FX_CAD_PER_USD = "DEXCAUS"
FX_USD_PER_GBP = "DEXUSUK"
FX_USD_PER_EUR = "DEXUSEU"
FX_DEM_PER_USD = "EXGEUS"
# EXGEUS's last month (FRED, measured 2026-10-23): the mark gave way to the
# euro, so the series has stopped and is read from its bake alone (19.3).
FX_DEM_ENDED = pd.Timestamp("2001-12-01")
# The rate fixed when the euro replaced the mark (1998-12-31): marks per euro.
DEM_PER_EUR = 1.95583
# Every FRED series read here, for the bake (``bake.fred_baked_codes``).
FX_SERIES = (FX_CAD_PER_USD, FX_USD_PER_GBP, FX_USD_PER_EUR, FX_DEM_PER_USD)

# The Canadian dollar's first month, and its gold par with the pound until
# J562 begins in 1913: $4.86 2/3 per pound.
CAD_BEGAN = pd.Timestamp("1858-01-01")
CAD_PER_GBP_AT_PAR = 73 / 15
# The Deutsche mark's official parities, marks per U.S. dollar, from the day
# each took effect (the currency reform of 1948-06-21, the devaluation of
# 1949-09-19, the revaluation of 1961-03-06), until M14 begins in 1963.
DEM_PER_USD_PARITIES = (
    (pd.Timestamp("1948-06-21"), 10 / 3),
    (pd.Timestamp("1949-09-19"), 4.20),
    (pd.Timestamp("1961-03-06"), 4.00),
)


@dataclass(frozen=True)
class Rate:
    """Units of one currency per unit of another, and where it comes from.

    ``dated`` is the date of the oldest observation it is made from (a
    cross rate takes two), ``source`` names the series.
    """

    value: float
    dated: pd.Timestamp
    source: str


@dataclass(frozen=True)
class _Older:
    """One of the older sources of a currency's units per U.S. dollar (batch 18.4)."""

    values: pd.Series  # units per U.S. dollar, by the date each describes
    source: str


def _listed(rows: list[tuple[str, float]]) -> pd.Series:
    """A baked list as a date-indexed series."""
    return pd.Series([value for _date, value in rows], index=pd.DatetimeIndex([date for date, _value in rows]), dtype=float)


@functools.cache
def _older(currency: str) -> tuple[_Older, ...]:
    """Return ``currency``'s older sources, newest first, each to be read only where the ones before it have no rate yet.

    Built once from the baked lists. A cross rate through the pound divides
    two values of the same month (M14 and M15 have every month they span).
    """
    dollars_per_pound = _listed(EMBEDDED_UK_USD_PER_GBP_HISTORY)
    if currency == "GBP":
        return (_Older(1.0 / dollars_per_pound, "BoE millennium M15"),)
    if currency == "CAD":
        return (
            _Older(_listed(EMBEDDED_UK_CAD_PER_GBP_HISTORY).div(dollars_per_pound).dropna(), "BoE millennium M14 over M15"),
            _Older(_listed(EMBEDDED_CDN_PER_USD_HISTORY), "HSC J562, the year's average"),
            _Older(CAD_PER_GBP_AT_PAR / dollars_per_pound.loc[CAD_BEGAN:], "the gold par, $4.86 2/3 per pound, over BoE millennium M15"),
        )
    if currency == "EUR":
        marks = _listed(EMBEDDED_UK_DEM_PER_GBP_HISTORY).div(dollars_per_pound).dropna()
        parities = pd.Series([value for _day, value in DEM_PER_USD_PARITIES], index=pd.DatetimeIndex([day for day, _value in DEM_PER_USD_PARITIES]))
        return (
            _Older(marks / DEM_PER_EUR, f"BoE millennium M14 over M15 at {DEM_PER_EUR} marks per euro"),
            _Older(parities / DEM_PER_EUR, f"the mark's parity at {DEM_PER_EUR} marks per euro"),
        )
    raise ValueError(f"no exchange rate for {currency!r}")


def _latest_value(values: pd.Series, on: pd.Timestamp, source: str) -> Rate | None:
    """``values``' last value dated on or before ``on``, or None if it has none by then."""
    values = values[values.index <= on]
    if values.empty:
        return None
    return Rate(float(values.iloc[-1]), values.index[-1], source)


def _latest(series_id: str, on: pd.Timestamp, stopped: pd.Timestamp | None = None) -> Rate | None:
    """FRED series ``series_id``'s last value dated on or before ``on``, or None if it has none by then."""
    frame = fred_series(series_id, revised=False, stopped=stopped)
    return _latest_value(frame.set_index(DATE_COLUMN)[series_id].dropna(), on, f"FRED {series_id}")


def _from_fred(currency: str, on: pd.Timestamp) -> Rate | None:
    """``currency``'s units per U.S. dollar on ``on`` from FRED's rates, or None before they begin."""
    if currency == "CAD":
        return _latest(FX_CAD_PER_USD, on)
    if currency == "GBP":
        per_pound = _latest(FX_USD_PER_GBP, on)
        return None if per_pound is None else Rate(1.0 / per_pound.value, per_pound.dated, per_pound.source)
    if currency == "EUR":
        per_euro = _latest(FX_USD_PER_EUR, on)
        if per_euro is not None:
            return Rate(1.0 / per_euro.value, per_euro.dated, per_euro.source)
        marks = _latest(FX_DEM_PER_USD, on, stopped=FX_DEM_ENDED)
        if marks is None:
            return None
        return Rate(marks.value / DEM_PER_EUR, marks.dated, f"{marks.source} at {DEM_PER_EUR} marks per euro")
    raise ValueError(f"no exchange rate for {currency!r}")


def units_per_usd(currency: str, on: pd.Timestamp) -> Rate | None:
    """Return how many units of ``currency`` a U.S. dollar was worth on ``on`` (the latest rate by then), or None if none is known.

    ``currency`` is an ISO 4217 code of ``config.CURRENCY_SYMBOLS``. FRED's
    rates first, then the older ones (``_older``): a source is read only
    where every newer one has no rate yet, so each is used only before the
    next begins.
    """
    if currency == "USD":
        return Rate(1.0, on, "")
    found = _from_fred(currency, on)
    if found is not None:
        return found
    for older in _older(currency):
        found = _latest_value(older.values, on, older.source)
        if found is not None:
            return found
    return None


def rate(source: str, target: str, on: pd.Timestamp) -> Rate | None:
    """Return the units of currency ``target`` per unit of ``source`` on ``on`` (through the U.S. dollar), or None if either is not known by then."""
    if source == target:
        return Rate(1.0, on, "")
    to_source, to_target = units_per_usd(source, on), units_per_usd(target, on)
    if to_source is None or to_target is None:
        return None
    sources = " and ".join(name for name in (to_source.source, to_target.source) if name)
    return Rate(to_target.value / to_source.value, min(to_source.dated, to_target.dated), sources)
