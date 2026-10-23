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
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import DATE_COLUMN
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


@dataclass(frozen=True)
class Rate:
    """Units of one currency per unit of another, and where it comes from.

    ``dated`` is the date of the oldest observation it is made from (a
    cross rate takes two), ``source`` names the series.
    """

    value: float
    dated: pd.Timestamp
    source: str


def _latest(series_id: str, on: pd.Timestamp, stopped: pd.Timestamp | None = None) -> Rate | None:
    """FRED series ``series_id``'s last value dated on or before ``on``, or None if it has none by then."""
    frame = fred_series(series_id, revised=False, stopped=stopped)
    values = frame.set_index(DATE_COLUMN)[series_id].dropna()
    values = values[values.index <= on]
    if values.empty:
        return None
    return Rate(float(values.iloc[-1]), values.index[-1], f"FRED {series_id}")


def units_per_usd(currency: str, on: pd.Timestamp) -> Rate | None:
    """Return how many units of ``currency`` a U.S. dollar was worth on ``on`` (the latest rate by then), or None if none is known.

    ``currency`` is an ISO 4217 code of ``config.CURRENCY_SYMBOLS``.
    """
    if currency == "USD":
        return Rate(1.0, on, "")
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


def rate(source: str, target: str, on: pd.Timestamp) -> Rate | None:
    """Return the units of currency ``target`` per unit of ``source`` on ``on`` (through the U.S. dollar), or None if either is not known by then."""
    if source == target:
        return Rate(1.0, on, "")
    to_source, to_target = units_per_usd(source, on), units_per_usd(target, on)
    if to_source is None or to_target is None:
        return None
    sources = " and ".join(name for name in (to_source.source, to_target.source) if name)
    return Rate(to_target.value / to_source.value, min(to_source.dated, to_target.dated), sources)
