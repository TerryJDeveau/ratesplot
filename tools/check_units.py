#!/usr/bin/env python3
"""Check that the date interpolations give the same answer whatever unit their dates are stored in (9.5).

pandas stores dates parsed from text in microseconds and keeps a unit it is given; ``asi8`` counts in each one's own
unit and a ``Timestamp.value`` in nanoseconds. Until 9.5 ``measures.index_on`` compared the two, so with Daily values
France's constant prices drew nothing and an amount before its nation's price index began was divided by the first
month's index. So, with no network, for dates and series in nanoseconds, microseconds and seconds, an index beginning
before 1970 and after it:

* ``measures.index_on`` filled in (each month's value at its middle, the straight line between two by days): equal to
  the same interpolation worked out here on nanoseconds, and missing before the index's first month;
* ``measures.index_on`` held (Daily values off): its month's value, missing before its first month;
* ``measures.population_on``: log-linear between estimates, missing before the first;
* ``measures.microseconds`` of a date in 1600 (a chart may start there, before nanoseconds reach).

    python tools/check_units.py

Exit status 0 only if every check passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ratesplot import measures  # noqa: E402
from ratesplot.measures import index_on, population_on  # noqa: E402

# Absent before 9.5: the harness still runs on an older tree, to show what it finds there.
microseconds = getattr(measures, "microseconds", None)

results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail != "" else ""))


UNITS = ("ns", "us", "s")
# Every day of 1950 to 2000, and of a stretch before each index's first month.
DATES = pd.Series(pd.date_range("1950-01-01", "2000-12-31", freq="D"))
MONTHS = pd.date_range("1955-01-01", "2000-12-01", freq="MS")
INDEX = pd.Series(np.linspace(10.0, 120.0, len(MONTHS)), index=MONTHS)


def expected_filled(dates: pd.Series, index: pd.Series) -> np.ndarray:
    """The filled-in index on ``dates``, worked out on nanoseconds: each month's value at its middle, missing before its first month."""
    middles = index.index + pd.to_timedelta(index.index.days_in_month // 2, unit="D")
    when = dates.dt.as_unit("ns").astype("int64").to_numpy()
    values = np.interp(when, middles.as_unit("ns").asi8, index.to_numpy())
    values[when < index.index[0].as_unit("ns").value] = np.nan
    return values


def expected_held(dates: pd.Series, index: pd.Series) -> np.ndarray:
    """The index held from each month's first day, missing before its first month."""
    return index.reindex(dates.dt.to_period("M").dt.to_timestamp()).to_numpy()


def same(got: pd.Series, want: np.ndarray) -> tuple[bool, str]:
    got = got.to_numpy(dtype=float)
    nan_same = bool((np.isnan(got) == np.isnan(want)).all())
    both = ~np.isnan(want)
    gap = float(np.abs(got[both] - want[both]).max()) if both.any() else 0.0
    return nan_same and gap < 1e-9, f"{int(np.isnan(got).sum())} missing, {int(np.isnan(want).sum())} expected; largest gap {gap:.2e}"


for first in ("1955-01-01", "1996-01-01"):
    index = INDEX.loc[first:]
    want_filled, want_held = expected_filled(DATES, index), expected_held(DATES, index)
    for date_unit in UNITS:
        for index_unit in UNITS[:2]:
            dates = DATES.dt.as_unit(date_unit)
            known = index.set_axis(index.index.as_unit(index_unit))
            ok, detail = same(index_on(dates, known, filled=True), want_filled)
            check(f"index_on filled, index from {first[:7]}, dates in {date_unit}, index in {index_unit}", ok, detail)
            ok, detail = same(index_on(dates, known, filled=False), want_held)
            check(f"index_on held, index from {first[:7]}, dates in {date_unit}, index in {index_unit}", ok, detail)

# The population: yearly estimates from 1960 and from 1980, log-linear between them.
for first in ("1960-07-01", "1980-07-01"):
    estimates = pd.Series(np.geomspace(40e6, 60e6, 2001 - int(first[:4])), index=pd.date_range(first, "2000-07-01", freq="YS-JUL"))
    when = DATES.dt.as_unit("ns").astype("int64").to_numpy()
    want = np.exp(np.interp(when, estimates.index.as_unit("ns").asi8, np.log(estimates.to_numpy())))
    want[when < estimates.index[0].as_unit("ns").value] = np.nan
    for date_unit in UNITS:
        for estimate_unit in UNITS[:2]:
            got = population_on(DATES.dt.as_unit(date_unit), estimates.set_axis(estimates.index.as_unit(estimate_unit)))
            got_values = got.to_numpy(dtype=float)
            both = ~np.isnan(want)
            ok = bool((np.isnan(got_values) == np.isnan(want)).all()) and float(np.abs(got_values[both] / want[both] - 1).max()) < 1e-12
            check(f"population_on, estimates from {first[:4]}, dates in {date_unit}, estimates in {estimate_unit}", ok,
                  f"{int(np.isnan(got_values).sum())} missing, {int(np.isnan(want).sum())} expected")

early = pd.Series(pd.to_datetime(["1600-01-01", "1970-01-01"]).as_unit("s"))
counted = list(microseconds(early)) if microseconds is not None else "no measures.microseconds"
check("microseconds: 1600 counted, before nanoseconds reach", counted == [-11676096000 * 1_000_000, 0], counted)

failed = results.count(False)
print(f"\n{len(results) - failed} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
