#!/usr/bin/env python3
"""Bake the historical data into the code: the archive data modules' generated blocks, and the live sources' data files.

Downloads the terminated and historical sources (see ``ratesplot/bake.py``),
extracts the rows the charts need and writes them as Python literals between
the BEGIN/END markers of

* ``ratesplot/cdn_archive_data.py``: the Canadian history (StatCan archived
  tables, *Historical Statistics of Canada* with the Canadian dollar's rate
  1913-1977, Bank of Canada term bands);
* ``ratesplot/us_archive_data.py``: U.S. state and local government debt apart
  (Census Bureau). Needs ``pyodbc`` and the Microsoft Access ODBC driver, to
  read the Census historical database, and ``xlrd`` for one old ``.xls``
  table (both ``pip install``-able; only this bake uses them);
* ``ratesplot/uk_archive_data.py``: the UK history (the Bank of England's
  "A millennium of macroeconomic data", no longer updated), its exchange
  rates of the pound among it (batch 18.4). Needs
  ``openpyxl``. ``--uk-workbook FILE`` reads a copy already downloaded
  instead of fetching the 27.5 MB workbook.
* ``ratesplot/de_archive_data.py``: Germany's 10-year before 1972 (the
  Bundesbank's frozen yield on public debt securities, from 1956), and the
  Bundesbank's discount rate 1948-1998 on the days it changed (batch 9.6), and
  West Germany's consumer prices from 1948 (the Federal Statistical Office's
  long series, batch 16; needs ``openpyxl``) and its population 1950 to 1959
  (the Bundesbank's long series, a PDF, batch 16; needs ``pdftotext`` unless its
  page's text is given) and the Bundesbank's older mortgage rates, 1982 to 2003
  (flow BBIB1, batch 16) and West Germany's GDP, 1950 to 1991 (the Federal
  Statistical Office's table 81000-117 and its revised quarters, batch 16; needs
  ``openpyxl``) and Germany's debt from 1950 and interest from 1950, its levels
  from 1970 (Fachserie 14 Reihe 5, Fachserie 18 Reihe S.7, S.29 and Reihe 1.4). ``--de-csv FILE``, ``--de-discount-csv FILE``,
  ``--de-cpi-workbook FILE``, ``--de-population-text FILE``,
  ``--de-mortgage-5y-csv FILE``, ``--de-mortgage-10y-csv FILE``,
  ``--de-gdp-annual-csv FILE``, ``--de-gdp-quarterly-csv FILE``, ``--de-debt-csv FILE``,
  ``--de-interest-west-csv FILE`` and ``--de-interest-csv FILE`` read the
  downloads, or the extracts of them, already saved (tools/de_fixtures). West
  Germany's interest of 1950 to 1969 (Fachserie 18 Reihe S.7, a PDF on a host that
  refuses scripts) is always read from its transcription,
  ``tools/de_fixtures/raw/destatis_fs18_s7_interest.csv``, typed from the page.
* ``ratesplot/data/boe/``: the Bank of England database's series, every value
  of each, one file per series (batch 19.2: the live sources' history, of
  which a drawing then asks only for the recent part; ``ratesplot/baked.py``).
  A series whose download fails, or lacks dates its file has, keeps its file
  as it was, and the run ends with exit code 1. What changed in each file is
  printed, each revised value with its size (the first 20 of a series).
* ``ratesplot/data/boc/``: the Bank of Canada's Valet series, in the same way
  (batch 19.2's second source).
* ``ratesplot/data/fred/``: FRED's series, in the same way (the third), with
  the dates FRED lists without a value kept as rows without one.
* ``ratesplot/data/ecb/``: the ECB Data Portal's series, in the same way (the
  fourth), each file named by the series' flow and key.
* ``ratesplot/data/eurostat/``: Eurostat's series, in the same way (the
  fifth), each dataset asked for once and each series read of it (a sector of
  the debt or the interest) a file, named by the dataset and the categories.
* ``ratesplot/data/ons/``: the ONS's time series, in the same way (the
  sixth), each file named by the series' CDID and holding the frequency the
  program reads of it (months or quarters).
* ``ratesplot/data/bbk/``: the Bundesbank's series, in the same way (the
  seventh): each term's end-of-month and daily term structure, each file
  named by the series' flow and key.
* ``ratesplot/data/statcan/``: Statistics Canada's live tables, in the same
  way (the eighth), each table's ZIP asked for once and each vector read of
  it a file, named by the vector.

Nothing is written for a country's archive module unless every one of its
sources is extracted and the new module compiles.

This is a maintenance step, not an option of the program (it was
``--bake-archives`` until 2026-09-27): run it when an extraction changes or a
source is added (the Census publishes a new fiscal year each summer), check
the charts, and commit the regenerated module with the change that needed it.
The live sources' history is re-baked daily (Terry, decision 49). Normal runs
only read the modules and the files.

Usage (from the project root)::

    python tools/bake_archives.py            # every nation, and boe, boc, fred, ecb, eurostat, ons, bbk and statcan
    python tools/bake_archives.py --only us  # or cdn, uk, de, boe, boc, fred, ecb, eurostat, ons, bbk, statcan
    python tools/bake_archives.py --only uk --uk-workbook a-millennium-of-macroeconomic-data-for-the-uk.xlsx
    python tools/bake_archives.py --only de --de-csv tools/de_fixtures/raw/bbk01_WU0004.csv --de-discount-csv tools/de_fixtures/raw/bbin1_BBKDIS.csv --de-cpi-workbook tools/de_fixtures/raw/destatis_vpi_lange_reihen.xlsx --de-population-text tools/de_fixtures/raw/bbk_lange_zeitreihen_V1.txt --de-mortgage-5y-csv tools/de_fixtures/raw/bbib1_HYP_F05J.csv --de-mortgage-10y-csv tools/de_fixtures/raw/bbib1_HYP_F10J.csv --de-gdp-annual-csv tools/de_fixtures/raw/destatis_81000_117_gdp.csv --de-gdp-quarterly-csv tools/de_fixtures/raw/destatis_fs18_s27_gdp_q.csv --de-debt-csv tools/de_fixtures/raw/destatis_fs14_r5_debt.csv --de-interest-west-csv tools/de_fixtures/raw/destatis_fs18_s29_interest.csv --de-interest-csv tools/de_fixtures/raw/destatis_fs18_r14_interest.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import http  # noqa: E402
from ratesplot.bake import (  # noqa: E402
    bake_bbk_history,
    bake_boc_history,
    bake_boe_history,
    bake_canadian_archives,
    bake_ecb_history,
    bake_eurostat_history,
    bake_fred_history,
    bake_german_archives,
    bake_ons_history,
    bake_statcan_history,
    bake_uk_archives,
    bake_us_archives,
)

BAKES = {
    "cdn": bake_canadian_archives,
    "us": bake_us_archives,
    "uk": bake_uk_archives,
    "de": bake_german_archives,
    "boe": bake_boe_history,
    "boc": bake_boc_history,
    "fred": bake_fred_history,
    "ecb": bake_ecb_history,
    "eurostat": bake_eurostat_history,
    "ons": bake_ons_history,
    "bbk": bake_bbk_history,
    "statcan": bake_statcan_history,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=sorted(BAKES), help="bake one nation's archives, or one live source's history (boe, boc, fred, ecb, eurostat, ons, bbk, statcan)")
    parser.add_argument("--uk-workbook", type=Path, help="the UK millennium workbook already on disk (not downloaded)")
    parser.add_argument("--de-csv", type=Path, help="the Bundesbank's WU0004 download already on disk (not downloaded)")
    parser.add_argument("--de-discount-csv", type=Path, help="the Bundesbank's discount rate download (BBIN1) already on disk")
    parser.add_argument("--de-cpi-workbook", type=Path, help="the Federal Statistical Office's long series of consumer prices already on disk")
    parser.add_argument("--de-population-text", type=Path, help="the text of the population's page of the Bundesbank's long series already on disk")
    parser.add_argument("--de-mortgage-5y-csv", type=Path, help="the Bundesbank's older 5-year mortgage rate (BBIB1) already on disk")
    parser.add_argument("--de-mortgage-10y-csv", type=Path, help="the Bundesbank's older 10-year mortgage rate (BBIB1) already on disk")
    parser.add_argument("--de-gdp-annual-csv", type=Path, help="the extract of West Germany's yearly GDP from table 81000-117 already on disk")
    parser.add_argument("--de-gdp-quarterly-csv", type=Path, help="the extract of West Germany's quarterly GDP, 1970 to 1991, already on disk")
    parser.add_argument("--de-debt-csv", type=Path, help="the extract of Germany's debt by level, Fachserie 14 Reihe 5, already on disk")
    parser.add_argument("--de-interest-west-csv", type=Path, help="the extract of West Germany's interest by level, Fachserie 18 Reihe S.29, already on disk")
    parser.add_argument("--de-interest-csv", type=Path, help="the extract of Germany's interest by level from 1991, Fachserie 18 Reihe 1.4, already on disk")
    args = parser.parse_args(argv)
    all_baked = True
    # One pass, as a drawing: a source that does not answer is asked nothing more in it (batch 19.3).
    with http.drawing_downloads():
        for key, bake in BAKES.items():
            if args.only in (None, key):
                if key == "uk":
                    bake(workbook_path=args.uk_workbook)
                elif key == "de":
                    bake(
                        saved_csv=args.de_csv,
                        saved_discount_csv=args.de_discount_csv,
                        saved_cpi_workbook=args.de_cpi_workbook,
                        saved_population_text=args.de_population_text,
                        saved_mortgage_csvs={"EMBEDDED_DE_MORTGAGE_5Y_HISTORY": args.de_mortgage_5y_csv, "EMBEDDED_DE_MORTGAGE_10Y_HISTORY": args.de_mortgage_10y_csv},
                        saved_gdp_annual_csv=args.de_gdp_annual_csv,
                        saved_gdp_quarterly_csv=args.de_gdp_quarterly_csv,
                        saved_debt_csv=args.de_debt_csv,
                        saved_interest_west_csv=args.de_interest_west_csv,
                        saved_interest_csv=args.de_interest_csv,
                    )
                else:
                    # The archives raise when they cannot be baked; a live source's
                    # history returns a SeriesBake per series, each written or not.
                    result = bake()
                    if isinstance(result, list):
                        all_baked &= all(item.written for item in result)
    return 0 if all_baked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
