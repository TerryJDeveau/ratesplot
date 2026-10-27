"""Application constants, per-country chart metadata, HTTP session, and PlotConfig.

Everything tunable lives here so the data and plotting modules contain logic
only. Numeric literals that affect chart appearance (padding, font sizes,
default limits) are deliberately centralised rather than scattered through the
plot functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Canvas and date defaults
# ---------------------------------------------------------------------------

# Without --start the chart begins where the last of the chosen curves begins
# (plotting.resolve_start). It is found by preparing the data from this date;
# it is also the first date the page's calendar and its "Earlier" button
# reach. Terry, 2026-10-06 (batch 3): as early as pandas allows, with a
# small margin. pandas' timestamps (nanoseconds) begin 1677-09-21; 1680-01-01
# leaves two years, and precedes every series: the UK's national debt (1691)
# and GDP (1700), Canada's from Confederation (1867). Spans longer than
# pandas' 292-year Timedelta are added as date offsets
# (frontend.move_dates_updates). Before batch 3 it was 1867-01-01; no Canadian
# or U.S. curve begins before that, so their automatic start is as it was.
EARLIEST_DATA_START = pd.Timestamp("1680-01-01")
# Without --start the chart begins no earlier than this date (Terry,
# 2026-10-06: he kept setting the start by hand, "so maybe just making the
# default 2000 is just as good as anything else"). The start is the later of
# this date and the first date on which every chosen curve has data, so a
# curve that begins after it is still not cut at the left. A chart ending
# before this date takes the automatic start alone. Any date before
# EARLIEST_DATA_START (e.g. "1500-01-01") restores the fully automatic start
# of 2026-09-29, as Terry asked: a setting, not a hard-coded year.
DEFAULT_START_FLOOR = pd.Timestamp("2000-01-01")
# The shortest window: --end at least this many days after --start.
MIN_WINDOW_DAYS = 7
DEFAULT_CANVAS_PX = (2048, 1536)
CANVAS_DPI = 100
MIN_CANVAS_PX = 800


def _today() -> pd.Timestamp:
    """Return today's date as a midnight Timestamp (the default chart end)."""
    return pd.Timestamp.today().normalize()


# ---------------------------------------------------------------------------
# Axis behaviour
# ---------------------------------------------------------------------------

# Fallback limits used when an axis has no data or the data span is degenerate,
# and for the other end when only one end of the right axis is pinned. The
# right axis has one per measure: dollars, percent of GDP (-r), dollars per
# person (-p).
DEFAULT_YIELD_YLIM = (-0.3, 7.5)
DEFAULT_MACRO_YLIM = (10_000_000_000, 100_000_000_000_000)
DEFAULT_RELATIVE_YLIM = (0.1, 1_000.0)
DEFAULT_PER_CAPITA_YLIM = (1.0, 1_000_000.0)

# Yield axis (linear): padding is a fraction of the *displayed* span, clamped
# to an absolute minimum so a flat series still gets visible breathing room.
YIELD_BOTTOM_PAD_FRACTION = 0.015
YIELD_TOP_PAD_FRACTION = 0.04
YIELD_MIN_BOTTOM_PAD = 0.02
YIELD_MIN_TOP_PAD = 0.08

# Macro axis (log10): padding is expressed in decades.
MACRO_PAD_FRACTION = 0.05
MACRO_MIN_PAD_DECADES = 0.05

# Date axis: small symmetric pad so lines do not touch the plot border.
DATE_PAD_FRACTION = 0.015
MIN_DATE_PAD_DAYS = 1

# Font sizes in points, as designed for the default 2048 x 1536 canvas. Every
# use multiplies them by ``PlotConfig.font_scale`` so other canvas sizes keep
# the same proportions (a fixed 24 pt title overflowed a 1100 px canvas).
TITLE_FS = 24
LABEL_FS = 22
TICK_FS = 18
LEGEND_FS = 16
# Gap between a y-axis label and its tick labels, in points (scaled like the fonts).
AXIS_LABEL_PAD_PT = 8

# Lower bound on ``PlotConfig.font_scale``. Linear scaling would take the
# 800 px minimum canvas to 0.39 (7 pt tick labels, about 10 px tall); 0.5
# keeps them legible. At the floor the title may still be too wide, so it is
# also shrunk to fit on its own (see ``legend.finish_legend_and_title``).
MIN_FONT_SCALE = 0.5

# Regression segments (--reg, ratesplot.regression): how far a piece's line
# may lie from any observation it covers, as a percentage of the right axis's
# height (in log terms, so the same distance on the picture everywhere).
# 0.3 % (Terry, 2026-10-12, "after some testing", decision 30; 1 % until
# batch 8) is about 4 px on the default canvas, within the piece's own
# width. --reg:TOL sets it (PlotConfig.regression_tolerance).
DEFAULT_REGRESSION_TOLERANCE_PCT = 0.3
# ...but never less than this percentage of the value (ln 1.01 for 1 %), with
# --reg:TOL too: below it, on a window of a year or two, the pieces would
# follow each quarter's noise.
MIN_REGRESSION_TOLERANCE_PCT = 1.0

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

HTTP_TIMEOUT_SECONDS = 90
HTTP_POST_TIMEOUT_SECONDS = 60
# Statistics Canada's table ZIPs. A requests timeout is the longest silence
# allowed (before the first byte, or between two), not the whole download.
# Measured 2026-09-30 over 42 downloads of the 4 live and 11 archived tables:
# the first byte came within 1.4 s and no silence lasted 0.2 s. So 30 s is
# some twenty times the worst seen, and a request StatCan accepts and never
# answers (one did, 2026-09-30) is given up after 30 s rather than 90.
STATCAN_TIMEOUT_SECONDS = 30
# A request is asked once more, this long after it failed, only when its
# connection was dropped or reset part way or the server answered with an
# error status of its own (5xx); never after a 404 or other 4xx, an outage
# page, a bot check, a refused connection or a timeout, which the same request
# seconds later does not get past (batch 19.3, Terry's decision 52,
# 2026-10-22: "one retry after 2 s"; ``http._with_retries``). Before it a
# request had 4 attempts (FRED's 3), 2, 4 and 8 s apart, a 404 among the
# failures retried. On record then: one recovery (a Bundesbank download broken
# off part way, 2026-10-06, on its first retry); every retry failed for two
# Valet 404s and two FRED outage pages; the daily job's 9 runs, about 500
# requests, had no failed attempt.
RETRY_WAIT_SECONDS = 2
# How old a kept download may be before it is fetched again: on the web page
# for every drawing (it serves every visitor from one process for days), in
# the window at Refresh (F5). The regular sources publish at most once a day
# (yields in the afternoon, Debt to the Penny the next morning), so an hour
# shows each new figure within an hour at most, and the visitor who comes
# after a quiet hour waits for the downloads (about 10 s). Intraday quotes
# are never kept (``http.latest_get(cached=False)``).
DOWNLOAD_MAX_AGE_SECONDS = 3600
# The live sources' baked history (batch 19.2, ``ratesplot.baked``): how far
# before a baked series' last date each drawing asks its source again, so
# that late values and revisions in that span arrive. Terry's figures in
# 19.2's plan: about two months for market and announced rates, which are
# not revised, and 24 months for figures that are (GDP, debt, interest,
# population; survey results such as quoted mortgage rates). None of the
# Bank of England's nine series changed a value between 2026-10-06 and
# 2026-10-21 (measured).
RECENT_PART_UNREVISED = pd.DateOffset(months=2)
RECENT_PART_REVISED = pd.DateOffset(months=24)
# How far past its last day a chart may read a series (19.2 (b): a chart that
# ends before a recent part asks nothing for it; ``baked.chart_ending``): up
# to one of the series' periods. A rate observed over a month is dated by the
# month's last day and drawn across the month (the Bank of England's quoted
# mortgage rates, the ECB's German ones), and a value per person on a chart's
# last day may lie between the population's figure before it and the one
# after. Measured 2026-10-23 on 66 charts, each series altered from a day
# after the chart's end on: 10 charts read values dated after their end,
# none from 92 days after it on. A year, not the 92 days measured, since no
# live series is published less often than yearly: it holds for any chart.
CHART_READS_PAST_END = pd.DateOffset(years=1)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
BOC_GROUP_URL = "https://www.bankofcanada.ca/valet/observations/group/{group}/csv"
BOC_SERIES_URL = "https://www.bankofcanada.ca/valet/observations/{series_code}/csv"
STATCAN_TABLE_URL = "https://www150.statcan.gc.ca/n1/tbl/csv/{table_id}-eng.zip"
STATCAN_WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"
# Vectors' values from a date (a table's recent part, batch 19.2), by
# reference period. The end is required (406 without one); 9999-12-31, after
# any period, is accepted (measured 2026-10-22).
STATCAN_WDS_RANGE_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange"
STATCAN_WDS_RANGE_END = "9999-12-31"

# Each source's name in the message log, by the host its requests go to: a
# source that fails gets one warning per drawing, which names it once (batch
# 19.4, Terry's decision 53, 2026-10-22; ``http.drawing_downloads``). Each
# label its series and downloads are named by begins with it ("FRED DGS10",
# "Statistics Canada table 36100467"), and is listed without it there.
SOURCE_NAMES = {
    "fred.stlouisfed.org": "FRED",
    "www.bankofcanada.ca": "Bank of Canada",
    "www150.statcan.gc.ca": "Statistics Canada",
    "www.bankofengland.co.uk": "Bank of England",
    "www.ons.gov.uk": "ONS",
    "data-api.ecb.europa.eu": "ECB",
    "ec.europa.eu": "Eurostat",
    "api.statistiken.bundesbank.de": "Bundesbank",
    "www.bundesbank.de": "Bundesbank",
    "home.treasury.gov": "U.S. Treasury",
    "api.fiscaldata.treasury.gov": "U.S. Treasury",
    "quote.cnbc.com": "CNBC",
    "www2.census.gov": "Census Bureau",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}
# Single session for the Canadian providers (Bank of Canada, Statistics Canada)
# so TCP connections are reused across the several downloads per run. FRED is
# deliberately *not* routed through this session: see ``http.fetch_fred_csv``.
CANADIAN_SESSION = requests.Session()
CANADIAN_SESSION.headers.update(_BROWSER_HEADERS)
# The sources of the latest values (--cur, ``ratesplot.latest``): U.S. Treasury
# and the quote feed. A session of their own, so a problem there cannot
# disturb the Canadian downloads.
LATEST_SESSION = requests.Session()
LATEST_SESSION.headers.update(_BROWSER_HEADERS)
# The UK's sources (Bank of England, ONS): a session of their own, as the
# latest values have, with a browser's headers, which both require.
UK_SESSION = requests.Session()
UK_SESSION.headers.update(_BROWSER_HEADERS | {"Accept-Language": "en-GB,en;q=0.9"})
# Germany's sources (Deutsche Bundesbank, the ECB, Eurostat; batch 4): a
# session of their own, with a browser's headers, as they were measured with
# from Terry's laptop (2026-10-06).
DE_SESSION = requests.Session()
DE_SESSION.headers.update(_BROWSER_HEADERS | {"Accept-Language": "en-GB,en;q=0.9,de;q=0.8"})
# The quote feed is an extra: one quick try (asked once more only as every
# request is, RETRY_WAIT_SECONDS), then the chart is drawn without it (with a
# warning).
LATEST_QUOTE_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# Data sources and units
# ---------------------------------------------------------------------------

# The Bank of Canada Valet API is only needed from the point where the
# transcribed historical yield table (which ends 2000-12) stops. A one-month
# overlap is kept so forward-filling across the join sees the last live values.
BOC_START_DATE = "2000-12-01"
CANADIAN_YIELD_HIST_END = pd.Timestamp("2000-12-31")

# Live StatCan tables, and the vector the program reads of each
# (cdn_data.STATCAN_SERIES_READ; the GFS table's 22 are cdn_data.GFS_VECTORS).
# Measured 2026-10-22. Their history is baked (batch 19.2): a drawing asks
# Statistics Canada's WDS for the last 24 months only.
STATCAN_CDN_DEBT_TABLE = "36100467"       # general government gross debt, quarterly
STATCAN_CDN_GDP_TABLE = "36100104"        # GDP at market prices, SAAR, quarterly
STATCAN_CDN_INTEREST_TABLE = "10100015"   # consolidated government interest, quarterly
STATCAN_CDN_DEBT_VECTOR = "v111463452"    # "Debt"; also the WDS fallback's vector
STATCAN_CDN_GDP_VECTOR = "v62305783"      # current prices, SAAR, GDP at market prices
# The CMHC conventional 5-year mortgage lending rate, monthly from 1951
# (rates.cdn_mortgage_history), which carries Canada's posted 5-year rate back.
CDN_MORTGAGE_HISTORY_TABLE = "34100145"
CDN_MORTGAGE_HISTORY_VECTOR = "v733833"

# Archived (terminated) StatCan tables. They no longer change, so the bake
# (``tools/bake_archives.py``) downloads them once and writes the required rows
# into ``ratesplot/cdn_archive_data.py``. URLs are kept for auditability.
ARCHIVED_CDN_INTEREST_TABLE = "36100245"
ARCHIVED_CDN_FEDERAL_DEBT_TABLE = "36100533"
ARCHIVED_CDN_PROV_LOCAL_DEBT_TABLE = "36100534"
ARCHIVED_CDN_INTEREST_URL = STATCAN_TABLE_URL.format(table_id=ARCHIVED_CDN_INTEREST_TABLE)
ARCHIVED_CDN_FEDERAL_DEBT_URL = STATCAN_TABLE_URL.format(table_id=ARCHIVED_CDN_FEDERAL_DEBT_TABLE)
ARCHIVED_CDN_PROV_LOCAL_DEBT_URL = STATCAN_TABLE_URL.format(table_id=ARCHIVED_CDN_PROV_LOCAL_DEBT_TABLE)
# The same balance sheet split by level (provincial + local = 36100534 exactly),
# for the debt components (--debt:p, --debt:m).
ARCHIVED_CDN_PROVINCIAL_DEBT_TABLE = "36100535"
ARCHIVED_CDN_LOCAL_DEBT_TABLE = "36100536"

# Older history, also baked (see ``ratesplot.bake``).
# National accounts on the 1968 SNA basis, the source of GDP and government
# interest before 1961: annual from 1926, quarterly (SAAR) from 1947 for GDP
# and from 1950 for interest (the quarterly table is blank before that).
HISTORICAL_CDN_GDP_ANNUAL_TABLE = "36100150"
HISTORICAL_CDN_GDP_QUARTERLY_TABLE = "36100137"
HISTORICAL_CDN_INTEREST_ANNUAL_TABLE = "36100177"
HISTORICAL_CDN_INTEREST_QUARTERLY_TABLE = "36100142"
# Historical Statistics of Canada (StatCan 11-516-X), section H: federal debt
# from 1867, provincial and local debt from 1933 (1933, 1937, 1939, 1941,
# 1943, then yearly from 1945). Plain CSV files, not StatCan tables, in a
# folder per section ("sectionh"), named by the section's letter and the
# first and last series they hold.
HSC_URL = "https://www150.statcan.gc.ca/n1/pub/11-516-x/section{section}/{series}-eng.csv"
HSC_FEDERAL_DEBT_SERIES = "H35_51"
HSC_PROVINCIAL_DEBT_SERIES = "H382_397"
HSC_LOCAL_DEBT_SERIES = "H398_403"
# Section J: foreign exchange rates 1913-1977, Canadian dollars per unit of
# each currency (batch 18.4). ``fx`` reads J562, the U.S. dollar's annual
# average, for 1913 to 1962 (see there).
HSC_EXCHANGE_RATE_SERIES = "J560_567"
HSC_CAD_PER_USD = "J562"
# Bank of Canada financial market statistics (monthly, last Wednesday). Its
# average yields for the 1-3 and 3-5 year bands stand in for the 2- and 5-year
# benchmarks before those begin (1982-06 and 1980-11), as the 5-10 year and
# over-10 year bands already do for the 10- and 30-year history.
BOC_FINANCIAL_MARKET_TABLE = "10100122"
# Population: annual estimates from 1867 (baked), quarterly from 1946 (live).
HISTORICAL_CDN_POPULATION_TABLE = "17100063"
STATCAN_CDN_POPULATION_TABLE = "17100009"
STATCAN_CDN_POPULATION_VECTOR = "v1"

# Archive splice tuning: the median live/archived ratio is estimated over their
# overlap up to this year, and the last ``ARCHIVE_SPLICE_YEARS`` of the archive
# are ramped geometrically toward that ratio.
ARCHIVE_CALIBRATION_END_YEAR = 1994
ARCHIVE_SPLICE_YEARS = 5
ARCHIVE_BEGIN_MARKER = "# BEGIN AUTO-GENERATED CANADIAN ARCHIVE DATA"
ARCHIVE_END_MARKER = "# END AUTO-GENERATED CANADIAN ARCHIVE DATA"

# U.S. state and local government debt apart (Census Bureau), baked into
# ``ratesplot/us_archive_data.py``: the historical database of national totals
# (fiscal years 1902-2008, an Access file), then each later year's estimates
# by state and type of government (fixed-width text; 2009-2010 on the old
# site, later years inside each year's "Individual Unit File" ZIP).
CENSUS_HIST_FIN_URL = "https://www2.census.gov/programs-surveys/gov-finances/datasets/historical/hist_fin.zip"
CENSUS_OLD_ESTIMATES_URL = "https://www2.census.gov/govs/estimate/"
CENSUS_TABLES_URL = "https://www2.census.gov/programs-surveys/gov-finances/tables/"
US_ARCHIVE_BEGIN_MARKER = "# BEGIN AUTO-GENERATED U.S. ARCHIVE DATA"
US_ARCHIVE_END_MARKER = "# END AUTO-GENERATED U.S. ARCHIVE DATA"

# The UK (batch 3, 2026-10-06): the Bank of England's statistical database
# (IADB: gilt yields, Bank Rate, quoted mortgage rates) and the Office for
# National Statistics (debt, interest, GDP, population), both read live; the
# Bank's "A millennium of macroeconomic data" (no longer updated) baked into
# ``ratesplot/uk_archive_data.py``. Spans measured from Terry's laptop
# 2026-10-06 (tools/uk_fixtures/README.md).
BOE_IADB_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
# The database answers a request from this date; from 1950 or 1960 it
# redirects to its error page 905 instead (measured 2026-10-06). No series
# read from it begins before 1975.
BOE_IADB_FROM = "01/Jan/1975"
ONS_TIMESERIES_URL = "https://www.ons.gov.uk{path}/data"
UK_MILLENNIUM_URL = (
    "https://www.bankofengland.co.uk/-/media/boe/files/statistics/research-datasets/"
    "a-millennium-of-macroeconomic-data-for-the-uk.xlsx"
)
UK_ARCHIVE_BEGIN_MARKER = "# BEGIN AUTO-GENERATED UK ARCHIVE DATA"
UK_ARCHIVE_END_MARKER = "# END AUTO-GENERATED UK ARCHIVE DATA"

# Germany (batch 4, 2026-10-07): the Deutsche Bundesbank's time-series
# database (yields), the ECB Data Portal (key interest rates, bank lending
# rates, annual debt) and Eurostat (quarterly debt, interest, GDP,
# population), all read live; the Bundesbank's yield on public debt
# securities before 1972 (a frozen series) baked into
# ``ratesplot/de_archive_data.py``. Spans measured from Terry's laptop
# 2026-10-06 (tools/de_fixtures/README.md).
BUNDESBANK_SERIES_URL = "https://api.statistiken.bundesbank.de/rest/download/{flow}/{key}"
# The same database's SDMX web service: asked with format=csv&lang=en, the
# same CSV as the download above (the same text, for a whole series), but it
# reads startPeriod, which the download ignores (measured 2026-10-22). Batch
# 19.2 asks it for a series' recent part (``de_data.bundesbank_download``).
BUNDESBANK_DATA_URL = "https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}"
# The Bundesbank's old download, where the series of its former database
# (BBK01) that were never moved to the new one are kept, frozen at 2020-04.
BUNDESBANK_OLD_SERIES_URL = "https://www.bundesbank.de/statistic-rmi/StatisticDownload"
ECB_SERIES_URL = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
EUROSTAT_DATASET_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
DE_ARCHIVE_BEGIN_MARKER = "# BEGIN AUTO-GENERATED GERMAN ARCHIVE DATA"
DE_ARCHIVE_END_MARKER = "# END AUTO-GENERATED GERMAN ARCHIVE DATA"

# The latest values (--cur), newer than the regular series (see ratesplot.latest).
# U.S. Treasury's daily par yield curve: the source of FRED's DGS series,
# posted the same afternoon, where FRED follows a business day or more later.
TREASURY_YIELD_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all"
)
# U.S. Treasury's "Debt to the Penny": total public debt outstanding each
# business day, one day behind; FRED's quarterly GFDEBTN is its quarter-end value.
TREASURY_DEBT_TO_PENNY_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
# CNBC's quote feed (the one cnbc.com's own pages read): intraday government
# bond yields for both countries, a few minutes old. Unofficial, so it may
# change without notice; the chart is then drawn without it, with a warning.
CNBC_QUOTE_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
# Quotes are timed in New York / Toronto time (both markets' hours), and so
# dated by Toronto's day, as the chart's end is; each chart's subtitle gives
# their time in its own market's zone (Nation.market_timezone, batch 10.3).
MARKET_TIMEZONE = "America/Toronto"
# Chart column -> CNBC symbol, per country (``plotting.Country.key``): the
# yields intraday quotes extend (--cur, ratesplot.latest). Only the columns a
# chart draws are asked for (--yields:LIST); the U.S. terms outside the
# default five are CNBC's symbols of the same pattern, not yet seen answering
# from here (the cloud copy has no route to the feed). Moved here from
# ``latest`` in batch 11.3: the automatic refresh's rule reads it too
# (``PlotConfig.quoted_columns``).
QUOTE_SYMBOLS = {
    "us": {
        "1-Month": "US1M", "3-Month": "US3M", "6-Month": "US6M", "1-Year": "US1Y", "2-Year": "US2Y",
        "5-Year": "US5Y", "7-Year": "US7Y", "10-Year": "US10Y", "20-Year": "US20Y", "30-Year": "US30Y",
    },
    # Canada's (batch 9.3: CA1M, CA6M, CA1Y and CA3Y seen answering
    # 2026-10-20; CA7Y answers empty, so the 7-year ends on its last official day).
    "cdn": {
        "1-Month": "CA1M", "3-Month": "CA3M", "6-Month": "CA6M", "1-Year": "CA1Y", "2-Year": "CA2Y",
        "3-Year": "CA3Y", "5-Year": "CA5Y", "10-Year": "CA10Y", "30-Year": "CA30Y",
    },
    # The UK's three terms (batch 3; seen answering from the laptop 2026-10-06,
    # tools/uk_fixtures). Not GB3M-GB: that is a gilt repo rate, not a yield.
    "uk": {"5-Year": "GB5Y-GB", "10-Year": "GB10Y-GB", "20-Year": "GB20Y-GB"},
    # Germany's seven terms (batch 4; all seen answering from the laptop
    # 2026-10-06, tools/de_fixtures). CNBC does not know DE3M-DE. Quotes of
    # Bunds, against the Bundesbank's fitted zero-coupon curve: used as they
    # are, as the UK's are (a few basis points apart on the day measured).
    "de": {
        "1-Year": "DE1Y-DE", "2-Year": "DE2Y-DE", "5-Year": "DE5Y-DE", "7-Year": "DE7Y-DE",
        "10-Year": "DE10Y-DE", "20-Year": "DE20Y-DE", "30-Year": "DE30Y-DE",
    },
}
# The automatic refresh (--auto-refresh:MIN, batch 11.3; ratesplot.refresh):
# every 5 minutes when no value is given, and never more often, on the web
# page or anywhere else (Terry, 2026-10-08 and 2026-10-12, decision 23); at
# least once a day, since a longer wait is no refresh.
DEFAULT_AUTO_REFRESH_MINUTES = 5
MIN_AUTO_REFRESH_MINUTES = 5
MAX_AUTO_REFRESH_MINUTES = 24 * 60
# The markets' hours for the automatic refresh: Monday to Friday, from the
# first hour up to the second, in the zone of each chart's market
# (Nation.market_timezone). Within them each refresh draws again; outside
# them only when a quote has changed (plan 11.3). A working day's hours in
# each centre, ending where the U.S. quotes become the next day's session
# (``latest._NEXT_SESSION_HOUR``); a public holiday is not known, and is
# refreshed as a working day.
MARKET_HOURS = (8, 17)
# Bank of Canada: Government of Canada treasury bills and domestic marketable
# bonds outstanding, the total (real return bonds with their inflation
# adjustment), dollars, each business day, a few days behind; from 2025. It is
# the Fiscal Monitor's "market debt payable in Canadian currency" to within
# 0.5 %, months sooner. The series holds the current year; each earlier year
# is the same name with "_YYYY" added.
BOC_CDN_MARKET_DEBT_SERIES = "DOM_DBT_OUTSTANDING_AMOUNT_INF_ADJ_TOTAL"

# Unit multipliers. StatCan tables and FRED's GFDEBTN/SLGSDODNS report millions;
# FRED's GDP and interest series report billions; its population, thousands.
THOUSAND = 1_000
MILLION = 1_000_000
BILLION = 1_000_000_000

# ---------------------------------------------------------------------------
# Column names shared across data and plotting layers
# ---------------------------------------------------------------------------

DATE_COLUMN = "DATE"
YIELD_COLUMNS = ("3-Month", "2-Year", "5-Year", "10-Year", "30-Year")

# Yield terms (--yields:LIST): the short form a term is written in -> its
# column. Shortest first, which is the drawing and legend order. The five of
# YIELD_COLUMNS are drawn by default and are the only ones with Canada's
# history before 2001. Canada has all but the 20-year (batch 9.3: the 1- and
# 6-month, 1-, 3- and 7-year from 2001; see cdn_data.CDN_YIELD_COLUMNS); the
# U.S. all but the 3-year (FRED's DGS series; see us_data.US_YIELD_SERIES).
YIELD_TERMS = {
    "1m": "1-Month",
    "3m": "3-Month",
    "6m": "6-Month",
    "1y": "1-Year",
    "2y": "2-Year",
    "3y": "3-Year",
    "5y": "5-Year",
    "7y": "7-Year",
    "10y": "10-Year",
    "20y": "20-Year",
    "30y": "30-Year",
}
DEFAULT_YIELD_TERMS = ("3m", "2y", "5y", "10y", "30y")

GDP_COLUMN = "TTM Nominal GDP ($)"
CDN_DEBT_COLUMN = "Total Canadian Debt ($)"
# Before 1933 only federal debt is recorded; it is a separate curve, not part of
# the aggregate, because it is only about half of it (53 % in 1933).
CDN_FEDERAL_DEBT_COLUMN = "Federal Canadian Debt ($)"
POPULATION_COLUMN = "Population"
CDN_INTEREST_COLUMN = "TTM Interest Payable ($)"
US_DEBT_COLUMN = "Total Aggregate Debt ($)"
US_INTEREST_COLUMN = "TTM Interest Payments ($)"
UK_DEBT_COLUMN = "Total UK Debt (£)"
# Before general government debt begins (1975), the national debt alone: a
# curve of its own, dotted, as Canada's federal debt before 1933 is.
UK_NATIONAL_DEBT_COLUMN = "UK National Debt (£)"
# The UK's headline debt, beside the gross (Terry, 2026-10-06: "add net too").
UK_NET_DEBT_COLUMN = "UK Net Debt (£)"
# --aggregate:LIST (batch 10.4; Terry, 2026-10-13 and 2026-10-14, decision
# 33): the aggregate debt drawn, "gross" (general government gross debt, which
# every nation has) and "net" (the UK's public sector net debt excluding the
# public sector banks). Gross alone by default: gross debt is what the other
# charts draw, and the measure international comparisons use. Before, the UK
# drew both whenever debt was drawn (batch 3).
DEBT_AGGREGATES = ("gross", "net")
DEFAULT_DEBT_AGGREGATES = ("gross",)
UK_INTEREST_COLUMN = "TTM UK Interest Paid (£)"
DE_DEBT_COLUMN = "Total German Debt (€)"
DE_INTEREST_COLUMN = "TTM German Interest Paid (€)"

# ---------------------------------------------------------------------------
# Chart styling and per-country metadata
# ---------------------------------------------------------------------------

YIELD_LINE_STYLE = {"linewidth": 1.2, "alpha": 0.9}
# The left axis's label (PlotConfig.left_axis_label): with the yields drawn,
# or else with only other rates on it (--policy, --mortgages).
YIELD_AXIS_LABEL = "Bond Yield (%)"
RATE_AXIS_LABEL = "Rate (%)"
# --policy (ratesplot.rates): a step line, as a policy rate holds until it is
# changed; dark brown, a colour no yield term has, a little thicker than the
# yields so it reads as the anchor of the curve. (Dark gold at first: on
# real data it was hard to tell from the 2-year's orange where they cross;
# Terry chose dark brown, 2026-10-06.)
POLICY_RATE_STYLE = {"color": "#5c4033", "linewidth": 1.8, "drawstyle": "steps-post"}
# --policy:LIST (batch 9.1; Terry, decision 27, 2026-10-13): each central
# bank's official rate ("target", the default) and the market's overnight rate
# around it ("market": the effective fed funds rate, CORRA, SONIA, €STR), which
# moves day to day (the "jitter" Terry asked about, 2026-10-12). Every nation
# has both. The market rate alone is drawn as the policy rate was before
# (POLICY_RATE_STYLE); with the target, thin and pale beside the target's
# steps: the policy brown at 60 % on white, given as a colour of its own, not
# as transparency, since the end labels take a hidden line of a curve's colour
# and dashes for a piece of it (``endlabels._curve_end``), and the target's
# band has one.
POLICY_TERMS = ("target", "market")
DEFAULT_POLICY_TERMS = ("target",)
POLICY_MARKET_STYLE = POLICY_RATE_STYLE | {"color": "#9d8c85", "linewidth": 0.8}
# The U.S. target range (from 2008-12-16) is drawn as a band between its two
# limits, each a step line in the policy rate's style, shaded between them.
POLICY_BAND_ALPHA = 0.25
# --mortgages (ratesplot.rates): the terms, as written on the command line ->
# the countries that have them and the yield term whose colour they take (None:
# no yield of that term, so a colour of their own, MORTGAGE_OWN_COLORS). In
# this order on the chart. "5v" is Canada's 5-year variable rate; "prime" each
# country's banks' prime rate: Canada's chartered banks', which Canadian
# variable-rate mortgages are priced from (Terry, 2026-10-06: the 3-year and
# 6-month variable mortgages are popular in Canada, and have no series of
# their own; prime in their place), and since batch 9.4 the U.S. banks' prime
# loan rate, which prices home-equity lines (Terry, 2026-10-08). One term for
# both, as "10" is each country's 10-year yield: --mo:prime draws each chart's
# own prime rate.
MORTGAGE_TERMS = {
    "30": (("us",), "30y"),
    "15": (("us",), None),
    "5": (("cdn",), "5y"),
    # The 3-year yield's colour (batch 9.3), which is the colour the 3-year
    # mortgage had as its own before Canada had a 3-year yield.
    "3": (("cdn",), "3y"),
    "1": (("cdn",), "1y"),
    "5v": (("cdn",), "5y"),
    "prime": (("cdn", "us"), None),
    # The UK (batch 3): the Bank of England's quoted rates for new loans at
    # 75 % loan to value, fixed for 2, 3 or 5 years, and the standard
    # variable rate (SVR) a fixed rate reverts to. Written with an "f" so
    # they are not Canada's 5 and 3 (posted rates of other lenders).
    "2f": (("uk",), "2y"),
    "3f": (("uk",), "3y"),
    "5f": (("uk",), "5y"),
    "svr": (("uk",), None),
    # The UK tracker (batch 9.5, Terry's decision 26): Bank Rate plus a
    # margin (``MORTGAGE_MARGINS``), from 1997, when the Bank of England's
    # quoted tracker rate begins (``rates.UK_TRACKER_FROM``).
    "tracker": (("uk",), None),
    # Germany (batch 4): the MFI interest rates on new housing loans to
    # households (ECB), by initial rate fixation: over 1 and up to 5 years,
    # over 5 and up to 10, over 10. Named by the band, as the statistics
    # are; coloured as the yield of the band's top (the 20-year for over 10).
    "1-5": (("de",), "5y"),
    "5-10": (("de",), "10y"),
    "over10": (("de",), "20y"),
}
DEFAULT_MORTGAGE_TERMS = ("30", "5")
# The terms drawn plus a margin in points, each with a box beside its tick
# (batch 9.4, the prime rate; batch 9.5, the UK tracker): term -> the
# PlotConfig field holding the margin. The options, the controls and the
# drawing take them from here.
MORTGAGE_MARGINS = {"prime": "prime_margin", "tracker": "tracker_margin"}
# The tracker's margin by default, in points over Bank Rate (Terry, decision
# 26): about the Bank of England's quoted lifetime tracker less Bank Rate at
# its end (IUMBV24, 1.71 in 2025-03, its last month; median 1.68 in
# 2022-2025, 0.99 in 1997-2007, 2.44 in 2010-2019; measured 2026-10-21).
DEFAULT_TRACKER_MARGIN = 1.75
# The legend lists each nation's mortgage terms longest first, then its
# variable and prime rates, as it lists the yields longest first (batch 17.2,
# Terry 2026-10-15: "this would echo the vertical placement of the curves");
# they are drawn, and written on the command line, in MORTGAGE_TERMS' order.
MORTGAGE_LEGEND_ORDER = (
    "30", "15", "5", "3", "1", "5v", "prime", "5f", "3f", "2f", "svr", "tracker", "over10", "5-10", "1-5",
)
assert sorted(MORTGAGE_LEGEND_ORDER) == sorted(MORTGAGE_TERMS)
# The SVR has the prime rate's colour, a variable base rate as it is; the
# tracker the policy rate's brown, Bank Rate plus a margin as it is. (The
# 3-year mortgages, Canada's and the UK's, had dark slate here, #2f4f4f,
# until the 3-year yield took that colour in batch 9.3; they take the
# 3-year's colour now, as the other terms take theirs.)
MORTGAGE_OWN_COLORS = {"15": "#556b2f", "prime": "#696969", "svr": "#696969", "tracker": POLICY_RATE_STYLE["color"]}
# Dashed steps (a posted or surveyed rate holds until the next), thinner than
# the policy rate; the variable rates dash-dotted: Canada's, as it shares the
# 5-year's colour, and the UK tracker, as it shares the policy rate's.
MORTGAGE_STYLE = {"linewidth": 1.5, "linestyle": "--", "drawstyle": "steps-post"}
VARIABLE_MORTGAGE_STYLE = MORTGAGE_STYLE | {"linestyle": "-."}
# The prime rate: dotted, a base rate rather than a mortgage of a term.
PRIME_RATE_STYLE = MORTGAGE_STYLE | {"linestyle": ":", "linewidth": 1.8}
# --spreads[:LIST] (ratesplot.rates): pairs of yield terms, the first less the
# second, in percentage points. Drawn thick in colours no yield term, rate or
# right-axis curve has, one per pair in the order given (then round again),
# with their inverted stretches shaded (SPREAD_INVERSION_ALPHA). When one is
# drawn the left axis is "Yield and Spread (%)".
DEFAULT_SPREADS = (("10y", "2y"), ("10y", "3m"), ("30y", "10y"))
SPREAD_COLORS = ("#4b0082", "#c71585", "#000080", "#800000", "#008080")
SPREAD_STYLE = {"linewidth": 2.5}
SPREAD_AXIS_LABEL = "Yield and Spread (%)"


# ---------------------------------------------------------------------------
# Nations: what each one has (batch 2, 2026-10-06)
# ---------------------------------------------------------------------------

# The nations' currencies, by ISO 4217 code, and the symbol each chart's
# right axis writes its amounts with (``CountryMetadata.currency_prefix``),
# which the window and the page also show right of a nation's Top and Bottom
# boxes (batch 18.1, Terry 2026-10-14: "a $ (or other national currency
# symbol) drawn to the right of the Top/Bot value boxes").
CURRENCY_SYMBOLS = {"CAD": "C$", "USD": "$", "GBP": "£", "EUR": "€"}


@dataclass(frozen=True)
class Nation:
    """What one nation's chart can draw, and how the command line names it.

    The capabilities decide the controls in its panel (only its own yield
    terms and mortgage terms are offered) and what a choice made for every
    nation means for it (a term it lacks is left off its chart, with a note).
    Adding a nation means one of these, its CountryMetadata, its fetchers
    and its ``plotting.Country``.
    """

    key: str  # as plotting.Country.key and CountryMetadata.key
    name: str  # in messages and on its panel
    codes: tuple[str, ...]  # the prefixes that name it on the command line ("--us:top:20t"), lower case
    yield_terms: tuple[str, ...]  # the YIELD_TERMS keys it has a series for
    adjective: str  # in messages: "no Canadian 7-Year yield"
    # Drawn when the command line names no nation. Canada and the U.S. are,
    # as they always were; a nation added later is drawn only when asked for
    # (batch 3: every existing command line draws what it drew).
    shown_by_default: bool = True
    # Its own value of a list in PER_NATION_FIELDS, used while that list is
    # at the default for every chart (_LIST_DEFAULTS), where the default
    # would draw little or nothing on its chart: (field, value) pairs. With
    # none, the default is simply viewed as far as its chart has the terms.
    own_defaults: tuple[tuple[str, object], ...] = ()
    # Codes that name it in --nations:LIST only, never in front of a value:
    # there they would spell another option (batch 4: "--de:fp" is --debt:fp).
    list_only_codes: tuple[str, ...] = ()
    # The time zone of its main financial centre, in which its chart's
    # subtitle gives the time of the day's quotes (batch 10.3, Terry
    # 2026-10-08: London time on the UK's chart, not EDT). The quotes are
    # still dated by Toronto's day (MARKET_TIMEZONE), as the chart's end is.
    market_timezone: str = MARKET_TIMEZONE
    # The aggregate debts it has (DEBT_AGGREGATES): gross, and the UK net
    # too (batch 10.4). A nation with one has nothing to choose, so its panel
    # offers no box for it.
    debt_aggregates: tuple[str, ...] = DEFAULT_DEBT_AGGREGATES
    # Its levels of government (--debt:LETTERS; batch 10.5, Terry
    # 2026-10-13: "offering only the series that nation has"): the boxes in
    # its panel, (letter, caption), named for its governments, in the
    # plan's order, each caption its legend's name of the level
    # (``CountryMetadata.level_names``; Terry, 2026-10-23: "Länder" and
    # "State & Local", not the plan's "States" and "Non-federal"); and
    # letters that mean one of them on its chart
    # (synonym, letter): the UK's "n", all but central government, is its
    # local government, "m".
    level_boxes: tuple[tuple[str, str], ...] = ()
    level_synonyms: tuple[tuple[str, str], ...] = ()
    # The currency its amounts are in (a key of CURRENCY_SYMBOLS).
    currency: str = ""

    @property
    def currency_symbol(self) -> str:
        """The symbol its chart writes its amounts with ("C$"), shown right of its Top and Bottom boxes."""
        return CURRENCY_SYMBOLS[self.currency]

    @property
    def level_letters(self) -> tuple[str, ...]:
        """The letters its chart draws a level for, its synonyms included."""
        return tuple(letter for letter, _caption in self.level_boxes) + tuple(synonym for synonym, _letter in self.level_synonyms)

    @property
    def prefix(self) -> str:
        """The code written in front of its values in messages ("cdn", "ger"): its key, if that is a prefix."""
        prefixes = [code for code in self.codes if code not in self.list_only_codes]
        return self.key if self.key in prefixes else prefixes[0]

    @property
    def mortgage_terms(self) -> tuple[str, ...]:
        """The MORTGAGE_TERMS keys it has, in their order."""
        return tuple(term for term, (countries, _yield) in MORTGAGE_TERMS.items() if self.key in countries)

    @property
    def show_field(self) -> str:
        """The PlotConfig field that chooses its chart ("show_cdn")."""
        return f"show_{self.key}"

    def view(self, field: str, value: object) -> object:
        """Return what a list in ``field`` draws on this nation's chart: the yield and mortgage terms it has, the spreads of them.

        A term or pair it lacks is left off its chart (with a note), so two
        lists with the same view draw the same chart (a spread's colour goes
        by its place among those drawn, ``rates.yield_spreads``). The
        default list for every chart draws the nation's own default where it
        has one (``own_defaults``). The aggregate debts: those it has, and
        its gross debt where the list names none of them (``--aggregate:net``
        on Canada's chart; batch 10.4). The levels: those it has, a synonym
        as the level it means (the UK's "n" as "m"), in COMPONENT_LETTERS
        order; none where it has none of them, so its chart draws its
        aggregate lines, with a note (the UK and "p"; batch 10.5), as it
        draws its gross debt where it has none of the aggregates named. Top's
        and Bottom's currency: none where it is the nation's own (batch
        18.3). Any other field is its value.
        """
        own = dict(self.own_defaults)
        if field in own and value == _LIST_DEFAULTS[field]:
            return own[field]
        if field in LIMIT_CURRENCY_FIELDS:
            # A limit in its own currency is one without a currency (batch 18.3).
            return None if value == self.currency else value
        if field == "debt_aggregates":
            return tuple(item for item in value if item in self.debt_aggregates) or self.debt_aggregates[:1]
        if field == "components":
            synonyms = dict(self.level_synonyms)
            levels = {synonyms.get(letter, letter) for letter in value if letter in self.level_letters}
            return "".join(letter for letter in COMPONENT_LETTERS if letter in levels)
        if field == "yield_terms":
            return tuple(term for term in value if term in self.yield_terms)
        if field == "mortgage_terms":
            return tuple(term for term in value if term in self.mortgage_terms)
        if field == "spread_pairs":
            return tuple(pair for pair in value if all(term in self.yield_terms for term in pair))
        return value


# In drawing order, as plotting.COUNTRIES. The codes are ISO 3166 two-letter
# codes, plus the program's own "cdn".
# Their market zones (batch 10.3): Toronto, New York (the same clock),
# London (GMT, BST in summer) and Frankfurt (CET, CEST; the time-zone
# database's Europe/Berlin).
NATIONS: tuple[Nation, ...] = (
    # Canada: all terms but the 20-year (the Bank of Canada has none); the
    # U.S.: all but the 3-year (FRED's DGS3 exists, but was not asked for).
    Nation(
        "cdn", "Canada", ("ca", "cdn"), tuple(term for term in YIELD_TERMS if term != "20y"), "Canadian",
        market_timezone="America/Toronto", currency="CAD",
        level_boxes=(("f", "Federal"), ("p", "Provincial"), ("m", "Municipal"), ("n", "Non-federal")),
    ),
    Nation(
        "us", "United States", ("us",), tuple(term for term in YIELD_TERMS if term != "3y"), "U.S.",
        market_timezone="America/New_York", currency="USD",
        level_boxes=(("f", "Federal"), ("p", "State"), ("m", "Local"), ("n", "State & Local")),
    ),
    # Batch 3: drawn only when asked for, so every existing command line
    # draws what it drew. Its own defaults, since the defaults for every
    # chart would draw two of its three yield terms, none of its mortgage
    # terms and none of its spreads: all three terms, all its mortgage terms
    # (Terry, 2026-10-08, batch 10.2: for nations other than Canada and the
    # U.S., all ticked; the standard variable rate alone before; the tracker
    # with them since batch 9.5, as the plan said: "five UK mortgage lines
    # when mortgages are ticked"), the 10y-5y and 20y-10y spreads.
    Nation(
        "uk", "United Kingdom", ("gb", "uk"), ("5y", "10y", "20y"), "UK", shown_by_default=False,
        market_timezone="Europe/London", currency="GBP", debt_aggregates=DEBT_AGGREGATES,
        # Central and local government: the devolved governments are inside
        # central government in its accounts (CountryMetadata UK, uk_data).
        level_boxes=(("f", "Central"), ("m", "Local")), level_synonyms=(("n", "m"),),
        own_defaults=(
            ("yield_terms", ("5y", "10y", "20y")),
            ("mortgage_terms", ("2f", "3f", "5f", "svr", "tracker")),
            ("spread_pairs", (("10y", "5y"), ("20y", "10y"))),
        ),
    ),
    # Batch 4: drawn only when asked for, as the UK is. Its code "de" names it
    # in --nations only: "--de" is --debt and "--de:fp" --debt:fp, so a value
    # for Germany alone is written "--ger:max:8" (or "--deu:max:8", its ISO
    # three-letter code; Terry, 2026-10-07: "--deu:max:6 is ok"). Its own defaults, which are
    # what the defaults for every chart draw on its chart (it has no 3-month
    # yield), given so that no default chart notes the 3-month's absence;
    # and all three fixation bands as its mortgage rates (batch 10.2, as the
    # UK's; its usual fixation, 5 to 10 years, alone before).
    Nation(
        "de", "Germany", ("de", "ger", "deu"), ("1y", "2y", "5y", "7y", "10y", "20y", "30y"), "German",
        shown_by_default=False, list_only_codes=("de",), market_timezone="Europe/Berlin", currency="EUR",
        level_boxes=(("f", "Federal"), ("p", "Länder"), ("m", "Local"), ("n", "Länder & Local")),
        own_defaults=(
            ("yield_terms", ("2y", "5y", "10y", "30y")),
            ("mortgage_terms", ("1-5", "5-10", "over10")),
            ("spread_pairs", (("10y", "2y"), ("30y", "10y"))),
        ),
    ),
)


def nation_by_code(code: str, *, prefix: bool = False) -> Nation | None:
    """Return the nation a code names ("ca", "CDN", "us"), or None; with ``prefix``, only a code allowed in front of a value."""
    code = code.lower()
    return next(
        (nation for nation in NATIONS if code in nation.codes and not (prefix and code in nation.list_only_codes)), None
    )


def nation_by_key(key: str) -> Nation | None:
    """Return the nation with this key ("cdn"), or None."""
    return next((nation for nation in NATIONS if nation.key == key), None)


# The currency Top and Bottom are given in (batch 18.3): None for the chart's
# own, else an ISO code of CURRENCY_SYMBOLS, converted at each drawing.
LIMIT_CURRENCY_FIELDS = ("macro_top_currency", "macro_bottom_currency")
# The choices that can differ by nation (PlotConfig.for_nation): the yield
# axis's lists, the axis limits (Top and Bottom are in each nation's own
# currency unless given in another, so a limit right for one is wrong for the
# other), the aggregate debts (batch 10.4: only the UK has a choice), and the
# levels of government (batch 10.5, each nation's own in its panel).
PER_NATION_FIELDS = (
    "yield_terms", "mortgage_terms", "spread_pairs", "yield_ymin", "yield_ymax", "macro_bottom", "macro_top",
    "prime_margin", "policy_terms", "tracker_margin", "debt_aggregates", "components", *LIMIT_CURRENCY_FIELDS,
)
# The defaults of the lists a nation may have its own default of (Nation.own_defaults).
_LIST_DEFAULTS = {
    "yield_terms": DEFAULT_YIELD_TERMS,
    "mortgage_terms": DEFAULT_MORTGAGE_TERMS,
    "spread_pairs": DEFAULT_SPREADS,
}
# The colour of each yield term when the terms are chosen (--yields:LIST,
# --no-yields:LIST). The five default terms have the colours matplotlib's
# colour cycle gives them when all five are drawn (blue, orange, green, red,
# purple), and the other five the rest of that palette. Without a choice of
# terms the lines still take the cycle in drawing order, as they always have,
# so those charts are unchanged (plotting._yield_style).
TERM_COLORS = {
    "3m": "#1f77b4",
    "2y": "#ff7f0e",
    "5y": "#2ca02c",
    "10y": "#d62728",
    "30y": "#9467bd",
    "1m": "#8c564b",
    "6m": "#e377c2",
    "1y": "#7f7f7f",
    "7y": "#bcbd22",
    "20y": "#17becf",
    # The 11th term (batch 9.3), past the palette's ten: dark slate, which the
    # 3-year mortgages had as their own colour before (MORTGAGE_TERMS).
    "3y": "#2f4f4f",
}

# The same three semantic macro curves are drawn on both country charts, plus
# (Canada only) federal debt alone before the aggregate begins: dotted, so the
# drop in level where it hands over reads as a change of coverage.
MACRO_PLOT_STYLES = {
    "debt": {"color": "black", "linewidth": 2.5, "drawstyle": "steps-post"},
    "federal_debt": {"color": "black", "linewidth": 2.5, "drawstyle": "steps-post", "linestyle": ":"},
    "gdp": {"color": "darkgreen", "linewidth": 2.5, "drawstyle": "steps-post", "linestyle": "-."},
    "interest": {"color": "darkred", "linewidth": 2.5, "drawstyle": "steps-post", "linestyle": "--"},
    # Net debt (the UK's, batch 3), drawn with gross debt: solid as debt is,
    # in slate grey, a colour no other right-axis curve has.
    "net_debt": {"color": "#708090", "linewidth": 2.5, "drawstyle": "steps-post"},
}

# Components of debt and interest (--debt:LETTERS / --interest:LETTERS): f
# federal, n non-federal (provincial + local), p provincial or state (s is
# accepted for it), m municipal (local). Drawing order, and one colour each;
# debt lines are solid and interest lines dashed, as for the aggregates. The
# colours are darker than the thin yield lines' and avoid GDP's green.
COMPONENT_LETTERS = ("f", "n", "p", "m")
COMPONENT_SYNONYMS = {"s": "p"}
COMPONENT_COLORS = {"f": "#1f3a93", "n": "#8b4513", "p": "#d35400", "m": "#008080"}
MACRO_PLOT_STYLES.update(
    {
        f"{kind}_{letter}": {"color": color, "linewidth": 2.5, "drawstyle": "steps-post", "linestyle": linestyle}
        for kind, linestyle in (("debt", "-"), ("interest", "--"))
        for letter, color in COMPONENT_COLORS.items()
    }
)


# --cur on a chart reaching today: each right-axis curve's stretch from its last
# data to today, projected like a debt clock (ratesplot.latest.project_to_now),
# is drawn straight and fainter in the curve's own colour and dashes; one grey
# legend entry says what the faint stretches are, and their end labels read "≈".
# Canadian debt, when steered by the Government of Canada's market debt, is
# not straight, and the entry says so.
PROJECTION_ALPHA = 0.4
PROJECTION_LABEL = "Projected at the past year's pace"
PROJECTION_LABEL_STEERED = "Projected; debt follows market debt"
PROJECTION_KEY_COLOR = "0.35"
PROJECTION_LABEL_PREFIX = "≈"

# --spreads: a spread's inverted stretches (below zero) are shaded between it
# and zero in its own colour, this opaque (plotting.add_rate_lines).
SPREAD_INVERSION_ALPHA = 0.2


def component_column(kind: str, letter: str) -> str:
    """Return the column holding one level's ``kind`` ("debt" or "interest"), e.g. ``"Debt [f] ($)"``."""
    return f"{kind.capitalize()} [{letter}] ($)"


# Wording for -r (debt and interest as a percentage of GDP) and -p (per
# person): the right axis label, and what is added to the legend labels and
# to the title's macro phrase. The -p axis label is per country (its currency).
RELATIVE_AXIS_LABEL = "Percent of TTM GDP (Log Scale)"
RELATIVE_LABEL_SUFFIX = " / TTM GDP"
RELATIVE_TITLE_SUFFIX = " as % of TTM GDP"
PER_CAPITA_SUFFIX = " per Capita"
# Ends the title when debt or interest is drawn for more than one level of
# government; the legend names the levels (Terry, 2026-09-27: the title need
# not repeat the legend where that makes it awkward).
LEVELS_TITLE_SUFFIX = " by Level of Government"


def _measure_suffixes(config: PlotConfig) -> tuple[str, str]:
    """Return ``(legend_suffix, title_suffix)`` for the measure ``config`` asks for ("" for dollars)."""
    if config.relative:
        return RELATIVE_LABEL_SUFFIX, RELATIVE_TITLE_SUFFIX
    if config.per_capita:
        return PER_CAPITA_SUFFIX, PER_CAPITA_SUFFIX
    return "", ""


def _with_suffix(label: str, suffix: str) -> str:
    """Add ``suffix`` to a legend label, before a closing parenthetical such as "(pre-1933)"."""
    if suffix and label.endswith(")") and " (" in label:
        head, _, tail = label.rpartition(" (")
        return f"{head}{suffix} ({tail}"
    return label + suffix


def _without_years(label: str) -> str:
    """Return a legend label without its closing parenthetical: "UK National Debt (pre-1975)" -> "UK National Debt"."""
    if label.endswith(")") and " (" in label:
        return label.rpartition(" (")[0]
    return label


@dataclass(frozen=True)
class CountryMetadata:
    """Labels, column names and title wording for one country's chart.

    ``*_label`` strings appear in the legend; ``*_title`` strings are the
    phrases assembled into the chart title for whichever series were drawn.
    Under -r and -p both are qualified (see ``_measure_suffixes``).
    """

    key: str
    country_name: str
    currency_prefix: str
    currency_label: str
    per_capita_label: str
    yield_title: str
    debt_column: str
    debt_label: str
    debt_title: str
    interest_column: str
    interest_label: str
    interest_title: str = "Interest Outlays"
    gdp_column: str = GDP_COLUMN
    gdp_label: str = "TTM Nominal GDP"
    gdp_title: str = "TTM GDP"
    # Federal debt alone, for the years before the aggregate exists (None: no such curve).
    federal_debt_column: str | None = None
    federal_debt_label: str = ""
    federal_debt_title: str = ""
    # Net debt, drawn with the debt curve when chosen (--aggregate:LIST,
    # batch 10.4; None: no such curve). ``net_debt_title`` names it beside
    # gross debt ("Net Debt"), ``net_debt_alone_title`` without it, naming
    # the nation as the gross debt's phrase does.
    net_debt_column: str | None = None
    net_debt_label: str = ""
    net_debt_title: str = ""
    net_debt_alone_title: str = ""
    # The word the title phrases name the nation by, its adjective
    # ("Canadian", "German"; "US" and "UK" as they are), kept only in a
    # title's first phrase (batch 21, title_for). Terry, 2026-10-22 (batch
    # 22, decision 50): "the long-form adjectival form is to be preferred in
    # general ... only using the abbreviation when useful to keep the title
    # font size from having to shrink by a lot". The legend's labels keep
    # their own wording ("Aggregate CDN Public Debt").
    title_nation: str = ""
    # The short form put in place of ``title_nation`` in the first phrase
    # where the adjective would shrink the title a lot (title_for's
    # ``short``, chosen by legend.finish_legend_and_title): "CDN" for Canada
    # (Terry: "CDN is preferred, but for other nations use the international
    # standard"), for every other nation its ISO 3166-1 three-letter code
    # ("DEU"). "" for a nation whose word is short already ("US", "UK").
    # A nation added later gets both forms (decision 50).
    title_short: str = ""
    # Components (--debt:LETTERS): the name of each level, and the wording
    # around a name ("{}" is replaced by it, or in a title by nothing).
    level_names: tuple[tuple[str, str], ...] = (
        ("f", "Federal"), ("n", "Non-federal"), ("p", "Provincial"), ("m", "Municipal"),
    )
    component_debt_label: str = "{} Public Debt"
    component_interest_label: str = "{} TTM Interest Payable"
    component_debt_title: str = "{} Public Debt"
    component_interest_title: str = "{} Interest Outlays"

    def level_name(self, letter: str) -> str:
        """Return the name of level ``letter`` ("f" -> "Federal")."""
        return dict(self.level_names)[letter]

    def macro_axis_label(self, config: PlotConfig) -> str:
        """Return the right (macro) axis label for the measure ``config`` asks for."""
        if config.relative:
            return RELATIVE_AXIS_LABEL
        return self.per_capita_label if config.per_capita else self.currency_label

    def macro_specs(self, config: PlotConfig, *, aggregate_debt: bool = True) -> tuple[tuple[str, bool, str, str], ...]:
        """Return ``(style_key, enabled, column, label)`` for each macro curve, in legend order.

        Under -r GDP is the denominator and is not drawn itself. With
        components chosen, each of debt and interest is one line per level
        instead of the aggregate (and the federal-only debt before 1933 is
        simply the start of the federal line).

        ``aggregate_debt`` False: the aggregate's source failed, so the debt
        alone is drawn past the years its label gives and is named without
        them ("UK National Debt", not "UK National Debt (pre-1975)", when the
        ONS's gross debt fails and the national debt runs to 2016).

        The aggregate debts are those chosen that the nation has
        (``--aggregate:LIST``, ``Nation.view``; batch 10.4): gross debt, with
        the debt alone before it (Canada's federal debt to 1933, the UK's
        national debt to 1975), and the UK's net debt.
        """
        suffix = _measure_suffixes(config)[0]
        # The levels it has, a synonym as the level it means (the UK's "n" as
        # "m"); none of them, its aggregate lines (batch 10.5, ``Nation.view``).
        letters = nation_by_key(self.key).view("components", config.components)
        if letters:
            specs = [
                (f"debt_{letter}", config.include_debt, component_column("debt", letter),
                 self.component_debt_label.format(self.level_name(letter)))
                for letter in letters
            ]
            specs.append(("gdp", config.draws_gdp, self.gdp_column, self.gdp_label))
            specs += [
                (f"interest_{letter}", config.include_interest, component_column("interest", letter),
                 self.component_interest_label.format(self.level_name(letter)))
                for letter in letters
            ]
            return tuple((key, enabled, column, _with_suffix(label, suffix)) for key, enabled, column, label in specs)
        aggregates = nation_by_key(self.key).view("debt_aggregates", config.debt_aggregates)
        gross = config.include_debt and "gross" in aggregates
        specs = [
            ("debt", gross, self.debt_column, self.debt_label),
            ("gdp", config.draws_gdp, self.gdp_column, self.gdp_label),
            ("interest", config.include_interest, self.interest_column, self.interest_label),
        ]
        if self.net_debt_column is not None:
            # Chosen with the debt curve, when among the aggregates; listed after gross debt.
            net = config.include_debt and "net" in aggregates
            specs.insert(1, ("net_debt", net, self.net_debt_column, self.net_debt_label))
        if self.federal_debt_column is not None:
            # Chosen with gross debt, whose years before it it covers; listed
            # straight after it. Without the aggregate it is named by its
            # legend label less the years, not by its title phrase, which may
            # word the nation differently (batch 22: "Federal Canadian Public
            # Debt" in a title).
            label = self.federal_debt_label if aggregate_debt else _without_years(self.federal_debt_label)
            specs.insert(1, ("federal_debt", gross, self.federal_debt_column, label))
        return tuple((key, enabled, column, _with_suffix(label, suffix)) for key, enabled, column, label in specs)

    def title_for(
        self,
        *,
        yields_drawn: bool,
        macro_keys_drawn: Iterable[str],
        config: PlotConfig,
        rate_titles: Iterable[str] = (),
        short: bool = False,
    ) -> str:
        """Compose the chart title from the series that were actually drawn.

        Parts are joined with commas and a final ampersand, e.g.
        ``"U.S. Treasury Yields, Aggregate Public Debt & TTM GDP"``.
        Federal debt alone is named only when the aggregate is not drawn.
        Under -r and -p the macro phrase is qualified and set off from the
        yields by a semicolon, since the qualifier does not apply to them:
        ``"Canadian Benchmark Yields; Aggregate Public Debt & Interest
        Outlays as % of TTM GDP"``. ``rate_titles`` name the yield axis's other
        curves drawn (``ratesplot.rates``), after the yields, in the order
        given (the spreads first, ``plotting.draw_country``): "U.S. Treasury
        Yields, Spreads, Policy Rate, Aggregate Public Debt …".

        A title whose first phrase does not name the nation begins with it
        (batch 17.6, Terry 2026-10-20: every chart "should have the nation
        that pertains to the tab that it is plotted on included somewhere near
        the beginning of the main title"): "Canada: Policy Rate", "United
        States: TTM GDP & Interest Outlays". The yield and debt phrases name
        it ("Canadian Benchmark Yields", "Aggregate US Public Debt"), so a
        title beginning with one has no such prefix.

        The nation is named once (batch 21, Terry 2026-10-21: "once the
        country is identified in the main title, don't repeat it"): every
        phrase after the first drops it ("Aggregate Canadian Public Debt"
        becomes "Aggregate Public Debt"), and so after "Canada: " does every
        phrase. The legend keeps its labels, which name each series whole.

        ``short``: the first phrase names the nation by ``title_short``
        ("CDN Benchmark Yields"), the form drawn only where the adjective
        would shrink the title a lot (batch 22, decision 50). A nation with
        no short form, or a title beginning "Canada: ", is the same either way.
        """
        drawn = set(macro_keys_drawn)
        if "debt" in drawn:
            drawn.discard("federal_debt")
        macro_titles = {
            "debt": self.debt_title,
            "federal_debt": self.federal_debt_title,
            # Beside gross debt "Net Debt"; without it, named whole (batch 10.4).
            "net_debt": self.net_debt_title if "debt" in drawn else self.net_debt_alone_title,
            "gdp": self.gdp_title,
            "interest": self.interest_title,
        }
        # Component lines ("debt_f", "interest_p" …). A single level is named,
        # "Federal Canadian Public Debt"; with more, the legend names them and
        # the title ends "… by Level of Government" (after the -r / -p
        # qualifier, set off by a comma). Debt and interest split alike are
        # named once, after GDP: "TTM GDP & Canadian Public Debt and Interest
        # Outlays by Level of Government", "Federal Canadian Public Debt and
        # Interest Outlays" (the phrases as built; "Canadian" is dropped below
        # unless it comes first).
        levels = {
            kind: [letter for letter in COMPONENT_LETTERS if f"{kind}_{letter}" in drawn] for kind in ("debt", "interest")
        }
        split = [kind for kind in ("debt", "interest") if levels[kind]]
        by_level = any(len(levels[kind]) > 1 for kind in split)
        names = {kind: "" if by_level else self.level_name(levels[kind][0]) for kind in split}
        templates = {"debt": self.component_debt_title, "interest": self.component_interest_title}
        # The phrases that name the nation: the yields' and the debt's.
        naming = {self.yield_title, self.debt_title, self.federal_debt_title} | ({self.net_debt_alone_title} - {""})
        if len(split) == 2 and names["debt"] == names["interest"]:
            both = templates["debt"].format(names["debt"]).strip() + " and " + templates["interest"].format("").strip()
            naming.add(both)
            macro_parts = ([self.gdp_title] if "gdp" in drawn else []) + [both]
        else:
            for kind in split:
                drawn.add(kind)
                macro_titles[kind] = templates[kind].format(names[kind]).strip()
            naming.add(macro_titles["debt"])
            macro_parts = [macro_titles[key] for key in macro_titles if key in drawn]
        levels_suffix = LEVELS_TITLE_SUFFIX if by_level else ""
        yield_parts = ([self.yield_title] if yields_drawn else []) + list(dict.fromkeys(rate_titles))
        parts = yield_parts + macro_parts
        if not parts:
            return f"{self.country_name}: no series selected"
        nation = "" if parts[0] in naming else f"{self.country_name}: "
        # The nation named once: the first phrase keeps it (when it names it,
        # nothing else does); every later phrase that names it drops it.
        parts = [
            part if index == 0 or part not in naming else _nation_word_replaced(part, self.title_nation, "")
            for index, part in enumerate(parts)
        ]
        if short and self.title_short and not nation:
            parts[0] = _nation_word_replaced(parts[0], self.title_nation, self.title_short)
        yield_parts, macro_parts = parts[: len(yield_parts)], parts[len(yield_parts) :]
        title_suffix = _measure_suffixes(config)[1]
        if title_suffix and macro_parts:
            macro_phrase = _join_title_parts(macro_parts) + title_suffix + ("," if levels_suffix else "") + levels_suffix
            return nation + "; ".join(yield_parts + [macro_phrase])
        return nation + _join_title_parts(parts) + levels_suffix


def _nation_word_replaced(phrase: str, nation: str, word: str) -> str:
    """Return a title phrase with the word that names the nation replaced by ``word``, or dropped when it is "".

    "Aggregate Canadian Public Debt" -> "Aggregate Public Debt" (``word`` "")
    or "Aggregate CDN Public Debt" (``word`` "CDN").
    """
    words = phrase.split(" ")
    if nation not in words:
        raise ValueError(f"title phrase {phrase!r} does not name the nation by {nation!r}")
    at = words.index(nation)
    words[at : at + 1] = [word] if word else []
    return " ".join(words)


def _join_title_parts(parts: list[str]) -> str:
    """Join title phrases with commas and a final ampersand: "A, B & C"."""
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} & {parts[-1]}"


CDN = CountryMetadata(
    key="cdn",
    country_name="Canada",
    currency_prefix=CURRENCY_SYMBOLS["CAD"],
    currency_label="Nominal Units (CAD – Log Scale)",
    per_capita_label="Nominal Units per Capita (CAD – Log Scale)",
    # The titles name the nation by its adjective, the legend by CDN (batch 22).
    yield_title="Canadian Benchmark Yields",
    title_nation="Canadian",
    title_short="CDN",
    debt_column=CDN_DEBT_COLUMN,
    debt_label="Aggregate CDN Public Debt",
    debt_title="Aggregate Canadian Public Debt",
    interest_column=CDN_INTEREST_COLUMN,
    interest_label="TTM Interest Payable",
    federal_debt_column=CDN_FEDERAL_DEBT_COLUMN,
    federal_debt_label="Federal CDN Public Debt (pre-1933)",
    federal_debt_title="Federal Canadian Public Debt",
    component_debt_label="{} CDN Public Debt",
    component_debt_title="{} Canadian Public Debt",
)

US = CountryMetadata(
    key="us",
    country_name="United States",
    currency_prefix=CURRENCY_SYMBOLS["USD"],
    currency_label="Nominal Units (USD – Log Scale)",
    per_capita_label="Nominal Units per Capita (USD – Log Scale)",
    yield_title="U.S. Treasury Yields",
    # "U.S." in the yields' phrase, which always comes first; "US" in the rest.
    title_nation="US",
    debt_column=US_DEBT_COLUMN,
    debt_label="Aggregate US Public Debt",
    debt_title="Aggregate US Public Debt",
    interest_column=US_INTEREST_COLUMN,
    interest_label="TTM Interest Payable",
    # FRED has federal and state-and-local debt and interest quarterly; state
    # and local apart are yearly (Census debt, BEA interest) and split the
    # quarterly combined figures (see us_data).
    level_names=(("f", "Federal"), ("n", "State & Local"), ("p", "State"), ("m", "Local")),
    component_debt_label="{} US Public Debt",
    component_debt_title="{} US Public Debt",
)

UK = CountryMetadata(
    key="uk",
    country_name="United Kingdom",
    currency_prefix=CURRENCY_SYMBOLS["GBP"],
    currency_label="Nominal Units (GBP – Log Scale)",
    per_capita_label="Nominal Units per Capita (GBP – Log Scale)",
    # The Bank of England's fitted par yields (monthly averages of gilt
    # redemption yields before them): the title says which kind they are.
    yield_title="UK Gilt Yields (fitted par)",
    title_nation="UK",
    debt_column=UK_DEBT_COLUMN,
    debt_label="UK General Government Gross Debt",
    debt_title="UK General Government Gross Debt",
    interest_column=UK_INTEREST_COLUMN,
    # ONS NMYX: interest (and the odd dividend) the government sector pays
    # outside itself, so consolidated as the other aggregates are.
    interest_label="TTM Interest Paid (consolidated)",
    federal_debt_column=UK_NATIONAL_DEBT_COLUMN,
    federal_debt_label="UK National Debt (pre-1975)",
    federal_debt_title="UK National Debt",
    # ONS HF6W: public sector net debt excluding the public sector banks,
    # the UK's own headline measure, beside gross general government debt
    # when chosen (batch 10.4).
    net_debt_column=UK_NET_DEBT_COLUMN,
    net_debt_label="UK Public Sector Net Debt (ex banks)",
    net_debt_title="Net Debt",
    net_debt_alone_title="UK Public Sector Net Debt",
    # Central and local government only: the devolved governments are inside
    # central government in the UK accounts, so there is no "p" level, and
    # the non-central level "n" is local government (ratesplot.uk_data).
    level_names=(("f", "Central"), ("n", "Local"), ("p", "Devolved"), ("m", "Local")),
    component_debt_label="{} UK Public Debt",
    component_debt_title="{} UK Public Debt",
)

DE = CountryMetadata(
    key="de",
    country_name="Germany",
    currency_prefix=CURRENCY_SYMBOLS["EUR"],
    currency_label="Nominal Units (EUR – Log Scale)",
    per_capita_label="Nominal Units per Capita (EUR – Log Scale)",
    # The Bundesbank's Svensson term structure: zero-coupon yields fitted to
    # the Federal securities' prices; the title says which kind they are.
    yield_title="German Federal Yields (Svensson fitted)",
    title_nation="German",
    title_short="DEU",
    debt_column=DE_DEBT_COLUMN,
    debt_label="German General Government Gross Debt",
    debt_title="German General Government Gross Debt",
    interest_column=DE_INTEREST_COLUMN,
    # D.41 payable by general government, consolidated (less than the sum of
    # its subsectors' by 0.2 % on average, 2002-2026).
    interest_label="TTM Interest Payable (consolidated)",
    # Bund, Länder, Gemeinden (ratesplot.de_data); the social security funds
    # are no level of the chart.
    level_names=(("f", "Federal"), ("n", "Länder & Local"), ("p", "Länder"), ("m", "Local")),
    component_debt_label="{} German Public Debt",
    component_debt_title="{} German Public Debt",
)


# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlotConfig:
    """All runtime choices used by the data and plotting layers.

    Built once by ``cli.parse_args`` and passed down, so no module reads
    mutable global state to find out what the user asked for.
    """

    # None: DEFAULT_START_FLOOR, or the first date on which every chosen
    # curve has a value if that is later (Terry, 2026-09-29 and 2026-10-06),
    # found from the data by plotting.resolve_start before the charts are
    # prepared; nothing downstream of it sees None.
    start: pd.Timestamp | None = None
    end: pd.Timestamp = field(default_factory=_today)
    width_px: int = DEFAULT_CANVAS_PX[0]
    height_px: int = DEFAULT_CANVAS_PX[1]
    yield_ymin: float | None = None
    yield_ymax: float | None = None
    macro_bottom: float | None = None
    macro_top: float | None = None
    # --top:USD20t (batch 18.3): the currency Top and Bottom are given in, an
    # ISO code of CURRENCY_SYMBOLS; None, the chart's own. Converted to the
    # chart's own at the rate of its end date when it is drawn (plotting).
    macro_bottom_currency: str | None = None
    macro_top_currency: str | None = None
    include_yield: bool = True
    # --policy: each country's policy rate on the yield axis (ratesplot.rates);
    # additive, not under the curve rule.
    policy_rates: bool = False
    # --policy:LIST (batch 9.1): which of POLICY_TERMS, the official rate
    # ("target") and the market's overnight rate ("market"). Per nation
    # (--us:policy:market).
    policy_terms: tuple[str, ...] = DEFAULT_POLICY_TERMS
    # --mortgages[:LIST]: mortgage rates on the yield axis, the terms of
    # MORTGAGE_TERMS chosen (each drawn on the chart of its country); additive.
    mortgages: bool = False
    mortgage_terms: tuple[str, ...] = DEFAULT_MORTGAGE_TERMS
    # --prime:MARGIN (batch 9.4): the prime rate drawn plus this many points
    # (negative allowed), for the variable mortgages priced from it; 0 draws
    # the prime rate itself, as before. Per nation (--cdn:prime:-0.25).
    prime_margin: float = 0.0
    # --tracker:MARGIN (batch 9.5): the UK tracker drawn at Bank Rate plus
    # this many points (negative allowed). Per nation (--uk:tracker:2); only
    # the UK has a tracker.
    tracker_margin: float = DEFAULT_TRACKER_MARGIN
    # --spreads[:LIST]: yield spreads on the yield axis, each a pair of
    # YIELD_TERMS keys (the first less the second); additive. Their terms are
    # fetched even when the yields are not drawn.
    spreads: bool = False
    spread_pairs: tuple[tuple[str, str], ...] = DEFAULT_SPREADS
    # --yields:LIST / --no-yields:LIST: the yield terms drawn, as keys of
    # YIELD_TERMS in that order. A term a country has no series for is
    # simply not drawn on its chart, with a note (Canada has no 20-year, the
    # U.S. no 3-year: Nation.yield_terms).
    yield_terms: tuple[str, ...] = DEFAULT_YIELD_TERMS
    include_debt: bool = True
    include_gdp: bool = True
    include_interest: bool = True
    show_cdn: bool = True
    show_us: bool = True
    # The UK's chart (batch 3): only when asked for (--uk, --nations:gb).
    show_uk: bool = False
    # Germany's chart (batch 4): only when asked for (--ger, --nations:de).
    show_de: bool = False
    # --debt:LETTERS / --interest:LETTERS: the levels of government to split
    # debt and interest into, as letters from COMPONENT_LETTERS in that order
    # ("" = the aggregate lines).
    components: str = ""
    # --aggregate:LIST (batch 10.4): which aggregate debts are drawn
    # (DEBT_AGGREGATES), when debt is and no level is chosen. Per nation
    # (--uk:aggregate:gross,net); only the UK has net debt (Nation.view).
    debt_aggregates: tuple[str, ...] = DEFAULT_DEBT_AGGREGATES
    # -r: debt and interest as a percentage of TTM GDP, on a log percent axis;
    # GDP itself is not drawn.
    relative: bool = False
    # -p: GDP, debt and interest per person, still on a log dollar axis. At
    # most one of relative / per_capita is set (options.config_from_choices).
    per_capita: bool = False
    # -l: print each drawn line's last value at its right-hand end, in the
    # line's colour; the date axis is widened to make room (ratesplot.endlabels).
    end_labels: bool = False
    # --reg: fit each drawn right-axis curve with the fewest straight pieces on
    # its log axis, each labelled with its growth in %/yr (ratesplot.regression).
    regression: bool = False
    # --reg:TOL: the pieces' tolerance, in percent of the right axis's height;
    # None = DEFAULT_REGRESSION_TOLERANCE_PCT. Never below
    # MIN_REGRESSION_TOLERANCE_PCT of the value (ratesplot.regression).
    regression_tolerance: float | None = None
    # Choices for one nation only ("--us:top:20t"): (nation key, ((field,
    # value), ...)) for each nation with any, the fields among
    # PER_NATION_FIELDS. Every other nation, and every field not named,
    # takes the value above. See ``for_nation``.
    nation_settings: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = ()
    # --cur (on unless --no-cur): extend the regular series with the latest
    # values from faster sources, down to intraday quotes (ratesplot.latest).
    current: bool = True
    # --projections (on unless --no-projections): carry each right-axis curve
    # from its last observation to today (latest.project_to_now). Its own
    # switch since batch 11 (Terry, 2026-10-27, decision 72: "a clean break
    # between controlling projections with --projections and current quotes
    # with --current"); --cur turned both on and off before.
    projections: bool = True
    # --hover (on unless --no-hover, batch 11.2): the read-out by the pointer
    # resting on a line, in the window, on the web page and in the plain
    # matplotlib windows (ratesplot.hover). It draws nothing on the chart, so
    # the front ends do not draw again when only it changes (``same_chart``).
    hover: bool = True
    # --auto-refresh[:MIN] (batch 11.3, off by default): every MIN minutes
    # (None: DEFAULT_AUTO_REFRESH_MINUTES) what Refresh does, in the window, on
    # the web page and in the plain matplotlib windows, and the --save files
    # written again (ratesplot.refresh). It draws nothing on the chart, so the
    # front ends do not draw again when only it changes (``same_chart``).
    auto_refresh: bool = False
    auto_refresh_minutes: int | None = None
    # Open the interactive window (ratesplot.gui) rather than plain matplotlib windows.
    gui: bool = True
    # --save:FILE (batch 11.1): write the charts to FILE, the format by its
    # extension, and open no window (cli.save_charts).
    save: str | None = None

    def for_nation(self, key: str) -> PlotConfig:
        """Return the config one nation's chart is drawn with: these choices, with that nation's own over them.

        A list still at the default for every chart takes the nation's own
        default, if it has one (``Nation.own_defaults``).
        """
        own: dict[str, object] = {}
        for nation, overrides in self.nation_settings:
            if nation == key and overrides:
                own = dict(overrides)
        nation = nation_by_key(key)
        for field_name, value in nation.own_defaults if nation is not None else ():
            if field_name not in own and getattr(self, field_name) == _LIST_DEFAULTS[field_name]:
                own[field_name] = value
        return replace(self, **own) if own else self

    def same_chart(self, other: PlotConfig | None) -> bool:
        """Whether ``other`` draws the same charts as this: it may differ in what draws nothing, the hover read-out (batch 11.2) and the automatic refresh (11.3)."""
        if other is None:
            return False
        neither = {"hover": True, "auto_refresh": False, "auto_refresh_minutes": None}
        return replace(self, **neither) == replace(other, **neither)

    @property
    def refresh_minutes(self) -> int:
        """Return the minutes between automatic refreshes (--auto-refresh:MIN; batch 11.3)."""
        return DEFAULT_AUTO_REFRESH_MINUTES if self.auto_refresh_minutes is None else self.auto_refresh_minutes

    def quoted_columns(self, key: str) -> tuple[str, ...]:
        """Return the yield columns of nation ``key``'s chart that intraday quotes extend (--cur): those fetched that the feed quotes (``QUOTE_SYMBOLS``).

        The spreads' terms among them: a spread runs on to the day's quotes,
        as the yields it is taken from do (plotting).
        """
        symbols = QUOTE_SYMBOLS.get(key, {})
        return tuple(column for column in self.for_nation(key).fetched_yield_columns if column in symbols)

    @property
    def refresh_brings_nothing(self) -> str | None:
        """Return why an automatic refresh can bring nothing new to these charts, or None when it can (batch 11.3).

        Plan 11.3 (Terry): greyed "when it can bring nothing new: --cur off,
        End not today, or no yields on any chart shown (only yields have
        intraday quotes, now, but when new series are added later that have
        them, this would apply to them also)". So the rule asks for a curve
        the quotes extend (``quoted_columns``): the spreads count, since a
        spread runs on to the day's quotes. An End after today keeps it, as
        the day's quotes are drawn there too. The window and the page grey
        the box out (``options.auto_refresh_idle``); the command line draws
        once, with this reason (``cli``).
        """
        if not self.current:
            return "the intraday quotes are off (--no-cur)"
        if self.end < _today():
            return f"the End date, {self.end:%Y-%m-%d}, is before today"
        shown = [nation for nation in NATIONS if getattr(self, nation.show_field)]
        if not any(self.quoted_columns(nation.key) for nation in shown):
            return "no chart shown has a yield with intraday quotes"
        return None

    @property
    def figsize_inches(self) -> tuple[float, float]:
        """Return the configured pixel canvas converted to inches for Matplotlib."""
        return self.width_px / CANVAS_DPI, self.height_px / CANVAS_DPI

    @property
    def font_scale(self) -> float:
        """Return the factor applied to every font size and font-related spacing.

        Exactly 1.0 on the default canvas, so the default chart is unchanged.
        Otherwise it is the smaller of the width and height ratios to the
        default. That way a wide, short canvas is scaled for the height it
        lacks, and a tall, narrow one for the width. It never goes below
        ``MIN_FONT_SCALE``. Canvases larger than the default scale up, so text
        does not shrink to a speck on a 4096 px render.
        """
        ratio = min(self.width_px / DEFAULT_CANVAS_PX[0], self.height_px / DEFAULT_CANVAS_PX[1])
        return max(MIN_FONT_SCALE, ratio)

    @property
    def line_scale(self) -> float:
        """Return the factor applied to line widths, grid lines, tick marks and the axes frame.

        On canvases larger than the default it equals ``font_scale``, so a
        4096 px render is a true enlargement rather than big text over
        hairlines. It never goes below 1.0: the default yield lines are
        1.2 pt, only about 1.7 px, and thinning them on a small canvas
        would make them fade.
        """
        return max(1.0, self.font_scale)

    @property
    def yield_columns(self) -> tuple[str, ...]:
        """Return the yield columns drawn, in drawing order; none when the yield curves are off."""
        return tuple(YIELD_TERMS[term] for term in self.yield_terms) if self.include_yield else ()

    @property
    def fetched_yield_columns(self) -> tuple[str, ...]:
        """Return the yield columns to fetch: those drawn, and those the spreads are taken from, in drawing order."""
        spread_terms = {term for pair in self.spread_pairs for term in pair} if self.spreads else set()
        drawn = set(self.yield_terms) if self.include_yield else set()
        return tuple(column for term, column in YIELD_TERMS.items() if term in drawn | spread_terms)

    @property
    def has_left_axis_series(self) -> bool:
        """True when at least one curve on the left (yield) axis is chosen: the yields, or a curve of ``ratesplot.rates``."""
        return self.include_yield or self.policy_rates or self.mortgages or self.spreads

    @property
    def left_axis_label(self) -> str:
        """Return the left axis's label for the curves chosen on it: "Rate (%)" when the yields are not among them."""
        return YIELD_AXIS_LABEL if self.include_yield else RATE_AXIS_LABEL

    @property
    def draws_gdp(self) -> bool:
        """True when the GDP curve is drawn: selected, and not the -r denominator."""
        return self.include_gdp and not self.relative

    @property
    def needs_gdp(self) -> bool:
        """True when GDP must be fetched: to draw it, or to divide debt or interest by it (-r)."""
        return self.include_gdp or (self.relative and (self.include_debt or self.include_interest))

    @property
    def has_macro_series(self) -> bool:
        """True when at least one curve on the right (log) axis is drawn."""
        return self.include_debt or self.draws_gdp or self.include_interest

    @property
    def has_explicit_macro_limits(self) -> bool:
        """True when the user pinned either end of the right axis."""
        return self.macro_bottom is not None or self.macro_top is not None

    @property
    def default_macro_ylim(self) -> tuple[float, float]:
        """Return the right axis's fallback limits, in the units of its measure."""
        if self.relative:
            return DEFAULT_RELATIVE_YLIM
        return DEFAULT_PER_CAPITA_YLIM if self.per_capita else DEFAULT_MACRO_YLIM
