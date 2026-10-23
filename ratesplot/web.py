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
    the defaults are drawn instead. This replaces the window's remembered
    settings.

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
    "◀ Earlier" and "Later ▶" move the dates by half the window, "Zoom out"
    doubles their span (``frontend.move_dates_updates``: between 1680 and
    today, keeping the span). "Back" undoes one zoom, move, Unzoom or Reset;
    "Unzoom" returns to the charts before the first zoom or move, as one
    more step that Back undoes; each is greyed while it would do nothing (as
    in the window). The axis limits are
    each nation's own, so zooming one chart's axes leaves the other's; the
    dates are shared, as on the command line.

Dates
    Beside each date field a 📅 button opens Streamlit's calendar (between
    1680 and today) and a "Blank (default)" button, as the window's does:
    picking a day writes ``YYYY-MM-DD`` in the field, and typing ``YYYY`` or
    ``YYYY-MM`` still works (``_date_control``).

Size
    Width and height boxes and a "Preserve aspect ratio" lock, as in the
    window: with the lock on, changing one box sets the other, so a chart
    whose shape suits can be drawn larger or smaller by typing one number
    (``_size_control``). The ``WxH`` text behind them stays the source of truth.

Not here (the window has them)
    The wheel's zoom and the right-drag pan (the buttons move the dates),
    and remembered settings (the address keeps the chart instead).
"""

from __future__ import annotations

import datetime
import functools
import os
import struct
import threading
import time
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # before pyplot is imported (by plotting): a server has no display

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from . import http  # noqa: E402
from .cli import sort_tokens  # noqa: E402
from .config import (  # noqa: E402
    DEFAULT_REGRESSION_TOLERANCE_PCT,
    DOWNLOAD_MAX_AGE_SECONDS,
    EARLIEST_DATA_START,
    MARKET_TIMEZONE,
    NATIONS,
    Nation,
    PlotConfig,
)
from .console import this_thread_output_to  # noqa: E402
from .frontend import (  # noqa: E402
    LIMIT_COLUMNS,
    LIMITS,
    NATION_OPTIONS,
    TAB_TITLES,
    ChartGeometry,
    Choices,
    all_tick,
    all_tick_offered,
    bound_keys,
    bounds_in_other_units,
    choice_refusal,
    choice_rows,
    choice_values,
    choices_text,
    control_blocks,
    current_tab,
    drawn_payloads,
    field_hints,
    field_problems,
    idle_controls,
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
    reset_choices,
    saved_log_name,
    saved_png_name,
    settled_all_ticks,
    size_boxes_at_fault,
    starting_choices,
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

PAGE_TITLE = "Bond Yields and Public Debt"
PAGE_SUMMARY = (
    "Government bond yields against public debt, GDP, and interest outlays, for Canada and the "
    "United States, from Statistics Canada, the Bank of Canada, FRED, the U.S. Treasury and the "
    "U.S. Census Bureau; and, when ticked, for the United Kingdom, from the Bank of England and the "
    "Office for National Statistics, and for Germany, from the Deutsche Bundesbank, the ECB and Eurostat. Choose the charts in the panel on the left (the » button on a phone); "
    "each change redraws them."
)
_SCRIPT_NAME = "ratesplot.py"
# The query parameter that holds the chart's command line.
ADDRESS_KEY = "chart"
# What a blank field means, shown in it until a drawing gives the value in
# effect (``frontend.field_hints``: Terry, 2026-10-08, a blank field shows its
# default or automatic value in grey). The other blank fields mean
# "automatic" (the axis limits) or are filled with their default.
_PLACEHOLDERS = {
    "start": "automatic",
    "end": "today",
    "regression-tolerance": f"{DEFAULT_REGRESSION_TOLERANCE_PCT:g}",
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
# The window's words and bars (Terry, 2026-10-08); the page has no pan or wheel.
_ZOOM_HINT = (
    "Drag pointer: zoom to box (its width sets the dates, its height the axes' limits) | "
    "buttons: move the dates | Back: undo a zoom"
)

# Session-state keys: one per control, and the page's own records.
_FLAG = "flag:"      # + option name: a check box
_VALUE = "value:"    # + option name, or a nation's choice key ("us:max"): a text field
_LEVEL = "level:"    # + nation key + ":" + letter: one of a nation's "By level" boxes (batch 10.5)
_CHOICE = "choice:"  # + choice key + ":" + value: one tick box of a list option (Option.choices)
_CHOICE_OTHERS = "choice_others:"  # + choice key: the values given that no offered box has
_ALL = "all:"        # + a nation's limit key ("us:max"): its "All" box, one tick for every nation's (batch 18.2)
_READY = "ready"     # the controls have been set from the address
_ADDRESS_PROBLEMS = "address_problems"
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
# The calendar's first day: no series starts earlier (config.EARLIEST_DATA_START).
_CALENDAR_FIRST = EARLIEST_DATA_START.date()
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
# Streamlit builds the component's element afresh on every run of the page
# (measured with Streamlit 1.64: a new parent element each run, and the
# function returned below called just before), so nothing is kept between
# runs: the picture's object URL is released by that function, and the
# picture is given its size from the PNG's header, so that the browser keeps
# its place while decoding it and the page does not jump.
_CHART_JS = """
const MIN_DRAG = 8;

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const frame = document.createElement("div");
  frame.className = "chart";
  frame.innerHTML = '<img alt="Chart" draggable="false"><div class="band"></div>';
  parentElement.appendChild(frame);
  const img = frame.querySelector("img");
  const band = frame.querySelector(".band");

  const header = new DataView(data.buffer, data.byteOffset, 24);  // PNG: IHDR width, height at 16, 20
  img.width = header.getUint32(16);
  img.height = header.getUint32(20);
  const url = URL.createObjectURL(new Blob([data], { type: "image/png" }));
  img.src = url;

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
    if (event.pointerType === "touch" || event.button !== 0) return;
    event.preventDefault();
    img.setPointerCapture(event.pointerId);
    start = point(event);
    showBand(start, start);
  };
  img.onpointermove = (event) => {
    if (start) showBand(start, point(event));
  };
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
  return () => URL.revokeObjectURL(url);
}
"""
_CHART_CSS = """
.chart { position: relative; line-height: 0; }
.chart img { width: 100%; height: auto; cursor: crosshair; user-select: none; -webkit-user-select: none; }
.band {
  position: absolute; display: none; box-sizing: border-box; pointer-events: none;
  border: 2px dashed #1f5fbf; background: rgba(31, 95, 191, 0.08);
}
"""
def _chart_component():
    """Register the chart component with the running Streamlit and return the command that shows a chart.

    Registration belongs to Streamlit's runtime, not to this module, so it is
    done on every run rather than once at import: a process may start a
    second runtime (Streamlit's AppTest does, one per test), which would not
    know the component. Registering the same definition again is silent.
    """
    return st.components.v2.component("ratesplot_chart", js=_CHART_JS, css=_CHART_CSS)


def _png_size(png: bytes) -> tuple[int, int]:
    """Return a PNG's width and height in pixels, read from its header (the IHDR chunk)."""
    width, height = struct.unpack(">II", png[16:24])
    return width, height


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


def _choices_from_address() -> tuple[Choices, list[str]]:
    """Return the starting choices from the address's command line, and any problems with it.

    The address is read as the command line is (``cli.sort_tokens``, then
    ``options.config_from_choices``), and laid over the defaults as the window
    lays a command line over them (``frontend.starting_choices``, with nothing
    remembered). If it cannot be read, the defaults are used.
    """
    text = st.query_params.get(ADDRESS_KEY, "")
    payloads, flags, unmatched, misspelled = sort_tokens(text.split())
    problems = [f"{token}: not an option" for token in unmatched] + misspelled
    config = PlotConfig()
    if not problems:
        try:
            config = config_from_choices(payloads, flags)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        payloads, flags = {}, {}
    choices, _notes = starting_choices(config, payloads, flags, {})
    return choices, problems


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
    if len(history) > _HISTORY_LIMIT:
        del history[1 : len(history) - _HISTORY_LIMIT + 1]


def _unzoomed() -> bool:
    """True when there is no view before the first zoom to return to, or it is the one shown (as in the window)."""
    history = st.session_state.get(_HISTORY)
    return not history or history[0][0] == _snapshot()


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
    from 1680 to today). The axis limits go into the fields of the chart's
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
    """Return to the charts before the first zoom: one more step, so Back returns to the zoom."""
    if not _unzoomed():
        first = st.session_state[_HISTORY][0][0]
        _remember_view()
        _load_choices(first)


# ---------------------------------------------------------------------------
# The controls
# ---------------------------------------------------------------------------


def _help(option: Option, extra: str = "") -> str:
    """The option's help, as the window's tooltip, one paragraph per line (Markdown)."""
    return "\n\n".join([*option_help_lines(option), *([extra] if extra else [])])


def _flag_control(where, option: Option) -> None:
    callbacks = {"country": _country_changed, "units": _measure_changed, "curves": _curve_changed}
    callback = callbacks.get(option.group)
    where.checkbox(
        option.label,
        key=_FLAG + option.name,
        help=_help(option),
        on_change=callback,
        args=(option.name,) if callback else None,
        # What has no effect is greyed, its tick kept (frontend.idle_controls):
        # GDP under -r, where it is the divisor; % of GDP, Per capita and the
        # regression segments with no curve to act on.
        disabled=option.name in _idle(),
    )


def _idle() -> frozenset[str]:
    """The options greyed out for the check boxes' state now (``frontend.idle_controls``), as in the window."""
    return idle_controls({option.name: bool(st.session_state.get(_FLAG + option.name, False)) for option in _gui_options(False)})


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
        help=_help(option, "Blank = default (shown in grey)."),
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
    return date if date is not None and _CALENDAR_FIRST <= date <= _today() else None


def _today() -> datetime.date:
    return pd.Timestamp.today().date()


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
            max_value=_today(),
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
    where.markdown(f"**{option.label}**", help=_help(option, "None ticked = debt and interest in total."))
    idle = option.name in _idle()  # greyed without debt or interest, as in the window
    row = where.container(horizontal=True, wrap=True)
    for letter, caption in nation.level_boxes:
        row.checkbox(caption, key=_LEVEL + nation.key + ":" + letter, disabled=idle)


def _choices_control(where, option: Option, nation: Nation | None = None) -> None:
    """A list option as tick boxes (``Option.choices``): a row of boxes per row offered, with its caption.

    One that belongs to a flag (mortgage terms, spreads) is greyed while
    the flag is off, as its field was, and the UK's aggregate debts while
    none is drawn (``frontend.idle_nation_keys``). A nation's own list has its label
    always, and only the boxes its chart can draw (``frontend.choice_rows``).
    The boxes of a row flow, wrapping when the sidebar is narrow, and the
    help is on the list's label alone: a column per box, each with its "?",
    left no room for the text at the sidebar's narrow default width
    (2026-10-13: Canada's yield terms showed only their "?", the spreads
    "10…").
    """
    key = nation_choice(nation, option) if nation else option.name
    disabled = option.turns_on is not None and not st.session_state.get(_FLAG + option.turns_on, False)
    disabled = disabled or key in idle_nation_keys(*_snapshot())
    if option.turns_on is None or nation is not None:
        where.markdown(f"**{option.label}**", help=_help(option))
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
    buttons = bar.columns(2)
    # One button, as in the window (Terry, 2026-10-08: "Refresh", meaning
    # reload data): a drawing after a change of the controls is automatic.
    buttons[0].button(
        "Refresh",
        on_click=_force_redraw,
        help="Draw again with the latest data: the intraday quotes of the moment, and anything downloaded over an hour ago.",
        width="stretch",
    )
    buttons[1].button("Reset", on_click=_reset, help="Back to the default charts.", width="stretch")
    st.session_state[_HINTS] = _field_hints()
    _settle_all_ticks()  # before the "All" boxes are laid out, which fixes their state for this run
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
    for nation in NATIONS:
        _nation_controls(bar, nation)


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
        disabled=not all_tick_offered(payloads, flags, key),
        help=(
            f"This {option.label} for every nation's chart. Ticked, the value goes into every nation's field, and a value "
            "entered in any of them goes into the others; unticked, each keeps its own. Top and Bottom go with their "
            "currency (20t from the U.S. field as USD20t), each chart converting them at the rate of its end date. "
            "Greyed while the field is blank or only one nation is ticked."
        ),
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
    geometry: dict[str, ChartGeometry | None] = {}
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
                # Measured after savefig, so the axes positions are the final rendered ones (as in the window).
                geometry[country.key] = ChartGeometry.from_figure(figure, drawn)
    return Drawing(
        config=config,
        drawn=drawn,
        pngs=pngs,
        geometry=geometry,
        tokens=tokens,
        log="".join(lines),
        error=error,
        failed=failed,
        copies=tuple(downloads.copies_used()),
        seconds=time.perf_counter() - began,
        finished=pd.Timestamp.now(tz=MARKET_TIMEZONE),
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
    at_first = drawn is None or drawn.start <= EARLIEST_DATA_START
    at_today = drawn is None or drawn.end >= pd.Timestamp.today().normalize()
    buttons = (
        ("◀ Back", _back, (), not history, "Undo the last zoom, move of the dates, Unzoom or Reset."),
        ("Unzoom", _unzoom, (), _unzoomed(), "Back to the charts before the first zoom or move (Back undoes it)."),
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


def _show(drawing: Drawing) -> None:
    """The charts, one tab per country, each with its download button; then the command line and log."""
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
                    data=drawing.pngs[key],
                    on_box_change=functools.partial(_box_dragged, key),
                )
                st.download_button(
                    "Download this chart (PNG)",
                    data=drawing.pngs[key],
                    file_name=saved_png_name(key, drawing.drawn),
                    mime="image/png",
                    on_click="ignore",
                    key=f"download:{key}",
                )
        st.caption(
            f"Drawn at {drawing.finished:%Y-%m-%d %H:%M %Z} in {drawing.seconds:.1f} s. "
            "The page's address holds this chart's settings: copy it from the address bar to share the chart."
        )
    st.markdown("**The same chart from the command line**")
    st.code(" ".join(["python", _SCRIPT_NAME, *drawing.tokens]), language=None, wrap_lines=True)
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


def main() -> None:
    """Draw the page (Streamlit runs this from the top on every change of a control)."""
    st.set_page_config(page_title=PAGE_TITLE, page_icon="📈", layout="wide")
    state = st.session_state
    if not state.get(_READY):
        choices, problems = _choices_from_address()
        _load_choices(choices)
        state[_ADDRESS_PROBLEMS] = problems
        state[_READY] = True

    # Judged before the controls are laid out, so a wrong field's label is red (_WRONG).
    choices = _snapshot()
    config, problems = _config_for(choices)
    _controls()
    st.header(PAGE_TITLE)
    st.caption(PAGE_SUMMARY)
    if state.get(_ADDRESS_PROBLEMS):
        st.warning(
            "The chart named in this page's address could not be drawn ("
            + "; ".join(state[_ADDRESS_PROBLEMS])
            + "). The default charts are shown instead."
        )
    if state.get(_NOTICE):
        st.info(state.pop(_NOTICE))

    previous: Drawing | None = state.get(_DRAWING)
    forced = state.pop(_FORCE, False)
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
            state[_ADDRESS_PROBLEMS] = []  # the visitor has moved on from the address's chart
        if drawing.error is None:
            _set_address(tokens)
        if _field_hints() != state.get(_HINTS):
            # The controls were laid out before this drawing: lay them out
            # again (no new drawing) so the blank fields show its values.
            st.rerun()
    drawing = state.get(_DRAWING)
    if drawing is not None:
        _show(drawing)

    with st.expander("Every option, as the command line spells it"):
        st.code(help_epilog(), language=None)
