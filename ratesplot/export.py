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
from collections.abc import Sequence

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.text import Text

from .config import PlotConfig, nation_by_key

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
# column's (name, axis); on the figure, its subtitle's Text.
_SERIES_ATTR = "_ratesplot_export_series"
_SUBTITLE_ATTR = "_ratesplot_export_subtitle"
YIELD_AXIS = "yield"
MACRO_AXIS = "macro"
# Each nation's currency as a column's unit names it (the axis's own symbol
# is "$" for the U.S., which alone in a file says too little).
_CURRENCY_UNITS = {"USD": "US$", "CAD": "C$", "GBP": "£", "EUR": "€"}


def mark_series(line: Line2D, name: str, axis: str) -> Line2D:
    """Record that ``line`` is (a piece of) the curve exported as ``name``, on ``axis`` (``YIELD_AXIS``, ``MACRO_AXIS``)."""
    setattr(line, _SERIES_ATTR, (name, axis))
    return line


def mark_subtitle(figure: Figure, text: Text) -> None:
    """Record ``text`` as ``figure``'s subtitle, the second row of its exported data."""
    setattr(figure, _SUBTITLE_ATTR, text)


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
            mark = getattr(line, _SERIES_ATTR, None)
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


def _macro_unit(config: PlotConfig, nation_key: str) -> str:
    if config.relative:
        return "% of TTM GDP"
    currency = _CURRENCY_UNITS.get(nation_by_key(nation_key).currency, nation_by_key(nation_key).currency)
    return f"{currency} per person" if config.per_capita else currency


def chart_data(figure: Figure, config: PlotConfig, nation_key: str) -> ChartData:
    """Return the data ``figure`` shows (see the module docstring); ``config`` is the nation's own (``for_nation``)."""
    curves = _pieces(figure)
    start, end = (mdates.date2num(pd.Timestamp(value).to_pydatetime()) for value in (config.start, config.end))
    days = np.unique(np.concatenate([piece.x for pieces in curves.values() for piece in pieces] or [np.empty(0)]))
    days = days[(days >= start) & (days <= end)]
    columns = [_values_on(pieces, days) for pieces in curves.values()]
    units = tuple("%" if axis == YIELD_AXIS else _macro_unit(config, nation_key) for _name, axis in curves)
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


def xlsx_bytes(sheets: Sequence[tuple[str, ChartData]]) -> bytes:
    """A workbook with a sheet for each ``(sheet name, data)``: dates as dates shown YYYY-MM-DD, numbers as numbers."""
    from openpyxl import Workbook  # only when a workbook is written: the page installs it, the rest need not
    from openpyxl.styles import Font

    book = Workbook()
    book.remove(book.active)
    for sheet_name, data in sheets:
        sheet = book.create_sheet(sheet_name[:31])  # Excel's limit on a sheet's name
        for row in _table(data):
            sheet.append([value.to_pydatetime() if isinstance(value, pd.Timestamp) else value for value in row])
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
