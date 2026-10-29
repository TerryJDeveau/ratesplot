"""Export chart (batch 11.1): a chart as an image, or the data it shows, the format by the file's extension.

Terry asked for "Save image" in place of "Save PNG", offering PNG, JPG and
PDF (2026-10-08 and 2026-10-12, decision 22), then for "Export chart",
writing as well "exactly the time series data shown in the window, with
formats implied by the file extension: XLSX, CSV, and TSV" (2026-10-21,
decision 46). The window's Export chart button, the web page's download
and the command line's --save:FILE all come here.

* An image (``IMAGE_FORMATS``): PNG is the bytes the chart was drawn as, so
  a saved chart is the one shown; JPG, PDF and SVG are the same figure
  saved again in that format (PDF and SVG as lines and text, sharp at any
  size).
* The data (``DATA_FORMATS``, ``chart_data``): the first row the chart's
  title, the second its subtitle (the dates), the third each column's name
  (the date, then each curve as its legend names it), the fourth each
  column's unit in brackets, the values from the fifth. A row for each date
  in the window on which any curve drawn has a point. Each column holds the
  value its line shows on that date (Terry: "The exported file should have
  values that match what the series lines portray for each date within the
  time window selected"): a curve drawn as steps, the value in force; one
  drawn as a line, the line between its two points, straight as the axis
  draws it (on a log axis, in the logarithm); blank where the chart has no
  line for it (before it begins, after it ends, in a gap). A value outside
  the axis limits is written, an intraday quote is its yield's last row
  (dated by its day, unmarked), the projections to today are written when
  drawn; the regression segments are not (a fit, not a series). The U.S.
  target range is two columns, its lower and upper limits. Full precision.
  XLSX is one sheet, the chart shown; "XLSX-global" (``every_chart``) a sheet
  for each chart drawn.

Which line is which curve is not read from the figure's labels, which hide
a curve's later pieces as "_nolegend_" (Canada's daily yields after the
monthly history, the band's upper limit alike): plotting marks each piece
it draws with its column's name and axis (``mark_series``), an attribute no
renderer reads, so the charts are unchanged. The subtitle is marked too
(``mark_subtitle``).
"""

from __future__ import annotations

import csv
import dataclasses
import io
import os
import time
from collections.abc import Callable, Sequence

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text

from .config import MASTER_SYMBOLS, PlotConfig, nation_by_key

# The file's extension -> matplotlib's format name.
IMAGE_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".pdf": "pdf", ".svg": "svg"}
DATA_FORMATS = (".xlsx", ".csv", ".tsv")
FORMATS = (*IMAGE_FORMATS, *DATA_FORMATS)
# The choices offered by the window's dialog and the page's menu, in this
# order: (caption, extension, every chart drawn). XLSX twice: the chart
# shown, or a workbook with a sheet for each chart ("XLSX-global", decision 46).
EXPORT_CHOICES: tuple[tuple[str, str, bool], ...] = (
    ("PNG image", ".png", False),
    ("JPG image", ".jpg", False),
    ("PDF document", ".pdf", False),
    ("SVG drawing", ".svg", False),
    ("XLSX workbook, this chart", ".xlsx", False),
    ("XLSX-global workbook, every chart", ".xlsx", True),
    ("CSV, comma-separated", ".csv", False),
    ("TSV, tab-separated", ".tsv", False),
)
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
}
# JPG's quality: high, since thin lines and small text blur at the default 75.
JPEG_QUALITY = 95

# The marks plotting puts on what it draws: on each piece of a curve, its
# column's (name, axis); on the figure, its subtitle's Text, and the currency
# its amounts are in when it is converted to the master's (batch 30).
_SERIES_ATTR = "_ratesplot_export_series"
_SUBTITLE_ATTR = "_ratesplot_export_subtitle"
_CURRENCY_ATTR = "_ratesplot_amounts_currency"
YIELD_AXIS = "yield"
MACRO_AXIS = "macro"
# Each currency as a column's unit names it (the axis's own symbol is "$"
# for the U.S., which alone in a file says too little): the symbols a chart
# in the master currency writes (config.MASTER_SYMBOLS, the same four).
_CURRENCY_UNITS = MASTER_SYMBOLS


def mark_series(line: Line2D, name: str, axis: str) -> Line2D:
    """Record that ``line`` is (a piece of) the curve exported as ``name``, on ``axis`` (``YIELD_AXIS``, ``MACRO_AXIS``)."""
    setattr(line, _SERIES_ATTR, (name, axis))
    return line


def series_of(line: Line2D) -> tuple[str, str] | None:
    """The curve ``line`` is (a piece of), as ``mark_series`` marked it: ``(name, axis)``; None if it is not marked."""
    return getattr(line, _SERIES_ATTR, None)


def mark_subtitle(figure: Figure, text: Text) -> None:
    """Record ``text`` as ``figure``'s subtitle, the second row of its exported data."""
    setattr(figure, _SUBTITLE_ATTR, text)


def mark_amounts_currency(figure: Figure, currency: str | None) -> None:
    """Record the currency ``figure``'s amounts are drawn in when not its nation's own (the master's, batch 30); None for its own."""
    setattr(figure, _CURRENCY_ATTR, currency)


def marked_amounts_currency(figure: Figure) -> str | None:
    """The currency ``mark_amounts_currency`` recorded for ``figure``: the master's on a chart converted to it, else None."""
    return getattr(figure, _CURRENCY_ATTR, None)


def amounts_currency(figure: Figure, nation_key: str) -> str:
    """The currency ``figure``'s amounts are drawn in: the master's where ``mark_amounts_currency`` said so, else nation ``nation_key``'s own."""
    return marked_amounts_currency(figure) or nation_by_key(nation_key).currency


def format_of(path: str) -> str | None:
    """Return the export format a file name asks for, its extension in lower case (".png"); None if none is offered."""
    suffix = path[path.rfind("."):].lower() if "." in path.replace("\\", "/").rsplit("/", 1)[-1] else ""
    return suffix if suffix in FORMATS else None


@dataclasses.dataclass(frozen=True)
class ChartData:
    """The data a chart shows, as exported: its title and subtitle, each column's name and unit, and the rows."""

    title: str
    subtitle: str
    names: tuple[str, ...]  # each curve's column, after the date's
    units: tuple[str, ...]  # each curve's unit, without brackets
    dates: tuple[pd.Timestamp, ...]
    values: tuple[tuple[float | None, ...], ...]  # a row for each date, a value (or None) for each curve


@dataclasses.dataclass
class _Piece:
    """One drawn piece of a curve: its points (dates as matplotlib's day numbers), drawn as steps or not, on a log axis or not."""

    x: np.ndarray
    y: np.ndarray
    steps: bool
    log: bool


def _pieces(figure: Figure) -> dict[tuple[str, str], list[_Piece]]:
    """Each marked curve's drawn pieces, curves in drawing order, each curve's pieces by their first date."""
    curves: dict[tuple[str, str], list[_Piece]] = {}
    for ax in figure.axes:
        for line in ax.get_lines():
            mark = series_of(line)
            if mark is None:
                continue
            xy = np.asarray(line.get_xydata(), dtype=float)  # dates already as day numbers
            if not len(xy):
                continue
            steps = line.get_drawstyle().startswith("steps")
            curves.setdefault(mark, []).append(_Piece(xy[:, 0], xy[:, 1], steps, line.axes.get_yscale() == "log"))
    for pieces in curves.values():
        pieces.sort(key=lambda piece: piece.x[0])
    return curves


def _values_on(pieces: list[_Piece], days: np.ndarray) -> np.ndarray:
    """The value a curve's line shows on each of ``days`` (day numbers): NaN where it shows none.

    A piece drawn as steps holds each value until its next point, and its
    last value until the curve's next piece begins (Canada's monthly yields
    until its daily ones); a piece drawn as a line joins its points straight
    as the axis draws them (in the logarithm on a log axis). A point whose
    value is NaN is a break in the line.
    """
    out = np.full(len(days), np.nan)
    for index, piece in enumerate(pieces):
        later = pieces[index + 1].x[0] if index + 1 < len(pieces) else None
        last = piece.x[-1] if not piece.steps or later is None else later
        inside = (days >= piece.x[0]) & ((days <= last) if not piece.steps or later is None else (days < last))
        inside &= np.isnan(out)  # the earlier piece keeps a date both reach (a projection begins on its data's last day)
        if not inside.any():
            continue
        when = days[inside]
        at = np.searchsorted(piece.x, when, side="right") - 1  # the last point on or before each date
        if piece.steps:
            out[inside] = piece.y[at]
            continue
        exact = piece.x[at] == when
        result = np.full(len(when), np.nan)
        result[exact] = piece.y[at[exact]]
        between = ~exact & (at + 1 < len(piece.x))
        left, right = at[between], at[between] + 1
        x0, x1 = piece.x[left], piece.x[right]
        y0, y1 = piece.y[left], piece.y[right]
        share = (when[between] - x0) / (x1 - x0)
        if piece.log:
            with np.errstate(invalid="ignore", divide="ignore"):
                result[between] = np.exp(np.log(y0) + share * (np.log(y1) - np.log(y0)))
        else:
            result[between] = y0 + share * (y1 - y0)
        out[inside] = result
    return out


def _macro_unit(figure: Figure, config: PlotConfig, nation_key: str) -> str:
    """The right axis's unit in a data file: "% of TTM GDP", or its amounts' currency (the master's on a chart converted to it), per person under -p."""
    if config.relative:
        return "% of TTM GDP"
    code = amounts_currency(figure, nation_key)
    currency = _CURRENCY_UNITS.get(code, code)
    return f"{currency} per person" if config.per_capita else currency


def chart_data(figure: Figure, config: PlotConfig, nation_key: str) -> ChartData:
    """Return the data ``figure`` shows (see the module docstring); ``config`` is the nation's own (``for_nation``)."""
    curves = _pieces(figure)
    start, end = (mdates.date2num(pd.Timestamp(value).to_pydatetime()) for value in (config.start, config.end))
    days = np.unique(np.concatenate([piece.x for pieces in curves.values() for piece in pieces] or [np.empty(0)]))
    days = days[(days >= start) & (days <= end)]
    columns = [_values_on(pieces, days) for pieces in curves.values()]
    units = tuple("%" if axis == YIELD_AXIS else _macro_unit(figure, config, nation_key) for _name, axis in curves)
    title = figure._suptitle.get_text() if figure._suptitle is not None else ""
    subtitle_text = getattr(figure, _SUBTITLE_ATTR, None)
    rows = tuple(
        tuple(None if np.isnan(column[row]) else float(column[row]) for column in columns) for row in range(len(days))
    )
    return ChartData(
        title=title,
        subtitle=subtitle_text.get_text() if subtitle_text is not None else "",
        names=tuple(name for name, _axis in curves),
        units=units,
        dates=tuple(pd.Timestamp(mdates.num2date(day).replace(tzinfo=None)).normalize() for day in days),
        values=rows,
    )


def _table(data: ChartData) -> list[list[object]]:
    """The rows of a data file: title, subtitle, the columns' names, their units, then a row for each date."""
    return [
        [data.title],
        [data.subtitle],
        ["Date", *data.names],
        ["(YYYY-MM-DD)", *(f"({unit})" for unit in data.units)],
        *([date, *values] for date, values in zip(data.dates, data.values)),
    ]


def _text(value: object) -> str:
    """A cell as text: a date as YYYY-MM-DD, a number to 15 significant digits, nothing as blank.

    Fifteen digits are every digit a source's figures have and all a double
    holds exactly, while the binary leftovers of arithmetic go: a spread of
    2.17 less 1.65 is 0.58 here, not 0.5800000000000001 (``repr``).
    """
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return f"{value:%Y-%m-%d}"
    return format(value, ".15g") if isinstance(value, float) else str(value)


def delimited_bytes(data: ChartData, delimiter: str) -> bytes:
    """``data`` as CSV (``delimiter`` ",") or TSV ("\\t"): UTF-8 with its byte-order mark, which Excel reads as UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    for row in _table(data):
        writer.writerow([_text(value) for value in row])
    return buffer.getvalue().encode("utf-8-sig")


def _cell(value: object) -> object:
    """A cell as a workbook holds it: a date as a date, a number to 15 significant digits, as the CSV's (``_text``).

    openpyxl writes a number to 16 digits (measured 2026-10-27, 3.1.5), which
    keeps the leftovers of arithmetic (0.5800000000000001) and differs from
    the CSV's numbers in the last digit; rounded first, the two files agree.
    """
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return float(format(value, ".15g")) if isinstance(value, float) else value


def xlsx_bytes(sheets: Sequence[tuple[str, ChartData]]) -> bytes:
    """A workbook with a sheet for each ``(sheet name, data)``: dates as dates shown YYYY-MM-DD, numbers as numbers."""
    from openpyxl import Workbook  # only when a workbook is written: the page installs it, the rest need not
    from openpyxl.styles import Font

    book = Workbook()
    book.remove(book.active)
    for sheet_name, data in sheets:
        sheet = book.create_sheet(sheet_name[:31])  # Excel's limit on a sheet's name
        for row in _table(data):
            sheet.append([_cell(value) for value in row])
        sheet["A1"].font = Font(bold=True)
        for cell in sheet["A"][4:]:
            cell.number_format = "yyyy-mm-dd"
        sheet.column_dimensions["A"].width = 13
        for column in range(2, len(data.names) + 2):
            sheet.column_dimensions[sheet.cell(row=3, column=column).column_letter].width = max(12, min(40, len(data.names[column - 2]) + 2))
        sheet.freeze_panes = "B5"
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def image_bytes(figure: Figure, png: bytes, extension: str) -> bytes:
    """The chart as an image in ``extension``'s format: PNG the bytes drawn (``png``), the others ``figure`` saved again."""
    kind = IMAGE_FORMATS[extension]
    if kind == "png":
        return png
    buffer = io.BytesIO()
    options = {"pil_kwargs": {"quality": JPEG_QUALITY}} if kind == "jpeg" else {}
    figure.savefig(buffer, format=kind, dpi=figure.dpi, **options)
    return buffer.getvalue()


def data_bytes(extension: str, charts: Sequence[tuple[str, ChartData]]) -> bytes:
    """The data file in ``extension``'s format: a workbook with a sheet per chart, or (CSV, TSV) the one chart's."""
    if extension == ".xlsx":
        return xlsx_bytes(charts)
    if len(charts) != 1:
        raise ValueError(f"a {extension} file holds one chart's data, not {len(charts)}")
    return delimited_bytes(charts[0][1], "," if extension == ".csv" else "\t")


def per_nation_path(path: str, code: str) -> str:
    """``rates.png`` -> ``rates_ca.png``: the command line's file for one nation's chart (decision 46)."""
    dot = path.rfind(".")
    return f"{path[:dot]}_{code}{path[dot:]}"


# The lengths of a number after a name's last underscore that is never
# counted on (batch 33, Terry, 2026-10-28): four digits, a time or a year
# (the program's log: ``ratesplot_log_2026-10-28_1507.txt``; ``report_2026``);
# six and eight, a date or a time written without dashes (``261028``,
# ``150734``, ``20261028``), which counted on would read as the next one.
# The program's chart names end in a date with dashes, never a number
# (``cdn_rates_1981-09-01_2026-09-29.png``).
_NOT_COUNTED = (4, 6, 8)
# The most names refused in one write before the refusal is taken to be the
# folder's, not a file another program holds, and raised (batch 11.3).
_MOST_HELD = 99
# A refused replace is tried again after these pauses (seconds) before the
# file counts as held: a file written a moment before was refused once, in
# one of four runs of check_refresh on 2026-10-28 (Windows' virus scan or
# indexer opening it, most likely), and then written as "_1" for nothing.
# A workbook open in Excel is still held after them.
_HELD_PAUSES = (0.05, 0.1, 0.2)


def _replace(temporary: str, name: str) -> None:
    """``os.replace``, tried again after each of ``_HELD_PAUSES`` while Windows refuses it; the last refusal raised."""
    for pause in _HELD_PAUSES:
        try:
            os.replace(temporary, name)
            return
        except PermissionError:
            time.sleep(pause)
    os.replace(temporary, name)


def _own_number(stem: str) -> tuple[str, str]:
    """``a_3`` -> (``a``, ``3``); a stem whose last underscore is not followed by a number counted on -> (the stem, "")."""
    base, underscore, digits = stem.rpartition("_")
    if underscore and base and digits.isascii() and digits.isdigit() and len(digits) not in _NOT_COUNTED:
        return base, digits
    return stem, ""


def next_path(path: str) -> str:
    """The name after ``path``'s (batches 11.3, 33): ``a.xlsx`` -> ``a_1.xlsx``, ``a_3.xlsx`` -> ``a_4.xlsx``.

    The name's own number is counted on, its width kept (``a_007`` ->
    ``a_008``); a name without one counted on gets ``_1`` (``a_2026`` ->
    ``a_2026_1``). A number that would come out at a length never counted on
    gets a leading zero (``a_999`` -> ``a_01000``), so the program never
    writes a number it would not count on again (Terry).
    """
    folder, name = os.path.split(path)
    stem, extension = os.path.splitext(name)
    base, digits = _own_number(stem)
    number = f"{int(digits) + 1:0{len(digits)}d}" if digits else "1"
    while len(number) in _NOT_COUNTED:
        number = f"0{number}"
    return os.path.join(folder, f"{base}_{number}{extension}") if folder else f"{base}_{number}{extension}"


def _same_file_name(path: str) -> str:
    """``path`` as Windows compares names: absolute, its case and slashes alike."""
    return os.path.normcase(os.path.abspath(path))


class SavedFiles:
    """The files one job saves, each written through a temporary file swapped in, and the names they go under (batches 11.3, 33).

    A job is a command line's run with all its refreshes (--save), or the
    window from its opening to its closing (Export chart, Save message log).

    Plan 11.3's notes (Terry): "Each write goes to a temporary file beside
    the target, which is closed and then swapped in for the old file in one
    step: a viewer never reads a half-written file, and nothing is held open
    between refreshes. If another program holds the old file locked, the
    program says so and appends a version number "_n" to the file name, with
    n starting at 1; it will keep using this same new name, unless that file
    also is found to be locked at some point, only then will n be incremented
    by 1."

    Batch 33 (Terry, 2026-10-28, decision 85): "all the ways of saving a file
    should follow the same rule. If the file already exists, and the current
    job knows that it exists (because it wrote to it previously) then it can
    overwrite with no issue and no warning. But if the file already exists,
    and the current job didn't previously write to it, then it should add an
    increment to the file name ... unless that number is already taken, or
    the file name already has [a number] on the end, then keep incrementing
    until you find an unused number." With an underscore ("let's go with
    underscore"), since the program's names end in dates; every number
    counted on but one of four, six or eight digits (Terry's four, a time or
    a year; six and eight added at his choice, dates without dashes).

    So: a name this job has written is replaced without a word. One it has
    not written that is already there, or one another program holds, gives
    way to the next free name (``next_path``: the name's own number counted
    on, else _1), each name tried skipped while a file has it, and the
    program says which name it wrote. A name the person picked in the
    window's Save As dialog, which asked before replacing it (measured
    2026-10-28, Tk 9.0.4), is replaced as if this job had written it
    (``chosen``). A file is "held" when Windows refuses to replace it
    (``PermissionError``: open in Excel, or read-only); any other failure is
    raised.
    """

    def __init__(self, say: Callable[[str], None] = print) -> None:
        # Where a name went that was not the name given: said once, through ``say``.
        self._say = say
        # The name given -> the name it was last written under.
        self._names: dict[str, str] = {}
        # Every name this job has written, as Windows compares them.
        self._written: set[str] = set()

    def wrote(self, name: str) -> bool:
        """Whether this job has written ``name``."""
        return _same_file_name(name) in self._written

    def free_path(self, target: str) -> str:
        """The name a Save As dialog offers for ``target``: it, or the next name no file has (``next_path``).

        A file this job wrote counts as taken here: the name offered is one
        Windows' dialog need not ask about, so pressing Save never replaces a
        file.
        """
        name = target
        while os.path.exists(name):
            name = next_path(name)
        return name

    def write(self, target: str, data: bytes, chosen: bool = False) -> str:
        """Write ``data`` for ``target`` (``rates_ca.png``) and return the name it went under.

        ``chosen``: the person picked ``target`` and confirmed replacing it,
        so it is tried first, whatever name it went under before.
        """
        name = target if chosen else self._names.get(target, target)
        held: list[str] = []
        taken: list[str] = []
        temporary = f"{target}.{os.getpid()}.tmp"
        with open(temporary, "wb") as output:
            output.write(data)
        try:
            while True:
                mine = self.wrote(name) or (chosen and name == target)
                if not mine and os.path.exists(name):
                    taken.append(name)  # a file this job did not write: never written over
                    name = next_path(name)
                    continue
                try:
                    _replace(temporary, name)
                except PermissionError:
                    held.append(name)
                    if len(held) >= _MOST_HELD:
                        raise  # every name refused: the folder itself, not a file another program holds
                    name = next_path(name)
                    continue
                self._say_where(held, taken, name)
                self._names[target] = name
                self._written.add(_same_file_name(name))
                return name
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def _say_where(self, held: list[str], taken: list[str], name: str) -> None:
        """Say where a file went that did not go under the name tried first: "a.xlsx is already there; written as a_1.xlsx"."""
        if not held and not taken:
            return
        parts = []
        if held:
            parts.append(f"Held by another program: {', '.join(held)}")
        if taken:
            parts.append(f"{', '.join(taken)} {'is' if len(taken) == 1 else 'are'} already there")
        self._say(f"  {'; '.join(parts)}; written as {name}{' instead' if held else ''}.")
