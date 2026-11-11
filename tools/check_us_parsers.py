#!/usr/bin/env python3
"""Check the U.S. Census bake's readers (plan item 23.3); offline, in seconds.

* the extract of the Census historical database
  (``tools/us_fixtures/census_hist_fin_debt.csv``, ``bake.parse_census_hist_fin_extract``):
  its fiscal years 1902 to 2008, each figure times a thousand equal to the
  module's (``EMBEDDED_US_DEBT_BY_LEVEL``) float for float, so the frozen part
  reproduces what the database gave; state plus local equal to the total; a
  damaged extract refused (a heading, a year twice or out of order, a figure
  below zero or not a number, a level with no figure); written and read back
  unchanged, a figure with a fraction included;
* the yearly estimates' fixed-width reader (``bake._parse_census_estimates``):
  the country's lines summed by level over items 44T, 49U and 64V, the
  states' lines and other items left out, a level without 49U refused.

The live check of the Census listing is ``tools/check_sources.py --only census``;
the bake itself, ``tools/bake_archives.py --only us``.

Usage (from the project root)::

    python tools/check_us_parsers.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import bake  # noqa: E402
from ratesplot.us_archive_data import EMBEDDED_US_DEBT_BY_LEVEL  # noqa: E402

RESULTS: list[bool] = []
HEADER = "fiscal year,state,local,state and local"


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    shown = f"  [{detail}]" if not condition or detail else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}")


def raises(call, *args) -> str | None:
    """The exception's type and message if ``call(*args)`` raises, else None."""
    try:
        call(*args)
    except Exception as exc:  # the checks want any refusal
        return f"{type(exc).__name__}: {exc}"
    return None


def check_extract() -> None:
    text = bake.US_CENSUS_HISTORY_EXTRACT.read_text(encoding="utf-8")
    thousands = bake.parse_census_hist_fin_extract(text)
    years = {key: sorted(by_year) for key, by_year in thousands.items()}
    check("extract: 71 fiscal years each level, 1902 to 2008",
          all(len(found) == 71 and found[0] == 1902 and found[-1] == 2008 for found in years.values()),
          {key: (len(found), found[0], found[-1]) for key, found in years.items()})
    levels = bake._census_history_levels(thousands, "the extract")
    for key in ("p", "m"):
        baked = {pd.Timestamp(date).year: value for date, value in EMBEDDED_US_DEBT_BY_LEVEL[key] if pd.Timestamp(date).year <= 2008}
        unequal = [year for year in baked if levels[key].get(year) != baked[year]]
        check(f"extract: level {key!r} through 2008, times a thousand, equal to the module's float for float ({len(baked)} years)",
              not unequal and set(baked) == set(levels[key].index), unequal[:5])
    check("extract: the module's 1902 state debt is the extract's 230,000 thousand", thousands["p"][1902] == 230_000)

    body = text.splitlines()
    first_row = next(index for index, line in enumerate(body) if line == HEADER) + 1
    damaged = {
        "a heading changed": [line.replace("state and local", "both") if line == HEADER else line for line in body],
        "a year twice": body[:first_row + 1] + [body[first_row]] + body[first_row + 1:],
        "years out of order": body[:first_row] + [body[first_row + 1], body[first_row]] + body[first_row + 2:],
        "a figure below zero": body[:first_row] + ["1902,-230000,1877000,2107000"] + body[first_row + 1:],
        "a word for a figure": body[:first_row] + ["1902,n/a,1877000,2107000"] + body[first_row + 1:],
        "a row of three cells": body[:first_row] + ["1902,230000,1877000"] + body[first_row + 1:],
        "a level with no figure": [HEADER, "1902,230000,,2107000"],
    }
    refused = {what: raises(bake.parse_census_hist_fin_extract, "\n".join(lines)) for what, lines in damaged.items()}
    check("extract: a damaged one refused (" + ", ".join(damaged) + ")", all(refused.values()),
          [what for what, message in refused.items() if not message])
    check("extract: a blank cell is a year that level lacks", bake.parse_census_hist_fin_extract(f"{HEADER}\n1902,1,,1\n1903,2,1,3")["m"] == {1903: 1.0})

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "extract.csv"
        bake._write_census_hist_fin_extract(thousands, b"zip bytes", path)
        again = bake.parse_census_hist_fin_extract(path.read_text(encoding="utf-8"))
        check("extract: written and read back, every figure equal", again == thousands)
        odd = {"p": {1902: 1234.5, 1903: 0.1 + 0.2}, "m": {1902: 7.0}, "sl": {1902: 1241.5}}
        bake._write_census_hist_fin_extract(odd, b"", path)
        check("extract: a figure with a fraction comes back as the same float", bake.parse_census_hist_fin_extract(path.read_text(encoding="utf-8")) == odd)
    check("extract: a level not adding up is refused (state + local against the total)",
          raises(bake._census_history_levels, {"p": {1902: 1.0}, "m": {1902: 1.0}, "sl": {1902: 3.0}}, "a test") is not None)


def estimates_line(state: str, level: str, item: str, thousands: int) -> str:
    """One line of a year's estimates by state and type of government: state (1-2), level (3), item (5-7), amount (9-20)."""
    return f"{state}{level}0{item} {thousands:>12d}  rest of the line"


def check_estimates() -> None:
    lines = [
        estimates_line("00", "1", "44T", 10), estimates_line("00", "1", "49U", 1000), estimates_line("00", "1", "64V", 100),
        estimates_line("00", "2", "49U", 400), estimates_line("00", "2", "64V", 40),
        estimates_line("00", "3", "49U", 600), estimates_line("00", "3", "64V", 60), estimates_line("00", "3", "44T", 10),
        estimates_line("01", "2", "49U", 99_999), estimates_line("00", "2", "19U", 99_999), "00 short",
    ]
    totals = bake._parse_census_estimates("\n".join(lines), 2099)
    check("estimates: the country's 44T + 49U + 64V by level, in dollars; states and other items left out",
          totals == {"sl": 1_110_000.0, "p": 440_000.0, "m": 670_000.0}, totals)
    without = [line for line in lines if not (line.startswith("003") and "49U" in line)]
    check("estimates: a level without 49U is refused", raises(bake._parse_census_estimates, "\n".join(without), 2099) is not None)


def main() -> int:
    for group in (check_extract, check_estimates):
        group()
    passed = sum(RESULTS)
    print(f"[us parsers] {passed} of {len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
