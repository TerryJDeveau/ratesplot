#!/usr/bin/env python3
"""Check Germany's parsers against responses saved from the real sources (batch 4); offline, in seconds.

The cloud copy cannot reach the Bundesbank, the ECB, Eurostat or CNBC, so
the parsers were written against responses saved on Terry's laptop on
2026-10-06 (``tools/de_fixtures/raw``, listed with their URLs in
``_index.tsv``). Each check reads a saved response through the program's
own code and compares a value read off the response by eye. The fetchers
themselves are run too: ``de_get`` is replaced by a reader of the saved
files, chosen by the URL and query the program asks for, so a request that
differs from the one measured fails here. The saved responses are whole
series, so the fetchers are run without the live sources' bake (batch 19.2):
each series asked for whole, as before it, and none joined to a recent part
the saved responses do not hold.

* the Bundesbank's CSV: daily and end-of-month term structure, each term's
  first month as ``DE_YIELD_EARLIEST`` says, the old database's frozen
  series, and the answers it must refuse (an unknown series, a 404, a
  changed unit); the baked history equals the saved download; the
  discount rate's change days read from its comments (batch 9.6), and the
  Lombard rate refused;
* the ECB's CSV: key rates on their change days, annual debt, bank lending
  rates; a wrong key, a wrong unit and an error page refused;
* Eurostat's JSON-stat: debt and interest by sector, GDP, population; the
  joins the chart makes (annual debt and interest against the quarters,
  the levels against the total, population at unification);
* CNBC's German quotes: every symbol the chart asks for is there and readable;
* the joined curves: yields, debt, interest, GDP, population, levels, and
  (``rates``) the policy rate and the mortgage rates;
* the Bundesbank's bot check (batch 19.2): asked once in a drawing and named
  once; with the bake, every term drawn from it to its last date; without
  it, the built-in history alone, as before.

The live check of the same sources is ``tools/check_sources.py``.

Usage (from the project root)::

    python tools/check_de_parsers.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import numpy as np
import openpyxl
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import bake, baked, de_archive_data, de_data, latest, measures, rates  # noqa: E402
from ratesplot.config import CNBC_QUOTE_URL, COMPONENT_LETTERS, DE, DE_DEBT_COLUMN, DE_INTEREST_COLUMN, GDP_COLUMN, PlotConfig, component_column  # noqa: E402
from ratesplot.http import BotCheck  # noqa: E402

RAW = ROOT / "tools" / "de_fixtures" / "raw"
RESULTS: list[bool] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    shown = f"  [{detail}]" if not condition or detail else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}")


def raises(call, *args, **kwargs) -> str | None:
    """The exception's type and message if ``call(*args)`` raises, else None."""
    try:
        call(*args, **kwargs)
    except Exception as exc:  # what is raised is the point
        return f"{type(exc).__name__}: {exc}"
    return None


def text(name: str) -> str:
    return (RAW / name).read_text(encoding="utf-8")


def _request_key(url: str, params: dict | None = None) -> tuple[str, frozenset]:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query)) | {key: str(value) for key, value in (params or {}).items()}
    return f"{parts.scheme}://{parts.netloc}{parts.path}", frozenset(query.items())


def _saved_answers() -> dict[tuple[str, frozenset], tuple[str, int]]:
    """The saved responses by request: ``_index.tsv``'s URL (and query) -> (file, HTTP status)."""
    answers = {}
    for line in (RAW / "_index.tsv").read_text(encoding="utf-8").splitlines():
        cells = line.split("\t")
        if len(cells) >= 7 and (RAW / cells[0]).exists() and cells[1].isdigit():
            answers[_request_key(cells[6])] = (cells[0], int(cells[1]))
    return answers


SAVED = _saved_answers()


def saved_get(url: str, params: dict | None = None, **_kwargs) -> requests.Response:
    """Answer a request from the saved responses, as ``http.de_get`` would; a request never measured raises."""
    key = _request_key(url, params)
    if key not in SAVED:
        raise requests.ConnectionError(f"no saved response for {url} {params}")
    name, status = SAVED[key]
    response = requests.Response()
    response.status_code, response.url, response.encoding = status, url, "utf-8"
    response._content = (RAW / name).read_bytes()
    response.raise_for_status()
    return response


def check_bundesbank() -> None:
    parse = de_data.parse_bundesbank_csv
    monthly = parse(text("bbk_ts_m_R10XX.csv"))
    check("Bundesbank monthly 10-year: 1972-09 dated its last day, 8.08",
          monthly.index[0] == pd.Timestamp("1972-09-30") and monthly.iloc[0] == 8.08, monthly.head(1).to_dict())
    check("Bundesbank monthly 10-year: 2026-09, 3.64", monthly.loc["2026-09-30"] == 3.64)
    daily = parse(text("bbk_ts_d_R10XX.csv"))
    check("Bundesbank daily 10-year: 2026-10-06, 3.52; the first value 1997-08-07",
          daily.loc["2026-10-06"] == 3.52 and daily.index[0] == pd.Timestamp("1997-08-07"), daily.index[0])
    check("Bundesbank daily: days without a value ('.') are left out", pd.Timestamp("2026-10-04") not in daily.index)
    first_30 = parse(text("bbk_ts_d_R30XX.csv"))
    check("Bundesbank daily 30-year from 2000-08-01, 5.49", first_30.index[0] == pd.Timestamp("2000-08-01") and first_30.iloc[0] == 5.49)
    firsts = {column: parse(text(f"bbk_ts_m_{code}.csv")).index[0] for column, code in de_data.DE_YIELD_SERIES.items()}
    check("Bundesbank: each term's first month is DE_YIELD_EARLIEST", firsts == de_data.DE_YIELD_EARLIEST, firsts)
    old_end_of_month = parse(text("bbk01_WZ9826.csv"))
    both = pd.concat([old_end_of_month, monthly], axis=1).dropna()
    apart = (both.iloc[:, 0] - both.iloc[:, 1]).abs()
    check("Bundesbank: the monthly term structure is the old database's end-of-month series (WZ9826), 1972-2020, within 0.01",
          len(both) > 500 and apart.max() <= 0.0100001, (len(both), int((apart > 0).sum()), apart.max()))
    check("Bundesbank: an unknown series of the old database is refused", raises(parse, text("bbk01_SU0112.csv")) is not None)
    check("Bundesbank: a 404 answer is refused", raises(parse, text("bbk_ts_m_R00X5.csv")) is not None)
    changed = text("bbk_ts_m_R10XX.csv").replace("BBK_UNIT_ENG,percent", "BBK_UNIT_ENG,index")
    check("Bundesbank: a changed unit is refused", raises(parse, changed) is not None)
    wu0004 = parse(text("bbk01_WU0004.csv"))
    baked = pd.Series({pd.Timestamp(date): value for date, value in de_archive_data.EMBEDDED_DE_PUBLIC_DEBT_YIELD_HISTORY})
    check("bake: the baked public debt yield is the saved WU0004, each month dated by its first day",
          list(baked.to_numpy()) == list(wu0004.to_numpy()) and (baked.index == wu0004.index.to_period("M").start_time).all()
          and baked.index[0] == pd.Timestamp("1956-05-01"), (len(baked), len(wu0004)))


def check_discount_rate() -> None:
    """Batch 9.6: the discount rate's change days, read from the download's comments (saved 2026-10-21)."""
    changes = bake.parse_bundesbank_change_days(text("bbin1_BBKDIS.csv"))
    check("discount rate: 94 changes, 5.00 from 1948-07-01, 2.50 from 1996-04-19 (to 1998-12-31)",
          len(changes) == 94 and changes.iloc[0] == 5.0 and changes.index[0] == pd.Timestamp("1948-07-01")
          and changes.index[-1] == pd.Timestamp("1996-04-19") and changes.iloc[-1] == 2.5, (len(changes), changes.tail(1).to_dict()))
    check("discount rate: 8.75 from 1992-07-17, the peak", changes.loc["1992-07-17"] == 8.75 and changes.max() == 8.75)
    baked = pd.Series({pd.Timestamp(date): value for date, value in de_archive_data.EMBEDDED_DE_DISCOUNT_RATE_CHANGES})
    check("bake: the baked changes are the saved download's", baked.equals(changes.rename(None)), (len(baked), len(changes)))
    check("discount rate: the Lombard rate is refused (its special rate in the month-end values, 1973-74, 1981-82)",
          raises(bake.parse_bundesbank_change_days, text("bbin1_BBKLOM.csv")) is not None)
    altered = text("bbin1_BBKDIS.csv").replace("Comment on 1995-08: From 25 August 3.50%", "Comment on 1995-08: From 25 August 3.75%")
    check("discount rate: a comment that disagrees with the month-end values is refused",
          raises(bake.parse_bundesbank_change_days, altered) is not None)


def check_west_prices() -> None:
    """Batch 16: West Germany's consumer prices, read from the Federal Statistical Office's workbook (saved 2026-11-04), and the joins."""
    workbook = openpyxl.load_workbook(RAW / "destatis_vpi_lange_reihen.xlsx", read_only=True, data_only=True)
    read = bake.parse_west_german_prices(workbook)
    west, four = read["all_households"], read["four_person"]
    check("West prices: all private households 1962-01 to 1991-01, every month, 32.7 and 87.3",
          len(west) == 349 and west.index[0] == pd.Timestamp("1962-01-01") and west.iloc[0] == 32.7
          and west.index[-1] == pd.Timestamp("1991-01-01") and west.iloc[-1] == 87.3, (len(west), west.iloc[0], west.iloc[-1]))
    check("West prices: four-person households 1948-06 to 1962-01, every month, 25.8 and 33.1",
          len(four) == 164 and four.index[0] == pd.Timestamp("1948-06-01") and four.iloc[0] == 25.8
          and four.index[-1] == pd.Timestamp("1962-01-01") and four.iloc[-1] == 33.1, (len(four), four.iloc[0], four.iloc[-1]))
    for name, values, rows in (("all private households", west, de_archive_data.EMBEDDED_DE_WEST_CPI_ALL_HOUSEHOLDS),
                               ("four-person households", four, de_archive_data.EMBEDDED_DE_WEST_CPI_FOUR_PERSON)):
        baked_values = pd.Series({pd.Timestamp(date): value for date, value in rows})
        check(f"bake: the baked {name} are the workbook's", baked_values.equals(values.rename(None)), (len(baked_values), len(values)))
    moved = dict(bake._DE_WEST_CPI_COLUMNS)
    with_moved_column = {**moved, "all_households": (5, *moved["all_households"][1:])}
    bake._DE_WEST_CPI_COLUMNS = with_moved_column
    check("West prices: a column whose heading is not the one measured is refused", raises(bake.parse_west_german_prices, workbook) is not None)
    bake._DE_WEST_CPI_COLUMNS = moved
    begins_elsewhere = {**moved, "four_person": (*moved["four_person"][:2], pd.Timestamp("1948-07-01"), moved["four_person"][3])}
    bake._DE_WEST_CPI_COLUMNS = begins_elsewhere
    check("West prices: an index beginning elsewhere than measured is refused", raises(bake.parse_west_german_prices, workbook) is not None)
    bake._DE_WEST_CPI_COLUMNS = moved
    workbook.close()
    # The joins, on a made-up index for all of Germany from 1991-01 at twice the source's 87.3.
    months = pd.date_range("1991-01-31", periods=24, freq="ME")
    unified = pd.Series(np.arange(174.6, 174.6 + 24), index=months, name="made up")
    joined = de_data.with_west_germany(unified)
    check("join: the index for all of Germany is unchanged from its first month", joined.loc[months].equals(unified), joined.loc[months].head(2).to_dict())
    check("join: West Germany's keeps its own rise across 1990-12 to 1991-01 (87.3 over 86.7)",
          abs(joined.loc["1991-01-31"] / joined.loc["1990-12-31"] - 87.3 / 86.7) < 1e-12, joined.loc["1990-12-31"])
    check("join: all private households scaled by the one factor, 2 in this case", abs(joined.loc["1962-01-31"] - 2 * 32.7) < 1e-9, joined.loc["1962-01-31"])
    check("join: the four-person households keep their own rise to 1962-01 (33.1 over 32.9 in 1961-12)",
          abs(joined.loc["1962-01-31"] / joined.loc["1961-12-31"] - 33.1 / four.loc["1961-12-01"]) < 1e-12, joined.loc["1961-12-31"])
    check("join: every month from 1948-06, none twice",
          joined.index.equals(pd.date_range("1948-06-30", months[-1], freq="ME")), (joined.index[0], len(joined)))
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        alone = de_data.with_west_germany(pd.Series([1.0], index=pd.DatetimeIndex(["1999-01-31"]), name="made up"))
    check("join: an index beginning where West Germany's is not kept is returned alone, with a warning",
          len(alone) == 1 and "where West Germany's are not kept" in printed.getvalue(), (len(alone), printed.getvalue()))


def check_west_population() -> None:
    """Batch 16: West Germany's population, read from the page of the Bundesbank's long series (saved 2026-11-04), and its join to Eurostat's counts."""
    page = text("bbk_lange_zeitreihen_V1.txt")
    column = bake.parse_long_series_population(page)
    check("long series: 70 years, 49,989 thousand in 1950, 54,876 in 1959, 55,433 in 1960, 83,093 in 2019",
          len(column) == 70 and column.iloc[0] == 49_989 and column.loc["1959-07-01"] == 54_876 and column.loc["1960-07-01"] == 55_433 and column.iloc[-1] == 83_093,
          (len(column), column.iloc[0], column.iloc[-1]))
    check("long series: 64,074 thousand in 1991 (West Germany), 80,594 in 1992 (all of Germany), as the table's note says",
          column.loc["1991-07-01"] == 64_074 and column.loc["1992-07-01"] == 80_594, column.loc["1990-07-01":"1993-07-01"].to_dict())
    baked_values = pd.Series({pd.Timestamp(date): value for date, value in de_archive_data.EMBEDDED_DE_WEST_POPULATION}, dtype=float)
    check("bake: the baked ten years are the column's first ten, each dated 1 July",
          baked_values.equals(column.iloc[:10].rename(None).rename_axis(None)), (len(baked_values), baked_values.index[-1]))
    # The places in the column against a source of its own: each year from 1960 to 1988 against
    # the mean of Eurostat's counts on the 1 January before and after it (the census of 1970 the widest).
    january = de_data.parse_jsonstat(jsonstat("est_pjan_a"), "NR") / 1000
    gaps = {year: abs(column.loc[f"{year}-07-01"] / ((january.loc[f"{year}-12-31"] + january.loc[f"{year + 1}-12-31"]) / 2) - 1) for year in range(1960, 1989)}
    check("long series: every year 1960 to 1988 within 0.75 % of the mean of Eurostat's counts either side of it, all but 1970 within 0.35 %",
          max(gaps.values()) < 0.0075 and all(gap < 0.0035 for year, gap in gaps.items() if year != 1970), max(gaps, key=gaps.get))
    check("long series: a heading gone is refused", raises(bake.parse_long_series_population, page.replace("Jahresdurchschnitte", "Jahresenden")) is not None)
    check("long series: a row gone is refused", raises(bake.parse_long_series_population, page.replace("53.008", "")) is not None)
    lines = page.splitlines()
    first_rows = [number for number, line in enumerate(lines) if bake._DE_LONG_SERIES_POPULATION_ROW.match(line)]
    swapped = lines[:first_rows[-1]] + lines[first_rows[-1] + 1:]
    swapped.insert(first_rows[0], lines[first_rows[-1]])
    check("long series: a row out of its place, so that unification falls elsewhere, is refused", raises(bake.parse_long_series_population, "\n".join(swapped)) is not None)
    people = de_data.west_german_population()
    check("reader: persons, 1950-07-01 to 1959-07-01", people.index[0] == pd.Timestamp("1950-07-01") and people.iloc[0] == 49_989_000
          and people.index[-1] == pd.Timestamp("1959-07-01") and len(people) == 10, people.iloc[-1])


def csv_rows(name: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text(name))))


def check_german_debt() -> None:
    """Batch 16: Germany's debt in total and by level, read from the extract of Fachserie 14 Reihe 5 (saved 2026-11-05), its bake, its joins and its population."""
    rows = csv_rows("destatis_fs14_r5_debt.csv")
    read = bake.parse_german_debt(rows)
    total, each = read["total"], read["per_person"]
    check("debt: the total, 42 dates from 1950-03-31 to 1991-12-31, 9,573.94 and 599,511.2",
          len(total) == 42 and total.index[0] == pd.Timestamp("1950-03-31") and total.iloc[0] == 9573.94 and total.index[-1] == pd.Timestamp("1991-12-31") and total.iloc[-1] == 599511.2, len(total))
    check("debt: 31 March to 1959, 31 December from 1960, nothing between", total.index[9] == pd.Timestamp("1959-03-31") and total.index[10] == pd.Timestamp("1960-12-31"), total.index[10])
    check("debt: a date written with its footnote is read: 31.03.1952, 31.03.1958, 31.12.1960", total.loc["1952-03-31"] == 12276.12 and total.loc["1958-03-31"] == 23991.35 and total.loc["1960-12-31"] == 28998.43, total.loc["1952-03-31"])
    check("debt: per person to 1959, 190.2003 and 461.9329", len(each) == 10 and each.iloc[0] == 190.2003 and each.iloc[-1] == 461.9329, each.iloc[-1])
    check("debt: each level on 51 dates to 2000, 1990's 306,315.48, 168,001.82, 64,016.81",
          all(len(read[name]) == 51 and read[name].index[-1] == pd.Timestamp("2000-12-31") for name in ("federal", "states", "local"))
          and (read["federal"].loc["1990-12-31"], read["states"].loc["1990-12-31"], read["local"].loc["1990-12-31"]) == (306315.48, 168001.82, 64016.81), read["federal"].loc["1990-12-31"])
    for name, values in read.items():
        baked_values = pd.Series({pd.Timestamp(date): value for date, value in getattr(de_archive_data, f"EMBEDDED_DE_DEBT_{name.upper()}")}, dtype=float)
        check(f"bake: EMBEDDED_DE_DEBT_{name.upper()} holds the extract", baked_values.equals(values.rename(None).rename_axis(None)), len(baked_values))
    # Refusals: a table that moved a column or a unit, lost a date, or whose levels no longer add up.
    title_at = next(number for number, row in enumerate(rows) if row[0].startswith("1.1.1"))
    heading_at = next(number for number, row in enumerate(rows) if row[0] == "Stichtag")
    units_at = next(number for number, row in enumerate(rows) if "Mill. EUR" in row[1])
    first_at = next(number for number, row in enumerate(rows) if row[0].startswith("1950-03-31"))
    changed = lambda at, row: [*rows[:at], row, *rows[at + 1 :]]  # noqa: E731
    check("debt: another title is refused", raises(bake.parse_german_debt, changed(title_at, ["1.1.1 Schulden insgesamt", *rows[title_at][1:]])) is not None)
    check("debt: columns swapped are refused", raises(bake.parse_german_debt, changed(heading_at, [rows[heading_at][0], rows[heading_at][3], "", rows[heading_at][1], *rows[heading_at][4:]])) is not None)
    check("debt: another unit is refused", raises(bake.parse_german_debt, [[cell.replace("Mill. EUR", "Mill. DM") for cell in row] if number == units_at else row for number, row in enumerate(rows)]) is not None)
    check("debt: a date gone is refused", raises(bake.parse_german_debt, [row for row in rows if not row[0].startswith("1975-12-31")]) is not None)
    check("debt: a level a million off is not, three million off is",
          raises(bake.parse_german_debt, changed(first_at, [rows[first_at][0], str(float(rows[first_at][1]) + 1), *rows[first_at][2:]])) is None
          and raises(bake.parse_german_debt, changed(first_at, [rows[first_at][0], str(float(rows[first_at][1]) + 3.5), *rows[first_at][2:]])) is not None)
    # The joins, on made-up live series: the total to the ECB's first year end, a level to Eurostat's quarters.
    office = de_data._debt_in_euros(de_archive_data.EMBEDDED_DE_DEBT_TOTAL)
    live = pd.Series([618_218e6, 705_567e6], index=pd.to_datetime(["1991-12-31", "1992-12-31"]))
    joined = de_data._with_older_debt(office, live)
    ratio = 618_218 / 599_511.2
    check("join: the total's first figure and the live figures stay, its own 1991 gone", joined.index[0] == pd.Timestamp("1950-03-31") and joined.loc["1991-12-31"] == 618_218e6 and joined.loc["1992-12-31"] == 705_567e6 and len(joined) == 43, len(joined))
    check("join: 1986 and all before it as published, the steps at 1952 and 1960 kept", joined.loc[:"1986-12-31"].equals(office.loc[:"1986-12-31"]), joined.loc["1986-12-31"])
    check("join: 1990 raised 3.12 %, to 555.13 billion; 1991's rise the table's own", abs(joined.loc["1990-12-31"] / office.loc["1990-12-31"] - ratio) < 1e-9 and abs(joined.loc["1990-12-31"] / 1e9 - 555.13) < 0.01
          and abs(joined.loc["1991-12-31"] / joined.loc["1990-12-31"] - office.loc["1991-12-31"] / office.loc["1990-12-31"]) < 1e-9, joined.loc["1990-12-31"])
    check("join: the ramp is geometric over 1986 to 1990", abs(joined.loc["1988-12-31"] / office.loc["1988-12-31"] - ratio ** 0.5) < 1e-9, joined.loc["1988-12-31"])
    quarters = pd.date_range("2000-03-31", "2001-03-31", freq="QE")
    made_up = {
        ("S1311",): pd.Series([820e9, 821e9, 822e9, 814_963e6, 815e9], index=quarters),
        ("S1312",): pd.Series([345e9, 346e9, 347e9, 354_552e6, 355e9], index=quarters),
        ("S1313",): pd.Series([114e9, 114e9, 114e9, 109_615e6, 110e9], index=quarters),
        (de_data.GENERAL_GOVERNMENT,): pd.Series([1265e9, 1264e9, 1274e9, 1262e9, 1263e9], index=quarters),
    }

    def down(*_args, **_named):
        raise RuntimeError("down")

    real_quarterly, real_ecb = de_data._quarterly_debt, de_data.ecb_series
    config = PlotConfig(start=pd.Timestamp("1950-01-01"), end=pd.Timestamp("2005-01-01"))
    said = io.StringIO()
    try:
        de_data._quarterly_debt = made_up.__getitem__
        federal, states, local, together = (de_data._debt_of_level(sectors) for sectors in (("S1311",), ("S1312",), ("S1313",), ("S1312", "S1313")))
        with contextlib.redirect_stdout(said):
            de_data.ecb_series = down
            no_ecb = de_data.fetch_de_debt(config)[DE_DEBT_COLUMN]
            de_data.ecb_series = lambda *_args, **_named: live
            de_data._quarterly_debt = down
            no_eurostat = de_data.fetch_de_debt(config)[DE_DEBT_COLUMN]
    finally:
        de_data._quarterly_debt, de_data.ecb_series = real_quarterly, real_ecb
    check("down: the ECB gone, Eurostat's quarters alone, said so: West Germany's would be drawn straight across to them", no_ecb.index[0] == pd.Timestamp("2000-03-31") and "drawn from 2000" in said.getvalue(), no_ecb.index[0])
    check("down: Eurostat gone, West Germany's and the ECB's, said so", no_eurostat.index[0] == pd.Timestamp("1950-03-31") and no_eurostat.loc["1992-12-31"] == 705_567e6 and "year-end figures alone" in said.getvalue(), no_eurostat.index[-1])
    office_federal = de_data._debt_in_euros(de_archive_data.EMBEDDED_DE_DEBT_FEDERAL)
    office_states = de_data._debt_in_euros(de_archive_data.EMBEDDED_DE_DEBT_STATES)
    office_local = de_data._debt_in_euros(de_archive_data.EMBEDDED_DE_DEBT_LOCAL)
    check("join: a level as published to 1995, raised at 1999 by Eurostat's ratio at 2000's end, 5.18 %, then Eurostat's alone",
          federal.loc[:"1995-12-31"].equals(office_federal.loc[:"1995-12-31"]) and abs(federal.loc["1999-12-31"] / office_federal.loc["1999-12-31"] - 814_963e6 / office_federal.loc["2000-12-31"]) < 1e-9
          and federal.loc["2000-03-31"] == 820e9 and pd.Timestamp("2000-12-31") in federal.index and federal.loc["2000-12-31"] == 814_963e6, federal.loc["1999-12-31"])
    check("join: Länder and local together: the two tables' sum in 1980, and exactly the two joined lines added up on every date, the ramps included",
          abs(together.loc["1980-12-31"] - office_states.loc["1980-12-31"] - office_local.loc["1980-12-31"]) < 1e-3 and together.equals((states + local).dropna().rename(together.name)), together.loc["1999-12-31"])
    # The population behind it.
    people = de_data.west_german_debt_population()
    check("population: to 1959 the debt over its figure per person: 50,336 and 55,124 thousand, 1951's rounded figure kept",
          round(people.loc["1950-03-31"] / 1e3) == 50_336 and round(people.loc["1959-03-31"] / 1e3) == 55_124 and abs(people.loc["1951-03-31"] / 1e3 - 50_692.6) < 0.1, people.loc["1959-03-31"])
    check("population: the population drawn from 1960-12-31 and from 1991-12-31", pd.isna(people.loc["1960-12-31"]) and pd.isna(people.loc["1991-12-31"]), people.notna().sum())
    gdp_people = de_data.west_german_gdp_population()
    check("population: through 1990 and 1991 West Germany's, the same as its GDP's", np.isclose(people.loc["1990-12-31"], gdp_people.loc["1990-12-31"]) and 63_000_000 < people.loc["1990-12-31"] < 64_000_000, people.loc["1990-12-31"])
    own = de_data.west_german_own_populations()
    check("population: GDP's its own; the total's and every level's debt the debt's; interest none", own[GDP_COLUMN].equals(gdp_people) and all(own[column].equals(people) for column in (DE_DEBT_COLUMN, *(component_column("debt", letter) for letter in COMPONENT_LETTERS)))
          and DE_INTEREST_COLUMN not in own, sorted(own))
    dates = pd.to_datetime(["1950-03-31", "1952-03-31", "1959-04-01", "1961-01-01", "1990-12-31", "1991-01-01", "1991-12-31"])
    values = [9573.94e6, 12276.12e6, 25463.4e6, 28998.43e6, 555.13e9, 555.13e9, 618.218e9]
    column = component_column("debt", "f")
    frame = pd.DataFrame({"DATE": dates, DE_DEBT_COLUMN: values, column: [value / 2 for value in values]})
    frame.loc[5, [DE_DEBT_COLUMN, column]] = frame.loc[4, [DE_DEBT_COLUMN, column]].to_numpy()
    drawn = pd.Series([50e6, 80e6], index=pd.to_datetime(["1961-01-01", "1991-12-31"]))
    per_person = measures.per_person(frame, DE, drawn, own)
    check("per person: 1950's figure before the population drawn begins comes back as published, 190.2003", abs(per_person[DE_DEBT_COLUMN].iloc[0] - 190.2003) < 1e-6, per_person[DE_DEBT_COLUMN].iloc[0])
    check("per person: a level over the same people as the total", abs(per_person[column].iloc[1] * 2 - per_person[DE_DEBT_COLUMN].iloc[1]) < 1e-9, per_person[column].iloc[1])
    check("per person: 1960's, shown on 1961-01-01, by the population drawn", abs(per_person[DE_DEBT_COLUMN].iloc[3] - 28998.43e6 / 50e6) < 1e-6, per_person[DE_DEBT_COLUMN].iloc[3])
    check("per person: 1990's by West Germany's, whatever the population drawn says, and held", abs(per_person[DE_DEBT_COLUMN].iloc[4] - 555.13e9 / people.loc["1990-12-31"]) < 1e-6 and per_person[DE_DEBT_COLUMN].iloc[5] == per_person[DE_DEBT_COLUMN].iloc[4], per_person[DE_DEBT_COLUMN].iloc[4])
    check("per person: all of Germany's from 1991-12-31 by the population drawn", abs(per_person[DE_DEBT_COLUMN].iloc[6] - 618.218e9 / 80e6) < 1e-6, per_person[DE_DEBT_COLUMN].iloc[6])


def check_west_gdp() -> None:
    """Batch 16: West Germany's GDP, read from the extracts of the Federal Statistical Office's tables (saved 2026-11-05), its bake, its joins and its population."""
    annual_rows, quarter_rows = csv_rows("destatis_81000_117_gdp.csv"), csv_rows("destatis_fs18_s27_gdp_q.csv")
    read = bake.parse_west_german_gdp(annual_rows)
    narrow, each, old_basis = read["narrow"], read["per_person"], read["old_basis"]
    check("West GDP: without the Saarland and West Berlin 1950 to 1959, 49.69 and 130.31, each year's 31 December",
          len(narrow) == 10 and narrow.iloc[0] == 49.69 and narrow.loc["1951-12-31"] == 61 and narrow.index[-1] == pd.Timestamp("1959-12-31") and narrow.iloc[-1] == 130.31, narrow.to_dict())
    check("West GDP: per person 1950 to 1959, 1059 and 2524", len(each) == 10 and each.iloc[0] == 1059 and each.iloc[-1] == 2524, each.to_dict())
    check("West GDP: the whole territory on the old basis 1960 to 1970, 154.77, 305.22 and 345.28",
          len(old_basis) == 11 and old_basis.iloc[0] == 154.77 and old_basis.loc["1969-12-31"] == 305.22 and old_basis.iloc[-1] == 345.28, old_basis.to_dict())
    quarters = bake.parse_west_german_quarterly_gdp(quarter_rows)
    check("West GDP: 88 quarters 1970 to 1991, 80.2 and 374.67, each dated by its last day",
          len(quarters) == 88 and quarters.index[0] == pd.Timestamp("1970-03-31") and quarters.iloc[0] == 80.2 and quarters.index[-1] == pd.Timestamp("1991-12-31") and quarters.iloc[-1] == 374.67, len(quarters))
    for name, values in (("NARROW", narrow), ("PER_PERSON", each), ("OLD_BASIS", old_basis), ("QUARTERS", quarters)):
        baked_values = pd.Series({pd.Timestamp(date): value for date, value in getattr(de_archive_data, f"EMBEDDED_DE_WEST_GDP_{name}")}, dtype=float)
        check(f"bake: EMBEDDED_DE_WEST_GDP_{name} holds the extract", baked_values.equals(values.rename(None).rename_axis(None)), len(baked_values))
    # The table's own revised years, which the quarters must add up to, and the two figures for 1960, 1970 and 1991.
    table = {(row[1], row[2], row[4], int(row[6])): float(row[7]) for row in annual_rows[1:]}
    revised = {year: value for (where, _span, kind, year), value in table.items() if where.endswith("(Ergebnisse der VGR-Revision 2005)") and kind == "in jeweiligen Preisen"}
    sums = quarters.groupby(quarters.index.year).sum()
    gaps = {year: abs(sums.loc[year] - value) for year, value in revised.items()}
    check("West GDP: the quarters add up to the table's revised year in all 22 years, within 0.03, and exactly at 1970, 1980, 1990, 1991",
          len(gaps) == 22 and max(gaps.values()) < 0.03 and all(gaps[year] < 1e-6 for year in (1970, 1980, 1990, 1991)), max(gaps.values()))
    whole, without = table[("Früheres Bundesgebiet", "1960-1970", "in jeweiligen Preisen", 1960)], table[("Früheres Bundesgebiet (ohne Berlin-West und Saarland)", "1950-1960", "in jeweiligen Preisen", 1960)]
    check("West GDP: 1960's two rows differ by the territory, 6.0 %", (whole, without) == (154.77, 146.04) and abs(whole / without - 1.0598) < 0.0001, whole / without)
    # Refusals: a table that moved a territory or a unit, lost a year or a quarter, or changed its columns.
    renamed = [[cell.replace("ohne Berlin-West und Saarland", "mit Berlin-West und Saarland") for cell in row] for row in annual_rows]
    check("West GDP: another territory named for 1950 to 1960 is refused", raises(bake.parse_west_german_gdp, renamed) is not None)
    respanned = [[cell.replace("1960-1970", "1960-1969") for cell in row] for row in annual_rows]
    check("West GDP: another span for the whole territory is refused", raises(bake.parse_west_german_gdp, respanned) is not None)
    check("West GDP: a year gone is refused", raises(bake.parse_west_german_gdp, [row for row in annual_rows if not (row[6] == "1955" and row[4] == "in jeweiligen Preisen")]) is not None)
    check("West GDP: another unit is refused", raises(bake.parse_west_german_gdp, [[("Mio. EUR" if cell == "Mrd. EUR" else cell) for cell in row] for row in annual_rows]) is not None)
    check("West GDP: columns moved are refused", raises(bake.parse_west_german_gdp, [annual_rows[0][::-1], *annual_rows[1:]]) is not None)
    check("West GDP: a quarter gone is refused", raises(bake.parse_west_german_quarterly_gdp, [row for row in quarter_rows if row[2] != "80.2"]) is not None)
    check("West GDP: another column of the quarters is refused", raises(bake.parse_west_german_quarterly_gdp, [[("Mrd. DM" if cell == "Mrd. EUR" else cell) for cell in row] for row in quarter_rows]) is not None)
    # The joins.
    west = de_data.west_german_gdp() / 1e9
    check("join: 105 figures, from 1950-12-31 to West Germany's own 1991-12-31", len(west) == 105 and west.index[0] == pd.Timestamp("1950-12-31") and west.index[-1] == pd.Timestamp("1991-12-31"), len(west))
    check("join: the step at 1960 kept (130.31, then 154.77); 1960 to 1965 as published", west.loc["1959-12-31"] == 130.31 and abs(west.loc["1960-12-31"] - 154.77) < 1e-9 and abs(west.loc["1965-12-31"] - 234.77) < 1e-9, west.loc["1959":"1961"].to_dict())
    check("join: 1969 raised 4.437 % to 318.76, so 1970's growth stays the old basis's, 13.12 %",
          abs(west.loc["1969-12-31"] / 305.22 - 360.60 / 345.28) < 1e-9 and abs(west.loc["1970-12-31"] / west.loc["1969-12-31"] - 345.28 / 305.22) < 1e-9, west.loc["1969-12-31"])
    check("join: the ramp is geometric over 1965 to 1969", abs(west.loc["1967-12-31"] / 252.76 - (360.60 / 345.28) ** 0.5) < 1e-9, west.loc["1967-12-31"])
    check("join: four-quarter sums from 1970-12-31 (360.60), 1991-09-30 1391.36, the quarters of 1970 not summed before it",
          abs(west.loc["1970-12-31"] - 360.60) < 1e-9 and abs(west.loc["1991-09-30"] - 1391.36) < 1e-9 and pd.Timestamp("1970-09-30") not in west.index, west.loc["1991-09-30"])
    # The population behind it, and what it gives per person.
    people = de_data.west_german_gdp_population()
    check("population: GDP's own 46,922 thousand in 1950, 51,628 in 1959 (GDP over its figure per person)",
          round(people.loc["1950-12-31"] / 1e3) == 46_922 and round(people.loc["1959-12-31"] / 1e3) == 51_628, people.loc["1959-12-31"])
    check("population: the population drawn from 1960-12-31 and from 1991-12-31", pd.isna(people.loc["1960-12-31"]) and pd.isna(people.loc["1991-12-31"]) and people.notna().sum() == 18, people.notna().sum())
    check("population: West Germany's at unification, from 1990-01-01, 64,074 thousand held from 1991-07-01; every West German figure of the span has its own",
          people.index[11] == pd.Timestamp("1990-01-01") and 62_000_000 < people.iloc[11] < 63_000_000 and np.isclose(people.loc["1991-09-30"], 64_074_000)
          and all(date in people.index for date in pd.date_range("1990-03-31", "1991-09-30", freq="QE")), people.iloc[11])
    dates = pd.to_datetime(["1959-12-31", "1960-01-01", "1960-12-31", "1989-12-31", "1990-12-31", "1991-09-30", "1991-12-31"])
    gdp = [130.31e9, 130.31e9, 154.77e9, 1000e9, 1306.68e9, 1391.36e9, 1590e9]
    frame = pd.DataFrame({"DATE": dates, GDP_COLUMN: [np.nan, gdp[1], gdp[2], gdp[3], gdp[4], gdp[5], gdp[6]]})
    drawn = pd.Series([50e6, 80e6], index=pd.to_datetime(["1960-01-01", "1991-12-31"]))
    per_person = measures.per_person(frame, DE, drawn, {GDP_COLUMN: people})[GDP_COLUMN]
    check("per person: 1959's figure showing on 1960-01-01 comes back as published, 2524", abs(per_person.iloc[1] - 2524) < 1e-6, per_person.iloc[1])
    check("per person: 1960's and 1989's by the population drawn", abs(per_person.iloc[2] - gdp[2] / measures.population_on(frame["DATE"], drawn).iloc[2]) < 1e-6
          and abs(per_person.iloc[3] - gdp[3] / measures.population_on(frame["DATE"], drawn).iloc[3]) < 1e-6, per_person.iloc[2])
    check("per person: 1990's and 1991's West German figures by West Germany's, whatever the population drawn says", abs(per_person.iloc[4] - gdp[4] / people.loc["1990-12-31"]) < 1e-6
          and np.isclose(per_person.iloc[5], 1391.36e9 / 64_074_000), per_person.iloc[4])
    check("per person: all of Germany's from 1991-12-31 by the population drawn", abs(per_person.iloc[6] - 1590e9 / 80e6) < 1e-6, per_person.iloc[6])
    # Eurostat down: West Germany's alone, said so; its figures unchanged.
    printed = io.StringIO()

    def down(*_args, **_kwargs):
        raise OSError("down")

    real_series, de_data.eurostat_series = de_data.eurostat_series, down
    try:
        with contextlib.redirect_stdout(printed):
            alone = de_data.fetch_de_gdp(PlotConfig(start=pd.Timestamp("1950-01-01"), end=pd.Timestamp("2026-10-07")))
            relative = de_data.fetch_de_gdp(PlotConfig(start=pd.Timestamp("1950-01-01"), end=pd.Timestamp("2026-10-07"), relative=True))
    finally:
        de_data.eurostat_series = real_series
    check("Eurostat down: West Germany's alone, to 1991-12-31, with a warning", alone is not None and alone[GDP_COLUMN].index[-1] == pd.Timestamp("1991-12-31")
          and "West Germany's alone" in printed.getvalue(), printed.getvalue())
    check("Eurostat down, under -r: none, with a warning, or all of Germany's debt would be divided by West Germany's GDP", relative is None and "not drawn" in printed.getvalue(), printed.getvalue())


def check_older_mortgages() -> None:
    """Batch 16: the Bundesbank's older mortgage rates, as saved 2026-11-04, their bake, and what was measured against the ECB's bands."""
    series = bake.DE_MORTGAGE_HISTORY_SERIES
    five_series, ten_series = series["EMBEDDED_DE_MORTGAGE_5Y_HISTORY"], series["EMBEDDED_DE_MORTGAGE_10Y_HISTORY"]
    five = bake.parse_german_mortgage_history(text("bbib1_HYP_F05J.csv"), five_series)
    ten = bake.parse_german_mortgage_history(text("bbib1_HYP_F10J.csv"), ten_series)
    check("BBIB1: 253 months, 1982-06 to 2003-06, dated by each first day; 5-year 10.07 to 4.06, 10-year 10.07 to 4.77",
          len(five) == len(ten) == 253 and five.index[0] == ten.index[0] == pd.Timestamp("1982-06-01") and five.index[-1] == pd.Timestamp("2003-06-01")
          and five.iloc[0] == 10.07 and five.iloc[-1] == 4.06 and ten.iloc[0] == 10.07 and ten.iloc[-1] == 4.77, (len(five), len(ten)))
    for name, values in (("EMBEDDED_DE_MORTGAGE_5Y_HISTORY", five), ("EMBEDDED_DE_MORTGAGE_10Y_HISTORY", ten)):
        rows = getattr(de_archive_data, name)
        baked_values = pd.Series({pd.Timestamp(date): value for date, value in rows}, dtype=float)
        check(f"bake: {name} holds the download, every month", baked_values.equals(values.rename(None).rename_axis(None)), len(baked_values))
    check("BBIB1: another series' answer is refused", raises(bake.parse_german_mortgage_history, text("bbib1_HYP_F05J.csv"), ten_series) is not None)
    check("BBIB1: a month gone is refused", raises(bake.parse_german_mortgage_history, text("bbib1_HYP_F05J.csv").replace("1990-02,", "1990-02-gone,"), five_series) is not None)
    check("BBIB1: a value after 2003-06 is refused", raises(bake.parse_german_mortgage_history, text("bbib1_HYP_F05J.csv").rstrip() + "\n2003-07,4.00,\n", five_series) is not None)
    # What the join rests on: the ECB's own flag on each month, and how its over-10 estimates were made.
    flags = pd.read_csv(io.StringIO(text("ecb_mir_house_1_5.csv")), usecols=["TIME_PERIOD", "OBS_STATUS"]).set_index("TIME_PERIOD")["OBS_STATUS"]
    check("ECB: every month of 2000-01 to 2002-12 flagged an estimate (E), 2003-01 on not",
          (flags.loc["2000-01":"2002-12"] == "E").all() and len(flags.loc["2000-01":"2002-12"]) == 36 and flags.loc["2003-01"] == "A", flags.loc["2002-11":"2003-02"].to_dict())
    over10 = de_data.parse_ecb_csv(text("ecb_mir_house_10plus.csv"), "MIR.M.DE.B.A2C.P.R.A.2250.EUR.N", "PCPA")
    over10 = over10.set_axis(over10.index.to_period("M").start_time)
    gaps = (over10.loc["2000-01-01":"2002-12-01"] - ten.loc["2000-01-01":"2002-12-01"]).round(2)
    check("ECB: the over-10 estimates of those 36 months are the Bundesbank's 10-year plus 0.02", len(gaps) == 36 and (gaps == 0.02).all(), gaps.value_counts().to_dict())
    check("join: the Bundesbank's before it, 2003-01; the bands the 5- and 10-year go under named; none for over 10",
          rates.DE_MORTGAGE_JOIN == pd.Timestamp("2003-01-01") and set(rates.DE_MORTGAGE_HISTORY) == {"1-5", "5-10"}, sorted(rates.DE_MORTGAGE_HISTORY))


def check_ecb() -> None:
    parse = de_data.parse_ecb_csv
    fixed = parse(text("ecb_mro_fixed.csv"), "FM.B.U2.EUR.4F.KR.MRR_FR.LEV", "PCPA")
    check("ECB MRO fixed rate: 3 on 1999-01-01, 2.65 from 2026-09-16",
          fixed.loc["1999-01-01"] == 3.0 and fixed.loc["2026-09-16"] == 2.65 and len(fixed) == 48)
    minbid = parse(text("ecb_mro_minbid.csv"), "FM.B.U2.EUR.4F.KR.MRR_MBR.LEV", "PCPA")
    check("ECB minimum bid rate: 4.25 from 2000-06-28; its row without a value (2008-10-15) left out",
          minbid.loc["2000-06-28"] == 4.25 and minbid.index[-1] == pd.Timestamp("2008-10-08"), minbid.index[-1])
    annual = parse(text("ecb_gfs_a_debt.csv"), "GFS." + de_data.ECB_ANNUAL_DEBT[1], "XDC")
    check("ECB annual debt: 1991, €618,218m, dated 31 December", annual.loc["1991-12-31"] == 618_218e6 and annual.index[0].year == 1991)
    mortgage = parse(text("ecb_mir_house_5_10.csv"), "MIR.M.DE.B.A2C.O.R.A.2250.EUR.N", "PCPA")
    check("ECB housing loans 5-10 years: 3.81 in 2026-08 (dated its last day), from 2000-01",
          mortgage.loc["2026-08-31"] == 3.81 and mortgage.index[0] == pd.Timestamp("2000-01-31"))
    check("ECB: another series' answer is refused", raises(parse, text("ecb_deposit.csv"), "FM.B.U2.EUR.4F.KR.MRR_FR.LEV", "PCPA") is not None)
    check("ECB: a changed unit is refused", raises(parse, text("ecb_mro_fixed.csv"), "FM.B.U2.EUR.4F.KR.MRR_FR.LEV", "PC") is not None)
    check("ECB: its error page (the floating-rate loans' 500) is refused",
          raises(parse, text("ecb_mir_house_float.csv"), "MIR.M.DE.B.A2C.F.R.A.2250.EUR.N", "PCPA") is not None)


def jsonstat(name: str) -> dict:
    return json.loads(text(f"{name}.json"))


def check_eurostat() -> None:
    parse = de_data.parse_jsonstat
    debt = parse(jsonstat("est_ggdebt_q"), "MIO_EUR", sector="S13")
    check("Eurostat debt S13: 2026 Q1 €2,902,035.3m, from 2000 Q1",
          debt.loc["2026-03-31"] == 2_902_035.3 and debt.index[0] == pd.Timestamp("2000-03-31"), debt.index[0])
    check("Eurostat: a dimension with several categories must be chosen", raises(parse, jsonstat("est_ggdebt_q"), "MIO_EUR") is not None)
    check("Eurostat: a changed unit is refused", raises(parse, jsonstat("est_ggdebt_q"), "THS_EUR", sector="S13") is not None)
    check("Eurostat: an unknown sector is refused", raises(parse, jsonstat("est_ggdebt_q"), "MIO_EUR", sector="S99") is not None)
    annual = de_data.parse_ecb_csv(text("ecb_gfs_a_debt.csv"), "GFS." + de_data.ECB_ANNUAL_DEBT[1], "XDC")
    years = [year for year in range(2000, 2026)]
    gaps = [abs(annual.loc[f"{year}-12-31"] / 1e6 / debt.loc[f"{year}-12-31"] - 1) for year in years]
    check("join: the ECB's year-end debt is Eurostat's fourth quarter, 2000-2025 (within 1e-6)", max(gaps) < 1e-6, max(gaps))
    levels = sum(parse(jsonstat("est_ggdebt_q"), "MIO_EUR", sector=sector) for sector in ("S1311", "S1312", "S1313", "S1314"))
    ratio = (levels / debt).dropna()
    check("levels: the subsectors add up to 0.6-2 % more than the consolidated total", ratio.between(1.006, 1.02).all(), (ratio.min(), ratio.max()))
    interest = parse(jsonstat("est_ggnfa_q"), "MIO_EUR", sector="S13")
    yearly = parse(jsonstat("est_edpt1_a"), "MIO_EUR", sector="S13", na_item="D41PAY")
    sums = de_data.ttm_sum(interest)
    # 2025 differs: the annual table (April) predates the quarters' revision (July).
    check("join: annual interest (edpt1) is the four-quarter sum, 2002-2024",
          all(sums.loc[f"{year}-12-31"] == yearly.loc[f"{year}-12-31"] for year in range(2002, 2025)))
    check("Eurostat interest: annual from 1995, quarterly from 2002", yearly.index[0].year == 1995 and interest.index[0] == pd.Timestamp("2002-03-31"))
    gdp = parse(jsonstat("est_gdp_q"), "CP_MEUR")
    check("Eurostat GDP: from 1991 Q1, €358,976.1m; 2026 Q2", gdp.index[0] == pd.Timestamp("1991-03-31") and gdp.loc["2026-06-30"] == 1_151_030.0)
    people = parse(jsonstat("est_pop_q"), "THS_PER")
    check("Eurostat population: 83,337 thousand in 2026 Q2", people.loc["2026-06-30"] == 83_337)
    january = parse(jsonstat("est_pjan_a"), "NR")
    check("Eurostat population on 1 January: from 1960; West Germany to 1990, then unified (+17.1 million)",
          january.index[0].year == 1960 and january.loc["1990-12-31"] == 62_679_035 and january.loc["1991-12-31"] == 79_753_227)


def check_fetchers() -> None:
    """The program's own fetchers, served the saved responses, with no bake (batch 19.2): each series asked for whole."""
    real_get, de_data.de_get = de_data.de_get, saved_get
    real_folder, no_bake = baked.DATA_FOLDER, tempfile.TemporaryDirectory(prefix="ratesplot_no_bake_")
    baked.DATA_FOLDER = Path(no_bake.name)
    baked.forget_read_files()
    try:
        config = PlotConfig(start=pd.Timestamp("1950-01-01"), end=pd.Timestamp("2026-10-07"), yield_terms=de_data.DE_YIELD_TERMS)
        yields = de_data.fetch_de_yields(config)
        through = yields.attrs[de_data.YIELD_HISTORY_ATTR]
        check("yields: the seven terms", list(yields.columns) == list(de_data.DE_YIELD_SERIES), list(yields.columns))
        check("yields: the 10-year from the baked 1956-05 (6.4), monthly to 1997-07, daily from 1997-08-07",
              yields["10-Year"].first_valid_index() == pd.Timestamp("1956-05-01") and yields.loc["1956-05-01", "10-Year"] == 6.4
              and through["10-Year"] == pd.Timestamp("1997-07-31") and yields.loc["1997-08-07", "10-Year"] == daily_value("R10XX", "1997-08-07"),
              through)
        check("yields: the baked months end where the fitted 10-year begins (1972-08, then 8.08 at 1972-09-30)",
              yields["10-Year"].loc["1972-08-01":"1972-09-30"].dropna().to_dict() == {pd.Timestamp("1972-08-01"): 7.9, pd.Timestamp("1972-09-30"): 8.08})
        check("yields: the 30-year monthly 2000-01 to 2000-07, then daily", through["30-Year"] == pd.Timestamp("2000-07-31"), through["30-Year"])
        debt = de_data.fetch_de_debt(config)[de_data.DE_DEBT_COLUMN]
        check("debt: West Germany's from 1950-03-31, year-end 1991-1999 (ECB), then quarterly (Eurostat) from 2000 Q1",
              debt.index[0] == pd.Timestamp("1950-03-31") and debt.loc["1991-12-31"] == 618_218e6 and debt.loc["1999-12-31"] == 1_253_598e6
              and pd.Timestamp("2000-03-31") in debt.index and debt.loc["2026-03-31"] == 2_902_035.3e6)
        interest = de_data.fetch_de_interest(config)[de_data.DE_INTEREST_COLUMN]
        check("interest: annual 1995-2001, then four-quarter sums from 2002 Q4",
              interest.index[0] == pd.Timestamp("1995-12-31") and interest.loc["2001-12-31"] > 0
              and interest.index[interest.index > pd.Timestamp("2001-12-31")][0] == pd.Timestamp("2002-12-31"))
        gdp = de_data.fetch_de_gdp(config)[GDP_COLUMN]
        unified = de_data.ttm_sum(de_data.parse_jsonstat(jsonstat("est_gdp_q"), "CP_MEUR")) * 1e6
        check("GDP: West Germany's from 1950-12-31 to 1991-09-30, then Eurostat's four-quarter sums from 1991 Q4",
              gdp.index[0] == pd.Timestamp("1950-12-31") and gdp.index[gdp.index < unified.index[0]][-1] == pd.Timestamp("1991-09-30")
              and unified.index[0] == pd.Timestamp("1991-12-31") and np.isclose(gdp.loc["1991-12-31"], unified.iloc[0])
              and np.isclose(gdp.iloc[-1], unified.iloc[-1]), unified.iloc[0])
        people = de_data.fetch_de_population()
        check("population: annual averages 1950 to 1959, then 1 January from 1960 (1991's the first unified), then mid-quarters (79,777 thousand on 1991-02-15)",
              people.index[0] == pd.Timestamp("1950-07-01") and people.loc["1959-07-01"] == 54_876_000 and people.loc["1960-01-01"] == 55_257_088
              and people.loc["1991-01-01"] == 79_753_227 and people.loc["1991-02-15"] == 79_777_000 and pd.Timestamp("1991-04-01") not in people.index)
        levels = de_data.fetch_de_components(PlotConfig(start=config.start, end=config.end, components="fnpm"))
        n = levels[component_column("debt", "n")]
        check("levels: f n p m debt and interest; n is the Länder and local together",
              len(levels.columns) == 8 and (n == levels[component_column("debt", "p")] + levels[component_column("debt", "m")]).all())
        policy = rates.de_policy_target().values
        check("policy: the fixed rate (3 in 1999), the minimum bid 2000-06-28 to 2008-10-14, fixed again from 2008-10-15",
              policy.loc["1999-01-04"] == 3.0 and policy.loc["2000-06-28"] == 4.25 and policy.loc["2000-10-06"] == 4.75
              and policy.loc["2008-10-14"] == 4.25 and policy.loc["2008-10-15"] == 3.75,
              policy.loc["2008-10-13":"2008-10-16"].to_dict())
        joined = rates.de_policy_target()
        check("policy: the Bundesbank's discount rate before 1999 (batch 9.6): 5.0 from 1948-07-01, 2.5 to the ECB's first day",
              joined.values.index[0] == pd.Timestamp("1948-07-01") and joined.values.iloc[0] == 5.0
              and joined.values.loc[:"1998-12-31"].iloc[-1] == 2.5 and joined.values.loc["1999-01-01"] == 3.0
              and joined.label == "Bundesbank Discount Rate, ECB Main Refinancing Rate from 1999-01", joined.label)
        check("policy: each day carried to the next change, the last to today (2.65 since 2026-09-16)",
              policy.loc["2026-09-30"] == 2.65 and policy.index[-1] >= pd.Timestamp("2026-10-07") and policy.loc["2025-01-01"] == 3.15)
        mortgage = rates.mortgage_rate("5-10")
        check("mortgages: the 5-10 year band dated by each month's first day (3.81 for 2026-08), in the 10-year's colour",
              mortgage.values.loc["2026-08-01"] == 3.81 and mortgage.color_of == "10-Year", mortgage.label)
        check("mortgages: the 5-10 year band from 1982-06, the Bundesbank's 10-year to 2002-12 (5.52), then the ECB's (5.39 for 2003-01)",
              mortgage.values.index[0] == pd.Timestamp("1982-06-01") and mortgage.values.loc["2002-12-01"] == 5.52 and mortgage.values.loc["2003-01-01"] == 5.39
              and mortgage.values.index.is_monotonic_increasing and not mortgage.values.index.has_duplicates, mortgage.values.loc["2002-11-01":"2003-02-01"].to_dict())
        shorter = rates.mortgage_rate("1-5")
        check("mortgages: the 1-5 year band from 1982-06, the Bundesbank's 5-year to 2002-12 (4.96), then the ECB's (4.94 for 2003-01), each month once",
              shorter.values.index[0] == pd.Timestamp("1982-06-01") and shorter.values.loc["2002-12-01"] == 4.96 and shorter.values.loc["2003-01-01"] == 4.94
              and not shorter.values.index.has_duplicates, shorter.values.loc["2002-11-01":"2003-02-01"].to_dict())
        longest = rates.mortgage_rate("over10")
        check("mortgages: the over-10 band still the ECB's alone, from 2000-01 (5.54 for 2002-12)",
              longest.values.index[0] == pd.Timestamp("2000-01-01") and longest.values.loc["2002-12-01"] == 5.54, longest.values.iloc[:2].to_dict())
    finally:
        de_data.de_get = real_get
        baked.DATA_FOLDER = real_folder
        baked.forget_read_files()
        no_bake.cleanup()


def check_bot_check() -> None:
    """The Bundesbank answering with its bot check (batch 19.2): asked once, named once; the yields from the bake, else the built-in history."""
    asked: list[str] = []

    def bot_checked_get(url: str, params: dict | None = None, **_kwargs) -> requests.Response:
        if "api.statistiken.bundesbank.de" in url:
            asked.append(url)
            raise BotCheck("api.statistiken.bundesbank.de")
        return saved_get(url, params)

    def draw() -> tuple[pd.DataFrame, list[str]]:
        asked.clear()
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            yields = de_data.fetch_de_yields(PlotConfig(start=pd.Timestamp("1950-01-01"), yield_terms=de_data.DE_YIELD_TERMS))
        return yields, [line.strip() for line in printed.getvalue().splitlines() if "Warning" in line]

    flow = de_data.BUNDESBANK_TERM_STRUCTURE_FLOW
    codes = {(column, frequency): f"{flow}.{de_data.term_structure_key(column, frequency)}"
             for column in de_data.DE_YIELD_SERIES for frequency in de_data.TERM_STRUCTURE_FREQUENCIES}
    real_get, de_data.de_get = de_data.de_get, bot_checked_get
    real_folder, no_bake = baked.DATA_FOLDER, tempfile.TemporaryDirectory(prefix="ratesplot_no_bake_")
    try:
        yields, warnings = draw()
        bakes = {pair: baked.read_series(de_data.BUNDESBANK_BAKED_SOURCE, code) for pair, code in codes.items()}
        end = max(series.index[-1] for series in bakes.values())
        check("bot check, with the bake: one request, one warning naming it and the bake's last date",
              len(asked) == 1 and len(warnings) == 1 and "sent a bot check instead of data" in warnings[0]
              and f"The German yields drawn from their baked history, to {end:%Y-%m-%d}." in warnings[0], (asked, warnings))
        # On the bake's own dates (the frame has every term's dates, a gap of a day or two filled).
        check("bot check, with the bake: the seven terms, each daily part its bake's",
              list(yields.columns) == list(de_data.DE_YIELD_SERIES)
              and all((yields[column].reindex(bakes[(column, "D")].index).to_numpy() == bakes[(column, "D")].to_numpy()).all()
                      for column in de_data.DE_YIELD_SERIES), list(yields.columns))
        baked.DATA_FOLDER = Path(no_bake.name)
        baked.forget_read_files()
        yields, warnings = draw()
        check("bot check, without the bake: one request, the built-in 10-year alone, as before 19.2",
              len(asked) == 1 and list(yields.columns) == ["10-Year"] and len(warnings) == 1
              and warnings[0].endswith("No German yield downloaded: only the built-in history is drawn."), (asked, warnings))
    finally:
        de_data.de_get = real_get
        baked.DATA_FOLDER = real_folder
        baked.forget_read_files()
        no_bake.cleanup()


def daily_value(code: str, day: str) -> float:
    return de_data.parse_bundesbank_csv(text(f"bbk_ts_d_{code}.csv")).loc[day]


def check_cnbc() -> None:
    quotes = {quote["symbol"]: quote for quote in json.loads(text("cnbc_de_quotes.json"))["FormattedQuoteResult"]["FormattedQuote"]}
    asked = latest._quote_symbols("de", list(de_data.DE_YIELD_SERIES))
    check("CNBC: a German symbol for each of the seven terms", set(asked) == set(de_data.DE_YIELD_SERIES), asked)
    check("CNBC: every German symbol asked for is in the feed", set(asked.values()) <= set(quotes), sorted(quotes))
    check("CNBC: DE3M-DE (unknown to the feed) is not asked for", "DE3M-DE" not in asked.values() and quotes["DE3M-DE"]["code"] == 1)
    readable = []
    for symbol in asked.values():
        quote = quotes[symbol]
        value = latest._percent(quote["last"])
        when = pd.Timestamp(quote["last_time"]).tz_convert("UTC")
        latest._day_change(quote)
        readable.append(latest._PLAUSIBLE_YIELD[0] <= value <= latest._PLAUSIBLE_YIELD[1] and when.year == 2026)
    check("CNBC: each German quote's yield, time and change are read", all(readable))
    check("CNBC: the feed is the one latest reads", "quote.cnbc.com" in CNBC_QUOTE_URL)


def main() -> int:
    for group in (check_bundesbank, check_discount_rate, check_west_prices, check_west_population, check_west_gdp, check_german_debt, check_older_mortgages, check_ecb, check_eurostat, check_fetchers, check_bot_check, check_cnbc):
        group()
    passed = sum(RESULTS)
    print(f"[de parsers] {passed} of {len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
