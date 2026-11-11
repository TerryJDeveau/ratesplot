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
  exactly where both exist. Before them West Germany's, baked (``_with_older_debt``):
  the Federal Statistical Office's debt to the non-public sector from 1950-03-31,
  dated 31 March to 1959 and 31 December from 1960, its own figure for 1991 giving the
  ratio to the ECB's over the same territory. West Berlin comes in at 1952 and the
  Saarland at 1960, and unification at 1991, each kept as a step.
* Levels (``--debt:LETTERS``): the federal government ("f", Bund, central
  government S1311 with its special funds), the Länder ("p", state
  government S1312), local government ("m", Gemeinden, S1313), and "n" the
  Länder and local together. The social security funds (S1314, under 0.5 %
  of the total) are no level of the chart. The levels are not consolidated
  with each other, so they add up to about 1 % more than the total; before
  2000 the same Office's table, from 1950, its figure for 2000 giving each ratio
  to Eurostat's, so there they add up to the Office's total, not to the line drawn.
* Interest: D.41 interest payable by general government (consolidated),
  quarterly from 2002 (Eurostat gov_10q_ggnfa), summed over four quarters,
  and before it the annual figures from 1995 (gov_10dd_edpt1), which equal
  the sums of their quarters exactly where both exist. Before them the Federal
  Statistical Office's years, baked (``_older_interest``): all of Germany's from
  1991 (Fachserie 18 Reihe 1.4), which from 1995 are Eurostat's exactly, and
  West Germany's from 1970 (Reihe S.29), unification kept as a step at 1991,
  and the total before it from 1950 (``west_german_interest_before_1970``, Reihe
  S.7 of 1985, typed from its table), without the Saarland and West Berlin to
  1959, a step at 1960, its 1965 to 1969 bridged to the revised level at 1970 as
  GDP's are. Each level the same from 1970 (no older source splits
  it), the Office's years until Eurostat's quarters begin (2002).
* GDP: at market prices, current prices, not seasonally adjusted, quarterly
  from 1991 (Eurostat namq_10_gdp), summed over four quarters, from 1991-12-31.
  Before it West Germany's, baked (``west_german_gdp``): the Federal Statistical
  Office's four-quarter sums from 1970-12-31 to 1991-09-30, its years on the old
  basis from 1960 and without the Saarland and West Berlin from 1950, each at its
  year's end. The two changes of territory are kept as steps (1960, 1991); the
  revision of 2005 at 1970 is bridged, not a change of territory.
* Population: Eurostat namq_10_pe (thousands, quarterly from 1991, dated
  mid-quarter), and before it demo_pjan (on 1 January, from 1960: West
  Germany until 1990, so the curve steps up by 17 million at unification,
  as the UK's steps at Ireland's independence), and before it the
  Bundesbank's annual averages for 1950 to 1959, baked, each dated 1 July.
* The balance of payments (batch 23): the Bundesbank's monthly items
  (``DE_PAYMENTS_SERIES``), read here and added up by ``ratesplot.payments``;
  per person its twelve-month sums of 1990 and 1991 have a population of
  their own (``payments_population``).

Every figure is dated by the day it describes: a stock at the end of its
quarter or year, a four-quarter sum at the end of its last quarter, an
end-of-month yield at the month's end, a monthly average at the month's
start. Values are in euros (and persons); each source's unit is checked
against the one measured, so a change of unit fails rather than shifting a
curve a thousandfold. Deutsche Mark figures before 1999 are in euros at
1.95583, as the ECB publishes them in national currency (XDC) and Eurostat in
its national-currency units (MIO_NAC, CP_MNAC). Eurostat's euro units (MIO_EUR,
CP_MEUR) are not asked for: they convert each year before 1999 at that year's
ECU rate instead (measured 2026-11-10: GDP 4.6 % low in 1991, interest 4.4 %
high in 1995; from 1999 the two units agree exactly).

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
from typing import Mapping, NamedTuple

import numpy as np
import pandas as pd

from .config import (
    BILLION,
    BUNDESBANK_DATA_URL,
    BUNDESBANK_SERIES_URL,
    COMPONENT_LETTERS,
    DATE_COLUMN,
    DE_DEBT_COLUMN,
    DE_INTEREST_COLUMN,
    DEM_PER_EUR,
    ECB_SERIES_URL,
    EUROSTAT_DATASET_URL,
    GDP_COLUMN,
    MILLION,
    PAYMENTS_CREDITS_COLUMN,
    PAYMENTS_DEBITS_COLUMN,
    POPULATION_COLUMN,
    RECENT_PART_REVISED,
    RECENT_PART_UNREVISED,
    THOUSAND,
    YIELD_TERMS,
    PlotConfig,
    component_column,
)
from .baked import frame_with_recent_part, read_series, with_recent_part
from .de_archive_data import (
    EMBEDDED_DE_DEBT_FEDERAL,
    EMBEDDED_DE_DEBT_LOCAL,
    EMBEDDED_DE_DEBT_PER_PERSON,
    EMBEDDED_DE_DEBT_STATES,
    EMBEDDED_DE_DEBT_TOTAL,
    EMBEDDED_DE_INTEREST_FEDERAL,
    EMBEDDED_DE_INTEREST_LOCAL,
    EMBEDDED_DE_INTEREST_STATES,
    EMBEDDED_DE_INTEREST_TOTAL,
    EMBEDDED_DE_PUBLIC_DEBT_YIELD_HISTORY,
    EMBEDDED_DE_WEST_CPI_ALL_HOUSEHOLDS,
    EMBEDDED_DE_WEST_CPI_FOUR_PERSON,
    EMBEDDED_DE_WEST_GDP_NARROW,
    EMBEDDED_DE_WEST_GDP_OLD_BASIS,
    EMBEDDED_DE_WEST_GDP_PER_PERSON,
    EMBEDDED_DE_WEST_GDP_QUARTERS,
    EMBEDDED_DE_WEST_INTEREST_BEFORE_1970,
    EMBEDDED_DE_WEST_INTEREST_FEDERAL,
    EMBEDDED_DE_WEST_INTEREST_LOCAL,
    EMBEDDED_DE_WEST_INTEREST_STATES,
    EMBEDDED_DE_WEST_INTEREST_TOTAL,
    EMBEDDED_DE_WEST_POPULATION,
    EMBEDDED_DE_WEST_POPULATION_AT_UNIFICATION,
)
from .http import BotCheck, de_get, downloads_of
from .joins import embedded_frame, splice_archived_series, ttm_sum

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


class LinkedBond(NamedTuple):
    """One inflation-linked Federal bond (``DE_LINKED_BONDS``): its class in flow BBSSY's key, its redemption day, and its last value's day once redeemed."""

    security_class: str
    redeemed: pd.Timestamp
    last_value: pd.Timestamp | None = None


# Germany's real yields (batch 13.3; Terry, 2026-11-04, decision 108). The
# Bundesbank publishes no real curve, but each inflation-linked Federal bond's
# real yield, daily, by ISIN (flow BBSSY, "Yields by ISIN": "The yield
# indicated here for I/L is the real yield", its price list of 2026-11-03,
# whose figures it matches), for these five, all it holds; the bonds of 2006
# and 2009 are not in it. Their redemption days from that list and the bonds'
# names (all on 15 April); no new one has been issued since 2023 (Finanzagentur,
# 2023-11-22), so after April 2032 no term below has a bond under it.
DE_LINKED_BOND_FLOW = "BBSSY"
_LINKED_BOND_KEY = "D.REN.EUR.{security_class}.{isin}.A"
DE_LINKED_BONDS = {
    "DE0001030542": LinkedBond("A630", pd.Timestamp("2023-04-15"), pd.Timestamp("2023-04-12")),
    "DE0001030567": LinkedBond("A630", pd.Timestamp("2026-04-15"), pd.Timestamp("2026-04-10")),
    "DE0001030559": LinkedBond("A630", pd.Timestamp("2030-04-15")),
    "DE0001030583": LinkedBond("A630", pd.Timestamp("2033-04-15")),
    "DE0001030575": LinkedBond("A640", pd.Timestamp("2046-04-15")),
}
# Chart column -> its constant years to redemption, and its first day (the
# first with a bond on either side, measured 2026-11-04).
DE_REAL_TERMS = {"5-Year Real": 5.0, "7-Year Real": 7.0, "10-Year Real": 10.0}
DE_REAL_EARLIEST = {
    "5-Year Real": pd.Timestamp("2018-04-16"),
    "7-Year Real": pd.Timestamp("2016-04-15"),
    "10-Year Real": pd.Timestamp("2014-04-08"),
}
# A bond this near redemption is left out: its yield runs wild on so little
# time left (the bond of 2023 reached about -6 in its last year or so).
_LINKED_BOND_MIN_YEARS = 1.0
_DAYS_IN_A_YEAR = 365.25
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
# The consumer price index, all items, Germany, monthly from 1991-01, 2020 =
# 100, not seasonally adjusted (batch 13.1, --inflation; measured 2026-11-03:
# 430 months to 2026-10, each with a value). A new base year comes as a new
# key (I20 for 2020 = 100), this one then stopping. Baked under
# ``ratesplot/data/bbk/`` with the term structure. West Germany's older
# indexes carry it back (``with_west_germany``, batch 16).
DE_CPI_SERIES = ("BBDP1", "M.DE.N.VPI.C.A00000.I20.A")
# The same index seasonally adjusted (key M.DE.Y...), on the same base (batch
# 13.4, the price index on the right axis; measured 2026-11-03: 1991-01 to
# 2026-10, 430 months, each with a value; each year's mean within 0.09 % of
# the unadjusted index's). Revised as its seasonal factors are re-estimated,
# so its recent part is a revised series' (``fetch_de_consumer_prices``).
DE_CPI_SA_SERIES = ("BBDP1", "M.DE.Y.VPI.C.A00000.I20.A")
# The balance of payments (batch 23's third stage, --payments; measured
# 2026-11-11): the Bundesbank's monthly balance of payments (flow BBFBOPV),
# unadjusted ("N"), Germany against the rest of the world, each item's credits
# ("C", receipts) and debits ("D", expenditure), millions of euros a month,
# from 1971-01: West Germany to 1990-06 and all of Germany from 1990-07 in one
# series, the Deutsche Mark years in euros at 1.95583. Items: goods ("G"),
# services ("S"), primary income ("IN1") and secondary income ("IN2"); credits
# less debits over the four equal the current account balance (key
# ...T.B.CA...) within 0.002 million every month, and from 1991 each quarter
# equals Eurostat's bop_c6_q (MIO_NAC) exactly. Only these monthly figures are
# unadjusted and whole (the adjusted file holds the latest quarter alone);
# nothing monthly or quarterly before 1971, and no series of West Germany's
# own. The key's seventeenth part, "ALL", is required: without it the
# Bundesbank answers 404 (measured 2026-11-11). Revised as the accounts are.
DE_PAYMENTS_FLOW = "BBFBOPV"
_DE_PAYMENTS_KEY = "M.N.DE.W1.S1.S1.T.{side}.{item}._Z._Z._Z.EUR._T._X.N.ALL"
DE_PAYMENTS_SIDES = ("C", "D")
DE_PAYMENTS_ITEMS = ("G", "S", "IN1", "IN2")
# (side, item) -> (flow, key) of each of the eight series.
DE_PAYMENTS_SERIES = {
    (side, item): (DE_PAYMENTS_FLOW, _DE_PAYMENTS_KEY.format(side=side, item=item))
    for side in DE_PAYMENTS_SIDES for item in DE_PAYMENTS_ITEMS
}
# The first month of the balance of payments' figures for all of Germany.
DE_PAYMENTS_UNIFIED_FROM = pd.Timestamp("1990-07-01")
# The unit of each Bundesbank series not in percent, as its CSV gives it
# (``parse_bundesbank_csv``), by flow and key.
_BUNDESBANK_UNITS = {
    DE_CPI_SERIES: ("2020=100",),
    DE_CPI_SA_SERIES: ("2020=100",),
    **{series: ("euro",) for series in DE_PAYMENTS_SERIES.values()},
}
# The multiplier of each Bundesbank series whose CSV gives another than one,
# by flow and key: its figures are returned as written, in that multiple.
_BUNDESBANK_MULTIPLIERS = {series: "millions" for series in DE_PAYMENTS_SERIES.values()}
# A series whose CSV gives a multiplier that is not its figures': the bond of
# 2023's says "Tens", where its figures are percent as written, as the other
# bonds' are (0.090 on its first day, issued at about par with a coupon of
# 0.1; measured 2026-11-04).
_BUNDESBANK_MULTIPLIER_MISWRITTEN = ("BBSSY.D.REN.EUR.A630.DE0001030542.A",)
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
# Amounts in national currency (MIO_NAC, CP_MNAC), Deutsche Marks before 1999
# at 1.95583; not in MIO_EUR or CP_MEUR, which convert those years at each
# year's ECU rate (the module's docstring). Measured 2026-11-10: the GDP of
# 1991 is then 1591.61 billion, the Federal Statistical Office's own, not
# 1518.03; the interest of 1995 is 66,581 million, the Office's, not 69,497.6;
# from 1999 every value of all four datasets the same in either unit.
EUROSTAT_QUERIES = {
    "gov_10q_ggdebt": ({"geo": "DE", "unit": "MIO_NAC", "na_item": "GD"}, "MIO_NAC"),
    "gov_10q_ggnfa": ({"geo": "DE", "unit": "MIO_NAC", "na_item": "D41PAY", "s_adj": "NSA"}, "MIO_NAC"),
    "gov_10dd_edpt1": ({"geo": "DE", "unit": "MIO_NAC"}, "MIO_NAC"),
    "namq_10_gdp": ({"geo": "DE", "unit": "CP_MNAC", "na_item": "B1GQ", "s_adj": "NSA"}, "CP_MNAC"),
    "namq_10_pe": ({"geo": "DE", "unit": "THS_PER", "na_item": "POP_NC", "s_adj": "NSA"}, "THS_PER"),
    "demo_pjan": ({"geo": "DE", "sex": "T", "age": "TOTAL"}, "NR"),
}
_EUROSTAT_MULTIPLIER = {"MIO_NAC": MILLION, "CP_MNAC": MILLION, "THS_PER": THOUSAND, "NR": 1}
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
    "German General Government Debt (West Germany's from 1950, the ECB's year ends from 1991)": pd.Timestamp("1950-03-31"),
    "TTM Nominal GDP (West Germany's from 1950, Eurostat's quarters from 1991)": pd.Timestamp("1950-12-31"),
    "TTM German Interest Payable (West Germany's from 1950, the Office's from 1991, Eurostat's from 1995)": pd.Timestamp("1950-12-31"),
}

# Where Germany's GDP covers another territory than the population drawn, so has a
# population of its own (``west_german_gdp_population``). Its first figure with the
# Saarland and West Berlin: an observation shows on the first chart date on or after
# its own, so 1959's may show on 1960-01-01, and its population holds until this date,
# not to 1959-12-31. The first count in the population drawn that unification's step
# reaches: interpolated towards all of Germany's from here. The first sum for all of
# Germany: the population drawn is the GDP's again.
_DE_GDP_WHOLE_TERRITORY_FROM = pd.Timestamp("1960-12-31")
_DE_POPULATION_STEP_REACHES_FROM = pd.Timestamp("1990-01-01")
_DE_GDP_UNIFIED_FROM = pd.Timestamp("1991-12-31")
# The population drawn's first count of all of Germany (Eurostat's demo_pjan on
# 1 January 1991), held back over 1990 for the balance of payments' months of
# all of Germany (``payments_population``).
_DE_POPULATION_UNIFIED_FROM = pd.Timestamp("1991-01-01")

# The Federal Statistical Office's debt by the Eurostat subsector it is joined to, and
# the last year it can be compared with a live series: its figures stop at that year.
_DE_DEBT_OF_SECTOR = {"S1311": EMBEDDED_DE_DEBT_FEDERAL, "S1312": EMBEDDED_DE_DEBT_STATES, "S1313": EMBEDDED_DE_DEBT_LOCAL}
_DE_DEBT_RATIO_UNTIL_YEAR = 2000
# The Office's interest paid by the Eurostat sector it is joined to: West Germany's years
# (1970-1990) and all of Germany's (from 1991, the total to 1995 and each level to 2002, the
# first year of the live series, whose figure is the live series' own and is not drawn).
_DE_INTEREST_OF_SECTOR = {
    GENERAL_GOVERNMENT: (EMBEDDED_DE_WEST_INTEREST_TOTAL, EMBEDDED_DE_INTEREST_TOTAL),
    "S1311": (EMBEDDED_DE_WEST_INTEREST_FEDERAL, EMBEDDED_DE_INTEREST_FEDERAL),
    "S1312": (EMBEDDED_DE_WEST_INTEREST_STATES, EMBEDDED_DE_INTEREST_STATES),
    "S1313": (EMBEDDED_DE_WEST_INTEREST_LOCAL, EMBEDDED_DE_INTEREST_LOCAL),
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


def parse_bundesbank_csv(text: str, units: tuple[str, ...] = _BUNDESBANK_PERCENT, multiplier: str = "one") -> pd.Series:
    """Parse one series of a Bundesbank CSV download; a date-indexed float series in one of ``units`` (percent), named by its key.

    The layout: a header line ``"",KEY,KEY_FLAGS``, lines of metadata
    (title, unit, multiplier, last update), then ``date,value,flag`` rows;
    "." or "-" where there is no value (weekends in a daily series). A month
    ``1972-09`` is dated by its last day (the term structure's monthly
    values are end-of-month values). The unit must be one of ``units`` and the
    multiplier ``multiplier`` (one; millions for the balance of payments,
    whose figures are returned as written, in millions); anything else, and an
    answer with no dated rows (the old download's "Die Zeitreihe ... ist nicht
    gültig"), raises.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or len(rows[0]) < 2 or not rows[0][1].strip():
        raise ValueError(f"expected a Bundesbank series CSV, got {text[:80]!r}")
    key = rows[0][1].strip()
    meta = {row[0].strip().lower(): row[1].strip() for row in rows[1:] if len(row) >= 2 and not _BUNDESBANK_DATE.match(row[0].strip())}
    unit = meta.get("bbk_unit_eng", meta.get("unit", ""))
    if unit.lower() not in units:
        raise ValueError(f"Bundesbank {key}: expected {units[0]}, found unit {unit!r}")
    if meta.get("unit multiplier", "one").lower() != multiplier and key not in _BUNDESBANK_MULTIPLIER_MISWRITTEN:
        raise ValueError(f"Bundesbank {key}: expected the multiplier {multiplier}, found {meta.get('unit multiplier', 'one')!r}")
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
    values = parse_bundesbank_csv(
        de_get(url, params).text, _BUNDESBANK_UNITS.get((flow, key), _BUNDESBANK_PERCENT), _BUNDESBANK_MULTIPLIERS.get((flow, key), "one")
    )
    if values.name != f"{flow}.{key}":
        raise ValueError(f"the Bundesbank answered {values.name} for {flow}.{key}")
    return values


def bundesbank_series(flow: str, key: str, *, revised: bool = False, stopped: pd.Timestamp | None = None) -> pd.Series:
    """Return one series of the Bundesbank's database (``parse_bundesbank_csv``): its baked history, then its recent part from the Bundesbank.

    Batch 19.2 (``ratesplot.baked``): the history is in
    ``ratesplot/data/bbk/``, and only the last two months are asked for
    (market yields, not revised), or the last 24 if the series is revised
    (``revised``: a seasonally adjusted index, batch 13.4), from the period
    holding that date on; a series not baked is asked for whole. If the Bundesbank fails,
    the baked history alone, to its last value, with a warning; but a bot
    check is raised (``BotCheck``), for the caller to name once. Measured
    2026-10-22: the bake joined to its recent part is the Bundesbank's whole
    answer, value for value. A series ``stopped`` (a bond redeemed, batch
    13.3) is its bake alone, as ``baked.with_recent_part`` says.
    """
    return with_recent_part(
        BUNDESBANK_BAKED_SOURCE,
        f"{flow}.{key}",
        f"Bundesbank {flow}.{key}",
        lambda start: bundesbank_download(flow, key, start),
        RECENT_PART_REVISED if revised else RECENT_PART_UNREVISED,
        passes=(BotCheck,),
        stopped=stopped,
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


def ecb_series(flow: str, key: str, unit: str, *, revised: bool, stopped: pd.Timestamp | None = None) -> pd.Series:
    """Return one ECB Data Portal series (``parse_ecb_csv``): its baked history, then its recent part from the ECB.

    Batch 19.2 (``ratesplot.baked``): the history is in
    ``ratesplot/data/ecb/``, and only the last two months are asked for, or
    the last 24 if the ECB revises the series (``revised``: the debt, the
    mortgage rates; each caller says which), from the period holding that
    date on; a series not yet baked is asked for whole. A series that has
    stopped (``stopped``, its last value's date, declared by the caller:
    batch 19.3) is its bake alone, with no request (``baked.with_recent_part``).
    If the ECB fails,
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
        stopped=stopped,
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
        elif term in terms and column in DE_REAL_TERMS:
            earliest[f"{column} Yield (between the inflation-linked bonds)"] = DE_REAL_EARLIEST[column]
    return {**earliest, **DE_SERIES_EARLIEST}


def _term_structure(column: str, frequency: str) -> pd.Series:
    """Return one term of the Bundesbank's Svensson term structure, daily ("D") or end-of-month ("M"): its bake and recent part."""
    return bundesbank_series(BUNDESBANK_TERM_STRUCTURE_FLOW, term_structure_key(column, frequency))


def _baked_term(column: str, frequency: str) -> pd.Series:
    """Return one term's series from its bake alone, without asking the Bundesbank; no values if it has no bake."""
    series = read_series(BUNDESBANK_BAKED_SOURCE, f"{BUNDESBANK_TERM_STRUCTURE_FLOW}.{term_structure_key(column, frequency)}")
    return _NO_VALUES if series is None else series


def linked_bond_key(isin: str) -> str:
    """The key of one inflation-linked Federal bond's real yield in flow ``DE_LINKED_BOND_FLOW``."""
    return _LINKED_BOND_KEY.format(security_class=DE_LINKED_BONDS[isin].security_class, isin=isin)


def real_yield_at(years: float, bonds: Mapping[str, pd.Series]) -> pd.Series:
    """Return the real yield at a constant ``years`` to redemption, day by day, between the inflation-linked bonds either side of it.

    In a straight line by years left, between the nearest bond at or under
    ``years`` and the nearest at or over it, each with at least
    ``_LINKED_BOND_MIN_YEARS`` left (Terry, 2026-11-04, decision 108): the
    Bundesbank publishes no real curve, and the other nations' terms are at a
    constant maturity. A bond's yield is carried over a holiday as a nominal
    yield's is. A day without a bond on either side has no value, so the term
    begins when two bonds first span it and ends when they no longer do.
    ``bonds``: each bond's real yield, by ISIN (``DE_LINKED_BONDS``).
    """
    table = pd.DataFrame(dict(bonds)).sort_index().ffill(limit=_DAILY_FILL_LIMIT)
    rows = np.arange(len(table))
    left = np.column_stack([(DE_LINKED_BONDS[isin].redeemed - table.index).days / _DAYS_IN_A_YEAR for isin in table.columns])
    values = table.to_numpy(dtype=float)
    usable = ~np.isnan(values) & (left >= _LINKED_BOND_MIN_YEARS)
    under = np.where(usable & (left <= years), left, -np.inf)
    over = np.where(usable & (left >= years), left, np.inf)
    below, above = under.argmax(axis=1), over.argmin(axis=1)
    spanned = np.isfinite(under[rows, below]) & np.isfinite(over[rows, above])
    rows, below, above = rows[spanned], below[spanned], above[spanned]
    low, high = left[rows, below], left[rows, above]
    # A bond exactly at the term is both of them, its own yield.
    share = np.divide(years - low, high - low, out=np.zeros_like(low), where=high > low)
    result = values[rows, below] + (values[rows, above] - values[rows, below]) * share
    return pd.Series(result, index=table.index[spanned], name=DATE_COLUMN).rename(None)


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
    every later one drawn from its bake. A real yield (batch 13.3) is worked
    out between the inflation-linked bonds (``real_yield_at``), daily, each
    bond read as a term's parts are.
    """
    chosen = [column for column in config.fetched_yield_columns if column in DE_YIELD_SERIES or column in DE_REAL_TERMS]
    absent = [column for column in config.yield_columns if column not in DE_YIELD_SERIES and column not in DE_REAL_TERMS]
    if absent and len(absent) < len(config.yield_columns):  # none left: plotting._warn_no_yields
        print(f"  Note: no German {', '.join(absent)} yield; the German chart is drawn without it.")
    if not chosen:
        return pd.DataFrame()

    columns: dict[str, pd.Series] = {}
    history_through: dict[str, pd.Timestamp] = {}
    bot_check: BotCheck | None = None  # the Bundesbank sent one: no more requests
    bake_ends: list[pd.Timestamp] = []  # after it, the last date of each bake drawn
    for column in (column for column in chosen if column in DE_YIELD_SERIES):
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

    real = [column for column in chosen if column in DE_REAL_TERMS]
    if real:
        bonds: dict[str, pd.Series] = {}
        for isin, bond in DE_LINKED_BONDS.items():
            key = linked_bond_key(isin)
            if bot_check is None:
                try:
                    bonds[isin] = bundesbank_series(DE_LINKED_BOND_FLOW, key, stopped=bond.last_value)
                except BotCheck as exc:
                    bot_check = exc
                except Exception as exc:
                    print(f"  Warning: Bundesbank inflation-linked bond {isin} unavailable ({exc}); the real yields drawn without it.")
            if bot_check is not None:
                baked = read_series(BUNDESBANK_BAKED_SOURCE, f"{DE_LINKED_BOND_FLOW}.{key}")
                if baked is not None:
                    bonds[isin] = baked
                    bake_ends.append(baked.index[-1])
        if bonds:
            for column in real:
                values = real_yield_at(DE_REAL_TERMS[column], bonds)
                if not values.empty:
                    columns[column] = values.rename(column)

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
    """Return general government gross debt: West Germany's until the ECB's year ends begin (1991-12-31), and those until Eurostat's quarters begin, then the quarters.

    If Eurostat fails, the older figures alone, with a warning; if the ECB does, the
    quarters alone (from 2000), with a warning: West Germany's would be drawn straight
    across to them.
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
    if annual is not None:
        joined = _with_older_debt(_debt_in_euros(EMBEDDED_DE_DEBT_TOTAL), joined)
    return joined.rename(DE_DEBT_COLUMN).to_frame() if joined is not None else None


def _debt_in_euros(rows: list[tuple[str, float]]) -> pd.Series:
    """Return a baked list in millions of euros as euros, on its dates."""
    return embedded_frame(rows, DE_DEBT_COLUMN)[DE_DEBT_COLUMN] * MILLION


def _with_older_debt(older: pd.Series, live: pd.Series) -> pd.Series:
    """Return the Federal Statistical Office's debt until ``live`` begins, raised to ``live``'s level, then ``live``.

    ``older``'s last figure is of the year ``live`` first reaches, on the same
    territory, so the ratio of the two is a difference of definition alone: the
    Office counts debt to the non-public sector, the ECB and Eurostat the Maastricht
    measure. The older years reach it by the rule every other archive joins by
    (``joins.splice_archived_series``), the ratio at that year and a ramp over the five
    before it, so the rise into that year stays the Office's own. Changes of
    territory (1952, 1960, 1991) are left as the steps they are.
    """
    return splice_archived_series(
        older.to_frame(DE_DEBT_COLUMN),
        live.to_frame(DE_DEBT_COLUMN),
        DE_DEBT_COLUMN,
        annual_historical=True,
        calibration_end_year=_DE_DEBT_RATIO_UNTIL_YEAR,
    )[DE_DEBT_COLUMN]


def _debt_of_level(sectors: tuple[str, ...]) -> pd.Series:
    """Return the gross debt of these subsectors together: each the Federal Statistical Office's from 1950, raised to Eurostat's level (``_with_older_debt``), until its quarters begin in 2000.

    Each joined on its own, so "n" is exactly the Länder and local government added up.
    """
    parts = [_with_older_debt(_debt_in_euros(_DE_DEBT_OF_SECTOR[sector]), _quarterly_debt((sector,))) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


def west_german_debt_population() -> pd.Series:
    """Return the population West Germany's debt, and each level's, is divided by where the population drawn does not serve, in persons, each held until the next; a date with none: the population drawn from there.

    Two spans, as West Germany's GDP has (``west_german_gdp_population``). To 1959 the
    debt over the Office's own figure per person, which come back as published. They
    use the whole territory's population while the debt leaves out West Berlin until
    1952 and the Saarland until 1960, the Office's choice and no step at either; and the
    first figure, 1950-03-31, is before the first population drawn, 1950-07-01. The
    levels are over the same people, so they add up: the Office's own column for the
    Gemeinden is over fewer people (105.84 million over 2.29854 euros a head is 46.05
    million in 1950, against 50.34 for the total), presumably those outside the city
    states, which the table does not say. Through 1990 and 1991 the
    population drawn runs up to all of Germany's while the debt is West Germany's: the
    same population as West Germany's GDP. All of Germany's from 1991-12-31: the
    population drawn.
    """
    each = embedded_frame(EMBEDDED_DE_DEBT_PER_PERSON, DE_DEBT_COLUMN)[DE_DEBT_COLUMN]
    published = _debt_in_euros(EMBEDDED_DE_DEBT_TOTAL).loc[each.index] / each
    return pd.concat([published, west_german_gdp_population().loc[_DE_GDP_WHOLE_TERRITORY_FROM:]]).rename(POPULATION_COLUMN)


def payments_population(population: pd.Series) -> pd.Series:
    """Return the population the balance of payments' twelve-month sums are divided by while they cover other people than the population drawn: each sum over the mean of its twelve months' populations, in persons; from the first sum of all of Germany's months alone, the population drawn.

    The Bundesbank's months are West Germany's to 1990-06 and all of Germany's from
    1990-07 (``DE_PAYMENTS_UNIFIED_FROM``), so the sums ending 1990-07 to 1991-05
    hold some of each, while ``population`` (the population drawn) runs from West
    Germany's count on 1990-01-01 to all of Germany's on 1991-01-01, half a year ahead
    of them: over it the second half of 1990 would read about 12 % low. A month counts
    West Germany's people to 1990-06 (its annual averages, log-linear between their
    middles, as for its GDP: ``west_german_gdp_population``) and all of Germany's from
    1990-07 (``population``, log-linear between its figures, its first count of all of
    Germany, 1991-01-01, held back over 1990's last six months). So the sums ending
    1990-01 to 1990-06, West Germany's alone, are over its own people where the
    population drawn has begun to rise; from 1991-06-30 the population drawn.
    """
    # The months of every sum from the first the population drawn has begun to rise on
    # (1990-01-31) to the last holding a month of West Germany's (1991-05-31).
    first_sum = _DE_POPULATION_STEP_REACHES_FROM + pd.offsets.MonthEnd(0)
    months = pd.date_range(first_sum - pd.DateOffset(months=11), DE_PAYMENTS_UNIFIED_FROM + pd.DateOffset(months=11), freq="ME")
    west_averages = embedded_frame(EMBEDDED_DE_WEST_POPULATION_AT_UNIFICATION, POPULATION_COLUMN)[POPULATION_COLUMN] * THOUSAND
    known = population.dropna().sort_index()
    # All of Germany's population on each month's last day, its first count held back over 1990.
    unified_dates = pd.DatetimeIndex(np.maximum(months.as_unit("ns").asi8, _DE_POPULATION_UNIFIED_FROM.as_unit("ns").value))
    unified = np.exp(np.interp(unified_dates.asi8, known.index.as_unit("ns").asi8, np.log(known.to_numpy(dtype=float))))
    west = np.exp(np.interp(months.as_unit("ns").asi8, west_averages.index.as_unit("ns").asi8, np.log(west_averages.to_numpy(dtype=float))))
    each_month = pd.Series(np.where(months < DE_PAYMENTS_UNIFIED_FROM, west, unified), index=months)
    means = each_month.rolling(12, min_periods=12).mean().dropna()
    drawn = pd.Series(np.nan, index=pd.DatetimeIndex([means.index[-1] + pd.offsets.MonthEnd(1)]))
    return pd.concat([means, drawn]).rename(POPULATION_COLUMN)


def west_german_own_populations(population: pd.Series | None = None) -> dict[str, pd.Series]:
    """Return each column's own population for -p (``measures.per_person``): West Germany's GDP's, and its debt's and interest's, in total and for every level; with ``population`` (the population drawn) the balance of payments' too (``payments_population``).

    The interest's is GDP's (``west_german_gdp_population``): to 1959 the total's
    territory is the narrow one GDP's population there counts (without the Saarland and
    West Berlin; the levels begin in 1970), and West Germany's 1990 is over West Germany's people
    on its own date, where the population drawn has run up towards all of Germany's
    (about 20 % too many by the end of 1990); all of Germany's from 1991 over the
    population drawn.
    """
    debt = west_german_debt_population()
    gdp = west_german_gdp_population()
    own = {
        GDP_COLUMN: gdp,
        DE_DEBT_COLUMN: debt,
        DE_INTEREST_COLUMN: gdp,
        **{component_column("debt", letter): debt for letter in COMPONENT_LETTERS},
        **{component_column("interest", letter): gdp for letter in COMPONENT_LETTERS},
    }
    if population is not None and population.notna().any():
        payments = payments_population(population)
        own.update({PAYMENTS_CREDITS_COLUMN: payments, PAYMENTS_DEBITS_COLUMN: payments})
    return own


def _in_euros(rows: list[tuple[str, float]]) -> pd.Series:
    """Return a baked list in billions of euros as euros, on its dates."""
    return embedded_frame(rows, GDP_COLUMN)[GDP_COLUMN] * BILLION


def west_german_gdp() -> pd.Series:
    """Return West Germany's trailing-twelve-month GDP to 1991, in euros (batch 16): each year's end from 1950, then four-quarter sums from 1970-12-31.

    Three spans the Federal Statistical Office says are not fully comparable.
    From 1960 the Saarland and West Berlin are in, a change of territory: a step,
    kept (1959's figure leaves them out, 1960's has them, 6.0 % of it). At 1970 the
    revision of 2005 raises the level by 4.4 %, no change of territory: the older
    years reach the revised sum by the rule every other archive joins by
    (``joins.splice_archived_series``), the ratio at 1970 and a ramp over 1965 to
    1969, so 1970's growth is the old basis's own.
    """
    whole = splice_archived_series(
        _in_euros(EMBEDDED_DE_WEST_GDP_OLD_BASIS).to_frame(GDP_COLUMN),
        ttm_sum(_in_euros(EMBEDDED_DE_WEST_GDP_QUARTERS)).to_frame(GDP_COLUMN),
        GDP_COLUMN,
        annual_historical=True,
    )[GDP_COLUMN]
    return _before(_in_euros(EMBEDDED_DE_WEST_GDP_NARROW), whole)


def west_german_gdp_population() -> pd.Series:
    """Return the population West Germany's GDP is divided by where the population drawn covers another territory, in persons, each held until the next; a date with none: the population drawn from there.

    Two spans. To 1959 the GDP leaves out the Saarland and West Berlin and the
    population drawn has them (``west_german_population``), which would read about
    6 % low and step up at 1960: GDP over its published figure per person, each
    dated by 31 December, so those figures come back as published. Through 1990 and
    1991 the population drawn runs from West Germany's count on 1990-01-01 to all of
    Germany's on 1991-01-01, and stays there, while the GDP is West Germany's to
    1991-09-30, which would read up to about 20 % low: West Germany's annual averages,
    log-linear between their middles, 1991's held after its own, on each date the GDP
    is observed.
    """
    each = embedded_frame(EMBEDDED_DE_WEST_GDP_PER_PERSON, GDP_COLUMN)[GDP_COLUMN]
    narrow = _in_euros(EMBEDDED_DE_WEST_GDP_NARROW) / each
    gdp_dates = west_german_gdp().index
    dates = gdp_dates[(gdp_dates > _DE_POPULATION_STEP_REACHES_FROM) & (gdp_dates < _DE_GDP_UNIFIED_FROM)].insert(0, _DE_POPULATION_STEP_REACHES_FROM)
    averages = embedded_frame(EMBEDDED_DE_WEST_POPULATION_AT_UNIFICATION, POPULATION_COLUMN)[POPULATION_COLUMN] * THOUSAND
    west = pd.Series(np.exp(np.interp(dates.as_unit("ns").asi8, averages.index.as_unit("ns").asi8, np.log(averages.to_numpy(dtype=float)))), index=dates)
    drawn = pd.Series(np.nan, index=pd.DatetimeIndex([_DE_GDP_WHOLE_TERRITORY_FROM, _DE_GDP_UNIFIED_FROM]))
    return pd.concat([narrow, west, drawn]).sort_index().rename(POPULATION_COLUMN)


@downloads_of("Eurostat GDP")
def fetch_de_gdp(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month nominal GDP: West Germany's (``west_german_gdp``) until four-quarter sums of Eurostat's quarters begin (1991-12-31), then those.

    If Eurostat fails, West Germany's alone, with a warning; under -r None, with a
    warning, since all of Germany's debt and interest would be divided by West
    Germany's GDP and their ratio then held to the chart's end.
    """
    if not config.needs_gdp:
        return None
    west = west_german_gdp()
    try:
        unified = ttm_sum(eurostat_series("namq_10_gdp"))
    except Exception as exc:
        if config.relative:
            print(f"  Warning: Eurostat German GDP unavailable ({exc}); not drawn.")
            return None
        print(f"  Warning: Eurostat German GDP unavailable ({exc}); West Germany's alone, to {west.index[-1]:%Y-%m-%d}.")
        return west.rename(GDP_COLUMN).to_frame()
    return _before(west, unified).rename(GDP_COLUMN).to_frame()


def _interest_in_euros(rows: list[tuple[str, float]]) -> pd.Series:
    """Return a baked list in billions of euros as euros, on its dates."""
    return embedded_frame(rows, DE_INTEREST_COLUMN)[DE_INTEREST_COLUMN] * BILLION


def west_german_interest_before_1970() -> pd.Series:
    """Return West Germany's interest on public debt, 1950 to 1970, general government's as a whole, in euros at the mark's fixed rate, each year at its end; its 1970 only for the ratio to Reihe S.29's.

    The Office's Fachserie 18 Reihe S.7 (1985), typed from its table (``bake``): without
    the Saarland and West Berlin to 1959, with them from 1960, a step of 3.8 % there
    (2,110 to 2,190 million DM in 1960), kept as GDP's and debt's are.
    """
    rows = embedded_frame(EMBEDDED_DE_WEST_INTEREST_BEFORE_1970, DE_INTEREST_COLUMN)[DE_INTEREST_COLUMN]
    return rows * MILLION / DEM_PER_EUR


def _older_interest(sector: str) -> pd.Series:
    """Return the Federal Statistical Office's interest paid by a Eurostat sector (``_DE_INTEREST_OF_SECTOR``), in euros, each year at its end: West Germany's from 1970 (the total from 1950), all of Germany's from 1991.

    Laid end to end, unification a step at 1991 (34.35 billion in 1990, West Germany,
    to 42.65 in 1991, all of Germany, the total), as GDP's and debt's are: West
    Germany's own 1991 is on the revision of 2005, all of Germany's on the current
    basis, so no year gives a ratio that is not also unification. All of Germany's
    years are the Office's current figures, which from 1995 (the total) and 2002 (each
    level's quarters) are Eurostat's, value for value (measured 2026-11-10, Eurostat's
    in national currency): the live series follow on with no step and nothing scaled.
    The total's years before 1970 (``west_german_interest_before_1970``, an older
    edition) are a revision apart, not a change of territory, so they reach Reihe
    S.29's level as GDP's older basis does (decision 118, ``joins.splice_archived_series``,
    at Terry's word for 16.7): the ratio at 1970, 6,513 over 6,550 million DM (0.9943),
    by a geometric ramp over 1965 to 1969, so 1969 is lowered 0.57 % and 1970's growth is
    the older edition's own, 12.2 %; 1965 and before as published. Before 1970 no level apart.
    """
    west, unified = _DE_INTEREST_OF_SECTOR[sector]
    older = _before(_interest_in_euros(west), _interest_in_euros(unified))
    if sector != GENERAL_GOVERNMENT:
        return older
    return splice_archived_series(
        west_german_interest_before_1970().to_frame(DE_INTEREST_COLUMN),
        older.to_frame(DE_INTEREST_COLUMN),
        DE_INTEREST_COLUMN,
        annual_historical=True,
    )[DE_INTEREST_COLUMN]


@downloads_of("Eurostat interest outlays")
def fetch_de_interest(config: PlotConfig) -> pd.DataFrame | None:
    """Return trailing-twelve-month general government interest payable: the Office's years from 1950 (``_older_interest``), Eurostat's annual figures (1995-), then four-quarter sums (2002-).

    Either of Eurostat's alone, with a warning, if the other fails; None if both
    do. The Office's years only with Eurostat's annual figures: with the quarters
    alone they would be drawn straight across 1995 to 2002.
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
    if annual is not None:
        joined = _before(_older_interest(GENERAL_GOVERNMENT), joined)
    return joined.rename(DE_INTEREST_COLUMN).to_frame() if joined is not None else None


def _interest_of_level(sectors: tuple[str, ...]) -> pd.Series:
    """Return the interest paid by these subsectors together, summed over four quarters: each the Office's years from 1970 (``_older_interest``) until Eurostat's quarters' first sum (2002), then those.

    Each joined on its own, so "n" is exactly the Länder and local government added up.
    """
    parts = [_before(_older_interest(sector), _ttm_interest((sector,))) for sector in sectors]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna()


@downloads_of("Eurostat debt and interest by level of government")
def fetch_de_components(config: PlotConfig) -> pd.DataFrame | None:
    """Return debt and TTM interest by level of government (--debt:LETTERS): federal, Länder, local, Länder and local.

    Eurostat's quarters (debt from 2000, interest from 2002): its annual tables
    have the levels only lately. Before them the Federal Statistical Office's
    years, debt from 1950 (``_debt_of_level``) and interest from 1970
    (``_interest_of_level``). A level whose Eurostat series fails is left out,
    with a warning.
    """
    columns: list[pd.Series] = []
    for letter in COMPONENT_LETTERS:
        if letter not in config.components:
            continue
        sectors = _LEVEL_SECTORS[letter]
        for kind, include, fetch in (("debt", config.include_debt, _debt_of_level), ("interest", config.include_interest, _interest_of_level)):
            if not include:
                continue
            try:
                values = fetch(sectors)
            except Exception as exc:
                print(f"  Warning: Eurostat German {kind}, level {letter} ({'+'.join(sectors)}) unavailable ({exc}); not drawn.")
                continue
            columns.append(values.rename(component_column(kind, letter)))
    return pd.concat(columns, axis=1).sort_index() if columns else None


def _month_ends(rows: list[tuple[str, float]]) -> pd.Series:
    """Return a baked monthly list, each month dated by its first day there, dated by its last day, as the Bundesbank's months are."""
    months = pd.DatetimeIndex([date for date, _value in rows], name=DATE_COLUMN).to_period("M")
    return pd.Series([value for _date, value in rows], index=months.end_time.normalize(), dtype=float)


def with_west_germany(unified: pd.Series) -> pd.Series:
    """Return Germany's consumer price index carried back to 1948-06 by West Germany's, on its base; from its own first month, unchanged.

    Three indexes, each scaled to the next at the month where the next begins,
    so each keeps its own rises and no level is lost: four-person households on
    a middle income to 1961-12, all private households to 1990-12, then the
    index for all of Germany from 1991-01. Unlike the amounts, an index has no
    step at unification: the East's prices enter as a share of a rise, not as
    a jump in a level. The rises of the 12 months of 1991 are the months' index
    for all of Germany over West Germany's a year before. If ``unified`` does not
    begin where the older index is kept, it is returned alone, with a warning.
    """
    all_households = _month_ends(EMBEDDED_DE_WEST_CPI_ALL_HOUSEHOLDS)
    four_person = _month_ends(EMBEDDED_DE_WEST_CPI_FOUR_PERSON)
    join = unified.index[0]
    if join not in all_households.index:
        print(f"  Warning: Germany's consumer prices begin {join:%Y-%m-%d}, where West Germany's are not kept; drawn without them.")
        return unified
    west = all_households * (unified.iloc[0] / all_households.loc[join])
    older = four_person * (west.iloc[0] / four_person.loc[west.index[0]])
    return pd.concat([older.loc[older.index < west.index[0]], west.loc[west.index < join], unified]).rename(unified.name)


def fetch_de_consumer_prices(*, adjusted: bool = False) -> pd.Series:
    """Return Germany's consumer price index (``DE_CPI_SERIES``, 2020 = 100), each month dated by its last day: its baked history and recent part, carried back by West Germany's (``with_west_germany``, batch 16).

    ``adjusted``: the seasonally adjusted index instead (``DE_CPI_SA_SERIES``,
    batch 13.4, from 1991-01; West Germany's index was published unadjusted),
    whose recent part is a revised series'. If the Bundesbank fails, the bake
    alone, with a warning (``bundesbank_series``); after a bot check, the bake
    alone too, with a warning that names it, as the yields' does. Raises if
    there is neither.
    """
    flow, key = DE_CPI_SA_SERIES if adjusted else DE_CPI_SERIES
    try:
        index = bundesbank_series(flow, key, revised=adjusted)
    except BotCheck as exc:
        index = read_series(BUNDESBANK_BAKED_SOURCE, f"{flow}.{key}")
        if index is None or index.empty:
            raise
        print(f"  Warning: the Bundesbank ({exc.host}) sent a bot check instead of data; a VPN can cause this. "
              f"Germany's consumer prices drawn from their baked history, to {index.index[-1]:%Y-%m-%d}.")
    return index if adjusted else with_west_germany(index)


def west_german_population() -> pd.Series:
    """Return West Germany's population 1950 to 1959, in persons: the Bundesbank's annual averages, each dated by 1 July (batch 16).

    On the whole territory, the Saarland and West Berlin included, as Eurostat's
    counts from 1960 are, and within about 0.2 % of the first of them, so the two
    are laid end to end unscaled, as Canada's two estimates are.
    """
    dates = pd.DatetimeIndex([date for date, _value in EMBEDDED_DE_WEST_POPULATION], name=DATE_COLUMN)
    return pd.Series([value * THOUSAND for _date, value in EMBEDDED_DE_WEST_POPULATION], index=dates, dtype=float)


@downloads_of("Eurostat population")
def fetch_de_population() -> pd.Series | None:
    """Return Germany's population for -p: West Germany's annual averages (from 1950), then the 1 January counts (from 1960; West Germany to 1990), until the quarters begin (1991).

    The averages are dated by 1 July, the quarters (thousands) by their middles,
    the counts by 1 January. Either source of Eurostat's alone, with a warning, if
    the other fails; the averages only with the counts, or a gap of 30 years.
    """
    try:
        annual = eurostat_series("demo_pjan")
        annual = annual.set_axis(pd.DatetimeIndex(annual.index.to_period("Y").start_time, name=DATE_COLUMN))
        annual = _before(west_german_population(), annual)
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
