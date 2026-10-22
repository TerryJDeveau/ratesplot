#!/usr/bin/env python3
"""Bake the historical data into the code: the archive data modules' generated blocks, and the live sources' data files.

Downloads the terminated and historical sources (see ``ratesplot/bake.py``),
extracts the rows the charts need and writes them as Python literals between
the BEGIN/END markers of

* ``ratesplot/cdn_archive_data.py``: the Canadian history (StatCan archived
  tables, *Historical Statistics of Canada*, Bank of Canada term bands);
* ``ratesplot/us_archive_data.py``: U.S. state and local government debt apart
  (Census Bureau). Needs ``pyodbc`` and the Microsoft Access ODBC driver, to
  read the Census historical database, and ``xlrd`` for one old ``.xls``
  table (both ``pip install``-able; only this bake uses them);
* ``ratesplot/uk_archive_data.py``: the UK history (the Bank of England's
  "A millennium of macroeconomic data", no longer updated). Needs
  ``openpyxl``. ``--uk-workbook FILE`` reads a copy already downloaded
  instead of fetching the 27.5 MB workbook.
* ``ratesplot/de_archive_data.py``: Germany's 10-year before 1972 (the
  Bundesbank's frozen yield on public debt securities, from 1956), and the
  Bundesbank's discount rate 1948-1998 on the days it changed (batch 9.6).
  ``--de-csv FILE`` and ``--de-discount-csv FILE`` read the downloads
  already saved (tools/de_fixtures).
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
    python tools/bake_archives.py --only de --de-csv tools/de_fixtures/raw/bbk01_WU0004.csv --de-discount-csv tools/de_fixtures/raw/bbin1_BBKDIS.csv
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
    args = parser.parse_args(argv)
    all_baked = True
    # One pass, as a drawing: a source that does not answer is asked nothing more in it (batch 19.3).
    with http.drawing_downloads():
        for key, bake in BAKES.items():
            if args.only in (None, key):
                if key == "uk":
                    bake(workbook_path=args.uk_workbook)
                elif key == "de":
                    bake(saved_csv=args.de_csv, saved_discount_csv=args.de_discount_csv)
                else:
                    # The archives raise when they cannot be baked; a live source's
                    # history returns a SeriesBake per series, each written or not.
                    result = bake()
                    if isinstance(result, list):
                        all_baked &= all(item.written for item in result)
    return 0 if all_baked else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
