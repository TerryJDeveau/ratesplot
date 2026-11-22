"""France's data pipelines (batch 14.3, decision 171): Germany's code paths with FR in place of DE.

Sources, each measured on 2026-11-19 and again 2026-11-20 before it was drawn
(``G:\\Research\\Claude\\ratesplot_b143\\measure_fr.py``), all on hosts the
program already asks:

* The 10-year yield: the OECD's long-term interest rate on FRED,
  ``IRLTLT01FRM156N``, a monthly average from 1960-01, dated by each month's
  first day (FRED's dates) and drawn across its month as steps, as the UK's
  monthly averages are. Against Eurostat's convergence-criterion yield
  (``irt_lt_mcby_m``, from 1980; measured 2026-11-20, ``check_sources``
  fr_joins): equal every month from 2000-01 (4.89 both in 2026-10), within
  0.1 point 1987 to 1999, and 0.4 to 1.2 points above it 1980 to 1986,
  where the two measure different bonds. No daily French
  yields are on those hosts: the Banque de France's Webstat has them, behind
  a key Terry has not registered.
* General government gross debt (Maastricht, consolidated): the ECB's year
  ends (``GFS``, the series Germany's chart reads with FR) 1995 to 1999, then
  Eurostat's quarters (``gov_10q_ggdebt``, S13) from 2000-Q1.
* Interest payable (D.41): four-quarter sums of Eurostat's quarters
  (``gov_10q_ggnfa``), from 1995-Q4.
* Nominal GDP: four-quarter sums of Eurostat's quarters at current prices,
  unadjusted (``namq_10_gdp``, CP_MNAC), from 1980-Q4.
* Population (-p, --population): Eurostat's quarters (``namq_10_pe``) from
  1980, dated by each quarter's middle, as Germany's are.
* Consumer prices (--constant, --inflation, --cpi): Eurostat's harmonised
  index, all items, 2025 = 100 (``prc_hicp_minr``), from 1996-01; unadjusted.
  Before it (batch 14.3's third stage, 9.5): France's national consumer price
  index as the OECD published it on FRED (``FRACPIALLMINMEI``, 1955-01 to
  2025-03, stopped), scaled to the harmonised index at its first month
  (``with_older_index``). Measured 2026-11-21
  (``G:\\Research\\Claude\\ratesplot_b143c\\measure_fr_cpi.py``): in the 339
  months both have a 12-month rise, the harmonised index's runs above the
  national one's by 0.19 point on average, by 1.04 at most (2023-01).
* Levels of government: central government (S1311) and local (S1313).
  France has no state level (S1312 is empty); the social security funds
  (S1314) are no level of the chart, as Germany's are not. Their debt is
  Eurostat's quarters; their interest its yearly accounts (``gov_10a_main``,
  1995 to 2025, each year dated by its last day), since the quarterly
  interest is published for S13 alone (measured 2026-11-20).

The policy rate is the euro area's (``rates``, Germany's functions), and the
mortgage rates the ECB's for France (``rates.FR_MORTGAGE_SERIES``). Amounts in
euros (national currency, so French francs before 1999 at 6.55957, as the ECB
and Eurostat publish them). Every series is baked (batch 14.3's fourth stage,
9.6, 2026-11-22), as Germany's are: a drawing asks FRED for the yield's last
two months, the ECB for the debt's and the mortgage rates' last 24 months, and
Eurostat for each dataset's last 24 months, one request a dataset
(``de_data.FR_EUROSTAT_SERIES_READ``); the national price index, stopped, is
its bake alone.
"""
from __future__ import annotations

import pandas as pd

from .config import (
    COMPONENT_LETTERS,
    DATE_COLUMN,
    FR_DEBT_COLUMN,
    FR_INTEREST_COLUMN,
    GDP_COLUMN,
    POPULATION_COLUMN,
    PlotConfig,
    component_column,
)
from .de_data import GENERAL_GOVERNMENT, YIELD_HISTORY_ATTR, ecb_series, eurostat_series
from .de_data import _before as before  # Germany's join: history until the live series begins
from .http import downloads_of
from .joins import ttm_sum
from .us_data import fred_series

# Eurostat's code for France, in place of Germany's in the same queries.
FR_GEO = "FR"
# The yields France has: the OECD's monthly 10-year on FRED.
FR_YIELD_SERIES = {"10-Year": "IRLTLT01FRM156N"}
# The ECB's annual general government debt for France: Germany's series
# (``de_data.ECB_ANNUAL_DEBT``) with FR, in national currency (XDC).
FR_ECB_ANNUAL_DEBT = ("GFS", "A.N.FR.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC")
# Levels of government (--debt:LETTERS): Eurostat's subsectors of each.
_LEVEL_SECTORS = {"f": ("S1311",), "m": ("S1313",)}
# A quarter's population is dated this many days after the quarter begins, as Germany's.
_QUARTER_MIDDLE_DAYS = 45
# France's consumer prices before Eurostat's harmonised index (batch 14.3's third stage, decision 173): the national
# index, all items, unadjusted, 2015 = 100, in the OECD's Main Economic Indicators (FRED's notes: METHODOLOGY N, the
# national index, not the harmonised one), monthly from 1955-01. FRED's last value is 2025-03 (measured 2026-11-21):
# stopped, so it is baked and never asked (``us_data.fred_series``' ``stopped``, the date of its last value).
FR_CPI_HISTORY_SERIES = "FRACPIALLMINMEI"
FR_CPI_HISTORY_STOPPED = pd.Timestamp("2025-03-01")

# First observation of each French input, to warn when --start is earlier
# (``fr_series_earliest`` adds the chosen yields). Measured 2026-11-20.
FR_YIELD_EARLIEST = {"10-Year": pd.Timestamp("1960-01-01")}
FR_SERIES_EARLIEST = {
    "French General Government Debt (the ECB's year ends from 1995, Eurostat's quarters from 2000)": pd.Timestamp("1995-12-31"),
    "TTM Nominal GDP (Eurostat's quarters from 1980)": pd.Timestamp("1980-12-31"),
    "TTM French Interest Payable (Eurostat's quarters from 1995)": pd.Timestamp("1995-12-31"),
}


def fr_series_earliest(config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of the French inputs, by name, for the coverage warning: the chosen yields France has, then the rest."""
    earliest = {
        f"{column} Yield (OECD, monthly average)": FR_YIELD_EARLIEST[column]
        for column in config.fetched_yield_columns
        if column in FR_YIELD_SERIES
    }
    return {**earliest, **FR_SERIES_EARLIEST}


def fetch_fr_yields(config: PlotConfig) -> pd.DataFrame:
    """Return France's yields, date-indexed: each term's monthly averages (FRED), all drawn as steps.

    The columns are the chosen ones France has (``config.fetched_yield_columns``),
    trimmed to the window; ``attrs[YIELD_HISTORY_ATTR]`` gives each column's last
    date, since every value is monthly. A term whose series fails is left out,
    with a warning.
    """
    chosen = [column for column in config.fetched_yield_columns if column in FR_YIELD_SERIES]
    absent = [column for column in config.yield_columns if column not in FR_YIELD_SERIES]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no French {', '.join(absent)} yield; the French chart is drawn without it.")
    columns: dict[str, pd.Series] = {}
    for column in chosen:
        series_id = FR_YIELD_SERIES[column]
        try:
            frame = fred_series(series_id, revised=False)
        except Exception as exc:
            print(f"  Warning: FRED {series_id} (French {column} yield) unavailable ({exc}); not drawn.")
            continue
        values = pd.to_numeric(frame.set_index(DATE_COLUMN)[series_id], errors="coerce").dropna()
        columns[column] = values.set_axis(pd.DatetimeIndex(values.index, name=DATE_COLUMN))
    if not columns:
        return pd.DataFrame()
    frame = pd.concat(columns, axis=1).sort_index().rename_axis(DATE_COLUMN).loc[config.start : config.end]
    frame.attrs[YIELD_HISTORY_ATTR] = {column: values.index[-1] for column, values in columns.items()}
    return frame


def _quarterly_debt(sectors: tuple[str, ...]) -> pd.Series:
    """Return the gross debt of these Eurostat subsectors together, at each quarter's end, in euros."""
    parts = [eurostat_series("gov_10q_ggdebt", geo=FR_GEO, sector=sector) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


def _ttm_interest(sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest payable (D.41) by these Eurostat subsectors together, summed over four quarters, in euros."""
    parts = [eurostat_series("gov_10q_ggnfa", geo=FR_GEO, sector=sector) for sector in sectors]
    return ttm_sum(pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna())


def _yearly_interest(sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest payable (D.41) by these subsectors together in each calendar year, dated by its last day, in euros (Eurostat's yearly accounts).

    A level's: Eurostat's quarters hold the interest of S13 alone for France.
    A year's sum is the trailing twelve months at its end, as a quarter's TTM is.
    """
    parts = [eurostat_series("gov_10a_main", geo=FR_GEO, sector=sector) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


@downloads_of("ECB and Eurostat government debt")
def fetch_fr_debt(config: PlotConfig) -> pd.DataFrame | None:
    """Return general government gross debt: the ECB's year ends (1995-1999), then Eurostat's quarters (2000-).

    Either alone, with a warning, if the other fails; None if both do.
    """
    if not config.include_debt:
        return None
    try:
        annual = ecb_series(*FR_ECB_ANNUAL_DEBT, revised=True)
    except Exception as exc:
        print(f"  Warning: ECB annual French debt unavailable ({exc}); drawn from 2000.")
        annual = None
    try:
        quarterly = _quarterly_debt((GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly French debt unavailable ({exc}); the year-end figures alone.")
        quarterly = None
    joined = before(annual, quarterly)
    return joined.rename(FR_DEBT_COLUMN).to_frame() if joined is not None else None


@downloads_of("Eurostat GDP")
def fetch_fr_gdp(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: four-quarter sums of Eurostat's quarters (from 1980-Q4); None, with a warning, if Eurostat fails."""
    if not config.needs_gdp:
        return None
    try:
        quarters = eurostat_series("namq_10_gdp", geo=FR_GEO)
    except Exception as exc:
        print(f"  Warning: Eurostat French GDP unavailable ({exc}); not drawn.")
        return None
    return ttm_sum(quarters).rename(GDP_COLUMN).to_frame()


@downloads_of("Eurostat interest outlays")
def fetch_fr_interest(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month general government interest payable: four-quarter sums of Eurostat's quarters (from 1995-Q4); None, with a warning, if Eurostat fails."""
    if not config.include_interest:
        return None
    try:
        values = _ttm_interest((GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly French interest unavailable ({exc}); not drawn.")
        return None
    return values.rename(FR_INTEREST_COLUMN).to_frame()


@downloads_of("Eurostat debt and interest by level of government")
def fetch_fr_components(config: PlotConfig) -> pd.DataFrame | None:
    """Return debt and TTM interest by level of government (--debt:LETTERS): central and local, debt from Eurostat's quarters (from 2000), interest from its years (1995 to 2025).

    A level whose series fails is left out, with a warning.
    """
    columns: list[pd.Series] = []
    for letter in COMPONENT_LETTERS:
        if letter not in config.components or letter not in _LEVEL_SECTORS:
            continue
        sectors = _LEVEL_SECTORS[letter]
        for kind, include, fetch in (("debt", config.include_debt, _quarterly_debt), ("interest", config.include_interest, _yearly_interest)):
            if not include:
                continue
            try:
                values = fetch(sectors)
            except Exception as exc:
                print(f"  Warning: Eurostat French {kind}, level {letter} ({'+'.join(sectors)}) unavailable ({exc}); not drawn.")
                continue
            columns.append(values.rename(component_column(kind, letter)))
    return pd.concat(columns, axis=1).sort_index() if columns else None


def with_older_index(harmonised: pd.Series) -> pd.Series:
    """Return France's consumer price index carried back to 1955-01 by the national index, on the harmonised index's base; from its own first month, unchanged.

    The national index (``FR_CPI_HISTORY_SERIES``) is scaled to the
    harmonised one at the month where the harmonised one begins, so each keeps
    its own rises and no level is lost, as Germany's older indexes are joined
    (``de_data.with_west_germany``). The rises of the first 12 months after
    the join are the harmonised index over the scaled national one a year
    before. If the national index cannot be read, or does not hold the
    harmonised index's first month, ``harmonised`` is returned alone, with a
    warning.
    """
    try:
        frame = fred_series(FR_CPI_HISTORY_SERIES, revised=False, stopped=FR_CPI_HISTORY_STOPPED)
    except Exception as exc:
        print(f"  Warning: FRED {FR_CPI_HISTORY_SERIES} (France's consumer prices before {harmonised.index[0]:%Y-%m}) unavailable ({exc}); drawn without them.")
        return harmonised
    national = pd.to_numeric(frame.set_index(DATE_COLUMN)[FR_CPI_HISTORY_SERIES], errors="coerce").dropna()
    national = national.set_axis(pd.DatetimeIndex(national.index, name=DATE_COLUMN).to_period("M").start_time)
    join = harmonised.index[0]
    if join not in national.index:
        print(f"  Warning: France's harmonised consumer prices begin {join:%Y-%m-%d}, where FRED {FR_CPI_HISTORY_SERIES} has no value; drawn without it.")
        return harmonised
    older = national * (harmonised.iloc[0] / national.loc[join])
    return pd.concat([older.loc[older.index < join], harmonised]).rename(harmonised.name)


@downloads_of("Eurostat consumer prices")
def fetch_fr_consumer_prices() -> pd.Series:
    """Return France's consumer price index (2025 = 100), each month dated by its first day: Eurostat's harmonised index, all items, from 1996-01, carried back to 1955-01 by the national index (``with_older_index``); raises if Eurostat has none.

    Unadjusted: no seasonally adjusted index is published with it (--cpi:sa
    is not offered for France, as for the UK).
    """
    index = eurostat_series("prc_hicp_minr", geo=FR_GEO)
    harmonised = index.set_axis(pd.DatetimeIndex(index.index.to_period("M").start_time, name=DATE_COLUMN)).rename("prc_hicp_minr")
    return with_older_index(harmonised)


@downloads_of("Eurostat population")
def fetch_fr_population() -> pd.Series | None:
    """Return France's population for -p: Eurostat's quarters (from 1980, thousands), each dated by the quarter's middle; None, with a warning, if Eurostat fails."""
    try:
        quarterly = eurostat_series("namq_10_pe", geo=FR_GEO)
    except Exception as exc:
        print(f"  Warning: Eurostat French population unavailable ({exc}); not drawn.")
        return None
    middles = quarterly.index.to_period("Q").start_time + pd.Timedelta(days=_QUARTER_MIDDLE_DAYS)
    return quarterly.set_axis(pd.DatetimeIndex(middles, name=DATE_COLUMN)).rename(POPULATION_COLUMN)
