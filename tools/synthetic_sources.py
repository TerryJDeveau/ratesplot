"""Synthetic stand-ins for every download the program makes, for a machine with no route to the sources.

The cloud copy of this project (Claude Code on the web) has so far had FRED,
the Bank of Canada, Statistics Canada, the Treasury and CNBC all refused by
its network policy (2026-10-06). The values here are made up, smooth
plausible paths plus seeded noise, but they are deterministic and in each
source's own format (FRED frames, Valet CSV, StatCan table ZIPs and WDS JSON), so:

* two program trees fed the same synthetic data can be compared byte for
  byte (``tools/regress_charts.py --synthetic``, ``tools/verify_web.py
  --synthetic``): a change proved neutral there is neutral in the code,
  though not shown against real data;
* new curves can be seen drawn, at plausible sizes, before the real data are
  reachable. They are never evidence about the data themselves.

``synth(key)`` answers one ``ratesplot.http._cached`` key: ``("fred", ID)``
-> DataFrame; ``("canadian", url, params)``, ``("uk", url, params)`` and
``("de", url, params)`` -> Response (the UK's: the Bank of England
database's CSV and the ONS's JSON, in the layouts saved from the laptop in
tools/uk_fixtures; batch 3. Germany's: the Bundesbank's CSV, the ECB's
csvdata and Eurostat's JSON-stat, as saved in tools/de_fixtures; batch 4). A source with no
synthetic answer (the Treasury, CNBC) raises, as a failed download would,
and the program falls back with its usual warning. The series end in
September 2026, past the regression set's pinned end, so a pinned chart
never asks for them. ``install_synthetic_cache`` puts ``synth`` behind the
regression tool's disk cache and refuses every real request, and gives the
program a synthetic bake of the series it has baked (batch 19.2,
``install_synthetic_bake``).

Add a source here when the program reads a new one (its key is printed by
the "no synthetic answer" line).
"""

from __future__ import annotations

import hashlib
import importlib
import io
import itertools
import json
import pickle
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# The U.S. short rate's path (percent) and the 10y-less-short slope's, as
# anchors joined by straight lines; every synthetic yield, policy and
# mortgage rate is built from the two, so they move together as real ones do.
_SHORT = [
    ("1934-01-01", 0.8), ("1946-01-01", 0.4), ("1954-07-01", 1.0), ("1960-01-01", 3.5), ("1970-01-01", 7.5),
    ("1974-07-01", 11.0), ("1977-01-01", 4.7), ("1981-01-01", 17.0), ("1986-01-01", 7.0), ("1989-03-01", 9.8),
    ("1993-01-01", 3.0), ("2000-06-01", 6.5), ("2003-06-01", 1.0), ("2006-07-01", 5.25), ("2008-12-15", 0.1),
    ("2015-12-01", 0.15), ("2019-01-01", 2.4), ("2020-04-01", 0.05), ("2022-03-01", 0.1), ("2023-08-01", 5.33),
    ("2024-09-01", 5.1), ("2025-12-31", 3.9), ("2026-09-30", 3.6),
]
_SLOPE = [
    ("1934-01-01", 2.0), ("1966-01-01", 0.5), ("1969-06-01", -0.6), ("1972-01-01", 1.5), ("1973-08-01", -1.0),
    ("1975-06-01", 2.0), ("1979-01-01", -1.5), ("1981-06-01", -2.0), ("1982-12-01", 2.5), ("1989-03-01", -0.3),
    ("1992-06-01", 3.5), ("2000-09-01", -0.6), ("2003-06-01", 3.0), ("2006-12-01", -0.5), ("2008-12-01", 2.5),
    ("2013-01-01", 2.0), ("2019-08-01", -0.3), ("2021-01-01", 1.2), ("2023-06-01", -1.6), ("2024-12-01", 0.1),
    ("2026-09-30", 0.6),
]


def _anchors(points: list[tuple[str, float]], dates: pd.DatetimeIndex) -> np.ndarray:
    """Return the anchored path at ``dates`` (straight between anchors; flat beyond them)."""
    xs = np.array([pd.Timestamp(d).as_unit("ns").value for d, _ in points], dtype=float)
    ys = np.array([v for _, v in points], dtype=float)
    return np.interp(dates.as_unit("ns").asi8.astype(float), xs, ys)


def _rng(name: str) -> np.random.Generator:
    """A generator seeded by ``name``, so each series has its own noise, the same on every run."""
    return np.random.default_rng(int(hashlib.sha1(name.encode()).hexdigest()[:8], 16))


def _noise(name: str, n: int, scale: float) -> np.ndarray:
    """A smooth seeded wander: a random walk pulled back toward zero."""
    steps = _rng(name).normal(0.0, scale, n)
    out = np.empty(n)
    level = 0.0
    for i, step in enumerate(steps):
        level = 0.97 * level + step
        out[i] = level
    return out


def _yield_path(name: str, dates: pd.DatetimeIndex, years: float, offset: float = 0.0) -> np.ndarray:
    """A yield of term ``years``: the short rate plus its share of the slope, plus noise; two decimals."""
    short = _anchors(_SHORT, dates) + offset
    slope = _anchors(_SLOPE, dates)
    shape = (1 - np.exp(-years / 3.0)) / (1 - np.exp(-10 / 3.0))
    value = short + slope * shape + _noise(name, len(dates), 0.03)
    return np.round(np.maximum(value, 0.01), 2)


def _growth(dates: pd.DatetimeIndex, first: float, last: float, name: str) -> np.ndarray:
    """A level growing geometrically from ``first`` to ``last`` (debt, GDP, interest), with 1 % noise."""
    t = (dates - dates[0]).days.to_numpy(dtype=float)
    span = max(t[-1], 1.0)
    base = first * (last / first) ** (t / span)
    return base * (1 + 0.01 * _noise(name, len(dates), 0.2))


# FRED's daily series: each yield's term in years, and each series' first day.
_TENOR_YEARS = {
    "DGS1MO": 1 / 12, "DGS3MO": 0.25, "DGS6MO": 0.5, "DGS1": 1, "DGS2": 2, "DGS3": 3, "DGS5": 5, "DGS7": 7,
    "DGS10": 10, "DGS20": 20, "DGS30": 30, "DFII5": 5, "DFII7": 7, "DFII10": 10, "DFII20": 20, "DFII30": 30,
}
# The real yields (batch 13.3) run this far below the nominal ones (each its own noise, whose floor keeps it above zero).
_REAL_OFFSET = -2.0
_DAILY_START = {
    "DFII5": "2003-01-02", "DFII7": "2003-01-02", "DFII10": "2003-01-02", "DFII20": "2004-07-27", "DFII30": "2010-02-22",
    "DGS1MO": "2001-07-31", "DGS3MO": "1981-09-01", "DGS6MO": "1981-09-01", "DGS1": "1962-01-02",
    "DGS2": "1976-06-01", "DGS3": "1962-01-02", "DGS5": "1962-01-02", "DGS7": "1969-07-01", "DGS10": "1962-01-02",
    "DGS20": "1962-01-02", "DGS30": "1977-02-15", "DFF": "1954-07-01", "T10Y2Y": "1976-06-01",
    "T10Y3M": "1982-01-04", "DPRIME": "1955-08-04",
}
_GROWTH = {  # id -> (start, freq, first, last), FRED's units
    "GDP": ("1947-01-01", "QS", 243.0, 31_500.0),
    "GFDEBTN": ("1966-01-01", "QS", 320_000.0, 37_200_000.0),
    "SLGSDODNS": ("1945-10-01", "QS", 16_000.0, 3_350_000.0),
    "A180RC1Q027SBEA": ("1947-01-01", "QS", 4.6, 1_650.0),
    "A091RC1Q027SBEA": ("1947-01-01", "QS", 4.2, 1_250.0),
    "B111RC1Q027SBEA": ("1947-01-01", "QS", 0.4, 400.0),
    "W756RC1A027NBEA": ("1959-01-01", "YS", 0.6, 170.0),
    "W856RC1A027NBEA": ("1959-01-01", "YS", 1.2, 230.0),
    "B230RC0Q173SBEA": ("1947-01-01", "QS", 144_000.0, 343_000.0),
    "NGDPSAXDCCAQ": ("1961-01-01", "QS", 40_000.0, 3_200_000.0),
    # Japan's GDP (billions of yen, SAAR) and population (batch 14.3).
    "JPNNGDP": ("1994-01-01", "QS", 500_000.0, 680_000.0),
    "POPTOTJPA647NWDB": ("1960-01-01", "YS", 94_000_000.0, 124_000_000.0),
}
# The balance of payments (batch 23, ``ratesplot.payments``): id -> (start, end, first, last, sign), quarterly, FRED's
# units: BPM6 in millions from 1999; BPM5 in billions 1960 to 2014-Q1 (stopped), its debits negative. BOPBCA,
# the older balance, is made from BOPX and BOPM in ``fred``, with net transfers paid of a billion a quarter.
_PAYMENTS = {
    "IEAX": ("1999-01-01", "2026-04-01", 330_000.0, 1_300_000.0, 1),
    "IEAM": ("1999-01-01", "2026-04-01", 370_000.0, 1_500_000.0, 1),
    "IEAXGS": ("1999-01-01", "2026-04-01", 240_000.0, 790_000.0, 1),
    "IEAMGS": ("1999-01-01", "2026-04-01", 280_000.0, 1_000_000.0, 1),
    # Their last values aimed so that each path meets its BPM6 series' first value at the join, 1999-Q1.
    "BOPX": ("1960-01-01", "2014-01-01", 7.0, 1_390.0, 1),
    "BOPM": ("1960-01-01", "2014-01-01", 5.5, 1_870.0, -1),
    "BOPXGS": ("1960-01-01", "2014-01-01", 6.0, 990.0, 1),
    "BOPMGS": ("1960-01-01", "2014-01-01", 5.0, 1_320.0, -1),
}


def _quarter_points(values: np.ndarray) -> np.ndarray:
    """An announced rate from a path: rounded to quarter points, never below zero."""
    return np.maximum(np.round(values * 4) / 4, 0.0)


# The exchange rates (batch 18.3, ``ratesplot.fx``): id -> (start, end, freq,
# first, last), FRED's units, drifting from the first to the last.
_FX = {
    "DEXCAUS": ("1971-01-04", "2026-09-30", "B", 1.01, 1.39),
    "DEXUSUK": ("1971-01-04", "2026-09-30", "B", 2.39, 1.34),
    "DEXUSEU": ("1999-01-04", "2026-09-30", "B", 1.18, 1.16),
    "EXGEUS": ("1971-01-01", "2001-12-01", "MS", 3.64, 2.19),
    "DEXJPUS": ("1971-01-04", "2026-09-30", "B", 358.0, 147.0),
}

@dataclass(frozen=True, eq=False)
class _EuroSynthetic:
    """A euro-area nation's made-up series (batch 14.3, ``ratesplot.euro_data``): its paths, first and last values, in each source's units.

    ``key`` begins each series' seed ("fr_debt"), so a nation's answers stay
    the same when another is added.
    """

    key: str
    geo: str
    offset: float  # its yields' and mortgage rates' place against the U.S.' path
    yield_series: str
    yield_from: str
    cpi_series: str
    cpi_last: str
    cpi_path: tuple[float, float]
    sector_shares: dict[str, float]
    eurostat_paths: dict[str, tuple[str, float, float]]  # dataset: (first period, first value, last value)
    hicp_path: tuple[float, float]
    yearly_interest_path: tuple[float, float]
    gfs_early_path: tuple[float, float]  # the ECB's year ends 1995 to 1999
    payments_paths: dict[tuple[str, str], tuple[float, float]]  # (item, flow): a quarter's flow, first and last
    payments_from: str  # its first quarter
    months_from: str  # its first month
    mortgage_bands: tuple[str, ...] = ("I", "O", "P")  # the ECB's bands of its mortgage rates (rates.EURO_MORTGAGE_SERIES)
    # Eurostat's convergence-criterion yield, first and last, monthly from 1980-01 (decision 178: Italy's), or None.
    yield_history_path: tuple[float, float] | None = None
    # Daily yields on BPstat (9.13, Portugal's) or Webstat (9.14, France's), by series id: (term in years, first day,
    # gaps as (first, last) days with no value); Portugal's ``yield_series`` then empty, no FRED yield; France's 10-year
    # FRED's monthly before its daily one.
    daily_yields: dict[str, tuple[float, str, tuple[tuple[str, str], ...]]] = field(default_factory=dict)
    daily_source: str = "bpstat"  # the service of ``daily_yields`` (``euro_data.EuroNation.daily_source``)


# The euro area's nations after Germany, by Eurostat's code. France's (batch 14.3): no state level, the social security
# funds no level of the chart; its yields and mortgage rates between Germany's and the U.S.'.
_EURO = {
    "FR": _EuroSynthetic(
        key="fr", geo="FR", offset=-0.6, yield_series="IRLTLT01FRM156N", yield_from="1960-01-01",
        cpi_series="FRACPIALLMINMEI", cpi_last="2025-03-01", cpi_path=(7.43, 120.38),
        sector_shares={"S13": 1.0, "S1311": 0.80, "S1313": 0.08, "S1314": 0.12},
        eurostat_paths={
            "gov_10q_ggdebt": ("2000Q1", 870_000, 3_416_000),
            "gov_10q_ggnfa": ("1995Q1", 9_800, 17_200),
            "namq_10_gdp": ("1980Q1", 74_000, 760_000),
            "namq_10_pe": ("1980Q1", 55_100, 68_700),
        },
        hicp_path=(64.0, 101.2), yearly_interest_path=(39_000, 60_100), gfs_early_path=(663_000, 804_000),
        payments_paths={
            ("CA", "CRE"): (120_000, 399_000), ("CA", "DEB"): (110_000, 406_000),
            ("GS", "CRE"): (85_000, 274_000), ("GS", "DEB"): (80_000, 270_000),
        },
        payments_from="1999Q1", months_from="2008-01", mortgage_bands=("I", "O", "P", "F"),  # F, its variable rate, 9.8
        # Its eight daily terms on Webstat (9.14), from Webstat's first days; one gap of a week in the 20-year, so a
        # break is drawn.
        daily_yields={
            **{f"FM.D.FR.EUR.FR2.BB.FRMOYTEC{years}.HSTA": (years, "2004-11-03", ()) for years in (1, 2, 3, 5, 7, 10)},
            "FM.D.FR.EUR.FR2.BB.FRMOYTEC20.HSTA": (20, "2004-11-03", (("2012-05-07", "2012-05-14"),)),
            "FM.D.FR.EUR.FR2.BB.FRMOYTEC30.HSTA": (30, "2006-10-02", ()),
        },
        daily_source="webstat",
    ),
    # Portugal's (batch 14.3, decision 175): the same shapes, its yields and mortgage rates above France's; its central
    # government's debt above general government's, as Eurostat's is (each subsector consolidated within it alone).
    "PT": _EuroSynthetic(
        key="pt", geo="PT", offset=0.3, yield_series="", yield_from="1993-07-16",
        cpi_series="PRTCPIALLMINMEI", cpi_last="2025-04-01", cpi_path=(1.0, 123.5),
        sector_shares={"S13": 1.0, "S1311": 1.07, "S1313": 0.04, "S1314": 0.01},
        eurostat_paths={
            "gov_10q_ggdebt": ("2000Q1", 62_000, 294_000),
            "gov_10q_ggnfa": ("1999Q1", 900, 1_400),
            "namq_10_gdp": ("1995Q1", 21_000, 81_000),
            "namq_10_pe": ("1995Q1", 10_000, 10_880),
        },
        hicp_path=(52.7, 105.1), yearly_interest_path=(4_100, 6_000), gfs_early_path=(36_000, 52_000),
        payments_paths={
            ("CA", "CRE"): (6_000, 45_000), ("CA", "DEB"): (7_500, 46_000),
            ("GS", "CRE"): (5_000, 37_000), ("GS", "DEB"): (7_000, 37_300),
        },
        payments_from="1996Q1", months_from="1996-01", mortgage_bands=("I", "O", "P", "F"),
        # Its five daily terms (9.13), from BPstat's first days, with two of BPstat's gaps, so a break is drawn.
        daily_yields={
            "12099454": (2, "1993-07-16", (("2002-07-17", "2003-02-13"),)),
            "12099455": (3, "1993-07-16", ()),
            "12099457": (5, "1994-02-04", ()),
            "12099458": (7, "1993-07-16", (("2015-02-03", "2016-04-19"),)),
            "12099459": (10, "1993-07-16", ()),
        },
    ),
    # Italy's (batch 14.3, decision 177): the same shapes, its yields and mortgage rates above Portugal's; its central
    # government owing nearly all of general government's debt.
    "IT": _EuroSynthetic(
        key="it", geo="IT", offset=0.6, yield_series="IRLTLT01ITM156N", yield_from="1991-03-01",
        cpi_series="ITACPIALLMINMEI", cpi_last="2025-03-01", cpi_path=(2.9, 122.5),
        sector_shares={"S13": 1.0, "S1311": 0.98, "S1313": 0.033, "S1314": 0.0001},
        eurostat_paths={
            "gov_10q_ggdebt": ("2000Q1", 1_300_000, 3_208_000),
            "gov_10q_ggnfa": ("1999Q1", 19_000, 28_700),
            "namq_10_gdp": ("1995Q1", 230_000, 577_000),
            "namq_10_pe": ("1995Q1", 56_800, 58_950),
        },
        hicp_path=(54.3, 106.2), yearly_interest_path=(100_000, 87_000), gfs_early_path=(1_150_000, 1_280_000),
        payments_paths={
            ("CA", "CRE"): (60_000, 240_000), ("CA", "DEB"): (55_000, 241_000),
            ("GS", "CRE"): (50_000, 198_000), ("GS", "DEB"): (45_000, 186_000),
        },
        payments_from="1995Q1", months_from="2008-01", mortgage_bands=("I", "O", "P", "F"),
        yield_history_path=(14.0, 4.7),
    ),
    # Spain's (batch 14.3, decision 180): the same shapes, its yields and mortgage rates between France's and
    # Portugal's; a state level (S1312, its autonomous communities), its quarters from 1995.
    "ES": _EuroSynthetic(
        key="es", geo="ES", offset=0.1, yield_series="IRLTLT01ESM156N", yield_from="1980-01-01",
        cpi_series="ESPCPIALLMINMEI", cpi_last="2025-03-01", cpi_path=(1.6, 125.5),
        sector_shares={"S13": 1.0, "S1311": 0.915, "S1312": 0.20, "S1313": 0.012, "S1314": 0.077},
        eurostat_paths={
            "gov_10q_ggdebt": ("1995Q1", 280_000, 1_763_000),
            "gov_10q_ggnfa": ("1995Q1", 6_000, 13_200),
            "namq_10_gdp": ("1995Q1", 110_000, 441_000),
            "namq_10_pe": ("1995Q1", 39_300, 49_850),
        },
        hicp_path=(50.5, 105.9), yearly_interest_path=(24_000, 40_400), gfs_early_path=(300_000, 370_000),
        payments_paths={
            ("CA", "CRE"): (35_000, 212_000), ("CA", "DEB"): (37_000, 203_000),
            ("GS", "CRE"): (30_000, 168_000), ("GS", "DEB"): (33_000, 153_000),
        },
        payments_from="1993Q1", months_from="2008-01", mortgage_bands=("I", "O", "P", "F"),
    ),
    # The Netherlands' (batch 14.3, decision 182): the same shapes, its yields and mortgage rates a little below
    # Spain's; no state level; its balance of payments from 2003-Q2 (its months never asked: none exist).
    "NL": _EuroSynthetic(
        key="nl", geo="NL", offset=-0.3, yield_series="IRLTLT01NLM156N", yield_from="1959-01-01",
        cpi_series="NLDCPIALLMINMEI", cpi_last="2025-04-01", cpi_path=(15.8, 134.7),
        sector_shares={"S13": 1.0, "S1311": 1.11, "S1313": 0.101, "S1314": 0.0056},
        eurostat_paths={
            "gov_10q_ggdebt": ("2000Q1", 255_000, 524_000),
            "gov_10q_ggnfa": ("1999Q1", 4_300, 2_400),
            "namq_10_gdp": ("1995Q1", 80_000, 304_000),
            "namq_10_pe": ("1995Q1", 15_430, 18_170),
        },
        hicp_path=(50.0, 104.8), yearly_interest_path=(17_000, 8_500), gfs_early_path=(241_000, 230_000),
        payments_paths={
            ("CA", "CRE"): (105_000, 364_000), ("CA", "DEB"): (101_000, 347_000),
            ("GS", "CRE"): (74_000, 260_000), ("GS", "DEB"): (66_000, 230_000),
        },
        payments_from="2003Q2", months_from="2008-01", mortgage_bands=("I", "O", "P", "F"),
    ),
}
# Each nation's FRED series, by code.
_EURO_YIELDS = {euro.yield_series: euro for euro in _EURO.values() if euro.yield_series}
# Each daily yield on BPstat (9.13), by series id: its nation, and its term, first day and gaps.
_BPSTAT_YIELDS = {series_id: (euro, term) for euro in _EURO.values() if euro.daily_source == "bpstat"
                  for series_id, term in euro.daily_yields.items()}
# Each daily yield on Webstat (9.14), by series key, as BPstat's.
_WEBSTAT_YIELDS = {key: (euro, term) for euro in _EURO.values() if euro.daily_source == "webstat"
                   for key, term in euro.daily_yields.items()}
_EURO_CPIS = {euro.cpi_series: euro for euro in _EURO.values()}

# Every FRED series ``fred`` answers.
_FRED_IDS = (
    "FEDFUNDS", "DFEDTAR", "DFEDTARL", "DFEDTARU", "MORTGAGE30US", "MORTGAGE15US", "CPIAUCNS", "CPIAUCSL", *_GROWTH, *_DAILY_START, *_FX,
    *_PAYMENTS, "BOPBCA",
    *(code for euro in _EURO.values() for code in (euro.cpi_series, euro.yield_series) if code),
)


def fred(series_id: str) -> pd.DataFrame:
    """Return one FRED series as ``http.fetch_fred_csv`` returns it: ``DATE`` and the series' values.

    Whole, whatever date it is asked from (a key ``("fred", ID, SINCE)``,
    batch 19.2), as the Bank of England's and Valet's are: the program cuts
    what it asked for.
    """
    if series_id == "FEDFUNDS":
        # The effective rate's monthly average (batch 9.1).
        dates = pd.date_range("1954-07-01", "2026-09-01", freq="MS")
        values = np.round(np.maximum(_anchors(_SHORT, dates), 0.04), 2)
    elif series_id in ("DFEDTAR", "DFEDTARL", "DFEDTARU"):
        # The target, every calendar day, then its range a quarter point wide.
        first, last = ("1982-09-27", "2008-12-15") if series_id == "DFEDTAR" else ("2008-12-16", "2026-09-30")
        dates = pd.date_range(first, last, freq="D")
        values = _quarter_points(_anchors(_SHORT, dates)) + (0.25 if series_id == "DFEDTARU" else 0.0)
    elif series_id == "CPIAUCNS":
        # The consumer price index (batch 13.1), monthly from 1913, three decimals as FRED gives it.
        dates = pd.date_range("1913-01-01", "2026-09-01", freq="MS")
        values = np.round(_growth(dates, 9.8, 337.0, series_id), 3)
    elif series_id == "CPIAUCSL":
        # The same index seasonally adjusted (batch 13.4), monthly from 1947.
        dates = pd.date_range("1947-01-01", "2026-09-01", freq="MS")
        values = np.round(_growth(dates, 21.5, 336.3, series_id), 3)
    elif series_id in _EURO_YIELDS:
        # A euro-area nation's 10-year (batch 14.3): the OECD's monthly average, each month's first day.
        euro = _EURO_YIELDS[series_id]
        dates = pd.date_range(euro.yield_from, "2026-09-01", freq="MS")
        values = _yield_path(series_id, dates, 10, euro.offset)
    elif series_id in _EURO_CPIS:
        # A euro-area nation's national consumer price index (batch 14.3's third stage), 2015 = 100, from 1955-01 to its
        # stop, as many decimals as FRED gives it.
        euro = _EURO_CPIS[series_id]
        dates = pd.date_range("1955-01-01", euro.cpi_last, freq="MS")
        values = _growth(dates, *euro.cpi_path, series_id)
    elif series_id in _GROWTH:
        start, freq, first, last = _GROWTH[series_id]
        end = "2026-07-01" if freq == "QS" else "2025-01-01"
        dates = pd.date_range(start, end, freq=freq)
        values = np.round(_growth(dates, first, last, series_id), 1)
    elif series_id in _PAYMENTS:
        start, end, first, last, sign = _PAYMENTS[series_id]
        dates = pd.date_range(start, end, freq="QS")
        values = sign * np.round(_growth(dates, first, last, series_id), 3 if first < 1_000 else 0)
    elif series_id == "BOPBCA":
        credits, debits = (fred(code).set_index("DATE")[code] for code in ("BOPX", "BOPM"))
        dates, values = credits.index, np.round((credits + debits - 1.0).to_numpy(), 3)
    elif series_id in _FX:
        start, end, freq, first, last = _FX[series_id]
        dates = pd.bdate_range(start, end) if freq == "B" else pd.date_range(start, end, freq=freq)
        values = np.round(_growth(dates, first, last, series_id), 4)
    elif series_id in _DAILY_START or series_id.startswith("MORTGAGE"):
        if series_id.startswith("MORTGAGE"):
            start = "1971-04-02" if series_id == "MORTGAGE30US" else "1991-08-30"
            dates = pd.date_range(start, "2026-10-01", freq="W-THU")
            margin = 1.7 if series_id == "MORTGAGE30US" else 1.0
            values = _yield_path(series_id, dates, 10) + margin
        else:
            dates = pd.bdate_range(_DAILY_START[series_id], "2026-09-30")
            if series_id == "DFF":
                values = np.round(np.maximum(_anchors(_SHORT, dates) + _noise("DFF", len(dates), 0.01), 0.04), 2)
            elif series_id == "DPRIME":
                # The banks' prime loan rate (batch 9.4): by convention the policy rate plus 3 points.
                values = np.round(np.maximum(_anchors(_SHORT, dates), 0.0) + 3.0, 2)
            elif series_id in ("T10Y2Y", "T10Y3M"):
                other = "DGS2" if series_id == "T10Y2Y" else "DGS3MO"
                ten, short = fred("DGS10").set_index("DATE")["DGS10"], fred(other).set_index("DATE")[other]
                both = (ten - short).dropna()
                both = both.loc[both.index >= dates[0]]
                dates, values = both.index, np.round(both.to_numpy(), 2)
            else:
                values = _yield_path(series_id, dates, _TENOR_YEARS[series_id], _REAL_OFFSET if series_id.startswith("DFII") else 0.0)
    else:
        raise KeyError(f"no synthetic FRED series {series_id}")
    return pd.DataFrame({"DATE": dates, series_id: np.asarray(values, dtype=float)})


def _response(content: bytes) -> requests.Response:
    """A successful Response with ``content`` as its body, as ``http.canadian_get`` returns one."""
    response = requests.Response()
    response._content = content
    response.status_code = 200
    response.encoding = "utf-8"
    return response


def _valet_csv(columns: dict[str, np.ndarray], dates: pd.DatetimeIndex) -> bytes:
    """A Valet CSV: a metadata block, then "date" and one column per series (``http.parse_boc_csv``)."""
    lines = ['"TERMS AND CONDITIONS"', '"https://www.bankofcanada.ca/terms/"', "", '"SERIES"', "", '"OBSERVATIONS"']
    lines.append(",".join(['"date"'] + [f'"{name}"' for name in columns]))
    for i, day in enumerate(dates):
        lines.append(",".join([f'"{day:%Y-%m-%d}"'] + [("" if np.isnan(v[i]) else f'"{v[i]:.2f}"') for v in columns.values()]))
    return "\n".join(lines).encode()


# Canadian yields run this far above the U.S. ones. Valet series: code ->
# (first day, frequency, term in years for the yield shape (0: the short rate
# itself, a policy rate), margin above that yield).
_CDN_OFFSET = 0.3
_VALET_SERIES = {
    "V80691303": ("2000-12-01", "B", 0.25, 0.0),
    "TB.CDN.90D.MID": ("2001-01-02", "B", 0.25, 0.0),
    "TB.CDN.30D.MID": ("2001-01-02", "B", 1 / 12, 0.0),
    "TB.CDN.180D.MID": ("2001-01-02", "B", 0.5, 0.0),
    "TB.CDN.1Y.MID": ("2001-01-02", "B", 1, 0.0),
    "V122530": ("1935-03-01", "MS", 0.0, 0.25),
    # Batch 9.1: the weekly Bank Rate and the daily overnight target, in
    # quarter points (``valet``), the target a quarter point below.
    "V80691310": ("1980-01-02", "W-WED", 0.0, 0.25),
    "CBC20210": ("2001-01-01", "B", 0.0, 0.0),
    "AVG.INTWO": ("1997-01-02", "B", 0.0, 0.0),
    "V80691335": ("1975-01-01", "W-WED", 10, 2.4),
    "V80691334": ("1980-01-02", "W-WED", 3, 2.6),
    "V80691333": ("1980-01-02", "W-WED", 1, 2.7),
    "BROKER_AVERAGE_5YR_VRM": ("2011-01-05", "W-WED", 0.25, 0.9),
    "V80691311": ("1975-01-01", "W-WED", 0.0, 2.2),
}


def valet(url: str, params: tuple) -> bytes:
    """Return a Valet response body: the benchmark-yield group, or one series, whole whatever its ``start_date``.

    Whole: each series' noise is drawn day by day from its first date, so an
    answer cut at a later date would give other values on the same days. As
    the Bank of England's (``iadb``), the program cuts what it asked for
    (batch 19.2). The starts the program asked for before then (2000-12-01
    for the group and the bills, 1900-01-01 for the rates) precede or equal
    each synthetic series' first day, so its earlier answers are unchanged.
    """
    del params  # every answer whole (above)
    if "group/bond_yields_benchmark" in url:
        dates = pd.bdate_range("2000-12-01", "2026-08-31")
        columns = {
            code: _yield_path("cdn" + code, dates, years, _CDN_OFFSET)
            for code, years in (
                ("BD.CDN.2YR.DQ.YLD", 2), ("BD.CDN.3YR.DQ.YLD", 3), ("BD.CDN.5YR.DQ.YLD", 5), ("BD.CDN.7YR.DQ.YLD", 7),
                ("BD.CDN.10YR.DQ.YLD", 10), ("BD.CDN.LONG.DQ.YLD", 30),
            )
        }
        columns["BD.CDN.RRB.DQ.YLD"] = _yield_path("cdnBD.CDN.RRB.DQ.YLD", dates, 30, _CDN_OFFSET + _REAL_OFFSET)
        return _valet_csv(columns, dates)
    code = url.rstrip("/").split("/")[-2]
    first, freq, years, margin = _VALET_SERIES[code]
    dates = pd.bdate_range(first, "2026-08-31") if freq == "B" else pd.date_range(first, "2026-08-31", freq=freq)
    if code in ("V80691310", "CBC20210"):
        values = _quarter_points(_anchors(_SHORT, dates) + _CDN_OFFSET - 0.4) + margin
    elif years == 0:
        values = np.round(np.maximum(_anchors(_SHORT, dates) + _CDN_OFFSET - 0.4, 0.25) + margin, 2)
    else:
        values = _yield_path("cdn" + code, dates, years, _CDN_OFFSET) + margin
    return _valet_csv({code: values}, dates)


def _zip(table_id: str, frame: pd.DataFrame) -> bytes:
    """A StatCan table ZIP: the data CSV and a metadata CSV (``cdn_data.statcan_zip_table_with_metadata``)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{table_id}.csv", frame.to_csv(index=False))
        archive.writestr(f"{table_id}_MetaData.csv", "Cube Title\nsynthetic\n")
    return buffer.getvalue()


# The vector of each series of the synthetic tables that the program reads: the real ones
# (cdn_data.STATCAN_SERIES_READ, measured 2026-10-22), so that a selection by the table's labels
# finds the vector declared, as in the real tables (19.2's Statistics Canada stage). A series not
# read gets a made-up vector from 900000001 on. Each table also has its unit and scale (UOM,
# SCALAR_FACTOR, SCALAR_ID), as the real ones.
_STATCAN_GFS_VECTORS = {
    ("Consolidated government", "Interest"): "v52531011",
    ("Federal government", "Interest"): "v52531068",
    ("Federal government", "Special drawing rights (SDRs), liabilities"): "v1563966091",
    ("Federal government", "Currency and deposits, liabilities"): "v52531103",
    ("Federal government", "Debt securities, liabilities"): "v52531104",
    ("Federal government", "Loans, liabilities"): "v52531105",
    ("Federal government", "Insurance and pension schemes, liabilities"): "v52531107",
    ("Federal government", "Other accounts payable, liabilities"): "v52531108",
    ("Provincial and territorial government", "Interest"): "v52531125",
    ("Provincial and territorial government", "Special drawing rights (SDRs), liabilities"): "v1563966095",
    ("Provincial and territorial government", "Currency and deposits, liabilities"): "v52531160",
    ("Provincial and territorial government", "Debt securities, liabilities"): "v52531161",
    ("Provincial and territorial government", "Loans, liabilities"): "v52531162",
    ("Provincial and territorial government", "Insurance and pension schemes, liabilities"): "v52531164",
    ("Provincial and territorial government", "Other accounts payable, liabilities"): "v52531165",
    ("Local government", "Interest"): "v52531182",
    ("Local government", "Special drawing rights (SDRs), liabilities"): "v1563966099",
    ("Local government", "Currency and deposits, liabilities"): "v52531217",
    ("Local government", "Debt securities, liabilities"): "v52531218",
    ("Local government", "Loans, liabilities"): "v52531219",
    ("Local government", "Insurance and pension schemes, liabilities"): "v52531221",
    ("Local government", "Other accounts payable, liabilities"): "v52531222",
}
# The balance of payments' (batch 23): table -> (its quarters, {(side, account): (vector, first, last value)}),
# millions a quarter, the real vectors (config.STATCAN_CDN_PAYMENTS_VECTORS). The archived 36-10-0047 is
# baked into cdn_archive_data and asked for by nothing synthetic (Terry, 2026-11-11).
_STATCAN_PAYMENTS = {
    "36100018": (("1981-01-01", "2026-04-01"), {
        ("Receipts, seasonally adjusted", "Total current account"): ("v61915244", 26_400, 330_000),
        ("Payments, seasonally adjusted", "Total current account"): ("v61915273", 30_000, 338_000),
        ("Receipts, seasonally adjusted", "Goods and services"): ("v61915245", 23_700, 270_000),
        ("Payments, seasonally adjusted", "Goods and services"): ("v61915274", 23_000, 276_000),
    }),
}
_MILLIONS = {"UOM": "Dollars", "SCALAR_FACTOR": "millions", "SCALAR_ID": 6}
_UNITS = {"SCALAR_FACTOR": "units", "SCALAR_ID": 0}
# Canada's trade each month (batch 43.3c): goods on a balance of payments basis (12-10-0011, from 1997) and total
# services (12-10-0144, from 2007), millions a month, to 2026-09, a quarter past the balance of payments; each line
# (exports, imports) about a third of the quarterly "Goods and services" at its end.
_STATCAN_MONTHLY_TRADE = {
    "12100011": ("1997-01-01", {"v87008955": (16_000, 72_000), "v87008839": (15_000, 74_000)}),
    "12100144": ("2007-01-01", {"v1105277795": (5_500, 18_000), "v1105277805": (7_000, 18_500)}),
}
# The tables the WDS's answers are drawn from (``statcan_wds``); the Real Return Bonds' 10-10-0122, asked of the
# WDS only by the bake's fallback (9.15), its vector in no other table; the monthly trade's, asked of the WDS alone.
_STATCAN_TABLES = ("36100467", "36100104", "10100015", "17100009", "34100145", "18100004", "18100006", *_STATCAN_PAYMENTS, "10100122",
                   *_STATCAN_MONTHLY_TRADE)


def statcan(table_id: str) -> bytes:
    """Return a StatCan table ZIP with the columns and members the program selects on (millions; persons; percent)."""
    quarters = pd.date_range("1990-01-01", "2026-04-01", freq="QS")
    ref = [f"{d:%Y-%m}" for d in quarters]
    if table_id == "36100467":
        values = _growth(quarters, 780_000, 3_600_000, "cdn_debt")
        frame = pd.DataFrame({"REF_DATE": ref, "GEO": "Canada", "Estimates": "Debt", **_MILLIONS, "VECTOR": "v111463452",
                              "VALUE": np.round(values, 0)})
        other = frame.assign(Estimates="Gross debt to GDP", UOM="Percent", **_UNITS, VECTOR="v900000001", VALUE=60.0)
        return _zip(table_id, pd.concat([frame, other]))
    if table_id == "36100104":
        q = pd.date_range("1961-01-01", "2026-04-01", freq="QS")
        values = _growth(q, 42_000, 3_150_000, "cdn_gdp")
        frame = pd.DataFrame({
            "REF_DATE": [f"{d:%Y-%m}" for d in q], "GEO": "Canada",
            "Prices": "Current prices", "Seasonal adjustment": "Seasonally adjusted at annual rates",
            "Estimates": "Gross domestic product at market prices", **_MILLIONS, "VECTOR": "v62305783", "VALUE": np.round(values, 0),
        })
        return _zip(table_id, frame)
    if table_id == "10100015":
        rows = []
        sectors = {
            "Consolidated government": 1.0, "Federal government": 0.5,
            "Provincial and territorial government": 0.42, "Local government": 0.08,
        }
        items = {
            "Interest": (11_000, 21_000),
            "Debt securities, liabilities": (500_000, 2_400_000),
            "Loans, liabilities": (60_000, 250_000),
            "Currency and deposits, liabilities": (20_000, 60_000),
            "Special drawing rights (SDRs), liabilities": (1_000, 20_000),
            "Insurance and pension schemes, liabilities": (100_000, 500_000),
            "Other accounts payable, liabilities": (40_000, 200_000),
        }
        made_up = itertools.count(900000002)
        for sector, share in sectors.items():
            for item, (first, last) in items.items():
                values = _growth(quarters, first * share, last * share, sector + item)
                rows.append(pd.DataFrame({
                    "REF_DATE": ref, "GEO": "Canada", "Government sectors": sector,
                    "Statement of government operations and balance sheet": item, **_MILLIONS,
                    "VECTOR": _STATCAN_GFS_VECTORS.get((sector, item)) or f"v{next(made_up)}", "VALUE": np.round(values, 0),
                }))
        return _zip(table_id, pd.concat(rows))
    if table_id == "17100009":
        q = pd.date_range("1946-01-01", "2026-07-01", freq="QS")
        values = _growth(q, 12_000_000, 41_700_000, "cdn_pop")
        frame = pd.DataFrame({"REF_DATE": [f"{d:%Y-%m}" for d in q], "GEO": "Canada", "UOM": "Persons", **_UNITS, "VECTOR": "v1",
                              "VALUE": np.round(values, 0)})
        return _zip(table_id, frame)
    if table_id == "34100145":
        months = pd.date_range("1951-01-01", "2026-08-01", freq="MS")
        values = _yield_path("cdn_mortgage5", months, 10, _CDN_OFFSET) + 2.0
        frame = pd.DataFrame({
            "REF_DATE": [f"{d:%Y-%m}" for d in months], "GEO": "Canada", "DGUID": "2016A000011124",
            "UOM": "Percent", **_UNITS, "VECTOR": "v733833", "VALUE": values,
        })
        return _zip(table_id, frame)
    if table_id == "18100004":
        # The consumer price index (batch 13.1), monthly from 1914, 2002 = 100, to a tenth.
        months = pd.date_range("1914-01-01", "2026-09-01", freq="MS")
        values = _growth(months, 6.0, 170.0, "cdn_cpi")
        frame = pd.DataFrame({
            "REF_DATE": [f"{d:%Y-%m}" for d in months], "GEO": "Canada", "Products and product groups": "All-items",
            "UOM": "2002=100", **_UNITS, "VECTOR": "v41690973", "VALUE": np.round(values, 1),
        })
        return _zip(table_id, frame)
    if table_id == "18100006":
        # The same index seasonally adjusted (batch 13.4), monthly from 1992.
        months = pd.date_range("1992-01-01", "2026-09-01", freq="MS")
        values = _growth(months, 84.0, 170.0, "cdn_cpi_sa")
        frame = pd.DataFrame({
            "REF_DATE": [f"{d:%Y-%m}" for d in months], "GEO": "Canada", "Products and product groups": "All-items",
            "UOM": "2002=100", **_UNITS, "VECTOR": "v41690914", "VALUE": np.round(values, 1),
        })
        return _zip(table_id, frame)
    if table_id == "10100122":
        # The Real Return Bonds' long-term yield (batch 13.3), monthly from 1991-11, its months before that blank.
        months = pd.date_range("1962-01-01", "2026-09-01", freq="MS")
        values = _yield_path("cdn_rrb", months, 30, _CDN_OFFSET + _REAL_OFFSET)
        frame = pd.DataFrame({
            "REF_DATE": [f"{d:%Y-%m}" for d in months], "GEO": "Canada", "Rates": "Real return bonds, long-term",
            "UOM": "Percent", **_UNITS, "VECTOR": "v122553", "VALUE": np.where(months >= pd.Timestamp("1991-11-01"), values, np.nan),
        })
        return _zip(table_id, frame)
    if table_id in _STATCAN_PAYMENTS:
        # The balance of payments (batch 23): 36-10-0018 from 1981.
        (first, last), lines = _STATCAN_PAYMENTS[table_id]
        q = pd.date_range(first, last, freq="QS")
        rows = [
            pd.DataFrame({
                "REF_DATE": [f"{d:%Y-%m}" for d in q], "GEO": "Canada", "Receipts, payments and balances": side,
                "Current account": account, **_MILLIONS, "VECTOR": vector, "VALUE": np.round(_growth(q, low, high, table_id + vector), 0),
            })
            for (side, account), (vector, low, high) in lines.items()
        ]
        return _zip(table_id, pd.concat(rows))
    if table_id in _STATCAN_MONTHLY_TRADE:
        first, lines = _STATCAN_MONTHLY_TRADE[table_id]
        months = pd.date_range(first, "2026-09-01", freq="MS")
        rows = [
            pd.DataFrame({"REF_DATE": [f"{d:%Y-%m}" for d in months], "GEO": "Canada", **_MILLIONS, "VECTOR": vector,
                          "VALUE": np.round(_growth(months, low, high, table_id + vector), 0)})
            for vector, (low, high) in lines.items()
        ]
        return _zip(table_id, pd.concat(rows))
    raise KeyError(f"no synthetic StatCan table {table_id}")


def _statcan_rows(vector: str) -> pd.DataFrame:
    """The rows of one vector in the synthetic tables, as the table's CSV gives them."""
    for table_id in _STATCAN_TABLES:
        with zipfile.ZipFile(io.BytesIO(statcan(table_id))) as archive:
            table = pd.read_csv(io.BytesIO(archive.read(f"{table_id}.csv")), low_memory=False)
        rows = table.loc[table["VECTOR"].eq(vector)]
        if not rows.empty:
            return rows
    raise KeyError(f"no synthetic StatCan vector {vector}")


def statcan_wds(params: tuple) -> bytes:
    """Return a WDS answer to getDataFromVectorByReferencePeriodRange: each vector asked, whole whatever its start (the program trims).

    In WDS's own form (``cdn_data._statcan_wds_range``): a list of {"status", "object"}, each object
    with its vectorId and vectorDataPoint list (refPer, value, scalarFactorCode, ...).
    """
    asked = dict(params)["vectorIds"].replace('"', "").split(",")
    answer = []
    for vector_id in asked:
        rows = _statcan_rows(f"v{vector_id}")
        points = [
            {"refPer": ref if len(ref) > 7 else f"{ref}-01", "value": float(value), "decimals": 0,
             "scalarFactorCode": int(scale), "symbolCode": 0, "statusCode": 0}
            for ref, value, scale in zip(rows["REF_DATE"].astype(str), rows["VALUE"], rows["SCALAR_ID"])
        ]
        answer.append({"status": "SUCCESS", "object": {"vectorId": int(vector_id), "vectorDataPoint": points}})
    return json.dumps(answer).encode()


# The UK (batch 3): gilt yields run this far above the U.S. ones; the Bank
# of England's database series: code -> (first day, "B" daily or "ME" month
# end, term in years (0: the short rate, Bank Rate), margin above it).
_UK_OFFSET = 0.6
_IADB_SERIES = {
    "IUDSNPY": ("1993-12-01", "B", 5, 0.0),
    "IUDMNPY": ("1993-11-01", "B", 10, 0.0),
    "IUDLNPY": ("2000-01-04", "B", 20, 0.0),
    "IUDBEDR": ("1975-01-02", "B", 0, 0.25),
    "IUDSOIA": ("1997-01-02", "B", 0, 0.2),  # SONIA (batch 9.1), just under Bank Rate
    "IUMBV34": ("1995-01-31", "ME", 2, 1.2),
    "IUMBV37": ("1995-01-31", "ME", 3, 1.25),
    "IUMBV42": ("1995-01-31", "ME", 5, 1.3),
    "IUMTLMV": ("1995-01-31", "ME", 0, 3.0),
}
# ONS series: CDID -> (unit as its description gives it, first period,
# "stock" or "flow", first and last value in that unit, and whether it has
# months). Flows are per quarter; stocks at the period's end.
_ONS_SERIES = {
    "BKPX": ("m", "1975-01-01", "stock", 53_670, 3_195_774, True),
    "BKPW": ("m", "1975-01-01", "stock", 41_319, 3_181_031, True),
    "MDYT": ("", "1966-01-01", "stock", 7_832, 138_883, False),
    "HF6W": ("bn", "1975-01-01", "stock", 52.1, 2_985.5, True),
    "NMYX": ("m", "1946-01-01", "flow", 135, 33_518, False),
    "NMFX": ("m", "1946-01-01", "flow", 124, 33_146, False),
    "NUGW": ("m", "1946-01-01", "flow", 11, 372, False),
    "YBHA": ("m", "1955-01-01", "flow", 4_645, 787_197, False),
    "EBAQ": (",000", "1955-01-01", "stock", 50_901, 69_628, False),
    # The CPI's 12-month rate (batch 13.1): a rate in percent, months only (``ons``).
    "D7G7": ("%", "1989-01-01", "rate", 2.5, 2.5, True),
    # The CPI's index (batch 13.2), 2015 = 100, monthly from 1988 (``ons``).
    "D7BT": ("Index, base year = 100", "1988-01-01", "stock", 48.4, 144.1, True),
    # The balance of payments (batch 23): the current account's credits and debits, exports and imports, £m a quarter.
    "HBON": ("m", "1955-01-01", "flow", 1_200, 362_755, False),
    "HBOO": ("m", "1955-01-01", "flow", 1_150, 382_687, False),
    "IKBH": ("m", "1955-01-01", "flow", 900, 244_417, False),
    "IKBI": ("m", "1955-01-01", "flow", 950, 257_191, False),
}


def iadb(params: tuple) -> bytes:
    """A Bank of England database CSV (``CSVF=TN``): DATE, then the series asked for, dates "01 Sep 2026"."""
    code = dict(params)["SeriesCodes"]
    first, freq, years, margin = _IADB_SERIES[code]
    dates = pd.bdate_range(first, "2026-10-02") if freq == "B" else pd.date_range(first, "2026-08-31", freq="ME")
    if years == 0:
        values = np.round(np.maximum(_anchors(_SHORT, dates) + _UK_OFFSET - 0.5, 0.1) + margin, 2)
    else:
        values = np.round(_yield_path("uk" + code, dates, years, _UK_OFFSET) + margin, 4)
    lines = [f"DATE,{code}"] + [f"{day:%d %b %Y},{value:g}" for day, value in zip(dates, values)]
    return "\n".join(lines).encode()


# The Bank of England's real spot curve (batch 13.3): years -> its first day,
# and the span with none from (its 20-year's gap, as the Bank's has one).
_UK_REAL_YEARS = {5: "1985-01-02", 7: "1985-01-02", 10: "1985-01-02", 20: "1986-06-09", 30: "2016-01-04"}
_UK_REAL_GAP = ("1988-10-05", "1992-04-29")


def uk_real_curve() -> pd.DataFrame:
    """The real spot curve, a date-indexed column per ``years``, to the last day the synthetic Bank of England has."""
    dates = pd.bdate_range("1985-01-02", "2026-10-02")
    frame = pd.DataFrame(index=dates)
    for years, first in _UK_REAL_YEARS.items():
        frame[years] = np.where(dates >= pd.Timestamp(first), _yield_path(f"ukreal{years}", dates, years, _UK_OFFSET + _REAL_OFFSET), np.nan)
    frame.loc[_UK_REAL_GAP[0] : _UK_REAL_GAP[1], 20] = np.nan
    return frame


def _uk_real_zip(url: str) -> bytes:
    """One of the Bank's yield-curve zips: a workbook of the real curve, its sheet of the spot curve (``uk_data.parse_real_spot_curves``).

    The archive holds the days to the bake's end, the current month's file
    those after it: so the join gives the whole answer, as for the others.
    """
    import openpyxl

    frame = uk_real_curve()
    latest = "latest-yield-curve-data" in url
    frame = frame.loc[frame.index > SYNTHETIC_BAKE_END] if latest else frame.loc[frame.index <= SYNTHETIC_BAKE_END]
    book = openpyxl.Workbook(write_only=True)
    sheet = book.create_sheet("4. spot curve")
    years = [2.5, *frame.columns, 40]
    sheet.append(["years:", *years])
    for day, row in frame.iterrows():
        sheet.append([day.to_pydatetime(), None, *(None if np.isnan(value) else float(value) for value in row), None])
    workbook = io.BytesIO()
    book.save(workbook)
    buffer = io.BytesIO()
    name = "GLC Real daily data current month.xlsx" if latest else "GLC Real daily data_1985 to present.xlsx"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, workbook.getvalue())
    return buffer.getvalue()


def ons(cdid: str) -> bytes:
    """An ONS time series's JSON: its description (with the unit) and lists of months, quarters and years."""
    unit, first, kind, low, high, has_months = _ONS_SERIES[cdid]
    if kind == "rate":
        # Months only, to a tenth, wandering around ``low``, as D7G7 is given.
        months = pd.date_range(first, "2026-09-01", freq="MS")
        rates = np.round(low + _noise("uk" + cdid, len(months), 0.3), 1)
        return json.dumps({
            "description": {"title": f"synthetic {cdid}", "unit": unit, "cdid": cdid},
            "months": [{"date": f"{d.year} {d:%b}".upper(), "value": f"{v:.1f}", "label": ""} for d, v in zip(months, rates)],
            "quarters": [],
            "years": [],
        }).encode()
    quarters = pd.date_range(first, "2026-04-01", freq="QS")
    values = _growth(quarters, low, high, "uk" + cdid)

    def row(date: str, value: float) -> dict:
        return {"date": date, "value": f"{value:.1f}" if unit == "bn" else f"{value:.0f}", "label": date}

    data = {
        "description": {"title": f"synthetic {cdid}", "unit": unit, "cdid": cdid},
        "quarters": [row(f"{d.year} Q{d.quarter}", v) for d, v in zip(quarters, values)],
        "months": [],
        "years": [],
    }
    if has_months:
        months = pd.date_range(first, "2026-08-01", freq="MS")
        monthly = _growth(months, low, high * 1.004, "ukm" + cdid)
        data["months"] = [row(f"{d.year} {d:%b}".upper(), v) for d, v in zip(months, monthly)]
    return json.dumps(data).encode()


# Germany (batch 4): Bund yields run this far below the U.S. ones. The
# Bundesbank's term structure: term code -> (years, first month of the
# end-of-month series, first day of the daily one).
_DE_OFFSET = -1.2
_BUNDESBANK_TERMS = {
    "R01XX": (1, "1972-09", "1997-08-01"), "R02XX": (2, "1972-09", "1997-08-01"), "R03XX": (3, "1972-09", "1997-08-01"),
    "R05XX": (5, "1972-09", "1997-08-01"), "R07XX": (7, "1972-09", "1997-08-01"), "R10XX": (10, "1972-09", "1997-08-01"),
    "R15XX": (15, "1986-06", "1997-08-01"), "R20XX": (20, "1986-06", "1997-08-01"), "R30XX": (30, "2000-01", "2000-08-01"),
}
# The balance of payments' monthly items (batch 23), millions of euros a month: (side, item) -> first and
# last month's level, near the Bundesbank's own (measured 2026-11-11).
_DE_PAYMENTS_LEVELS = {
    ("C", "G"): (4_600, 106_000), ("C", "S"): (860, 37_000), ("C", "IN1"): (590, 21_000), ("C", "IN2"): (100, 5_200),
    ("D", "G"): (3_900, 93_000), ("D", "S"): (1_170, 48_000), ("D", "IN1"): (340, 12_000), ("D", "IN2"): (520, 9_500),
}
# The inflation-linked Federal bonds' real yields (batch 13.3): ISIN -> first day, last day.
_DE_LINKED_BONDS = {
    "DE0001030542": ("2012-03-22", "2023-04-12"), "DE0001030567": ("2015-03-10", "2026-04-10"), "DE0001030559": ("2014-04-08", "2026-10-02"),
    "DE0001030583": ("2021-02-09", "2026-10-02"), "DE0001030575": ("2015-06-12", "2026-10-02"),
}


def bundesbank(url: str) -> bytes:
    """A Bundesbank series CSV: its key and metadata lines, then ``date,value,flag`` ("." on days without a value).

    The same answer from its download (``/rest/download/``) and its SDMX web
    service (``/rest/data/``, batch 19.2), whole, whatever period it is asked
    from (``startPeriod``), as the other baked sources' answers are: the
    program cuts what it asked for.
    """
    key = re.split(r"/rest/(?:download|data)/", url)[1].replace("/", ".", 1)
    if key.startswith("BBDP1."):
        # The consumer price index (batch 13.1), monthly from 1991, 2020 = 100, to a tenth; seasonally
        # adjusted (batch 13.4) under key M.DE.Y...
        months = pd.date_range("1991-01-31", "2026-10-31", freq="ME")
        values = _growth(months, 60.5, 126.4, "de_cpi_sa" if ".M.DE.Y." in key else "de_cpi")
        lines = [f'"",{key},{key}_FLAGS', '"",synthetic consumer price index,', "unit,2020=100,", "unit multiplier,One,"]
        lines += [f"{day:%Y-%m},{value:.1f}," for day, value in zip(months, values)]
        return ("\ufeff" + "\n".join(lines)).encode()
    if key.startswith("BBFBOPV."):
        # A balance of payments item (batch 23), monthly from 1971-01, millions of euros a month, to three places.
        side, item = key.split(".")[8], key.split(".")[9]
        months = pd.date_range("1971-01-31", "2026-08-31", freq="ME")
        values = _growth(months, *_DE_PAYMENTS_LEVELS[(side, item)], "de_bop" + side + item)
        lines = [f'"",{key},{key}_FLAGS', f'"",synthetic Current account / {item} / {side},', "unit,Euro,", "unit multiplier,Millions,"]
        lines += [f"{day:%Y-%m},{value:.3f}," for day, value in zip(months, values)]
        return ("﻿" + "\n".join(lines)).encode()
    if key.startswith("BBSSY."):
        # An inflation-linked bond's real yield (batch 13.3), each business day of its life.
        isin = key.split(".")[5]
        first, last = _DE_LINKED_BONDS[isin]
        dates = pd.bdate_range(first, last)
        values = _yield_path("de" + isin, dates, 10, _DE_OFFSET + _REAL_OFFSET / 2)
        lines = [f'"",{key},{key}_FLAGS', f'"",synthetic {isin} / Yield,', "unit,Prozent,", "unit multiplier,One,"]
        lines += [f"{day:%Y-%m-%d},{value:.4f}," for day, value in zip(dates, values)]
        return ("\ufeff" + "\n".join(lines)).encode()
    frequency, term = key.split(".")[1], key.split(".")[9]
    years, first_month, first_day = _BUNDESBANK_TERMS[term]
    if frequency == "M":
        dates = pd.date_range(first_month, "2026-09-30", freq="ME")
        labels = [f"{day:%Y-%m}" for day in dates]
    else:
        dates = pd.date_range(first_day, "2026-10-02", freq="D")
        labels = [f"{day:%Y-%m-%d}" for day in dates]
    values = np.round(_yield_path("de" + key, dates, years, _DE_OFFSET), 2)
    lines = [f'"",{key},{key}_FLAGS', f'"",synthetic {term} / {frequency},', "BBK_UNIT_ENG,percent,", "unit multiplier,One,"]
    for day, label, value in zip(dates, labels, values):
        weekend = frequency == "D" and day.dayofweek >= 5
        lines.append(f"{label},.,No value available" if weekend else f"{label},{value:.2f},")
    return ("\ufeff" + "\n".join(lines)).encode()


def _ecb_change_days(name: str, margin: float) -> pd.Series:
    """A key rate on the days it changed: the short rate less ``margin``, in quarter points, from 1999."""
    months = pd.date_range("1999-01-01", "2026-09-01", freq="MS")
    path = np.maximum(np.round((_anchors(_SHORT, months) - margin) * 4) / 4, 0.0)
    rates = pd.Series(path, index=months)
    return rates.loc[rates.ne(rates.shift())]


# Every ECB series ``ecb`` answers, as (flow, key, unit): the key rates, EONIA and €STR, the
# three mortgage bands and the annual debt (rates.DE_*, de_data.ECB_ANNUAL_DEBT).
_ECB_SERIES = (
    ("FM", "B.U2.EUR.4F.KR.MRR_FR.LEV", "PCPA"),
    ("FM", "B.U2.EUR.4F.KR.MRR_MBR.LEV", "PCPA"),
    ("EON", "D.EONIA_TO.RATE", "PC"),
    ("EST", "B.EU000A2X2A25.WT", "PC"),
    ("MIR", "M.DE.B.A2C.I.R.A.2250.EUR.N", "PCPA"),
    ("MIR", "M.DE.B.A2C.O.R.A.2250.EUR.N", "PCPA"),
    ("MIR", "M.DE.B.A2C.P.R.A.2250.EUR.N", "PCPA"),
    ("MIR", "M.DE.B.A2C.F.R.A.2250.EUR.N", "PCPA"),  # Germany's variable rate (9.8, decision 176)
    ("GFS", "A.N.DE.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    # The euro-area nations' after Germany (batch 14.3: rates.EURO_MORTGAGE_SERIES, euro_data's ecb_annual_debt), baked
    # from France's fourth stage.
    *(series for geo, euro in _EURO.items() for series in (
        *(("MIR", f"M.{geo}.B.A2C.{band}.R.A.2250.EUR.N", "PCPA") for band in euro.mortgage_bands),
        ("GFS", f"A.N.{geo}.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    )),
)


def ecb(url: str) -> bytes:
    """An ECB csvdata answer: one row per observation, KEY, TIME_PERIOD, OBS_VALUE, its unit and multiplier.

    Whole, whatever period it is asked from (``startPeriod``, batch 19.2),
    as the other baked sources' answers are: the program cuts what it asked for.
    """
    flow, key = url.split("/service/data/")[1].split("/", 1)
    unit_column, unit, multiplier = "UNIT", "PCPA", 0
    if flow == "FM":
        rates = _ecb_change_days("ecb", 1.0)
        variable = (rates.index >= "2000-06-28") & (rates.index < "2008-10-15")
        if key.endswith("MRR_MBR.LEV"):
            chosen = pd.concat([pd.Series([rates.asof(pd.Timestamp("2000-06-28"))], index=[pd.Timestamp("2000-06-28")]),
                                rates.loc[variable & (rates.index > "2000-06-28")],
                                pd.Series([np.nan], index=[pd.Timestamp("2008-10-15")])])
        else:
            chosen = pd.concat([rates.loc[~variable & (rates.index < "2000-06-28")],
                                pd.Series([rates.asof(pd.Timestamp("2008-10-15"))], index=[pd.Timestamp("2008-10-15")]),
                                rates.loc[rates.index > "2008-10-15"]])
        periods, values = [f"{day:%Y-%m-%d}" for day in chosen.index], list(chosen.to_numpy())
    elif flow in ("EON", "EST"):
        # The overnight rates (batch 9.1): EONIA 1999-2021, €STR from 2019-10,
        # 0.085 below it while both were published; in percent ("PC").
        first, last = ("1999-01-04", "2021-12-31") if flow == "EON" else ("2019-10-01", "2026-09-30")
        days = pd.bdate_range(first, last)
        path = np.round(_anchors(_SHORT, days) - 1.1 + _noise("ecb" + flow, len(days), 0.01) - (0.085 if flow == "EST" else 0.0), 3)
        periods, values, unit = [f"{day:%Y-%m-%d}" for day in days], list(path), "PC"
    elif flow == "MIR":
        months = pd.date_range("2000-01-31", "2026-08-31", freq="ME")
        band = {"F": 1, "I": 3, "O": 10, "P": 20}[key.split(".")[4]]  # F: the variable rate (Portugal's 14.3, Germany's and France's 9.8)
        offset = _EURO[key.split(".")[1]].offset if key.split(".")[1] in _EURO else _DE_OFFSET  # a euro-area nation's bands (batch 14.3)
        values = list(np.round(_yield_path("demir" + key, months, band, offset) + 1.4, 2))
        periods = [f"{day:%Y-%m}" for day in months]
    elif flow == "GFS" and key.split(".")[2] in _EURO:
        # A euro-area nation's year ends (batch 14.3), 1995 to 1999 and on; from 2000 on the Eurostat quarters' path.
        euro = _EURO[key.split(".")[2]]
        early = pd.date_range("1995-12-31", "1999-12-31", freq="YE")
        quarters = pd.date_range("2000-03-31", "2026-03-31", freq="QE")
        _first, low, high = euro.eurostat_paths["gov_10q_ggdebt"]
        later = pd.Series(_growth(quarters, low, high, f"{euro.key}_debt"), index=quarters).loc[lambda q: q.index.month == 12]
        years = early.append(later.index)
        values = list(np.round(np.concatenate([_growth(early, *euro.gfs_early_path, f"{euro.key}_gfs_a"), later.to_numpy()]), 0))
        periods, unit_column, unit, multiplier = [str(day.year) for day in years], "UNIT_MEASURE", "XDC", 6
    elif flow == "GFS":
        # Unification doubled the debt in the 1990s; from 2000 the year-ends
        # follow the Eurostat quarters' path (equal on real data).
        early = pd.date_range("1991-12-31", "1999-12-31", freq="YE")
        quarters = pd.date_range("2000-03-31", "2026-03-31", freq="QE")
        later = pd.Series(_growth(quarters, 1_265_509, 2_902_035, "de_debt"), index=quarters).loc[lambda q: q.index.month == 12]
        years = early.append(later.index)
        values = list(np.round(np.concatenate([_growth(early, 618_218, 1_253_598, "de_gfs_a"), later.to_numpy()]), 0))
        periods, unit_column, unit, multiplier = [str(day.year) for day in years], "UNIT_MEASURE", "XDC", 6
    else:
        raise KeyError(f"no synthetic ECB series {flow}.{key}")
    frame = pd.DataFrame({"KEY": f"{flow}.{key}", "TIME_PERIOD": periods, "OBS_VALUE": values,
                          unit_column: unit, "UNIT_MULT": str(multiplier)})
    return frame.to_csv(index=False).encode()


def bpstat_series(series_id: str) -> pd.Series:
    """One synthetic BPstat daily yield (9.13): business days from its first day to 2026-09-30, its gaps left out."""
    euro, (years, first, gaps) = _BPSTAT_YIELDS[series_id]
    dates = pd.bdate_range(first, "2026-09-30")
    for start, end in gaps:
        dates = dates[(dates < start) | (dates > end)]
    return pd.Series(_yield_path(series_id, dates, years, euro.offset), index=dates)


def webstat_series(key: str) -> pd.Series:
    """One synthetic Webstat daily yield (9.14): business days from its first day to 2026-09-30, its gaps left out."""
    euro, (years, first, gaps) = _WEBSTAT_YIELDS[key]
    dates = pd.bdate_range(first, "2026-09-30")
    for start, end in gaps:
        dates = dates[(dates < start) | (dates > end)]
    return pd.Series(_yield_path(key, dates, years, euro.offset), index=dates)


def webstat(params: tuple) -> bytes:
    """Webstat's export of one series (``euro_data.parse_webstat``): a row for each calendar day, null on a day without
    a value (each weekend and gap), as Webstat's; from the day its query names, or whole."""
    where = dict(params)["where"]
    match = re.fullmatch(r'series_key="([^"]+)"(?: and time_period_start>=date\'(\d{4}-\d{2}-\d{2})\')?', where)
    if match is None:
        raise KeyError(f"no synthetic Webstat answer for {where!r}")
    key, start = match[1], match[2]
    values = webstat_series(key)
    days = pd.date_range(values.index[0], values.index[-1], freq="D")
    if start is not None:
        days = days[days >= start]
    return json.dumps([
        {"series_key": key, "time_period": f"{day:%Y-%m-%d}",
         "obs_value": float(values[day]) if day in values.index else None}
        for day in days
    ]).encode()


def bpstat(params: tuple) -> bytes:
    """BPstat's JSON-stat 2.0 answer for one series (``euro_data.parse_bpstat``), whole whatever day it is asked from."""
    series_id = dict(params)["series_ids"]
    values = bpstat_series(series_id)
    one = {
        "40": ("Periodicity", "4263", "Daily"), "45": ("Residual maturity", "0", "term"),
        "70": ("Unit of measure", "3327", "Percentage"),
    }
    dimension = {dim: {"label": label, "category": {"index": [code], "label": {code: name}}}
                 for dim, (label, code, name) in one.items()}
    dimension["reference_date"] = {"label": "Date", "category": {"index": [f"{day:%Y-%m-%d}" for day in values.index]}}
    return json.dumps({
        "version": "2.0", "class": "dataset", "id": [*one, "reference_date"], "size": [1, 1, 1, len(values)],
        "dimension": dimension, "value": [float(value) for value in values], "status": ["F"] * len(values),
        "extension": {"num_series": 1, "series": [{"id": int(series_id)}]},
    }).encode()


def _jsonstat(label: str, dims: list[tuple[str, list[str]]], value) -> bytes:
    """A JSON-stat 2.0 dataset over ``dims`` (the last is time); ``value(categories)`` gives each cell (None: no value)."""
    sizes = [len(codes) for _dim, codes in dims]
    values = {}
    for flat, combo in enumerate(itertools.product(*[codes for _dim, codes in dims])):
        cell = value(dict(zip([dim for dim, _codes in dims], combo)))
        if cell is not None:
            values[str(flat)] = round(float(cell), 1)
    return json.dumps({
        "version": "2.0", "class": "dataset", "label": label, "id": [dim for dim, _codes in dims], "size": sizes,
        "dimension": {dim: {"category": {"index": {code: i for i, code in enumerate(codes)}}} for dim, codes in dims},
        "value": values,
    }).encode()


# Eurostat: the German series, first and last value (millions of euros,
# thousands of persons, persons) and each sector's share of the total.
_DE_SECTOR_SHARES = {"S13": 1.0, "S1311": 0.70, "S1312": 0.235, "S1313": 0.07, "S1314": 0.005}
_EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
# Every Eurostat series the program reads, by its baked file's name (de_data.eurostat_code): its
# dataset, the categories chosen and the nation (de_data.EUROSTAT_SERIES_READ_BY_GEO; batch 19.2,
# France's from batch 14.3's fourth stage).
_EUROSTAT_SERIES = {
    **{f"{dataset}.{sector}": (dataset, {"sector": sector}, "DE")
       for dataset in ("gov_10q_ggdebt", "gov_10q_ggnfa") for sector in ("S13", "S1311", "S1312", "S1313")},
    "gov_10dd_edpt1.D41PAY.S13": ("gov_10dd_edpt1", {"sector": "S13", "na_item": "D41PAY"}, "DE"),
    "namq_10_gdp": ("namq_10_gdp", {}, "DE"),
    "namq_10_pe": ("namq_10_pe", {}, "DE"),
    "demo_pjan": ("demo_pjan", {}, "DE"),
    **{code: series for geo in _EURO for code, series in (
        *((f"gov_10q_ggdebt.{geo}.{sector}", ("gov_10q_ggdebt", {"sector": sector}, geo)) for sector in ("S13", "S1311", "S1313")),
        (f"gov_10q_ggnfa.{geo}.S13", ("gov_10q_ggnfa", {"sector": "S13"}, geo)),
        *((f"gov_10a_main.{geo}.{sector}", ("gov_10a_main", {"sector": sector}, geo)) for sector in ("S1311", "S1313")),
        (f"namq_10_gdp.{geo}", ("namq_10_gdp", {}, geo)),
        (f"namq_10_pe.{geo}", ("namq_10_pe", {}, geo)),
        (f"prc_hicp_minr.{geo}", ("prc_hicp_minr", {}, geo)),
        *((f"{dataset}.{item}.{geo}.{flow}", (dataset, {"bop_item": item, "stk_flow": flow}, geo))
          for dataset in ("bop_c6_q", "bop_c6_m") for item in ("CA", "GS") for flow in ("CRE", "DEB")),
    )},
    # Italy's 10-year before the OECD's (decision 178); a tree whose de_data has no such query skips it.
    **{f"irt_lt_mcby_m.{geo}": ("irt_lt_mcby_m", {}, geo) for geo, euro in _EURO.items() if euro.yield_history_path},
}


def _euro_payments(euro: _EuroSynthetic, dataset: str, query: dict) -> bytes:
    """A euro-area nation's ``bop_c6_q`` (quarters from its first to 2026-Q2) or ``bop_c6_m`` (months from its first to 2026-09, each a third of its quarter's path), the query's items and flows (batch 14.3's second stage)."""
    items, flows = list(query["bop_item"]), list(query["stk_flow"])
    quarters = pd.period_range(euro.payments_from, "2026Q3", freq="Q")
    paths = {
        key: dict(zip(quarters, _growth(quarters.to_timestamp(how="end"), low, high, f"{euro.key}_bop_{key[0]}_{key[1]}")))
        for key, (low, high) in euro.payments_paths.items()
    }
    if dataset == "bop_c6_q":
        periods, frequency, share = list(quarters[:-1]), "Q", 1.0
        times = [f"{p.year}-Q{p.quarter}" for p in periods]
    else:
        periods, frequency, share = list(pd.period_range(euro.months_from, "2026-09", freq="M")), "M", 1 / 3
        times = [f"{p.year}-{p.month:02d}" for p in periods]
    by_time = dict(zip(times, periods))
    dims = [
        ("freq", [frequency]), ("currency", [query["currency"]]), ("bop_item", items), ("sector10", [query["sector10"]]),
        ("sectpart", [query["sectpart"]]), ("stk_flow", flows), ("partner", [query["partner"]]), ("geo", [euro.geo]), ("time", times),
    ]
    return _jsonstat(dataset, dims, lambda c: paths[(c["bop_item"], c["stk_flow"])][by_time[c["time"]].asfreq("Q")] * share)


def eurostat(url: str, params: tuple) -> bytes:
    """A Eurostat JSON-stat answer for the query the program sends (``de_data.EUROSTAT_QUERIES``).

    Whole, whatever period it is asked from (``sinceTimePeriod``, batch 19.2),
    as the other baked sources' answers are: the program cuts what it asked for.
    """
    dataset = url.rstrip("/").rsplit("/", 1)[1]
    query = dict(params)
    unit = query.get("unit", "NR")
    quarters = lambda first, last: [f"{p.year}-Q{p.quarter}" for p in pd.period_range(first, last, freq="Q")]  # noqa: E731
    fixed = [(dim, [query[dim]]) for dim in ("na_item", "s_adj", "age", "sex", "coicop18") if dim in query]
    geo = query.get("geo", "DE")
    common = [("freq", ["Q"]), ("unit", [unit]), *fixed, ("geo", [geo])]

    def path(name: str, periods: list[str], first: float, last: float) -> dict[str, float]:
        dates = pd.DatetimeIndex([pd.Period(period.replace("-", ""), freq="Q" if "Q" in period else "Y").end_time.normalize() for period in periods])
        return dict(zip(periods, _growth(dates, first, last, name)))

    if geo in _EURO:
        # A euro-area nation after Germany (batch 14.3): its own paths, the same shapes as Germany's answers.
        euro = _EURO[geo]
        shares = euro.sector_shares
        if dataset == "irt_lt_mcby_m" and euro.yield_history_path:
            # The convergence-criterion yield (decision 178): monthly from 1980-01, its measure in int_rt.
            months = pd.period_range("1980-01", "2026-09", freq="M")
            times = [f"{month.year}-{month.month:02d}" for month in months]
            level = dict(zip(times, np.round(_growth(months.to_timestamp(), *euro.yield_history_path, f"{euro.key}_mcby"), 3)))
            dims = [("freq", ["M"]), ("int_rt", ["MCBY"]), ("geo", [geo]), ("time", times)]
            return _jsonstat("EMU convergence criterion series", dims, lambda c: level[c["time"]])
        if dataset == "prc_hicp_minr":
            months = pd.period_range("1996-01", "2026-09", freq="M")
            times = [f"{month.year}-{month.month:02d}" for month in months]
            index = dict(zip(times, _growth(months.to_timestamp(), *euro.hicp_path, f"{euro.key}_hicp")))
            return _jsonstat("HICP", [("freq", ["M"]), ("unit", [unit]), *fixed, ("geo", [geo]), ("time", times)], lambda c: index[c["time"]])
        if dataset == "gov_10a_main":
            # Each subsector's yearly interest (its levels' interest), 1995 to 2025.
            times = [str(year) for year in range(1995, 2026)]
            yearly = path(f"{euro.key}_gov_10a_main", times, *euro.yearly_interest_path)
            dims = [("freq", ["A"]), ("unit", [unit]), ("sector", list(shares)), *fixed, ("geo", [geo]), ("time", times)]
            return _jsonstat(dataset, dims, lambda c: yearly[c["time"]] * shares[c["sector"]])
        if dataset in ("bop_c6_q", "bop_c6_m"):
            return _euro_payments(euro, dataset, query)
        first, low, high = euro.eurostat_paths[dataset]
        times = quarters(first, "2026Q2" if dataset.startswith("namq") else "2026Q1")
        total = path(f"{euro.key}_{dataset}", times, low, high)
        if dataset.startswith("gov_10q"):
            dims = [*common[:2], ("sector", list(shares)), *common[2:], ("time", times)]
            return _jsonstat(dataset, dims, lambda c: total[c["time"]] * shares[c["sector"]])
        return _jsonstat(dataset, [*common, ("time", times)], lambda c: total[c["time"]])
    if dataset == "gov_10q_ggdebt":
        times = quarters("2000Q1", "2026Q1")
        total = path("de_debt", times, 1_265_509, 2_902_035)
        dims = [*common[:2], ("sector", list(_DE_SECTOR_SHARES)), *common[2:], ("time", times)]
        return _jsonstat("Quarterly government debt", dims, lambda c: total[c["time"]] * _DE_SECTOR_SHARES[c["sector"]] * (1.01 if c["sector"] != "S13" else 1))
    if dataset == "gov_10q_ggnfa":
        times = quarters("2002Q1", "2026Q1")
        total = path("de_interest", times, 16_304, 12_135)
        dims = [*common[:2], ("sector", list(_DE_SECTOR_SHARES)), *common[2:], ("time", times)]
        return _jsonstat("Quarterly non-financial accounts", dims, lambda c: total[c["time"]] * _DE_SECTOR_SHARES[c["sector"]])
    if dataset == "gov_10dd_edpt1":
        times = [str(year) for year in range(1995, 2026)]
        interest = path("de_interest_a", times, 69_498, 49_544)
        dims = [("freq", ["A"]), ("unit", [unit]), ("sector", ["S13"]), ("na_item", ["D41PAY", "GD"]), ("geo", ["DE"]), ("time", times)]
        return _jsonstat("Government deficit/surplus, debt", dims, lambda c: interest[c["time"]] if c["na_item"] == "D41PAY" else None)
    if dataset == "namq_10_gdp":
        times = quarters("1991Q1", "2026Q2")
        gdp = path("de_gdp", times, 358_976, 1_151_030)
        return _jsonstat("GDP", [*common, ("time", times)], lambda c: gdp[c["time"]])
    if dataset == "namq_10_pe":
        times = quarters("1991Q1", "2026Q2")
        people = path("de_pop_q", times, 79_777, 83_337)
        return _jsonstat("Population", [*common, ("time", times)], lambda c: people[c["time"]])
    if dataset == "demo_pjan":
        times = [str(year) for year in range(1960, 2026)]
        # West Germany to 1990, then unified Germany: two paths, a step between.
        west = path("de_pop_w", times, 55_257_088, 62_679_035 * 62_679_035 / 55_257_088)
        unified = path("de_pop_u", times, 75_000_000, 83_577_140)
        dims = [("freq", ["A"]), ("unit", ["NR"]), *fixed, ("geo", ["DE"]), ("time", times)]
        return _jsonstat("Population on 1 January", dims, lambda c: west[c["time"]] if int(c["time"]) <= 1990 else unified[c["time"]])
    raise KeyError(f"no synthetic Eurostat dataset {dataset}")


# Japan (batch 14.3, decision 190, ``ratesplot.jp_data``): its yields, call rate, flow of funds, balance of payments and
# consumer prices, each in its source's own layout, its rates well below the U.S.' as Japan's are.
_JP_OFFSET = -2.5
_JP_TERMS = {"1Y": (1, "1974-09-24"), "2Y": (2, "1974-09-24"), "3Y": (3, "1974-09-24"), "4Y": (4, "1974-09-24"),
             "5Y": (5, "1974-09-24"), "6Y": (6, "1974-09-24"), "7Y": (7, "1974-09-24"), "8Y": (8, "1974-09-24"),
             "9Y": (9, "1974-09-24"), "10Y": (10, "1986-07-05"), "15Y": (15, "1991-08-30"), "20Y": (20, "1986-12-01"),
             "25Y": (25, "2004-03-22"), "30Y": (30, "1999-09-02"), "40Y": (40, "2007-11-06")}
# The Ministry's history file runs to the last month's end, its current month's file from the month's first day.
_MOF_CURRENT_FROM = pd.Timestamp("2026-09-01")
_FF_SECTOR_SHARES = {"0": 1.0, "1": 0.86, "2": 0.13}
_FF_ITEM_SHARES = {"200": 0.3, "300": 0.7}
_BOJ_PAYMENTS = {  # 100 million yen a month, first and last
    "BPBP6JYNEX": (40_000.0, 105_000.0), "BPBP6JYNIM": (32_000.0, 108_000.0), "BPBP6JYNSC": (5_000.0, 26_000.0),
    "BPBP6JYNSD": (6_500.0, 29_000.0), "BPBP6JYNPIC": (5_500.0, 45_000.0), "BPBP6JYNPID": (2_000.0, 14_000.0),
    "BPBP6JYNSIC": (300.0, 3_000.0), "BPBP6JYNSID": (1_000.0, 6_000.0),
}


def _jgb_frame() -> pd.DataFrame:
    """The Ministry's every term on every business day from 1974-09-24 to 2026-09-30, none before its first day."""
    days = pd.bdate_range("1974-09-24", "2026-09-30")
    frame = pd.DataFrame(index=days)
    for term, (years, first) in _JP_TERMS.items():
        values = pd.Series(_yield_path(f"JGB{term}", days, years, _JP_OFFSET), index=days)
        frame[term] = values.where(days >= pd.Timestamp(first))
    return frame


def mof(url: str) -> bytes:
    """One of the Ministry's two CSV files (``jp_data.parse_mof_csv``): a title line, the header, a row a business day,
    "-" before a term's first day; the history to 2026-08-31, the current month's file 2026-09."""
    frame = _jgb_frame()
    current = url.endswith("/jgbcme.csv")
    frame = frame.loc[frame.index >= _MOF_CURRENT_FROM] if current else frame.loc[frame.index < _MOF_CURRENT_FROM]
    lines = ["Interest Rate (synthetic)," + "," * (len(_JP_TERMS) - 1), "Date," + ",".join(_JP_TERMS)]
    for day, row in frame.iterrows():
        cells = ["-" if pd.isna(value) else f"{value:.3f}" for value in row]
        lines.append(f"{day.year}/{day.month}/{day.day}," + ",".join(cells))
    if current:
        lines += ["," * len(_JP_TERMS), '"  (a note, as the Ministry ends its current month\'s file with one)"']
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def boj_values(code: str) -> tuple[pd.Series, str]:
    """One synthetic Bank of Japan series and its frequency as the Bank names it."""
    if code == "STRDCLUCON":
        dates = pd.bdate_range("1998-01-05", "2026-09-30")
        values = np.round(np.maximum(_anchors(_SHORT, dates) + _JP_OFFSET, -0.08), 3)
        return pd.Series(values, index=dates), "DAILY"
    if code in ("STRACLUCON", "STRACLCOON"):
        dates = pd.date_range("1985-07-01" if code == "STRACLUCON" else "1960-01-01", "2026-09-01", freq="MS")
        margin = 0.05 if code == "STRACLCOON" else 0.0
        return pd.Series(np.round(np.maximum(_anchors(_SHORT, dates) + _JP_OFFSET + margin, -0.08), 3), index=dates), "MONTHLY"
    if code.startswith("FOF_FF"):
        share = _FF_SECTOR_SHARES[code[-5]] * _FF_ITEM_SHARES[code[-3:]]
        if code.startswith("FOF_FFAS"):
            dates = pd.date_range("1997-10-01", "2026-04-01", freq="QS")
            return pd.Series(np.round(_growth(dates, 4_500_000.0 * share, 12_700_000.0 * share, code)), index=dates), "QUARTERLY"
        dates = pd.date_range("1979-01-01", "2025-01-01", freq="YS")
        return pd.Series(np.round(_growth(dates, 1_000_000.0 * share, 12_600_000.0 * share, code)), index=dates), "ANNUAL(MAR)"
    first, last = _BOJ_PAYMENTS[code]
    dates = pd.date_range("1996-01-01", "2026-09-01", freq="MS")
    return pd.Series(np.round(_growth(dates, first, last, code), 3), index=dates), "MONTHLY"


def _boj_period(day: pd.Timestamp, frequency: str) -> str:
    """A period as the Bank writes it: a day YYYYMMDD, a month YYYYMM, a quarter YYYYQQ, a year YYYY."""
    return {"DAILY": f"{day:%Y%m%d}", "MONTHLY": f"{day:%Y%m}", "QUARTERLY": f"{day:%Y}{day.quarter:02d}"}.get(frequency, f"{day:%Y}")


def boj(params: tuple) -> bytes:
    """The Bank's ``getDataCode`` answer for the codes asked (``jp_data.parse_boj_csv``), whole whatever period it is asked from."""
    asked = dict(params)
    lines = ["STATUS,200", "MESSAGEID,M181000I", "MESSAGE,Successfully completed", f"PARAMETER,DB,{asked['db']}", "NEXTPOSITION,",
             "SERIES_CODE,NAME_OF_TIME_SERIES,UNIT,FREQUENCY,CATEGORY,LAST_UPDATE,SURVEY_DATES,VALUES"]
    for code in asked["code"].split(","):
        values, frequency = boj_values(code)
        lines += [f"{code},synthetic {code},units,{frequency},synthetic,20260930,{_boj_period(day, frequency)},{value}"
                  for day, value in values.items()]
    return ("\n".join(lines) + "\n").encode()


def imf_cpi() -> bytes:
    """The IMF's SDMX answer of Japan's consumer price index (``jp_data.parse_imf_monthly``), monthly 1955-01 to 2026-09, to one decimal."""
    dates = pd.date_range("1955-01-01", "2026-09-01", freq="MS")
    values = np.round(_growth(dates, 15.0, 114.5, "JPN.CPI"), 1)
    observations = "".join(f'<Obs TIME_PERIOD="{day:%Y}-M{day:%m}" OBS_VALUE="{value}"/>' for day, value in zip(dates, values))
    return ('<?xml version="1.0" encoding="UTF-8"?><message:StructureSpecificData '
            'xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"><message:DataSet>'
            f'<Series>{observations}</Series></message:DataSet></message:StructureSpecificData>').encode()


def synth(key: tuple):
    """Return the synthetic answer to one download-cache key; KeyError for a source with none."""
    if key[0] == "fred":
        return fred(key[1])
    tag, url, params = key
    if "bankofcanada.ca/valet" in url:
        return _response(valet(url, params))
    if "statcan.gc.ca/n1/tbl/csv/" in url:
        return _response(statcan(url.rsplit("/", 1)[-1].split("-")[0]))
    if "statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange" in url:
        return _response(statcan_wds(params))
    if "bankofengland.co.uk/boeapps/database" in url:
        return _response(iadb(params))
    if "bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/" in url:
        return _response(_uk_real_zip(url))
    if "ons.gov.uk" in url:
        return _response(ons(url.split("/timeseries/")[1].split("/")[0].upper()))
    if "api.statistiken.bundesbank.de/rest/download/" in url or "api.statistiken.bundesbank.de/rest/data/" in url:
        return _response(bundesbank(url))
    if "data-api.ecb.europa.eu/service/data/" in url:
        return _response(ecb(url))
    if "ec.europa.eu/eurostat/api/dissemination" in url:
        return _response(eurostat(url, params))
    if "bpstat.bportugal.pt/data/v1/" in url:
        return _response(bpstat(params))
    if "webstat.banque-france.fr/api/explore/" in url:
        return _response(webstat(params))
    if "mof.go.jp/english/policy/jgbs/" in url:
        return _response(mof(url))
    if "stat-search.boj.or.jp/api/v1/getDataCode" in url:
        return _response(boj(params))
    if "api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI/JPN" in url:
        return _response(imf_cpi())
    raise KeyError(f"no synthetic source for {key!r}")


def _refused(*_args, **_kwargs):
    raise requests.ConnectionError("synthetic data only: real requests are refused")


# Batch 19.2: the program draws the Bank of England's series, the Bank of
# Canada's, FRED's, the ECB's, Eurostat's, the ONS's, the Bundesbank's and Statistics Canada's from their
# baked history (ratesplot/data/boe/, data/boc/, data/fred/, data/ecb/, data/eurostat/, data/ons/,
# data/bbk/, data/statcan/) and takes from the sources only the recent part
# (the ONS is asked for the whole series, which it always sends). With synthetic answers the bake must
# be synthetic too, or a chart would join the real history to a made-up
# recent part. So each series'
# synthetic answer is baked to this date, in a folder of its own, and the
# program reads it from there: the join is drawn, and gives exactly the
# whole synthetic answer, which an older tree (no bake) draws, so the two
# compare byte for byte. ``synth`` answers the recent part with the whole
# series, which the program trims, as a source that ignores the date asked
# for is.
SYNTHETIC_BAKE_END = pd.Timestamp("2026-07-15")


def install_synthetic_bake(folder: Path) -> bool:
    """Bake the synthetic Bank of England, Bank of Canada, FRED, ECB, Eurostat, ONS, Bundesbank and Statistics Canada series, to ``SYNTHETIC_BAKE_END``, into ``folder``, and have the program read its bake there.

    Through the program's own ``baked.write_series``. Returns False, changing
    nothing, for a tree without a bake (before batch 19.2). A tree that bakes
    fewer sources reads none of the others' files, and draws them as before.
    """
    try:
        baked = importlib.import_module("ratesplot.baked")
    except ModuleNotFoundError:
        return False
    uk_data = importlib.import_module("ratesplot.uk_data")
    http = importlib.import_module("ratesplot.http")

    def bake(source: str, code: str, whole: pd.Series) -> None:
        series = whole.dropna().rename(code)
        baked.write_series(folder / source / f"{code}.csv", series.loc[:SYNTHETIC_BAKE_END], f"synthetic {code}, tools/synthetic_sources.py")

    for code in _IADB_SERIES:
        bake(uk_data.BOE_BAKED_SOURCE, code, uk_data.parse_iadb_csv(iadb((("SeriesCodes", code),)).decode())[code])
    # The real spot curve (batch 13.3; a tree before it reads no such file).
    if hasattr(uk_data, "UK_REAL_TERMS"):
        curve = uk_real_curve()
        for column, years in uk_data.UK_REAL_TERMS.items():
            bake(uk_data.BOE_BAKED_SOURCE, uk_data.real_curve_code(column), curve[years])
    valet_url = "https://www.bankofcanada.ca/valet/observations/"
    group = http.parse_boc_csv(valet(f"{valet_url}group/bond_yields_benchmark/csv", ()).decode())
    for code in group.columns:
        bake("boc", code, pd.to_numeric(group[code], errors="coerce"))
    for code in _VALET_SERIES:
        bake("boc", code, pd.to_numeric(http.parse_boc_csv(valet(f"{valet_url}{code}/csv", ()).decode()).iloc[:, 0], errors="coerce"))
    for code in _FRED_IDS:
        bake("fred", code, fred(code).set_index("DATE")[code])
    for code in _BPSTAT_YIELDS:  # Portugal's daily yields (9.13)
        bake("bpstat", code, bpstat_series(code))
    for code in _WEBSTAT_YIELDS:  # France's daily yields (9.14)
        bake("webstat", code, webstat_series(code))
    de_data = importlib.import_module("ratesplot.de_data")
    for flow, key, unit in _ECB_SERIES:
        answer = ecb(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}").decode()
        bake("ecb", f"{flow}.{key}", de_data.parse_ecb_csv(answer, f"{flow}.{key}", unit))
    for code, (dataset, chosen, geo) in _EUROSTAT_SERIES.items():
        if dataset not in de_data.EUROSTAT_QUERIES:
            continue  # a tree before the dataset was read (France's, batch 14.3)
        params, unit = de_data.EUROSTAT_QUERIES[dataset]
        answer = json.loads(eurostat(f"{_EUROSTAT_URL}{dataset}", tuple(sorted((params | {"geo": geo}).items()))))
        # The unit's dimension where it is not ``unit`` (the balance of payments'; a tree before 9.4 takes no such argument).
        dimension = (de_data.EUROSTAT_UNIT_DIMENSIONS.get(dataset, "unit"),) if hasattr(de_data, "EUROSTAT_UNIT_DIMENSIONS") else ()
        bake("eurostat", code, de_data.parse_jsonstat(answer, unit, *dimension, **chosen))
    # The frequency the program reads of each (uk_data.ONS_SERIES_READ): months where the synthetic series has them.
    for cdid, (*_spec, has_months) in _ONS_SERIES.items():
        bake("ons", cdid, uk_data.parse_ons_series(json.loads(ons(cdid)), cdid, "months" if has_months else "quarters"))
    # The Bundesbank's term structure, each term's end-of-month and daily series (a tree before 19.2's
    # Bundesbank stage has no term_structure_key, and reads no Bundesbank file).
    if hasattr(de_data, "term_structure_key"):
        flow = de_data.BUNDESBANK_TERM_STRUCTURE_FLOW
        for column in de_data.DE_YIELD_SERIES:
            for frequency in de_data.TERM_STRUCTURE_FREQUENCIES:
                key = de_data.term_structure_key(column, frequency)
                answer = bundesbank(f"https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}").decode()
                bake(de_data.BUNDESBANK_BAKED_SOURCE, f"{flow}.{key}", de_data.parse_bundesbank_csv(answer))
    # The consumer price indexes (batch 13.1, the seasonally adjusted one 13.4; a tree before either reads no
    # such file).
    for name in ("DE_CPI_SERIES", "DE_CPI_SA_SERIES"):
        if hasattr(de_data, name):
            flow, key = getattr(de_data, name)
            answer = bundesbank(f"https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}").decode()
            units = de_data._BUNDESBANK_UNITS[(flow, key)]
            bake(de_data.BUNDESBANK_BAKED_SOURCE, f"{flow}.{key}", de_data.parse_bundesbank_csv(answer, units))
    # The inflation-linked bonds' real yields (batch 13.3; a tree before it reads no such file).
    if hasattr(de_data, "DE_LINKED_BONDS"):
        for isin in de_data.DE_LINKED_BONDS:
            flow, key = de_data.DE_LINKED_BOND_FLOW, de_data.linked_bond_key(isin)
            answer = bundesbank(f"https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}").decode()
            bake(de_data.BUNDESBANK_BAKED_SOURCE, f"{flow}.{key}", de_data.parse_bundesbank_csv(answer))
    # The balance of payments' items (batch 23's third stage; a tree before it reads no such file).
    for flow, key in getattr(de_data, "DE_PAYMENTS_SERIES", {}).values():
        answer = bundesbank(f"https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}").decode()
        units, multiplier = de_data._BUNDESBANK_UNITS[(flow, key)], de_data._BUNDESBANK_MULTIPLIERS[(flow, key)]
        bake(de_data.BUNDESBANK_BAKED_SOURCE, f"{flow}.{key}", de_data.parse_bundesbank_csv(answer, units, multiplier))
    # Statistics Canada's live tables, each vector read, selected by the program's own labels (a tree before
    # 19.2's Statistics Canada stage has no STATCAN_SERIES_READ, and reads no Statistics Canada file).
    cdn_data = importlib.import_module("ratesplot.cdn_data")
    if hasattr(cdn_data, "STATCAN_SERIES_READ"):
        for table_id in cdn_data.STATCAN_SERIES_READ:
            with zipfile.ZipFile(io.BytesIO(statcan(table_id))) as archive:
                table = pd.read_csv(io.BytesIO(archive.read(f"{table_id}.csv")), low_memory=False)
            for vector, values in cdn_data._statcan_vectors(table, table_id).items():
                bake(cdn_data.STATCAN_BAKED_SOURCE, vector, values)
    # Japan's (batch 14.3; a tree before it reads no such file).
    try:
        jp_data = importlib.import_module("ratesplot.jp_data")
    except ModuleNotFoundError:
        jp_data = None
    if jp_data is not None:
        terms = pd.concat([jp_data.parse_mof_csv(mof("https://www.mof.go.jp/historical/jgbcme_all.csv")),
                           jp_data.parse_mof_csv(mof("https://www.mof.go.jp/jgbcme.csv"))])
        for code in jp_data.JP_YIELD_COLUMNS.values():
            bake(jp_data.MOF_BAKED_SOURCE, code, terms[code])
        for db, code in jp_data.BOJ_SERIES_READ:
            bake(jp_data.BOJ_BAKED_SOURCE, code, jp_data.parse_boj_csv(boj((("code", code), ("db", db))))[0][code])
        bake(jp_data.IMF_BAKED_SOURCE, jp_data.IMF_CPI_KEY, jp_data.parse_imf_monthly(imf_cpi(), jp_data.IMF_CPI_KEY))
    baked.DATA_FOLDER = folder
    baked.forget_read_files()
    return True


def install_synthetic_cache(http_module, cache_dir: Path) -> bool:
    """Answer every download from ``synth`` (kept as pickles in ``cache_dir``), and refuse every real request.

    The same interface as ``regress_charts.install_disk_cache``: returns
    False, changing nothing, for a tree older than the program's download
    cache. ``cache_dir`` must not be the real download cache. The synthetic
    bake goes in its ``baked`` folder (``install_synthetic_bake``).
    """
    if not hasattr(http_module, "_cached"):
        return False
    cache_dir.mkdir(parents=True, exist_ok=True)

    def cached(key, _download):
        path = cache_dir / (hashlib.sha1(repr(key).encode()).hexdigest() + ".pkl")
        if path.exists():
            return pickle.loads(path.read_bytes())
        try:
            result = synth(key)
        except KeyError as exc:
            print(f"[synthetic] no synthetic answer for {key!r}", file=sys.stderr)
            raise requests.ConnectionError(str(exc)) from None
        path.write_bytes(pickle.dumps(result))
        return result

    http_module._cached = cached
    install_synthetic_bake(cache_dir / "baked")
    # The quotes (not cached), the bake and anything else that would reach out.
    requests.Session.get = _refused  # type: ignore[assignment]
    requests.Session.post = _refused  # type: ignore[assignment]
    return True
