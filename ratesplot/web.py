"""The web page: the charts in a browser, for anyone with the link (Streamlit).

Run it with ``streamlit run streamlit_app.py`` from the project root; on
Streamlit Community Cloud the same file is the entry point.

What it is
    A third front end beside the command line and the window, over the same
    option table and the same drawing. Every chart is
    ``plotting.build_figure`` rendered to PNG (``frontend.png_bytes``): on the
    same machine, byte for byte what the window shows and saves. The controls
    are generated from ``options.OPTIONS`` as the window's are (options with
    ``in_gui=False`` are left out), in the window's blocks and order
    (``frontend.control_blocks``), and follow the
    window's rules: at least one country stays ticked; one measure at a time,
    and changing it clears Top and Bottom; GDP greyed out under -r, and what
    has no curve to act on (``frontend.idle_controls``: % of GDP, By level,
    Per capita, the regression segments, Top and Bottom), ticks and texts
    kept, greyed texts ignored and left out of the address; each
    nation's own choices (``frontend.NATION_OPTIONS``: its yield terms,
    spreads and mortgage terms, only those its chart can draw, and its axis
    limits) in a sidebar section of its own, each limit with its unit and an
    "All" tick that copies it to every nation (batch 18); a value
    that belongs to a flag (the regression tolerance) greyed while the flag
    is off, and ignored then; a blank text field showing the value in effect
    in grey, as its placeholder (``frontend.field_hints``: the start found,
    the end, the tolerance's default, each chart's axis limits as drawn). A
    new option in the table appears here with no change to this module.

The chart's address
    The page's address carries the chart's command line: ``?chart=-c+-r+--reg``
    holds the same tokens ``python ratesplot.py -c -r --reg`` takes
    (``options.command_line_tokens``). Opening such a link draws that chart;
    after each drawing the address is updated, so a chart can be bookmarked
    or sent to someone. An address the program cannot read is reported, and
    the settings remembered, or the defaults, are drawn instead. Under the
    command line the chart's link is shown with a copy button, labelled
    "Web page:" as in the window, which shows it on the page's own address
    (batch 31.3, ``frontend.chart_link``); beside it Go opens it in a new
    tab, a copy of the charts that goes on by itself (batch 34.1).

Remembered settings
    As the window remembers its settings, the page keeps the last chart's
    command line, as the address holds it, in a cookie in the visitor's
    browser (batch 24.6, ``_remember_settings``), behind a "Remember my
    settings" box, ticked at every visit, with one line saying what is
    kept. A visit opens on the address's chart if it has one, else on the
    settings remembered, else on the defaults; so a shared link draws what
    it says. The page's own script writes the cookie, and reads it back at
    the start of a visit with no chart in its address, before anything is
    drawn (``_read_remembered``): Streamlit Community Cloud gives the app no
    cookies. Unticked, the cookie is left as it is, neither written nor
    cleared. Reset gives the defaults, which the next drawing keeps (the
    cookie removed) while the box is ticked. The sidebar's width, which
    Streamlit keeps in the browser once it is dragged, is kept only while
    the box is ticked, as the window's column's is (batch 31.1,
    ``_keep_sidebar_width``).

Visitors
    Streamlit runs each visitor's page in its own thread, all in one process.
    - Downloads are shared by every visitor and kept for
      ``DOWNLOAD_MAX_AGE_SECONDS`` (``http.enable_download_cache``); the
      intraday quotes are fetched for every drawing, as in the window.
    - The last good copy of each download is kept on the server's disk and
      drawn when its source fails, with a notice above the charts (batch 20,
      ``http.enable_last_good_copies``). The disk lasts only while the app
      runs: a Reboot or a sleep starts it empty.
    - Charts are drawn one at a time (``_DRAWING_LOCK``). Matplotlib does not
      promise that drawing in several threads at once is safe, and a free
      server has two processors; a visitor who asks during another's drawing
      waits for it, a few seconds.
    - What a drawing prints (progress, warnings, the start found) goes to
      that visitor's log only (``console``).
    - "Today", the default end, is the markets' date (Toronto) on a server,
      whatever the server's own time zone (``_use_market_time_zone``).

Zoom and dates
    As in the window, the mouse and the buttons write the fields a visitor
    would type in, so the fields stay the single source of truth (the
    address, the command line and the downloads all follow). Drag a box on
    a chart to zoom to it: its width sets Start and End, its height the
    yield Min and Max and the right axis's Top and Bottom (the window's
    rules, ``frontend.zoom_updates``). The chart is a small in-page component
    (``_chart_component``) because ``st.image`` reports no mouse events.
    The wheel over a chart zooms the dates about the pointer, as in the
    window (batch 24.7, ``_wheel_turned``, ``frontend.scale_dates_updates``):
    the notches are collected and applied once the wheel has been still for
    350 ms, one drawing for each turn; over a chart the page does not
    scroll, and Ctrl and the wheel is the browser's own zoom.
    "◀ Earlier" and "Later ▶" move the dates by half the window, "Zoom out"
    doubles their span (``frontend.move_dates_updates``: between 1600 and
    today, keeping the span). "Back" undoes one zoom, move, Unzoom or Reset;
    "Unzoom" returns to the charts before the first zoom or move since the
    last Reset (batch 28.2), as one more step that Back undoes; each is
    greyed while it would do nothing (as in the window). The axis limits are
    each nation's own, so zooming one chart's axes leaves the other's; the
    dates are shared, as on the command line.

Dates
    Beside each date field a 📅 button opens Streamlit's calendar (between
    1600 and 2100) and a "Blank (default)" button, as the window's does:
    picking a day writes ``YYYY-MM-DD`` in the field, and typing ``YYYY`` or
    ``YYYY-MM`` still works (``_date_control``).

Size
    Width and height boxes and a "Preserve aspect ratio" lock, as in the
    window: with the lock on, changing one box sets the other, so a chart
    whose shape suits can be drawn larger or smaller by typing one number
    (``_size_control``). The ``WxH`` text behind them stays the source of truth.

Downloads
    Under each chart a menu of formats and an "Export chart" button, named as
    the window's ("Download" until batch 31.4; batch 11.1, ``export``): the
    chart as a PNG (the bytes shown), JPG, PDF or SVG, or the data it shows
    as XLSX, CSV or TSV, or a workbook of every chart. The file is made on
    the click (``_export_bytes``).

The hover read-out
    As in the window (batch 11.2, ``hover``): the pointer resting on a line
    shows its name, date and value by the pointer, worked out in the
    visitor's browser from data sent with the chart (``_chart_bytes``), so
    following a line asks nothing of the server. Its box ("Hover read-out")
    changes no chart: unticking it sends the charts without the data, and
    draws nothing again.

Not here (the window has it)
    The right-drag pan (the buttons move the dates).
"""

from __future__ import annotations

import datetime
import functools
import json
import math
import os
import struct
import threading
import time
import urllib.parse
import zlib
from dataclasses import dataclass, replace

import matplotlib

matplotlib.use("Agg")  # before pyplot is imported (by plotting): a server has no display

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import export, hover, http  # noqa: E402
from .cli import sort_tokens  # noqa: E402
from .config import (  # noqa: E402
    DEFAULT_AUTO_REFRESH_MINUTES,
    DEFAULT_CANVAS_PX,
    DEFAULT_REGRESSION_TOLERANCE_PCT,
    DOWNLOAD_MAX_AGE_SECONDS,
    EARLIEST_DATE,
    MARKET_TIMEZONE,
    NATIONS,
    PHONE_CANVAS_PX,
    PHONE_FONT_SCALE,
    PHONE_WIDTH_PX,
    Nation,
    PlotConfig,
)
from .console import this_thread_output_to  # noqa: E402
from .export import EXPORT_CHOICES, IMAGE_FORMATS, MIME_TYPES  # noqa: E402
from .frontend import (  # noqa: E402
    ADDRESS_KEY,
    BACK_HELP,
    BLANK_DATE_WORDS,
    EXPORT_HELP,
    EXPORT_LABEL,
    LIMIT_COLUMNS,
    LIMITS,
    NATION_OPTIONS,
    REFRESH_HELP,
    REMEMBER_HELP,
    REMEMBER_LABEL,
    RESET_HELP,
    UNZOOM_HELP,
    HELP_KEY,
    TAB_TITLES,
    WHEEL_DELAY_MS,
    WHEEL_ZOOM_FACTOR,
    WHEEL_ZOOM_WORDS,
    ChartGeometry,
    Choices,
    all_tick,
    all_tick_reason,
    bound_keys,
    bounds_in_other_units,
    chart_link,
    choice_refusal,
    choice_rows,
    choice_values,
    choices_text,
    control_blocks,
    current_tab,
    drawn_payloads,
    field_hints,
    field_problems,
    greyed_line,
    greyed_reasons,
    help_address,
    help_text,
    idle_choices,
    idle_nation_keys,
    level_letters,
    level_text,
    limit_copies,
    limit_unit,
    move_dates_updates,
    nation_boxes,
    option_help_lines,
    option_of,
    panel_lists,
    png_bytes,
    problem_text,
    reset_changes_nothing,
    reset_choices,
    saved_export_name,
    saved_log_name,
    scale_dates_updates,
    settled_all_ticks,
    size_boxes_at_fault,
    starting_choices,
    trim_history,
    unzoom_target,
    version_text,
    with_leading_zero,
    zoom_updates,
)
from .options import (  # noqa: E402
    OPTIONS,
    Kind,
    Option,
    by_name,
    command_line_tokens,
    config_from_choices,
    field_default,
    help_epilog,
    margin_options,
    nation_choice,
    options_in,
    parse_date_spec,
)
from .plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402
from .refresh import Ticker  # noqa: E402

PAGE_TITLE = "Bond Yields and Public Debt"
PAGE_SUMMARY = (
    "Government bond yields against public debt, GDP, and interest outlays, for Canada and the "
    "United States, from Statistics Canada, the Bank of Canada, FRED, the U.S. Treasury and the "
    "U.S. Census Bureau; and, when ticked, for the United Kingdom, from the Bank of England and the "
    "Office for National Statistics, and for Germany, from the Deutsche Bundesbank, the ECB and Eurostat. Choose the charts in the panel on the left (the » button on a phone); "
    "each change redraws them."
)
_SCRIPT_NAME = "ratesplot.py"
# Go's tip (batch 34.1): the window's Go opens the page in the browser
# (``gui._GO_TIP``); the page's opens a second tab of itself.
_GO_HELP = "Open this chart in a new tab, a copy that goes on by itself; this tab is left as it is."
# The settings remembered between visits (batch 24.6): the chart's command
# line, as the address holds it, in a cookie of this name, kept a year. The
# page's own script writes it (``_MEMORY_JS``) and reads it back
# (``_READER_JS``): Streamlit sets no cookie, and on Community Cloud the app
# is given none (its proxy filters them from the visit's first request, so
# ``st.context.cookies`` was empty there; 6.10, 2026-10-27). The longest
# command line measured, four nations with every value set, was 963
# characters encoded (2026-10-27), a quarter of a cookie's 4 KB.
REMEMBER_COOKIE = "ratesplot_settings"
_REMEMBER_DAYS = 365
# The one line under the box, saying what is kept (Terry, decision 60).
_REMEMBER_LINE = (
    "Kept in this browser: the chart's settings, as in the address, in a cookie for a year; and the sidebar's width once "
    "it is dragged."
)
# What a blank field means, shown in it until a drawing gives the value in
# effect (``frontend.field_hints``: Terry, 2026-10-08, a blank field shows its
# default or automatic value in grey). The other blank fields mean
# "automatic" (the axis limits) or are filled with their default.
_PLACEHOLDERS = {
    **BLANK_DATE_WORDS,
    "regression-tolerance": f"{DEFAULT_REGRESSION_TOLERANCE_PCT:g}",
    "auto-refresh-minutes": f"{DEFAULT_AUTO_REFRESH_MINUTES}",  # batch 11.3
    # The margins at their defaults: the prime margin's 0 (batch 9.4).
    **{margin.name: f"{field_default(margin.fields[0]):g}" for margin in margin_options().values()},
}
_DEFAULT_PLACEHOLDER = "automatic"
# A margin's field beside its term's box in a nation's panel (batch 9.4, the
# prime rate's): narrow, a number of points, so it stays on the box's row in
# the sidebar.
_MARGIN_FIELD_PX = 110
# A nation's axis limit field, with its unit and its "All" box on its right
# (batch 18): narrow enough for the three to share a row in half the sidebar.
_LIMIT_FIELD_PX = 80
_DRAWING_LOCK = threading.Lock()
# How many zoom and pan steps "Back" can undo (as in the window); the view
# before the first one is always kept, for Unzoom.
_HISTORY_LIMIT = 50
# The buttons move the dates by this fraction of the window, or scale it by this factor.
_DATE_STEP_FRACTION = 0.5
_ZOOM_OUT_FACTOR = 2.0
# The window's words and bars (Terry, 2026-10-08); the page has no pan.
_ZOOM_HINT = (
    "Drag pointer: zoom to box (its width sets the dates, its height the axes' limits) | "
    "wheel: zoom dates | buttons: move the dates | Back: undo a zoom"
)
# The notches a wheel's turn may send, either way: the page's script counts
# what the browser reports, so a check on what reaches the server. More
# would ask for a span past all the data, which the zoom cuts anyway.
_WHEEL_MAX_NOTCHES = 60

# Session-state keys: one per control, and the page's own records.
_FLAG = "flag:"      # + option name: a check box
_VALUE = "value:"    # + option name, or a nation's choice key ("us:max"): a text field
_LEVEL = "level:"    # + nation key + ":" + letter: one of a nation's "By level" boxes (batch 10.5)
_CHOICE = "choice:"  # + choice key + ":" + value: one tick box of a list option (Option.choices)
_CHOICE_OTHERS = "choice_others:"  # + choice key: the values given that no offered box has
_ALL = "all:"        # + a nation's limit key ("us:max"): its "All" box, one tick for every nation's (batch 18.2)
_READY = "ready"     # the controls have been set from the address, the settings remembered or the defaults
_ADDRESS_PROBLEMS = "address_problems"
_REMEMBERED_PROBLEMS = "remembered_problems"  # the settings remembered could not be read (batch 24.6)
_STARTED_FROM = "started_from"  # "address", "remembered" or "defaults": what the visit opened on
_REMEMBER = "remember"   # the "Remember my settings" box (batch 24.6)
_READER = "reader"       # the component that reads the cookie back (batch 24.6)
_HEARD = "heard"         # the cookie's value as its script sent it; absent until it has answered
_WIDTH = "width"         # the component that says whether the screen is narrow (batch 28.4)
_NARROW = "narrow"       # True below PHONE_WIDTH_PX; absent until the page's script has said
_NOTICE = "notice"   # a message from a control's callback, shown once
_DRAWING = "drawing"  # the last Drawing
_FORCE = "force_redraw"
_HINTS = "hints"    # the grey values the fields were laid out with (frontend.field_hints), by key
_HISTORY = "history"  # the choices before each zoom, pan or Reset, for Back and Unzoom
_CHART = "chart:"     # + country key + drawing number: a chart (its dragged box)
_CALENDAR = "calendar:"  # + option name: a date field's calendar
_SIZE = "size:"          # + "width", "height", "lock", "ratio": the Size boxes, their lock and kept shape
_CHANGED = "changed"     # the text fields changed by hand, oldest first (frontend.field_problems)
_WRONG = "wrong"         # the fields in the wrong now, by key: their labels are red
_TAB = "tab"             # the charts' tabs: the title of the one shown
_TICKED = "ticked"       # a nation ticked by hand, whose tab is shown once its chart is drawn (batch 17.4)
_EXPORT = "export"       # the format last chosen under any chart, by its caption (batch 11.1)
_EXPORT_MENU = "export:"  # + country key: the format menu under that nation's chart
_IDLE = "idle"           # the options greyed out, judged once as the controls are laid out (frontend.idle_choices)
_REASONS = "reasons"     # why each greyed control is greyed, by key, judged with _IDLE (frontend.greyed_reasons, batch 29.1)
_AUTO_TICKER = "auto_ticker"  # the automatic refresh's Ticker for this visitor (batch 11.3)
_AUTO_LAID_OUT = "auto_laid_out"  # True while its fragment runs as part of the whole page's run
# The calendar's first day: the earliest date a chart shows (config.EARLIEST_DATE, batch 28.3).
_CALENDAR_FIRST = EARLIEST_DATE.date()
# Its last day: as far as the window's calendar reaches (its years to 2100).
# Today until 2026-10-28, when Terry found it would not pick the End he
# could type: a chart whose End is later than today shows a change of policy
# rate already announced for a day in it (batch 32, decision 83).
_CALENDAR_LAST = datetime.date(2100, 12, 31)
# A date field with its calendar button: room for a whole YYYY-MM-DD.
_DATE_ROW_PX = 230
# The blocks whose check boxes share rows (Terry, 2026-10-08: the nations,
# the yields, spreads, policy and mortgages, the measure; Start and End are
# on one row anyway), as in the window at its default width.
_TWO_COLUMN_BLOCKS = ("country", "rates", "units")


@dataclass(frozen=True)
class Drawing:
    """One drawing of the charts, kept in the visitor's session."""

    config: PlotConfig  # as the controls described it (an automatic start is None)
    drawn: PlotConfig | None  # with the start found; None if the drawing failed
    pngs: dict[str, bytes]  # Country.key -> PNG bytes
    figures: dict[str, Figure]  # Country.key -> the figure drawn, for the downloads in other formats (batch 11.1)
    geometry: dict[str, ChartGeometry | None]  # Country.key -> where its axes are, for zooming
    tokens: tuple[str, ...]  # the chart's command line (after the script name)
    log: str
    error: str | None  # the whole drawing failed (no start found)
    # Country.key -> why its chart alone was not drawn (a source down,
    # 2026-10-21): the other charts are drawn and shown.
    failed: dict[str, str]
    # The sources drawn from their last good copies, their own having failed,
    # each with its copy's date (batch 20, ``http._Drawing.copies_used``).
    copies: tuple[str, ...]
    seconds: float
    finished: pd.Timestamp
    # Country.key -> where its lines run and what they say, for the hover
    # read-out (batch 11.2, ``hover.payload``), deflated: sent after the PNG
    # while the read-out is on (``_chart_bytes``). Made with the drawing, so
    # ticking the box again sends it without drawing anything.
    readouts: dict[str, bytes]

    def chart_key(self, key: str) -> str:
        """The session key of ``key``'s chart in this drawing (a new drawing, a new chart: no stale box)."""
        return f"{_CHART}{key}:{self.finished.value}"


# ---------------------------------------------------------------------------
# The chart on the page: a picture that reports a box dragged over it
# ---------------------------------------------------------------------------

# Streamlit's own st.image reports no mouse events, so each chart is shown by
# this small component (Streamlit's components v2: it runs in the page
# itself, not in a frame, so the picture resizes with the page as st.image
# does). It shows the PNG bytes and, while the mouse button is held down,
# a dashed box as the window does. On release it sends the box back once,
# as fractions of the picture (0 to 1 from the left and from the top),
# whatever size the browser shows it at; _box_dragged turns that into the
# fields' texts. A click, or a drag shorter than 8 screen pixels both ways,
# sends nothing. Touch is left to scrolling the page: a finger drag on a
# chart that fills a phone's screen would otherwise trap it there. On a
# phone the buttons above the charts move the dates.
#
# The wheel over the picture (batch 24.7) zooms the dates as the window's
# does: the notches are added up (a notch is 100 of the browser's pixels,
# or 3 lines, or a page; away from the person zooms in), the zoom they make
# shown beside the pointer in the window's words, and once the wheel has
# been still for frontend.WHEEL_DELAY_MS the notches and the pointer's place
# (a fraction of the width) are sent once; _wheel_turned zooms by them. The
# page does not scroll while the wheel turns over the picture. A turn begun
# off the picture is the page's scroll, and stays so while its notches keep
# coming (gaps under the same pause), though the page brings the picture
# under the pointer: otherwise scrolling down the page with the pointer in
# the middle ended in a zoom (found in a browser, 2026-10-27; Chrome scrolls
# such a turn before the page's script sees it, and then hands it to the
# picture, not cancelable, the sign that is used). Ctrl and the
# wheel is left to the browser (its zoom, and a trackpad's pinch), and so is
# a sideways scroll. A turn not yet sent when the page runs again is dropped.
#
# Streamlit builds the component's element afresh on every run of the page
# (measured with Streamlit 1.64: a new parent element each run, and the
# function returned below called just before), so nothing is kept between
# runs: the picture's object URL is released by that function, and the
# picture is given its size from the PNG's header, so that the browser keeps
# its place while decoding it and the page does not jump.
#
# The hover read-out (batch 11.2): while it is on, the PNG's bytes are
# followed by where the chart's lines run and what they say
# (``hover.payload``), deflated (``_chart_bytes``); the script finds where
# the PNG ends (its IEND chunk) and inflates the rest with the browser's own
# DecompressionStream. ``reading``, ``nearestLine``, ``nearestSteps`` and the
# Controller follow ``hover.ChartLines.reading``, ``hover._nearest_line``,
# ``hover._nearest_steps`` and ``hover.Controller`` line for line: the read-out
# says on the page what it says in the window. Its reach is 3 of the
# screen's pixels, whatever size the picture is shown at; a touch shows nothing.
_CHART_JS = """
const MIN_DRAG = 8;
const SHOW_DELAY_MS = __SHOW_DELAY_MS__;
const HIDE_DELAY_MS = __HIDE_DELAY_MS__;
const REACH_PX = __REACH_PX__;
const OFFSET_PX = __OFFSET_PX__;
const BOX_SLACK_PX = 0.5;
const WHEEL_DELAY_MS = __WHEEL_DELAY_MS__;
const WHEEL_ZOOM_FACTOR = __WHEEL_ZOOM_FACTOR__;
const WHEEL_WORDS = __WHEEL_WORDS__;

// What is shown while the wheel turns (frontend.wheel_zoom_text).
function wheelText(notches) {
  const zoom = Math.pow(WHEEL_ZOOM_FACTOR, -notches);
  return WHEEL_WORDS[0] + (zoom >= 0.01 ? zoom.toFixed(2) : "<0.01") + WHEEL_WORDS[1];
}

// Right of the pointer and below it, turned back where that would leave the picture.
function besidePointer(element, x, y, rect) {
  const width = element.offsetWidth, height = element.offsetHeight;
  element.style.left = (x + OFFSET_PX + width <= rect.width ? x + OFFSET_PX : Math.max(x - OFFSET_PX - width, 0)) + "px";
  element.style.top = (y + OFFSET_PX + height <= rect.height ? y + OFFSET_PX : Math.max(y - OFFSET_PX - height, 0)) + "px";
}

// Where the PNG ends: after its IEND chunk. Anything after it is the read-out's data.
function pngLength(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let at = 8;
  while (at + 8 <= bytes.byteLength) {
    const length = view.getUint32(at);
    const type = String.fromCharCode(bytes[at + 4], bytes[at + 5], bytes[at + 6], bytes[at + 7]);
    at += 12 + length;
    if (type === "IEND") return at;
  }
  return bytes.byteLength;
}

// hover.payload, inflated and unpacked: each run's days and y (tenths) were sent as changes; x is the day's.
async function readLines(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
  const lines = JSON.parse(await new Response(stream).text());
  const [origin, perDay] = lines.days_to_x;
  for (const curve of lines.curves) {
    for (const run of curve.runs) {
      const count = run.d.length;
      run.day = new Array(count);
      run.x = new Float64Array(count);
      run.yy = new Float64Array(count);
      let day = 0, tenths = 0;
      for (let i = 0; i < count; i++) {
        day += run.d[i];
        tenths += run.y[i];
        run.day[i] = day;
        run.x[i] = origin + day * perDay;
        run.yy[i] = tenths / 10;
      }
      run.end = run.until === null ? null : [origin + run.until * perDay, run.until];
    }
  }
  return lines;
}

function lowerBound(xs, value) {  // the first index whose x is at least value
  let low = 0, high = xs.length;
  while (low < high) { const mid = (low + high) >> 1; if (xs[mid] < value) low = mid + 1; else high = mid; }
  return low;
}

function upperBound(xs, value) {  // the first index whose x is more than value
  let low = 0, high = xs.length;
  while (low < high) { const mid = (low + high) >> 1; if (xs[mid] <= value) low = mid + 1; else high = mid; }
  return low;
}

function inside(x, y, box) {
  const [left, top, right, bottom] = box;
  return x >= left - BOX_SLACK_PX && x <= right + BOX_SLACK_PX && y >= top - BOX_SLACK_PX && y <= bottom + BOX_SLACK_PX;
}

function nearestLine(run, px, py, reach, box) {
  const count = run.x.length;
  if (count < 2) return null;
  const low = Math.max(lowerBound(run.x, px - reach) - 1, 0);
  const high = Math.min(upperBound(run.x, px + reach), count - 1);
  let best = null;
  for (let i = low; i < high; i++) {
    const x0 = run.x[i], y0 = run.yy[i], dx = run.x[i + 1] - x0, dy = run.yy[i + 1] - y0;
    const length2 = dx * dx + dy * dy;
    const along = Math.min(Math.max(length2 > 0 ? ((px - x0) * dx + (py - y0) * dy) / length2 : 0, 0), 1);
    const cx = x0 + along * dx, cy = y0 + along * dy;
    if (!inside(cx, cy, box)) continue;
    const distance = Math.hypot(px - cx, py - cy);
    if (best === null || distance < best.distance) best = { distance, i, along };
  }
  if (best === null || !(best.distance <= reach)) return null;
  const index = best.i + (best.along >= 0.5 ? 1 : 0);
  return { distance: best.distance, x: run.x[index], y: run.yy[index], index, day: run.day[index] };
}

function nearestSteps(run, px, py, reach, box) {
  const count = run.x.length;
  const flats = run.end === null ? count - 1 : count;
  const endX = (i) => (i + 1 < count ? run.x[i + 1] : run.end[0]);
  const endDay = (i) => (i + 1 < count ? run.day[i + 1] : run.end[1]);
  const first = lowerBound(run.x, px - reach), last = upperBound(run.x, px + reach);
  const candidates = [];
  let flat = null;
  for (let i = Math.max(first - 1, 0); i < Math.min(last, flats); i++) {
    const cx = Math.min(Math.max(px, run.x[i]), endX(i)), cy = run.yy[i];
    if (!inside(cx, cy, box)) continue;
    const distance = Math.hypot(px - cx, py - cy);
    if (flat === null || distance < flat.distance) flat = { distance, i, cx, cy };
  }
  if (flat !== null) {
    const i = flat.i, span = endX(i) - run.x[i];
    const share = span > 0 ? (flat.cx - run.x[i]) / span : 0;
    const day = Math.floor(run.day[i] + share * (endDay(i) - run.day[i]));
    candidates.push({ distance: flat.distance, order: 2 * i, x: flat.cx, y: flat.cy, index: i, day });
  }
  let riser = null;
  for (let i = Math.max(first, 1); i < Math.min(last, count); i++) {
    const low = Math.min(run.yy[i - 1], run.yy[i]), high = Math.max(run.yy[i - 1], run.yy[i]);
    const cx = run.x[i], cy = Math.min(Math.max(py, low), high);
    if (!inside(cx, cy, box)) continue;
    const distance = Math.hypot(px - cx, py - cy);
    if (riser === null || distance < riser.distance) riser = { distance, i, cx, cy };
  }
  if (riser !== null) {
    candidates.push({ distance: riser.distance, order: 2 * riser.i - 1, x: riser.cx, y: riser.cy, index: riser.i, day: run.day[riser.i] });
  }
  let best = null;
  for (const found of candidates) {
    if (best === null || found.distance < best.distance || (found.distance === best.distance && found.order < best.order)) best = found;
  }
  if (best === null || !(best.distance <= reach)) return null;
  return best;
}

function dateText(day) {
  return new Date(day * 86400000).toISOString().slice(0, 10);
}

function whenText(lines, curve, run, found) {
  const day = dateText(found.day);
  if (curve.projected) return day + " (projected)";
  const observed = run.day[found.index];
  if (curve.steps && found.day !== observed) return day + " (observed " + dateText(observed) + ")";
  if (curve.quoted && lines.quote !== null && observed === lines.quote[0]) return day + lines.quote[1];
  return day;
}

// Every line within reach, the nearest first, each curve (by its name) once (hover.ChartLines.reading, batch 11.6).
function reading(lines, x, y, reach) {
  const [left, top, right, bottom] = lines.box;
  if (!(left - reach <= x && x <= right + reach && top - reach <= y && y <= bottom + reach)) return null;
  const best = new Map();
  lines.curves.forEach((curve, order) => {
    for (const run of curve.runs) {
      const found = curve.steps ? nearestSteps(run, x, y, reach, lines.box) : nearestLine(run, x, y, reach, lines.box);
      const kept = best.get(curve.name);
      if (found !== null && (kept === undefined || found.distance < kept.found.distance)) {
        best.set(curve.name, { found, order: kept === undefined ? order : kept.order, curve, run });
      }
    }
  });
  if (best.size === 0) return null;
  const ranked = [...best.values()].sort((a, b) => a.found.distance - b.found.distance || a.order - b.order);
  return ranked.map(({ found, curve, run }) => ({
    name: curve.name, color: curve.color, value: curve.texts[run.t[found.index]],
    when: whenText(lines, curve, run, found), x: found.x, y: found.y,
  }));
}

// When the read-out shows, follows the pointer and goes (hover.Controller).
class Controller {
  constructor(show, hide) {
    this.show = show; this.hide = hide; this.shown = false;
    this.waiting = null; this.showTimer = null; this.hideTimer = null;
  }
  moved(found, x, y) {
    if (found === null) {
      this.waiting = null;
      this.stopTimer("showTimer");
      if (this.shown && this.hideTimer === null) {
        this.hideTimer = setTimeout(() => { this.hideTimer = null; this.shown = false; this.hide(); }, HIDE_DELAY_MS);
      }
      return;
    }
    this.stopTimer("hideTimer");
    if (this.shown) { this.show(found, x, y); return; }
    this.waiting = [found, x, y];
    if (this.showTimer === null) {
      this.showTimer = setTimeout(() => {
        this.showTimer = null;
        if (this.waiting !== null) { this.shown = true; this.show(...this.waiting); this.waiting = null; }
      }, SHOW_DELAY_MS);
    }
  }
  stop() {
    this.waiting = null;
    this.stopTimer("showTimer");
    this.stopTimer("hideTimer");
    if (this.shown) { this.shown = false; this.hide(); }
  }
  stopTimer(name) {
    if (this[name] !== null) { clearTimeout(this[name]); this[name] = null; }
  }
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const frame = document.createElement("div");
  frame.className = "chart";
  frame.innerHTML = '<img alt="Chart" draggable="false"><div class="band"></div>'
    + '<div class="readout"></div><div class="wheel"></div>';
  parentElement.appendChild(frame);
  const img = frame.querySelector("img");
  const band = frame.querySelector(".band");
  const readout = frame.querySelector(".readout");
  const wheelBox = frame.querySelector(".wheel");
  const rings = [];  // one for each line read, made as needed

  const pngEnd = pngLength(data);
  const header = new DataView(data.buffer, data.byteOffset, 24);  // PNG: IHDR width, height at 16, 20
  // The picture's own width: img.width, once it is shown, is the width it is shown at.
  const imageWidth = header.getUint32(16);
  img.width = imageWidth;
  img.height = header.getUint32(20);
  const url = URL.createObjectURL(new Blob([data.subarray(0, pngEnd)], { type: "image/png" }));
  img.src = url;

  let lines = null;
  if (pngEnd < data.byteLength) {
    readLines(data.subarray(pngEnd)).then((read) => { lines = read; }).catch(() => {});
  }
  // Each line read: its name in its colour, its value and date under it; a ring on its point. Bordered in the nearest's colour.
  const show = (readings, x, y) => {
    const rect = img.getBoundingClientRect();
    const scale = rect.width / imageWidth;  // screen pixels per image pixel
    while (rings.length < readings.length) {
      const ring = document.createElement("div");
      ring.className = "ring";
      frame.insertBefore(ring, readout);
      rings.push(ring);
    }
    rings.forEach((ring, index) => {
      const one = readings[index];
      ring.style.display = one === undefined ? "none" : "block";
      if (one === undefined) return;
      ring.style.left = one.x * scale + "px";
      ring.style.top = one.y * scale + "px";
      ring.style.borderColor = one.color;
    });
    readout.replaceChildren(...readings.flatMap((one) => {
      const name = document.createElement("div"), value = document.createElement("div");
      name.textContent = one.name;
      name.style.color = one.color;
      value.textContent = one.value + "  " + one.when;
      return [name, value];
    }));
    readout.style.borderColor = readings[0].color;
    readout.style.display = "block";
    besidePointer(readout, x, y, rect);
  };
  const hide = () => {
    for (const ring of rings) ring.style.display = "none";
    readout.style.display = "none";
  };
  const controller = new Controller(show, hide);

  let start = null;
  const point = (event) => {
    const rect = img.getBoundingClientRect();
    return {
      x: Math.min(Math.max(event.clientX - rect.left, 0), rect.width),
      y: Math.min(Math.max(event.clientY - rect.top, 0), rect.height),
      width: rect.width,
      height: rect.height,
    };
  };
  const showBand = (a, b) => {
    band.style.left = Math.min(a.x, b.x) + "px";
    band.style.top = Math.min(a.y, b.y) + "px";
    band.style.width = Math.abs(b.x - a.x) + "px";
    band.style.height = Math.abs(b.y - a.y) + "px";
    band.style.display = "block";
  };
  img.onpointerdown = (event) => {
    controller.stop();
    if (event.pointerType === "touch" || event.button !== 0) return;
    event.preventDefault();
    img.setPointerCapture(event.pointerId);
    start = point(event);
    showBand(start, start);
  };
  img.onpointermove = (event) => {
    if (start) {
      showBand(start, point(event));
      return;
    }
    if (lines === null || event.pointerType === "touch" || event.buttons !== 0) return;
    const at = point(event);
    const perScreen = imageWidth / at.width;  // image pixels per screen pixel
    controller.moved(reading(lines, at.x * perScreen, at.y * perScreen, REACH_PX * perScreen), at.x, at.y);
  };
  img.onpointerleave = () => controller.moved(null, 0, 0);
  img.onpointerup = (event) => {
    if (!start) return;
    const a = start;
    const b = point(event);
    start = null;
    band.style.display = "none";
    if (Math.abs(b.x - a.x) < MIN_DRAG && Math.abs(b.y - a.y) < MIN_DRAG) return;
    setTriggerValue("box", {
      x0: Math.min(a.x, b.x) / b.width,
      x1: Math.max(a.x, b.x) / b.width,
      y0: Math.min(a.y, b.y) / b.height,
      y1: Math.max(a.y, b.y) / b.height,
    });
  };
  img.onpointercancel = () => {
    start = null;
    band.style.display = "none";
  };

  // A turn begun off the picture scrolls the page, and goes on scrolling it
  // while its notches keep coming, though the page brings the picture under
  // the pointer: only a turn begun on the picture zooms.
  let pageWheelAt = -Infinity;
  const pageWheel = (event) => { if (!event.composedPath().includes(img)) pageWheelAt = event.timeStamp; };
  document.addEventListener("wheel", pageWheel, { passive: true, capture: true });
  let notches = 0, wheelX = 0, wheelTimer = null;
  img.addEventListener("wheel", (event) => {
    if (event.ctrlKey || event.deltaY === 0) return;
    // Not cancelable: the browser has scrolled the page already (a turn begun
    // where nothing holds the wheel), and only then found the picture under
    // the pointer.
    if (!event.cancelable || (wheelTimer === null && event.timeStamp - pageWheelAt < WHEEL_DELAY_MS)) {
      pageWheelAt = event.timeStamp;  // the page's scroll, carried on
      return;
    }
    event.preventDefault();
    if (start) return;  // a box is being dragged
    controller.stop();
    notches -= event.deltaY / (event.deltaMode === 1 ? 3 : event.deltaMode === 2 ? 1 : 100);
    const at = point(event);
    wheelX = at.x / at.width;
    wheelBox.textContent = wheelText(notches);
    wheelBox.style.display = "block";
    besidePointer(wheelBox, at.x, at.y, img.getBoundingClientRect());
    clearTimeout(wheelTimer);
    wheelTimer = setTimeout(() => {
      wheelTimer = null;
      if (Math.abs(notches) < 0.005) {  // turned back to where it began: nothing to ask the server
        wheelBox.style.display = "none";
      } else {
        setTriggerValue("wheel", { notches: notches, x: wheelX });
      }
      notches = 0;
    }, WHEEL_DELAY_MS);
  }, { passive: false });
  return () => {
    controller.stop();
    clearTimeout(wheelTimer);
    document.removeEventListener("wheel", pageWheel, { capture: true });
    URL.revokeObjectURL(url);
  };
}
""".replace("__SHOW_DELAY_MS__", str(hover.SHOW_DELAY_MS)).replace("__HIDE_DELAY_MS__", str(hover.HIDE_DELAY_MS)).replace(
    "__REACH_PX__", str(hover.REACH_PX)
).replace("__OFFSET_PX__", str(hover.OFFSET_PX)).replace("__WHEEL_DELAY_MS__", str(WHEEL_DELAY_MS)).replace(
    "__WHEEL_ZOOM_FACTOR__", str(WHEEL_ZOOM_FACTOR)
).replace("__WHEEL_WORDS__", json.dumps(WHEEL_ZOOM_WORDS))
_CHART_CSS = f"""
.chart {{ position: relative; line-height: 0; }}
.chart img {{ width: 100%; height: auto; cursor: crosshair; user-select: none; -webkit-user-select: none; }}
.band {{
  position: absolute; display: none; box-sizing: border-box; pointer-events: none;
  border: 2px dashed #1f5fbf; background: rgba(31, 95, 191, 0.08);
}}
.ring {{
  position: absolute; display: none; box-sizing: border-box; pointer-events: none;
  width: 10px; height: 10px; margin: -5px 0 0 -5px; border: 2px solid; border-radius: 50%;
}}
.readout, .wheel {{
  position: absolute; display: none; pointer-events: none; z-index: 1; white-space: pre; line-height: 1.35;
  padding: 3px 7px; border: 1.5px solid; border-radius: 4px; font-size: 13px;
  background: {hover.BOX_FACE}; color: {hover.BOX_TEXT}; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
}}
.wheel {{ border-color: #888888; }}
"""
def _chart_component():
    """Register the chart component with the running Streamlit and return the command that shows a chart.

    Registration belongs to Streamlit's runtime, not to this module, so it is
    done on every run rather than once at import: a process may start a
    second runtime (Streamlit's AppTest does, one per test), which would not
    know the component. Registering the same definition again is silent.
    """
    return st.components.v2.component("ratesplot_chart", js=_CHART_JS, css=_CHART_CSS)


# The settings remembered (batch 24.6): a component with nothing to show,
# whose script writes the chart's command line into the cookie, encoded
# (spaces, commas and "%" are not allowed in a cookie as they are), or
# removes the cookie for the defaults, whose line is empty. It writes only
# when the cookie differs, since Streamlit lays the page out, and runs the
# script, on every change of a control.
_MEMORY_JS = """
export default function (component) {
  const { name, line, seconds } = component.data;
  const kept = document.cookie.split("; ").find((pair) => pair.startsWith(name + "="));
  const value = encodeURIComponent(line);
  if (line === "") {
    if (kept !== undefined) document.cookie = name + "=; max-age=0; path=/; SameSite=Lax";
  } else if (kept !== name + "=" + value) {
    document.cookie = name + "=" + value + "; max-age=" + seconds + "; path=/; SameSite=Lax"
      + (location.protocol === "https:" ? "; Secure" : "");
  }
}
"""


# The settings remembered, read back (batch 24.6): at the start of a visit
# whose address names no chart it can draw, the page lays out this component
# alone, and its script sends the cookie's value as it is ("" for none, or
# where the browser refuses cookies to scripts) once; the page then starts
# from it. One round trip, and nothing drawn before the answer. Its script
# runs wherever the page's charts can be shown, so the page waits for it.
_READER_JS = """
export default function (component) {
  const { data, setTriggerValue } = component;
  let value = "";
  try {
    const kept = document.cookie.split("; ").find((pair) => pair.startsWith(data.name + "="));
    if (kept !== undefined) value = kept.slice(data.name.length + 1);
  } catch (error) {
    value = "";
  }
  setTriggerValue("line", value);
}
"""


# The sidebar's width, kept only while "Remember my settings" is ticked
# (batch 31.1, as the window's column). Streamlit keeps it itself: a drag of
# the sidebar's edge writes it into the browser's localStorage under
# SIDEBAR_WIDTH_KEY, whatever the box says, and the sidebar is built at it
# at the next visit (measured 2026-10-28 in Chrome, Streamlit 1.64; nothing
# is kept before a drag). The page cannot stop that write, so this
# component, with nothing to show, laid out on every run, notes the width
# kept when the box is unticked and puts it back as the visit ends
# ("pagehide": the tab closed, the page left or reloaded), or takes it away
# if none was kept. Streamlit reads it only when it builds the sidebar, so
# the visit keeps the width dragged to. Ticked again, nothing is put back:
# the width shown stays kept, as the window keeps its column's. The note is
# the page's own (``window``), so a new visit starts with none.
SIDEBAR_WIDTH_KEY = "sidebarWidth"
_SIDEBAR_JS = """
export default function (component) {
  const { remember, key } = component.data;
  if (remember) {
    window.ratesplotSidebarKept = undefined;
  } else if (window.ratesplotSidebarKept === undefined) {
    let width = null;
    try {
      width = localStorage.getItem(key);
    } catch (error) {
      return;  // the browser keeps nothing for this page: nothing to put back
    }
    window.ratesplotSidebarKept = { width };
  }
  if (window.ratesplotSidebarPutBack === undefined) {
    window.ratesplotSidebarPutBack = () => {
      const kept = window.ratesplotSidebarKept;
      if (kept === undefined) return;
      try {
        if (kept.width === null) localStorage.removeItem(key);
        else localStorage.setItem(key, kept.width);
      } catch (error) {}
    };
    window.addEventListener("pagehide", window.ratesplotSidebarPutBack);
  }
}
"""


def _keep_sidebar_width(remember: bool) -> None:
    """Lay out the sidebar width's keeper (``_SIDEBAR_JS``): with the box unticked, the width kept is put back as the visit ends."""
    keeper = st.components.v2.component("ratesplot_sidebar", js=_SIDEBAR_JS)
    keeper(key="sidebar_width", data={"remember": remember, "key": SIDEBAR_WIDTH_KEY})


# The screen's width (batch 28.4): a component with nothing to show, whose
# script says whether the browser's window is narrower than the limit, at the
# visit's start and when it crosses it (a phone turned). It speaks only when
# its answer differs from the page's, which the page hands it, so its answer
# does not run the page again and again.
_WIDTH_JS = """
export default function (component) {
  const { data, setTriggerValue } = component;
  const tell = () => {
    const narrow = window.innerWidth < data.limit;
    if (narrow !== data.narrow) setTriggerValue("narrow", narrow);
  };
  tell();
  window.addEventListener("resize", tell);
  return () => window.removeEventListener("resize", tell);
}
"""


def _width_told() -> None:
    """The page's script has said whether the screen is narrow (``_WIDTH_JS``)."""
    st.session_state[_NARROW] = bool((st.session_state.get(_WIDTH) or {}).get("narrow"))


def _read_width() -> None:
    """Lay out the width's component; its answer, when it differs, runs the page again (``_width_told``)."""
    width = st.components.v2.component("ratesplot_width", js=_WIDTH_JS)
    width(key=_WIDTH, data={"narrow": st.session_state.get(_NARROW), "limit": PHONE_WIDTH_PX}, on_narrow_change=_width_told)


def for_screen(config: PlotConfig, narrow: bool) -> PlotConfig:
    """Return ``config`` as the page draws it on a narrow screen (batch 28.4), else as it is.

    Terry, 2026-10-28: a higher floor for the font scale, for the page alone.
    Below ``PHONE_WIDTH_PX`` the text is never smaller than
    ``PHONE_FONT_SCALE`` of its default size, and the canvas is
    ``PHONE_CANVAS_PX`` unless a size other than the default is given (the
    size field holds the default, 2048x1536, until one is). The chart's command line,
    its link and the address are the controls' as before, so they draw the
    full-size chart; the line under the chart says so.
    """
    if not narrow:
        return config
    default = (config.width_px, config.height_px) == DEFAULT_CANVAS_PX
    size = {"width_px": PHONE_CANVAS_PX[0], "height_px": PHONE_CANVAS_PX[1]} if default else {}
    return replace(config, font_floor=PHONE_FONT_SCALE, **size)


def remembered_line(value: object) -> str:
    """The command line in the cookie's value as the page's script sent it (batch 24.6), decoded as ``_MEMORY_JS`` encoded it.

    "" for anything but text.
    """
    return urllib.parse.unquote(value) if isinstance(value, str) else ""


def _remembered_line() -> str | None:
    """The command line remembered in this browser (``_READER_JS``); None until the page's script has answered."""
    heard = st.session_state.get(_HEARD)
    return None if heard is None else remembered_line(heard)


def _cookie_read() -> None:
    """The page's script has sent the cookie's value: kept for the visit's start ("" for none)."""
    sent = (st.session_state.get(_READER) or {}).get("line")
    st.session_state[_HEARD] = sent if isinstance(sent, str) else ""


def _read_remembered() -> None:
    """Ask the page's script for the cookie's value; its answer runs the page again (``_cookie_read``)."""
    reader = st.components.v2.component("ratesplot_reader", js=_READER_JS)
    reader(key=_READER, data={"name": REMEMBER_COOKIE}, on_line_change=_cookie_read)
    st.caption("Looking for the settings remembered in this browser …")


def _remember_settings(line: str) -> None:
    """Keep ``line``, the chart's command line, in this browser's cookie; "" (the defaults) removes it (batch 24.6)."""
    remember = st.components.v2.component("ratesplot_memory", js=_MEMORY_JS)
    remember(key="memory", data={"name": REMEMBER_COOKIE, "line": line, "seconds": _REMEMBER_DAYS * 86400})


def _png_size(png: bytes) -> tuple[int, int]:
    """Return a PNG's width and height in pixels, read from its header (the IHDR chunk)."""
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def _chart_bytes(drawing: Drawing, key: str) -> bytes:
    """What the chart component gets: the PNG, then, while the hover read-out is on, its data (batch 11.2).

    One payload, since the component takes one: the script finds the PNG's
    end by its IEND chunk (``_CHART_JS``), and the browser shows the PNG
    alone, the bytes drawn.
    """
    png = drawing.pngs[key]
    return png + drawing.readouts.get(key, b"") if drawing.config.hover else png


def png_part(data: bytes) -> bytes:
    """The PNG at the head of a chart component's bytes (``_chart_bytes``): its chunks up to and with IEND."""
    at = 8
    while at + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        at += 12 + length
        if kind == b"IEND":
            return data[:at]
    return data


# ---------------------------------------------------------------------------
# Process-wide setup (once per server process: imported modules are cached)
# ---------------------------------------------------------------------------


def _use_market_time_zone() -> None:
    """Make the process's local time Toronto's, so "today" is the markets' date.

    A cloud server usually runs on UTC, where "today" turns over at 20:00 in
    Toronto: the default end would then be tomorrow's date for four hours each
    evening. ``time.tzset`` exists only on Unix, so on Windows (running the
    page on Terry's own machine) the machine's own zone is kept, as the
    command line and the window keep it.
    """
    if hasattr(time, "tzset"):
        os.environ["TZ"] = MARKET_TIMEZONE
        time.tzset()


_use_market_time_zone()
http.enable_download_cache(max_age_seconds=DOWNLOAD_MAX_AGE_SECONDS)
http.enable_last_good_copies()


# ---------------------------------------------------------------------------
# Choices <-> controls
# ---------------------------------------------------------------------------


def _gui_options(kind_is_value: bool) -> list[Option]:
    """The options that have a control here, VALUE ones or the others."""
    return [option for option in OPTIONS if option.in_gui and (option.kind is Kind.VALUE) == kind_is_value]


def _value_keys() -> list[tuple[str, Option, Nation | None]]:
    """Every value control: ``(choice key, option, nation)``; a nation's own (``NATION_OPTIONS``) once for each nation."""
    shared = [(option.name, option, None) for option in _gui_options(True) if option not in NATION_OPTIONS]
    own = [(nation_choice(nation, option), option, nation) for nation in NATIONS for option in NATION_OPTIONS]
    return shared + own


def _choices_from_line(text: str) -> tuple[Choices | None, list[str]]:
    """Return the choices a command line gives, laid over the defaults; or None and its problems.

    Read as the command line is (``cli.sort_tokens``, then
    ``options.config_from_choices``), and laid over the defaults as the
    window lays a command line over them (``frontend.starting_choices``,
    with nothing remembered).
    """
    payloads, flags, unmatched, misspelled = sort_tokens(text.split())
    problems = [f"{token}: not an option" for token in unmatched] + misspelled
    if not problems:
        try:
            config = config_from_choices(payloads, flags)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        return None, problems
    return starting_choices(config, payloads, flags, {})[0], []


def _starting_choices() -> tuple[Choices, str, list[str], list[str]] | None:
    """Return a visit's starting choices, what they came from, and any problems with the address and with the settings remembered.

    The address's chart, so a shared link draws what it says; else, or if
    it cannot be read, the settings remembered in this browser (batch 24.6);
    else the defaults. What came from is "address", "remembered" or "defaults".
    None while the settings remembered are needed and the page's script has
    not yet sent them (``_read_remembered``).
    """
    address_problems: list[str] = []
    address = st.query_params.get(ADDRESS_KEY)
    if address is not None and address.strip():
        choices, address_problems = _choices_from_line(address)
        if choices is not None:
            return choices, "address", [], []
    if address is not None and not address_problems:
        # "?chart=" with nothing after it: a link to the defaults (batch 28.5).
        defaults, _notes = starting_choices(PlotConfig(), {}, {}, {})
        return defaults, "address", [], []
    remembered_problems: list[str] = []
    remembered = _remembered_line()
    if remembered is None:
        return None
    if remembered.strip():
        choices, remembered_problems = _choices_from_line(remembered)
        if choices is not None:
            return choices, "remembered", address_problems, []
    defaults, _notes = starting_choices(PlotConfig(), {}, {}, {})
    return defaults, "defaults", address_problems, remembered_problems


def _load_choices(choices: Choices) -> None:
    """Set every control from ``choices``."""
    payloads, flags = choices
    for key, option, nation in _value_keys():
        if option.editor == "levels":
            letters = level_letters(payloads.get(key, ""), nation)
            for letter, _caption in nation.level_boxes:
                st.session_state[_LEVEL + nation.key + ":" + letter] = letter in letters
        elif option.editor == "choices":
            text = payloads.get(key, "")
            rows = choice_rows(option, text, nation)
            st.session_state[_CHOICE_OTHERS + key] = [value for value, _box in rows[-1][1]] if rows[-1][0] == "other" else []
            ticked = choice_values(option, text, nation)
            for _caption, boxes in rows:
                for value, _box in boxes:
                    st.session_state[_CHOICE + key + ":" + value] = value in ticked
        else:
            st.session_state[_VALUE + key] = payloads.get(key, "")
            if option.editor == "size":
                _size_boxes_from_text(key)
    for option in _gui_options(kind_is_value=False):
        st.session_state[_FLAG + option.name] = bool(flags.get(option.name, False))
    _set_all_ticks({name: bool(flags.get(all_tick(name), False)) for name in LIMITS})


def _limit_keys(name: str) -> list[str]:
    """Every nation's field of limit ``name`` ("cdn:max", "us:max", ...)."""
    return [nation_choice(nation, by_name(name)) for nation in NATIONS]


def _set_all_ticks(ticks: dict[str, bool]) -> None:
    """Tick or untick each limit's "All" (name -> ticked) in every nation's section: one tick, shown in each (batch 18.2)."""
    for name, ticked in ticks.items():
        for key in _limit_keys(name):
            st.session_state[_ALL + key] = ticked


def _snapshot() -> Choices:
    """Return every control's value, blanks included, as the window's ``_snapshot`` does."""
    payloads: dict[str, str] = {}
    for key, option, nation in _value_keys():
        if option.editor == "levels":
            ticked = [letter for letter, _caption in nation.level_boxes if st.session_state.get(_LEVEL + nation.key + ":" + letter, False)]
            payloads[key] = level_text(ticked)
        elif option.editor == "choices":
            ticked = [
                value for value in _choice_values_offered(key) if st.session_state.get(_CHOICE + key + ":" + value, False)
            ]
            payloads[key] = choices_text(option, ticked)
        else:
            payloads[key] = st.session_state.get(_VALUE + key, "")
    flags = {option.name: bool(st.session_state.get(_FLAG + option.name, False)) for option in _gui_options(False)}
    # The "All" ticks, as the window keeps them (batch 18.2): every nation's box shows the one tick.
    for name in LIMITS:
        flags[all_tick(name)] = any(st.session_state.get(_ALL + key, False) for key in _limit_keys(name))
    return payloads, flags


def _config_for(choices: Choices) -> tuple[PlotConfig | None, list[str]]:
    """Return the PlotConfig the controls describe, or None and the problems, each naming its field.

    The fields in the wrong are those of the window (``frontend.field_problems``):
    a problem between two (Min not below Max) is on the one changed last.
    They are kept for the labels (``_WRONG``); a problem no field is
    involved in (-r with -p) is reported alone.
    """
    flags = choices[1]
    # A greyed field has no effect: a bad text left there must not stop the drawing (as in the window).
    payloads = drawn_payloads(*choices)
    wrong = field_problems(payloads, flags, st.session_state.get(_CHANGED, []))
    st.session_state[_WRONG] = wrong
    problems = [problem_text(key, message) for key, message in wrong.items()]
    try:
        return config_from_choices(payloads, flags), problems
    except ValueError as exc:
        return None, problems or [str(exc)]


# ---------------------------------------------------------------------------
# Control callbacks (they run before the page is drawn again)
# ---------------------------------------------------------------------------


def _country_changed(name: str) -> None:
    """Keep at least one country ticked (the command line's "none means both" would look like a bug); note one ticked.

    A nation ticked by hand gets its tab once its chart is drawn (batch
    17.4, ``_show``); unticked before that, it does not.
    """
    countries = [option.name for option in options_in("country") if option.in_gui]
    if not any(st.session_state[_FLAG + country] for country in countries):
        st.session_state[_FLAG + name] = True
        st.session_state[_NOTICE] = "At least one country must stay selected."
        return
    key = nation_boxes()[name]
    if st.session_state[_FLAG + name]:
        st.session_state[_TICKED] = key
    elif st.session_state.get(_TICKED) == key:
        del st.session_state[_TICKED]


def _measure_changed(name: str) -> None:
    """One measure at a time; Top and Bottom are in the measure's units, so they are cleared."""
    units = [option.name for option in options_in("units") if option.in_gui]
    if st.session_state[_FLAG + name]:
        for other in units:
            if other != name:
                st.session_state[_FLAG + other] = False
    for bound in bound_keys():
        st.session_state[_VALUE + bound] = ""


def _curve_changed(_name: str) -> None:
    """A curve ticked or unticked can give -r its effect or take it away: clear Top and Bottom in the other unit."""
    for bound in bounds_in_other_units(*_snapshot()):
        st.session_state[_VALUE + bound] = ""


def _remember_view(lock: bool = False) -> None:
    """Keep the controls' choices for Back and Unzoom (at most ``_HISTORY_LIMIT``, the first always kept).

    ``lock``: keep the aspect-ratio lock too (a Reset changes it); each step
    is ``(choices, lock or None)``.
    """
    history = st.session_state.setdefault(_HISTORY, [])
    history.append((_snapshot(), st.session_state.get(_SIZE + "lock", True) if lock else None))
    trim_history(history, _HISTORY_LIMIT)


def _unzoomed() -> bool:
    """True when there is no view before the first zoom or move since the last Reset to go back to, or it is the one shown (``frontend.unzoom_target``), as in the window."""
    history = st.session_state.get(_HISTORY) or []
    target = unzoom_target(history)
    return target is None or history[target][0] == _snapshot()


def _set_lock(lock: bool) -> None:
    """Tick or untick the aspect-ratio lock; ticked, it keeps the boxes' shape now."""
    st.session_state[_SIZE + "lock"] = lock
    if lock:
        _remember_ratio()


def _choice_values_offered(key: str) -> list[str]:
    """Every value a list control has a box for now: those offered, then any others given (``_CHOICE_OTHERS``)."""
    _key, option, nation = next(entry for entry in _value_keys() if entry[0] == key)
    offered = [value for _caption, boxes in choice_rows(option, "", nation) for value, _box in boxes]
    return offered + st.session_state.get(_CHOICE_OTHERS + key, [])


def _choice_changed(key: str, value: str) -> None:
    """Keep at least one box of a list ticked: drawing none is the curve's own box (``choice_refusal``)."""
    if not any(st.session_state.get(_CHOICE + key + ":" + item, False) for item in _choice_values_offered(key)):
        st.session_state[_CHOICE + key + ":" + value] = True
        st.session_state[_NOTICE] = choice_refusal(option_of(key))


def _reset() -> None:
    """The default charts for the nations ticked, and the aspect-ratio lock ticked, as in the window (Back undoes both).

    Terry, 2026-10-20 (batch 17.5): Reset leaves the nation boxes alone
    (``frontend.reset_choices``).
    """
    _remember_view(lock=True)
    _load_choices(reset_choices(_snapshot()[1]))
    _set_lock(True)
    st.query_params.clear()


def _force_redraw() -> None:
    st.session_state[_FORCE] = True


def _apply_view(updates: dict[str, str], key: str | None = None) -> None:
    """Write a zoom's or a date move's texts into the fields, undoably (Back), as the window does.

    Nothing is kept for Back when the fields already say it (e.g. Zoom out
    from 1600 to today). The axis limits go into the fields of the chart's
    own nation (``key``); the dates are the same for every chart.
    """
    nation = next((nation for nation in NATIONS if nation.key == key), None)
    own = {option.name for option in NATION_OPTIONS}
    updates = {nation_choice(nation, option_of(name)) if nation and name in own else name: text for name, text in updates.items()}
    payloads, flags = _snapshot()
    if all(payloads.get(name, "") == text for name, text in updates.items()):
        return
    _remember_view()
    # A limit whose "All" is ticked goes into every nation's field (batch 18.2).
    for name, text in {**updates, **limit_copies(updates, flags)}.items():
        st.session_state[_VALUE + name] = text


def _box_dragged(key: str) -> None:
    """A box was dragged on ``key``'s chart: zoom to it, by the window's rules (``frontend.zoom_updates``)."""
    drawing: Drawing | None = st.session_state.get(_DRAWING)
    if drawing is None or drawing.geometry.get(key) is None:
        return
    box = (st.session_state.get(drawing.chart_key(key)) or {}).get("box")
    if not box:
        return
    width, height = _png_size(drawing.pngs[key])
    _apply_view(
        zoom_updates(
            drawing.geometry[key],
            drawing.drawn.for_nation(key) if drawing.drawn is not None else None,
            box["x0"] * width,
            box["y0"] * height,
            box["x1"] * width,
            box["y1"] * height,
        ),
        key,
    )


def _wheel_zoom(drawing: Drawing, key: str, wheel: object) -> dict[str, str] | None:
    """Return the Start and End texts for a turn of the wheel over ``key``'s chart, or None for a turn that is no turn.

    The page's script sends the notches (positive away from the person) and
    the pointer's place as a fraction of the picture's width. They come from
    the browser, so a turn that is not two numbers, or none, is ignored, the
    place is kept to the picture and the notches to ``_WHEEL_MAX_NOTCHES``
    either way; then the window's rule (``frontend.scale_dates_updates``).
    """
    try:
        notches, x = float(wheel["notches"]), float(wheel["x"])
    except (TypeError, KeyError, ValueError):
        return None
    if not (math.isfinite(notches) and math.isfinite(x)) or notches == 0:
        return None
    notches = min(max(notches, -_WHEEL_MAX_NOTCHES), _WHEEL_MAX_NOTCHES)
    width, _height = _png_size(drawing.pngs[key])
    return scale_dates_updates(drawing.geometry[key], WHEEL_ZOOM_FACTOR ** notches, min(max(x, 0.0), 1.0) * width)


def _wheel_turned(key: str) -> None:
    """The wheel was turned over ``key``'s chart and is still: zoom the dates about the pointer, as the window does (batch 24.7)."""
    drawing: Drawing | None = st.session_state.get(_DRAWING)
    if drawing is None or drawing.geometry.get(key) is None:
        return
    updates = _wheel_zoom(drawing, key, (st.session_state.get(drawing.chart_key(key)) or {}).get("wheel"))
    if updates:
        _apply_view(updates)


def _move_dates(shift: float, scale: float) -> None:
    """Move or rescale the dates drawn (``frontend.move_dates_updates``): the buttons over the charts."""
    drawing: Drawing | None = st.session_state.get(_DRAWING)
    if drawing is not None and drawing.drawn is not None:
        _apply_view(move_dates_updates(drawing.drawn.start, drawing.drawn.end, shift=shift, scale=scale))


def _back() -> None:
    history = st.session_state.get(_HISTORY)
    if history:
        choices, lock = history.pop()
        _load_choices(choices)
        if lock is not None:
            _set_lock(lock)


def _unzoom() -> None:
    """Return to the charts before the first zoom or move since the last Reset: one more step, so Back returns to the zoom."""
    if not _unzoomed():
        history = st.session_state[_HISTORY]
        first = history[unzoom_target(history)][0]
        _remember_view()
        _load_choices(first)


# ---------------------------------------------------------------------------
# The controls
# ---------------------------------------------------------------------------


def _help(option: Option, extra: str = "", key: str | None = None) -> str:
    """The option's help, as the window's ⓘ panel: one paragraph per line (Markdown), then why it is greyed and More.

    Batch 29.1 (decision 76): the "?" stays live while its control is
    greyed (measured 2026-10-27), so its tip says why the control is greyed
    now (``frontend.greyed_reasons``, judged as the controls are laid out),
    and ends with a link to the option's topic where it has one, opened
    alone in a new tab (``_show_help``). ``key`` names a nation's own control
    ("us:max"), else the option's.
    """
    reason = st.session_state.get(_REASONS, {}).get(key or option.name, "")
    more = f"[More]({help_address(option.topic)})" if option.topic else ""
    return "\n\n".join(line for line in (*option_help_lines(option), extra, greyed_line(reason), more) if line)


def _flag_control(where, option: Option) -> None:
    callbacks = {"country": _country_changed, "units": _measure_changed, "curves": _curve_changed}
    callback = callbacks.get(option.group)
    where.checkbox(
        option.label,
        key=_FLAG + option.name,
        help=_help(option),
        on_change=callback,
        args=(option.name,) if callback else None,
        # What has no effect is greyed, its tick kept (frontend.idle_choices):
        # GDP under -r, where it is the divisor; % of GDP, Per capita and the
        # regression segments with no curve to act on; the automatic refresh
        # where it can bring nothing new.
        disabled=option.name in _idle(),
    )


def _idle() -> frozenset[str]:
    """The options greyed out for the controls' state now (``frontend.idle_choices``), as in the window.

    Judged once as the sidebar is laid out (``_controls``): the automatic
    refresh's rule builds the choices' config (batch 11.3).
    """
    idle = st.session_state.get(_IDLE)
    return idle_choices(*_snapshot()) if idle is None else idle


def _field_changed(key: str) -> None:
    """Record a field changed by hand, last (``_CHANGED``)."""
    changed = [other for other in st.session_state.get(_CHANGED, []) if other != key]
    st.session_state[_CHANGED] = [*changed, key]


def _field_typed(key: str) -> None:
    """A text field changed by hand (Enter, or the box left): a number typed without its 0 gets it, then it is recorded.

    ".3" becomes "0.3" in the box, and so in the address and the command
    line (Terry, 2026-10-13, batch 15.5; ``frontend.with_leading_zero``).
    """
    st.session_state[_VALUE + key] = with_leading_zero(st.session_state.get(_VALUE + key, ""))
    _field_changed(key)
    # A limit whose "All" is ticked goes into every nation's box (batch 18.2);
    # a blank unticks it instead, when the page settles (``_settle_all_ticks``).
    # A text box reports only on Enter or when left, as decision 47 asks.
    payloads, flags = _snapshot()
    for other, text in limit_copies({key: payloads[key]}, flags).items():
        st.session_state[_VALUE + other] = text


def _all_changed(key: str) -> None:
    """The "All" box beside ``key``'s limit field ticked or unticked: the same in every nation's section (batch 18.2).

    Ticked, the field's value goes into every other nation's field of the
    limit (``frontend.limit_copies``); unticked, each keeps its value, as in
    the window (``gui._all_ticked``).
    """
    ticked = bool(st.session_state.get(_ALL + key, False))
    _set_all_ticks({option_of(key).name: ticked})
    payloads, flags = _snapshot()
    for other, text in limit_copies({key: payloads[key]}, flags).items():
        st.session_state[_VALUE + other] = text


def _settle_all_ticks() -> None:
    """Untick the "All" ticks whose rule no longer holds (``frontend.settled_all_ticks``), before the controls are laid out.

    One nation ticked, a field blanked (the page has only what a field
    reported on Enter or when left), Top and Bottom out of % of GDP.
    """
    payloads, flags = _snapshot()
    _set_all_ticks({name: settled_all_ticks(payloads, flags)[all_tick(name)] for name in LIMITS})


def _red_if_wrong(label: str, wrong: bool) -> str:
    """A field's label, red while the field is in the wrong (Streamlit cannot colour the text in a box)."""
    return f":red[{label}]" if wrong else label


def _value_control(where, option: Option, key: str | None = None, label: str | None = None, width: int | str = "stretch") -> None:
    """A text field; ``key`` names a nation's own field ("us:max"), else the option's name.

    Blank, it shows the value in effect in grey (the placeholder): the
    last drawing's (``_HINTS``), or before any drawing what blank means.
    ``label`` replaces the option's label (a margin's "margin (pts)" beside
    its term's box). Greyed while its flag is off, while it has no curve to
    act on, and a nation's margin while its chart draws not its term, the
    prime rate (``frontend.idle_nation_keys``), as in the window.
    """
    key = key or option.name
    flag_off = option.turns_on is not None and not st.session_state.get(_FLAG + option.turns_on, False)
    where.text_input(
        _red_if_wrong(option.label if label is None else label, key in st.session_state.get(_WRONG, {})),
        key=_VALUE + key,
        on_change=_field_typed,
        args=(key,),
        help=_help(option, "Blank = default (shown in grey).", key),
        placeholder=st.session_state.get(_HINTS, {}).get(key) or _PLACEHOLDERS.get(option.name, _DEFAULT_PLACEHOLDER),
        disabled=flag_off or option.name in _idle() or key in idle_nation_keys(*_snapshot()),
        width=width,
    )


def _field_date(option: Option) -> datetime.date | None:
    """The date a date field names now, for its calendar; None if blank, unreadable or outside the calendar's range."""
    text = st.session_state.get(_VALUE + option.name, "").strip()
    try:
        date = parse_date_spec(text, kind=option.name).date() if text else None
    except ValueError:
        return None
    return date if date is not None and _CALENDAR_FIRST <= date <= _CALENDAR_LAST else None


def _date_picked(name: str) -> None:
    """A day was picked in a field's calendar: write it in the field (a cleared calendar changes nothing)."""
    picked = st.session_state.get(_CALENDAR + name)
    if picked is not None:
        st.session_state[_VALUE + name] = f"{picked:%Y-%m-%d}"
        _field_changed(name)


def _date_blanked(name: str) -> None:
    st.session_state[_VALUE + name] = ""
    _field_changed(name)


def _date_control(where, option: Option) -> None:
    """A date field with a calendar button beside it, as in the window.

    Picking a day writes ``YYYY-MM-DD`` in the field, which stays the single
    source of truth (typing ``YYYY`` or ``YYYY-MM`` still works); "Blank"
    empties it, meaning the option's default (today for the end; for the
    start, ``config.DEFAULT_START_FLOOR`` or the first date on which every
    chosen curve has data, if later). The
    calendar opens at the field's date: it is set from the field on every
    run, before it is drawn.
    """
    # One row that never wraps (st.columns would put the button under the
    # field on a phone); the field takes the room the button leaves. Its
    # width is a date's and the button's, so two such rows share a line
    # only when both fit (``_controls``).
    row = where.container(horizontal=True, wrap=False, vertical_alignment="bottom", width=_DATE_ROW_PX)
    _value_control(row, option)
    with row.popover("📅", help="Pick a date from a calendar"):
        st.session_state[_CALENDAR + option.name] = _field_date(option)
        st.date_input(
            option.label,
            key=_CALENDAR + option.name,
            min_value=_CALENDAR_FIRST,
            max_value=_CALENDAR_LAST,
            format="YYYY-MM-DD",
            on_change=_date_picked,
            args=(option.name,),
        )
        st.button(
            "Blank (default)",
            key=f"blank:{option.name}",
            on_click=_date_blanked,
            args=(option.name,),
            help=_PLACEHOLDERS.get(option.name, _DEFAULT_PLACEHOLDER).capitalize() + " when blank.",
            # Greyed while the field is blank already, where it would do nothing (batch 28.1).
            disabled=not st.session_state.get(_VALUE + option.name, "").strip(),
        )


def _pixels(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdigit() and int(text) > 0 else None


def _remember_ratio() -> None:
    """Take the boxes' shape as the one the lock keeps (width / height), if both are numbers."""
    width = _pixels(st.session_state.get(_SIZE + "width", ""))
    height = _pixels(st.session_state.get(_SIZE + "height", ""))
    if width and height:
        st.session_state[_SIZE + "ratio"] = width / height


def _size_boxes_from_text(name: str) -> None:
    """Show a ``WxH`` text set from elsewhere (the address, Back, Reset) in the boxes, and take its shape.

    As in the window: one dimension alone means 4:3 on the command line, so
    the other box shows the size that implies.
    """
    text = st.session_state.get(_VALUE + name, "").strip().lower()
    width, height = (part.strip() for part in text.split("x", 1)) if "x" in text else (text, "")
    if width.isdigit() and not height:
        height = str(round(int(width) * 3 / 4))
    elif height.isdigit() and not width:
        width = str(round(int(height) * 4 / 3))
    st.session_state[_SIZE + "width"] = width
    st.session_state[_SIZE + "height"] = height
    _remember_ratio()


def _size_box_changed(name: str, which: str) -> None:
    """A Size box changed: with the lock on, set the other from the kept shape; then write the ``WxH`` text."""
    state = st.session_state
    ratio = state.get(_SIZE + "ratio")
    if state.get(_SIZE + "lock", True) and ratio:
        other = "height" if which == "width" else "width"
        value = _pixels(state[_SIZE + which])
        if value is not None:
            state[_SIZE + other] = str(max(1, round(value / ratio if which == "width" else value * ratio)))
        elif not state[_SIZE + which].strip():
            state[_SIZE + other] = ""
    else:
        _remember_ratio()
    width, height = state[_SIZE + "width"].strip(), state[_SIZE + "height"].strip()
    state[_VALUE + name] = f"{width}x{height}" if width and height else width or (f"x{height}" if height else "")
    _field_changed(name)


def _size_lock_changed() -> None:
    # Ticking the lock keeps the shape the boxes have now.
    if st.session_state[_SIZE + "lock"]:
        _remember_ratio()


def _size_control(where, option: Option) -> None:
    """Width and height boxes and a "Preserve aspect ratio" lock, as in the window (``gui._SizeEditor``).

    Terry, 2026-09-30: "if you have a chart shape you like, and have saved to
    PNG, but you need an upscaled or downscaled version of it, you can just
    change one number and the other automatically adjusts." The option's own
    ``WxH`` text (``_VALUE`` + name, the command-line form) stays the single
    source of truth for drawing, the address, Back and Reset; the boxes are a
    view of it and write it back. With the lock on (the default), changing
    one box sets the other from the shape the pair had when the lock was
    ticked or the size was loaded, so repeated edits do not drift; with it
    off, each box changes alone. A blank box with the other filled keeps the
    command line's meaning: 4:3 from the one given.
    """
    st.session_state.setdefault(_SIZE + "lock", True)
    tip = _help(option, "Width and height in pixels. Blank = default.")
    row = where.container(horizontal=True, wrap=False)
    wrong = st.session_state.get(_WRONG, {})
    # Which box is wrong, red alone (Terry, 2026-10-12: he was not sure at once which was).
    faults = size_boxes_at_fault(st.session_state.get(_VALUE + option.name, "")) if option.name in wrong else (False, False)
    for (which, placeholder), fault in zip((("width", PlotConfig().width_px), ("height", PlotConfig().height_px)), faults):
        row.text_input(
            _red_if_wrong(f"{which.capitalize()} (px)", fault),
            key=_SIZE + which,
            help=tip,
            placeholder=str(placeholder),
            on_change=_size_box_changed,
            args=(option.name, which),
        )
    where.checkbox(
        "Preserve aspect ratio",
        key=_SIZE + "lock",
        on_change=_size_lock_changed,
        help="When ticked, changing one box changes the other to keep the current shape.",
    )


def _levels_control(where, option: Option, nation: Nation) -> None:
    """A nation's "By level" over its boxes, named for its governments, as many to a row as fit.

    Batch 10.5 (Terry, 2026-10-13): in each nation's section, its own boxes
    (``Nation.level_boxes``), where the column had one control for every
    chart. A row that wraps, as the nations' and the rates' (``_controls``;
    the window's rule, Terry, 2026-10-14, batch 15.2).
    """
    where.markdown(f"**{option.label}**", help=_help(option, "None ticked = debt and interest in total.", nation_choice(nation, option)))
    idle = option.name in _idle()  # greyed without debt or interest, as in the window
    row = where.container(horizontal=True, wrap=True)
    for letter, caption in nation.level_boxes:
        row.checkbox(caption, key=_LEVEL + nation.key + ":" + letter, disabled=idle)


def _choices_control(where, option: Option, nation: Nation | None = None) -> None:
    """A list option as tick boxes (``Option.choices``): a row of boxes per row offered, with its caption.

    One that belongs to a flag (mortgage terms, spreads) is greyed while
    the flag is off, as its field was, the yield terms while the yields are
    off (``frontend.idle_controls``, batch 28.1), and the UK's aggregate
    debts while none is drawn (``frontend.idle_nation_keys``). A nation's own list has its label
    always, and only the boxes its chart can draw (``frontend.choice_rows``).
    The boxes of a row flow, wrapping when the sidebar is narrow, and the
    help is on the list's label alone: a column per box, each with its "?",
    left no room for the text at the sidebar's narrow default width
    (2026-10-13: Canada's yield terms showed only their "?", the spreads
    "10…").
    """
    key = nation_choice(nation, option) if nation else option.name
    disabled = option.turns_on is not None and not st.session_state.get(_FLAG + option.turns_on, False)
    disabled = disabled or option.name in _idle() or key in idle_nation_keys(*_snapshot())
    if option.turns_on is None or nation is not None:
        where.markdown(f"**{option.label}**", help=_help(option, key=key))
    others = st.session_state.get(_CHOICE_OTHERS + key, [])
    rows = [row for row in choice_rows(option, "", nation)]
    if others:
        rows.append(("other", [(value, value.replace("-", "–")) for value in others]))
    for caption, boxes in rows:
        if caption:
            where.caption(caption)
        # A nation's box of a term drawn plus a margin has the margin's field
        # beside it (batch 9.4, the prime rate's), as in the window.
        margins = margin_options() if nation is not None and option.fields == ("mortgage_terms",) else {}
        margin = next((margins[value] for value, _text in boxes if value in margins), None)
        row = where.container(horizontal=True, wrap=True, vertical_alignment="bottom" if margin else "top")
        for value, text in boxes:
            row.checkbox(
                text,
                key=_CHOICE + key + ":" + value,
                disabled=disabled,
                on_change=_choice_changed,
                args=(key, value),
            )
        if margin:
            _value_control(row, margin, key=nation_choice(nation, margin), label="margin (pts)", width=_MARGIN_FIELD_PX)


def _field_hints() -> dict[str, str]:
    """The grey values from the last drawing that succeeded (``frontend.field_hints``), as the window shows them."""
    drawing: Drawing | None = st.session_state.get(_DRAWING)
    if drawing is None or drawing.drawn is None:
        return field_hints(None, {})
    return field_hints(drawing.drawn, drawing.geometry)


def _controls() -> None:
    """The sidebar: two buttons, then the column's blocks (``frontend.control_blocks``), all from the table.

    In the window's order (Terry, 2026-10-08, batch 7). A block with no
    title (the regression segments; the line labels with the latest data)
    is set off by a line alone.
    """
    bar = st.sidebar
    bar.caption(version_text())  # the version, small and grey at the top left (batch 11.7)
    buttons = bar.columns(2)
    # One button, as in the window (Terry, 2026-10-08: "Refresh", meaning
    # reload data): a drawing after a change of the controls is automatic.
    buttons[0].button("Refresh", on_click=_force_redraw, help=REFRESH_HELP, width="stretch")
    # Greyed at the defaults, the size lock ticked among them, where it would do nothing (batch 28.1).
    at_reset = reset_changes_nothing(_snapshot()) and st.session_state.get(_SIZE + "lock", True)
    buttons[1].button("Reset", on_click=_reset, help=RESET_HELP, width="stretch", disabled=at_reset)
    # Changing it draws nothing: it governs only the cookie (batch 24.6).
    bar.checkbox(REMEMBER_LABEL, key=_REMEMBER, help=REMEMBER_HELP)
    bar.caption(_REMEMBER_LINE)
    st.session_state[_HINTS] = _field_hints()
    _settle_all_ticks()  # before the "All" boxes are laid out, which fixes their state for this run
    st.session_state[_IDLE] = idle_choices(*_snapshot())
    every = _snapshot()
    st.session_state[_REASONS] = greyed_reasons([*every[0], *every[1]], *every)
    for key, title, members in control_blocks():
        if title:
            bar.subheader(title, divider="gray")
        else:
            bar.divider()
        # A value that belongs to a flag goes right under it (the tolerance
        # under "Regression segments"), as on the window's row.
        attached = {option.turns_on: option for option in members if option.kind is Kind.VALUE and option.turns_on}
        values = [option for option in members if option.kind is Kind.VALUE and option not in attached.values()]
        flags = [option for option in members if option.kind is not Kind.VALUE]
        if key in _TWO_COLUMN_BLOCKS and not attached:
            # As many to a row as fit, as in the window (Terry, 2026-10-08):
            # two at the sidebar's default width, more when it is dragged
            # wider, one on a phone; each row filled before the next, so
            # four may go three and one (Terry, 2026-10-14, batch 15.2). A
            # row that wraps, each box as wide as its text: fixed columns cut
            # "United States" to "United Sta…" there.
            row = bar.container(horizontal=True, wrap=True)
            for option in flags:
                _flag_control(row, option)
            flags = []
        for option in flags:
            _flag_control(bar, option)
            if option.name in attached and attached[option.name].editor == "choices":
                # Straight in the sidebar: Streamlit allows no columns inside its columns there.
                _choices_control(bar, attached[option.name])
            elif option.name in attached:
                _value_control(bar.columns([1, 12])[1], attached[option.name])
        # Start and End side by side when the sidebar is wide enough for
        # both to show a whole date, else one under the other (two columns
        # of the default sidebar left "2000-01-01" showing "200"); other text
        # fields two to a row (Max and Min, Top and Bottom).
        dates = [option for option in values if option.editor == "date"]
        row = bar.container(horizontal=True, wrap=True) if dates else None
        for option in dates:
            _date_control(row, option)
        paired = [option for option in values if option.editor not in ("date", "levels", "size", "choices")]
        for index in range(0, len(paired), 2):
            for column, option in zip(bar.columns(2), paired[index:index + 2]):
                _value_control(column, option)
        for option in values:
            if option.editor == "choices":
                _choices_control(bar, option)
            elif option.editor == "size":
                _size_control(bar, option)
    # Only a ticked nation's section, as the window shows a tab only for a
    # ticked nation (batch 28.1). Terry, 2026-10-26: "remove the national
    # sub-panel from the interface completely, if the box isn't ticked, as
    # eventually there will be many national tick-boxes, and it is annoying
    # to have to scroll through them all looking for the one you want". An
    # unticked nation keeps its values for when it is ticked again.
    flags = _snapshot()[1]
    boxes = {key: name for name, key in nation_boxes().items()}
    for nation in NATIONS:
        if flags.get(boxes[nation.key], False):
            _nation_controls(bar, nation)
        else:
            _keep_section(nation)


def _keep_section(nation: Nation) -> None:
    """Keep the values of ``nation``'s section through a run that does not lay it out (batch 28.1).

    Streamlit forgets a widget's value at the end of a run that does not lay
    the widget out; a value assigned to its own key first is kept (its
    documented way). Its terms' boxes, its levels, its limits, their "All"
    boxes and its margins: every key of the section, by its prefix.
    """
    prefixes = tuple(prefix + nation.key + ":" for prefix in (_VALUE, _CHOICE, _LEVEL, _ALL))
    for key in [key for key in st.session_state if key.startswith(prefixes)]:
        st.session_state[key] = st.session_state[key]


def _nation_controls(bar, nation: Nation) -> None:
    """A nation's own section (``frontend.NATION_OPTIONS``), as the panel under its tab in the window.

    Its yield terms, spreads, policy terms and mortgage terms (only those its
    chart can draw), the UK's aggregate debts (batch 10.4), its levels of
    government (batch 10.5), in the window's
    order (``frontend.panel_lists``), then its axis limits as in the window: the yield axis's Max above
    its Min, beside the right axis's Top above its Bottom (Terry, 2026-10-12;
    ``LIMIT_COLUMNS``), each field with its unit and its "All" box on its
    right (batch 18, ``_limit_control``).
    """
    bar.subheader(f"{nation.name} only", divider="gray")
    for option in panel_lists(nation):
        if option.editor == "levels":
            _levels_control(bar, option, nation)
        else:
            _choices_control(bar, option, nation)
    for row in zip(*LIMIT_COLUMNS):  # (max, top), then (min, bottom)
        for column, name in zip(bar.columns(2), row):
            _limit_control(column, nation, by_name(name))


def _limit_control(where, nation: Nation, option: Option) -> None:
    """A nation's axis limit field, then right of it its unit and its "All" box, as in the window (batch 18).

    Terry, 2026-10-14: the unit symbol "immediately to the right" of the box
    (``frontend.limit_unit``: "%", the nation's currency, blank for % of
    GDP), then an "All" tick that copies the value to every nation's field
    and keeps them alike while ticked (``_all_changed``), greyed where it
    cannot be given (``frontend.all_tick_offered``). The three in a row
    aligned at the bottom, so the unit and the box sit level with the field.
    """
    key = nation_choice(nation, option)
    payloads, flags = _snapshot()
    unoffered = all_tick_reason(payloads, flags, key)  # "" while its "All" can be ticked (frontend.all_tick_offered)
    row = where.container(horizontal=True, vertical_alignment="bottom", gap="small")
    _value_control(row, option, key=key, width=_LIMIT_FIELD_PX)
    # Kept as wide as the widest symbol ("C$"), so the "All" boxes line up,
    # and raised from the row's bottom to the middle of the field: the
    # field's own element runs on below it (measured 2026-10-23, Streamlit
    # 1.64: the symbol's middle 15 px below the field's at 0.5rem). In an
    # HTML block, where Markdown takes no "$" for the start of a formula and
    # an escape would show.
    symbol = limit_unit(nation, option.name, flags) or "&nbsp;"
    row.markdown(f'<div style="padding-bottom: 1.4rem">{symbol}</div>', unsafe_allow_html=True, width=20)
    row.checkbox(
        "All",
        key=_ALL + key,
        on_change=_all_changed,
        args=(key,),
        disabled=bool(unoffered),
        help="\n\n".join(line for line in (
            f"This {option.label} for every nation's chart. Ticked, the value goes into every nation's field, and a value "
            "entered in any of them goes into the others; unticked, each keeps its own. Top and Bottom go with their "
            "currency (20t from the U.S. field as USD20t), each chart converting them at the rate of its end date. "
            "Greyed while the field is blank or only one nation is ticked.",
            greyed_line(unoffered),  # why it is greyed now (batch 29.1)
        ) if line),
    )


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _draw(config: PlotConfig, tokens: tuple[str, ...]) -> Drawing:
    """Draw every chosen country's chart for ``config``; never raises (a failure is in the Drawing).

    A chart that cannot be drawn (its source down: FRED's maintenance page,
    2026-10-21, took every chart with it) is named in ``Drawing.failed`` and
    the others are drawn. A source that fails but has a last good copy is
    drawn from it, and named in ``Drawing.copies`` (batch 20).
    """
    lines: list[str] = []
    began = time.perf_counter()
    source = "the automatic start" if config.start is None else f"{config.start:%Y-%m-%d}"
    lines.append(f"--- drawing {config.width_px}x{config.height_px}, {source} to {config.end:%Y-%m-%d}\n")
    drawn: PlotConfig | None = None
    pngs: dict[str, bytes] = {}
    figures: dict[str, Figure] = {}
    geometry: dict[str, ChartGeometry | None] = {}
    readouts: dict[str, bytes] = {}
    error: str | None = None
    failed: dict[str, str] = {}
    # Each real download logged, and those reused counted, once the lock is held (http.drawing_downloads).
    with this_thread_output_to(lines.append), _DRAWING_LOCK, http.drawing_downloads() as downloads:
        try:
            drawn = resolve_start(config)
        except Exception as exc:  # shown on the page and in the log, never swallowed
            error, trace = http.not_drawn(exc)
            lines.extend([trace or "", http.not_drawn_line("the charts", error)])
        else:
            for country in COUNTRIES:
                if not getattr(drawn, country.show_field):
                    continue
                try:
                    figure = build_figure(country, drawn)
                except Exception as exc:  # that chart alone; shown on the page and in the log
                    # One line, "NOT DRAWN: ...", for a source not answering; the traceback too for anything else (batch 19.4).
                    why, trace = http.not_drawn(exc)
                    failed[country.key] = why
                    lines.extend([trace or "", http.not_drawn_line(f"the {TAB_TITLES[country.key]} chart", why)])
                    continue
                pngs[country.key] = png_bytes(figure)
                figures[country.key] = figure
                # Measured after savefig, so the axes positions are the final rendered ones (as in the window).
                geometry[country.key] = ChartGeometry.from_figure(figure, drawn)
                drawn_lines = hover.chart_lines(figure)
                if drawn_lines is not None:
                    readouts[country.key] = zlib.compress(json.dumps(hover.payload(drawn_lines), separators=(",", ":")).encode())
    return Drawing(
        config=config,
        drawn=drawn,
        pngs=pngs,
        figures=figures,
        geometry=geometry,
        tokens=tokens,
        log="".join(lines),
        error=error,
        failed=failed,
        copies=tuple(downloads.copies_used()),
        seconds=time.perf_counter() - began,
        finished=pd.Timestamp.now(tz=MARKET_TIMEZONE),
        readouts=readouts,
    )


def _set_address(tokens: tuple[str, ...]) -> None:
    """Write the chart's command line into the page's address (nothing at all for the defaults)."""
    text = " ".join(tokens)
    if st.query_params.get(ADDRESS_KEY, "") == text:
        return
    if text:
        st.query_params[ADDRESS_KEY] = text
    else:
        st.query_params.pop(ADDRESS_KEY, None)


def _view_buttons(drawing: Drawing) -> None:
    """Back, Unzoom and the date buttons, in one row over the charts, and how to zoom."""
    history = st.session_state.get(_HISTORY, [])
    drawn = drawing.drawn
    at_first = drawn is None or drawn.start <= EARLIEST_DATE
    at_today = drawn is None or drawn.end >= pd.Timestamp.today().normalize()
    buttons = (
        ("◀ Back", _back, (), not history, BACK_HELP),
        ("Unzoom", _unzoom, (), _unzoomed(), UNZOOM_HELP),
        ("◀ Earlier", _move_dates, (-_DATE_STEP_FRACTION, 1.0), at_first, "Move the dates back by half the window."),
        ("Later ▶", _move_dates, (_DATE_STEP_FRACTION, 1.0), at_today, "Move the dates on by half the window, up to today."),
        ("Zoom out", _move_dates, (0.0, _ZOOM_OUT_FACTOR), at_first and at_today, "Twice the span of dates, about its middle."),
    )
    # A row that wraps (not st.columns, which a phone stacks one per line,
    # pushing the charts below the screen).
    row = st.container(horizontal=True, wrap=True)
    for label, callback, args, disabled, tip in buttons:
        row.button(label, on_click=callback, args=args, disabled=disabled, help=tip)
    st.caption(_ZOOM_HINT)


def _export_bytes(drawing: Drawing, key: str, extension: str, every: bool) -> bytes:
    """The file a chart's download gives (batch 11.1, ``export``), made only when the button is clicked.

    Streamlit runs this on a thread of its own, beside the page's next run.
    A PNG is the bytes drawn; JPG, PDF and SVG the figure saved again, with
    ``_DRAWING_LOCK`` held, since saving draws and matplotlib's font cache is
    shared by every thread (a visitor's drawing waits, or this waits for it).
    The data read the figure's lines, which draws nothing. A workbook of
    every chart (``every``) has a sheet for each drawn, named as its tab.
    """
    if extension in IMAGE_FORMATS:
        if extension == ".png":
            return drawing.pngs[key]
        with _DRAWING_LOCK:
            return export.image_bytes(drawing.figures[key], drawing.pngs[key], extension)
    assert drawing.drawn is not None  # a chart was drawn
    keys = [each for each in TAB_TITLES if each in drawing.figures] if every and extension == ".xlsx" else [key]
    sheets = [(TAB_TITLES[each], export.chart_data(drawing.figures[each], drawing.drawn.for_nation(each), each)) for each in keys]
    return export.data_bytes(extension, sheets)


def _export_chosen(menu: str) -> None:
    """A format chosen under one chart: every chart's menu shows it from now on."""
    st.session_state[_EXPORT] = st.session_state[menu]


def _export_row(drawing: Drawing, key: str) -> None:
    """Under a chart: a menu of the formats (``export.EXPORT_CHOICES``) and the download button, "Export chart" as in the window.

    The file is named as the window's Save PNG named it, with the format's
    extension (``frontend.saved_export_name``), and made only on the click
    (``_export_bytes``), so a page that is only looked at draws nothing more.
    """
    types = {caption: (extension, every) for caption, extension, every in EXPORT_CHOICES}
    if st.session_state.get(_EXPORT) not in types:
        st.session_state[_EXPORT] = EXPORT_CHOICES[0][0]
    chosen = st.session_state[_EXPORT]
    menu = f"{_EXPORT_MENU}{key}"
    st.session_state[menu] = chosen  # set before the menu is laid out, so each tab's shows the format last chosen
    extension, every = types[chosen]
    row = st.container(horizontal=True, vertical_alignment="center", wrap=True)  # the button under the menu on a phone
    row.selectbox(
        "Format",
        list(types),
        key=menu,
        on_change=_export_chosen,
        args=(menu,),
        label_visibility="collapsed",
        width=300,
    )
    row.download_button(
        EXPORT_LABEL,
        data=functools.partial(_export_bytes, drawing, key, extension, every),
        file_name=saved_export_name(key, drawing.drawn, extension, every),
        mime=MIME_TYPES[extension],
        on_click="ignore",
        key=f"download:{key}",
        help=EXPORT_HELP,
    )


def _show(drawing: Drawing, config: PlotConfig | None = None) -> None:
    """The charts, one tab per country, each with its format menu and download button; then the command line and log.

    ``config``: the controls' now, None where they draw nothing; under the
    charts, its automatic refresh (``_auto_refresh``, batch 11.3).
    """
    if drawing.error is not None:
        st.error(f"Drawing failed: {drawing.error} (details in the message log below)")
    for key, why in drawing.failed.items():
        st.error(f"{TAB_TITLES[key]}: chart not drawn. {why} (details in the message log below)")
    if drawing.copies:
        st.warning(
            "Some sources did not answer, so their last good copies were drawn: "
            + "; ".join(drawing.copies)
            + " (details in the message log below)."
        )
    if drawing.pngs:
        _view_buttons(drawing)
        show_chart = _chart_component()
        keys = [key for key in TAB_TITLES if key in drawing.pngs]
        # The tab made current (batch 17.4, ``frontend.current_tab``): a nation
        # ticked by hand once its chart is drawn, else the one shown, else the
        # first. The tabs keep their place in the session (a click on one
        # reruns the page, which draws nothing new), so it can be set here.
        ticked = st.session_state.get(_TICKED)
        if ticked in keys:
            del st.session_state[_TICKED]
        by_title = {title: key for key, title in TAB_TITLES.items()}
        current = current_tab(keys, by_title.get(st.session_state.get(_TAB)), ticked)
        st.session_state[_TAB] = TAB_TITLES[current]
        for tab, key in zip(st.tabs([TAB_TITLES[key] for key in keys], key=_TAB, on_change="rerun"), keys):
            with tab:
                show_chart(
                    key=drawing.chart_key(key),
                    data=_chart_bytes(drawing, key),
                    on_box_change=functools.partial(_box_dragged, key),
                    on_wheel_change=functools.partial(_wheel_turned, key),
                )
                _export_row(drawing, key)
        narrow = drawing.drawn is not None and drawing.drawn.font_floor > PlotConfig().font_floor
        st.caption(
            f"Drawn at {drawing.finished:%Y-%m-%d %H:%M %Z} in {drawing.seconds:.1f} s"
            + (
                f", for a narrow screen: {drawing.drawn.width_px} x {drawing.drawn.height_px} px and larger text, as"
                " Export chart gives it; the command line and the web page's link below draw the full-size chart"
                if narrow else ""
            )
            + "."
        )
        _auto_refresh(config)
    # The command line, and under it the chart's link, each in a box with
    # Streamlit's copy button, labelled as the window labels its two lines
    # (batch 31.3; the link under the Drawn line since batch 28.5: the
    # address bar is out of reach on a phone, and bare after a Reset).
    st.markdown("**Command line:**")
    st.code(" ".join(["python", _SCRIPT_NAME, *drawing.tokens]), language=None, wrap_lines=True)
    st.markdown("**Web page:**")
    link = chart_link(st.context.url, drawing.tokens)
    # Go beside the link (batch 34.1), as the window's beside its Copy (31.8):
    # the link opened in a new tab, which draws the same charts and goes on by
    # itself, this tab left as it is (Terry: like Chrome's "Duplicate", a live
    # copy to come back to). Beside the box on a phone too: the box wraps.
    row = st.container(horizontal=True, wrap=False, vertical_alignment="center")
    row.code(link, language=None, wrap_lines=True)
    row.link_button("Go", link, help=_GO_HELP, key="go")
    with st.expander("Message log"):
        log = drawing.log.rstrip() or "(nothing printed)"
        st.code(log, language=None, wrap_lines=True)
        # Under the log, as the window's third button (Terry, 2026-10-13,
        # batch 15.3): the log as shown, named by the drawing's time.
        st.download_button(
            "Save log file",
            data=log + "\n",
            file_name=saved_log_name(drawing.finished),
            mime="text/plain",
            on_click="ignore",
            key="download:log",
            help="Save this drawing's message log as a text file.",
        )


def _auto_refresh(config: PlotConfig | None) -> None:
    """The automatic refresh (--auto-refresh, batch 11.3): a fragment Streamlit runs again every few minutes, under the charts.

    Laid out with the page, it says how often; each run of its own after
    that asks this visitor's ``refresh.Ticker`` and, when it is due, does
    what Refresh does: the page's downloads are an hour old at most anyway
    (``DOWNLOAD_MAX_AGE_SECONDS``), so a drawing forced. Every whole run of
    the page lays it out again, which starts its minutes again, so they run
    from the last drawing or change of a control. None where it is off or
    can bring nothing new (its box greyed).
    """
    if config is None or not config.auto_refresh or config.refresh_brings_nothing is not None:
        return
    every = datetime.timedelta(minutes=config.refresh_minutes)
    st.session_state[_AUTO_LAID_OUT] = True
    try:
        st.fragment(_auto_refresh_tick, run_every=every)(config)
    finally:
        st.session_state[_AUTO_LAID_OUT] = False


def _auto_refresh_tick(config: PlotConfig) -> None:
    """The automatic refresh's fragment (``_auto_refresh``): what it says, and at each run of its own whether to draw again."""
    state = st.session_state
    note = f"Refreshed automatically every {config.refresh_minutes} minutes; outside market hours only when a quote has changed."
    if state.get(_AUTO_LAID_OUT):
        st.caption(note)
        return
    if config.refresh_brings_nothing is not None:
        st.rerun(scope="app")  # the day has changed: the whole page judges the controls again (a blank End is today)
    with this_thread_output_to(None), http.drawing_downloads():
        due = state.setdefault(_AUTO_TICKER, Ticker()).due(config)
    if due:
        state[_FORCE] = True
        st.rerun(scope="app")
    st.caption(f"{note} Asked at {pd.Timestamp.now(tz=MARKET_TIMEZONE):%H:%M %Z}: no quote has changed since the last refresh.")


# Streamlit's "?" beside a label made an ⓘ, as the window's (batch 29.1;
# Terry, 2026-10-27: "If there isn't a simple way for streamlit to change the
# label of its control from "?" to "ⓘ", then it's ok to leave it as "?"").
# One style rule: Streamlit 1.64 draws the "?" as an SVG in a button labelled
# "Help for …" (measured 2026-10-28), hidden here, the ⓘ shown in its place;
# the tip of a button (Refresh) wraps the button itself and is left alone.
# Never greyed (Terry: "It would not be greyed out when that control is
# greyed out"): a greyed control's label colour, the text colour at 40 %,
# reaches the ⓘ, which takes it back at full strength, in either theme.
_INFO_ICON_STYLE = """<style>
[data-testid="stTooltipIcon"] button[aria-label^="Help for"] svg { display: none; }
[data-testid="stTooltipIcon"] button[aria-label^="Help for"]::after {
  content: "ⓘ"; font-size: 1rem; line-height: 1; color: rgb(from currentColor r g b / 1);
}
</style>"""


def _show_help(topic: str) -> None:
    """The help view (batch 29.1): topic ``topic``'s text alone, in the tab a More link opened.

    Its address holds only ``?help=TOPIC`` (``frontend.help_address``), as
    does a topic's link to another (batch 29.2), followed as it is: no chart is
    drawn, no control laid out, and the remembered settings are neither read
    nor written, so the visit the link came from is left as it was. The
    topic's Markdown is shown as it is; a name no option gives is refused
    (``frontend.help_text``), so the address cannot reach another file.
    """
    try:
        text = help_text(topic)
    except KeyError:
        st.error(f"There is no help page named “{topic}”.")
        return
    st.markdown(text)


def main() -> None:
    """Draw the page (Streamlit runs this from the top on every change of a control)."""
    st.set_page_config(page_title=PAGE_TITLE, page_icon="📈", layout="wide")
    topic = st.query_params.get(HELP_KEY)
    if topic is not None:
        _show_help(topic)
        return
    state = st.session_state
    if not state.get(_READY):
        started = _starting_choices()
        if started is None:
            _read_remembered()  # its answer runs the page again
            return
        choices, state[_STARTED_FROM], state[_ADDRESS_PROBLEMS], state[_REMEMBERED_PROBLEMS] = started
        _load_choices(choices)
        state[_REMEMBER] = True  # ticked at every visit, its off state never kept (decision 74)
        state[_READY] = True

    # Judged before the controls are laid out, so a wrong field's label is red (_WRONG).
    choices = _snapshot()
    config, problems = _config_for(choices)
    if config is not None:
        config = for_screen(config, bool(state.get(_NARROW)))
    st.html(_INFO_ICON_STYLE)
    _controls()
    _read_width()
    st.header(PAGE_TITLE)
    st.caption(PAGE_SUMMARY)
    if state.get(_ADDRESS_PROBLEMS):
        instead = "The settings remembered from your last visit" if state.get(_STARTED_FROM) == "remembered" else "The default charts"
        st.warning(
            "The chart named in this page's address could not be drawn ("
            + "; ".join(state[_ADDRESS_PROBLEMS])
            + f"). {instead} are shown instead."
        )
    if state.get(_REMEMBERED_PROBLEMS):
        st.warning(
            "The settings remembered from your last visit could not be used ("
            + "; ".join(state[_REMEMBERED_PROBLEMS])
            + "). The default charts are shown instead."
        )
    if state.get(_NOTICE):
        st.info(state.pop(_NOTICE))

    previous: Drawing | None = state.get(_DRAWING)
    forced = state.pop(_FORCE, False)
    if config is not None and previous is not None and not forced and previous.config != config and config.same_chart(previous.config):
        # Only the hover read-out's box changed (batch 11.2), or the automatic
        # refresh's (11.3): they draw nothing, so the charts stay; the address
        # and the command line follow them.
        tokens = tuple(command_line_tokens(*choices))
        state[_DRAWING] = previous = replace(previous, config=config, tokens=tokens)
        if previous.error is None:
            _set_address(tokens)
    if config is None:
        st.error("Not drawn: " + "; ".join(problems))
    elif previous is None or previous.config != config or forced:
        tokens = tuple(command_line_tokens(*choices))
        if _DRAWING_LOCK.locked():
            note = "Another visitor's chart is being drawn; yours is next …"
        elif previous is None:
            note = "Drawing … (after a quiet hour the data are downloaded first: about 15 s)"
        else:
            note = "Drawing …"
        with st.spinner(note, show_time=True):
            drawing = _draw(config, tokens)
        state[_DRAWING] = drawing
        if previous is not None:
            # The visitor has moved on from the chart the visit opened on.
            state[_ADDRESS_PROBLEMS] = state[_REMEMBERED_PROBLEMS] = []
        if drawing.error is None:
            _set_address(tokens)
        if _field_hints() != state.get(_HINTS):
            # The controls were laid out before this drawing: lay them out
            # again (no new drawing) so the blank fields show its values.
            st.rerun()
    drawing = state.get(_DRAWING)
    if drawing is not None:
        _show(drawing, config)

    with st.expander("Every option, as the command line spells it"):
        st.code(help_epilog(), language=None)
    # The last chart drawn, kept while the box is ticked (batch 24.6): its
    # line is the address's. At the page's foot, not the sidebar's: a
    # folded sidebar (a phone's, at first) runs no script of its own
    # (measured 2026-10-27, Streamlit 1.64: no cookie written).
    if state.get(_REMEMBER) and drawing is not None and drawing.error is None:
        _remember_settings(" ".join(drawing.tokens))
    # The sidebar's width, kept only while the box is ticked (batch 31.1): on every run, so its script knows the box.
    _keep_sidebar_width(bool(state.get(_REMEMBER)))
