#!/usr/bin/env python3
"""Check the UK's parsers against responses saved from the real sources (batch 3); offline, in seconds.

The cloud copy cannot reach the Bank of England, the ONS or CNBC, so the
parsers were written against responses saved on Terry's laptop on
2026-10-06 (``tools/uk_fixtures``). This keeps them honest when the code
changes: each check reads a saved response through the program's own
parser and compares a value read off the response by eye.

* the Bank of England database's CSV (daily and monthly), and the two
  answers it must refuse: its described layout and a redirect to its error
  page; with the redirect, a baked series drawn from its bake alone, with a
  warning (batch 19.2);
* each kind of ONS series: months, quarters, the units £m, £bn (HF6W),
  none (MDYT) and thousands, a changed unit refused, and a four-quarter sum against the
  ONS's own annual figure;
* the ONS fetchers themselves (debt, GDP, interest, population, local debt):
  ``uk_get`` is replaced by a reader of the saved responses, chosen by the URL
  the program asks for, so a request that differs from the one measured fails
  here. The saved responses are cut down (each list's first 4 and last 10
  entries), so the fetchers run without the live sources' bake (batch 19.2):
  each series as the saved response gives it, none joined to a recent part
  of it. With the bake: the ONS refused, a series is its bake alone, with a
  warning; an answer without values in the recent part, the same;
* CNBC's UK quotes: every symbol the chart asks for is there and readable,
  and the 3-month symbol (a repo rate, not a yield) is not asked for;
* the bake's reading of the millennium workbook's period cells.

The live check of the same sources is ``tools/check_sources.py``.

Usage (from the project root)::

    python tools/check_uk_parsers.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import bake, baked, latest, uk_data  # noqa: E402
from ratesplot.config import (  # noqa: E402
    CNBC_QUOTE_URL,
    DEBT_AGGREGATES,
    GDP_COLUMN,
    ONS_TIMESERIES_URL,
    RECENT_PART_REVISED,
    UK_DEBT_COLUMN,
    UK_INTEREST_COLUMN,
    UK_NATIONAL_DEBT_COLUMN,
    UK_NET_DEBT_COLUMN,
    PlotConfig,
    component_column,
)

FIXTURES = ROOT / "tools" / "uk_fixtures"
RESULTS: list[bool] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    shown = f"  [{detail}]" if not condition or detail else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}")


def raises(call, *args) -> str | None:
    """The exception's type and message if ``call(*args)`` raises, else None."""
    try:
        call(*args)
    except Exception as exc:  # what is raised is the point
        return f"{type(exc).__name__}: {exc}"
    return None


def text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def check_iadb() -> None:
    daily = uk_data.parse_iadb_csv(text("boe_iadb_daily.csv"))
    check("IADB daily: the 10-year par yield on 2026-09-30", daily.loc["2026-09-30", "IUDMNPY"] == 5.3714)
    check("IADB daily: Bank Rate on 2026-10-05, the yields blank that day",
          daily.loc["2026-10-05", "IUDBEDR"] == 3.75 and daily.loc["2026-10-05", "IUDMNPY"] != daily.loc["2026-10-05", "IUDMNPY"])
    check("IADB daily: every series the chart reads is a column",
          set(uk_data.UK_YIELD_SERIES.values()) | {"IUDBEDR"} <= set(daily.columns), list(daily.columns))
    monthly = uk_data.parse_iadb_csv(text("boe_iadb_monthly.csv"))
    check("IADB monthly: dated by the month's last day; the 2-year fixed for August 2026",
          monthly.loc["2026-08-31", "IUMBV34"] == 4.92 and monthly.index[0] == pd.Timestamp("2025-01-31"))
    check("IADB: the described layout (CSVF=CT) is refused", raises(uk_data.parse_iadb_csv, text("boe_iadb_described.csv")) is not None)
    check("IADB: its error page is refused", raises(uk_data.parse_iadb_csv, text("boe_iadb_error_905.txt")) is not None)

    def redirected(url, params=None, **_kwargs):
        response = requests.Response()
        response.status_code, response.url = 200, "https://www.bankofengland.co.uk/boeapps/database/ErrorPage.asp?ei=905"
        response.history = [requests.Response()]
        response._content = b"<html>error</html>"
        return response

    real_get, uk_data.uk_get = uk_data.uk_get, redirected
    printed = io.StringIO()
    try:
        message = raises(uk_data.iadb_download, "IUDMNPY")
        with contextlib.redirect_stdout(printed):
            series = uk_data.iadb_series("IUDMNPY")
    finally:
        uk_data.uk_get = real_get
    check("IADB: a redirect raises, naming the page", message is not None and "ErrorPage" in message, message)
    bake_ = baked.read_series(uk_data.BOE_BAKED_SOURCE, "IUDMNPY")
    said = printed.getvalue()
    check("IADB (19.2): the recent part redirected, the 10-year is its bake alone, with a warning naming it and its last date",
          bake_ is not None and series.equals(bake_) and "Bank of England IUDMNPY: its recent values unavailable" in said
          and f"drawn from its baked history, to {bake_.index[-1]:%Y-%m-%d}." in said, said.strip())


def ons(cdid: str) -> dict:
    return json.loads(text(f"ons_{cdid.lower()}.json"))


def check_ons() -> None:
    bkpx = uk_data.parse_ons_series(ons("BKPX"), "BKPX", "months")
    check("ONS BKPX months: August 2026, £m, dated its last day", bkpx.loc["2026-08-31"] == 3_195_774)
    quarters = uk_data.parse_ons_series(ons("BKPX"), "BKPX", "quarters")
    check("ONS BKPX quarters: 1975 Q1 dated 1975-03-31", quarters.index[0] == pd.Timestamp("1975-03-31") and quarters.iloc[0] == 53_670)
    mdyt = uk_data.parse_ons_series(ons("MDYT"), "MDYT", "quarters")
    check("ONS MDYT (no unit in its description): 2026 Q2", mdyt.loc["2026-06-30"] == 138_883)
    check("ONS MDYT has no months", uk_data.parse_ons_series(ons("MDYT"), "MDYT", "months").empty)
    hf6w = uk_data.parse_ons_series(ons("HF6W"), "HF6W", "months")
    check("ONS HF6W (£bn): August 2026", hf6w.loc["2026-08-31"] == 2_985.5)
    ebaq = uk_data.parse_ons_series(ons("EBAQ"), "EBAQ", "quarters")
    check("ONS EBAQ (thousands): 2026 Q2", ebaq.loc["2026-06-30"] == 69_628)
    changed = ons("YBHA")
    changed["description"]["unit"] = "bn"
    check("ONS: a changed unit is refused", raises(uk_data.parse_ons_series, changed, "YBHA", "quarters") is not None)
    nmyx = uk_data.parse_ons_series(ons("NMYX"), "NMYX", "quarters")
    annual = {row["date"]: float(row["value"]) for row in ons("NMYX")["years"] if row["value"]}
    check("ONS NMYX: four quarters of 2025 sum to the ONS's 2025 figure",
          uk_data.ttm_sum(nmyx).loc["2025-12-31"] == annual["2025"], (uk_data.ttm_sum(nmyx).loc["2025-12-31"], annual["2025"]))
    # The saved response keeps 1946's four quarters, then 2024 on: one sum for 1946, none across the gap.
    sums = uk_data.ttm_sum(nmyx)
    check("ONS: four consecutive quarters make a sum; a gap of quarters leaves none across it",
          sums.index[0] == pd.Timestamp("1946-12-31") and sums.loc["1947":"2024-09-30"].empty, list(sums.index[:3]))


# The saved ONS responses, by the URL the program asks for each (``uk_data.ONS_SERIES``).
SAVED_ONS = {ONS_TIMESERIES_URL.format(path=uk_data.ONS_SERIES[cdid][0]): f"ons_{cdid.lower()}.json"
             for cdid in ("BKPX", "HF6W", "MDYT", "EBAQ", "YBHA", "NMYX")}


def answer(url: str, body: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code, response.url, response.encoding = 200, url, "utf-8"
    response._content = body
    return response


def saved_get(url: str, params: dict | None = None, **_kwargs) -> requests.Response:
    """Answer a request from the saved ONS responses, as ``http.uk_get`` would; a request never measured raises."""
    if params or url not in SAVED_ONS:
        raise requests.ConnectionError(f"no saved response for {url} {params}")
    return answer(url, (FIXTURES / SAVED_ONS[url]).read_bytes())


def check_fetchers() -> None:
    """The program's ONS fetchers, served the saved responses, with no bake (batch 19.2): each series as the saved response gives it."""
    real_get, uk_data.uk_get = uk_data.uk_get, saved_get
    real_folder, no_bake = baked.DATA_FOLDER, tempfile.TemporaryDirectory(prefix="ratesplot_no_bake_")
    baked.DATA_FOLDER = Path(no_bake.name)
    baked.forget_read_files()
    printed = io.StringIO()
    try:
        # Both aggregate debts: net debt is asked for only when chosen (batch 10.4).
        config = PlotConfig(start=pd.Timestamp("1950-01-01"), end=pd.Timestamp("2026-10-07"), debt_aggregates=DEBT_AGGREGATES)
        with contextlib.redirect_stdout(printed):
            debt = uk_data.fetch_uk_debt(config)
            gdp = uk_data.fetch_uk_gdp(config)
            interest = uk_data.fetch_uk_interest(config)
            people = uk_data.fetch_uk_population()
            local = uk_data.fetch_uk_components(PlotConfig(start=config.start, end=config.end, components="m", include_interest=False))
    finally:
        uk_data.uk_get = real_get
        baked.DATA_FOLDER = real_folder
        baked.forget_read_files()
        no_bake.cleanup()
    gross, net, national = (debt[column].dropna() for column in (UK_DEBT_COLUMN, UK_NET_DEBT_COLUMN, UK_NATIONAL_DEBT_COLUMN))
    check("fetchers: gross debt by month (BKPX, August 2026 £3,195,774m), the national debt alone before 1975-03",
          gross.loc["2026-08-31"] == 3_195_774e6 and gross.index[0] == pd.Timestamp("1975-03-31")
          and national.index[-1] < pd.Timestamp("1975-03-31"), (gross.index[0], national.index[-1]))
    check("fetchers: net debt by month (HF6W, August 2026 £2,985.5bn)", net.loc["2026-08-31"] == 2_985.5e9, net.tail(1).to_dict())
    quarters = uk_data.parse_ons_series(ons("YBHA"), "YBHA", "quarters")
    check("fetchers: GDP ends in the saved YBHA's last four quarters summed, in pounds",
          gdp[GDP_COLUMN].dropna().iloc[-1] == uk_data.ttm_sum(quarters).iloc[-1] * 1e6
          and gdp[GDP_COLUMN].last_valid_index() == pd.Timestamp("2026-06-30"))
    annual = {row["date"]: float(row["value"]) for row in ons("NMYX")["years"] if row["value"]}
    check("fetchers: interest's 2025 sum is the ONS's 2025 figure, in pounds (NMYX)",
          interest[UK_INTEREST_COLUMN].loc["2025-12-31"] == annual["2025"] * 1e6)
    check("fetchers: the population, 2026 Q2 dated by its middle (69,628 thousand on 2026-05-16), the baked years before 1955",
          people.loc["2026-05-16"] == 69_628_000 and people.index[0] < pd.Timestamp("1955-01-01"), people.tail(1).to_dict())
    check("fetchers: local government debt by quarter (MDYT, 2026 Q2 £138,883m)",
          local[component_column("debt", "m")].loc["2026-06-30"] == 138_883e6, list(local.columns))
    said = printed.getvalue()
    check("fetchers: no warning (every request one measured, no bake read)", "Warning" not in said, said.strip())


def check_ons_bake() -> None:
    """With the bake (batch 19.2): the ONS refused, or answering without values in the recent part, a series is its bake alone, with a warning."""

    def refused(url: str, params: dict | None = None, **_kwargs) -> requests.Response:
        raise requests.ConnectionError("refused by check_uk_parsers")

    cut = ons("MDYT")
    cut["quarters"] = cut["quarters"][:4]  # 1966 alone: nothing in the last 24 months

    def answering_cut(url: str, params: dict | None = None, **_kwargs) -> requests.Response:
        return answer(url, json.dumps(cut).encode())

    for cdid, get, cause in (("BKPX", refused, "refused by check_uk_parsers"), ("MDYT", answering_cut, None)):
        bake_ = baked.read_series(uk_data.ONS_BAKED_SOURCE, cdid)
        last = bake_.index[-1]
        cause = cause or f"the ONS gave no values of {cdid} from {last - RECENT_PART_REVISED:%Y-%m-%d}"
        real_get, uk_data.uk_get = uk_data.uk_get, get
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                series = uk_data.ons_series(cdid)
        finally:
            uk_data.uk_get = real_get
        said = printed.getvalue().strip()
        check(f"ONS (19.2): {cdid} {'refused' if get is refused else 'answered without the recent part'}: its bake alone, in pounds, "
              "with a warning naming it, why, and its last date",
              series.equals(bake_ * 1e6) and said == f"Warning: ONS {cdid}: its recent values unavailable ({cause}); drawn from its baked "
                                                      f"history, to {last:%Y-%m-%d}.", said)


def check_cnbc() -> None:
    quotes = {quote["symbol"]: quote for quote in json.loads(text("cnbc_gb_quotes.json"))["FormattedQuoteResult"]["FormattedQuote"]}
    asked = latest._quote_symbols("uk", list(uk_data.UK_YIELD_SERIES))
    check("CNBC: every UK symbol asked for is in the feed", set(asked.values()) <= set(quotes), sorted(quotes))
    check("CNBC: the 3-month repo rate is not asked for", "GB3M-GB" not in asked.values())
    readable = []
    for symbol in asked.values():
        quote = quotes[symbol]
        value = latest._percent(quote["last"])
        when = pd.Timestamp(quote["last_time"]).tz_convert("UTC")
        latest._day_change(quote)
        readable.append(latest._PLAUSIBLE_YIELD[0] <= value <= latest._PLAUSIBLE_YIELD[1] and when.year == 2026)
    check("CNBC: each UK quote's yield, time (offsets differ) and change are read", all(readable))
    check("CNBC: the feed is the one latest reads", "quote.cnbc.com" in CNBC_QUOTE_URL)


def check_bake_periods() -> None:
    date = bake._millennium_date
    cases = [
        ("fy", ("1690/91", "End September"), None, "1691-09-30"),
        ("fy", ("1974/75", "31st March"), None, "1975-03-31"),
        ("fy", ("1750/51", "5th January"), None, "1751-01-05"),
        ("fy", ("1799/00", "5th January"), None, "1800-01-05"),
        ("year", (1700.0, None), None, "1700-12-31"),
        ("midyear", ("1922", None), None, "1922-06-30"),
        ("month", (1753, "Aug"), None, "1753-08-01"),
        ("month", (None, "Jan"), pd.Timestamp("1935-12-01"), "1936-01-01"),
        ("month", (None, "Feb"), pd.Timestamp("1936-01-01"), "1936-02-01"),
        ("day", (dt.datetime(1833, 1, 1), None), None, "1833-01-01"),
        ("day", ("02/11/2017", None), None, "2017-11-02"),
    ]
    found = [(cells, date(kind, cells, previous)) for kind, cells, previous, _expected in cases]
    check("bake: the millennium workbook's period cells", all(when == pd.Timestamp(expected) for (_c, when), (*_x, expected) in zip(found, cases)),
          [(cells, str(when.date())) for cells, when in found])
    check("bake: a row with no period has none", date("month", (None, None), pd.Timestamp("2017-03-01")) is None)
    check("bake: a financial year whose years do not follow is refused", raises(date, "fy", ("1690/92", "End September"), None) is not None)
    check("bake: a month with no year before it is refused", raises(date, "month", (None, "Aug"), None) is not None)


def main() -> int:
    for group in (check_iadb, check_ons, check_fetchers, check_ons_bake, check_cnbc, check_bake_periods):
        group()
    passed = sum(RESULTS)
    print(f"[uk parsers] {passed} of {len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
