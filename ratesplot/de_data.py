"""Deutsche Bundesbank / ECB / Eurostat data pipelines for Germany's chart (batch 4).

Sources, measured from Terry's laptop on 2026-10-06 (the cloud copy cannot
reach them; ``tools/de_fixtures/README.md`` holds the measurements):

* Yields: the Bundesbank's term structure of listed Federal securities
  (Svensson method), zero-coupon yields fitted to the Bund, Bobl and Schatz
  prices, daily from 1997-08-07 (the 30-year from 2000-08-01), and before
  that end-of-month values: 1 to 10 years from 1972-09, the 20-year from
  1986-06, the 30-year from 2000-01. They are joined monthly-then-daily as
  the UK's and Canada's histories are, the months drawn as steps. Terms 1,
  2, 5, 7, 10, 20 and 30 years: the Bundesbank also fits 3 and 15 years,
  which the program has no term for. Before 1972-09 the 10-year is carried
  back by the Bundesbank's monthly average yield on all public debt
  securities outstanding (BBK01.WU0004, from 1956-05; frozen at 2020-04, so
  baked into ``de_archive_data``): a different measure, an average over
  every maturity, 0.18 points below the fitted 10-year in 1972-09 where
  they meet (0.09 on average over their first year together).
* Debt: general government consolidated gross debt (Maastricht), quarterly
  from 2000 (Eurostat gov_10q_ggdebt, S13), and before it the year-end
  figures from 1991 (ECB GFS, annual), which equal the fourth quarters
  exactly where both exist. Germany's figures begin with unification: West
  Germany's (1950-1990) are still to be found and baked.
* Levels (``--debt:LETTERS``): the federal government ("f", Bund, central
  government S1311 with its special funds), the Länder ("p", state
  government S1312), local government ("m", Gemeinden, S1313), and "n" the
  Länder and local together. The social security funds (S1314, under 0.5 %
  of the total) are no level of the chart. The levels are not consolidated
  with each other, so they add up to about 1 % more than the total.
* Interest: D.41 interest payable by general government (consolidated),
  quarterly from 2002 (Eurostat gov_10q_ggnfa), summed over four quarters,
  and before it the annual figures from 1995 (gov_10dd_edpt1), which equal
  the sums of their quarters exactly where both exist. Levels from 2002.
* GDP: at market prices, current prices, not seasonally adjusted, quarterly
  from 1991 (Eurostat namq_10_gdp), summed over four quarters.
* Population: Eurostat namq_10_pe (thousands, quarterly from 1991, dated
  mid-quarter), and before it demo_pjan (on 1 January, from 1960: West
  Germany until 1990, so the curve steps up by 17 million at unification,
  as the UK's steps at Ireland's independence).

Every figure is dated by the day it describes: a stock at the end of its
quarter or year, a four-quarter sum at the end of its last quarter, an
end-of-month yield at the month's end, a monthly average at the month's
start. Values are in euros (and persons); each source's unit is checked
against the one measured, so a change of unit fails rather than shifting a
curve a thousandfold. Deutsche Mark figures before 1999 are in euros at
1.95583, as the ECB and Eurostat publish them.

The ECB's series (batch 19.2, ``ecb_series``): their history is in
``ratesplot/data/ecb/``, and a drawing asks the ECB only for the recent part,
from the period holding that date on; if the ECB fails, the baked history
alone, with a warning. Eurostat's alike (``eurostat_series``), in
``ratesplot/data/eurostat/``, each dataset's recent part asked for once for
all its series. The Bundesbank's alike (``bundesbank_series``), in
``ratesplot/data/bbk/``, the recent part asked of its SDMX web service, which
reads a start date where its download does not; a bot check (``BotCheck``)
that no last good copy answers for is named once, and the Bundesbank asked
nothing more in that drawing.
"""

from __future__ import annotations

import csv
import io
import re

import pandas as pd

from .config import (
    BUNDESBANK_DATA_URL,
    BUNDESBANK_SERIES_URL,
    COMPONENT_LETTERS,
    DATE_COLUMN,
    DE_DEBT_COLUMN,
    DE_INTEREST_COLUMN,
    ECB_SERIES_URL,
    EUROSTAT_DATASET_URL,
    GDP_COLUMN,
    MILLION,
    POPULATION_COLUMN,
    RECENT_PART_REVISED,
    RECENT_PART_UNREVISED,
    THOUSAND,
    YIELD_TERMS,
    PlotConfig,
    component_column,
)
from .baked import frame_with_recent_part, read_series, with_recent_part
from .de_archive_data import EMBEDDED_DE_PUBLIC_DEBT_YIELD_HISTORY
from .http import BotCheck, de_get, downloads_of
from .joins import embedded_frame, ttm_sum

# Chart column -> the Bundesbank's code of that residual maturity in the
# Svensson term structure ("R10XX" = 10.0 years), and the series key with
# the frequency ("D" daily, "M" monthly) still to fill in.
DE_YIELD_SERIES = {
    "1-Year": "R01XX", "2-Year": "R02XX", "5-Year": "R05XX", "7-Year": "R07XX",
    "10-Year": "R10XX", "20-Year": "R20XX", "30-Year": "R30XX",
}
BUNDESBANK_TERM_STRUCTURE_FLOW = "BBSIS"
_TERM_STRUCTURE_KEY = "{frequency}.I.ZST.ZI.EUR.S1311.B.A604.{term}.R.A.A._Z._Z.A"
# Each term's two series, end-of-month and daily (the key's first part).
TERM_STRUCTURE_FREQUENCIES = ("M", "D")
# The Bundesbank's series are baked (batch 19.2) under ``ratesplot/data/bbk/``
# (``tools/bake_archives.py --only bbk``), each file named by its flow and
# key: every term's end-of-month and daily series.
BUNDESBANK_BAKED_SOURCE = "bbk"
# How ``startPeriod`` is written for each frequency (a key's first part), so
# that the Bundesbank answers from the period holding the date asked for.
# Measured 2026-10-22 (all 14 term structure series): a monthly series asked
# from a day or from its month answers from that month (unlike the ECB, which
# begins with the next period); a daily series asked from a day answers from
# that day (a Saturday: from the Monday after), and refuses a month (400,
# "Period restriction 2026-08 does not match frequency D"). Each in its own
# period's form, as the ECB's are; a frequency not measured raises.
_BUNDESBANK_START_FORMS = {"M": "%Y-%m", "D": "%Y-%m-%d"}
# Each term's first month (its end-of-month value; measured 2026-10-06).
DE_YIELD_EARLIEST = {
    "1-Year": pd.Timestamp("1972-09-30"), "2-Year": pd.Timestamp("1972-09-30"),
    "5-Year": pd.Timestamp("1972-09-30"), "7-Year": pd.Timestamp("1972-09-30"),
    "10-Year": pd.Timestamp("1972-09-30"), "20-Year": pd.Timestamp("1986-06-30"),
    "30-Year": pd.Timestamp("2000-01-31"),
}
# Germany's terms (config.YIELD_TERMS keys), in their order.
DE_YIELD_TERMS = tuple(term for term, column in YIELD_TERMS.items() if column in DE_YIELD_SERIES)
# The baked monthly history of a term, before its end-of-month series begins.
_YIELD_HISTORY = {"10-Year": EMBEDDED_DE_PUBLIC_DEBT_YIELD_HISTORY}
# Where ``fetch_de_yields`` records, in the frame's ``attrs``, the last date
# of each column's monthly part ({column: date}), drawn as steps; the same
# name as the UK's, so the drawing and the spreads read both alike.
YIELD_HISTORY_ATTR = "monthly_history_through"
_NO_VALUES = pd.Series(dtype=float, index=pd.DatetimeIndex([], name=DATE_COLUMN))
# Short forward-fill of the daily yields: bridges a holiday or a missing
# print in one term, as for the UK's and Canada's, never more than this many rows.
_DAILY_FILL_LIMIT = 3

# The units the sources were measured in. The Bundesbank writes "percent"
# in its new database's English header and "Prozent"/"PROZENT" elsewhere;
# its central bank rates (flow BBIN1, the discount rate baked in batch 9.6)
# "% p.a.", a rate per year as the yields are.
_BUNDESBANK_PERCENT = ("percent", "prozent", "% p.a.")
_BUNDESBANK_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_BUNDESBANK_MISSING = (".", "-", "")

# ECB series: flow and key, and the unit its CSV gives (UNIT or UNIT_MEASURE).
# GFS debt is in "national currency" (XDC): euros, Deutsche Mark figures
# converted at the fixed parity.
ECB_ANNUAL_DEBT = ("GFS", "A.N.DE.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC")
# The ECB's series are baked (batch 19.2) under ``ratesplot/data/ecb/``
# (``tools/bake_archives.py --only ecb``), each file named by its flow and
# key: the annual debt here, the policy, market and mortgage rates in ``rates``.
ECB_BAKED_SOURCE = "ecb"
# How ``startPeriod`` is written for each frequency (a key's first part), so
# that the ECB answers from the period holding the date asked for. Measured
# 2026-10-22 (all eight series the program reads): asked from a day, the ECB
# answers from the first period beginning on or after it, so an annual series
# asked from 2023-12-31 begins with 2024 and a monthly one asked from
# 2026-06-30 with July; asked in the period's own form (2023, 2026-06), from
# that period. A frequency not measured raises.
_ECB_START_FORMS = {"A": "%Y", "M": "%Y-%m", "B": "%Y-%m-%d", "D": "%Y-%m-%d"}

# Eurostat datasets: dataset -> (the query sent, the unit expected). The
# query is the one measured from the laptop; one answer holds every sector.
EUROSTAT_QUERIES = {
    "gov_10q_ggdebt": ({"geo": "DE", "unit": "MIO_EUR", "na_item": "GD"}, "MIO_EUR"),
    "gov_10q_ggnfa": ({"geo": "DE", "unit": "MIO_EUR", "na_item": "D41PAY", "s_adj": "NSA"}, "MIO_EUR"),
    "gov_10dd_edpt1": ({"geo": "DE", "unit": "MIO_EUR"}, "MIO_EUR"),
    "namq_10_gdp": ({"geo": "DE", "unit": "CP_MEUR", "na_item": "B1GQ", "s_adj": "NSA"}, "CP_MEUR"),
    "namq_10_pe": ({"geo": "DE", "unit": "THS_PER", "na_item": "POP_NC", "s_adj": "NSA"}, "THS_PER"),
    "demo_pjan": ({"geo": "DE", "sex": "T", "age": "TOTAL"}, "NR"),
}
_EUROSTAT_MULTIPLIER = {"MIO_EUR": MILLION, "CP_MEUR": MILLION, "THS_PER": THOUSAND, "NR": 1}
# Each dataset's frequency (its one ``freq`` category), measured 2026-10-22;
# an answer of another raises (``eurostat_download``), since how
# ``sinceTimePeriod`` is written depends on it (``_eurostat_since``).
_EUROSTAT_FREQUENCIES = {
    "gov_10q_ggdebt": "Q", "gov_10q_ggnfa": "Q", "gov_10dd_edpt1": "A", "namq_10_gdp": "Q", "namq_10_pe": "Q", "demo_pjan": "A",
}
# Levels of government (--debt:LETTERS): Eurostat's subsectors of each.
# "n" is the Länder and local government together.
_LEVEL_SECTORS = {"f": ("S1311",), "n": ("S1312", "S1313"), "p": ("S1312",), "m": ("S1313",)}
GENERAL_GOVERNMENT = "S13"
# The annual interest payable (gov_10dd_edpt1, whose query gives every item and sector).
_ANNUAL_INTEREST = {"sector": GENERAL_GOVERNMENT, "na_item": "D41PAY"}
# Every series the program reads of each dataset: the categories chosen
# (``eurostat_series``' keyword arguments; none for a dataset of one series).
# These are baked (batch 19.2) under ``ratesplot/data/eurostat/``
# (``tools/bake_archives.py --only eurostat``), a file each, named by
# ``eurostat_code``; one request answers all of a dataset's.
_SECTORS_READ = tuple(sorted({GENERAL_GOVERNMENT, *(sector for sectors in _LEVEL_SECTORS.values() for sector in sectors)}))
EUROSTAT_SERIES_READ: dict[str, tuple[dict[str, str], ...]] = {
    "gov_10q_ggdebt": tuple({"sector": sector} for sector in _SECTORS_READ),
    "gov_10q_ggnfa": tuple({"sector": sector} for sector in _SECTORS_READ),
    "gov_10dd_edpt1": (_ANNUAL_INTEREST,),
    "namq_10_gdp": ({},),
    "namq_10_pe": ({},),
    "demo_pjan": ({},),
}
EUROSTAT_BAKED_SOURCE = "eurostat"

# A quarter's population is dated this many days after the quarter begins:
# about its middle, as the UK's is.
_QUARTER_MIDDLE_DAYS = 45

# First observation of each German input other than the yields, to warn when
# ``--start`` is earlier (``de_series_earliest`` adds the chosen yields).
DE_SERIES_EARLIEST = {
    "German General Government Debt (ECB, year-end from 1991)": pd.Timestamp("1991-12-31"),
    "TTM Nominal GDP (Eurostat, quarterly from 1991)": pd.Timestamp("1991-12-31"),
    "TTM German Interest Payable (Eurostat, annual from 1995)": pd.Timestamp("1995-12-31"),
}


# ---------------------------------------------------------------------------
# Raw source access
# ---------------------------------------------------------------------------


def _period_end(text: str) -> pd.Timestamp:
    """Return the last day of a period written ``1972-09``, ``2000-Q1`` or ``1995``; a day ``1999-01-04`` is itself."""
    text = text.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return pd.Timestamp(text)
    if re.fullmatch(r"\d{4}-Q[1-4]", text):
        return pd.Period(text.replace("-", ""), freq="Q").end_time.normalize()
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return pd.Period(text, freq="M").end_time.normalize()
    if re.fullmatch(r"\d{4}", text):
        return pd.Period(text, freq="Y").end_time.normalize()
    raise ValueError(f"not a period: {text!r}")


def parse_bundesbank_csv(text: str) -> pd.Series:
    """Parse one series of a Bundesbank CSV download; a date-indexed float series in percent, named by its key.

    The layout: a header line ``"",KEY,KEY_FLAGS``, lines of metadata
    (title, unit, multiplier, last update), then ``date,value,flag`` rows;
    "." or "-" where there is no value (weekends in a daily series). A month
    ``1972-09`` is dated by its last day (the term structure's monthly
    values are end-of-month values). The unit must be percent and the
    multiplier one; anything else, and an answer with no dated rows (the
    old download's "Die Zeitreihe ... ist nicht gültig"), raises.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or len(rows[0]) < 2 or not rows[0][1].strip():
        raise ValueError(f"expected a Bundesbank series CSV, got {text[:80]!r}")
    key = rows[0][1].strip()
    meta = {row[0].strip().lower(): row[1].strip() for row in rows[1:] if len(row) >= 2 and not _BUNDESBANK_DATE.match(row[0].strip())}
    unit = meta.get("bbk_unit_eng", meta.get("unit", ""))
    if unit.lower() not in _BUNDESBANK_PERCENT:
        raise ValueError(f"Bundesbank {key}: expected percent, found unit {unit!r}")
    if meta.get("unit multiplier", "one").lower() != "one":
        raise ValueError(f"Bundesbank {key}: expected the multiplier one, found {meta['unit multiplier']!r}")
    data = [row for row in rows[1:] if row and _BUNDESBANK_DATE.match(row[0].strip())]
    if not data:
        raise ValueError(f"Bundesbank {key}: no dated rows")
    present = [(row[0], row[1].strip()) for row in data if len(row) >= 2 and row[1].strip() not in _BUNDESBANK_MISSING]
    values = pd.Series(
        [float(value) for _date, value in present],
        index=pd.DatetimeIndex([_period_end(date) for date, _value in present], name=DATE_COLUMN),
        dtype=float,
        name=key,
    )
    if values.index.duplicated().any():
        raise ValueError(f"Bundesbank {key}: a date appears twice")
    return values.sort_index()


def term_structure_key(column: str, frequency: str) -> str:
    """The key of one term's series in the Svensson term structure (flow ``BUNDESBANK_TERM_STRUCTURE_FLOW``): ``frequency`` "M" end-of-month, "D" daily."""
    return _TERM_STRUCTURE_KEY.format(frequency=frequency, term=DE_YIELD_SERIES[column])


def _bundesbank_start_period(key: str, day: pd.Timestamp) -> str:
    """``startPeriod`` asking series ``key`` for the period holding ``day`` on: ``2026-07`` (monthly), the day itself (daily)."""
    frequency = key.split(".")[0]
    if frequency not in _BUNDESBANK_START_FORMS:
        raise ValueError(f"Bundesbank {key}: no startPeriod form measured for its frequency {frequency!r}")
    return f"{day:{_BUNDESBANK_START_FORMS[frequency]}}"


def bundesbank_download(flow: str, key: str, start: pd.Timestamp | None = None) -> pd.Series:
    """Ask the Bundesbank for one series (``parse_bundesbank_csv``): every value, or those from the period holding ``start`` on; raises if it is not that series.

    One request (cached and kept as the others are). The whole series is
    asked for as before batch 19.2, from the download the program has always
    read (``BUNDESBANK_SERIES_URL``), so its request is the same. That
    download ignores ``startPeriod`` (measured 2026-10-22, for all 14 term
    structure series: the whole series every time); a recent part is asked
    of the SDMX web service (``BUNDESBANK_DATA_URL``), which reads it and
    answers in the same CSV (asked for everything, the same text as the
    download). A range with no value is answered with the header alone,
    which raises ("no dated rows"): a recent part counted from the bake's
    last value always holds that value.
    """
    params = {"format": "csv", "lang": "en"}
    if start is None:
        url = BUNDESBANK_SERIES_URL.format(flow=flow, key=key)
    else:
        url = BUNDESBANK_DATA_URL.format(flow=flow, key=key)
        params["startPeriod"] = _bundesbank_start_period(key, start)
    values = parse_bundesbank_csv(de_get(url, params).text)
    if values.name != f"{flow}.{key}":
        raise ValueError(f"the Bundesbank answered {values.name} for {flow}.{key}")
    return values


def bundesbank_series(flow: str, key: str) -> pd.Series:
    """Return one series of the Bundesbank's database (``parse_bundesbank_csv``): its baked history, then its recent part from the Bundesbank.

    Batch 19.2 (``ratesplot.baked``): the history is in
    ``ratesplot/data/bbk/``, and only the last two months are asked for
    (market yields, not revised), from the period holding that date on; a
    series not baked is asked for whole. If the Bundesbank fails,
    the baked history alone, to its last value, with a warning; but a bot
    check is raised (``BotCheck``), for the caller to name once. Measured
    2026-10-22: the bake joined to its recent part is the Bundesbank's whole
    answer, value for value.
    """
    return with_recent_part(
        BUNDESBANK_BAKED_SOURCE,
        f"{flow}.{key}",
        f"Bundesbank {flow}.{key}",
        lambda start: bundesbank_download(flow, key, start),
        RECENT_PART_UNREVISED,
        passes=(BotCheck,),
    )


def parse_ecb_csv(text: str, series_key: str, unit: str) -> pd.Series:
    """Parse an ECB Data Portal CSV (``format=csvdata``) of one series; date-indexed floats in units (``UNIT_MULT`` applied).

    Each row is one observation: ``KEY``, ``TIME_PERIOD``, ``OBS_VALUE`` and
    the series' attributes. Every row's key must be ``series_key`` (flow
    and key, ``FM.B.U2.EUR.4F.KR.MRR_FR.LEV``) and its unit (``UNIT``, or
    ``UNIT_MEASURE``) ``unit``. A period is dated by its last day
    (``_period_end``); a row without a value is left out.
    """
    frame = pd.read_csv(io.StringIO(text), dtype=str)
    required = {"KEY", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT"}
    if not required <= set(frame.columns):
        raise ValueError(f"expected an ECB csvdata answer, missing {sorted(required - set(frame.columns))}")
    keys = set(frame["KEY"])
    if keys != {series_key}:
        raise ValueError(f"expected the ECB series {series_key}, found {sorted(keys)}")
    units = set(frame["UNIT"] if "UNIT" in frame.columns else frame["UNIT_MEASURE"])
    if units != {unit}:
        raise ValueError(f"ECB {series_key}: expected unit {unit!r}, found {sorted(units)}")
    multipliers = set(frame["UNIT_MULT"])
    if len(multipliers) != 1:
        raise ValueError(f"ECB {series_key}: more than one multiplier, {sorted(multipliers)}")
    present = frame.dropna(subset=["OBS_VALUE"])
    values = pd.Series(
        pd.to_numeric(present["OBS_VALUE"]).to_numpy() * 10 ** int(multipliers.pop()),
        index=pd.DatetimeIndex([_period_end(period) for period in present["TIME_PERIOD"]], name=DATE_COLUMN),
        dtype=float,
        name=series_key,
    )
    if values.index.duplicated().any():
        raise ValueError(f"ECB {series_key}: a period appears twice")
    return values.sort_index()


def _ecb_start_period(key: str, day: pd.Timestamp) -> str:
    """``startPeriod`` asking series ``key`` for the period holding ``day`` on: ``2023`` (annual), ``2026-06`` (monthly), the day itself (daily)."""
    frequency = key.split(".")[0]
    if frequency not in _ECB_START_FORMS:
        raise ValueError(f"ECB {key}: no startPeriod form measured for its frequency {frequency!r}")
    return f"{day:{_ECB_START_FORMS[frequency]}}"


def ecb_download(flow: str, key: str, unit: str, start: pd.Timestamp | None = None) -> pd.Series:
    """Ask the ECB Data Portal for one series (``parse_ecb_csv``): every value, or those from the period holding ``start`` on.

    One request (cached and kept as the others are). The whole series is
    asked for as before batch 19.2 (``format=csvdata`` alone), so its request
    is the same. The ECB answers a range it has no value in with an empty
    body (status 200), which raises here, naming it: no series the program
    reads is empty from any date it asks for.
    """
    params = {"format": "csvdata"}
    if start is not None:
        params["startPeriod"] = _ecb_start_period(key, start)
    response = de_get(ECB_SERIES_URL.format(flow=flow, key=key), params)
    if not response.text.strip():
        raise ValueError(f"the ECB gave no values of {flow}.{key}" + (f" from {params['startPeriod']}" if start is not None else ""))
    return parse_ecb_csv(response.text, f"{flow}.{key}", unit)


def ecb_series(flow: str, key: str, unit: str, *, revised: bool) -> pd.Series:
    """Return one ECB Data Portal series (``parse_ecb_csv``): its baked history, then its recent part from the ECB.

    Batch 19.2 (``ratesplot.baked``): the history is in
    ``ratesplot/data/ecb/``, and only the last two months are asked for, or
    the last 24 if the ECB revises the series (``revised``: the debt, the
    mortgage rates; each caller says which), from the period holding that
    date on; a series not yet baked is asked for whole. If the ECB fails,
    the baked history alone, to its last value, with a warning. Measured
    2026-10-22: the bake joined to its recent part is the ECB's whole
    answer, value for value.
    """
    return with_recent_part(
        ECB_BAKED_SOURCE,
        f"{flow}.{key}",
        f"ECB {flow}.{key}",
        lambda start: ecb_download(flow, key, unit, start),
        RECENT_PART_REVISED if revised else RECENT_PART_UNREVISED,
    )


def parse_jsonstat(data: dict, unit: str, **chosen: str) -> pd.Series:
    """Return one series of a Eurostat JSON-stat 2.0 answer: dated by each period's end, in the source's unit.

    ``chosen`` names a category for each dimension that has more than one
    (``sector="S1311"``); every other dimension but ``time`` must have just
    one, and the ``unit`` dimension's must be ``unit``. Values are stored
    flat, row-major over the dimensions in ``id`` order; a position with no
    value is left out.
    """
    ids, sizes = data.get("id", []), data.get("size", [])
    if "time" not in ids or len(ids) != len(sizes):
        raise ValueError("expected a JSON-stat dataset with a time dimension")
    categories = {
        dim: sorted(data["dimension"][dim]["category"]["index"], key=data["dimension"][dim]["category"]["index"].get)
        for dim in ids
    }
    units = categories.get("unit", [])
    if units != [unit]:
        raise ValueError(f"Eurostat {data.get('label', '')!r}: expected unit {unit!r}, found {units}")
    unknown = set(chosen) - set(ids)
    if unknown:
        raise ValueError(f"Eurostat {data.get('label', '')!r} has no dimension {sorted(unknown)}")
    position = []
    for dim in ids:
        if dim == "time":
            continue
        if dim in chosen:
            if chosen[dim] not in categories[dim]:
                raise ValueError(f"Eurostat {data.get('label', '')!r}: no {dim} {chosen[dim]!r} (it has {categories[dim]})")
            position.append(categories[dim].index(chosen[dim]))
        elif len(categories[dim]) == 1:
            position.append(0)
        else:
            raise ValueError(f"Eurostat {data.get('label', '')!r}: choose one {dim} of {categories[dim]}")
    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    time_axis = ids.index("time")
    base = sum(index * strides[i] for i, index in zip([i for i, dim in enumerate(ids) if dim != "time"], position))
    values = data.get("value", {})
    periods, numbers = [], []
    for t, period in enumerate(categories["time"]):
        value = values.get(str(base + t * strides[time_axis])) if isinstance(values, dict) else values[base + t * strides[time_axis]]
        if value is not None:
            periods.append(_period_end(period))
            numbers.append(float(value))
    return pd.Series(numbers, index=pd.DatetimeIndex(periods, name=DATE_COLUMN), dtype=float).sort_index()


def eurostat_code(dataset: str, **chosen: str) -> str:
    """The name of a Eurostat series' baked file: its dataset, then the category chosen in each dimension, by the dimension's name (``gov_10dd_edpt1.D41PAY.S13``)."""
    return ".".join([dataset, *(chosen[dimension] for dimension in sorted(chosen))])


def _eurostat_since(dataset: str, day: pd.Timestamp) -> str:
    """``sinceTimePeriod`` asking ``dataset`` for the period holding ``day`` on: ``2024-Q2`` (quarterly), ``2023`` (annual).

    Measured 2026-10-22, for all six datasets: asked from a day, Eurostat
    answers from the first period beginning on or after it, as the ECB does
    (debt asked from 2024-06-30 begins with 2024-Q3, the annual interest
    asked from 2023-12-31 with 2024); asked in the period's own form, from
    that period; ``2024Q2`` is refused (400). A frequency not measured raises.
    """
    frequency = _EUROSTAT_FREQUENCIES[dataset]
    if frequency == "Q":
        return f"{day.year}-Q{day.quarter}"
    if frequency == "A":
        return f"{day.year}"
    raise ValueError(f"Eurostat {dataset}: no sinceTimePeriod form measured for its frequency {frequency!r}")


def eurostat_download(dataset: str, start: pd.Timestamp | None = None) -> dict:
    """Ask Eurostat for one dataset (``EUROSTAT_QUERIES``): its JSON-stat answer, every period, or those from the period holding ``start`` on.

    One request (cached and kept as the others are), which answers every
    series of the dataset. The whole dataset is asked for as before batch
    19.2 (the query alone), so its request is the same. An answer whose
    frequency is not the one measured raises. Eurostat answers a range it
    has no period in with an answer of no periods (status 200), which
    ``parse_jsonstat`` reads as no values.
    """
    params, _unit = EUROSTAT_QUERIES[dataset]
    if start is not None:
        params = params | {"sinceTimePeriod": _eurostat_since(dataset, start)}
    data = de_get(EUROSTAT_DATASET_URL.format(dataset=dataset), params).json()
    frequencies = list(data.get("dimension", {}).get("freq", {}).get("category", {}).get("index", {}))
    if frequencies != [_EUROSTAT_FREQUENCIES[dataset]]:
        raise ValueError(f"Eurostat {dataset}: expected the frequency {_EUROSTAT_FREQUENCIES[dataset]!r}, found {frequencies}")
    return data


def _eurostat_frame(dataset: str, codes: dict[str, dict[str, str]], start: pd.Timestamp | None) -> pd.DataFrame:
    """Series ``codes`` (each file's name -> the categories chosen) of one answer of ``dataset`` (``eurostat_download``), a column each, in the dataset's unit.

    From ``start`` (a recent part), a series with no value raises, naming
    it: the join would otherwise lose its values from there on.
    """
    _params, unit = EUROSTAT_QUERIES[dataset]
    data = eurostat_download(dataset, start)
    columns = {}
    for code, chosen in codes.items():
        columns[code] = parse_jsonstat(data, unit, **chosen)
        if start is not None and columns[code].empty:
            raise ValueError(f"Eurostat gave no values of {code} from {_eurostat_since(dataset, start)}")
    return pd.concat(columns, axis=1).sort_index()


def eurostat_series(dataset: str, **chosen: str) -> pd.Series:
    """Return one series of a Eurostat dataset (``EUROSTAT_QUERIES``), in euros or persons; raises if it has none.

    Batch 19.2 (``ratesplot.baked``): the history of every series read
    (``EUROSTAT_SERIES_READ``) is in ``ratesplot/data/eurostat/``, and only
    the last 24 months are asked for (every one is a statistic Eurostat
    revises: debt, interest, GDP, population), from the period holding that
    date on. One request answers all of a dataset's series, so it is asked
    for once, from the earliest of their bakes' last values less 24 months
    (``baked.frame_with_recent_part``; the download cache is keyed by the
    query, the same for every series of it); a series not baked has its
    dataset asked for whole. If Eurostat fails, the baked history alone, to
    its last value, with a warning naming the series. Measured 2026-10-22:
    the bake joined to its recent part is Eurostat's whole answer, value for
    value, for all twelve.
    """
    _params, unit = EUROSTAT_QUERIES[dataset]
    code = eurostat_code(dataset, **chosen)
    codes = {eurostat_code(dataset, **read): read for read in EUROSTAT_SERIES_READ[dataset]}
    codes.setdefault(code, chosen)  # not one read before, so not baked: the dataset is asked for whole
    frame = frame_with_recent_part(
        EUROSTAT_BAKED_SOURCE, list(codes), f"Eurostat {code}", lambda start: _eurostat_frame(dataset, codes, start), RECENT_PART_REVISED
    )
    # Named as before 19.2 (none): the callers name what they make of it.
    values = frame[code].dropna().rename(None)
    if values.empty:
        raise ValueError(f"Eurostat {dataset} {chosen} has no values")
    return values * _EUROSTAT_MULTIPLIER[unit]


def _before(history: pd.Series | None, live: pd.Series | None) -> pd.Series | None:
    """Return ``history`` until ``live`` begins, then ``live``; either may be missing."""
    if history is None or history.empty:
        return live
    if live is None or live.empty:
        return history
    return pd.concat([history.loc[history.index < live.index[0]], live])


# ---------------------------------------------------------------------------
# Per-curve fetchers
# ---------------------------------------------------------------------------


def de_series_earliest(config: PlotConfig) -> dict[str, pd.Timestamp]:
    """Return the first observation of the German inputs, by name, for the coverage warning.

    The yields are those of the chosen terms Germany has (and the spreads'
    terms), the 10-year from its baked history.
    """
    terms = set(config.yield_terms) | ({term for pair in config.spread_pairs for term in pair} if config.spreads else set())
    earliest: dict[str, pd.Timestamp] = {}
    for term, column in YIELD_TERMS.items():
        if term in terms and column in DE_YIELD_SERIES:
            history = _YIELD_HISTORY.get(column)
            if history:
                earliest[f"{column} Yield (public debt securities before the fitted yield)"] = pd.Timestamp(history[0][0])
            else:
                earliest[f"{column} Yield (Svensson fitted)"] = DE_YIELD_EARLIEST[column]
    return {**earliest, **DE_SERIES_EARLIEST}


def _term_structure(column: str, frequency: str) -> pd.Series:
    """Return one term of the Bundesbank's Svensson term structure, daily ("D") or end-of-month ("M"): its bake and recent part."""
    return bundesbank_series(BUNDESBANK_TERM_STRUCTURE_FLOW, term_structure_key(column, frequency))


def _baked_term(column: str, frequency: str) -> pd.Series:
    """Return one term's series from its bake alone, without asking the Bundesbank; no values if it has no bake."""
    series = read_series(BUNDESBANK_BAKED_SOURCE, f"{BUNDESBANK_TERM_STRUCTURE_FLOW}.{term_structure_key(column, frequency)}")
    return _NO_VALUES if series is None else series


@downloads_of("Bundesbank Federal yields")
def fetch_de_yields(config: PlotConfig) -> pd.DataFrame:
    """Return Germany's Federal yields: each term's monthly values, then its daily ones, date-indexed.

    The 10-year's monthly part begins with the baked yield on public debt
    securities (1956-1972). The columns are the chosen ones Germany has
    (``config.fetched_yield_columns``), trimmed to the window;
    ``attrs[YIELD_HISTORY_ATTR]`` gives each column's last monthly date
    (drawn as steps). A part whose recent values fail is drawn from its
    bake alone, with a warning (``bundesbank_series``); a part without a
    bake that fails is left out with a warning, and the term drawn from the
    rest; a term with nothing left is left out. A bot check is named once,
    and the Bundesbank asked nothing more in the drawing: that part and
    every later one drawn from its bake.
    """
    chosen = [column for column in config.fetched_yield_columns if column in DE_YIELD_SERIES]
    absent = [column for column in config.yield_columns if column not in DE_YIELD_SERIES]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no German {', '.join(absent)} yield; the German chart is drawn without it.")
    if not chosen:
        return pd.DataFrame()

    columns: dict[str, pd.Series] = {}
    history_through: dict[str, pd.Timestamp] = {}
    bot_check: BotCheck | None = None  # the Bundesbank sent one: no more requests
    bake_ends: list[pd.Timestamp] = []  # after it, the last date of each bake drawn
    for column in chosen:
        parts: dict[str, pd.Series] = {}
        for frequency, name in (("M", "end-of-month"), ("D", "daily")):
            if bot_check is None:
                try:
                    parts[frequency] = _term_structure(column, frequency)
                except BotCheck as exc:
                    # Every other request would meet the same check (Terry's VPN,
                    # 2026-10-08): one warning that names it, below, not one per term.
                    bot_check = exc
                except Exception as exc:
                    print(f"  Warning: Bundesbank {column} yield, {name} ({DE_YIELD_SERIES[column]}) unavailable ({exc}); drawn without it.")
                    parts[frequency] = _NO_VALUES
            if bot_check is not None:
                parts[frequency] = _baked_term(column, frequency)
                if not parts[frequency].empty:
                    bake_ends.append(parts[frequency].index[-1])
        baked = embedded_frame(_YIELD_HISTORY.get(column, []), column)
        baked = baked[column] if baked is not None else None
        if baked is not None and not parts["M"].empty:
            # Months averaged (dated by their first day) until the month of
            # the first end-of-month value: 1972-08, then 8.08 on 1972-09-30.
            baked = baked.loc[baked.index < parts["M"].index[0].to_period("M").start_time]
        monthly = _before(baked, parts["M"])
        daily = parts["D"]
        if not daily.empty:
            monthly = monthly.loc[monthly.index < daily.index[0]]
        if monthly.empty and daily.empty:
            continue
        if not monthly.empty:
            history_through[column] = monthly.index[-1]
        columns[column] = pd.concat([monthly, daily]).rename(column)

    if bot_check is not None:
        drawn = (f"The German yields drawn from their baked history, to {max(bake_ends):%Y-%m-%d}." if bake_ends
                 else "No German yield downloaded: only the built-in history is drawn.")
        print(f"  Warning: the Bundesbank ({bot_check.host}) sent a bot check instead of data; a VPN can cause this. {drawn}")
    if not columns:
        return pd.DataFrame()
    frame = pd.concat(columns.values(), axis=1).sort_index()
    for column in frame.columns:
        daily_part = frame.index > history_through.get(column, pd.Timestamp.min)
        frame.loc[daily_part, column] = frame.loc[daily_part, column].ffill(limit=_DAILY_FILL_LIMIT)
    frame = frame.rename_axis(DATE_COLUMN).loc[config.start : config.end]
    frame.attrs[YIELD_HISTORY_ATTR] = history_through
    return frame


def _quarterly_debt(sectors: tuple[str, ...]) -> pd.Series:
    """Return the gross debt of these Eurostat subsectors together, at each quarter's end, in euros."""
    parts = [eurostat_series("gov_10q_ggdebt", sector=sector) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


def _ttm_interest(sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest payable (D.41) by these Eurostat subsectors together, summed over four quarters, in euros."""
    parts = [eurostat_series("gov_10q_ggnfa", sector=sector) for sector in sectors]
    return ttm_sum(pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna())


@downloads_of("ECB and Eurostat government debt")
def fetch_de_debt(config: PlotConfig) -> pd.DataFrame | None:
    """Return general government gross debt: year-end figures (ECB) until Eurostat's quarters begin, then the quarters.

    If Eurostat fails, the year-end figures alone, with a warning; if the
    ECB does, the quarters alone (from 2000), with a warning.
    """
    if not config.include_debt:
        return None
    try:
        annual = ecb_series(*ECB_ANNUAL_DEBT, revised=True)
    except Exception as exc:
        print(f"  Warning: ECB annual German debt unavailable ({exc}); drawn from 2000.")
        annual = None
    try:
        quarterly = _quarterly_debt((GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly German debt unavailable ({exc}); the year-end figures alone.")
        quarterly = None
    joined = _before(annual, quarterly)
    return joined.rename(DE_DEBT_COLUMN).to_frame() if joined is not None else None


@downloads_of("Eurostat GDP")
def fetch_de_gdp(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: four-quarter sums of Eurostat's quarters (from 1991); None, with a warning, if it fails."""
    if not config.needs_gdp:
        return None
    try:
        return ttm_sum(eurostat_series("namq_10_gdp")).rename(GDP_COLUMN).to_frame()
    except Exception as exc:
        print(f"  Warning: Eurostat German GDP unavailable ({exc}); not drawn.")
        return None


@downloads_of("Eurostat interest outlays")
def fetch_de_interest(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month general government interest payable: the annual figures (1995-), then four-quarter sums (2002-).

    Either alone, with a warning, if the other fails; None if both do.
    """
    if not config.include_interest:
        return None
    try:
        annual = eurostat_series("gov_10dd_edpt1", **_ANNUAL_INTEREST)
    except Exception as exc:
        print(f"  Warning: Eurostat annual German interest unavailable ({exc}); drawn from 2002.")
        annual = None
    try:
        quarterly = _ttm_interest((GENERAL_GOVERNMENT,))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly German interest unavailable ({exc}); the annual figures alone.")
        quarterly = None
    joined = _before(annual, quarterly)
    return joined.rename(DE_INTEREST_COLUMN).to_frame() if joined is not None else None


@downloads_of("Eurostat debt and interest by level of government")
def fetch_de_components(config: PlotConfig) -> pd.DataFrame | None:
    """Return debt and TTM interest by level of government (--debt:LETTERS): federal, Länder, local, Länder and local.

    Quarterly only (debt from 2000, interest from 2002): Eurostat's annual
    tables have the levels only lately. A level whose source fails is left
    out, with a warning.
    """
    columns: list[pd.Series] = []
    for letter in COMPONENT_LETTERS:
        if letter not in config.components:
            continue
        sectors = _LEVEL_SECTORS[letter]
        for kind, include, fetch in (("debt", config.include_debt, _quarterly_debt), ("interest", config.include_interest, _ttm_interest)):
            if not include:
                continue
            try:
                values = fetch(sectors)
            except Exception as exc:
                print(f"  Warning: Eurostat German {kind}, level {letter} ({'+'.join(sectors)}) unavailable ({exc}); not drawn.")
                continue
            columns.append(values.rename(component_column(kind, letter)))
    return pd.concat(columns, axis=1).sort_index() if columns else None


@downloads_of("Eurostat population")
def fetch_de_population() -> pd.Series | None:
    """Return Germany's population for -p: the 1 January counts (from 1960; West Germany to 1990) until the quarters begin (1991).

    The quarters (thousands) are dated by their middles, the counts by 1
    January. Either alone, with a warning, if the other fails.
    """
    try:
        annual = eurostat_series("demo_pjan")
        annual = annual.set_axis(pd.DatetimeIndex(annual.index.to_period("Y").start_time, name=DATE_COLUMN))
    except Exception as exc:
        print(f"  Warning: Eurostat German population on 1 January unavailable ({exc}); from 1991 only.")
        annual = None
    try:
        quarterly = eurostat_series("namq_10_pe")
        middles = quarterly.index.to_period("Q").start_time + pd.Timedelta(days=_QUARTER_MIDDLE_DAYS)
        quarterly = quarterly.set_axis(pd.DatetimeIndex(middles, name=DATE_COLUMN))
    except Exception as exc:
        print(f"  Warning: Eurostat quarterly German population unavailable ({exc}); the 1 January counts alone.")
        quarterly = None
    joined = _before(annual, quarterly)
    return joined.rename(POPULATION_COLUMN) if joined is not None else None
