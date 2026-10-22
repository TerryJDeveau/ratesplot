#!/usr/bin/env python3
"""Check the live sources' baked history (batch 19.2): its files, their reading, the join to the recent part, the re-bake's report.

Offline, in seconds:

* every file under ``ratesplot/data/`` reads (``baked.parse_series``): the
  bake's form, its dates in order and each once, every value a number;
* every Bank of England database series the program reads
  (``bake.boe_baked_codes``) has a file, and every file there is one of them;
* a series written by ``baked.write_series`` reads back float for float,
  and its text is the bake's form (comment, header, one row per value);
* ``baked.with_recent_part``, with made-up answers from the source: the bake,
  then the recent part from its first date (a value the source has revised
  there is the source's; the values before it that a source sends when it
  ignores the date asked for, left out); the source failing: the bake alone,
  with a warning naming the series and its last date; no bake: the whole
  series asked for, as before 19.2;
* the re-bake's report (``bake.bake_changes``): new values, each revised value
  with its size, dates within the bake that it lacked; a download that lacks
  dates the file has, refused.

The live checks: ``tools/check_sources.py`` draws through the bake and its
recent part; ``tools/check_drawn_values.py`` checks every drawn value against
the Bank of England's whole series; ``tools/check_uk_parsers.py`` the warning
when the database redirects.

Usage (from the project root)::

    python tools/check_baked.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot import bake, baked, uk_data  # noqa: E402
from ratesplot.config import DATE_COLUMN  # noqa: E402

RESULTS: list[bool] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    shown = f"  [{detail}]" if not condition or detail else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}")


def series(values: dict[str, float], code: str = "X") -> pd.Series:
    """A made-up series in the form the sources' readers return: floats, named, dated, oldest first."""
    dates = pd.DatetimeIndex(pd.to_datetime(list(values), format="%Y-%m-%d"), name=DATE_COLUMN)
    return pd.Series(list(values.values()), index=dates, dtype=float, name=code)


def check_files() -> None:
    files = sorted(baked.DATA_FOLDER.glob("*/*.csv"))
    problems = []
    for path in files:
        try:
            values = baked.parse_series(path.read_text(encoding="utf-8"), path.stem)
            if values.empty:
                problems.append(f"{path.name}: empty")
        except Exception as exc:
            problems.append(f"{path.name}: {exc}")
    check(f"every baked file reads in the bake's form ({len(files)} files)", bool(files) and not problems, problems)
    boe = {path.stem for path in (baked.DATA_FOLDER / uk_data.BOE_BAKED_SOURCE).glob("*.csv")}
    codes = set(bake.boe_baked_codes())
    check("every Bank of England series the program reads has a file, and every file is one of them",
          boe == codes, {"missing": sorted(codes - boe), "not read": sorted(boe - codes)})


def check_written(folder: Path) -> None:
    # Values whose shortest text has many digits, an integer, a tiny and a negative value.
    values = series({"2020-01-01": 5.3714, "2020-01-02": 0.1 + 0.2, "2020-02-01": 4.0, "2020-03-31": 1e-05, "2021-01-01": -0.25})
    path = folder / "written" / "X.csv"
    baked.write_series(path, values, "a made-up series\nits second line")
    text = path.read_text(encoding="utf-8")
    back = baked.parse_series(text, "X")
    check("a written series reads back float for float, its dates the same",
          back.index.equals(values.index) and (back.to_numpy() == values.to_numpy()).all(), back.to_dict())
    lines = text.splitlines()
    check("its text: the comment, the header, a row per value as Python writes the float",
          lines == ["# a made-up series", "# its second line", "date,value", "2020-01-01,5.3714", "2020-01-02,0.30000000000000004",
                    "2020-02-01,4.0", "2020-03-31,1e-05", "2021-01-01,-0.25"], lines)
    for bad, why in (
        ("date,value\n2020-01-02,1.0\n2020-01-01,2.0\n", "dates out of order"),
        ("date,value\n2020-01-01,1.0\n2020-01-01,2.0\n", "a date twice"),
        ("date,value\n2020-01-01,\n", "a row without a value"),
        ("date,price\n2020-01-01,1.0\n", "another header"),
        ("date,value\n2020-01-01,n/a\n", "a value that is not a number"),
    ):
        try:
            baked.parse_series(bad, "X")
            refused = False
        except Exception:
            refused = True
        check(f"a file with {why} is refused", refused)


def check_join(folder: Path) -> None:
    real_folder = baked.DATA_FOLDER
    baked.DATA_FOLDER = folder
    baked.forget_read_files()
    try:
        history = series({"2026-01-30": 1.0, "2026-06-30": 2.0, "2026-07-31": 3.0, "2026-08-31": 4.0, "2026-09-30": 5.0})
        baked.write_series(folder / "made-up" / "X.csv", history, "made up")
        asked: list[pd.Timestamp | None] = []

        def answering(start: pd.Timestamp | None) -> pd.Series:
            # Sends more than asked for (from 2026-06-30), and has revised 2026-08-31 and added 2026-10-31.
            asked.append(start)
            return series({"2026-06-30": 2.0, "2026-07-31": 3.0, "2026-08-31": 4.5, "2026-09-30": 5.0, "2026-10-31": 6.0})

        joined = baked.with_recent_part("made-up", "X", "made-up X", answering, pd.DateOffset(months=2))
        check("the recent part asked for from two months before the bake's last date", asked == [pd.Timestamp("2026-07-30")], asked)
        expected = series({"2026-01-30": 1.0, "2026-06-30": 2.0, "2026-07-31": 3.0, "2026-08-31": 4.5, "2026-09-30": 5.0,
                           "2026-10-31": 6.0})
        check("the bake before it, the source's values from it on (a revision there taken, a value before it left out)",
              joined.equals(expected) and joined.name == "X" and joined.index.name == DATE_COLUMN, joined.to_dict())

        def failing(start: pd.Timestamp | None) -> pd.Series:
            raise ConnectionError("refused by check_baked")

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            alone = baked.with_recent_part("made-up", "X", "made-up X", failing, pd.DateOffset(months=2))
        said = printed.getvalue().strip()
        check("the source failing: the bake alone", alone.equals(history), alone.to_dict())
        check("... with a warning naming the series, why, and the bake's last date",
              said == "Warning: made-up X: its recent values unavailable (refused by check_baked); drawn from its baked "
                      "history, to 2026-09-30.", said)
        alone.iloc[0] = 99.0
        check("... a copy: changing it leaves the bake as read", baked.read_series("made-up", "X").iloc[0] == 1.0)

        asked.clear()
        whole = baked.with_recent_part("made-up", "Y", "made-up Y", answering, pd.DateOffset(months=2))
        check("no bake: the whole series asked for, as before 19.2", asked == [None] and len(whole) == 5, asked)
    finally:
        baked.DATA_FOLDER = real_folder
        baked.forget_read_files()


def check_report() -> None:
    old = series({"2026-01-01": 1.0, "2026-02-01": 2.0, "2026-03-01": 3.0})
    changes = bake.bake_changes(None, old)
    check("report: a new file", changes.lines == ["new file, 3 values"] and changes.new_file and not changes.history_changed,
          changes.lines)
    changes = bake.bake_changes(old, old.copy())
    check("report: nothing new", changes.lines == ["0 new, 0 revised"] and not changes.history_changed and not len(changes.added),
          changes.lines)
    new = series({"2026-01-01": 1.0, "2026-01-15": 1.5, "2026-02-01": 2.25, "2026-03-01": 3.0, "2026-04-01": 4.0, "2026-05-01": 5.0})
    changes = bake.bake_changes(old, new)
    check("report: each revised value with its size, a date the bake lacked, the new values",
          changes.refused is None and changes.history_changed and changes.lines == [
              "revised 2026-02-01: 2.0 -> 2.25 (+0.25)",
              "1 values on dates within the bake that it lacked (2026-01-15)",
              "2 new (2026-04-01 to 2026-05-01), 1 revised",
          ], changes.lines)
    changes = bake.bake_changes(old, series({"2026-01-01": 1.0, "2026-02-01": 2.0, "2026-03-01": 3.0, "2026-04-01": 4.0}))
    check("report: new values alone change no history", not changes.history_changed and list(changes.added) == [pd.Timestamp("2026-04-01")],
          changes.lines)
    changes = bake.bake_changes(old, series({"2026-01-01": 1.0, "2026-03-01": 3.0, "2026-04-01": 4.0}))
    check("report: a download lacking a baked date refused, the date named, and reported withdrawn",
          changes.refused == "1 baked dates are not in the download (2026-02-01)" and changes.history_changed
          and changes.lines == ["1 baked dates are not in the download (2026-02-01)", "1 new (2026-04-01 to 2026-04-01), 0 revised, 1 withdrawn"],
          changes.lines)
    many_old = series({f"2025-{month:02d}-01": float(month) for month in range(1, 13)} | {f"2026-{month:02d}-01": float(month) for month in range(1, 13)})
    many_new = many_old + 0.5
    lines = bake.bake_changes(many_old, many_new).lines
    check("report: the first 20 revisions listed, then their count and the largest",
          len(lines) == 22 and lines[20] == "and 4 more revised, to 2026-12-01; the largest change 0.5" and lines[21] == "0 new, 24 revised",
          lines[19:])


def main() -> int:
    check_files()
    with tempfile.TemporaryDirectory(prefix="ratesplot_check_baked_") as temporary:
        check_written(Path(temporary))
        check_join(Path(temporary))
    check_report()
    passed = sum(RESULTS)
    print(f"[baked] {passed} of {len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
