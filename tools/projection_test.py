"""Batch 43.2: the formulas a smooth series may be carried on by, tested against each nation's own history.

Stands at each figure of a series from ``--since`` (default 2000-01) to the
last that leaves one to compare, cuts the series there, projects the next
three figures (months or quarters) with each formula of
``latest.PROJECTION_FORMULAS``, the seasonal swing over a few counts of years
and the damped trend at a few factors, and compares each projection with the
figure published. Reports, for each series and each formula, the
root-mean-square error in percent of the figure one, two and three figures
ahead (for a price index, about points of its twelve-month rise), and the
figures tested; the lowest at each horizon is starred. A summary at the end
gives each series' straight-line errors and the half year's against them.

The series (``--series``, any of them, comma-separated; default all):

* ``prices``: each nation's consumer price index, not seasonally adjusted
  (the one the inflation curve and --constant read), and seasonally adjusted
  where one is published (--cpi:sa); monthly.
* ``population``: each nation's population (-p, --population); quarterly.
* ``macro``: each nation's aggregate debt, GDP and interest, and the balance
  of payments' credits and debits (TTM sums); quarterly, the UK's debt and
  Germany's balance monthly. The U.S. debt is FRED's quarterly federal plus
  state and local debt (the chart's daily figures past it are not tested).
* ``levels``: debt and interest by level of government (--debt:fnpm,
  --interest:fnpm), where a nation publishes them recently.

The figures are those published now. The unadjusted price indexes are not
revised after their month; most other series are, so their test reads
revised figures and flatters every formula alike.

The projection to today reaches one or two figures past the last (the month
after the End's for a monthly index; a quarterly series' last quarter is one
or two behind): the one- and two-figure errors decide. The reports of
2026-11-17 decided ``latest._formula_for`` and ``latest._pace_span``.

Run from the repository's root:
    python tools/projection_test.py [--series LIST] [--since 2000-01] [--cache DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ratesplot import cli, http, latest  # noqa: E402
from ratesplot import plotting as P  # noqa: E402
from ratesplot import us_data  # noqa: E402
from ratesplot.cdn_data import fetch_cdn_components, fetch_cdn_population  # noqa: E402
from ratesplot.config import BILLION, DATE_COLUMN, MILLION, SEASONALLY_ADJUSTED_NATIONS  # noqa: E402
from ratesplot.de_data import fetch_de_components, fetch_de_population  # noqa: E402
from ratesplot.prices import consumer_prices  # noqa: E402
from ratesplot.uk_data import fetch_uk_components, fetch_uk_population  # noqa: E402

HORIZONS = (1, 2, 3)
DAMPING = (0.5, 0.8, 0.9, 0.95)
SEASONAL_YEARS = (1, 2, 3, 5, 8, 10)
NATIONS = ("cdn", "us", "uk", "de")
GROUPS = ("prices", "population", "macro", "levels")
# A series whose last figure is older than this is history, not projected (``latest._PROJECTION_MAX_AGE_DAYS``).
RECENT = pd.Timestamp("2024-01-01")
PERIOD_WORDS = {"M": "month", "Q": "quarter", None: "figure"}


def formulas() -> dict[str, latest.Formula]:
    """Every formula tried, by name: the program's list, the seasonal swing over each count of years and the damped trend at each factor."""
    tried = dict(latest.PROJECTION_FORMULAS)
    tried.update({f"seasonal{years}": latest.seasonal(years) for years in SEASONAL_YEARS})
    tried.update({f"damped{phi:g}": latest.damped(phi) for phi in DAMPING})
    return tried


def _figures(series: pd.Series) -> pd.Series:
    """A series' figures, sorted, one to a date."""
    series = series.dropna().sort_index()
    return series[~series.index.duplicated(keep="last")]


def errors(series: pd.Series, formula: latest.Formula, since: pd.Timestamp) -> dict[int, np.ndarray]:
    """For each horizon, the errors (100 x the logarithm of projected over published) of ``formula`` standing at each figure from ``since``.

    The figure ``h`` ahead is the one in the period (month or quarter, as
    the series is figured where it stands) ``h`` after the one stood at; a
    period with no figure (the U.S. index's 2025-10) is not compared.
    """
    series = _figures(series)
    found: dict[int, list[float]] = {h: [] for h in HORIZONS}
    dates = pd.DatetimeIndex(series.index)
    for position, origin in enumerate(dates):
        if origin < since or origin >= dates[-1]:
            continue
        known = series.iloc[: position + 1]
        period = latest._figure_period(known)
        if period is None:
            continue
        later = dates[position + 1 : position + 1 + 4 * max(HORIZONS)]
        by_period = dict(zip(later.to_period(period), later))
        targets = [(h, by_period[origin.to_period(period) + h]) for h in HORIZONS if origin.to_period(period) + h in by_period]
        if not targets:
            continue
        projected = formula(known, pd.DatetimeIndex([date for _h, date in targets]))
        if projected is None:
            continue
        for (h, date), value in zip(targets, projected):
            found[h].append(100 * np.log(value / series.loc[date]))
    return {h: np.array(values) for h, values in found.items()}


def report(name: str, series: pd.Series, since: pd.Timestamp, lines: list[str], summary: list[str]) -> None:
    """The table for one series: each formula's root-mean-square error at each horizon, the lowest starred; and its line in the summary."""
    series = _figures(series)
    table = {}
    for formula_name, formula in formulas().items():
        found = errors(series, formula, since)
        table[formula_name] = {h: (float(np.sqrt(np.mean(found[h] ** 2))) if len(found[h]) else math.nan, len(found[h])) for h in HORIZONS}
    best = {h: min(table, key=lambda f: table[f][h][0] if not math.isnan(table[f][h][0]) else math.inf) for h in HORIZONS}
    word = PERIOD_WORDS[latest._figure_period(series)]
    lines.append(f"{name}  (figures {series.index[0]:%Y-%m-%d} to {series.index[-1]:%Y-%m-%d}; tested from {since:%Y-%m})")
    lines.append(f"  {'formula':<12}" + "".join(f"{f'{h} {word}' + ('s' if h > 1 else ''):>12}" for h in HORIZONS) + f"{'tests':>8}")
    for formula_name, row in table.items():
        cells = "".join(f"{row[h][0]:>11.3f}{'*' if best[h] == formula_name else ' '}" for h in HORIZONS)
        lines.append(f"  {formula_name:<12}{cells}{row[1][1]:>8}")
    lines.append("")
    straight, half = table["straight"], table["half_year"]
    ratios = "/".join(f"{half[h][0] / straight[h][0]:.2f}" if straight[h][0] else "nan" for h in (1, 2))
    summary.append(f"  {name[:52]:<52}{straight[1][0]:>8.3f}{straight[2][0]:>8.3f}{ratios:>12}  {best[1]}, {best[2]}")
    print("\n".join(lines[-len(table) - 3 :]), flush=True)


def _columns(frame: pd.DataFrame | None, prefix: str = "") -> Iterator[tuple[str, pd.Series]]:
    """Each column of a fetched frame with recent figures, named."""
    if frame is None:
        return
    frame = frame.set_index(DATE_COLUMN) if DATE_COLUMN in frame.columns else frame
    for column in frame.columns:
        figures = _figures(frame[column])
        if len(figures) > 40 and figures.index[-1] >= RECENT:
            yield prefix + column, figures


def series_of(group: str) -> Iterator[tuple[str, pd.Series]]:
    """The series of one group (``GROUPS``), named "nation: series"."""
    if group == "prices":
        for nation in NATIONS:
            yield f"{nation}: consumer price index, not seasonally adjusted", consumer_prices(nation)
            if nation in SEASONALLY_ADJUSTED_NATIONS:
                yield f"{nation}: consumer price index, seasonally adjusted", consumer_prices(nation, adjusted=True)
    elif group == "population":
        for nation, fetch in (("cdn", fetch_cdn_population), ("us", us_data.fetch_us_population), ("uk", fetch_uk_population), ("de", fetch_de_population)):
            yield f"{nation}: population", fetch()
    elif group == "macro":
        config = P.resolve_start(cli.parse_args(["--no-gui", "-s:1950-01-01", "--debt", "--GDP", "--interest", "--payments"]))
        fetchers = {
            "cdn": (P.fetch_cdn_debt, P.fetch_cdn_gdp, P.fetch_cdn_interest),
            "uk": (P.fetch_uk_debt, P.fetch_uk_gdp, P.fetch_uk_interest),
            "de": (P.fetch_de_debt, P.fetch_de_gdp, P.fetch_de_interest),
        }
        for nation in NATIONS:
            if nation == "us":
                yield from _us_macro()
            else:
                for fetch in fetchers[nation]:
                    yield from _columns(fetch(config), f"{nation}: ")
            yield from _columns(P._payments(nation, config), f"{nation}: ")
    elif group == "levels":
        config = P.resolve_start(cli.parse_args(["--no-gui", "-s:1950-01-01", "--debt:fnpm", "--interest:fnpm"]))
        for nation, fetch in (("cdn", fetch_cdn_components), ("uk", fetch_uk_components), ("de", fetch_de_components)):
            yield from _columns(fetch(config), f"{nation}: ")
        for frame in us_data._fetch_us_interest_levels("fnpm", config):
            yield from _columns(frame, "us: ")


def _us_macro() -> Iterator[tuple[str, pd.Series]]:
    """The U.S. macro series from their FRED sources as ``us_data.fetch_us_macro`` reads them, before they are carried onto its rows."""
    federal = us_data._fetch_fred_quarterly(us_data.US_DEBT_SERIES_ID, "Fed_Debt", MILLION).set_index(DATE_COLUMN)["Fed_Debt"]
    state_local = us_data._fetch_fred_quarterly(us_data.US_STATE_LOCAL_DEBT_SERIES_ID, "State_Local_Debt", MILLION).set_index(DATE_COLUMN)["State_Local_Debt"]
    gdp = us_data._fetch_fred_quarterly(us_data.US_GDP_SERIES_ID, "GDP_SAAR", BILLION).set_index(DATE_COLUMN)["GDP_SAAR"]
    interest = us_data._ttm_interest(us_data._fetch_billions(us_data.US_INTEREST_SERIES_ID), "TTM").set_index(DATE_COLUMN)["TTM"]
    yield "us: aggregate debt (FRED's quarters)", federal + state_local
    yield "us: TTM nominal GDP", gdp.rolling(4, min_periods=4).mean()
    yield "us: TTM interest", interest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--series", default=",".join(GROUPS), help=f"the groups tested, comma-separated, of {', '.join(GROUPS)}")
    parser.add_argument("--since", default="2000-01", help="the first month stood at (YYYY-MM)")
    parser.add_argument("--cache", type=Path, help="a download cache folder of regress_charts.py's kind (default: download)")
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    args = parser.parse_args()
    groups = [group.strip() for group in args.series.split(",") if group.strip()]
    unknown = sorted(set(groups) - set(GROUPS))
    if unknown:
        parser.error(f"unknown series {', '.join(unknown)}; choose from {', '.join(GROUPS)}")
    if args.cache:
        from regress_charts import install_disk_cache

        install_disk_cache(http, args.cache.resolve())
    since = pd.Timestamp(args.since + "-01")
    lines = [
        "Batch 43.2: projection formulas against history, root-mean-square error in percent of the figure",
        "(100 x log of projected over published; for a price index about points of its twelve-month rise).",
        "",
    ]
    summary = [
        "Summary: the straight line's error one and two figures ahead, the half year's over it, the best at each",
        f"  {'series':<52}{'1 ahead':>8}{'2 ahead':>8}{'half/str.':>12}  best",
    ]
    for group in groups:
        for name, series in series_of(group):
            report(name, series, since, lines, summary)
    text = "\n".join(lines + summary)
    print("\n".join(summary))
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
