"""Batch 43.2: the formulas a lone series may be carried on by, tested against each nation's own history.

Stands at each month from ``--since`` (default 2000-01) to the last that
leaves a month to compare, cuts the series there, projects the three months
after it with each formula of ``latest.PROJECTION_FORMULAS``, the seasonal
swing over a few counts of years and the damped trend at a few factors, and compares each projection with the figure
published. Reports, for each series and each formula, the root-mean-square
error in percent of the figure one, two and three months ahead (for a price
index, about points of its twelve-month rise), and the months tested; the
lowest at each horizon is starred. A series is the consumer price index of
each nation, not seasonally adjusted (the one the inflation curve and
--constant read), and seasonally adjusted where one is published (--cpi:sa).

The figures are those published now. The unadjusted indexes are not revised
after their month; the adjusted ones are, each year, so their test reads
revised figures and flatters every formula alike.

The projection to today reaches one or two months past the last figure (the
month after the End's): the one- and two-month errors decide.

Run from the repository's root:
    python tools/projection_test.py [--since 2000-01] [--cache DIR] [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ratesplot import http, latest  # noqa: E402
from ratesplot.config import SEASONALLY_ADJUSTED_NATIONS  # noqa: E402
from ratesplot.prices import consumer_prices  # noqa: E402

HORIZONS = (1, 2, 3)
DAMPING = (0.5, 0.8, 0.9, 0.95)
SEASONAL_YEARS = (1, 2, 3, 5, 8, 10)
NATIONS = ("cdn", "us", "uk", "de")


def formulas() -> dict[str, latest.Formula]:
    """Every formula tried, by name: the program's list, the seasonal swing over each count of years and the damped trend at each factor."""
    tried = dict(latest.PROJECTION_FORMULAS)
    tried.update({f"seasonal{years}": latest.seasonal(years) for years in SEASONAL_YEARS})
    tried.update({f"damped{phi:g}": latest.damped(phi) for phi in DAMPING})
    return tried


def errors(series: pd.Series, formula: latest.Formula, since: pd.Timestamp) -> dict[int, np.ndarray]:
    """For each horizon, the errors (100 x the logarithm of projected over published) of ``formula`` standing at each month from ``since``."""
    series = series.dropna().sort_index()
    found: dict[int, list[float]] = {h: [] for h in HORIZONS}
    origins = series.index[(series.index >= since) & (series.index < series.index[-1])]
    for origin in origins:
        known = series.loc[:origin]
        dates = pd.DatetimeIndex([origin + pd.DateOffset(months=h) for h in HORIZONS])
        projected = formula(known, dates)
        if projected is None:
            continue
        for h, date, value in zip(HORIZONS, dates, projected):
            if date in series.index:
                found[h].append(100 * np.log(value / series.loc[date]))
    return {h: np.array(values) for h, values in found.items()}


def report(name: str, series: pd.Series, since: pd.Timestamp, lines: list[str]) -> None:
    """The table for one series: each formula's root-mean-square error at each horizon, the lowest starred."""
    table = {}
    for formula_name, formula in formulas().items():
        found = errors(series, formula, since)
        table[formula_name] = {h: (float(np.sqrt(np.mean(found[h] ** 2))) if len(found[h]) else float("nan"), len(found[h])) for h in HORIZONS}
    best = {h: min(table, key=lambda f: table[f][h][0]) for h in HORIZONS}
    lines.append(f"{name}  (figures {series.index[0]:%Y-%m} to {series.index[-1]:%Y-%m}; tested from {since:%Y-%m})")
    lines.append(f"  {'formula':<12}" + "".join(f"{f'{h} month' + ('s' if h > 1 else ''):>12}" for h in HORIZONS) + f"{'months':>8}")
    for formula_name, row in table.items():
        cells = "".join(f"{row[h][0]:>11.3f}{'*' if best[h] == formula_name else ' '}" for h in HORIZONS)
        lines.append(f"  {formula_name:<12}{cells}{row[1][1]:>8}")
    lines.append("")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--since", default="2000-01", help="the first month stood at (YYYY-MM)")
    parser.add_argument("--cache", type=Path, help="a download cache folder of regress_charts.py's kind (default: download)")
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    args = parser.parse_args()
    if args.cache:
        from regress_charts import install_disk_cache

        install_disk_cache(http, args.cache.resolve())
    since = pd.Timestamp(args.since + "-01")
    lines = [
        "Batch 43.2: projection formulas against history, root-mean-square error in percent of the figure",
        "(100 x log of projected over published; for a price index about points of its twelve-month rise).",
        "",
    ]
    for nation in NATIONS:
        report(f"{nation}: consumer price index, not seasonally adjusted", consumer_prices(nation), since, lines)
        if nation in SEASONALLY_ADJUSTED_NATIONS:
            report(f"{nation}: consumer price index, seasonally adjusted", consumer_prices(nation, adjusted=True), since, lines)
    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
