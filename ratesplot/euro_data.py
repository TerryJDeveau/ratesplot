"""The euro area's nations after Germany (batch 14.3, decisions 155, 171): Germany's code paths with each nation's code in place of DE.

Each nation is an ``EuroNation`` (below, its sources noted above it), and the
fetchers take it: France (decision 171, 9.3), Portugal (decision 175, 9.7),
Italy (decision 177, 9.9). All on hosts the program already asks (FRED, the
ECB, Eurostat), each series measured before it was drawn:

* The 10-year yield: the OECD's long-term interest rate on FRED
  (``IRLTLT01..M156N``), a monthly average, dated by each month's first day
  (FRED's dates) and drawn across its month as steps, as the UK's monthly
  averages are. No daily yields are on those hosts.
* General government gross debt (Maastricht, consolidated): the ECB's year
  ends (``GFS``, the series Germany's chart reads, with the nation's code)
  1995 to 1999, then Eurostat's quarters (``gov_10q_ggdebt``, S13) from
  2000-Q1.
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
  state level (S1312 is empty); the social security funds (S1314) are no
  level of the chart, as Germany's are not. Their debt is Eurostat's
  quarters; their interest its yearly accounts (``gov_10a_main``, from 1995,
  each year dated by its last day), since France's quarterly interest is
  published for S13 alone (measured 2026-11-20); Portugal's and Italy's
  levels the same way, though Portugal's levels' quarters begin in 2008.

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

from dataclasses import dataclass

import pandas as pd

from .config import (
    COMPONENT_LETTERS,
    DATE_COLUMN,
    FR_DEBT_COLUMN,
    FR_INTEREST_COLUMN,
    GDP_COLUMN,
    IT_DEBT_COLUMN,
    IT_INTEREST_COLUMN,
    POPULATION_COLUMN,
    PT_DEBT_COLUMN,
    PT_INTEREST_COLUMN,
    PlotConfig,
    component_column,
)
from .de_data import GENERAL_GOVERNMENT, YIELD_HISTORY_ATTR, ecb_series, eurostat_series
from .de_data import _before as before  # Germany's join: history until the live series begins
from .http import downloads_of
from .joins import ttm_sum
from .us_data import fred_series

# A quarter's population is dated this many days after the quarter begins, as Germany's.
_QUARTER_MIDDLE_DAYS = 45


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
    # Levels of government (--debt:LETTERS): Eurostat's subsectors of each.
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
PORTUGAL = EuroNation(
    key="pt",
    name="Portugal",
    adjective="Portuguese",
    geo="PT",
    yield_series={"10-Year": "IRLTLT01PTM156N"},
    yield_earliest={"10-Year": pd.Timestamp("1993-07-01")},
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
# 1980-01, not joined before it (decision 177's call). Debt from 1995 (the ECB's year ends, Eurostat's quarters from
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
    yield_earliest={"10-Year": pd.Timestamp("1991-03-01")},
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
)

# Every nation of this module, by its key.
EURO_NATIONS = {nation.key: nation for nation in (FRANCE, PORTUGAL, ITALY)}


def series_earliest(nation: EuroNation, config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of the nation's inputs, by name, for the coverage warning: the chosen yields it has, then the rest."""
    earliest = {
        f"{column} Yield (OECD, monthly average)": nation.yield_earliest[column]
        for column in config.fetched_yield_columns
        if column in nation.yield_series
    }
    return {**earliest, **nation.series_earliest}


def fetch_yields(nation: EuroNation, config: PlotConfig) -> pd.DataFrame:
    """Return the nation's yields, date-indexed: each term's monthly averages (FRED), all drawn as steps.

    The columns are the chosen ones it has (``config.fetched_yield_columns``),
    trimmed to the window; ``attrs[YIELD_HISTORY_ATTR]`` gives each column's last
    date, since every value is monthly. A term whose series fails is left out,
    with a warning.
    """
    chosen = [column for column in config.fetched_yield_columns if column in nation.yield_series]
    absent = [column for column in config.yield_columns if column not in nation.yield_series]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no {nation.adjective} {', '.join(absent)} yield; the {nation.adjective} chart is drawn without it.")
    columns: dict[str, pd.Series] = {}
    for column in chosen:
        series_id = nation.yield_series[column]
        try:
            frame = fred_series(series_id, revised=False)
        except Exception as exc:
            print(f"  Warning: FRED {series_id} ({nation.adjective} {column} yield) unavailable ({exc}); not drawn.")
            continue
        values = pd.to_numeric(frame.set_index(DATE_COLUMN)[series_id], errors="coerce").dropna()
        columns[column] = values.set_axis(pd.DatetimeIndex(values.index, name=DATE_COLUMN))
    if not columns:
        return pd.DataFrame()
    frame = pd.concat(columns, axis=1).sort_index().rename_axis(DATE_COLUMN).loc[config.start : config.end]
    frame.attrs[YIELD_HISTORY_ATTR] = {column: values.index[-1] for column, values in columns.items()}
    return frame


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
