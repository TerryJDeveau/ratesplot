"""The euro area's nations after Germany (batch 14.3, decisions 155, 171): Germany's code paths with each nation's code in place of DE.

Each nation is an ``EuroNation`` (below, its sources noted above it), and the
fetchers take it: France (decision 171, 9.3), Portugal (decision 175, 9.7),
Italy (decision 177, 9.9), Spain (decision 180, 9.11), the Netherlands
(decision 182, 9.12). All on hosts the program already asks (FRED, the ECB,
Eurostat), each series measured before it was drawn:

* The 10-year yield: the OECD's long-term interest rate on FRED
  (``IRLTLT01..M156N``), a monthly average, dated by each month's first day
  (FRED's dates) and drawn across its month as steps, as the UK's monthly
  averages are. No daily yields are on those hosts. Italy's before the
  OECD's first month (1991-03): Eurostat's convergence-criterion yield
  (``irt_lt_mcby_m``), the same monthly average, from 1980 (decision 178,
  9.10; ``EuroNation.yield_history_from``).
* Portugal's yields instead (9.13, decision 183): the Banco de Portugal's
  daily yields of its Treasury bonds at 2, 3, 5, 7 and 10 years (BPstat,
  ``EuroNation.daily_yields``), drawn day by day as Germany's daily yields
  are, a gap over three rows a break. Each month's average equals the
  OECD's monthly 10-year, the one drawn before 9.13, to 0.006 in 399 of
  its 400 months (measured 2026-11-23).
* General government gross debt (Maastricht, consolidated): the ECB's year
  ends (``GFS``, the series Germany's chart reads, with the nation's code)
  1995 to 1999, then Eurostat's quarters (``gov_10q_ggdebt``, S13) from
  2000-Q1; Spain's quarters from 1995-Q1, before the ECB's first year end.
* Interest payable (D.41): four-quarter sums of Eurostat's quarters
  (``gov_10q_ggnfa``).
* Nominal GDP: four-quarter sums of Eurostat's quarters at current prices,
  unadjusted (``namq_10_gdp``, CP_MNAC).
* Population (-p, --population): Eurostat's quarters (``namq_10_pe``), dated
  by each quarter's middle, as Germany's are.
* Consumer prices (--constant, --inflation, --cpi): Eurostat's harmonised
  index, all items, 2025 = 100 (``prc_hicp_minr``), from 1996-01; unadjusted.
  Before it, the nation's national consumer price index as the OECD published
  it on FRED (``...CPIALLMINMEI``, from 1955-01, stopped), scaled to the
  harmonised index at its first month (``with_older_index``).
* Levels of government: central government (S1311) and local (S1313). No
  state level (S1312 is empty) but Spain's, its autonomous communities
  (``EuroNation.level_sectors``' "p", "n" the regional and local
  together, as Germany's); the social security funds (S1314) are no
  level of the chart, as Germany's are not. Their debt is Eurostat's
  quarters; their interest its yearly accounts (``gov_10a_main``, from 1995,
  each year dated by its last day), since France's quarterly interest is
  published for S13 alone (measured 2026-11-20); Portugal's, Italy's,
  Spain's and the Netherlands' levels the same way, though Portugal's
  levels' quarters begin in 2008.

The policy rate is the euro area's (``rates``, Germany's functions), and the
mortgage rates the ECB's for the nation (``rates.EURO_MORTGAGE_SERIES``).
Amounts in euros (national currency: before 1999 the nation's own currency at
its conversion rate, as the ECB and Eurostat publish them). Every series is
baked, as Germany's are (batch 14.3's fourth stage, 9.6, 2026-11-22): a
drawing asks FRED for the yield's last two months, the ECB for the debt's and
the mortgage rates' last 24 months, and Eurostat for each dataset's last 24
months, one request a dataset (``de_data.EURO_EUROSTAT_SERIES_READ``); the
national price index, stopped, is its bake alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import (
    BPSTAT_DATA_URL,
    COMPONENT_LETTERS,
    DATE_COLUMN,
    FR_DEBT_COLUMN,
    FR_INTEREST_COLUMN,
    ES_DEBT_COLUMN,
    ES_INTEREST_COLUMN,
    GDP_COLUMN,
    IT_DEBT_COLUMN,
    IT_INTEREST_COLUMN,
    NL_DEBT_COLUMN,
    NL_INTEREST_COLUMN,
    POPULATION_COLUMN,
    PT_DEBT_COLUMN,
    PT_INTEREST_COLUMN,
    RECENT_PART_UNREVISED,
    PlotConfig,
    component_column,
)
from .baked import read_series, with_recent_part
from .de_data import (
    EUROSTAT_BAKED_SOURCE,
    GENERAL_GOVERNMENT,
    YIELD_HISTORY_ATTR,
    ecb_series,
    eurostat_code,
    eurostat_names,
    eurostat_series,
)
from .de_data import _before as before  # Germany's join: history until the live series begins
from .de_data import _DAILY_FILL_LIMIT  # Germany's daily yields' fill: a longer gap is a break
from .http import bpstat_get, downloads_of
from .joins import ttm_sum
from .us_data import fred_series

# A quarter's population is dated this many days after the quarter begins, as Germany's.
_QUARTER_MIDDLE_DAYS = 45

# The Banco de Portugal's BPstat (9.13, decision 183): its baked files, ``ratesplot/data/bpstat/ID.csv``, and the
# dataset of Portugal's daily yields, (domain, dataset): domain 26, the secondary market; Treasury bonds at a fixed
# rate, yields by residual maturity, daily and monthly, from LSEG (measured 2026-11-23).
BPSTAT_BAKED_SOURCE = "bpstat"
BPSTAT_YIELD_DATASET = (26, "690b7b36fd36c0dbe249c48cbbc39524")


@dataclass(frozen=True, eq=False)
class EuroNation:
    """One nation of the euro area drawn on Germany's code paths: its codes, its series and the words its messages use."""

    # The program's key ("fr": ``config.NATIONS``), its name and adjective in messages.
    key: str
    name: str
    adjective: str
    # Eurostat's and the ECB's code for it, in place of Germany's DE in the same queries.
    geo: str
    # The yields it has (the OECD's monthly 10-year on FRED), by column, and the first month of each.
    yield_series: dict[str, str]
    yield_earliest: dict[str, pd.Timestamp]
    # The ECB's annual general government debt: Germany's series (``de_data.ECB_ANNUAL_DEBT``) with the nation's
    # code, in national currency (XDC).
    ecb_annual_debt: tuple[str, str, str]
    # Levels of government (--debt:LETTERS): Eurostat's subsectors of each (several summed, as Germany's "n").
    level_sectors: dict[str, tuple[str, ...]]
    # The national consumer price index before Eurostat's harmonised one, all items, unadjusted, in the OECD's Main
    # Economic Indicators on FRED (its notes: METHODOLOGY N, the national index, not the harmonised one), and the date
    # of its last value: stopped, so it is baked and never asked (``us_data.fred_series``' ``stopped``).
    cpi_history_series: str
    cpi_history_stopped: pd.Timestamp
    # Its columns of debt and interest in the macro frame (``config``).
    debt_column: str
    interest_column: str
    # The first observation of each input but the yields, by the name the coverage warning gives it
    # (``series_earliest`` adds the chosen yields).
    series_earliest: dict[str, pd.Timestamp]
    # The first month of Eurostat's convergence-criterion yield (``irt_lt_mcby_m``) joined before the OECD's 10-year
    # (``_yield_history``; the nation's code in ``de_data.EURO_YIELD_HISTORY_GEOS``), or None: no join (decision 178,
    # Italy's alone: France's runs 0.4 to 1.2 points above the OECD's 1980 to 1986, a different bond; Portugal's falls
    # 2.4 points where the OECD's begins).
    yield_history_from: pd.Timestamp | None = None
    # Daily yields (Portugal's from BPstat, 9.13), by column: the series ids in ``BPSTAT_YIELD_DATASET``, drawn day by
    # day in place of a monthly series (a column is in this or ``yield_series``, never both).
    daily_yields: dict[str, str] = field(default_factory=dict)


# France (batch 14.3, decision 171, 9.3; its balance of payments 9.4, its consumer prices before 1996 9.5, its series
# baked 9.6). Measured 2026-11-19 and again 2026-11-20 (``G:\Research\Claude\ratesplot_b143\measure_fr.py``).
# The 10-year from 1960-01. Against Eurostat's convergence-criterion yield (``irt_lt_mcby_m``, from 1980;
# ``check_sources`` fr_joins): equal every month from 2000-01 (4.89 both in 2026-10), within 0.1 point 1987 to 1999,
# and 0.4 to 1.2 points above it 1980 to 1986, where the two measure different bonds. The Banque de France's Webstat
# has daily yields, behind a key Terry has not registered. Debt from 1995, GDP from 1980, interest from 1995, the
# population from 1980; francs before 1999 at 6.55957. The national price index (``FRACPIALLMINMEI``) 1955-01 to
# 2025-03; measured 2026-11-21 (``G:\Research\Claude\ratesplot_b143c\measure_fr_cpi.py``): in the 339 months both
# have a 12-month rise, the harmonised index's runs above the national one's by 0.19 point on average, by 1.04 at
# most (2023-01).
FRANCE = EuroNation(
    key="fr",
    name="France",
    adjective="French",
    geo="FR",
    yield_series={"10-Year": "IRLTLT01FRM156N"},
    yield_earliest={"10-Year": pd.Timestamp("1960-01-01")},
    ecb_annual_debt=("GFS", "A.N.FR.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    level_sectors={"f": ("S1311",), "m": ("S1313",)},
    cpi_history_series="FRACPIALLMINMEI",
    cpi_history_stopped=pd.Timestamp("2025-03-01"),
    debt_column=FR_DEBT_COLUMN,
    interest_column=FR_INTEREST_COLUMN,
    series_earliest={
        "French General Government Debt (the ECB's year ends from 1995, Eurostat's quarters from 2000)": pd.Timestamp("1995-12-31"),
        "TTM Nominal GDP (Eurostat's quarters from 1980)": pd.Timestamp("1980-12-31"),
        "TTM French Interest Payable (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
    },
)

# Portugal (batch 14.3, decision 175, 9.7), the second nation of the euro area's path. Measured 2026-11-22
# (``G:\Research\Claude\ratesplot_b143pt\measure_pt.py``, ``probe_pt.py``, ``measure_pt_cpi.py``). The OECD's 10-year
# from 1993-07, equal to Eurostat's convergence yield to its rounding (0.01) in all 400 months both have; Eurostat's
# runs from 1986, but falls 2.4 points from 1993-06 to 1993-07, where the OECD's and the ECB's begin: a different bond
# before. Debt from 1995 (the ECB's year ends, Eurostat's quarters from 2000), GDP and the population from 1995,
# interest from 1999 (Eurostat's quarters of S13; its levels' quarters from 2008, so their interest is the yearly
# accounts', from 1995, as France's); escudos before 1999 at 200.482. No state level (S1312 empty). Each subsector's
# debt is consolidated within it alone, so central government's runs above general government's (316 against 294
# billion in 2026-Q2). The national price index (``PRTCPIALLMINMEI``) 1955-01 to 2025-04: in the 340 months both
# have a 12-month rise, the harmonised index's runs above the national one's by 0.02 point on average, by 1.60 at
# most (2023-08).
# Its yields since 9.13 (decision 183): the Banco de Portugal's daily yields on BPstat, five terms, measured
# 2026-11-23 (``G:\Research\Claude\ratesplot_bpstat\measure_terms.py``, from the dataset's whole answer), each to
# 2026-11-13: the 10-year 8,539 days from 1993-07-16, holiday gaps alone (six days at most); the 2-year from
# 1993-07-16, gaps of five months a year to 1998 and 1998-07-24 to 1998-12-23, 2002-07-17 to 2003-02-13; the 3-year
# from 1993-07-16, gaps of five months a year to 1998; the 5-year from 1994-02-04, gaps to 1998-01; the 7-year from
# 1993-07-16, gaps 1993-10-22 to 1995-12-27 and 2015-02-03 to 2016-04-19. Each month's average equals BPstat's own
# monthly to 0.006 in 372 of 376 months (3-year), 378/378 (5-year), 361/362 (7-year), 399/400 (10-year), and the
# 10-year's the OECD's monthly (FRED ``IRLTLT01PTM156N``, drawn before 9.13) in all 400. BPstat's 4-year is left
# out: no such term on the chart. The gaps are drawn as breaks (``fetch_yields``).
PORTUGAL = EuroNation(
    key="pt",
    name="Portugal",
    adjective="Portuguese",
    geo="PT",
    yield_series={},
    daily_yields={"2-Year": "12099454", "3-Year": "12099455", "5-Year": "12099457", "7-Year": "12099458",
                  "10-Year": "12099459"},
    yield_earliest={"2-Year": pd.Timestamp("1993-07-16"), "3-Year": pd.Timestamp("1993-07-16"),
                    "5-Year": pd.Timestamp("1994-02-04"), "7-Year": pd.Timestamp("1993-07-16"),
                    "10-Year": pd.Timestamp("1993-07-16")},
    ecb_annual_debt=("GFS", "A.N.PT.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    level_sectors={"f": ("S1311",), "m": ("S1313",)},
    cpi_history_series="PRTCPIALLMINMEI",
    cpi_history_stopped=pd.Timestamp("2025-04-01"),
    debt_column=PT_DEBT_COLUMN,
    interest_column=PT_INTEREST_COLUMN,
    series_earliest={
        "Portuguese General Government Debt (the ECB's year ends from 1995, Eurostat's quarters from 2000)": pd.Timestamp("1995-12-31"),
        "TTM Nominal GDP (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
        "TTM Portuguese Interest Payable (Eurostat's quarters from 1999)": pd.Timestamp("1999-12-31"),
    },
)

# Italy (batch 14.3, decision 177, 9.9), the third nation of the euro area's path. Measured 2026-11-22
# (``G:\Research\Claude\ratesplot_b143it\measure_it.py``, ``probe_it.py``, ``measure_cpi_it.py``). The OECD's 10-year
# from 1991-03, equal to Eurostat's convergence yield to 0.005 in all 428 months both have; Eurostat's runs from
# 1980-01 with no step where the OECD's begins (13.78 in 1991-02, 13.77 in 1991-03), and is joined before it since
# 9.10 (decision 178, at Terry's word: decision 177's alternative). Debt from 1995 (the ECB's year ends, Eurostat's quarters from
# 2000), GDP and the population from 1995, interest from 1999 (Eurostat's quarters of S13; the levels' interest the
# yearly accounts', from 1995, as France's); lire before 1999 at 1,936.27. No state level (S1312 empty). The national
# price index (``ITACPIALLMINMEI``) 1955-01 to 2025-03: in the 339 months both have a 12-month rise, the harmonised
# index's runs above the national one's by 0.09 point on average, by 1.43 at most (2001-02).
ITALY = EuroNation(
    key="it",
    name="Italy",
    adjective="Italian",
    geo="IT",
    yield_series={"10-Year": "IRLTLT01ITM156N"},
    yield_earliest={"10-Year": pd.Timestamp("1980-01-01")},
    ecb_annual_debt=("GFS", "A.N.IT.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    level_sectors={"f": ("S1311",), "m": ("S1313",)},
    cpi_history_series="ITACPIALLMINMEI",
    cpi_history_stopped=pd.Timestamp("2025-03-01"),
    debt_column=IT_DEBT_COLUMN,
    interest_column=IT_INTEREST_COLUMN,
    series_earliest={
        "Italian General Government Debt (the ECB's year ends from 1995, Eurostat's quarters from 2000)": pd.Timestamp("1995-12-31"),
        "TTM Nominal GDP (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
        "TTM Italian Interest Payable (Eurostat's quarters from 1999)": pd.Timestamp("1999-12-31"),
    },
    yield_history_from=pd.Timestamp("1980-01-01"),
)

# Spain (batch 14.3, decision 180, 9.11), the fourth nation of the euro area's path. Measured 2026-11-23
# (``G:\Research\Claude\ratesplot_b143es\measure_es.py``, ``probe_es.py``, ``measure_cpi_es.py``). The OECD's 10-year
# from 1980-01; Eurostat's convergence yield runs from 1980-01 too, up to 1.22 points away before 1991 (91 months
# over 0.006), so not joined. Debt and interest by Eurostat's quarters from 1995-Q1 (the ECB's year ends, from 1995,
# only if Eurostat fails); GDP and the population from 1995; pesetas before 1999 at 166.386. A state level, the
# autonomous communities (S1312, 355 of 1,763 billion in 2026-Q2), drawn as Germany's Länder are; each subsector's
# debt consolidated within it alone. The national price index (``ESPCPIALLMINMEI``) 1954-03 to 2025-03: in the 339
# months both have a 12-month rise, the harmonised index's runs below the national one's by 0.01 point on average,
# 1.59 apart at most (2001-08).
SPAIN = EuroNation(
    key="es",
    name="Spain",
    adjective="Spanish",
    geo="ES",
    yield_series={"10-Year": "IRLTLT01ESM156N"},
    yield_earliest={"10-Year": pd.Timestamp("1980-01-01")},
    ecb_annual_debt=("GFS", "A.N.ES.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    level_sectors={"f": ("S1311",), "n": ("S1312", "S1313"), "p": ("S1312",), "m": ("S1313",)},
    cpi_history_series="ESPCPIALLMINMEI",
    cpi_history_stopped=pd.Timestamp("2025-03-01"),
    debt_column=ES_DEBT_COLUMN,
    interest_column=ES_INTEREST_COLUMN,
    series_earliest={
        "Spanish General Government Debt (Eurostat's quarters from 1995)": pd.Timestamp("1995-03-31"),
        "TTM Nominal GDP (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
        "TTM Spanish Interest Payable (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
    },
)

# The Netherlands (batch 14.3, decision 182, 9.12), the fifth nation of the euro area's path. Measured 2026-11-23
# (``G:\Research\Claude\ratesplot_b143nl\measure_nl.py``, ``probe_nl.py``, ``measure_cpi_nl.py``, ``bop_nl.py``).
# The OECD's 10-year from 1959-01, none missing; Eurostat's convergence yield runs from 1986-04, up to 0.066 points
# from it before 1993 (49 months over 0.006), so not used. Debt from 1995 (the ECB's year ends, Eurostat's quarters
# from 2000), GDP and the population from 1995, interest from 1999 (Eurostat's quarters of S13; the levels' interest
# the yearly accounts', from 1995, as France's); guilders before 1999 at 2.20371. No state level (S1312 empty). Each
# subsector's debt is consolidated within it alone, so central government's runs above general government's (582
# against 524 billion in 2026-Q2). The national price index (``NLDCPIALLMINMEI``) 1960-04 to 2025-04: in the 340
# months both have a 12-month rise, the harmonised index's runs above the national one's by 0.06 point on average,
# by 2.53 at most (2022-09).
NETHERLANDS = EuroNation(
    key="nl",
    name="Netherlands",
    adjective="Dutch",
    geo="NL",
    yield_series={"10-Year": "IRLTLT01NLM156N"},
    yield_earliest={"10-Year": pd.Timestamp("1959-01-01")},
    ecb_annual_debt=("GFS", "A.N.NL.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
    level_sectors={"f": ("S1311",), "m": ("S1313",)},
    cpi_history_series="NLDCPIALLMINMEI",
    cpi_history_stopped=pd.Timestamp("2025-04-01"),
    debt_column=NL_DEBT_COLUMN,
    interest_column=NL_INTEREST_COLUMN,
    series_earliest={
        "Dutch General Government Debt (the ECB's year ends from 1995, Eurostat's quarters from 2000)": pd.Timestamp("1995-12-31"),
        "TTM Nominal GDP (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
        "TTM Dutch Interest Payable (Eurostat's quarters from 1999)": pd.Timestamp("1999-12-31"),
    },
)

# Every nation of this module, by its key.
EURO_NATIONS = {nation.key: nation for nation in (FRANCE, PORTUGAL, ITALY, SPAIN, NETHERLANDS)}


def series_earliest(nation: EuroNation, config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of the nation's inputs, by name, for the coverage warning: the chosen yields it has, then the rest."""
    earliest = {
        (f"{column} Yield (Eurostat's convergence yield, then the OECD's; monthly averages)" if nation.yield_history_from
         else f"{column} Yield (Banco de Portugal, daily)" if column in nation.daily_yields
         else f"{column} Yield (OECD, monthly average)"): nation.yield_earliest[column]
        for column in config.fetched_yield_columns
        if column in nation.yield_series or column in nation.daily_yields
    }
    return {**earliest, **nation.series_earliest}


def parse_bpstat(data: dict, series_id: str) -> pd.Series:
    """Return one BPstat series from its JSON-stat 2.0 answer: dated by each reference day, in percent.

    The answer must hold that series alone (``extension.series``), daily, in
    percent ("Percentage"), every dimension but ``reference_date`` of one
    category: so the values, a flat list, are the series' own in the order of
    its days. A day without a value is left out. No day at all (asked from a
    day after its last) is an empty series.
    """
    listed = [str(entry.get("id")) for entry in (data.get("extension") or {}).get("series", [])]
    if listed and listed != [series_id]:
        raise ValueError(f"expected BPstat series {series_id} alone, found {listed}")
    ids, sizes = data.get("id", []), data.get("size", [])
    if "reference_date" not in ids or len(ids) != len(sizes):
        raise ValueError("expected a JSON-stat dataset with a reference_date dimension")
    labels = {}
    for dim, size in zip(ids, sizes):
        if dim == "reference_date":
            continue
        if size != 1:
            raise ValueError(f"expected one category of BPstat's dimension {dim}, found {size}")
        dimension = data["dimension"][dim]
        labels[dimension.get("label")] = next(iter(dimension["category"].get("label", {}).values()), None)
    if labels.get("Periodicity") != "Daily" or labels.get("Unit of measure") != "Percentage":
        raise ValueError(f"expected BPstat series {series_id} daily in percent, found {labels.get('Periodicity')} in "
                         f"{labels.get('Unit of measure')}")
    index = data["dimension"]["reference_date"]["category"].get("index", [])
    days = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
    values = data.get("value", [])
    if isinstance(values, dict):  # JSON-stat's sparse form, by position
        values = [values.get(str(position)) for position in range(len(days))]
    if len(values) != len(days):
        raise ValueError(f"BPstat series {series_id}: {len(values)} values for {len(days)} days")
    numbers = pd.to_numeric(pd.Series(values, dtype=object), errors="coerce").to_numpy(dtype=float)
    return pd.Series(numbers, index=pd.DatetimeIndex(days, name=DATE_COLUMN)).dropna().sort_index()


def bpstat_download(series_id: str, start: pd.Timestamp | None = None) -> pd.Series:
    """Ask BPstat for one series of ``BPSTAT_YIELD_DATASET``, from ``start`` (an ISO day, ``obs_since``) or whole (``parse_bpstat``)."""
    domain, dataset = BPSTAT_YIELD_DATASET
    params = {"lang": "EN", "series_ids": series_id}
    if start is not None:
        params["obs_since"] = f"{start:%Y-%m-%d}"
    response = bpstat_get(BPSTAT_DATA_URL.format(domain=domain, dataset=dataset), params)
    return parse_bpstat(response.json(), series_id)


def bpstat_series(series_id: str) -> pd.Series:
    """Return one BPstat series: its baked history (``ratesplot/data/bpstat/``), then its last two months asked for.

    As every live source (``baked.with_recent_part``): market yields, not
    revised, so the recent part is the last two months; with BPstat failing,
    the bake alone, with a warning; a series not baked is asked for whole.
    """
    return with_recent_part(
        BPSTAT_BAKED_SOURCE,
        series_id,
        f"Banco de Portugal {series_id}",
        lambda start: bpstat_download(series_id, start),
        RECENT_PART_UNREVISED,
    )


def fetch_yields(nation: EuroNation, config: PlotConfig) -> pd.DataFrame:
    """Return the nation's yields, date-indexed: each term's monthly averages (FRED), drawn as steps, or its daily yields (Portugal's, BPstat).

    The columns are the chosen ones it has (``config.fetched_yield_columns``),
    trimmed to the window; ``attrs[YIELD_HISTORY_ATTR]`` gives each monthly
    column's last date (every value of it monthly: steps); a daily column has
    none, so it is drawn as a line (``plotting.add_stepped_yield_lines``). A
    daily term is carried over a missing day for three rows at most, as
    Germany's daily yields are, so a longer gap is a break. A term whose
    series fails is left out, with a warning.
    """
    chosen = [column for column in config.fetched_yield_columns
              if column in nation.yield_series or column in nation.daily_yields]
    absent = [column for column in config.yield_columns
              if column not in nation.yield_series and column not in nation.daily_yields]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no {nation.adjective} {', '.join(absent)} yield; the {nation.adjective} chart is drawn without it.")
    columns: dict[str, pd.Series] = {}
    history_through: dict[str, pd.Timestamp] = {}
    for column in chosen:
        if column in nation.daily_yields:
            series_id = nation.daily_yields[column]
            try:
                daily = bpstat_series(series_id)
            except Exception as exc:
                print(f"  Warning: Banco de Portugal {series_id} ({nation.adjective} {column} yield) unavailable ({exc}); not drawn.")
                continue
            if not daily.empty:
                columns[column] = daily
            continue
        series_id = nation.yield_series[column]
        try:
            frame = fred_series(series_id, revised=False)
        except Exception as exc:
            print(f"  Warning: FRED {series_id} ({nation.adjective} {column} yield) unavailable ({exc}); not drawn.")
            continue
        values = pd.to_numeric(frame.set_index(DATE_COLUMN)[series_id], errors="coerce").dropna()
        values = values.set_axis(pd.DatetimeIndex(values.index, name=DATE_COLUMN))
        if column == "10-Year" and nation.yield_history_from is not None:
            values = before(_yield_history(nation), values)
        columns[column] = values
        history_through[column] = values.index[-1]
    if not columns:
        return pd.DataFrame()
    frame = pd.concat(columns, axis=1).sort_index()
    for column in frame.columns:
        if column not in history_through:
            frame[column] = frame[column].ffill(limit=_DAILY_FILL_LIMIT)
    frame = frame.rename_axis(DATE_COLUMN).loc[config.start : config.end]
    frame.attrs[YIELD_HISTORY_ATTR] = history_through
    return frame


def _yield_history(nation: EuroNation) -> pd.Series | None:
    """Return Eurostat's convergence-criterion yield for the nation from ``yield_history_from``, each month dated by its first day, as FRED dates the OECD's: the 10-year before the OECD's begins (decision 178).

    Read from its bake alone, with no request: only its months before the
    OECD's first are drawn (``de_data._before``), and those (1980 to 1991)
    are long past revision, so a drawing asking Eurostat for its newest
    months would bring nothing it draws. The daily job keeps the bake, as it
    keeps every Eurostat series read (``de_data.EURO_YIELD_HISTORY_READ``).
    With no bake, the dataset is asked for whole (``eurostat_series``); if
    that fails, a warning, and the OECD's alone.
    """
    dataset = "irt_lt_mcby_m"
    values = read_series(EUROSTAT_BAKED_SOURCE, eurostat_code(dataset, **eurostat_names(nation.geo)))
    if values is None or values.empty:
        try:
            values = eurostat_series(dataset, geo=nation.geo)
        except Exception as exc:
            print(f"  Warning: Eurostat {dataset} ({nation.adjective} 10-year before the OECD's) unavailable ({exc}); "
                  "the OECD's alone.")
            return None
    values = values.dropna()
    values.index = pd.DatetimeIndex(values.index).to_period("M").to_timestamp().rename(DATE_COLUMN)
    return values.loc[nation.yield_history_from:]


def _quarterly_debt(nation: EuroNation, sectors: tuple[str, ...]) -> pd.Series:
    """Return the gross debt of these Eurostat subsectors together, at each quarter's end, in euros."""
    parts = [eurostat_series("gov_10q_ggdebt", geo=nation.geo, sector=sector) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


def _ttm_interest(nation: EuroNation, sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest payable (D.41) by these Eurostat subsectors together, summed over four quarters, in euros."""
    parts = [eurostat_series("gov_10q_ggnfa", geo=nation.geo, sector=sector) for sector in sectors]
    return ttm_sum(pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna())


def _yearly_interest(nation: EuroNation, sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest payable (D.41) by these subsectors together in each calendar year, dated by its last day, in euros (Eurostat's yearly accounts).

    A level's: Eurostat's quarters hold the interest of S13 alone for France.
    A year's sum is the trailing twelve months at its end, as a quarter's TTM is.
    """
    parts = [eurostat_series("gov_10a_main", geo=nation.geo, sector=sector) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


@downloads_of("ECB and Eurostat government debt")
def fetch_debt(nation: EuroNation, config: PlotConfig) -> pd.DataFrame | None:
    """Return general government gross debt: the ECB's year ends (1995-1999), then Eurostat's quarters (2000-).

    Either alone, with a warning, if the other fails; None if both do.
    """
    if not config.include_debt:
        return None
    try:
        annual = ecb_series(*nation.ecb_annual_debt, revised=True)
    except Exception as exc:
        print(f"  Warning: ECB annual {nation.adjective} debt unavailable ({exc}); drawn from 2000.")
        annual = None
    try:
        quarterly = _quarterly_debt(nation, (GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly {nation.adjective} debt unavailable ({exc}); the year-end figures alone.")
        quarterly = None
    joined = before(annual, quarterly)
    return joined.rename(nation.debt_column).to_frame() if joined is not None else None


@downloads_of("Eurostat GDP")
def fetch_gdp(nation: EuroNation, config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: four-quarter sums of Eurostat's quarters; None, with a warning, if Eurostat fails."""
    if not config.needs_gdp:
        return None
    try:
        quarters = eurostat_series("namq_10_gdp", geo=nation.geo)
    except Exception as exc:
        print(f"  Warning: Eurostat {nation.adjective} GDP unavailable ({exc}); not drawn.")
        return None
    return ttm_sum(quarters).rename(GDP_COLUMN).to_frame()


@downloads_of("Eurostat interest outlays")
def fetch_interest(nation: EuroNation, config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month general government interest payable: four-quarter sums of Eurostat's quarters; None, with a warning, if Eurostat fails."""
    if not config.include_interest:
        return None
    try:
        values = _ttm_interest(nation, (GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly {nation.adjective} interest unavailable ({exc}); not drawn.")
        return None
    return values.rename(nation.interest_column).to_frame()


@downloads_of("Eurostat debt and interest by level of government")
def fetch_components(nation: EuroNation, config: PlotConfig) -> pd.DataFrame | None:
    """Return debt and TTM interest by level of government (--debt:LETTERS): debt from Eurostat's quarters (from 2000), interest from its years (from 1995).

    A level whose series fails is left out, with a warning.
    """
    columns: list[pd.Series] = []
    for letter in COMPONENT_LETTERS:
        if letter not in config.components or letter not in nation.level_sectors:
            continue
        sectors = nation.level_sectors[letter]
        for kind, include, fetch in (("debt", config.include_debt, _quarterly_debt), ("interest", config.include_interest, _yearly_interest)):
            if not include:
                continue
            try:
                values = fetch(nation, sectors)
            except Exception as exc:
                print(f"  Warning: Eurostat {nation.adjective} {kind}, level {letter} ({'+'.join(sectors)}) unavailable ({exc}); not drawn.")
                continue
            columns.append(values.rename(component_column(kind, letter)))
    return pd.concat(columns, axis=1).sort_index() if columns else None


def with_older_index(nation: EuroNation, harmonised: pd.Series) -> pd.Series:
    """Return the nation's consumer price index carried back to 1955-01 by its national index, on the harmonised index's base; from its own first month, unchanged.

    The national index (``EuroNation.cpi_history_series``) is scaled to the
    harmonised one at the month where the harmonised one begins, so each keeps
    its own rises and no level is lost, as Germany's older indexes are joined
    (``de_data.with_west_germany``). The rises of the first 12 months after
    the join are the harmonised index over the scaled national one a year
    before. If the national index cannot be read, or does not hold the
    harmonised index's first month, ``harmonised`` is returned alone, with a
    warning.
    """
    code = nation.cpi_history_series
    try:
        frame = fred_series(code, revised=False, stopped=nation.cpi_history_stopped)
    except Exception as exc:
        print(f"  Warning: FRED {code} ({nation.name}'s consumer prices before {harmonised.index[0]:%Y-%m}) unavailable ({exc}); drawn without them.")
        return harmonised
    national = pd.to_numeric(frame.set_index(DATE_COLUMN)[code], errors="coerce").dropna()
    national = national.set_axis(pd.DatetimeIndex(national.index, name=DATE_COLUMN).to_period("M").start_time)
    join = harmonised.index[0]
    if join not in national.index:
        print(f"  Warning: {nation.name}'s harmonised consumer prices begin {join:%Y-%m-%d}, where FRED {code} has no value; drawn without it.")
        return harmonised
    older = national * (harmonised.iloc[0] / national.loc[join])
    return pd.concat([older.loc[older.index < join], harmonised]).rename(harmonised.name)


@downloads_of("Eurostat consumer prices")
def fetch_consumer_prices(nation: EuroNation) -> pd.Series:
    """Return the nation's consumer price index (2025 = 100), each month dated by its first day: Eurostat's harmonised index, all items, from 1996-01, carried back to 1955-01 by the national index (``with_older_index``); raises if Eurostat has none.

    Unadjusted: no seasonally adjusted index is published with it (--cpi:sa
    is not offered, as for the UK).
    """
    index = eurostat_series("prc_hicp_minr", geo=nation.geo)
    harmonised = index.set_axis(pd.DatetimeIndex(index.index.to_period("M").start_time, name=DATE_COLUMN)).rename("prc_hicp_minr")
    return with_older_index(nation, harmonised)


@downloads_of("Eurostat population")
def fetch_population(nation: EuroNation) -> pd.Series | None:
    """Return the nation's population for -p: Eurostat's quarters (thousands), each dated by the quarter's middle; None, with a warning, if Eurostat fails."""
    try:
        quarterly = eurostat_series("namq_10_pe", geo=nation.geo)
    except Exception as exc:
        print(f"  Warning: Eurostat {nation.adjective} population unavailable ({exc}); not drawn.")
        return None
    middles = quarterly.index.to_period("Q").start_time + pd.Timedelta(days=_QUARTER_MIDDLE_DAYS)
    return quarterly.set_axis(pd.DatetimeIndex(middles, name=DATE_COLUMN)).rename(POPULATION_COLUMN)
