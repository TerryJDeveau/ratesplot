"""Japan (batch 14.3, decision 188): its readers, on two hosts the program had not asked before (Terry's decision 183).

The sources, measured 2026-11-26 from Buddug (the probe and the build's own
measurement, ``G:\\Research\\Claude\\ratesplot_jp``), each with python-requests'
own headers (``config.JP_SESSION``), never varied; neither host has a
robots.txt:

* Yields: the Ministry of Finance's JGB yields at constant maturities, daily,
  in two CSV files: the history to the last month's end
  (``MOF_HISTORY_URL``, 1.2 MB) and the current month to the day before
  (``MOF_CURRENT_URL``, 2 KB), no day in both. One title line, then
  ``Date,1Y,...,10Y,15Y,20Y,25Y,30Y,40Y``, dates ``YYYY/M/D``, ``-`` for none;
  the current month's file ends with a note in Japanese (cp932). The
  program's terms 1, 2, 3, 5, 7, 10, 20 and 30 years (``JP_YIELD_COLUMNS``):
  1 to 7 years from 1974-09-24, 10 years from 1986-07-05, 20 from 1986-12-01,
  30 from 1999-09-02. Nothing before the 10-year's first day (decision 188 (2)).
* The policy rate (decision 188 (3)): the Bank of Japan's uncollateralized
  overnight call rate, its operating target most years since 1995 and since
  2024: daily from 1998-01-05 (FM01 ``STRDCLUCON``), its monthly averages
  from 1985-07 before (FM02 ``STRACLUCON``), and the collateralized call
  rate's monthly averages from 1960-01 before that (``STRACLCOON``). The Bank
  publishes no series of the target itself. The call rate is Japan's
  overnight market rate too: ticked with "target", "market" draws nothing
  more (``rates``).
* Debt (decision 188 (4)): general government's loans and debt securities
  (liabilities) in the flow of funds, 100 million yen, quarterly from 1997 Q4
  (``FOF_FFAS420L200`` + ``L300``), and before it the fiscal years' March
  figures from March 1981 (``FOF_FFYS420L200`` + ``L300``: the Bank's year Y
  is the fiscal year ending March Y+1, equal to the quarterly (Y+1) Q1 in all
  29 years both hold). Not consolidated: central government (x = 1), local
  governments (2) and the social security funds (3) add up to it exactly.
  ``L900``, "Total", holds the difference between assets and liabilities: not
  a debt. 1,273.8 trillion yen at 2026 Q2, 185 % of GDP.
* GDP (decision 188 (5)): FRED's ``JPNNGDP``, nominal, seasonally adjusted
  at annual rates, billions of yen, quarterly from 1994 Q1; equal to the
  Cabinet Office's own table in all 131 quarters to 2026 Q3. The trailing
  year is the mean of four quarters' annual rates, as the U.S.' and Canada's.
* Interest: none quarterly (the IMF's QGFS has no Japan; the Cabinet Office's
  accounts are yearly by fiscal year): left out at first (decision 188 (9)).
* The balance of payments (decision 188 (6), ``payments``): the Bank of
  Japan's BP01 (BPM6, monthly, 100 million yen, not seasonally adjusted, from
  1996-01): credits are goods exports, services credit, primary and
  secondary income credit; debits the four debits. Credits less debits equal
  the current account balance in all 369 months, as do goods and services
  the trade balance. Twelve-month sums each month, as Germany's.
* Consumer prices (decision 188 (7)): the IMF's index for Japan, all items,
  2020 = 100, monthly from 1955-01, not seasonally adjusted
  (``IMF_CPI_KEY``), on the host the program already asks for Canada's
  stand-ins; proportional to the OECD's index on FRED (stopped 2021-06).
* Population (decision 188 (8)): FRED's ``POPTOTJPA647NWDB`` (the World
  Bank's midyear estimates), annual from 1960, each year dated by its middle.

Every series is baked (``ratesplot/data/mof``, ``boj``, ``imf``, and FRED's
three with FRED's), so a drawing asks for its recent part alone
(``baked.with_recent_part``): the Ministry's current month's file alone while
the bake reaches this month, the Bank's series from a date. A series not
baked is asked for whole.
"""
from __future__ import annotations

import csv
import io
import re
from xml.etree import ElementTree

import pandas as pd

from .baked import frame_with_recent_part, read_series, with_recent_part
from .config import (
    BOJ_DATA_URL,
    COMPONENT_LETTERS,
    DATE_COLUMN,
    GDP_COLUMN,
    IMF_SDMX_URL,
    JP_DEBT_COLUMN,
    MOF_CURRENT_URL,
    MOF_HISTORY_URL,
    POPULATION_COLUMN,
    RECENT_PART_REVISED,
    RECENT_PART_UNREVISED,
    PlotConfig,
    component_column,
)
from .de_data import YIELD_HISTORY_ATTR
from .de_data import _DAILY_FILL_LIMIT  # Germany's daily yields' fill: a longer gap is a break
from .http import downloads_of, jp_get
from .us_data import fred_series

# The baked files of each new source: ``ratesplot/data/mof/TERM.csv``, ``boj/CODE.csv``, ``imf/KEY.csv``.
MOF_BAKED_SOURCE = "mof"
BOJ_BAKED_SOURCE = "boj"
IMF_BAKED_SOURCE = "imf"

# The program's yield columns Japan has: the Ministry's column of each.
JP_YIELD_COLUMNS = {
    "1-Year": "1Y", "2-Year": "2Y", "3-Year": "3Y", "5-Year": "5Y", "7-Year": "7Y", "10-Year": "10Y", "20-Year": "20Y",
    "30-Year": "30Y",
}
# Each term's first day with a value (measured 2026-11-26), for the coverage warning.
JP_YIELD_EARLIEST = {
    "1-Year": pd.Timestamp("1974-09-24"), "2-Year": pd.Timestamp("1974-09-24"), "3-Year": pd.Timestamp("1974-09-24"),
    "5-Year": pd.Timestamp("1974-09-24"), "7-Year": pd.Timestamp("1974-09-24"), "10-Year": pd.Timestamp("1986-07-05"),
    "20-Year": pd.Timestamp("1986-12-01"), "30-Year": pd.Timestamp("1999-09-02"),
}
# The Ministry's files are read whole, so the recent part is asked from the bake's last day: the current month's file
# alone while the bake reaches this month (the daily job's), both files at a month's start until it runs. Market
# yields, never revised.
MOF_RECENT_PART = pd.DateOffset(days=0)
_MOF_DATE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")

# The Bank of Japan's series (database, code), measured 2026-11-26.
BOJ_CALL_DAILY = ("FM01", "STRDCLUCON")  # uncollateralized overnight call rate, daily from 1998-01-05
BOJ_CALL_MONTHLY = ("FM02", "STRACLUCON")  # its monthly average, from 1985-07
BOJ_CALL_COLLATERALIZED = ("FM02", "STRACLCOON")  # the collateralized overnight call rate's monthly average, from 1960-01
# The flow of funds' liabilities of a sector: loans (L200) and debt securities (L300), stocks, 100 million yen; the
# sector's digit: 0 general government, 1 central government, 2 local governments, 3 social security funds.
_FF_QUARTERLY = "FOF_FFAS42{sector}L{item}"
_FF_ANNUAL = "FOF_FFYS42{sector}L{item}"
FF_ITEMS = ("200", "300")
GENERAL_GOVERNMENT_SECTOR = "0"
# The chart's levels (--debt:LETTERS): central and local government; the social security funds are no level of the
# chart, as Germany's are not.
JP_LEVEL_SECTORS = {"f": "1", "m": "2"}
# The balance of payments (BP01, BPM6, monthly, 100 million yen, not seasonally adjusted, from 1996-01): each pair's
# credits and debits, the items added up.
BOJ_PAYMENTS = {
    "current": (("BPBP6JYNEX", "BPBP6JYNSC", "BPBP6JYNPIC", "BPBP6JYNSIC"),
                ("BPBP6JYNIM", "BPBP6JYNSD", "BPBP6JYNPID", "BPBP6JYNSID")),
    "trade": (("BPBP6JYNEX", "BPBP6JYNSC"), ("BPBP6JYNIM", "BPBP6JYNSD")),
}
BOJ_PAYMENTS_DB = "BP01"
JP_PAYMENTS_EARLIEST = pd.Timestamp("1996-01-01")
# The Bank's figures are in hundreds of millions of yen.
# A series asked for whole is asked from here, before every series read begins (the collateralized call rate,
# 1960-01): FM01's daily rate asked from 1850-01 answered nothing but a next position (2026-11-26), over the number of
# values one answer holds; from 1955 its 28 years of days are one answer.
BOJ_WHOLE_FROM = pd.Timestamp("1955-01-01")
_HUNDRED_MILLION = 100_000_000

# The IMF's consumer price index for Japan, all items, 2020 = 100, monthly (its CPI dataflow, version 5.0.0).
IMF_CPI_FLOW = "IMF.STA,CPI"
IMF_CPI_KEY = "JPN.CPI._T.IX.M"
# FRED: nominal GDP (billions of yen, SAAR) and the population (persons, annual).
JP_GDP_SERIES = "JPNNGDP"
JP_POPULATION_SERIES = "POPTOTJPA647NWDB"
# A year's midyear population is dated by its middle (FRED dates it by its first day).
_MIDYEAR = pd.DateOffset(months=6)

# The first observation of each input but the yields, for the coverage warning.
JP_SERIES_EARLIEST = {
    "Gross debt (Bank of Japan flow of funds: fiscal years to 1997, quarterly after)": pd.Timestamp("1981-03-31"),
    "TTM Nominal GDP (FRED JPNNGDP)": pd.Timestamp("1994-12-31"),
}


def series_earliest(config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of Japan's inputs, by name, for the coverage warning: the chosen yields it has, then the rest."""
    earliest = {
        f"{column} Yield (Ministry of Finance, daily)": JP_YIELD_EARLIEST[column]
        for column in config.fetched_yield_columns if column in JP_YIELD_COLUMNS
    }
    return {**earliest, **JP_SERIES_EARLIEST}


# ---------------------------------------------------------------------------
# The Ministry of Finance's yields
# ---------------------------------------------------------------------------


def parse_mof_csv(content: bytes) -> pd.DataFrame:
    """Return one of the Ministry's JGB files as a frame: a column per term ("10Y"), each day dated by itself, in percent.

    Read as cp932 (the current month's file ends with a note in Japanese).
    The header is the line starting "Date,"; a data row is one whose first
    field is a date ``YYYY/M/D``; ``-`` is no value. A file with no data row
    raises.
    """
    text = content.decode("cp932", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    header = next((row for row in rows if row and row[0].strip() == "Date"), None)
    if header is None:
        raise ValueError("expected the Ministry of Finance's header line starting 'Date,'")
    names = [name.strip() for name in header]
    data = [row for row in rows if row and _MOF_DATE.match(row[0].strip())]
    if not data:
        raise ValueError("the Ministry of Finance's file holds no day")
    frame = pd.DataFrame([row[: len(names)] + [""] * (len(names) - len(row)) for row in data], columns=names)
    days = pd.to_datetime(frame.pop("Date").str.strip(), format="%Y/%m/%d")
    values = frame.apply(lambda column: pd.to_numeric(column.str.strip().replace("-", ""), errors="coerce"))
    return values.set_axis(pd.DatetimeIndex(days, name=DATE_COLUMN)).sort_index()


def mof_download(start: pd.Timestamp | None = None) -> pd.DataFrame:
    """Ask the Ministry for its yields from ``start`` (or every day): the current month's file, and the history file where ``start`` is before the current month."""
    current = parse_mof_csv(jp_get(MOF_CURRENT_URL).content)
    if start is not None and start >= current.index[0].replace(day=1):
        return current
    history = parse_mof_csv(jp_get(MOF_HISTORY_URL).content)
    return pd.concat([history.loc[history.index < current.index[0]], current])


def mof_yields() -> pd.DataFrame:
    """Return the Ministry's yields of every term the program reads, by its column ("10Y"): the bake, then the recent part (``MOF_RECENT_PART``)."""
    codes = list(JP_YIELD_COLUMNS.values())
    return frame_with_recent_part(MOF_BAKED_SOURCE, codes, "Ministry of Finance JGB yields", lambda start: mof_download(start)[codes],
                                  MOF_RECENT_PART)


def fetch_yields(config: PlotConfig) -> pd.DataFrame:
    """Return Japan's chosen yields, date-indexed, each day by itself (the Ministry's), trimmed to the window.

    A term is carried over a missing day for three rows at most, as
    Germany's daily yields are, so a longer gap is a break. ``attrs[YIELD_HISTORY_ATTR]``
    is empty: no term has a monthly part. If the Ministry fails with nothing
    baked, no yield, with a warning.
    """
    chosen = [column for column in config.fetched_yield_columns if column in JP_YIELD_COLUMNS]
    absent = [column for column in config.yield_columns if column not in JP_YIELD_COLUMNS]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no Japanese {', '.join(absent)} yield; the Japanese chart is drawn without it.")
    if not chosen:
        return pd.DataFrame()
    try:
        terms = mof_yields()
    except Exception as exc:
        print(f"  Warning: Ministry of Finance JGB yields unavailable ({exc}); not drawn.")
        return pd.DataFrame()
    frame = pd.DataFrame({column: terms[JP_YIELD_COLUMNS[column]] for column in chosen}).dropna(how="all").sort_index()
    frame = frame.ffill(limit=_DAILY_FILL_LIMIT).rename_axis(DATE_COLUMN).loc[config.start : config.end]
    frame.attrs[YIELD_HISTORY_ATTR] = {}
    return frame


# ---------------------------------------------------------------------------
# The Bank of Japan's API
# ---------------------------------------------------------------------------


def _boj_period(text: str, frequency: str) -> pd.Timestamp:
    """The date a period of the Bank's answer is drawn on: a day itself, a month's first day, a quarter's or a March year's last day, a calendar year's first."""
    if frequency.startswith("DAILY"):
        return pd.Timestamp(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    if frequency.startswith("MONTHLY"):
        return pd.Timestamp(f"{text[:4]}-{text[4:6]}-01")
    if frequency.startswith("QUARTERLY"):
        return pd.Period(f"{text[:4]}Q{int(text[4:6])}", freq="Q").end_time.normalize()
    if frequency == "ANNUAL(MAR)":  # the fiscal year ending March Y+1
        return pd.Timestamp(f"{int(text[:4]) + 1}-03-31")
    if frequency.startswith("ANNUAL"):
        return pd.Timestamp(f"{text[:4]}-01-01")
    raise ValueError(f"the Bank of Japan's frequency {frequency!r} is not one read here")


def parse_boj_csv(content: bytes) -> tuple[dict[str, pd.Series], str]:
    """Return the series of one answer of the Bank's ``getDataCode``, by code, each dated by ``_boj_period`` with no value left out, and its ``NEXTPOSITION`` ("" when whole).

    The answer: header lines (``STATUS,200``, ``MESSAGE``, ``PARAMETER``,
    ``NEXTPOSITION``), then a table, one row per series and period, ``null``
    for no value. A status other than 200 raises with the Bank's message.
    """
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    head = {}
    for line in lines:
        if line.startswith("SERIES_CODE"):
            break
        parts = line.split(",", 1)
        head.setdefault(parts[0], parts[1] if len(parts) > 1 else "")
    if head.get("STATUS") != "200":
        raise ValueError(f"the Bank of Japan answered status {head.get('STATUS')}: {head.get('MESSAGE', '')}")
    start = next((i for i, line in enumerate(lines) if line.startswith("SERIES_CODE")), None)
    found: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    if start is not None:
        for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
            value = row.get("VALUES", "")
            if value in ("", "null"):
                continue
            found.setdefault(row["SERIES_CODE"], []).append((_boj_period(row["SURVEY_DATES"], row["FREQUENCY"]), float(value)))
    series = {
        code: pd.Series([v for _d, v in pairs], index=pd.DatetimeIndex([d for d, _v in pairs], name=DATE_COLUMN), name=code).sort_index()
        for code, pairs in found.items()
    }
    return series, head.get("NEXTPOSITION", "")


def _boj_start(start: pd.Timestamp, code: str) -> str:
    """``startDate`` for a series from ``start``: its year for an annual series (``FFYS``), ``YYYYQQ`` for a quarterly one (``FFAS``), else ``YYYYMM``."""
    if code.startswith("FOF_FFYS"):
        return f"{start:%Y}"
    if code.startswith("FOF_FFAS"):
        return f"{start:%Y}{start.quarter:02d}"
    return f"{start:%Y%m}"


def boj_download(db: str, codes: list[str], start: pd.Timestamp | None = None) -> dict[str, pd.Series]:
    """Ask the Bank for ``codes`` of database ``db`` from ``start`` (or every period, from ``BOJ_WHOLE_FROM``), following ``NEXTPOSITION`` if it sends one; each code answered, or a ValueError."""
    params = {"format": "csv", "lang": "en", "db": db, "code": ",".join(codes),
              "startDate": _boj_start(BOJ_WHOLE_FROM if start is None else start, codes[0])}
    found: dict[str, list[pd.Series]] = {}
    for _page in range(20):
        series, following = parse_boj_csv(jp_get(BOJ_DATA_URL, params).content)
        if following and not series:
            # Asked for more than one answer holds of a series (measured 2026-11-26: FM01's daily rate from 1850-01
            # answered no row and NEXTPOSITION 1, as often as it was asked), which a later start cannot be given.
            raise ValueError(f"the Bank of Japan answered no value of {db} from {params['startDate']}, only a next position")
        for code, values in series.items():
            found.setdefault(code, []).append(values)
        if not following:
            break
        params = {**params, "startPosition": following}
    else:
        raise ValueError(f"the Bank of Japan's answer for {db} did not end within 20 pages")
    joined = {code: pd.concat(parts).sort_index() for code, parts in found.items()}
    missing = [code for code in codes if code not in joined and start is None]
    if missing:
        raise ValueError(f"the Bank of Japan gave no value of {', '.join(missing)}")
    return {code: joined.get(code, pd.Series(dtype=float, name=code)) for code in codes}


def boj_series(db: str, code: str, *, revised: bool) -> pd.Series:
    """Return one Bank of Japan series: its bake (``ratesplot/data/boj/``), then its recent part (two months, or 24 for a series the Bank revises)."""
    return with_recent_part(
        BOJ_BAKED_SOURCE, code, f"Bank of Japan {code}", lambda start: boj_download(db, [code], start)[code],
        RECENT_PART_REVISED if revised else RECENT_PART_UNREVISED,
    )


def boj_frame(db: str, codes: list[str], *, revised: bool) -> pd.DataFrame:
    """Return several series of one Bank database asked together (one request): their bakes, then their recent part."""
    return frame_with_recent_part(
        BOJ_BAKED_SOURCE, codes, f"Bank of Japan {db}", lambda start: pd.DataFrame(boj_download(db, codes, start)),
        RECENT_PART_REVISED if revised else RECENT_PART_UNREVISED,
    )


def call_rate() -> tuple[pd.Series, pd.Series, pd.Series]:
    """The call rate's three parts, each its bake and recent part: the collateralized monthly averages, the uncollateralized monthly averages and the uncollateralized daily rate."""
    return (boj_series(*BOJ_CALL_COLLATERALIZED, revised=False), boj_series(*BOJ_CALL_MONTHLY, revised=False),
            boj_series(*BOJ_CALL_DAILY, revised=False))


def _sector_debt(sector: str) -> pd.Series:
    """A sector's loans and debt securities together, in yen: the March figures before the quarterly series' first quarter, then the quarters.

    The annual figures are read from their bake alone (asked whole if not
    baked): only those before 1997 Q4 are drawn, long past revision.
    """
    quarterly = boj_frame("FF", [_FF_QUARTERLY.format(sector=sector, item=item) for item in FF_ITEMS], revised=True)
    quarters = quarterly.sum(axis=1, min_count=len(FF_ITEMS)).dropna()
    annual_codes = [_FF_ANNUAL.format(sector=sector, item=item) for item in FF_ITEMS]
    bakes = [read_series(BOJ_BAKED_SOURCE, code) for code in annual_codes]
    if any(series is None or series.empty for series in bakes):
        answered = boj_download("FF", annual_codes)
        bakes = [answered[code] for code in annual_codes]
    years = pd.concat(bakes, axis=1).sum(axis=1, min_count=len(FF_ITEMS)).dropna()
    joined = pd.concat([years.loc[years.index < quarters.index[0]], quarters]) if len(quarters) else years
    return joined * _HUNDRED_MILLION


@downloads_of("Bank of Japan government debt")
def fetch_debt(config: PlotConfig) -> pd.DataFrame | None:
    """Return general government's loans and debt securities (decision 188 (4)): the March figures from 1981, the quarters from 1997 Q4; None, with a warning, if the Bank fails."""
    if not config.include_debt:
        return None
    try:
        values = _sector_debt(GENERAL_GOVERNMENT_SECTOR)
    except Exception as exc:
        print(f"  Warning: Bank of Japan flow of funds (Japanese debt) unavailable ({exc}); not drawn.")
        return None
    return values.rename(JP_DEBT_COLUMN).to_frame()


@downloads_of("FRED GDP")
def fetch_gdp(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: the mean of four quarters' annual rates (FRED JPNNGDP, billions of yen), dated by the last quarter's end; None, with a warning, if FRED fails."""
    if not config.needs_gdp:
        return None
    try:
        frame = fred_series(JP_GDP_SERIES, revised=True)
    except Exception as exc:
        print(f"  Warning: FRED {JP_GDP_SERIES} (Japanese GDP) unavailable ({exc}); not drawn.")
        return None
    saar = pd.to_numeric(frame.set_index(DATE_COLUMN)[JP_GDP_SERIES], errors="coerce").dropna() * 1e9
    quarters = pd.DatetimeIndex(saar.index) + pd.offsets.QuarterEnd(0)
    saar = saar.set_axis(pd.DatetimeIndex(quarters, name=DATE_COLUMN))
    return saar.rolling(4, min_periods=4).mean().dropna().rename(GDP_COLUMN).to_frame()


def fetch_interest(config: PlotConfig) -> pd.DataFrame | None:
    """Japan's interest paid: none quarterly (decision 188 (9)); a note where it is chosen, and None."""
    if config.include_interest:
        print("  Note: no quarterly figures of Japan's interest paid are published; the Japanese chart is drawn without it.")
    return None


@downloads_of("Bank of Japan debt by level of government")
def fetch_components(config: PlotConfig) -> pd.DataFrame | None:
    """Return debt by level of government (--debt:LETTERS): central and local government's loans and debt securities, as general government's; no interest (a note). A level whose series fails is left out, with a warning."""
    if config.include_interest:
        print("  Note: no quarterly figures of Japan's interest paid are published; its levels are drawn without it.")
    if not config.include_debt:
        return None
    columns: list[pd.Series] = []
    for letter in COMPONENT_LETTERS:
        if letter not in config.components or letter not in JP_LEVEL_SECTORS:
            continue
        try:
            values = _sector_debt(JP_LEVEL_SECTORS[letter])
        except Exception as exc:
            print(f"  Warning: Bank of Japan flow of funds, level {letter} unavailable ({exc}); not drawn.")
            continue
        columns.append(values.rename(component_column("debt", letter)))
    return pd.concat(columns, axis=1).sort_index() if columns else None


def payments_months(item: str) -> tuple[pd.Series, pd.Series]:
    """Japan's credits and debits of pair ``item``, each a month's flow in yen (BP01's items added up); a month lacking any item is left out."""
    credit_codes, debit_codes = BOJ_PAYMENTS[item]
    codes = sorted({*credit_codes, *debit_codes})
    frame = boj_frame(BOJ_PAYMENTS_DB, codes, revised=True)
    sides = []
    for side in (credit_codes, debit_codes):
        sides.append(frame[list(side)].sum(axis=1, min_count=len(side)).dropna() * _HUNDRED_MILLION)
    return sides[0], sides[1]


# ---------------------------------------------------------------------------
# The IMF's consumer prices, FRED's population
# ---------------------------------------------------------------------------


def parse_imf_monthly(content: bytes, key: str) -> pd.Series:
    """Return one monthly series of an IMF SDMX answer: each month's figure, dated by its first day (``TIME_PERIOD`` ``YYYY-Mmm``); no figure raises."""
    observations = [(obs.get("TIME_PERIOD", ""), obs.get("OBS_VALUE")) for obs in ElementTree.fromstring(content).iter("Obs")]
    if not observations:
        raise ValueError(f"the IMF gave no figures of {key}")
    months = pd.to_datetime([period.replace("-M", "-") for period, _value in observations], format="%Y-%m")
    values = pd.to_numeric(pd.Series([value for _period, value in observations], index=pd.DatetimeIndex(months, name=DATE_COLUMN)),
                           errors="coerce")
    return values.dropna().sort_index().rename(key)


def imf_cpi_download(start: pd.Timestamp | None = None) -> pd.Series:
    """Ask the IMF for Japan's consumer price index from ``start``'s year (or whole)."""
    params = {"startPeriod": f"{start:%Y}"} if start is not None else None
    return parse_imf_monthly(jp_get(IMF_SDMX_URL.format(flow=IMF_CPI_FLOW, key=IMF_CPI_KEY), params).content, IMF_CPI_KEY)


@downloads_of("IMF consumer prices")
def fetch_consumer_prices() -> pd.Series:
    """Return Japan's consumer price index (2020 = 100), monthly from 1955-01, not seasonally adjusted: the IMF's bake and recent part (revised: 24 months)."""
    return with_recent_part(IMF_BAKED_SOURCE, IMF_CPI_KEY, f"IMF {IMF_CPI_KEY}", imf_cpi_download, RECENT_PART_REVISED)


@downloads_of("FRED population")
def fetch_population() -> pd.Series | None:
    """Return Japan's population for -p: the World Bank's midyear estimates (FRED), each year dated by its middle; None, with a warning, if FRED fails."""
    try:
        frame = fred_series(JP_POPULATION_SERIES, revised=True)
    except Exception as exc:
        print(f"  Warning: FRED {JP_POPULATION_SERIES} (Japanese population) unavailable ({exc}); not drawn.")
        return None
    values = pd.to_numeric(frame.set_index(DATE_COLUMN)[JP_POPULATION_SERIES], errors="coerce").dropna()
    middles = pd.DatetimeIndex(values.index) + _MIDYEAR
    return values.set_axis(pd.DatetimeIndex(middles, name=DATE_COLUMN)).rename(POPULATION_COLUMN)


# Every Bank of Japan series the program reads (for the bake): (database, code).
BOJ_SERIES_READ = (
    BOJ_CALL_DAILY, BOJ_CALL_MONTHLY, BOJ_CALL_COLLATERALIZED,
    *(("FF", pattern.format(sector=sector, item=item)) for pattern in (_FF_QUARTERLY, _FF_ANNUAL)
      for sector in (GENERAL_GOVERNMENT_SECTOR, *JP_LEVEL_SECTORS.values()) for item in FF_ITEMS),
    *((BOJ_PAYMENTS_DB, code) for code in sorted({code for pair in BOJ_PAYMENTS.values() for side in pair for code in side})),
)
