#!/usr/bin/env python3
"""Check every curve drawn on the yield axis against its sources, point by point.

Terry, 2026-10-12, of the "jitter" in the policy rates: was it a design
choice or a bug, and "we need to take steps to ensure that whatever caused it
... is not also lurking in other parts of the code, causing data
hallucinations that are not so obvious to the naked eye". The jitter was the
market overnight rates as published (measured 2026-10-13); this tool makes
that check permanent.

Each case below is drawn through the program's own drawing
(``plotting.build_figure``), and every point of every line on the yield axis
(each yield term, the policy rate, each mortgage rate) is matched with the
sources that curve is made from, read on their own through the program's
lowest-level readers (FRED, the Bank of Canada's Valet, the Bank of
England's database, the Bundesbank, the ECB, Statistics Canada) and from its
built-in history:

* the source's value on the point's date: OK (a monthly rate the program
  dates by its month's first day is matched within its month);
* the value of the source's last observation before that date, carried:
  allowed for the line's first point (the value in effect at the window's
  start) and within the source's limit after that (a yield over a holiday:
  a few days; an observed rate's last value across its own period, batch
  17.3: up to a week; an announced rate, which holds until it changes and
  is drawn on to the chart's end: no limit);
* anything else is a drawn value no source has: FAIL.

A band (the U.S. target range, batch 9.1) is checked as one curve: its
upper limits, drawn unlabelled after its lower, against the same sources.
A curve joined from several sources is found by the label the window gives
it (``rates.legend_label``).

A spread is checked against the two yields drawn with it, point by point.
Each line is reported with the sources that explain it and the dates each
covers, so every join and stand-in is in the open, and with its carried
points (how many, the longest). The right-axis curves are derived (four-
quarter sums, splices, projections to the chart's end): they are listed with
their dates, not compared.

Usage (from the project root)::

    python tools/check_drawn_values.py               # every case, downloads from out/download_cache
    python tools/check_drawn_values.py --live        # fresh downloads (a few minutes)
    python tools/check_drawn_values.py --only us_1985,ca_2015
    python tools/check_drawn_values.py --list

The drawing and the sources read the same downloads (the regression cache,
or one live download each), so the check is of what the program does to
them, never of a difference between two fetches. Except the Bank of
England's series, the Bank of Canada's, FRED's, the ECB's and the
Bundesbank's (batch 19.2):
the drawing reads their baked history and asks for the recent part only, and
they are checked against each source's whole series, so the check covers
the bake too; a regression cache whose whole downloads are older than the bake then
lacks the bake's newest values, or has values since revised (run it on a
copy without them, fetched again).
Exit code 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from regress_charts import PINNED_END, install_disk_cache  # noqa: E402

from ratesplot import cdn_data, cli, de_data, http, rates, uk_data, us_data  # noqa: E402
from ratesplot.cdn_hist_yields import build_cdn_hist_yields  # noqa: E402
from ratesplot.de_archive_data import EMBEDDED_DE_DISCOUNT_RATE_CHANGES  # noqa: E402
from ratesplot.console import this_thread_output_to  # noqa: E402
from ratesplot.joins import embedded_frame  # noqa: E402
from ratesplot.plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402
from ratesplot.uk_archive_data import EMBEDDED_UK_BANK_RATE_HISTORY, EMBEDDED_UK_MORTGAGE_HISTORY  # noqa: E402

# Two readings of one download are the same floats; anything else is a different value.
TOLERANCE = 1e-9
# A daily yield may be carried over a holiday or a missing print (the
# program's own fills are three rows or fewer); longer is a gap filled.
DAILY_CARRY_DAYS = 7
# A monthly value may be carried to the next when one month is missing.
MONTHLY_CARRY_DAYS = 62
# Canada's 3-month was the treasury-bill auction average, one value every
# second week, its values carried up to six business days (found by this
# tool, 2026-10-13); since batch 9.2 it is the daily market yield from 2001,
# the auctions only in December 2000, so the daily limit holds for both.

# Each case: a name and the command line drawn (the pinned end added).
# Chosen to cross every join the yield axis has: Canada's PDF history to
# Valet (2001), the monthly Bank Rate to the weekly (1980), the Bank Rate to
# the overnight target (1996-02) and the weekly to the daily target (2001),
# CORRA's start (1997-08), the CMHC rate before the posted 5-year; the U.S.
# 20-year's gap (1987-1993), the fed funds monthly average to the target
# (1982-09) and the target to its range (2008-12); the UK's built-in yields,
# Bank Rate and variable mortgage rate to the Bank of England's series;
# Germany's built-in 10-year to the fitted curve (1972), the ECB's fixed rate
# to the minimum bid rate and back (2000-2008), EONIA to €STR (2019-10); and
# recent windows with every term, mortgage, both policy terms and the
# default spreads.
CASES: dict[str, list[str]] = {
    "ca_1960": ["-c", "-s:1960", "--e:1985", "--policy", "--mo:5"],
    "ca_1995": ["-c", "-s:1995", "--e:2005", "--po:target,market", "--mo:5,3,1,prime"],
    "ca_2015": ["-c", "-s:2015", "--po:target,market", "--mo:5,3,1,5v,prime", "--sp"],
    # Batch 9.3: every Canadian term across the start of the five new ones
    # (2001-01-02), and spreads of them.
    "ca_terms": ["-c", "-s:2000-06-01", "--y:1m,3m,6m,1,2,3,5,7,10,30", "--sp:7y-1m,3y-6m"],
    "us_1985": ["-u", "-s:1985", "--e:1995", "--y:3m,6m,1,2,5,7,10,20,30", "--policy", "--mo:30,15"],
    "us_2000": ["-u", "-s:2000", "--e:2008", "--y:1m,3m,6m,1,2,5,7,10,20,30", "--sp:30y-10y,30y-2y"],
    "us_2015": ["-u", "-s:2015", "--y:1m,3m,6m,1,2,5,7,10,20,30", "--po:target,market", "--mo:30,15", "--sp"],
    # Batch 9.1: the U.S. target across its three parts, and the market rate.
    "us_policy": ["-u", "-s:1978", "--no-yield", "--po:target,market"],
    # Batch 9.4: the prime rates plus a margin, each nation's own (the U.S.'
    # from FRED DPRIME, daily from 1955-08; Canada's below its prime).
    "prime_margin": ["-s:2005", "--mo:5v,30,prime", "--us:prime:0.5", "--cdn:prime:-0.25"],
    "uk_1970": ["--na:gb", "-s:1970", "--e:1990", "--policy", "--mo:svr"],
    "uk_2015": ["--na:gb", "-s:2015", "--po:target,market", "--mo:2f,3f,5f,svr", "--sp"],
    # Batch 9.5: the UK tracker, Bank Rate plus its margin, from where it begins (1997-01).
    "uk_tracker": ["--na:gb", "-s:1996-06-01", "--policy", "--mo:svr,tracker", "--uk:tracker:1.25"],
    "de_1965": ["--na:de", "-s:1965", "--e:1980"],
    # Batch 9.6: the Bundesbank's discount rate, then the ECB's rate from 1999.
    "de_policy": ["--na:de", "-s:1985", "--e:2004", "--policy", "--no-yield"],
    "de_1998": ["--na:de", "-s:1998", "--e:2010", "--po:target,market", "--mo:1-5,5-10,over10"],
    "de_2015": ["--na:de", "-s:2015", "--y:1,2,5,7,10,20,30", "--po:target,market", "--mo:1-5,5-10,over10", "--sp"],
}


# ---------------------------------------------------------------------------
# Sources, read on their own
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One source a curve is drawn from, as published (or as built into the program)."""

    name: str
    read: Callable[[], pd.Series]
    monthly: bool = False  # matched within its month (the program dates monthly rates by the month's first day)
    carry_days: int | None = DAILY_CARRY_DAYS  # longest carry allowed after one of its observations; None: no limit


def _clean(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce").dropna()
    values.index = pd.DatetimeIndex(values.index).normalize()
    return values.sort_index()


def fred(series_id: str, **kwargs) -> Source:
    def read() -> pd.Series:
        # FRED's whole series, not its bake and recent part (``us_data.fred_series``), which the drawing reads.
        frame = http.fetch_fred_csv(series_id)
        return _clean(frame.set_index(frame.columns[0])[series_id])

    return Source(f"FRED {series_id}", read, **kwargs)


def valet(code: str, **kwargs) -> Source:
    # Valet's whole series, not its bake and recent part (``boc_valet_series``), which the drawing reads.
    return Source(f"Valet {code}", lambda: _clean(cdn_data.valet_download(code)), **kwargs)


def valet_group(group: str, code: str, **kwargs) -> Source:
    # The group whole, from the date the drawing reads it from, not its bake and recent part (``boc_valet_group``).
    return Source(f"Valet {code}", lambda: _clean(cdn_data.valet_group_download(group, cdn_data.BOC_START_DATE)[code]), **kwargs)


def iadb(code: str, **kwargs) -> Source:
    # The database's whole series, not its bake and recent part (``iadb_series``), which the drawing reads.
    return Source(f"Bank of England {code}", lambda: _clean(uk_data.iadb_download(code)), **kwargs)


def bundesbank(column: str, frequency: str, **kwargs) -> Source:
    key = de_data.DE_YIELD_SERIES[column]
    name = f"Bundesbank {key}, {'end of month' if frequency == 'M' else 'daily'}"
    # The Bundesbank's whole series, not its bake and recent part (``de_data.bundesbank_series``), which the drawing reads.
    flow, series = de_data.BUNDESBANK_TERM_STRUCTURE_FLOW, de_data.term_structure_key(column, frequency)
    return Source(name, lambda: _clean(de_data.bundesbank_download(flow, series)), **kwargs)


def ecb(flow: str, key: str, unit: str, **kwargs) -> Source:
    # The ECB's whole series, not its bake and recent part (``de_data.ecb_series``), which the drawing reads.
    return Source(f"ECB {flow}.{key}", lambda: _clean(de_data.ecb_download(flow, key, unit)), **kwargs)


def statcan(table: str, vector: str, name: str, **kwargs) -> Source:
    # The table's ZIP, whole, not the vector's bake (``rates.cdn_mortgage_history``), which the drawing reads.
    return Source(f"StatCan {table} ({name})", lambda: _clean(cdn_data.statcan_download(table)[vector]), **kwargs)


def built_in(name: str, rows: list, **kwargs) -> Source:
    """History built into the program (baked or transcribed), as ``joins.embedded_frame`` reads it."""

    def read() -> pd.Series:
        frame = embedded_frame(rows, "value")
        return _clean(frame["value"]) if frame is not None else pd.Series(dtype=float)

    return Source(f"built in: {name}", read, **kwargs)


def built_in_cdn_yield(column: str) -> Source:
    return Source(
        "built in: Bank of Canada PDF tables 1919-2000",
        lambda: _clean(build_cdn_hist_yields()[column]) if column in build_cdn_hist_yields().columns else pd.Series(dtype=float),
        carry_days=MONTHLY_CARRY_DAYS,
    )


def yield_sources(nation: str, column: str) -> list[Source]:
    """The sources of one nation's yield term, newest first."""
    if nation == "us":
        return [fred(us_data.US_YIELD_SERIES[column])]
    if nation == "cdn":
        if column == "3-Month":
            live = [valet(cdn_data.BOC_3M_TBILL_SERIES), valet(cdn_data.BOC_3M_AUCTION_SERIES)]
        elif column in cdn_data.BOC_BILL_SERIES:
            live = [valet(cdn_data.BOC_BILL_SERIES[column])]
        else:
            code = next(code for code, name in cdn_data.BOC_BENCHMARK_COLUMNS.items() if name == column)
            live = [valet_group(cdn_data.BOC_BENCHMARK_GROUP, code)]
        sources = [*live, built_in_cdn_yield(column)]
        if column in cdn_data._YIELD_STAND_INS:
            sources.append(built_in(f"{column} stand-in (term-band average)", cdn_data._YIELD_STAND_INS[column], carry_days=MONTHLY_CARRY_DAYS))
        return sources
    if nation == "uk":
        sources = [iadb(uk_data.UK_YIELD_SERIES[column])]
        if column in uk_data._YIELD_HISTORY:
            sources.append(built_in(f"{column} monthly history", uk_data._YIELD_HISTORY[column], carry_days=MONTHLY_CARRY_DAYS))
        return sources
    sources = [bundesbank(column, "D"), bundesbank(column, "M", carry_days=MONTHLY_CARRY_DAYS)]
    if column in de_data._YIELD_HISTORY:
        sources.append(built_in("yield on public debt securities 1956-2020", de_data._YIELD_HISTORY[column], carry_days=MONTHLY_CARRY_DAYS))
    return sources


def within(source: Source, name: str, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None, less: float = 0.0) -> Source:
    """``source`` from ``start`` and before ``end`` only, less ``less``: the part of it a curve is drawn from."""

    def read() -> pd.Series:
        values = source.read()
        values = values.loc[(values.index >= (start or pd.Timestamp.min)) & (values.index < (end or pd.Timestamp.max))]
        return values - less

    return Source(name, read, source.monthly, source.carry_days)


def policy_sources(nation: str, key: str) -> list[Source]:
    """A policy term's sources (batch 9.1): the official rate's (``key`` "policy") or the market's ("policy_market")."""
    if key == "policy_market":
        return {
            "us": lambda: [fred(rates.US_MARKET_SERIES)],
            "cdn": lambda: [valet(rates.CDN_CORRA_SERIES)],
            "uk": lambda: [iadb(rates.UK_MARKET_SERIES)],
            "de": lambda: [ecb(*rates.DE_ESTR), ecb(*rates.DE_EONIA)],
        }[nation]()
    # An announced rate (the targets, the Bank Rates, the ECB's) holds until
    # it changes and is drawn on to the chart's end (batch 17.3): no limit to
    # its carry. The monthly average before the U.S. target is observed.
    if nation == "us":
        return [
            fred(rates.US_TARGET_SERIES, carry_days=None),
            *(fred(code, carry_days=None) for code in rates.US_TARGET_RANGE_SERIES),
            fred(rates.US_MONTHLY_EFFECTIVE_SERIES, monthly=True, carry_days=MONTHLY_CARRY_DAYS),
        ]
    if nation == "cdn":
        # The weekly Bank Rate is the Bank Rate before 1996-02-22, and less a
        # quarter point the overnight target after, until the daily target.
        weekly = valet(rates.CDN_WEEKLY_BANK_RATE_SERIES, carry_days=None)
        since = rates.CDN_TARGET_FROM
        return [
            valet(rates.CDN_TARGET_SERIES, carry_days=None),
            within(weekly, f"{weekly.name} less {rates.CDN_BANK_RATE_ABOVE_TARGET} from {since:%Y-%m-%d}", start=since,
                   less=rates.CDN_BANK_RATE_ABOVE_TARGET),
            within(weekly, f"{weekly.name} before {since:%Y-%m-%d}", end=since),
            valet(rates.CDN_BANK_RATE_SERIES, carry_days=None),
        ]
    if nation == "uk":
        return [iadb(rates.UK_POLICY_SERIES, carry_days=None), built_in("Bank Rate's changes 1833-2017", EMBEDDED_UK_BANK_RATE_HISTORY, carry_days=None)]
    # The ECB's rates are published on the days they change; the program
    # carries each to the next change (a rate holds until it changes). Before
    # them the Bundesbank's discount rate, baked on its change days (batch 9.6).
    return [
        ecb(*rates.DE_POLICY_FIXED, carry_days=None), ecb(*rates.DE_POLICY_MINIMUM_BID, carry_days=None),
        built_in("the Bundesbank's discount rate's changes 1948-1998", EMBEDDED_DE_DISCOUNT_RATE_CHANGES, carry_days=None),
    ]


def mortgage_sources(term: str, nation: str) -> list[Source]:
    """A mortgage term's sources on ``nation``'s chart (the prime rate is Canada's and the U.S.'; the tracker is Bank Rate)."""
    assert nation in rates.MORTGAGE_TERMS[term][0], (term, nation)
    # Announced: drawn on to the chart's end (batch 17.3). The prime rates,
    # and the UK tracker, Bank Rate's own daily values (batch 9.5).
    held = {"carry_days": None} if term in ("prime", "tracker") else {}
    if term == "tracker":
        return [iadb(rates.UK_POLICY_SERIES, **held)]
    if nation == "us":
        return [fred(rates.US_MORTGAGE_SERIES[term], **held)]
    if nation == "cdn":
        sources = [valet(rates.CDN_MORTGAGE_SERIES[term], **held)]
        if term == "5":
            sources.append(statcan(rates.CDN_MORTGAGE_HISTORY_TABLE, rates.CDN_MORTGAGE_HISTORY_VECTOR, "CMHC rate", carry_days=MONTHLY_CARRY_DAYS))
        return sources
    if nation == "uk":
        sources = [iadb(rates.UK_MORTGAGE_SERIES[term], monthly=True, carry_days=MONTHLY_CARRY_DAYS)]
        if term == "svr":
            sources.append(built_in("variable mortgage rate 1939-2017", EMBEDDED_UK_MORTGAGE_HISTORY, monthly=True, carry_days=MONTHLY_CARRY_DAYS))
        return sources
    return [ecb("MIR", rates.DE_MORTGAGE_SERIES[term], "PCPA", monthly=True, carry_days=MONTHLY_CARRY_DAYS)]


# ---------------------------------------------------------------------------
# The drawn lines, and the matching
# ---------------------------------------------------------------------------


@dataclass
class Drawn:
    """One curve as drawn: its label and its points (a curve drawn in two parts is put together)."""

    label: str
    values: pd.Series  # date-indexed, NaN dropped


def drawn_curves(axes) -> list[Drawn]:
    """The labelled curves on ``axes``, each with the unlabelled parts drawn after it in its colour."""
    curves: list[Drawn] = []
    for line in axes.get_lines():
        x = pd.DatetimeIndex(line.get_xdata()).normalize()
        values = pd.Series(np.asarray(line.get_ydata(), dtype=float), index=x).dropna()
        if line.get_label() == "_nolegend_" and curves:
            curves[-1].values = pd.concat([curves[-1].values, values]).sort_index()
        elif not line.get_label().startswith("_"):
            curves.append(Drawn(line.get_label(), values))
    return curves


@dataclass
class Result:
    explained: dict[str, list[pd.Timestamp]]  # source name -> the dates its own values explain
    carried: dict[str, list[int]]  # source name -> the gaps (days) of the points carried from it
    failures: list[str]


def match(drawn: pd.Series, sources: list[Source], read: dict[str, pd.Series]) -> Result:
    """Match each drawn point with its sources (see the module's docstring)."""
    result = Result({}, {}, [])
    dates = drawn.index
    unexplained = np.ones(len(drawn), dtype=bool)
    for source in sources:  # a source's own value on the date, the first that has it
        values = read[source.name]
        if values.empty:
            continue
        if source.monthly:
            by_month = values.groupby(values.index.to_period("M")).last()
            found = by_month.reindex(dates.to_period("M")).to_numpy()
        else:
            found = values.groupby(level=0).last().reindex(dates).to_numpy()
        same = unexplained & np.isclose(drawn.to_numpy(), found, rtol=0, atol=TOLERANCE)
        if same.any():
            result.explained[source.name] = list(dates[same])
        unexplained &= ~same
    for position in np.flatnonzero(unexplained):  # else carried from a source's last value before
        date, value = dates[position], drawn.iloc[position]
        for source in sources:
            values = read[source.name]
            earlier = values.loc[values.index < (date.to_period("M").start_time if source.monthly else date)]
            if earlier.empty or not np.isclose(earlier.iloc[-1], value, rtol=0, atol=TOLERANCE):
                continue
            gap = (date - earlier.index[-1]).days
            if position == 0 or source.carry_days is None or gap <= source.carry_days:
                result.carried.setdefault(source.name, []).append(gap if position else 0)
                break
            result.failures.append(f"{date:%Y-%m-%d} {value:g}: {source.name}'s {earlier.index[-1]:%Y-%m-%d} value carried {gap} days")
            break
        else:
            nearest = []
            for source in sources:
                values = read[source.name]
                if not values.empty:
                    at = values.index.get_indexer([date], method="nearest")[0]
                    nearest.append(f"{source.name} {values.index[at]:%Y-%m-%d} {values.iloc[at]:g}")
            result.failures.append(f"{date:%Y-%m-%d} {value:g}: no source has it (nearest: {'; '.join(nearest) or 'none'})")
    return result


def spread_failures(drawn: pd.Series, first: pd.Series, second: pd.Series) -> list[str]:
    """Each drawn spread point against the two yields drawn, at its date."""
    expected = (first.groupby(level=0).last() - second.groupby(level=0).last()).reindex(drawn.index)
    wrong = ~np.isclose(drawn.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-6)
    return [
        f"{date:%Y-%m-%d} {value:g}: the yields drawn give {want:g}"
        for date, value, want in zip(drawn.index[wrong], drawn[wrong], expected[wrong])
    ]


def span(dates: list[pd.Timestamp]) -> str:
    return f"{min(dates):%Y-%m-%d}..{max(dates):%Y-%m-%d} ({len(dates):,})"


def check_case(name: str, tokens: list[str]) -> bool:
    """Draw one case and check every yield-axis curve; print a line per curve; True if none failed."""
    printed: list[str] = []
    with this_thread_output_to(printed.append):
        config = resolve_start(cli.parse_args(["--no-gui", PINNED_END, *tokens]))
        figures = {country.key: build_figure(country, config) for country in COUNTRIES if getattr(config, country.show_field)}
        # The curves' labels and kinds, as the drawing prepared them.
        chosen_rates = {country.key: country.prepare(config.for_nation(country.key))[2] for country in COUNTRIES if country.key in figures}
    print(f"== {name}: {' '.join(tokens)} {PINNED_END}")
    passed = True
    for key, figure in figures.items():
        curves = {rates.legend_label(curve, config.for_nation(key)): curve for curve in chosen_rates[key]}
        yields = {}
        drawn_lines = drawn_curves(figure.axes[0])
        for line in drawn_lines:
            if line.label.endswith(" Yield"):
                yields[line.label.removesuffix(" Yield")] = line.values
        for line in drawn_lines:
            curve = curves.get(line.label)
            if curve is not None and curve.spread:
                pair = curve.key.removeprefix("spread_").split("-")
                columns = [_column_of(term) for term in pair]
                if any(column not in yields for column in columns):
                    print(f"  {key:4} {line.label[:44]:44} FAIL  a yield it is taken from is not drawn ({', '.join(columns)})")
                    passed = False
                    continue
                failures = spread_failures(line.values, yields[columns[0]], yields[columns[1]])
                status = "FAIL" if failures else "OK"
                print(f"  {key:4} {line.label[:44]:44} {status:5} {len(line.values):,} points, each {columns[0]} less {columns[1]} as drawn")
                for failure in failures[:3]:
                    print(f"         {failure}")
                passed &= not failures
                continue
            if line.label.endswith(" Yield"):
                sources = yield_sources(key, line.label.removesuffix(" Yield"))
            elif curve is not None and curve.key in ("policy", "policy_market"):
                sources = policy_sources(key, curve.key)
            elif curve is not None and curve.key.startswith("mortgage_"):
                term = curve.key.removeprefix("mortgage_")
                sources = mortgage_sources(term, key)
                field = rates.MORTGAGE_MARGINS.get(term)
                margin = getattr(config.for_nation(key), field) if field else 0.0
                if margin:
                    # The prime rate (batch 9.4) and the UK tracker (9.5) are drawn plus their margins: their sources so, too.
                    sources = [
                        Source(f"{source.name} {margin:+g}", lambda read=source.read: read() + margin, source.monthly, source.carry_days)
                        for source in sources
                    ]
            else:
                print(f"  {key:4} {line.label[:44]:44} FAIL  not known to this tool: add its sources")
                passed = False
                continue
            read = {}
            with this_thread_output_to(None):
                for source in sources:
                    try:
                        read[source.name] = source.read()
                    except Exception as exc:  # reported, never swallowed
                        read[source.name] = pd.Series(dtype=float)
                        print(f"  {key:4} {line.label[:44]:44} note  {source.name} could not be read ({exc})", file=sys.__stdout__)
            result = match(line.values, sources, read)
            parts = [f"{source} {span(dates)}" for source, dates in result.explained.items()]
            carried = [f"{len(gaps):,} carried from {source} (longest {max(gaps)} days)" for source, gaps in result.carried.items()]
            status = "FAIL" if result.failures else "OK"
            print(f"  {key:4} {line.label[:44]:44} {status:5} {len(line.values):,} points: {'; '.join(parts + carried) or 'none'}")
            for failure in result.failures[:5]:
                print(f"         {failure}")
            if len(result.failures) > 5:
                print(f"         ... {len(result.failures) - 5:,} more")
            passed &= not result.failures
        for line in drawn_curves(figure.axes[1]) if len(figure.axes) > 1 else []:
            if not line.values.empty:
                print(f"  {key:4} {line.label[:44]:44} right axis, derived (not compared): {span(list(line.values.index))}")
    # The drawing's warnings, each with the bulleted lines under it (the curves
    # it names), once: the curves were prepared twice, for the chart and above.
    blocks: list[list[str]] = []
    for text in "".join(printed).splitlines():
        if "Warning" in text:
            blocks.append([text.strip()])
        elif blocks and text.strip().startswith("•") and blocks[-1]:
            blocks[-1].append(text.strip())
        elif blocks and blocks[-1]:
            blocks.append([])  # the block ended
    for block in dict.fromkeys(tuple(block) for block in blocks if block):
        print("\n".join(f"  | {text}" for text in block))
    return passed


def _column_of(term: str) -> str:
    """A spread's term ("10y", "3m") as its yield column ("10-Year", "3-Month")."""
    number, unit = term[:-1], term[-1]
    return f"{number}-{'Year' if unit == 'y' else 'Month'}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated case names")
    parser.add_argument("--live", action="store_true", help="fresh downloads instead of the regression cache")
    parser.add_argument("--cache", type=Path, help="download cache folder (default out/download_cache)")
    parser.add_argument("--list", action="store_true", help="list the cases and exit")
    args = parser.parse_args(argv)
    names = args.only.split(",") if args.only else list(CASES)
    unknown = [name for name in names if name not in CASES]
    if unknown:
        parser.error(f"unknown case {unknown[0]} (cases: {', '.join(CASES)})")
    if args.list:
        for name in names:
            print(f"{name:10} {' '.join(CASES[name])}")
        return 0
    if args.live:
        http.enable_download_cache()  # one download each, shared by the drawing and the sources
    else:
        install_disk_cache(http, (args.cache or ROOT / "out" / "download_cache").resolve())
    results = [check_case(name, CASES[name]) for name in names]
    print(f"[drawn values] {sum(results)} of {len(results)} case(s) with every yield-axis point explained")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
