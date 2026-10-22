"""The live sources' history, baked into the package as data files (batch 19.2).

Terry, 2026-10-21 (decision 45): every live source's history baked into
the package, only the recent part fetched live, for "long-term
stability": a new install, a colleague's copy and the web page after each
Reboot all start with the history in hand, and a source that is down, or
gone, is still drawn to the bake's last date. Re-baked daily (decision 49)
by a separate job whose result is committed; the running program never
writes these files. Begun with the Bank of England's database, 2026-10-21;
then the Bank of Canada's Valet, 2026-10-22.

The files: ``ratesplot/data/SOURCE/CODE.csv``, one series each, written
only by the bake (``ratesplot.bake``, run by ``tools/bake_archives.py``):
comment lines starting ``#`` (what the series is), then the header
``date,value`` and one row for each date the source has a value, oldest
first, dated ``YYYY-MM-DD``, the value as Python writes a float (``repr``:
the shortest text that reads back as the same number; ``write_series``
checks that it does). Plain text, not compressed: a daily re-bake adds a
few lines, which git stores as a small change, where a compressed file
would be stored whole again every day. Nothing in a file says when it was
baked, so a file changes only when its source has new or revised values;
its last date says how far it reaches.

A drawing asks the source only for the recent part (``with_recent_part``):
from a while before the bake's last date (``config.RECENT_PART_UNREVISED``
or ``RECENT_PART_REVISED``, the source's own), so that late values and
revisions in that span arrive. The baked values and the recent part are
one series, so they meet without a ramp, unlike the joins of different
sources (``joins.chain``): the bake's values before the recent part's
first date, the source's from it on.
"""

from __future__ import annotations

import functools
import io
import os
import threading
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from .config import DATE_COLUMN

# The package's data files; a harness may point it elsewhere (tools/synthetic_sources.py).
DATA_FOLDER = Path(__file__).resolve().with_name("data")
_HEADER = "date,value"


def data_file(source: str, code: str) -> Path:
    """``ratesplot/data/SOURCE/CODE.csv``: where series ``code`` of ``source`` is baked."""
    return DATA_FOLDER / source / f"{code}.csv"


def parse_series(text: str, code: str) -> pd.Series:
    """Read a baked file's text: a float series named ``code``, indexed by date; raises if it is not in the bake's form.

    The values are read by Python's ``float``, which gives back exactly the
    float whose ``repr`` the bake wrote: the very float the live download
    gave. pandas' own conversion from text can be a unit in the last place
    off for a value written with 17 digits (``0.30000000000000004`` reads as
    0.3; tools/check_baked.py).
    """
    frame = pd.read_csv(io.StringIO(text), comment="#", dtype=str)
    if list(frame.columns) != ["date", "value"]:
        raise ValueError(f"baked {code}: expected the columns date,value, got {list(frame.columns)}")
    if frame["value"].isna().any():
        raise ValueError(f"baked {code}: a row without a value")
    dates = pd.DatetimeIndex(pd.to_datetime(frame["date"], format="%Y-%m-%d"), name=DATE_COLUMN)
    values = pd.Series([float(text) for text in frame["value"]], index=dates, dtype=float, name=code)
    if values.isna().any():
        raise ValueError(f"baked {code}: a value that is not a number")
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError(f"baked {code}: its dates are not in order, each once")
    return values


def format_series(series: pd.Series, comment: str) -> str:
    """The text of a baked file: ``comment`` (one ``#`` line per line), the header, a row per value."""
    lines = [f"# {line}".rstrip() for line in comment.splitlines()] + [_HEADER]
    lines += [f"{day:%Y-%m-%d},{float(value)!r}" for day, value in series.dropna().items()]
    return "\n".join(lines) + "\n"


def write_series(path: Path, series: pd.Series, comment: str) -> None:
    """Write ``series`` as a baked file at ``path``, replacing the one there at once (the bake and the harnesses only).

    The text is read back first and must give ``series`` exactly (its dates
    and every float), so a file is never written that would draw anything
    else. Written in text mode, as the bake writes the data modules: CRLF on
    Windows, LF elsewhere; git stores LF either way.
    """
    text = format_series(series, comment)
    expected = series.dropna().astype(float).rename(series.name)
    back = parse_series(text, str(series.name))
    if not back.index.equals(expected.index) or not (back.to_numpy() == expected.to_numpy()).all():
        raise ValueError(f"baked {series.name}: its text does not read back as the series downloaded")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@functools.lru_cache(maxsize=None)
def _read(path: Path) -> pd.Series | None:
    """The series baked at ``path``, read once per process; None if there is no file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return parse_series(text, path.stem)


def read_series(source: str, code: str) -> pd.Series | None:
    """Return series ``code`` of ``source`` as baked (a copy, the caller's own), or None if it has not been baked."""
    series = _read(data_file(source, code))
    return None if series is None else series.copy()


def forget_read_files() -> None:
    """Read the files again at their next use (a harness that has just written or moved them)."""
    _read.cache_clear()


def with_recent_part(
    source: str,
    code: str,
    label: str,
    fetch: Callable[[pd.Timestamp | None], pd.Series],
    recent: pd.DateOffset,
) -> pd.Series:
    """Return series ``code``: its baked history, then its recent part asked for live.

    ``fetch(start)`` asks the source for its values from ``start`` on;
    ``fetch(None)`` for every value, which is what a series not yet baked
    gets, as before batch 19.2. The recent part begins ``recent`` before
    the bake's last date, so a bake left behind (a re-bake that stopped, a
    copy not updated) is still followed by every newer value. Values before
    ``start`` in the answer are left out: a source that sends more than it
    was asked for (the Bundesbank's) changes nothing.

    If the recent part fails, the baked history alone, with a warning naming
    ``label`` and the bake's last date (decision 45). The request's last good
    copy (batch 20), where there is one, is drawn before that, by the
    download cache, which names it at the drawing's end.
    """
    baked = read_series(source, code)
    if baked is None or baked.empty:
        return fetch(None)
    start = baked.index[-1] - recent
    try:
        live = fetch(start)
    except Exception as exc:
        print(f"  Warning: {label}: its recent values unavailable ({exc}); drawn from its baked history, to {baked.index[-1]:%Y-%m-%d}.")
        return baked
    return pd.concat([baked.loc[baked.index < start], live.loc[live.index >= start]])


def frame_with_recent_part(
    source: str,
    codes: Sequence[str],
    label: str,
    fetch: Callable[[pd.Timestamp | None], pd.DataFrame],
    recent: pd.DateOffset,
) -> pd.DataFrame:
    """Return series ``codes`` of ``source``, which one request gives together (a group), as a frame: their baked history, then their recent part.

    ``with_recent_part`` for a request that answers several series at once
    (the Bank of Canada's benchmark yields): ``fetch(start)`` asks for the
    group from ``start`` on, ``fetch(None)`` for every value, which is what
    the group gets, as before batch 19.2, if any of ``codes`` is not baked.
    The recent part begins ``recent`` before the earliest of the bakes' last
    dates, so each series gets every newer value. The frame's columns are
    ``codes``, in their order, and its rows every date on which any of them
    has a value (a date the group lists with no value in any of them is not
    in the bake). If the recent part fails, or lacks one of ``codes``, the
    baked history alone, with a warning naming ``label`` and the bake's last
    date.
    """
    bakes = [read_series(source, code) for code in codes]
    if any(series is None or series.empty for series in bakes):
        return fetch(None)
    start = min(series.index[-1] for series in bakes) - recent
    # sort_index: concat along columns does not sort the dates one series lacks.
    history = pd.concat(bakes, axis=1).sort_index()
    try:
        live = fetch(start)[list(codes)]
    except Exception as exc:
        print(f"  Warning: {label}: its recent values unavailable ({exc}); drawn from its baked history, to {history.index[-1]:%Y-%m-%d}.")
        return history
    return pd.concat([history.loc[history.index < start], live.loc[live.index >= start]])
