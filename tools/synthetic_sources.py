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
    "DGS1MO": 1 / 12, "DGS3MO": 0.25, "DGS6MO": 0.5, "DGS1": 1, "DGS2": 2, "DGS5": 5, "DGS7": 7,
    "DGS10": 10, "DGS20": 20, "DGS30": 30,
}
_DAILY_START = {
    "DGS1MO": "2001-07-31", "DGS3MO": "1981-09-01", "DGS6MO": "1981-09-01", "DGS1": "1962-01-02",
    "DGS2": "1976-06-01", "DGS5": "1962-01-02", "DGS7": "1969-07-01", "DGS10": "1962-01-02",
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
}


def _quarter_points(values: np.ndarray) -> np.ndarray:
    """An announced rate from a path: rounded to quarter points, never below zero."""
    return np.maximum(np.round(values * 4) / 4, 0.0)


# Every FRED series ``fred`` answers.
_FRED_IDS = ("FEDFUNDS", "DFEDTAR", "DFEDTARL", "DFEDTARU", "MORTGAGE30US", "MORTGAGE15US", *_GROWTH, *_DAILY_START)


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
    elif series_id in _GROWTH:
        start, freq, first, last = _GROWTH[series_id]
        end = "2026-07-01" if freq == "QS" else "2025-01-01"
        dates = pd.date_range(start, end, freq=freq)
        values = np.round(_growth(dates, first, last, series_id), 1)
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
                values = _yield_path(series_id, dates, _TENOR_YEARS[series_id])
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
_MILLIONS = {"UOM": "Dollars", "SCALAR_FACTOR": "millions", "SCALAR_ID": 6}
_UNITS = {"SCALAR_FACTOR": "units", "SCALAR_ID": 0}
_STATCAN_TABLES = ("36100467", "36100104", "10100015", "17100009", "34100145")


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


def ons(cdid: str) -> bytes:
    """An ONS time series's JSON: its description (with the unit) and lists of months, quarters and years."""
    unit, first, kind, low, high, has_months = _ONS_SERIES[cdid]
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


def bundesbank(url: str) -> bytes:
    """A Bundesbank series CSV: its key and metadata lines, then ``date,value,flag`` ("." on days without a value).

    The same answer from its download (``/rest/download/``) and its SDMX web
    service (``/rest/data/``, batch 19.2), whole, whatever period it is asked
    from (``startPeriod``), as the other baked sources' answers are: the
    program cuts what it asked for.
    """
    key = re.split(r"/rest/(?:download|data)/", url)[1].replace("/", ".", 1)
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
    ("GFS", "A.N.DE.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T", "XDC"),
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
        band = {"I": 3, "O": 10, "P": 20}[key.split(".")[4]]
        values = list(np.round(_yield_path("demir" + key, months, band, _DE_OFFSET) + 1.4, 2))
        periods = [f"{day:%Y-%m}" for day in months]
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
# dataset and the categories chosen (de_data.EUROSTAT_SERIES_READ; batch 19.2).
_EUROSTAT_SERIES = {
    **{f"{dataset}.{sector}": (dataset, {"sector": sector})
       for dataset in ("gov_10q_ggdebt", "gov_10q_ggnfa") for sector in ("S13", "S1311", "S1312", "S1313")},
    "gov_10dd_edpt1.D41PAY.S13": ("gov_10dd_edpt1", {"sector": "S13", "na_item": "D41PAY"}),
    "namq_10_gdp": ("namq_10_gdp", {}),
    "namq_10_pe": ("namq_10_pe", {}),
    "demo_pjan": ("demo_pjan", {}),
}


def eurostat(url: str, params: tuple) -> bytes:
    """A Eurostat JSON-stat answer for the query the program sends (``de_data.EUROSTAT_QUERIES``).

    Whole, whatever period it is asked from (``sinceTimePeriod``, batch 19.2),
    as the other baked sources' answers are: the program cuts what it asked for.
    """
    dataset = url.rstrip("/").rsplit("/", 1)[1]
    query = dict(params)
    unit = query.get("unit", "NR")
    quarters = lambda first, last: [f"{p.year}-Q{p.quarter}" for p in pd.period_range(first, last, freq="Q")]  # noqa: E731
    fixed = [(dim, [query[dim]]) for dim in ("na_item", "s_adj", "age", "sex") if dim in query]
    common = [("freq", ["Q"]), ("unit", [unit]), *fixed, ("geo", ["DE"])]

    def path(name: str, periods: list[str], first: float, last: float) -> dict[str, float]:
        dates = pd.DatetimeIndex([pd.Period(period.replace("-", ""), freq="Q" if "Q" in period else "Y").end_time.normalize() for period in periods])
        return dict(zip(periods, _growth(dates, first, last, name)))

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
    if "ons.gov.uk" in url:
        return _response(ons(url.split("/timeseries/")[1].split("/")[0].upper()))
    if "api.statistiken.bundesbank.de/rest/download/" in url or "api.statistiken.bundesbank.de/rest/data/" in url:
        return _response(bundesbank(url))
    if "data-api.ecb.europa.eu/service/data/" in url:
        return _response(ecb(url))
    if "ec.europa.eu/eurostat/api/dissemination" in url:
        return _response(eurostat(url, params))
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
    valet_url = "https://www.bankofcanada.ca/valet/observations/"
    group = http.parse_boc_csv(valet(f"{valet_url}group/bond_yields_benchmark/csv", ()).decode())
    for code in group.columns:
        bake("boc", code, pd.to_numeric(group[code], errors="coerce"))
    for code in _VALET_SERIES:
        bake("boc", code, pd.to_numeric(http.parse_boc_csv(valet(f"{valet_url}{code}/csv", ()).decode()).iloc[:, 0], errors="coerce"))
    for code in _FRED_IDS:
        bake("fred", code, fred(code).set_index("DATE")[code])
    de_data = importlib.import_module("ratesplot.de_data")
    for flow, key, unit in _ECB_SERIES:
        answer = ecb(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}").decode()
        bake("ecb", f"{flow}.{key}", de_data.parse_ecb_csv(answer, f"{flow}.{key}", unit))
    for code, (dataset, chosen) in _EUROSTAT_SERIES.items():
        params, unit = de_data.EUROSTAT_QUERIES[dataset]
        answer = json.loads(eurostat(f"{_EUROSTAT_URL}{dataset}", tuple(sorted(params.items()))))
        bake("eurostat", code, de_data.parse_jsonstat(answer, unit, **chosen))
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
    # Statistics Canada's live tables, each vector read, selected by the program's own labels (a tree before
    # 19.2's Statistics Canada stage has no STATCAN_SERIES_READ, and reads no Statistics Canada file).
    cdn_data = importlib.import_module("ratesplot.cdn_data")
    if hasattr(cdn_data, "STATCAN_SERIES_READ"):
        for table_id in cdn_data.STATCAN_SERIES_READ:
            with zipfile.ZipFile(io.BytesIO(statcan(table_id))) as archive:
                table = pd.read_csv(io.BytesIO(archive.read(f"{table_id}.csv")), low_memory=False)
            for vector, values in cdn_data._statcan_vectors(table, table_id).items():
                bake(cdn_data.STATCAN_BAKED_SOURCE, vector, values)
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
