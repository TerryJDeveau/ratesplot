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
their dates, not compared; but on a chart in the master currency (batch
30), each is compared point by point with the same chart drawn without it,
times the rate of its End date worked out here on its own (``fx.rate``):
every amount its own currency's times that one rate. The consumer price
index (batch 13.4), on the right axis or on its own axis outside it, is
compared point by point with its source read here on its own: each point
its month's index, every month of it in the window drawn.

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
from dataclasses import dataclass, replace
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
from ratesplot.cdn_archive_data import EMBEDDED_CDN_POPULATION_HISTORY  # noqa: E402
from ratesplot.config import (  # noqa: E402
    BOC_FINANCIAL_MARKET_TABLE,
    POPULATION_LABEL,
    PRICE_INDEX_ADJUSTED_LABEL,
    PRICE_INDEX_LABEL,
    SEASONALLY_ADJUSTED_NATIONS,
    STATCAN_CDN_CPI_SA_TABLE,
    STATCAN_CDN_CPI_SA_VECTOR,
    STATCAN_CDN_POPULATION_TABLE,
    STATCAN_CDN_POPULATION_VECTOR,
    YIELD_TERMS,
    nation_by_key,
)
from ratesplot.console import this_thread_output_to  # noqa: E402
from ratesplot.fx import rate  # noqa: E402
from ratesplot.joins import embedded_frame  # noqa: E402
from ratesplot.plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402
from ratesplot.uk_archive_data import (  # noqa: E402
    EMBEDDED_UK_BANK_RATE_HISTORY,
    EMBEDDED_UK_CPI_HISTORY,
    EMBEDDED_UK_MORTGAGE_HISTORY,
    EMBEDDED_UK_POPULATION_HISTORY,
)

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
    # Batch 13.6: the U.S. 3-year (FRED DGS3) and a spread of it.
    "us_3y": ["-u", "-s:2015", "--y:2,3,5", "--sp:5y-3y"],
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
    # Batch 30: the master currency, its charts' right axes against the same
    # charts without it: U.S. dollars on all four, the yields unchanged; per
    # capita in Canadian dollars; euros in 1970, at the older rates through
    # the pound (M14 over M15) for the Canadian dollar and the mark.
    "master_usd": ["--na:ca,us,gb,de", "-s:2010", "--master:usd", "--po"],
    "master_cad_p": ["--na:ca,us,gb", "-s:1990", "-p", "--master:cad"],
    "master_eur_1970": ["--na:ca,de", "-s:1955", "--e:1970", "--master:eur"],
    # Batch 13.1: the inflation curve, each month's rise worked out here from
    # its index (the UK's: the millennium index, then the ONS's own rate from
    # 1989), across the U.S.' missing 2025-10 and the UK's join.
    "inflation": ["--na:ca,us,gb,de", "-s:1985", "--inf", "--no-yield"],
    # Batch 13.2: the amounts at constant prices against the same charts in
    # current prices, the index worked out here: from 1910 (each nation's
    # index beginning inside the window, the UK's join in 1988), per capita
    # from 1990, and in the master currency (both checks).
    "constant": ["--na:ca,us,gb,de", "-s:1910", "--constant", "--no-yield"],
    "constant_pc": ["--na:ca,us,gb,de", "-s:1990", "--constant", "-p", "--no-yield"],
    "constant_master": ["--na:ca,us", "-s:2005", "--constant", "--master:usd", "--no-yield"],
    # Batch 13.4: the consumer price index, each point its month's index read
    # here: alone on the right axis from 1910 (each nation's index beginning
    # inside the window, the UK's join in 1988), and seasonally adjusted on its
    # own axis outside the amounts per capita (the UK's unadjusted, named so).
    "cpi": ["--na:ca,us,gb,de", "-s:1910", "--cpi", "--no-yield", "--no-debt", "--no-gdp", "--no-interest"],
    "cpi_sa": ["--na:ca,us,gb,de", "-s:1945", "--cpi:sa", "-p", "--no-yield"],
    "population": ["--na:ca,us,gb,de", "-s:1700", "--population", "--no-yield", "--no-debt", "--no-gdp", "--no-interest"],
    "population_pc": ["--na:ca,us,gb,de", "-s:1960", "--pop", "-p", "--no-yield"],
    # Batch 13.3: the real yields, each nation's every one; Canada's monthly from 1991, then daily; the UK's
    # 20-year with its gaps; Germany's worked out here again, from each bond's own answer; and a spread of two.
    "real_yields": ["--na:ca,us,gb,de", "-s:1985", "--y:r5,r7,r10,r20,r30", "--no-gdp", "--no-debt", "--no-interest"],
    "real_breakeven": ["--na:us,gb,de", "-s:2012", "--y:10,r10", "--sp:10y-r10", "--no-gdp", "--no-debt", "--no-interest"],
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


def uk_real_curve(column: str) -> Source:
    """A real yield of the Bank of England's spot curve, from its two files whole, not its bake and recent part (``uk_data.real_spot_series``)."""

    def read() -> pd.Series:
        return _clean(pd.concat([uk_data.real_curve_archive(), uk_data.real_curve_latest()]).sort_index()[column])

    return Source(f"Bank of England real spot curve, {uk_data.UK_REAL_TERMS[column]} years", read)


def de_real_term(column: str) -> Source:
    """A German real yield worked out here again, a day at a time, from each bond's whole answer: the same rule, not ``de_data.real_yield_at``."""
    years = de_data.DE_REAL_TERMS[column]

    def read() -> pd.Series:
        bonds = {isin: _clean(de_data.bundesbank_download(de_data.DE_LINKED_BOND_FLOW, de_data.linked_bond_key(isin))) for isin in de_data.DE_LINKED_BONDS}
        table = pd.DataFrame(bonds).sort_index().ffill(limit=3)
        values: dict[pd.Timestamp, float] = {}
        for day, row in table.iterrows():
            points = sorted(
                ((de_data.DE_LINKED_BONDS[isin].redeemed - day).days / 365.25, value)
                for isin, value in row.items() if pd.notna(value) and (de_data.DE_LINKED_BONDS[isin].redeemed - day).days / 365.25 >= 1.0
            )
            below = [point for point in points if point[0] <= years]
            above = [point for point in points if point[0] >= years]
            if below and above:
                (low, first), (high, second) = below[-1], above[0]
                values[day] = first if high == low else first + (second - first) * (years - low) / (high - low)
        return pd.Series(values, dtype=float)

    return Source(f"between the inflation-linked bonds, {years:g} years", read)


def yield_sources(nation: str, column: str) -> list[Source]:
    """The sources of one nation's yield term, newest first."""
    if nation == "us":
        return [fred(us_data.US_YIELD_SERIES[column])]
    if nation == "cdn":
        if column == cdn_data.BOC_REAL_RETURN_COLUMN:
            # The monthly table to 2000 (dated the month's first day, as the Bank of Canada's PDF tables are), then Valet's.
            monthly = within(
                statcan(BOC_FINANCIAL_MARKET_TABLE, cdn_data.CDN_REAL_RETURN_VECTOR, "Real Return Bonds", carry_days=MONTHLY_CARRY_DAYS),
                "StatCan 10-10-0122 (Real Return Bonds) to 2000", end=pd.Timestamp("2001-01-01"),
            )
            code = next(code for code, name in cdn_data.BOC_BENCHMARK_COLUMNS.items() if name == column)
            return [valet_group(cdn_data.BOC_BENCHMARK_GROUP, code), monthly]
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
        if column in uk_data.UK_REAL_TERMS:
            return [uk_real_curve(column)]
        sources = [iadb(uk_data.UK_YIELD_SERIES[column])]
        if column in uk_data._YIELD_HISTORY:
            sources.append(built_in(f"{column} monthly history", uk_data._YIELD_HISTORY[column], carry_days=MONTHLY_CARRY_DAYS))
        return sources
    if column in de_data.DE_REAL_TERMS:
        return [de_real_term(column)]
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


def rise_of(source: Source, name: str) -> Source:
    """``source``'s rise over 12 months in percent, worked out here on its own: each month's value over the same month's a year before (batch 13.1)."""

    def read() -> pd.Series:
        values = source.read()
        months = values.groupby(values.index.to_period("M")).last()
        year_before = pd.Series(months.to_numpy(), index=months.index + 12)
        rise = (months / year_before.reindex(months.index) - 1.0) * 100.0
        return rise.set_axis(rise.index.to_timestamp()).dropna()

    return Source(name, read, monthly=True, carry_days=MONTHLY_CARRY_DAYS)


def inflation_sources(nation: str) -> list[Source]:
    """The inflation curve's sources (batch 13.1): each nation's index, its rise worked out here; the UK's the ONS's own rate from 1989."""
    if nation == "uk":
        ons = Source("ONS D7G7", lambda: _clean(uk_data.ons_download("D7G7", "months")), monthly=True, carry_days=MONTHLY_CARRY_DAYS)
        millennium = rise_of(built_in("millennium CPI", EMBEDDED_UK_CPI_HISTORY), "built in: millennium CPI, its 12-month rise")
        return [within(millennium, millennium.name, end=pd.Timestamp("1989-01-01")), ons]
    index = {
        "us": lambda: fred(us_data.US_CPI_SERIES_ID),
        "cdn": lambda: statcan("18100004", "v41690973", "CPI"),
        "de": lambda: Source("Bundesbank BBDP1 CPI", lambda: _clean(de_data.bundesbank_download(*de_data.DE_CPI_SERIES))),
    }[nation]()
    return [rise_of(index, f"{index.name}, its 12-month rise")]


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
            if values.empty:
                continue  # a source that could not be read (its note printed): it explains nothing
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
            elif curve is not None and curve.key == rates.INFLATION_KEY:
                sources = inflation_sources(key)
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
        for axis in figure.axes[1:]:  # the right axis, and the extra axis outside it (batch 13.4)
            for line in drawn_curves(axis):
                if line.label in (PRICE_INDEX_LABEL, PRICE_INDEX_ADJUSTED_LABEL):
                    passed &= check_price_index(key, line, config)
                elif line.label == POPULATION_LABEL:
                    passed &= check_population(key, line, config)
                elif axis is figure.axes[1] and not line.values.empty and config.master_currency is None and not config.constant_prices:
                    print(f"  {key:4} {line.label[:44]:44} right axis, derived (not compared): {span(list(line.values.index))}")
        if config.master_currency is not None:
            passed &= check_master(key, figure, config)
        if config.constant_prices:
            passed &= check_constant(key, figure, config)
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


def check_master(key: str, figure, config) -> bool:
    """A chart in the master currency (batch 30): each right-axis curve the same chart's without it, times its End's rate; True if every point is.

    The yield axis is checked above as on any chart. The rate is worked out
    here from ``fx.rate`` (the nation's currency to the master's on the End
    date), 1 on the master's own chart and where the master changes nothing.
    """
    nation = nation_by_key(key)
    target = config.master_for(key)
    with this_thread_output_to(None):
        plain = build_figure(next(country for country in COUNTRIES if country.key == key), replace(config, master_currency=None))
        found = rate(nation.currency, target, config.end) if target else None
    factor = found.value if found is not None else 1.0
    passed = True
    plain_curves = {line.label: line.values for line in drawn_curves(plain.axes[1])}
    for line in drawn_curves(figure.axes[1]):
        if line.values.empty:
            continue
        before = plain_curves.get(line.label)
        if before is None or not before.index.equals(line.values.index):
            print(f"  {key:4} {line.label[:44]:44} FAIL  not drawn on the same dates without the master currency")
            passed = False
            continue
        worst = float(((line.values / (before * factor)) - 1.0).abs().max())
        ok = worst <= TOLERANCE
        passed &= ok
        print(
            f"  {key:4} {line.label[:44]:44} {'OK' if ok else 'FAIL':5} {len(line.values):,} points, each its own currency's "
            f"x {factor:.5g} {target or nation.currency} per {nation.currency} (largest departure {worst:.1e})"
        )
    return passed


def price_index(nation: str) -> pd.Series:
    """A nation's consumer price index read on its own (batch 13.2), by month (a ``Period`` index): FRED's, Statistics Canada's, the Bundesbank's whole series; the UK's built-in millennium index, then the ONS's D7BT from its first month."""
    if nation == "uk":
        ons = _clean(uk_data.ons_download("D7BT", "months"))
        millennium = built_in("millennium CPI", EMBEDDED_UK_CPI_HISTORY).read()
        values = pd.concat([millennium.loc[millennium.index < ons.index[0].replace(day=1)], ons])
    else:
        values = {
            "us": fred(us_data.US_CPI_SERIES_ID),
            "cdn": statcan("18100004", "v41690973", "CPI"),
            "de": Source("Bundesbank BBDP1 CPI", lambda: _clean(de_data.bundesbank_download(*de_data.DE_CPI_SERIES))),
        }[nation].read()
    return values.groupby(values.index.to_period("M")).last()


def check_constant(key: str, figure, config) -> bool:
    """A chart at constant prices (batch 13.2): each right-axis curve against the same chart's in current prices; True if every point is explained.

    Worked out here on its own: the index (``price_index``) of the month
    each amount was observed in (the last change of the current-price
    curve on or before the point; the latest month published, if its own is
    not), against the index of the last month on or before the End. A
    curve's first run, observed before its first point (or on it, where the
    curve begins inside the window), is matched with the index of any of
    the 15 months to its first point; a point not drawn must be one
    observed before the index begins.
    """
    with this_thread_output_to(None):
        plain = build_figure(next(country for country in COUNTRIES if country.key == key), replace(config, constant_prices=False))
        index = price_index(key)
    base = index.loc[index.index <= pd.Period(config.end, "M")]
    if base.empty:
        print(f"  {key:4} no index on or before the End {config.end:%Y-%m-%d}: drawn in current prices")
        return True
    base_month, base_value = base.index[-1], float(base.iloc[-1])

    def at(month: pd.Period) -> float:
        known = index.loc[index.index <= month]
        return float(known.iloc[-1]) if not known.empty else np.nan

    passed = True
    plain_curves = {line.label.replace("TTM Nominal GDP", "TTM GDP"): line.values for line in drawn_curves(plain.axes[1])}
    for line in drawn_curves(figure.axes[1]):
        if line.values.empty:
            continue
        before = plain_curves.get(line.label)
        if before is None:
            print(f"  {key:4} {line.label[:44]:44} FAIL  not drawn in current prices")
            passed = False
            continue
        changed = before.ne(before.shift())
        changed.iloc[0] = False  # the first point's observation is before the window
        observed = pd.Series(before.index.where(changed), index=before.index).ffill()
        failures: list[str] = []
        first_run = 0
        for when, value in line.values.items():
            if when not in before.index:
                failures.append(f"{when:%Y-%m-%d}: drawn, but not in current prices")
                continue
            ratio = value / before[when]
            seen = observed[when]
            if pd.isna(seen):
                # The first run: observed before its first point, in one of the 15 months before it (or on it,
                # where the curve begins inside the window: Canada's aggregate debt in 1933).
                first = pd.Period(before.index[0], "M")
                months = pd.period_range(first - 15, first, freq="M")
                if not any(abs(ratio / (base_value / at(month)) - 1.0) <= TOLERANCE for month in months):
                    failures.append(f"{when:%Y-%m-%d}: {value:.6g}, no month's index in the 15 before explains it")
                first_run += 1
                continue
            expected = base_value / at(pd.Period(seen, "M"))
            if not abs(ratio / expected - 1.0) <= TOLERANCE:
                failures.append(f"{when:%Y-%m-%d}: {value:.6g}, expected {before[when] * expected:.6g} (observed {seen:%Y-%m-%d})")
        missing = before.index.difference(line.values.index)
        late = [when for when in missing if pd.notna(observed[when]) and pd.Period(observed[when], "M") >= index.index[0]]
        failures += [f"{when:%Y-%m-%d}: not drawn, though observed after the index begins" for when in late[:3]]
        ok = not failures
        passed &= ok
        print(
            f"  {key:4} {line.label[:44]:44} {'OK' if ok else 'FAIL':5} {len(line.values):,} points at {base_month} prices "
            f"(index {base_value:g}), {first_run:,} of them observed before the window; "
            f"{len(missing):,} not drawn, before the index ({index.index[0]})"
        )
        for failure in failures[:5]:
            print(f"         {failure}")
    return passed


def adjusted_price_index(nation: str) -> tuple[str, pd.Series]:
    """A nation's seasonally adjusted consumer price index read on its own (batch 13.4), by month (a ``Period`` index), with its source's name: FRED's, Statistics Canada's, the Bundesbank's whole series."""
    source = {
        "us": fred(us_data.US_CPI_SA_SERIES_ID),
        "cdn": statcan(STATCAN_CDN_CPI_SA_TABLE, STATCAN_CDN_CPI_SA_VECTOR, "CPI, seasonally adjusted"),
        "de": Source("Bundesbank BBDP1 CPI, seasonally adjusted", lambda: _clean(de_data.bundesbank_download(*de_data.DE_CPI_SA_SERIES))),
    }[nation]
    values = source.read()
    return source.name, values.groupby(values.index.to_period("M")).last()


def check_price_index(key: str, line: Drawn, config) -> bool:
    """The consumer price index drawn (batch 13.4): each point its month's index, every month of it in the window drawn; True if so.

    Worked out here on its own: the seasonally adjusted index where --cpi:sa
    draws one (``adjusted_price_index``), else the unadjusted one
    (``price_index``), the UK's under --cpi:sa too; its legend name must say
    which. Each month is dated by its first day; the window takes the months
    whose first day is in it.
    """
    adjusted = config.price_index_adjusted and key in SEASONALLY_ADJUSTED_NATIONS
    wanted = PRICE_INDEX_ADJUSTED_LABEL if adjusted else PRICE_INDEX_LABEL
    if line.label != wanted:
        print(f"  {key:4} {line.label[:44]:44} FAIL  named so, but the index drawn should be named {wanted!r}")
        return False
    try:
        with this_thread_output_to(None):
            name, index = adjusted_price_index(key) if adjusted else (f"{key}'s index, as check_constant reads it", price_index(key))
    except Exception as exc:  # reported, never swallowed
        print(f"  {key:4} {line.label[:44]:44} FAIL  its source could not be read ({exc})")
        return False
    expected = pd.Series(index.to_numpy(dtype=float), index=index.index.to_timestamp())
    return _each_point_is(key, line, expected, config, "the index", f"its month's index ({name}; the index from {index.index[0]})")


def population(nation: str) -> pd.Series:
    """A nation's population read on its own (batch 13.5), in persons, by date: each source's whole series, the older until the newer begins; a quarter dated by its middle, as its reader dates it for -p."""

    def by_middle(quarters: pd.Series) -> pd.Series:
        return quarters.set_axis(pd.DatetimeIndex(quarters.index.to_period("Q").start_time + pd.Timedelta(days=45)))

    if nation == "us":
        return fred(us_data.US_POPULATION_SERIES_ID).read() * 1000.0
    if nation == "cdn":
        older = built_in("Canada's estimates", EMBEDDED_CDN_POPULATION_HISTORY).read()
        newer = statcan(STATCAN_CDN_POPULATION_TABLE, STATCAN_CDN_POPULATION_VECTOR, "population").read()
    elif nation == "uk":
        older = built_in("the Bank of England's estimates", EMBEDDED_UK_POPULATION_HISTORY).read()
        newer = by_middle(_clean(uk_data.ons_download("EBAQ", "quarters")) * 1000.0)
    else:
        annual = _clean(de_data.parse_jsonstat(de_data.eurostat_download("demo_pjan"), "NR"))
        older = annual.set_axis(pd.DatetimeIndex(annual.index.to_period("Y").start_time))
        newer = by_middle(_clean(de_data.parse_jsonstat(de_data.eurostat_download("namq_10_pe"), "THS_PER")) * 1000.0)
    return pd.concat([older.loc[older.index < newer.index[0]], newer])


def check_population(key: str, line: Drawn, config) -> bool:
    """The population drawn (batch 13.5): each point its date's estimate, every estimate in the window drawn, the same under -p; True if so.

    Worked out here on its own (``population``). A count, so never divided.
    """
    try:
        with this_thread_output_to(None):
            people = population(key)
    except Exception as exc:  # reported, never swallowed
        print(f"  {key:4} {line.label[:44]:44} FAIL  its source could not be read ({exc})")
        return False
    return _each_point_is(key, line, people, config, "the population", f"its date's estimate (the estimates from {people.index[0]:%Y-%m-%d})")


def _each_point_is(key: str, line: Drawn, expected: pd.Series, config, what: str, said: str) -> bool:
    """Each point of ``line`` its date's value of ``expected``, every value in the chart's window drawn and no other; True if so, the outcome printed."""
    expected = expected.loc[(expected.index >= pd.Timestamp(config.start)) & (expected.index <= pd.Timestamp(config.end))]
    failures: list[str] = []
    extra = line.values.index.difference(expected.index)
    failures += [f"{when:%Y-%m-%d} {line.values[when]:g}: drawn, but {what} has no value there" for when in extra[:3]]
    missing = expected.index.difference(line.values.index)
    failures += [f"{when:%Y-%m-%d}: {what} has {expected[when]:g}, not drawn" for when in missing[:3]]
    both = line.values.index.intersection(expected.index)
    wrong = ~np.isclose(line.values[both].to_numpy(), expected[both].to_numpy(), rtol=0, atol=TOLERANCE)
    failures += [f"{when:%Y-%m-%d} {line.values[when]:g}: {what} has {expected[when]:g}" for when in both[wrong][:5]]
    ok = not failures
    print(
        f"  {key:4} {line.label[:44]:44} {'OK' if ok else 'FAIL':5} {len(line.values):,} points, each {said}; "
        f"{span(list(both)) if len(both) else 'none'}"
    )
    if len(extra) + len(missing) + int(wrong.sum()) > len(failures):
        failures.append(f"... {len(extra):,} drawn outside {what}, {len(missing):,} not drawn, {int(wrong.sum()):,} different in all")
    for failure in failures:
        print(f"         {failure}")
    return ok


def _column_of(term: str) -> str:
    """A spread's term ("10y", "3m", "r10") as its yield column ("10-Year", "3-Month", "10-Year Real")."""
    return YIELD_TERMS[term]


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
