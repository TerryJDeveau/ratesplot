"""Bank of Canada / Statistics Canada data pipelines.

Each ``fetch_cdn_*`` macro function returns a date-indexed frame (or ``None``
when the curve is deselected or unavailable), each value dated by the day it
describes: a quarterly figure by the quarter's last day, although the sources
date it by the first (``frames.at_quarter_end``), and a year-end one by
31 December. ``align_cdn_macro`` then forward-fills those values onto the
daily yield dates for plotting.

Debt, GDP and interest are each a chain of sources, joined oldest to newest
with ``joins.splice_archived_series`` (the newer source is never modified):

* older history baked from terminated sources (``cdn_archive_data``): GDP and
  interest from 1926, debt of all governments from 1933;
* for debt and interest, the 1961-1994 archive (national balance sheets and
  government sector accounts); and
* the live modern table, authoritative from where it starts (1961 for GDP,
  1990 for debt and interest).

Before 1933 only federal debt is recorded. It is kept as its own series
(``CDN_FEDERAL_DEBT_COLUMN``), drawn as a separate curve, rather than joined
to the aggregate, of which it is only about half.

With levels of government chosen (``--debt:LETTERS``), ``fetch_cdn_components``
replaces the aggregate debt and interest: each level is chained the same way
from its own history (see there).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .cdn_archive_data import (
    EMBEDDED_CDN_2Y_STAND_IN,
    EMBEDDED_CDN_5Y_STAND_IN,
    EMBEDDED_CDN_DEBT_HISTORY,
    EMBEDDED_CDN_DEBT_HISTORY_BY_LEVEL,
    EMBEDDED_CDN_EARLY_DEBT_HISTORY,
    EMBEDDED_CDN_EARLY_DEBT_HISTORY_BY_LEVEL,
    EMBEDDED_CDN_EARLY_INTEREST_HISTORY,
    EMBEDDED_CDN_EARLY_INTEREST_HISTORY_BY_LEVEL,
    EMBEDDED_CDN_FEDERAL_DEBT_HISTORY,
    EMBEDDED_CDN_GDP_HISTORY,
    EMBEDDED_CDN_INTEREST_HISTORY,
    EMBEDDED_CDN_INTEREST_HISTORY_BY_LEVEL,
    EMBEDDED_CDN_POPULATION_HISTORY,
)
from .baked import frame_with_recent_part, with_recent_part
from .cdn_hist_yields import build_cdn_hist_yields
from .config import (
    BOC_GROUP_URL,
    BOC_SERIES_URL,
    BOC_START_DATE,
    CDN_DEBT_COLUMN,
    CDN_FEDERAL_DEBT_COLUMN,
    CDN_INTEREST_COLUMN,
    CDN_MORTGAGE_HISTORY_TABLE,
    CDN_MORTGAGE_HISTORY_VECTOR,
    DATE_COLUMN,
    GDP_COLUMN,
    HTTP_POST_TIMEOUT_SECONDS,
    MILLION,
    POPULATION_COLUMN,
    RECENT_PART_REVISED,
    RECENT_PART_UNREVISED,
    STATCAN_CDN_DEBT_TABLE,
    STATCAN_CDN_DEBT_VECTOR,
    STATCAN_CDN_GDP_TABLE,
    STATCAN_CDN_GDP_VECTOR,
    STATCAN_CDN_INTEREST_TABLE,
    STATCAN_CDN_POPULATION_TABLE,
    STATCAN_CDN_POPULATION_VECTOR,
    STATCAN_TABLE_URL,
    STATCAN_TIMEOUT_SECONDS,
    STATCAN_WDS_URL,
    YIELD_COLUMNS,
    YIELD_TERMS,
    PlotConfig,
    component_column,
)
from .http import canadian_get, canadian_post, downloads_of, parse_boc_csv
from .joins import align_macro, chain, dated_by_quarter_end, embedded_frame
from .us_data import fred_series

# The Bank of Canada's Valet series are baked (batch 19.2) under
# ``ratesplot/data/boc/`` (``tools/bake_archives.py --only boc``).
BOC_BAKED_SOURCE = "boc"
# Valet gives a series from this date: it precedes every series' first value,
# so a request from it is the whole series (what the bake writes, and what
# the policy and mortgage rates are drawn from).
BOC_VALET_FROM = "1900-01-01"

# Bank of Canada Valet series codes -> chart column names. The 3-month T-bill
# is not part of the benchmark group, so it is fetched as a separate series.
# The group's 3- and 7-year (batch 9.3) begin on 2001-01-02, as the others'
# daily values do; the group's real return bond is not a yield term.
BOC_BENCHMARK_GROUP = "bond_yields_benchmark"
BOC_BENCHMARK_COLUMNS = {
    "BD.CDN.2YR.DQ.YLD": "2-Year",
    "BD.CDN.3YR.DQ.YLD": "3-Year",
    "BD.CDN.5YR.DQ.YLD": "5-Year",
    "BD.CDN.7YR.DQ.YLD": "7-Year",
    "BD.CDN.10YR.DQ.YLD": "10-Year",
    "BD.CDN.LONG.DQ.YLD": "30-Year",
}
# A Valet group -> the series of it the program reads, baked one file each
# (batch 19.2); the group is still asked for in one request.
BOC_GROUP_CODES = {BOC_BENCHMARK_GROUP: tuple(BOC_BENCHMARK_COLUMNS)}
# How ``http.parse_boc_csv`` names a Valet answer's dates; the bake's own
# name (``config.DATE_COLUMN``) is not kept, so a reader sees what it did
# before the bake.
_VALET_DATES = "date"
# The other treasury bills (batch 9.3; Terry, 2026-10-12: "a big gap" between
# 3 months and 2 years): daily mid-market yields from 2001-01-02, each its own
# series, so each is fetched only when chosen. Measured 2026-10-20.
BOC_BILL_SERIES = {
    "1-Month": "TB.CDN.30D.MID",
    "6-Month": "TB.CDN.180D.MID",
    "1-Year": "TB.CDN.1Y.MID",
}
# Where the terms with no history before the daily series begin (the PDF
# tables of 1919-2000 have the five of YIELD_COLUMNS only).
CDN_NEW_TERMS_START = pd.Timestamp("2001-01-02")
# The 3-month after the PDF history (batch 9.2): the daily mid-market yield
# of the 3-month treasury bill, from 2001-01-02, as the benchmarks are. It
# replaces the bi-weekly auction average, which is kept only before the
# daily begins: its two auctions of December 2000, after the history's last
# month. Measured 2026-10-20: on the 676 auction days since 2001 the two
# differ by a median 0.01 points, at most 0.34. Each stands in for the
# other, with a warning, if it fails (``_cdn_3_month``).
BOC_3M_TBILL_SERIES = "TB.CDN.90D.MID"
BOC_3M_AUCTION_SERIES = "V80691303"
# Baked term-band yields standing in for a benchmark before it begins.
_YIELD_STAND_INS = {"2-Year": EMBEDDED_CDN_2Y_STAND_IN, "5-Year": EMBEDDED_CDN_5Y_STAND_IN}
FRED_CDN_GDP_SERIES = "NGDPSAXDCCAQ"  # fallback if the StatCan GDP table fails
# Canada's yield columns, in term order (config.YIELD_TERMS): all but the 20-year.
CDN_YIELD_COLUMNS = tuple(
    column for column in YIELD_TERMS.values()
    if column in YIELD_COLUMNS or column in BOC_BENCHMARK_COLUMNS.values() or column in BOC_BILL_SERIES
)

# First observation of each Canadian input, used to warn when ``--start`` is earlier.
CANADIAN_SERIES_EARLIEST = {
    "3-Month Yield (Bank of Canada historical table)": pd.Timestamp("1934-03-01"),
    "2-Year Yield (1-3 year average before 1982-06)": pd.Timestamp(EMBEDDED_CDN_2Y_STAND_IN[0][0]),
    "5-Year Yield (3-5 year average before 1980-11)": pd.Timestamp(EMBEDDED_CDN_5Y_STAND_IN[0][0]),
    "10-Year Yield (Bank of Canada historical table)": pd.Timestamp("1951-01-01"),
    "30-Year Yield / Over 10 Years (Bank of Canada historical table)": pd.Timestamp("1919-01-01"),
    # The macro series begin where their oldest baked source does, on its own
    # date (a quarterly one's first quarter starts there, though its value is
    # drawn from the quarter's end: see _dated_by_quarter_end).
    "Federal CDN Public Debt (alone, before 1933)": pd.Timestamp(EMBEDDED_CDN_FEDERAL_DEBT_HISTORY[0][0]),
    "Aggregate CDN Public Debt": pd.Timestamp(EMBEDDED_CDN_EARLY_DEBT_HISTORY[0][0]),
    "TTM Nominal GDP": pd.Timestamp(EMBEDDED_CDN_GDP_HISTORY[0][0]),
    "TTM Interest Payable": pd.Timestamp(EMBEDDED_CDN_EARLY_INTEREST_HISTORY[0][0]),
}


def cdn_series_earliest(config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of the Canadian inputs, by name, for the coverage warning.

    The five default terms and the macro series always, as before the terms
    could be chosen (``CANADIAN_SERIES_EARLIEST``); then each chosen term
    without the PDF history (batch 9.3), and those the spreads are taken
    from, from 2001.
    """
    terms = set(config.yield_terms) | ({term for pair in config.spread_pairs for term in pair} if config.spreads else set())
    newer = {
        f"{column} Yield (Bank of Canada, daily)": CDN_NEW_TERMS_START
        for term, column in YIELD_TERMS.items()
        if term in terms and column in CDN_YIELD_COLUMNS and column not in YIELD_COLUMNS
    }
    return {**CANADIAN_SERIES_EARLIEST, **newer}


# ---------------------------------------------------------------------------
# Raw source access
# ---------------------------------------------------------------------------


def valet_group_download(group: str, start: str = BOC_VALET_FROM) -> pd.DataFrame:
    """Ask Valet for an observation group from ``start`` on (its every value by default): a date-indexed frame, a float column per series.

    One request (cached and kept as the others are). A day the group lists
    without a value in a series is NaN in that column. An answer with no
    values raises: no group the program reads is empty from any date it
    asks for, so an empty one is not to be drawn as the end of the group.
    """
    response = canadian_get(BOC_GROUP_URL.format(group=group), params={"start_date": start})
    frame = parse_boc_csv(response.text).apply(pd.to_numeric, errors="coerce")
    if frame.isna().all().all():
        raise ValueError(f"Valet gave no values of the group {group} from {start}")
    return frame


def valet_download(series_code: str, start: str = BOC_VALET_FROM) -> pd.Series:
    """Ask Valet for one series from ``start`` on (its every value by default): a date-indexed numeric series, named by its code.

    One request (cached and kept as the others are). A day listed without
    a value is NaN. An answer with no values raises, as for a group.
    """
    response = canadian_get(BOC_SERIES_URL.format(series_code=series_code), params={"start_date": start})
    frame = parse_boc_csv(response.text)
    values = pd.to_numeric(frame.iloc[:, 0], errors="coerce")
    if values.isna().all():
        raise ValueError(f"Valet gave no values of {series_code} from {start}")
    return values


def boc_valet_group(group: str, start: str = BOC_START_DATE) -> pd.DataFrame:
    """Return the series of a Bank of Canada Valet group that the program reads (``BOC_GROUP_CODES``), from ``start`` on: a column each.

    Batch 19.2 (``ratesplot.baked``): their history is in
    ``ratesplot/data/boc/``, and only the group's last two months are asked
    for, in one request; a group not yet baked is asked for whole from
    ``start``, every column of it. If Valet fails, the baked history alone,
    to its last date, with a warning.
    """
    frame = frame_with_recent_part(
        BOC_BAKED_SOURCE,
        BOC_GROUP_CODES[group],
        f"Bank of Canada {group}",
        lambda since: valet_group_download(group, start if since is None else f"{since:%Y-%m-%d}"),
        RECENT_PART_UNREVISED,
    )
    return frame.loc[frame.index >= pd.Timestamp(start)].rename_axis(_VALET_DATES)


def boc_valet_series(series_code: str, start: str = BOC_START_DATE, *, revised: bool = False) -> pd.Series:
    """Return one Bank of Canada Valet series from ``start`` on, date-indexed and numeric: its baked history, then its recent part from Valet.

    Batch 19.2 (``ratesplot.baked``): the history is in
    ``ratesplot/data/boc/``, and only the last two months are asked for
    (``revised``: 24 months, for a series Valet may revise); a series not yet
    baked is asked for whole from ``start``. If Valet fails, the baked
    history alone, to its last date, with a warning. The bake holds the
    whole series, cut here at ``start``: measured 2026-10-22, Valet's answer
    from a date is the whole series cut there.
    """
    values = with_recent_part(
        BOC_BAKED_SOURCE,
        series_code,
        f"Bank of Canada {series_code}",
        lambda since: valet_download(series_code, start if since is None else f"{since:%Y-%m-%d}"),
        RECENT_PART_REVISED if revised else RECENT_PART_UNREVISED,
    )
    return values.loc[values.index >= pd.Timestamp(start)].rename_axis(_VALET_DATES)


# The levels in the live GFS table 10-10-0015 (its fifth sector, the CPP and
# QPP, is not a level of government and is left out, as from "n").
_GFS_SECTORS = {"f": "Federal government", "p": "Provincial and territorial government", "m": "Local government"}
_GFS_ITEM_COLUMN = "Statement of government operations and balance sheet"
# A level's gross debt: all its liabilities except equity, the GFS definition
# that the aggregate (36-10-0467 "Debt") also follows.
_GFS_DEBT_ITEMS = (
    "Special drawing rights (SDRs), liabilities",
    "Currency and deposits, liabilities",
    "Debt securities, liabilities",
    "Loans, liabilities",
    "Insurance and pension schemes, liabilities",
    "Other accounts payable, liabilities",
)
# The vectors the program reads of the GFS table: the consolidated interest
# (``fetch_cdn_interest``), and each level's interest and the six liabilities
# that make its debt (``fetch_cdn_components``). Measured 2026-10-22.
GFS_VECTORS = {
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


def _debt_rows(table: pd.DataFrame) -> pd.Series:
    return table["Estimates"].eq("Debt")


def _gdp_rows(table: pd.DataFrame) -> pd.Series:
    return (
        table["Estimates"].str.contains("Gross domestic product at market prices", case=False, na=False)
        & table["Prices"].str.contains("Current prices", case=False, na=False)
        & table["Seasonal adjustment"].str.contains("Seasonally adjusted at annual rates", case=False, na=False)
    )


def _gfs_rows(sector: str, item: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda table: table["Government sectors"].eq(sector) & table[_GFS_ITEM_COLUMN].eq(item)


def _canada_rows(table: pd.DataFrame) -> pd.Series:
    return table["GEO"].eq("Canada")


@dataclass(frozen=True)
class StatcanRead:
    """What the program reads of one live Statistics Canada table (``STATCAN_SERIES_READ``).

    ``vectors``: each vector read, and how its rows are found in the whole
    table, by the table's own labels (the selections the program has always
    made). ``unit``: the table's ``UOM`` for them; ``scale``: its
    ``SCALAR_ID`` (6 millions, 0 units), which WDS calls ``scalarFactorCode``.
    """

    unit: str
    scale: int
    vectors: dict[str, Callable[[pd.DataFrame], pd.Series]]


# What the program reads of each live Statistics Canada table. Measured
# 2026-10-22, for all 26 vectors: each selection is one vector, one row per
# period, every period with a value, in the unit and scale given here. They
# are baked (batch 19.2) under ``ratesplot/data/statcan/``
# (``tools/bake_archives.py --only statcan``), a file per vector, named by it;
# one request answers every vector of a table.
STATCAN_SERIES_READ = {
    STATCAN_CDN_DEBT_TABLE: StatcanRead("Dollars", 6, {STATCAN_CDN_DEBT_VECTOR: _debt_rows}),
    STATCAN_CDN_GDP_TABLE: StatcanRead("Dollars", 6, {STATCAN_CDN_GDP_VECTOR: _gdp_rows}),
    STATCAN_CDN_INTEREST_TABLE: StatcanRead(
        "Dollars", 6, {vector: _gfs_rows(sector, item) for (sector, item), vector in GFS_VECTORS.items()}
    ),
    STATCAN_CDN_POPULATION_TABLE: StatcanRead("Persons", 0, {STATCAN_CDN_POPULATION_VECTOR: _canada_rows}),
    CDN_MORTGAGE_HISTORY_TABLE: StatcanRead("Percent", 0, {CDN_MORTGAGE_HISTORY_VECTOR: _canada_rows}),
}
STATCAN_BAKED_SOURCE = "statcan"


def statcan_zip_table_with_metadata(table_id: str) -> tuple[pd.DataFrame, str]:
    """Download a full Statistics Canada table ZIP and return ``(data, metadata_csv)``.

    The archive holds the data CSV plus a ``*_MetaData.csv`` describing the
    table's dimensions and members; the latter is returned as raw text.
    """
    with downloads_of(f"Statistics Canada table {table_id}"):
        response = canadian_get(STATCAN_TABLE_URL.format(table_id=table_id), timeout=STATCAN_TIMEOUT_SECONDS)

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        data_name = next(name for name in names if "MetaData" not in name)
        meta_name = next((name for name in names if "MetaData" in name), None)
        with archive.open(data_name) as csv_file:
            data = pd.read_csv(csv_file, low_memory=False)
        metadata = archive.read(meta_name).decode("utf-8-sig", errors="replace") if meta_name else ""
    return data, metadata


def statcan_zip_table(table_id: str) -> pd.DataFrame:
    """Download a full Statistics Canada table (CSV inside a ZIP) as a frame."""
    return statcan_zip_table_with_metadata(table_id)[0]


def _statcan_vectors(table: pd.DataFrame, table_id: str) -> pd.DataFrame:
    """The vectors read of a whole Statistics Canada table (``STATCAN_SERIES_READ``), a column each, in the table's unit.

    Each vector's rows are found by the table's labels and checked, not
    trusted: the vector declared and no other, the declared unit and scale,
    one row per period; anything else raises. A period is dated by its first
    day, as Statistics Canada dates it (``REF_DATE`` is ``YYYY-MM``, or
    ``YYYY-MM-DD`` in 17-10-0009); a row without a value is NaN.
    """
    read = STATCAN_SERIES_READ[table_id]
    columns = {}
    for vector, rows_of in read.vectors.items():
        rows = table.loc[rows_of(table)]
        found = sorted(set(rows["VECTOR"].astype(str)))
        if found != [vector]:
            raise ValueError(f"Statistics Canada {table_id}: expected the rows of {vector}, found {found or 'none'}")
        units = sorted(set(rows["UOM"].astype(str).str.strip())), sorted(set(rows["SCALAR_ID"]))
        if units != ([read.unit], [read.scale]):
            raise ValueError(f"Statistics Canada {table_id} {vector}: expected {read.unit} at scale {read.scale}, found {units}")
        if rows["REF_DATE"].duplicated().any():
            raise ValueError(f"Statistics Canada {table_id} {vector}: expected one row per period")
        text = rows["REF_DATE"].astype(str)
        dates = pd.DatetimeIndex(pd.to_datetime(text.where(text.str.len() > 7, text + "-01")), name=DATE_COLUMN)
        columns[vector] = pd.Series(pd.to_numeric(rows["VALUE"], errors="coerce").to_numpy(dtype=float), index=dates)
    return pd.concat(columns, axis=1).sort_index()


def statcan_download(table_id: str) -> pd.DataFrame:
    """Ask Statistics Canada for the vectors read of one live table (``STATCAN_SERIES_READ``): a column each, by date, in the table's unit.

    One request, the table's ZIP (cached and kept as the others are), each
    vector's rows found by the table's labels (``_statcan_vectors``).
    """
    return _statcan_vectors(statcan_zip_table(table_id), table_id)


def statcan_wds_vectors(vector_ids: Iterable[str | int], *, latest_n: int = 250) -> pd.DataFrame:
    """Fetch the latest ``latest_n`` observations of StatCan WDS vectors.

    Returns one column per vector, named ``v<id>``. Vectors that the service
    reports as failed are skipped; if none succeed a ``RuntimeError`` is raised.
    """
    payload = [
        {"vectorId": int(str(vector).lstrip("vV")), "latestN": latest_n} for vector in vector_ids
    ]
    with downloads_of("Statistics Canada vectors (WDS)"):
        response = canadian_post(STATCAN_WDS_URL, payload, timeout=HTTP_POST_TIMEOUT_SECONDS)

    frames: list[pd.DataFrame] = []
    for item in response.json():
        if item.get("status") != "SUCCESS":
            continue
        obj = item["object"]
        points = obj.get("vectorDataPoint", [])
        if not points:
            continue

        column = f"v{obj['vectorId']}"
        frame = pd.DataFrame(points)
        frame[DATE_COLUMN] = pd.to_datetime(frame["refPer"])
        frame[column] = pd.to_numeric(frame["value"], errors="coerce")
        frames.append(frame.set_index(DATE_COLUMN)[[column]])

    if not frames:
        raise RuntimeError("No data returned from WDS")
    return pd.concat(frames, axis=1).sort_index()


def _statcan_quarterly(values: pd.Series, column: str) -> pd.DataFrame:
    """Return one quarterly StatCan vector (``statcan_download``), in millions of dollars, in dollars as ``column``.

    Indexed by quarter start (``QS``), the source's own dating, like the baked
    histories, so all Canadian macro series share one calendar while they are
    joined. The fetchers then date the joined series by the quarter's end
    (``_dated_by_quarter_end``).
    """
    return (values * MILLION).rename(column).to_frame().resample("QS").last()


# ---------------------------------------------------------------------------
# Per-curve fetchers
# ---------------------------------------------------------------------------


def with_yield_stand_ins(historical: pd.DataFrame) -> pd.DataFrame:
    """Return ``historical`` with the 2- and 5-year columns extended back by their stand-ins.

    The Bank of Canada's 2- and 5-year benchmarks begin in 1982-06 and
    1980-11. Before that its average yields for the 1-3 and 3-5 year bands
    are used, the same kind of stand-in as the 5-10 and over-10 year bands
    that already supply the 10- and 30-year history. Over 1982-2000 the 1-3
    year band averages 0.08 points above the 2-year benchmark and the 3-5
    year band 0.00 points above the 5-year. Only months before a benchmark's
    first value are filled.
    """
    result = historical.copy()
    for column, rows in _YIELD_STAND_INS.items():
        stand_in = embedded_frame(rows, column)
        if stand_in is None or column not in result.columns:
            continue
        first_benchmark = result[column].first_valid_index()
        early = stand_in[column]
        if first_benchmark is not None:
            early = early.loc[early.index < first_benchmark]
        result[column] = result[column].combine_first(early)
    return result


def _cdn_3_month() -> pd.Series | None:
    """Return the 3-month yield after the PDF history: the auction average until the daily yield begins, then the daily.

    See ``BOC_3M_TBILL_SERIES``. Either alone, with a warning, if the other
    fails (or answers with no values); None, with a warning, if both do.
    """
    found: dict[str, pd.Series | None] = {}
    for code, name in ((BOC_3M_TBILL_SERIES, "daily 3-month T-bill yield"), (BOC_3M_AUCTION_SERIES, "3-month T-bill auctions")):
        try:
            values = boc_valet_series(code).dropna()
            if values.empty:
                raise ValueError("no values")
        except Exception as exc:
            print(f"  Warning: Bank of Canada {name} ({code}) unavailable ({exc}).")
            values = None
        found[code] = values
    daily, auctions = found[BOC_3M_TBILL_SERIES], found[BOC_3M_AUCTION_SERIES]
    if daily is None:
        print("  Warning: " + ("the 3-month auction averages instead, one every second week." if auctions is not None
                               else "no Canadian 3-month yield after 2000; drawn without it."))
        return auctions
    if auctions is None:
        return daily
    return pd.concat([auctions.loc[auctions.index < daily.index[0]], daily])


def fetch_cdn_yields(config: PlotConfig) -> pd.DataFrame:
    """Return Canadian benchmark yields: transcribed history through 2000, live after.

    The 2- and 5-year history is extended back by stand-ins (see
    ``with_yield_stand_ins``). The result is date-indexed with the chosen
    yield columns (``config.yield_columns``) that Canada has
    (``CDN_YIELD_COLUMNS``), and those the spreads are taken from
    (``config.fetched_yield_columns``), trimmed to the configured window.
    The terms outside the default five begin in 2001 (batch 9.3). A chosen
    term it does not have (--yields:20) is named, and the chart drawn
    without it.
    """
    chosen = [column for column in config.fetched_yield_columns if column in CDN_YIELD_COLUMNS]
    absent = [column for column in config.yield_columns if column not in CDN_YIELD_COLUMNS]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no Canadian {', '.join(absent)} yield; the Canadian chart is drawn without it.")
    if not chosen:
        return pd.DataFrame()

    with downloads_of("Bank of Canada benchmark yields"):
        yields = boc_valet_group(BOC_BENCHMARK_GROUP).rename(columns=BOC_BENCHMARK_COLUMNS)
        three_month = _cdn_3_month()
        if three_month is not None:
            yields = yields.join(three_month.rename("3-Month"), how="outer")
        for column in (column for column in chosen if column in BOC_BILL_SERIES):
            code = BOC_BILL_SERIES[column]
            try:
                yields = yields.join(boc_valet_series(code).rename(column), how="outer")
            except Exception as exc:
                print(f"  Warning: Bank of Canada {column} T-bill yield ({code}) unavailable ({exc}); drawn without it.")

    available = [column for column in CDN_YIELD_COLUMNS if column in yields.columns]
    # Short forward-fill bridges holidays and single missing prints only.
    yields = yields[available].dropna(how="all").ffill(limit=3)

    historical = with_yield_stand_ins(build_cdn_hist_yields())
    live_part = yields[yields.index > historical.index.max()]
    all_yields = pd.concat([historical, live_part]).sort_index().ffill(limit=3)
    return all_yields.loc[config.start : config.end, [column for column in all_yields.columns if column in chosen]]


def fetch_cdn_debt(config: PlotConfig) -> pd.DataFrame | None:
    """Return general-government gross debt, and federal debt alone before the aggregate begins.

    The aggregate (``CDN_DEBT_COLUMN``) chains the 1933-1975 history, the
    1961-1994 archive and the live table. ``CDN_FEDERAL_DEBT_COLUMN`` holds
    the federal-only years (1867-1932) as they are: a different quantity, so
    not scaled to the aggregate.
    """
    if not config.include_debt:
        return None

    try:
        modern = _statcan_quarterly(statcan_download(STATCAN_CDN_DEBT_TABLE)[STATCAN_CDN_DEBT_VECTOR], CDN_DEBT_COLUMN)
    except Exception as exc:
        print(f"  Warning: StatCan debt table failed ({exc}); trying WDS vector fallback …")
        try:
            wds = statcan_wds_vectors([STATCAN_CDN_DEBT_VECTOR], latest_n=250)
            modern = (wds[STATCAN_CDN_DEBT_VECTOR] * MILLION).rename(CDN_DEBT_COLUMN).to_frame().resample("QS").last()
        except Exception as exc2:
            print(f"  Warning: WDS fallback failed ({exc2}); using the baked history only (to 1994).")
            modern = None

    aggregate = chain(
        (
            embedded_frame(EMBEDDED_CDN_EARLY_DEBT_HISTORY, CDN_DEBT_COLUMN),
            embedded_frame(EMBEDDED_CDN_DEBT_HISTORY, CDN_DEBT_COLUMN),
            modern,
        ),
        CDN_DEBT_COLUMN,
        annual_historical=True,
    )
    federal_only = embedded_frame(EMBEDDED_CDN_FEDERAL_DEBT_HISTORY, CDN_FEDERAL_DEBT_COLUMN)
    parts = [dated_by_quarter_end(part) for part in (aggregate, federal_only) if part is not None]
    return pd.concat(parts, axis=1).sort_index() if parts else None


def fetch_cdn_gdp(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: the baked 1926-1994 history joined to the live table."""
    if not config.needs_gdp:
        return None

    history = embedded_frame(EMBEDDED_CDN_GDP_HISTORY, GDP_COLUMN)
    live = _fetch_live_cdn_gdp()
    if live is None and history is not None:
        print("  Warning: using the baked GDP history only (to 1994).")
    return dated_by_quarter_end(chain((history, live), GDP_COLUMN, annual_historical=False))


def _fetch_live_cdn_gdp() -> pd.DataFrame | None:
    """Return live TTM nominal GDP (mean of four SAAR quarters), or None if every source fails."""
    try:
        saar = _statcan_quarterly(statcan_download(STATCAN_CDN_GDP_TABLE)[STATCAN_CDN_GDP_VECTOR], "GDP_SAAR")
    except Exception as exc:
        print(f"  Warning: StatCan GDP table failed ({exc}); trying FRED fallback …")
        try:
            # Baked, and revised as GDP is (batch 19.2): 24 months asked for.
            fred = fred_series(FRED_CDN_GDP_SERIES, revised=True).set_index(DATE_COLUMN)
            saar = (fred.iloc[:, 0] * MILLION).rename("GDP_SAAR").to_frame().resample("QS").last()
        except Exception as exc2:
            print(f"  Warning: FRED GDP fallback failed ({exc2}).")
            return None

    # A SAAR value is already an annual rate, so the TTM level is the 4-quarter mean.
    return saar["GDP_SAAR"].rolling(4).mean().rename(GDP_COLUMN).to_frame()


def fetch_cdn_interest(config: PlotConfig) -> pd.DataFrame | None:
    """Return TTM public-debt interest: the 1926 history, the 1961-1994 archive and the live GFS table."""
    if not config.include_interest:
        return None

    try:
        consolidated = statcan_download(STATCAN_CDN_INTEREST_TABLE)[GFS_VECTORS[("Consolidated government", "Interest")]]
        quarterly = _statcan_quarterly(consolidated, "Interest_q")
        # The GFS table reports actual quarterly flows (not annualised), so TTM is a 4-quarter sum.
        modern = quarterly["Interest_q"].rolling(4).sum().rename(CDN_INTEREST_COLUMN).to_frame()
    except Exception as exc:
        print(f"  Warning: StatCan interest table failed ({exc}); using the baked history only (to 1994).")
        modern = None

    return dated_by_quarter_end(
        chain(
            (
                embedded_frame(EMBEDDED_CDN_EARLY_INTEREST_HISTORY, CDN_INTEREST_COLUMN),
                embedded_frame(EMBEDDED_CDN_INTEREST_HISTORY, CDN_INTEREST_COLUMN),
                modern,
            ),
            CDN_INTEREST_COLUMN,
            annual_historical=False,
        )
    )


# ---------------------------------------------------------------------------
# Components: debt and interest by level of government (--debt:LETTERS)
# ---------------------------------------------------------------------------

# The levels in the live GFS table 10-10-0015, and the items that make a
# level's debt: ``_GFS_SECTORS`` and ``_GFS_DEBT_ITEMS``, with the vectors read
# of it (``GFS_VECTORS``), under "Raw source access" above.


def _with_non_federal(levels: dict[str, pd.DataFrame | None], column: str) -> dict[str, pd.DataFrame | None]:
    """Add "n" (non-federal) = provincial + local, on the dates both exist."""
    provincial, local = levels.get("p"), levels.get("m")
    non_federal = None
    if provincial is not None and local is not None:
        non_federal = (provincial[column] + local[column]).dropna().rename(column).to_frame()
    return {**levels, "n": non_federal}


def _embedded_levels(by_level: dict[str, list[tuple[str, float]]], column: str) -> dict[str, pd.DataFrame | None]:
    """Return a baked by-level dictionary as frames keyed "f", "p", "m", plus "n"."""
    return _with_non_federal({key: embedded_frame(rows, column) for key, rows in by_level.items()}, column)


def _gfs_levels(table: pd.DataFrame, items: tuple[str, ...], column: str) -> dict[str, pd.DataFrame | None]:
    """Return each level's quarterly sum of ``items`` from the GFS table's vectors (``statcan_download``), in dollars, plus "n"."""
    levels: dict[str, pd.DataFrame | None] = {}
    for key, sector in _GFS_SECTORS.items():
        parts = [_statcan_quarterly(table[GFS_VECTORS[(sector, item)]], column)[column] for item in items]
        levels[key] = sum(parts[1:], parts[0]).rename(column).to_frame()
    return _with_non_federal(levels, column)


def fetch_cdn_components(config: PlotConfig) -> pd.DataFrame | None:
    """Return debt and/or interest for each level in ``config.components``, one ``component_column`` each.

    Each level is chained like its aggregate, oldest first, "n" being
    provincial + local within each source before the joins:

    * debt: *Historical Statistics of Canada* (federal from 1867, provincial
      and local from 1933), the 1961-1994 balance sheets, then the live GFS
      table 10-10-0015 (from 1990), where a level's debt is all its
      liabilities except equity;
    * interest: the 1968-SNA accounts (from 1926), the 1961-1994 sector
      accounts, then the live GFS interest (quarterly flows, TTM = four-quarter sum).

    The levels are each government's own figures. The consolidated aggregate
    nets out what one government owes another, so the levels need not add
    up to it. Returns None when neither curve is selected.
    """
    letters = config.components
    if not letters or not (config.include_debt or config.include_interest):
        return None
    try:
        table = statcan_download(STATCAN_CDN_INTEREST_TABLE)
    except Exception as exc:
        print(f"  Warning: StatCan GFS table failed ({exc}); levels of government shown only to 1994.")
        table = None

    columns: list[pd.Series] = []
    if config.include_debt:
        early = _embedded_levels(EMBEDDED_CDN_EARLY_DEBT_HISTORY_BY_LEVEL, CDN_DEBT_COLUMN)
        archive = _embedded_levels(EMBEDDED_CDN_DEBT_HISTORY_BY_LEVEL, CDN_DEBT_COLUMN)
        live = _gfs_levels(table, _GFS_DEBT_ITEMS, CDN_DEBT_COLUMN) if table is not None else {}
        for letter in letters:
            chained = chain(
                (early.get(letter), archive.get(letter), live.get(letter)), CDN_DEBT_COLUMN, annual_historical=True
            )
            if chained is not None:
                columns.append(chained[CDN_DEBT_COLUMN].rename(component_column("debt", letter)))
    if config.include_interest:
        early = _embedded_levels(EMBEDDED_CDN_EARLY_INTEREST_HISTORY_BY_LEVEL, CDN_INTEREST_COLUMN)
        archive = _embedded_levels(EMBEDDED_CDN_INTEREST_HISTORY_BY_LEVEL, CDN_INTEREST_COLUMN)
        live: dict[str, pd.DataFrame | None] = {}
        if table is not None:
            # The GFS table reports actual quarterly flows, so TTM is a 4-quarter sum.
            quarterly = _gfs_levels(table, ("Interest",), CDN_INTEREST_COLUMN)
            live = {key: frame[CDN_INTEREST_COLUMN].rolling(4).sum().to_frame() for key, frame in quarterly.items() if frame is not None}
        for letter in letters:
            chained = chain(
                (early.get(letter), archive.get(letter), live.get(letter)), CDN_INTEREST_COLUMN, annual_historical=False
            )
            if chained is not None:
                columns.append(chained[CDN_INTEREST_COLUMN].rename(component_column("interest", letter)))
    # Each series is moved before they are put side by side: interest dated
    # 1 October and debt dated 31 December would otherwise share a row twice.
    return pd.concat([dated_by_quarter_end(column) for column in columns], axis=1).sort_index() if columns else None


def fetch_cdn_population() -> pd.Series | None:
    """Return the population of Canada for -p: baked annual estimates until the live quarterly table begins.

    The estimates (as at 1 June, 1867-1977) and the live table (quarterly
    from 1946, first of the quarter) differ by about 0.2 % where both exist,
    mostly the month between their reference dates, too little to need a
    join: the baked years simply precede the live ones. Persons.
    """
    history = embedded_frame(EMBEDDED_CDN_POPULATION_HISTORY, POPULATION_COLUMN)
    try:
        # Canada's rows, one per quarter, in persons (checked by statcan_download).
        live = statcan_download(STATCAN_CDN_POPULATION_TABLE)[STATCAN_CDN_POPULATION_VECTOR].dropna().rename(None)
    except Exception as exc:
        print(f"  Warning: StatCan population table failed ({exc}); using the baked estimates only (to 1977).")
        live = None

    parts: list[pd.Series] = []
    if history is not None:
        early = history[POPULATION_COLUMN]
        parts.append(early if live is None or live.empty else early.loc[early.index < live.index.min()])
    if live is not None:
        parts.append(live)
    return pd.concat(parts).sort_index().rename(POPULATION_COLUMN) if parts else None


def align_cdn_macro(
    yields_all: pd.DataFrame, series: Iterable[pd.DataFrame | None], config: PlotConfig
) -> pd.DataFrame:
    """Forward-fill the Canadian macro series onto the yield dates (``joins.align_macro``).

    Federal debt alone is kept only until the aggregate begins: forward
    filling would otherwise carry its 1932 value on for ever.
    """
    aligned = align_macro(yields_all, series, config)
    if CDN_FEDERAL_DEBT_COLUMN in aligned.columns and CDN_DEBT_COLUMN in aligned.columns:
        aligned.loc[aligned[CDN_DEBT_COLUMN].notna(), CDN_FEDERAL_DEBT_COLUMN] = np.nan
    return aligned
