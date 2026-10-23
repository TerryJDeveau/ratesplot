"""The interactive window: every chart option adjustable, charts redrawn on the fly.

Opened by default (``--gui``); ``--no-gui`` gives the plain matplotlib windows.

Controls
    Generated from ``options.OPTIONS``: a check box for every on/off option, a
    text field for every VALUE option (``editor="date"`` adds a calendar
    button; ``editor="size"`` gives width and height boxes with an
    aspect-ratio lock; ``editor="levels"`` gives one check box per level of
    government, the single "By level" control for ``--debt:`` and
    ``--interest:``), in the blocks of ``frontend.control_blocks`` (Terry's
    order of 2026-10-08: the measure under "By level", the regression
    segments under the measure, the four rates on the yield axis together,
    the line labels with the latest data; --help keeps its sections), each with the option's
    help text and command-line spelling as a tooltip. A new option in the table
    appears here with no change to this module (``in_gui=False`` opts out). The
    choices become a ``PlotConfig`` through ``options.config_from_choices``, the
    same code the command line uses, so the two cannot disagree. The measure
    switches (-r, -p) exclude each other: ticking one unticks the other.
    Changing the measure clears Top and Bottom, whose units it changes
    (dollars, percent, dollars per person), and under -r the GDP box is
    greyed out, GDP being only the denominator. What has no curve to act on
    is greyed out too, its tick or text kept (``frontend.idle_controls``):
    % of GDP and By level without debt or interest; Per capita, Regression
    segments and each chart's Top and Bottom without debt, GDP or interest.
    A greyed field's text is ignored and left off the command line. A blank
    text field shows the value in effect in grey (``frontend.field_hints``):
    the automatic start, the end, the tolerance's default, each chart's axis
    limits as drawn; it is never written in (``_Hint``). Each nation's own choices
    (``frontend.NATION_OPTIONS``: its yield terms, spreads and mortgage terms
    as tick boxes, and its axis limits) are in a panel under its tab, keyed
    "NATION:OPTION". The controls scroll when the
    window is too short for them; Refresh, Save PNG and Save log file sit in
    a bar under them that does not, so they are always in sight (the log's
    button under the other two when the column is narrow). A handle between the
    controls and the charts sets the column's width, remembered with the
    window's; each block lays its controls out in as many columns as fit,
    (``_Flow``): two at the default width, one when narrow, each row
    filled before the next, so four boxes go three and one where three fit.

Remembered settings
    The choices of the last successful drawing, the preview mode, the selected
    tab, the window's size and place (on any monitor, or across several),
    whether it is maximized, and the column's width are saved after every drawing and on closing,
    and restored at the next start: each command window has its own file,
    so several windows can be open at once (``frontend.state_path``); a
    first run in a new command window starts from the file written last. Options given on the command line override the remembered ones
    they name: a value option individually; the curves, the countries or the
    measure each as a group, because naming one curve on the command line
    means "only this one".

Zoom and pan
    The mouse edits the same fields a user would type in, so the fields remain
    the single source of truth (and the command line, the remembered settings
    and "Save PNG" all follow). Left-drag a box to zoom to it: its width sets
    Start/End, its height sets the yield Min/Max and the right-axis Top/Bottom of
    whichever axes are drawn. Right- or middle-drag pans. The wheel zooms the
    dates about the pointer. "Back" undoes one zoom, pan, Unzoom or Reset;
    "Unzoom" returns to the view before the first zoom, as one more step that
    Back undoes (Terry, 2026-10-08: Back after Unzoom did nothing). Each is
    greyed while it would do nothing. The axis limits are each nation's own (the
    panel under its tab), so zooming one chart's axes leaves the other's; the
    dates are shared, as on the command line.

Drawing
    Each chart is drawn exactly as the command line draws it (the same
    ``plotting.draw_country``) on an off-screen Agg figure at the configured
    pixel size, rendered to PNG, and shown scaled to fit the window (or at
    actual size). "Save PNG" writes those same bytes, so a saved chart is the
    real output, not a screenshot of the preview. A blank Start is the
    automatic start, found for the charts drawn together
    (``plotting.resolve_start``) each time they are drawn, so it follows the
    chosen curves (no earlier than ``config.DEFAULT_START_FLOOR``); the log
    names it.

Threading
    Fetching and drawing run on one worker thread at a time so the window stays
    responsive during downloads. The worker never touches Tk; it posts messages
    to a queue that the window polls. Its printed progress and warnings are
    captured into the log pane (``console`` routes them by thread). If the choices change while a chart is being
    drawn, the newest choices are drawn as soon as the worker is free.

Downloads are cached for the session (``http.enable_download_cache``), so only
the first drawing waits for the network. "Refresh" (F5) draws again with the
intraday quotes of the moment (never kept) and fetches again anything
downloaded over an hour ago (``config.DOWNLOAD_MAX_AGE_SECONDS``, the web
page's rule). Terry, 2026-10-08: one button instead of Redraw and Reload data,
a drawing after a change of the controls being automatic anyway.
"""

from __future__ import annotations

import calendar
import io
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, ttk

import pandas as pd
from PIL import Image, ImageTk

from . import http
from .config import COMPONENT_LETTERS, DOWNLOAD_MAX_AGE_SECONDS, NATIONS, Nation, PlotConfig
from .console import this_thread_output_to
from .frontend import (
    GREYABLE_OPTIONS,
    LEVEL_BOXES,
    LIMIT_COLUMNS,
    NATION_OPTIONS,
    STATE_VERSION,
    TAB_TITLES,
    ChartGeometry,
    Choices,
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
    level_letters,
    load_state,
    nation_boxes,
    option_help_lines,
    option_of,
    pan_updates,
    png_bytes,
    problem_text,
    reset_choices,
    save_state,
    saved_log_name,
    saved_png_name,
    scale_dates_updates,
    size_boxes_at_fault,
    starting_choices,
    with_leading_zero,
    zoom_updates,
)
from .options import (
    Kind,
    Option,
    by_name,
    command_line_tokens,
    config_from_choices,
    idle_margins,
    margin_options,
    nation_choice,
    options_in,
    parse_date_spec,
)
from .plotting import COUNTRIES, Country, build_figure, resolve_start

WINDOW_TITLE = "Rates plot: yields, public debt, GDP & interest"
_SCRIPT_NAME = "ratesplot.py"
# Pause after the last keystroke in a text field before the chart is redrawn,
# so typing "2001" does not try to draw 2, 20 and 200 on the way.
_TEXT_REDRAW_DELAY_MS = 700
# How often the window collects messages from the worker thread.
_POLL_MS = 100
# Pause after a window resize before the preview is rescaled.
_RESIZE_DELAY_MS = 150
# Pause after the last wheel notch before the zoom is applied (one redraw per gesture).
_WHEEL_DELAY_MS = 350
# Date range multiplier per wheel notch (towards the pointer).
_WHEEL_ZOOM_FACTOR = 0.8
# How many zoom/pan steps "Back" can undo. The view before the first one is
# always kept, for Unzoom.
_HISTORY_LIMIT = 50
# The preview's mode at first and after Reset: the chart fitted to its tab.
_DEFAULT_PREVIEW = "fit"
# Initial window size as a fraction of the screen (when nothing is remembered).
_SCREEN_FRACTION = 0.9
_ERROR_FOREGROUND = "#b00020"
# A blank field's grey value (``_Hint``), on the field's own background.
_HINT_FOREGROUND = "#8c8c8c"
_FIELD_BACKGROUND = "SystemWindow" if sys.platform == "win32" else "white"
_GEOMETRY_PATTERN = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")
# A remembered window is put back where it was if this much of its title bar
# (the band this tall below its top edge) is on a monitor: enough to grab
# and drag it. Wherever that is: another monitor, across several.
_TITLE_BAR_PX = 30
_MIN_TITLE_ON_SCREEN_PX = 100
# The column's handle (Terry, 2026-10-08: its width adjustable): the handle's
# width, and the least the charts keep beside it.
_SASH_PX = 6
_MIN_CHARTS_PX = 300
# The controls' frame's padding in the column.
_PANEL_PAD_PX = 8
# The columns of a block's controls this far apart (``_Flow``).
_CELL_GAP_PX = 12
# The blocks in two columns at the column's default width (Terry, 2026-10-08:
# the nations, the yields, spreads, policy and mortgages, Start and End on one
# line, the aspect tick beside the size boxes, the measure), and the
# regression segments' row whole, its tolerance after the check box.
_TWO_COLUMN_BLOCKS = ("country", "rates", "dates", "canvas", "units", "regression")
# A date field's width in characters: room for YYYY-MM-DD.
_DATE_ENTRY_CHARS = 11
# The Preview's note wraps at the column's width, never narrower than this.
_NOTE_WRAP_PX = 150
# Terry's wording, 2026-10-08: "Drag pointer", "right/middle click", bars between.
_ZOOM_HINT = "Drag pointer: zoom to box | right/middle click-drag: pan | wheel: zoom dates"


# ---------------------------------------------------------------------------
# Small widgets
# ---------------------------------------------------------------------------


class _Tooltip:
    """Show ``text`` in a small borderless window while the pointer is over ``widget``."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event: tk.Event) -> None:
        if self.window is not None:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            self.window, text=self.text, justify="left", background="#ffffe0", relief="solid", borderwidth=1, padding=4
        ).pack()

    def _hide(self, _event: tk.Event) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


class _Hint:
    """Grey text over a blank text field: the value in effect while it is blank.

    Terry, 2026-10-08 (decision 18): a blank field shows its default or
    automatic value in grey, a typed value in black (``frontend.field_hints``).
    A Tk entry has no placeholder, so the grey text is a label laid over the
    entry, never the entry's text: the field's variable stays empty, so the
    command line, the remembered settings and Back see a blank field, which
    keeps meaning "default" or "automatic". It is shown while the field is
    empty and not greyed, from the place typed text starts, two pixels to the
    right so the cursor stays visible; typing hides it, clearing the field
    brings it back, and a click on it puts the cursor in the field.
    """

    def __init__(self, entry: ttk.Entry, variable: tk.StringVar, tip: str, text: str = "") -> None:
        self.entry = entry
        self.variable = variable
        self.text = text
        self.label = tk.Label(
            entry,
            text=text,
            foreground=_HINT_FOREGROUND,
            background=_FIELD_BACKGROUND,
            font="TkTextFont",
            borderwidth=0,
            padx=0,
            pady=0,
            cursor="xterm",
        )
        self.label.bind("<Button-1>", self._click)
        _Tooltip(self.label, tip)
        variable.trace_add("write", lambda *_args: self.update())
        entry.bind("<Configure>", lambda _event: self.update(), add="+")

    def set(self, text: str) -> None:
        self.text = text
        self.update()

    def update(self) -> None:
        if self.text and not self.variable.get() and not self.entry.instate(["disabled"]):
            self.label.configure(text=self.text)
            try:
                left = self.entry.bbox(0)[0]  # where typed text starts (the insertion point of an empty field)
            except (tk.TclError, IndexError):
                left = 3
            self.label.place(x=left + 2, rely=0.5, anchor="w")
        else:
            self.label.place_forget()

    def _click(self, _event: tk.Event) -> None:
        self.entry.focus_set()
        self.entry.icursor("end")


class DatePicker:
    """A small month calendar under a date field. Picking a day writes ``YYYY-MM-DD`` into it.

    Year and month can be typed or stepped, so distant decades are two clicks
    away. "Blank" empties the field, which means the option's default (today,
    for the end date; for the start, ``config.DEFAULT_START_FLOOR`` or the
    first date on which every chosen curve has data, if later).
    """

    _SELECTED = "#cfe3ff"
    _TODAY = "#fff2b3"

    def __init__(self, anchor: tk.Widget, variable: tk.StringVar, kind: str, on_pick) -> None:
        self.variable = variable
        self.on_pick = on_pick
        today = pd.Timestamp.today().normalize()
        try:
            self.selected = parse_date_spec(variable.get(), kind=kind) if variable.get().strip() else None
        except ValueError:
            self.selected = None
        shown = self.selected or today
        self.today = today
        self.year = tk.IntVar(value=shown.year)
        self.month = tk.StringVar(value=calendar.month_name[shown.month])

        self.top = tk.Toplevel(anchor)
        self.top.title("Pick a date")
        self.top.resizable(False, False)
        self.top.transient(anchor.winfo_toplevel())
        self.top.geometry(f"+{anchor.winfo_rootx()}+{anchor.winfo_rooty() + anchor.winfo_height() + 2}")
        self.top.bind("<Escape>", lambda _event: self.top.destroy())

        header = ttk.Frame(self.top, padding=4)
        header.pack(fill="x")
        ttk.Button(header, text="◀", width=3, command=lambda: self._step(-1)).pack(side="left")
        months = ttk.Combobox(
            header, textvariable=self.month, values=list(calendar.month_name)[1:], state="readonly", width=10
        )
        months.pack(side="left", padx=4)
        months.bind("<<ComboboxSelected>>", lambda _event: self._draw_days())
        years = ttk.Spinbox(header, from_=1900, to=2100, textvariable=self.year, width=6, command=self._draw_days)
        years.pack(side="left")
        years.bind("<Return>", lambda _event: self._draw_days())
        years.bind("<FocusOut>", lambda _event: self._draw_days())
        ttk.Button(header, text="▶", width=3, command=lambda: self._step(1)).pack(side="left", padx=(4, 0))

        self.days = ttk.Frame(self.top, padding=(4, 0))
        self.days.pack()
        footer = ttk.Frame(self.top, padding=4)
        footer.pack(fill="x")
        ttk.Button(footer, text="Today", command=lambda: self._pick(self.today)).pack(side="left")
        ttk.Button(footer, text="Blank (default)", command=self._blank).pack(side="left", padx=4)
        ttk.Button(footer, text="Cancel", command=self.top.destroy).pack(side="right")

        self._draw_days()
        self.top.focus_set()
        self.top.grab_set()

    def _month_number(self) -> int:
        return list(calendar.month_name).index(self.month.get())

    def _year_number(self) -> int | None:
        try:
            year = int(self.year.get())
        except (tk.TclError, ValueError):
            return None
        return year if 1000 <= year <= 9999 else None

    def _step(self, months: int) -> None:
        year = self._year_number()
        if year is None:
            return
        index = year * 12 + self._month_number() - 1 + months
        self.year.set(index // 12)
        self.month.set(calendar.month_name[index % 12 + 1])
        self._draw_days()

    def _draw_days(self) -> None:
        year = self._year_number()
        if year is None:
            return
        month = self._month_number()
        for child in self.days.winfo_children():
            child.destroy()
        for column, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            ttk.Label(self.days, text=name, width=4, anchor="center").grid(row=0, column=column)
        for row, week in enumerate(calendar.monthcalendar(year, month), start=1):
            for column, day in enumerate(week):
                if day == 0:
                    continue
                date = pd.Timestamp(year=year, month=month, day=day)
                background = (
                    self._SELECTED if date == self.selected else self._TODAY if date == self.today else "white"
                )
                tk.Button(
                    self.days, text=str(day), width=3, relief="flat", background=background,
                    command=lambda picked=date: self._pick(picked),
                ).grid(row=row, column=column, padx=1, pady=1)

    def _pick(self, date: pd.Timestamp) -> None:
        self.variable.set(f"{date:%Y-%m-%d}")
        self.top.destroy()
        self.on_pick()

    def _blank(self) -> None:
        self.variable.set("")
        self.top.destroy()
        self.on_pick()


class _LevelsEditor:
    """Keeps one check box per level of government and the option's letters (e.g. ``"fp"``) in step.

    See ``RatesPlotApp._add_levels_control``. The letters variable stays the
    single source of truth (for drawing, the command line, Back and the
    remembered settings); the boxes are a view of it. ``syncing`` stops the
    two sides' updates from triggering each other.
    """

    def __init__(self, payload: tk.StringVar, on_change) -> None:
        self.payload = payload
        self.on_change = on_change
        self.boxes = {letter: tk.BooleanVar(value=False) for letter in COMPONENT_LETTERS}
        self.widgets: list[ttk.Checkbutton] = []
        self.syncing = False
        self.payload.trace_add("write", lambda *_args: self._payload_changed())

    def set_state(self, state: list[str]) -> None:
        for widget in self.widgets:
            widget.state(state)

    def box_changed(self) -> None:
        if self.syncing:
            return
        self.syncing = True
        try:
            self.payload.set("".join(letter for letter in COMPONENT_LETTERS if self.boxes[letter].get()))
        finally:
            self.syncing = False
        self.on_change()

    def _payload_changed(self) -> None:
        """Show letters set from elsewhere (loading, Back, Reset) in the boxes."""
        if self.syncing:
            return
        letters = level_letters(self.payload.get())
        self.syncing = True
        try:
            for letter, box in self.boxes.items():
                box.set(letter in letters)
        finally:
            self.syncing = False


class _ChoicesEditor:
    """Keeps a list option's tick boxes (``Option.choices``) and its text (``"10y-2y,10y-3m"``) in step.

    See ``RatesPlotApp._add_choices_control``. As for the levels, the text
    stays the single source of truth; the boxes are a view of it. The last
    ticked box cannot be unticked (``refuse`` says why): drawing none is the
    curve's own box. A text "none" (a list for every chart that left this
    nation none of its items) ticks no box. A value set from elsewhere that
    has no box (a spread named on the command line) gets one, in a row "other".
    """

    def __init__(
        self, option: Option, payload: tk.StringVar, frame: ttk.Frame, on_change, refuse, nation: Nation | None = None
    ) -> None:
        self.option = option
        self.nation = nation
        self.payload = payload
        self.frame = frame
        self.on_change = on_change
        self.refuse = refuse
        self.boxes: dict[str, tk.BooleanVar] = {}
        self.widgets: list[ttk.Checkbutton] = []
        self.rows = 0
        self.syncing = False
        self.payload.trace_add("write", lambda *_args: self._payload_changed())

    def add_row(self, caption: str, boxes: list[tuple[str, str]]) -> None:
        """Add one row of boxes, its caption at the left."""
        ttk.Label(self.frame, text=f"{caption}:" if caption else "", foreground="#555555").grid(
            row=self.rows, column=0, sticky="w", padx=(0, 4)
        )
        for column, (value, text) in enumerate(boxes, start=1):
            variable = tk.BooleanVar(value=False)
            self.boxes[value] = variable
            check = ttk.Checkbutton(self.frame, text=text, variable=variable, command=lambda v=value: self.box_changed(v))
            check.grid(row=self.rows, column=column, sticky="w", padx=(0, 6))
            _Tooltip(check, _tooltip_text(self.option))
            self.widgets.append(check)
        self.rows += 1

    def set_state(self, state: list[str]) -> None:
        for widget in self.widgets:
            widget.state(state)

    def box_changed(self, value: str) -> None:
        if self.syncing:
            return
        ticked = [item for item, variable in self.boxes.items() if variable.get()]
        if not ticked:
            self.boxes[value].set(True)
            self.refuse(choice_refusal(self.option))
            return
        self.syncing = True
        try:
            self.payload.set(choices_text(self.option, ticked))
        finally:
            self.syncing = False
        self.on_change()

    def _payload_changed(self) -> None:
        """Show a text set from elsewhere (loading, Back, Reset) in the boxes."""
        if self.syncing:
            return
        values = choice_values(self.option, self.payload.get(), self.nation)
        new = [(value, value.replace("-", "–")) for value in values if value not in self.boxes]
        if new:
            self.add_row("other", new)
        self.syncing = True
        try:
            for value, variable in self.boxes.items():
                variable.set(value in values)
        finally:
            self.syncing = False


class _SizeEditor:
    """Keeps two boxes (width, height) and one ``WxH`` text variable in step.

    See ``RatesPlotApp._add_size_control``. ``syncing`` stops the three
    variables' write traces from triggering each other.
    """

    def __init__(self, payload: tk.StringVar, keep_ratio: bool) -> None:
        self.payload = payload
        self.width = tk.StringVar()
        self.height = tk.StringVar()
        self.keep_ratio = tk.BooleanVar(value=keep_ratio)
        self.ratio: float | None = None  # width / height, used while the lock is on
        self.syncing = False
        self.width.trace_add("write", lambda *_args: self._box_changed("width"))
        self.height.trace_add("write", lambda *_args: self._box_changed("height"))
        self.payload.trace_add("write", lambda *_args: self._payload_changed())

    @staticmethod
    def _number(text: str) -> int | None:
        text = text.strip()
        return int(text) if text.isdigit() and int(text) > 0 else None

    def _remember_ratio(self) -> None:
        width, height = self._number(self.width.get()), self._number(self.height.get())
        if width and height:
            self.ratio = width / height

    def lock_changed(self) -> None:
        # Ticking the lock freezes the shape the boxes have now.
        if self.keep_ratio.get():
            self._remember_ratio()

    def _box_changed(self, which: str) -> None:
        if self.syncing:
            return
        self.syncing = True
        try:
            if self.keep_ratio.get() and self.ratio:
                changed = self.width if which == "width" else self.height
                other = self.height if which == "width" else self.width
                value = self._number(changed.get())
                if value is not None:
                    other.set(str(max(1, round(value / self.ratio if which == "width" else value * self.ratio))))
                elif not changed.get().strip():
                    other.set("")
            else:
                self._remember_ratio()
            width, height = self.width.get().strip(), self.height.get().strip()
            self.payload.set(f"{width}x{height}" if width and height else width or (f"x{height}" if height else ""))
        finally:
            self.syncing = False

    def _payload_changed(self) -> None:
        """Show a ``WxH`` text set from elsewhere (loading, Back, Reset) in the boxes."""
        if self.syncing:
            return
        text = self.payload.get().strip().lower()
        if "x" in text:
            width, height = (part.strip() for part in text.split("x", 1))
        else:
            width, height = text, ""
        # One dimension alone means 4:3 on the command line; show the height it implies.
        if width.isdigit() and not height:
            height = str(round(int(width) * 3 / 4))
        elif height.isdigit() and not width:
            width = str(round(int(height) * 4 / 3))
        self.syncing = True
        try:
            self.width.set(width)
            self.height.set(height)
        finally:
            self.syncing = False
        self._remember_ratio()


class _Flow:
    """A block's controls in as many columns as fit, laid out again whenever the block's width changes.

    Terry, 2026-10-08: the column's width adjustable, its controls in two
    columns at the default width, in one when it is made narrow, in more
    when it is made wide. Each control is a cell (``add``), placed row by
    row; a cell added ``wide`` (a caption such as "By level") takes a row
    of its own and starts a new run of cells. Each run fills its rows in
    turn with as many cells as fit, the rest wrapping (Terry, 2026-10-14,
    batch 15.2: "three across, where possible, and if that leaves one down
    to make a total of four, so be it", with many more nations to come).
    Until then four boxes had gone two by two at any width, never three
    and one, so the nations and the rates stayed in two columns while the
    curves took three. Each column is as wide as its widest cell, so the
    cells line up from row to row.
    """

    def __init__(self, frame: ttk.Frame) -> None:
        self.frame = frame
        self.cells: list[tuple[tk.Widget, bool]] = []
        self.columns = 0  # the most columns that fit, as last laid out

    def add(self, cell: tk.Widget, wide: bool = False) -> None:
        self.cells.append((cell, wide))

    def most_columns(self) -> int:
        """The most columns any run of cells can use: as many as its cells."""
        return max(1, max((len(run) for run in self._runs()), default=1))

    def _runs(self) -> list[list[tk.Widget]]:
        """The runs of cells between the wide ones."""
        runs: list[list[tk.Widget]] = [[]]
        for cell, wide in self.cells:
            if wide:
                runs.append([])
            else:
                runs[-1].append(cell)
        return [run for run in runs if run]

    def _places(self, columns: int) -> list[tuple[tk.Widget, int, int, bool]]:
        """Each cell's row and column with up to ``columns`` columns: (cell, row, column, wide)."""
        places: list[tuple[tk.Widget, int, int, bool]] = []
        row = 0
        run: list[tk.Widget] = []

        def place_run() -> None:
            nonlocal row
            if not run:
                return
            across = min(columns, len(run))  # each row full before the next
            rows = -(-len(run) // across)
            for index, cell in enumerate(run):
                places.append((cell, row + index // across, index % across, False))
            row += rows
            run.clear()

        for cell, wide in self.cells:
            if wide:
                place_run()
                places.append((cell, row, 0, True))
                row += 1
            else:
                run.append(cell)
        place_run()
        return places

    def width_for(self, columns: int) -> int:
        """Return the width the cells need with up to ``columns`` columns (the block's padding and border not included)."""
        widths: dict[int, int] = {}
        wide = 0
        for cell, _row, column, is_wide in self._places(columns):
            if is_wide:
                wide = max(wide, cell.winfo_reqwidth())
            else:
                widths[column] = max(widths.get(column, 0), cell.winfo_reqwidth())
        return max(wide, sum(widths.values()) + _CELL_GAP_PX * max(0, len(widths) - 1))

    def fit(self, width: int) -> None:
        """Lay the cells out in the most columns that fit in a block ``width`` pixels wide (its frame's width)."""
        inner = width - _block_overhead(self.frame)
        fitting = [columns for columns in range(1, self.most_columns() + 1) if self.width_for(columns) <= inner]
        self.arrange(max(fitting, default=1))

    def arrange(self, columns: int) -> None:
        if columns == self.columns:
            return
        self.columns = columns
        places = self._places(columns)
        used = max((column for _cell, _row, column, wide in places if not wide), default=0) + 1
        for cell, row, column, wide in places:
            if wide:
                cell.grid(row=row, column=0, columnspan=used, sticky="w", pady=1, padx=0)
            else:
                cell.grid(row=row, column=column, columnspan=1, sticky="w", pady=1, padx=(0, _CELL_GAP_PX if column < used - 1 else 0))

    def used_columns(self) -> int:
        """How many columns the cells are in now."""
        return max((int(cell.grid_info().get("column", 0)) + 1 for cell, wide in self.cells if not wide and cell.grid_info()), default=1)


_overheads: dict[str, int] = {}


def _block_overhead(frame: ttk.Frame) -> int:
    """Return how much of a block's width its padding and border take, measured once per kind of frame."""
    kind = frame.winfo_class()
    if kind not in _overheads:
        probe = type(frame)(frame.master, padding=frame.cget("padding"))
        inner = tk.Frame(probe, width=100, height=1)
        inner.pack()
        probe.update_idletasks()
        _overheads[kind] = probe.winfo_reqwidth() - 100
        probe.destroy()
    return _overheads[kind]


def _tooltip_text(option: Option) -> str:
    """Return an option's group notes, its help text and its command-line spelling, one per line."""
    return "\n".join(option_help_lines(option))


def _enable_windows_dpi_awareness() -> None:
    """Ask Windows to render this process at native resolution.

    Without it, on a scaled display (e.g. 150 %) Windows stretches the whole
    window as a bitmap and the chart preview turns blurry. Purely cosmetic, so
    if the call is unavailable (older Windows) the window simply stays as it
    would otherwise be, and a note is printed.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError) as exc:
        print(f"Note: could not enable high-DPI rendering ({exc}); the preview may look soft.")


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


class RatesPlotApp:
    """The main window.

    Build with a Tk root, the starting choices (see ``starting_choices``),
    notes to show in the log, and the remembered window state.
    """

    def __init__(
        self,
        root: tk.Tk,
        choices: Choices,
        notes: list[str] | None = None,
        state: dict | None = None,
        normal_geometry: str | None = None,
    ) -> None:
        self.root = root
        self.messages: queue.Queue = queue.Queue()
        state = state or {}
        # The window's size and place when neither maximized nor minimized,
        # remembered with whether it is maximized (``_window_configured``);
        # ``normal_geometry`` is the one it was given, for a window that
        # starts maximized.
        self._normal_geometry = normal_geometry
        self._maximized = root.state() == "zoomed"
        root.bind("<Configure>", self._window_configured, add="+")

        # Controls, keyed by option name.
        self.payload_vars: dict[str, tk.StringVar] = {}
        self.flag_vars: dict[str, tk.BooleanVar] = {}
        self.flag_boxes: dict[str, ttk.Checkbutton] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self.value_entries: dict[str, ttk.Entry] = {}
        self.size_editors: dict[str, _SizeEditor] = {}
        self.size_entries: dict[str, tuple[ttk.Entry, ttk.Entry]] = {}  # the width and height boxes
        self.level_editors: dict[str, _LevelsEditor] = {}
        self.choice_editors: dict[str, _ChoicesEditor] = {}
        # The grey values of the text fields (keyed as payload_vars), and of the size boxes.
        self.hints: dict[str, _Hint] = {}
        self.size_hints: list[_Hint] = []

        # Per-country preview state, keyed by Country.key.
        self.tabs: dict[str, ttk.Frame] = {}
        self.canvases: dict[str, tk.Canvas] = {}
        self.scrollbars: dict[str, tuple[ttk.Scrollbar, ttk.Scrollbar]] = {}
        self.pngs: dict[str, bytes] = {}
        self.images: dict[str, Image.Image] = {}
        self.photos: dict[str, ImageTk.PhotoImage] = {}  # Tk shows an image only while a reference exists
        self.geometry: dict[str, ChartGeometry | None] = {}
        # Where each preview image sits on its canvas: (scale, left, top) in canvas coordinates.
        self.placement: dict[str, tuple[float, float, float]] = {}

        # Drawing state.
        self.rendering = False
        self.pending: tuple[PlotConfig, Choices] | None = None
        self._pending_forced = False  # a Refresh came during a drawing: draw again after it, even the same choices
        self.shown_config: PlotConfig | None = None
        # The shown charts' config with the automatic start filled in (the
        # dates they were drawn for); shown_config keeps a blank start blank.
        self.drawn_config: PlotConfig | None = None
        self.target_config: PlotConfig | None = None  # what the worker is drawing now
        # A nation ticked by hand: its tab is made current once its chart is drawn (batch 17.4).
        self._ticked_nation: str | None = None
        self.rendering_choices: Choices | None = None
        self.drawn_choices: Choices | None = None
        self._text_after_id: str | None = None
        self._resize_after_ids: dict[str, str] = {}
        self._loading = False
        # The text fields changed by hand, oldest first: a problem between two
        # (Min not below Max) is put on the one changed last (field_problems).
        self._changed: list[str] = []

        # Mouse state.
        # Each step Back can undo: the choices before it, and for a Reset the
        # preview's settings before it too (``_preview_settings``).
        self.history: list[tuple[Choices, tuple[str, dict[str, bool]] | None]] = []
        self._drag: dict | None = None
        self._wheel: dict | None = None

        self.zoom = tk.StringVar(value=state.get("zoom") if state.get("zoom") in ("fit", "actual") else _DEFAULT_PREVIEW)
        self.command = tk.StringVar()
        self.status = tk.StringVar(value="Starting …")

        self._build_layout()
        self._set_column_width(state.get("column_width"))
        self._load_choices(choices)
        for name, keep in state.get("keep_ratio", {}).items():
            if name in self.size_editors and isinstance(keep, bool):
                self.size_editors[name].keep_ratio.set(keep)
        if state.get("tab") in self.tabs:
            self.notebook.select(self.tabs[state["tab"]])
        for note in notes or []:
            self._append_log(note + "\n")
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._poll_id = self.root.after(_POLL_MS, self._poll)
        self.request_redraw()

    # -- layout -------------------------------------------------------------

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # The control column and the charts side by side, with a handle
        # between them that sets the column's width (Terry, 2026-10-08: "The
        # ability to adjust the horizontal width of the main options pane").
        # The width is remembered with the window's size (``_remember``).
        background = ttk.Style(self.root).lookup("TFrame", "background") or None
        self.paned = tk.PanedWindow(
            self.root,
            orient="horizontal",
            sashwidth=_SASH_PX,
            sashrelief="raised",
            borderwidth=0,
            background=background,
            opaqueresize=True,
        )
        self.paned.grid(row=0, column=0, sticky="nsew")
        self.column, panel, pinned = self._build_control_column(self.paned)
        self._build_option_controls(panel)
        self._build_actions(panel, pinned)
        self._build_log(panel)

        charts = ttk.Frame(self.paned, padding=(2, 8, 8, 8))
        charts.rowconfigure(0, weight=1)
        charts.columnconfigure(0, weight=1)
        self.notebook = ttk.Notebook(charts)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        for country in COUNTRIES:
            self._build_tab(country)
        self.paned.add(self.column, stretch="never")
        self.paned.add(charts, stretch="always", minsize=_MIN_CHARTS_PX)

        bar = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Command line:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.command, state="readonly").grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(bar, text="Copy", command=self._copy_command).grid(row=0, column=2)
        ttk.Label(bar, textvariable=self.status, anchor="w").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        self.root.bind("<F5>", lambda _event: self._refresh())
        self.root.bind("<Control-s>", lambda _event: self._save_png())
        self.root.bind("<Alt-Left>", lambda _event: self._back())

    def _build_control_column(self, master: tk.Widget) -> tuple[ttk.Frame, ttk.Frame, ttk.Frame]:
        """Return the column, and the frames the controls go in: a part that scrolls when the window is too short, and a bar below it.

        On a laptop screen (a 972 px window) the controls filled the column
        exactly, with the log out of sight, and one more row would have hidden
        the Redraw (now Refresh) and Save buttons. So the column is a canvas holding the
        controls' frame: when the window is taller than the controls need, the
        frame is stretched to the window and the log takes the rest, as
        before; when it is shorter, a scroll bar appears, and the mouse wheel
        scrolls the column while the pointer is over it (over the log, the log).
        The bar under it does not scroll: Refresh and Save go there, so they
        are always in sight however many controls there are (Terry,
        2026-10-06; batch 1 added a panel, and the buttons fell below the
        fold at 1728x972); Save log file joined them in batch 15. The
        column's width is the handle's (batch 7): the controls' frame takes
        the canvas's width, and each block lays its controls out to fit it
        (``_Flow``).
        """
        outer = ttk.Frame(master)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        pinned = ttk.Frame(outer, padding=(8, 4, 8, 8))
        pinned.grid(row=1, column=0, columnspan=2, sticky="ew")
        background = ttk.Style(self.root).lookup("TFrame", "background") or None
        # width=1: the canvas asks for no width of its own; the handle sets it.
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background=background, width=1)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        panel = ttk.Frame(canvas, padding=_PANEL_PAD_PX)
        window = canvas.create_window(0, 0, window=panel, anchor="nw")

        def fit(_event=None) -> None:
            width, needed = canvas.winfo_width(), panel.winfo_reqheight()
            height = max(needed, canvas.winfo_height())
            canvas.configure(scrollregion=(0, 0, width, height))
            canvas.itemconfigure(window, width=width, height=height)
            if needed > canvas.winfo_height():
                scroll.grid(row=0, column=1, sticky="ns")
            else:
                scroll.grid_remove()
                canvas.yview_moveto(0)

        def wheel(event) -> None:
            # Only with the pointer over the column; the charts zoom with their
            # own binding, and the log scrolls itself.
            try:
                widget = self.root.winfo_containing(event.x_root, event.y_root)
            except (KeyError, tk.TclError):  # Tk's own pop-ups have no tkinter widget
                return
            if isinstance(widget, tk.Text) or not scroll.winfo_ismapped():
                return
            while widget is not None and widget is not outer:
                widget = widget.master
            if widget is outer:
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        canvas.bind("<Configure>", fit)
        panel.bind("<Configure>", fit)
        self.root.bind_all("<MouseWheel>", wheel, add="+")
        self._scroll = scroll
        return outer, panel, pinned

    def _build_option_controls(self, panel: ttk.Frame) -> None:
        """One frame per block of the column (``frontend.control_blocks``), one control per GUI option, all from the table.

        A block with no title (the regression segments; the line labels with
        the latest data) is a frame like the others, its border unlabelled.
        Each control is a cell of its block's ``_Flow``, which puts the cells
        in as many columns as the column's width allows.
        """
        style = ttk.Style(self.root)
        style.configure("Error.TLabel", foreground=_ERROR_FOREGROUND)
        style.configure("Error.TEntry", foreground=_ERROR_FOREGROUND)

        self.flows: list[tuple[str, _Flow]] = []
        for key, title, members in control_blocks():
            frame = ttk.LabelFrame(panel, text=title or "", padding=(8, 4))
            frame.pack(fill="x", pady=(0, 6))
            flow = _Flow(frame)
            # A value that belongs to a flag (the regression tolerance) goes on
            # the flag's own row, which keeps the column short; tick boxes for
            # a flag's list (mortgage terms, spreads) go on the rows under it.
            attached = {
                option.turns_on: option
                for option in members
                if option.kind is Kind.VALUE and option.turns_on and option.editor != "choices"
            }
            under = {
                option.turns_on: option
                for option in members
                if option.kind is Kind.VALUE and option.turns_on and option.editor == "choices"
            }
            rows: list[Option] = []
            for option in members:
                if option in attached.values() or option in under.values():
                    continue
                rows.append(option)
                if option.name in under:
                    rows.append(under[option.name])
            for option in rows:
                cell = ttk.Frame(frame)
                if option.kind is Kind.VALUE and option.editor == "choices":
                    self._add_choices_control(cell, 0, option)
                    flow.add(cell, wide=True)
                elif option.kind is Kind.VALUE and option.editor == "size":
                    flow.add(cell)
                    flow.add(self._add_size_control(cell, frame, option))
                elif option.kind is Kind.VALUE and option.editor == "levels":
                    # "By level" over its boxes, which line up with the curves' (Terry, 2026-10-08).
                    caption, boxes = self._add_levels_control(frame, option)
                    flow.add(caption, wide=True)
                    for box in boxes:
                        flow.add(box)
                elif option.kind is Kind.VALUE:
                    self._add_value_control(cell, 0, option, entry_width=_DATE_ENTRY_CHARS if option.editor == "date" else 16)
                    flow.add(cell)
                else:
                    value = attached.get(option.name)
                    field = ttk.Frame(frame) if value is not None else None
                    self._add_flag_control(cell, 0, option, value, field)
                    flow.add(cell)
                    if field is not None:
                        flow.add(field)
            frame.bind("<Configure>", lambda event, flow=flow: flow.fit(event.width), add="+")
            self.flows.append((key, flow))

    def _add_flag_control(
        self, cell: ttk.Frame, row: int, option: Option, value: Option | None = None, field: ttk.Frame | None = None
    ) -> None:
        """A check box in ``cell``; with ``value``, that option's text field in ``field``, the cell after it.

        The regression tolerance reads as one phrase with its box (Terry,
        2026-10-08: the box between the words): "Regression segments,
        tolerance [1] % of axis". Its label, "tolerance, % of axis", stays
        whole in messages and on the page, where a box cannot sit inside a
        caption; here the box goes where its comma was. The field is a cell
        of its own, so it goes under the check box when the column is narrow.
        """
        variable = tk.BooleanVar(value=False)
        self.flag_vars[option.name] = variable
        box = ttk.Checkbutton(
            cell,
            text=option.label if value is None else f"{option.label},",
            variable=variable,
            command=lambda name=option.name: self._flag_changed(name),
        )
        box.grid(row=row, column=0, sticky="w")
        self.flag_boxes[option.name] = box
        _Tooltip(box, _tooltip_text(option))
        if value is not None and field is not None:
            before, _comma, after = value.label.partition(", ")
            # No padding: the row stays as tall as a check box.
            self._add_value_control(field, 0, value, entry_width=5, pady=0, text=before, after=after)

    def _add_value_control(
        self,
        frame: ttk.Frame,
        row: int,
        option: Option,
        entry_width: int = 16,
        pady: int = 1,
        key: str | None = None,
        text: str | None = None,
        after: str = "",
    ) -> None:
        """A label and a text field; ``key`` names a nation's own field ("us:max"), else the option's name.

        ``text`` replaces the option's label before the field; ``after`` is put after it ("% of axis").
        """
        key = key or option.name
        variable = tk.StringVar()
        self.payload_vars[key] = variable
        label = ttk.Label(frame, text=option.label if text is None else text)
        label.grid(row=row, column=0, sticky="w", padx=(0, 6), pady=pady)
        entry = ttk.Entry(frame, textvariable=variable, width=entry_width)
        entry.grid(row=row, column=1, sticky="ew", pady=pady)
        if after:
            ttk.Label(frame, text=after).grid(row=row, column=2, sticky="w", padx=(4, 0), pady=pady)
        # A number typed without its 0 gets it on Enter or on leaving the field (batch 15.5).
        entry.bind("<Return>", lambda _event: (self._add_leading_zero(key), self.request_redraw()))
        entry.bind("<FocusOut>", lambda _event: self._add_leading_zero(key), add="+")
        variable.trace_add("write", lambda *_args: self._text_changed(key))
        self.value_labels[key] = label
        self.value_entries[key] = entry
        tip = _tooltip_text(option) + "\nBlank = default (shown in grey)."
        for widget in (label, entry):
            _Tooltip(widget, tip)
        self.hints[key] = _Hint(entry, variable, tip)
        if option.editor == "date":
            button = ttk.Button(
                frame, text="📅", width=3,
                command=lambda: DatePicker(entry, variable, option.name, on_pick=self.request_redraw),
            )
            button.grid(row=row, column=2, padx=(2, 0), pady=1)
            _Tooltip(button, "Pick a date from a calendar")

    def _add_levels_control(self, frame: ttk.Frame, option: Option) -> tuple[ttk.Label, list[ttk.Checkbutton]]:
        """One check box per level of government, writing the option's letters ("fp" …): return its caption and its boxes.

        Ticking none gives the aggregate lines. The one control serves debt and
        interest alike (``--debt:`` and ``--interest:`` take the same letters).
        The caption and each box are cells of the block (``_Flow``).
        """
        payload = tk.StringVar()
        self.payload_vars[option.name] = payload
        label = ttk.Label(frame, text=option.label)
        self.value_labels[option.name] = label
        editor = _LevelsEditor(payload, on_change=self.request_redraw)
        self.level_editors[option.name] = editor
        tip = _tooltip_text(option) + "\nNone ticked = debt and interest in total."
        boxes = []
        for letter, text in LEVEL_BOXES:
            check = ttk.Checkbutton(frame, text=text, variable=editor.boxes[letter], command=editor.box_changed)
            editor.widgets.append(check)
            _Tooltip(check, tip)
            boxes.append(check)
        _Tooltip(label, tip)
        return label, boxes

    def _add_choices_control(self, frame: ttk.LabelFrame, row: int, option: Option, nation: Nation | None = None) -> None:
        """A list option as tick boxes (``Option.choices``), one row of boxes per row offered.

        A list that belongs to a flag (mortgage terms, spreads) sits indented
        under that flag's check box, with no label of its own, and is greyed
        while the flag is off; one of its own (the yield terms) has its label
        at the left, as the other fields do. A nation's own list (under its
        tab) has its label above, and only the boxes its chart can draw. A
        nation's box of a term drawn plus a margin (``options.margin_options``)
        has the margin's field beside it (batch 9.4): "prime margin [0.5] pts",
        as the tolerance sits on the regression row.
        """
        key = nation_choice(nation, option) if nation else option.name
        payload = tk.StringVar()
        self.payload_vars[key] = payload
        box = ttk.Frame(frame)
        if nation is not None:
            label = ttk.Label(frame, text=option.label)
            label.grid(row=0, column=row, sticky="w", padx=(0, 12))
            self.value_labels[key] = label
            _Tooltip(label, _tooltip_text(option))
            box.grid(row=1, column=row, sticky="nw", padx=(0, 12))
        elif option.turns_on:
            box.grid(row=row, column=0, columnspan=3, sticky="w", padx=(22, 0), pady=(0, 2))
        else:
            label = ttk.Label(frame, text=option.label)
            label.grid(row=row, column=0, sticky="nw", padx=(0, 6), pady=(3, 1))
            self.value_labels[option.name] = label
            _Tooltip(label, _tooltip_text(option))
            box.grid(row=row, column=1, columnspan=2, sticky="w", pady=1)
        editor = _ChoicesEditor(option, payload, box, on_change=self._choices_changed, refuse=self.status.set, nation=nation)
        for caption, boxes in choice_rows(option, "", nation):
            editor.add_row(caption, boxes)
        self.choice_editors[key] = editor
        if nation is None or option.fields != ("mortgage_terms",):
            return
        for term, margin in margin_options().items():
            if term not in editor.boxes:
                continue
            # The editor keeps its boxes and their widgets in the same order.
            term_box = editor.widgets[list(editor.boxes).index(term)].grid_info()
            cell = ttk.Frame(box)
            # Spanning the columns after it, so no box of the row above is widened.
            cell.grid(row=int(term_box["row"]), column=int(term_box["column"]) + 1, columnspan=8, sticky="w")
            self._add_value_control(cell, 0, margin, entry_width=5, pady=0, key=nation_choice(nation, margin), text="margin", after="pts")

    def _choices_changed(self) -> None:
        """A tick box of a list changed: what it greys or ungreys (a margin), then a drawing."""
        self._update_dependent_controls()
        self.request_redraw()

    def _add_size_control(self, cell: ttk.Frame, frame: ttk.Frame, option: Option) -> ttk.Checkbutton:
        """Width and height boxes, "x" between them, in ``cell``; return the "Preserve aspect ratio" lock, made in ``frame``.

        The option's own text variable (``WxH``, the command-line form) stays
        the single source of truth for drawing, the command line, Back/Unzoom
        and the remembered settings; the two boxes are a view of it and write
        it back. With the lock on, changing one box recomputes the other from
        the ratio the pair had when the lock was last set (or the pair was
        loaded); with it off, each box changes alone. A blank box with the
        other filled keeps the command line's meaning: 4:3 from the one given.
        The lock is a cell of its own in the block, so it stands beside the
        boxes when the column is wide enough and under them when it is not
        (Terry, 2026-10-08).
        """
        payload = tk.StringVar()
        self.payload_vars[option.name] = payload
        label = ttk.Label(cell, text=option.label)
        label.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=1)
        self.value_labels[option.name] = label

        box = ttk.Frame(cell)
        box.grid(row=0, column=1, sticky="w", pady=1)
        editor = _SizeEditor(payload, keep_ratio=True)
        self.size_editors[option.name] = editor
        width_entry = ttk.Entry(box, textvariable=editor.width, width=7, justify="right")
        width_entry.grid(row=0, column=0)
        ttk.Label(box, text=" x ").grid(row=0, column=1)
        height_entry = ttk.Entry(box, textvariable=editor.height, width=7, justify="right")
        height_entry.grid(row=0, column=2)
        ttk.Label(box, text=" px").grid(row=0, column=3)
        lock = ttk.Checkbutton(frame, text="Preserve aspect ratio", variable=editor.keep_ratio, command=editor.lock_changed)

        payload.trace_add("write", lambda *_args: self._text_changed(option.name))
        self.size_entries[option.name] = (width_entry, height_entry)
        for entry in (width_entry, height_entry):
            entry.bind("<Return>", lambda _event: self.request_redraw())
        tip = _tooltip_text(option) + "\nWidth x height in pixels. Blank = default (shown in grey)."
        for widget in (label, width_entry, height_entry):
            _Tooltip(widget, tip)
        default = PlotConfig()
        for entry, variable, pixels in (
            (width_entry, editor.width, default.width_px),
            (height_entry, editor.height, default.height_px),
        ):
            self.size_hints.append(_Hint(entry, variable, tip, str(pixels)))
        _Tooltip(lock, "When ticked, changing one box changes the other to keep the current shape.")
        return lock

    def _set_column_width(self, remembered: object) -> None:
        """Give the column its remembered width, or the default; and the narrowest the handle lets it be.

        The default is wide enough for two columns in the blocks Terry named
        on 2026-10-08 (the nations, the four rates, Start and End, the size
        with its lock, the measure: ``_TWO_COLUMN_BLOCKS``), and never
        narrower than the narrowest. The narrowest is what every block needs
        in one column, the Preview panel and the pinned bar in two rows; the
        handle stops there, and the charts keep at least ``_MIN_CHARTS_PX``.
        A remembered width outside those bounds (another screen) is not used.
        """
        # The Preview's note at its narrowest wrap: it widens with the column
        # (``_build_actions``), and its width then is no measure of the least.
        self._zoom_note.configure(wraplength=_NOTE_WRAP_PX)
        self.root.update_idletasks()
        around = 2 * _PANEL_PAD_PX + self._scroll.winfo_reqwidth()  # the panel's padding, and room for its scroll bar
        one = [flow.width_for(1) + _block_overhead(flow.frame) for _key, flow in self.flows]
        two = [flow.width_for(2) + _block_overhead(flow.frame) for key, flow in self.flows if key in _TWO_COLUMN_BLOCKS]
        bar = self._pinned.winfo_reqwidth() - self._bar.winfo_reqwidth() + self._bar_width(2)  # its padding, and two rows
        narrowest = max(max(one) + around, self._preview.winfo_reqwidth() + around, bar)
        default = max([narrowest, *(width + around for width in two)])
        widest = self.root.winfo_screenwidth() - _MIN_CHARTS_PX
        width = remembered if isinstance(remembered, int) and narrowest <= remembered <= widest else default
        self._column_width = width
        self.paned.paneconfigure(self.column, minsize=narrowest, width=width)

    def _current_column_width(self) -> int:
        """The column's width now (the handle's place), or the one it was given while the window is not shown."""
        if self.paned.winfo_ismapped():
            self._column_width = self.paned.sash_coord(0)[0]
        return self._column_width

    def _build_actions(self, panel: ttk.Frame, pinned: ttk.Frame) -> None:
        """The Preview panel and the Reset button in the column; Refresh, Save PNG and Save log file in the ``pinned`` bar."""
        preview = ttk.LabelFrame(panel, text="Preview", padding=(8, 4))
        preview.pack(fill="x", pady=(0, 6))
        self._preview, self._pinned = preview, pinned
        preview.columnconfigure((0, 1), weight=1)
        for column, (value, text) in enumerate((("fit", "Fit to window"), ("actual", "Actual size"))):
            ttk.Radiobutton(preview, text=text, value=value, variable=self.zoom, command=self._refresh_all_views).grid(
                row=0, column=column, sticky="w"
            )
        self.back_button = ttk.Button(preview, text="◀ Back (Alt+←)", command=self._back)
        self.back_button.grid(row=1, column=0, sticky="ew", padx=1, pady=1)
        self.unzoom_button = ttk.Button(preview, text="Unzoom", command=self._unzoom)
        self.unzoom_button.grid(row=1, column=1, sticky="ew", padx=1, pady=1)
        hint = ttk.Label(preview, text=_ZOOM_HINT, wraplength=_NOTE_WRAP_PX, foreground="#555555")
        hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        # The note wraps to the column's width, whatever the handle makes it.
        preview.bind("<Configure>", lambda event: hint.configure(wraplength=max(_NOTE_WRAP_PX, event.width - 24)), add="+")
        self._zoom_note = hint

        # The pinned bar: Refresh, Save PNG and Save log file (Terry,
        # 2026-10-14, batch 15.3: the third button beside the other two). In
        # one row when the column is wide enough (at the default width), else
        # the log's button under the other two (``_arrange_bar``): the bar
        # takes two rows, as the blocks do, rather than making the column's
        # narrowest width larger.
        self._bar = ttk.Frame(pinned)
        self._bar.pack(fill="x")
        self._bar_buttons = [
            ttk.Button(self._bar, text=text, command=command)
            for text, command in (
                ("Refresh (F5)", self._refresh),
                ("Save PNG… (Ctrl+S)", self._save_png),
                ("Save log file…", self._save_log),
            )
        ]
        _Tooltip(self._bar_buttons[2], "Save the whole message log as a text file.")
        self._bar_rows = 0
        self._arrange_bar(1)
        self._bar.bind("<Configure>", lambda event: self._arrange_bar(1 if event.width >= self._bar_width(1) else 2), add="+")

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(0, 6))
        ttk.Button(buttons, text="Reset to defaults", command=self._reset).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        buttons.columnconfigure(0, weight=1)

    def _bar_width(self, rows: int) -> int:
        """The width the pinned bar's buttons need in one row, or in two (the log's button under the other two)."""
        widths = [button.winfo_reqwidth() + 2 for button in self._bar_buttons]  # each with its padx of 1 a side
        return sum(widths) if rows == 1 else max(widths[0] + widths[1], widths[2])

    def _arrange_bar(self, rows: int) -> None:
        """Put the pinned bar's buttons in one row, or the log's button under the other two."""
        if rows == self._bar_rows:
            return
        self._bar_rows = rows
        refresh, save, log = self._bar_buttons
        refresh.grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        save.grid(row=0, column=1, sticky="ew", padx=1, pady=1)
        if rows == 1:
            log.grid(row=0, column=2, columnspan=1, sticky="ew", padx=1, pady=1)
        else:
            log.grid(row=1, column=0, columnspan=2, sticky="ew", padx=1, pady=1)
        self._bar.columnconfigure((0, 1), weight=1)
        self._bar.columnconfigure(2, weight=1 if rows == 1 else 0)

    def _build_log(self, panel: ttk.Frame) -> None:
        frame = ttk.LabelFrame(panel, text="Message log", padding=4)
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(frame, width=24, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_tab(self, country: Country) -> None:
        tab = ttk.Frame(self.notebook)
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)
        canvas = tk.Canvas(tab, background="white", highlightthickness=0, cursor="crosshair")
        x_scroll = ttk.Scrollbar(tab, orient="horizontal", command=canvas.xview)
        y_scroll = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        key = country.key
        canvas.bind("<Configure>", lambda _event: self._schedule_view_refresh(key))
        canvas.bind("<ButtonPress-1>", lambda event: self._drag_start(key, event, "zoom"))
        canvas.bind("<B1-Motion>", lambda event: self._drag_motion(key, event))
        canvas.bind("<ButtonRelease-1>", lambda event: self._drag_end(key, event))
        for button in (2, 3):
            canvas.bind(f"<ButtonPress-{button}>", lambda event: self._drag_start(key, event, "pan"))
            canvas.bind(f"<B{button}-Motion>", lambda event: self._drag_motion(key, event))
            canvas.bind(f"<ButtonRelease-{button}>", lambda event: self._drag_end(key, event))
        canvas.bind("<MouseWheel>", lambda event: self._wheel_turned(key, event))
        self._build_nation_panel(tab, next(nation for nation in NATIONS if nation.key == key))
        self.notebook.add(tab, text=TAB_TITLES.get(country.key, country.key))
        self.tabs[key] = tab
        self.canvases[key] = canvas
        self.scrollbars[key] = (x_scroll, y_scroll)

    def _build_nation_panel(self, tab: ttk.Frame, nation: Nation) -> None:
        """The nation's own controls, under its chart (``frontend.NATION_OPTIONS``).

        Its yield terms, spreads, policy terms and mortgage terms as tick
        boxes (only those its chart can draw), then its axis limits. They set that chart only;
        the curves' own boxes (yields, spreads, mortgages on or off) stay in
        the column, for both charts (Terry, 2026-10-06: a panel under each
        tab, ready for more nations).
        """
        frame = ttk.LabelFrame(tab, text=f"{nation.name} only", padding=(8, 2))
        frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        column = 0
        limits = ttk.Frame(frame)
        # The spreads next to the yield terms, as in the column (Terry,
        # 2026-10-06); the policy terms (batch 9.1) before the mortgages, as
        # the column has the policy rate before them.
        lists = sorted(
            (option for option in NATION_OPTIONS if option.editor == "choices"),
            key=lambda option: ("yield_terms", "spread_pairs", "policy_terms", "mortgage_terms").index(option.fields[0]),
        )
        for option in lists:
            self._add_choices_control(frame, column, option, nation)
            column += 1
        limits.grid(row=0, column=column, rowspan=2, sticky="nw")
        # A column per axis, Max above Min, Top above Bottom (LIMIT_COLUMNS).
        for axis, names in enumerate(LIMIT_COLUMNS):
            for place, name in enumerate(names):
                cell = ttk.Frame(limits)
                cell.grid(row=place, column=axis, sticky="e", padx=(0, 10))
                option = by_name(name)
                self._add_value_control(cell, 0, option, entry_width=7, pady=1, key=nation_choice(nation, option))

    # -- choices ------------------------------------------------------------

    def _load_choices(self, choices: Choices) -> None:
        """Set every control from ``choices`` without triggering a redraw per control."""
        payloads, flags = choices
        self._loading = True
        try:
            for name, text in payloads.items():
                if name in self.payload_vars:
                    self.payload_vars[name].set(text)
            for name, value in flags.items():
                if name in self.flag_vars:
                    self.flag_vars[name].set(value)
        finally:
            self._loading = False
        self._update_dependent_controls()

    def _snapshot(self) -> Choices:
        """Return every control's current value, blanks included."""
        return (
            {name: var.get() for name, var in self.payload_vars.items()},
            {name: var.get() for name, var in self.flag_vars.items()},
        )

    def _flag_changed(self, name: str) -> None:
        # The command-line rule "no country means both" would make unticking
        # the last country draw both, which would look like a bug here.
        countries = [option.name for option in options_in("country") if option.in_gui]
        if name in countries and not any(self.flag_vars[country].get() for country in countries):
            self.flag_vars[name].set(True)
            self.status.set("At least one country must stay selected.")
            return
        if name in nation_boxes():
            # Batch 17.4: a nation ticked by hand gets its tab once its chart is
            # drawn (``_show_chart``); unticked before that, it does not.
            key = nation_boxes()[name]
            if self.flag_vars[name].get():
                self._ticked_nation = key
            elif self._ticked_nation == key:
                self._ticked_nation = None
        units = [option.name for option in options_in("units") if option.name in self.flag_vars]
        if name in units:
            # One measure at a time: ticking one unticks the others.
            if self.flag_vars[name].get():
                for other in units:
                    if other != name:
                        self.flag_vars[other].set(False)
            # Top and Bottom are in the measure's units (dollars, or percent
            # under -r), so values typed or zoomed for one measure are wrong
            # for another: clear them without a redraw per field.
            self._loading = True
            try:
                for bound in bound_keys():
                    if bound in self.payload_vars:
                        self.payload_vars[bound].set("")
            finally:
                self._loading = False
        # A curve ticked or unticked can give -r its effect or take it away
        # (it needs debt or interest): Top and Bottom in the other unit go.
        payloads, flags = self._snapshot()
        self._loading = True
        try:
            for bound in bounds_in_other_units(payloads, flags):
                self.payload_vars[bound].set("")
        finally:
            self._loading = False
        self._update_dependent_controls()
        self.request_redraw()

    def _update_dependent_controls(self) -> None:
        """Grey out controls that have no effect (Terry, 2026-10-08), keeping their ticks and texts.

        GDP under -r, where it is the divisor and is not drawn; what has no
        curve to act on (``frontend.idle_controls``): % of GDP and the levels
        without debt or interest, Per capita, the regression segments and
        each chart's Top and Bottom without debt, GDP or interest; and a
        value whose flag is off (the regression tolerance without --reg, the
        mortgage terms without mortgages); and a nation's margin while its
        chart draws not its term, the prime rate (``options.idle_margins``).
        """
        flags = {name: variable.get() for name, variable in self.flag_vars.items()}
        idle = idle_controls(flags)
        idle_margin_keys = idle_margins(self._snapshot()[0], flags)
        for name, box in self.flag_boxes.items():
            if name in GREYABLE_OPTIONS:
                box.state(["disabled"] if name in idle else ["!disabled"])
        for key in self.payload_vars:
            option = option_of(key)
            off = option.turns_on in flags and not flags[option.turns_on]
            if option.turns_on not in flags and option.name not in GREYABLE_OPTIONS:
                continue
            state = ["disabled"] if off or option.name in idle or key in idle_margin_keys else ["!disabled"]
            if key in self.value_entries:
                self.value_entries[key].state(state)
            if key in self.value_labels:
                self.value_labels[key].state(state)
            if key in self.choice_editors:
                self.choice_editors[key].set_state(state)
            if key in self.level_editors:
                self.level_editors[key].set_state(state)
        # A greyed field shows no grey value; one no longer greyed shows it again.
        for hint in (*self.hints.values(), *self.size_hints):
            hint.update()

    def _show_hints(self) -> None:
        """Give each blank field the value in effect, from the charts on screen (``frontend.field_hints``)."""
        drawn = self.drawn_config
        keys = [country.key for country in COUNTRIES if drawn is not None and getattr(drawn, country.show_field)]
        hints = field_hints(drawn, {key: self.geometry.get(key) for key in keys})
        for key, hint in self.hints.items():
            hint.set(hints.get(key, ""))

    def _add_leading_zero(self, key: str) -> None:
        """Rewrite a number typed without the 0 before its point with it: ".3" → "0.3" (Terry, 2026-10-13, batch 15.5).

        The command line follows (``--reg:0.3``); the value is the same, so
        nothing is drawn again for it (``frontend.with_leading_zero``).
        """
        variable = self.payload_vars[key]
        text = variable.get()
        fixed = with_leading_zero(text)
        if fixed != text:
            variable.set(fixed)

    def _text_changed(self, key: str) -> None:
        if self._loading:
            return
        if key in self._changed:
            self._changed.remove(key)
        self._changed.append(key)
        if self._text_after_id is not None:
            self.root.after_cancel(self._text_after_id)
        self._text_after_id = self.root.after(_TEXT_REDRAW_DELAY_MS, self.request_redraw)

    def _update_command_line(self) -> None:
        tokens = command_line_tokens(*self._snapshot())
        self.command.set(subprocess.list2cmdline(["python", _SCRIPT_NAME, *tokens]))

    def _mark_invalid_fields(self, payloads: dict[str, str], flags: dict[str, bool]) -> list[str]:
        """Colour the label and the text of every field in the wrong (``frontend.field_problems``); return the messages.

        Terry, 2026-10-12: the text red as well as the label, since he was
        not sure at once which of the width and height boxes was wrong; and
        crossed or equal limits marked too, on the box changed last.
        """
        problems = field_problems(payloads, flags, self._changed)
        for key, label in self.value_labels.items():
            label.configure(style="Error.TLabel" if key in problems else "TLabel")
        for key, entry in self.value_entries.items():
            entry.configure(style="Error.TEntry" if key in problems else "TEntry")
        for name, entries in self.size_entries.items():
            faults = size_boxes_at_fault(payloads[name]) if name in problems else (False, False)
            for entry, fault in zip(entries, faults):
                entry.configure(style="Error.TEntry" if fault else "TEntry")
        return [problem_text(key, message) for key, message in problems.items()]

    # -- drawing ------------------------------------------------------------

    def request_redraw(self, force: bool = False) -> None:
        """Validate the controls and, if they describe a new chart, draw it."""
        if self._text_after_id is not None:
            self.root.after_cancel(self._text_after_id)
        self._text_after_id = None
        self._update_command_line()
        self._update_view_buttons()
        snapshot = self._snapshot()
        # A greyed field has no effect: a bad text left there must not stop the drawing.
        payloads = drawn_payloads(*snapshot)
        problems = self._mark_invalid_fields(payloads, snapshot[1])
        try:
            config = config_from_choices(payloads, snapshot[1])
        except ValueError as exc:
            # A field's problem first (a problem between fields is on the one
            # changed last); one no field is involved in (-r with -p) alone.
            self.status.set(f"Not drawn: {problems[0] if problems else exc}")
            return

        if force:
            self.shown_config = None
        if self.rendering:
            # Compare with what is being drawn, not what is on screen: going
            # back to the displayed view while a new one is being drawn must
            # still queue a drawing, or the old view would replace it. A
            # Refresh asked for meanwhile is kept: the drawing under way may
            # be using the downloads it dropped.
            if config == self.target_config and not force and not self._pending_forced:
                self.pending = None
                return
            self.pending = (config, snapshot)
            self._pending_forced = self._pending_forced or force
            self.status.set("Will redraw with the new settings when the current drawing finishes …")
            return
        if config == self.shown_config:
            return
        self._start_render(config, snapshot)

    def _start_render(self, config: PlotConfig, choices: Choices) -> None:
        self.rendering = True
        self.target_config = config
        self.rendering_choices = choices
        countries = [country for country in COUNTRIES if getattr(config, country.show_field)]
        # Tk makes the nearest tab current when the current one is hidden; the
        # first shown is made current instead (batch 17.4, as on the page).
        current = self._current_tab_key()
        for country in COUNTRIES:
            self.notebook.tab(self.tabs[country.key], state="normal" if country in countries else "hidden")
        key = current_tab([country.key for country in countries], current)
        if key is not None and key != self._current_tab_key():
            self.notebook.select(self.tabs[key])
        self.status.set("Drawing …")
        # What is really downloaded is logged line by line, and what is
        # reused counted at the end (http.drawing_downloads).
        start = "the automatic start" if config.start is None else f"{config.start:%Y-%m-%d}"
        self._append_log(f"--- drawing {config.width_px}x{config.height_px}, {start} to {config.end:%Y-%m-%d}\n")
        threading.Thread(target=self._render_worker, args=(config, countries), daemon=True).start()

    def _render_worker(self, config: PlotConfig, countries: list[Country]) -> None:
        """Worker thread: draw each country to PNG bytes and post them. Never touches Tk.

        A blank Start is found first, once for all the charts (``resolve_start``).
        What this thread prints goes to the message log (``console``), with a
        line for each real download (``http.drawing_downloads``); the main
        thread's output goes to the console as before. A chart that cannot
        be drawn (its source down, 2026-10-21) is named, and the others are
        drawn; a source drawn from its last good copy (batch 20) is named in
        the status line, once the drawing's log has its warning.
        """
        with this_thread_output_to(lambda text: self.messages.put(("log", text))), http.drawing_downloads() as downloads:
            try:
                drawn = resolve_start(config)
            except Exception as exc:  # reported in the window and log, never swallowed
                self.messages.put(("failed", config, f"{type(exc).__name__}: {exc}", traceback.format_exc()))
                return
            not_drawn: dict[str, str] = {}
            for country in countries:
                try:
                    figure = build_figure(country, drawn)
                except Exception as exc:  # that chart alone; reported in the window and log
                    not_drawn[country.key] = f"{type(exc).__name__}: {exc}"
                    self.messages.put(("not drawn", country.key, traceback.format_exc()))
                    continue
                png = png_bytes(figure)
                # Measured after savefig, so the axes positions are the final rendered ones.
                geometry = ChartGeometry.from_figure(figure, drawn)
                self.messages.put(("chart", country.key, png, geometry))
        self.messages.put(("done", config, drawn, not_drawn, downloads.copies_used()))

    def _poll(self) -> None:
        """Handle every message the worker has posted, then check again shortly."""
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]
                if kind == "log":
                    self._append_log(message[1])
                elif kind == "chart":
                    self._show_chart(message[1], message[2], message[3])
                elif kind == "not drawn":
                    self._append_log(message[2])
                    self._clear_chart(message[1])
                elif kind == "done":
                    self._render_finished(message[1], None, message[2], message[3], message[4])
                elif kind == "failed":
                    self._append_log(message[3])
                    self._render_finished(message[1], message[2])
        except queue.Empty:
            pass
        self._poll_id = self.root.after(_POLL_MS, self._poll)

    def _show_chart(self, key: str, png: bytes, geometry: ChartGeometry | None) -> None:
        self.pngs[key] = png
        self.geometry[key] = geometry
        image = Image.open(io.BytesIO(png))
        image.load()
        self.images[key] = image
        self._refresh_view(key)
        if key == self._ticked_nation:
            self._ticked_nation = None
            self.notebook.select(self.tabs[key])

    def _clear_chart(self, key: str) -> None:
        """Take a chart that could not be drawn off its tab, so an older drawing is not shown as this one."""
        self.pngs.pop(key, None)
        self.images.pop(key, None)
        self.geometry[key] = None
        self.canvases[key].delete("all")

    def _render_finished(
        self,
        config: PlotConfig,
        error: str | None,
        drawn: PlotConfig | None = None,
        not_drawn: dict[str, str] | None = None,
        copies: list[str] | None = None,
    ) -> None:
        self.rendering = False
        if error is None:
            self.shown_config = config
            self.drawn_config = drawn
            self.drawn_choices = self.rendering_choices
            not_drawn = not_drawn or {}
            drawn = [TAB_TITLES.get(c.key, c.key) for c in COUNTRIES if getattr(config, c.show_field) and c.key not in not_drawn]
            if len(drawn) > 1:
                names = f"{', '.join(drawn[:-1])} and {drawn[-1]}"
            else:  # one chart, or none: every chart's source failing (an IndexError here until 2026-10-22)
                names = drawn[0] if drawn else ""
            failures = "; ".join(f"{TAB_TITLES.get(key, key)} not drawn: {why}" for key, why in not_drawn.items())
            # Sources that failed and were drawn from their last good copies (batch 20).
            from_copies = f"From last good copies, their sources failing: {'; '.join(copies)}." if copies else ""
            if failures or from_copies:
                parts = [f"Drawn: {names}." if drawn else "", f"{failures}." if failures else "", from_copies]
                self.status.set(" ".join(part for part in parts if part) + " (details in the message log)")
            else:
                self.status.set(f"Drawn: {names} at {config.width_px} x {config.height_px} px.")
            self._show_hints()
            self._remember()
        else:
            self.status.set(f"Drawing failed: {error} (details in the message log)")
        pending, self.pending = self.pending, None
        forced, self._pending_forced = self._pending_forced, False
        if pending is not None and (pending[0] != self.shown_config or forced):
            self._start_render(*pending)

    # -- preview ------------------------------------------------------------

    def _schedule_view_refresh(self, key: str) -> None:
        previous = self._resize_after_ids.pop(key, None)
        if previous is not None:
            self.root.after_cancel(previous)
        self._resize_after_ids[key] = self.root.after(_RESIZE_DELAY_MS, lambda: self._refresh_view(key))

    def _refresh_all_views(self) -> None:
        for key in self.images:
            self._refresh_view(key)

    def _refresh_view(self, key: str) -> None:
        """Show the chart scaled to fit its tab, or at actual size with scroll bars.

        Fitted, it is shrunk or enlarged to fill the tab, keeping its shape
        (Terry, 2026-10-12: it only ever shrank, leaving a small chart in a
        sea of white). An enlarged preview is the PNG's own pixels scaled up,
        so slightly soft, as in any image viewer; the saved file is the PNG
        itself, and "Actual size" shows it pixel for pixel. Drawing the chart
        again at the tab's size would be sharp, but the ticks, the legend's
        place and the labels are chosen in pixels, so it could differ from
        the file saved.
        """
        # A refresh after a resize may still be waiting (this call came from
        # a new chart, or the preview's mode): cancel it, or once forgotten it
        # could fire after the window is closed ("invalid command name").
        waiting = self._resize_after_ids.pop(key, None)
        if waiting is not None:
            self.root.after_cancel(waiting)
        image = self.images.get(key)
        canvas = self.canvases[key]
        if image is None:
            return
        # Scroll bars only mean something at actual size.
        for scrollbar in self.scrollbars[key]:
            if self.zoom.get() == "fit":
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
        canvas.update_idletasks()
        view_width, view_height = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        canvas.delete("all")
        if self.zoom.get() == "fit":
            scale = min(view_width / image.width, view_height / image.height)
            shown = image
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            if size != (image.width, image.height):
                shown = image.resize(size, Image.Resampling.LANCZOS)
                scale = shown.width / image.width
            left, top = (view_width - shown.width) // 2, (view_height - shown.height) // 2
            canvas.configure(scrollregion=(0, 0, view_width, view_height))
        else:
            shown, scale, left, top = image, 1.0, 0, 0
            canvas.configure(scrollregion=(0, 0, image.width, image.height))
        self.photos[key] = ImageTk.PhotoImage(shown)
        canvas.create_image(left, top, image=self.photos[key], anchor="nw", tags="chart")
        self.placement[key] = (scale, left, top)

    # -- zoom and pan -------------------------------------------------------

    def _image_point(self, key: str, event: tk.Event) -> tuple[float, float] | None:
        """Return the event position in chart-image pixels, or None if no chart is shown."""
        if key not in self.placement or self.geometry.get(key) is None:
            return None
        canvas = self.canvases[key]
        scale, left, top = self.placement[key]
        return (canvas.canvasx(event.x) - left) / scale, (canvas.canvasy(event.y) - top) / scale

    def _drag_start(self, key: str, event: tk.Event, mode: str) -> None:
        point = self._image_point(key, event)
        if point is None:
            return
        canvas = self.canvases[key]
        x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
        self._drag = {"key": key, "mode": mode, "image": point, "canvas": (x, y), "last": (x, y), "band": None}
        if mode == "zoom":
            self._drag["band"] = canvas.create_rectangle(x, y, x, y, outline="#1f5fbf", dash=(4, 2), width=2)
        else:
            canvas.configure(cursor="fleur")

    def _drag_motion(self, key: str, event: tk.Event) -> None:
        drag = self._drag
        if drag is None or drag["key"] != key:
            return
        canvas = self.canvases[key]
        x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
        if drag["mode"] == "zoom":
            x0, y0 = drag["canvas"]
            canvas.coords(drag["band"], x0, y0, x, y)
        else:
            # Move the picture with the pointer for immediate feedback; the real
            # redraw happens on release.
            last_x, last_y = drag["last"]
            canvas.move("chart", x - last_x, y - last_y)
            drag["last"] = (x, y)

    def _drag_end(self, key: str, event: tk.Event) -> None:
        drag, self._drag = self._drag, None
        if drag is None or drag["key"] != key:
            return
        canvas = self.canvases[key]
        canvas.configure(cursor="crosshair")
        if drag["band"] is not None:
            canvas.delete(drag["band"])
        end = self._image_point(key, event)
        if end is None:
            return
        (x0, y0), (x1, y1) = drag["image"], end
        if drag["mode"] == "zoom":
            self._zoom_to_box(key, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        else:
            self._pan(key, x1 - x0, y1 - y0)

    def _zoom_to_box(self, key: str, x0: float, y0: float, x1: float, y1: float) -> None:
        geometry = self.geometry.get(key)
        if geometry is None:
            return
        updates = zoom_updates(geometry, self._shown_for(key), x0, y0, x1, y1)
        if updates:
            self._apply_view(updates, "Zoomed", key)

    def _pan(self, key: str, dx: float, dy: float) -> None:
        """Shift the view so the point under the pointer moves by (dx, dy) image pixels."""
        geometry = self.geometry.get(key)
        if geometry is None:
            return
        updates = pan_updates(geometry, self._shown_for(key), dx, dy)
        if updates:
            self._apply_view(updates, "Panned", key)
        else:
            self._refresh_view(key)  # put the picture back where it was

    def _wheel_turned(self, key: str, event: tk.Event) -> None:
        """Collect wheel notches; zoom the dates about the pointer once the wheel stops."""
        point = self._image_point(key, event)
        if point is None:
            return
        if self._wheel is None or self._wheel["key"] != key:
            self._wheel = {"key": key, "notches": 0.0, "x": point[0], "after": None}
        wheel = self._wheel
        wheel["notches"] += event.delta / 120.0  # Windows: one notch = 120, positive = away = zoom in
        wheel["x"] = point[0]
        if wheel["after"] is not None:
            self.root.after_cancel(wheel["after"])
        wheel["after"] = self.root.after(_WHEEL_DELAY_MS, self._apply_wheel)
        self.status.set(f"Zoom ×{_WHEEL_ZOOM_FACTOR ** -wheel['notches']:.2f} (applies when the wheel stops) …")

    def _apply_wheel(self) -> None:
        wheel, self._wheel = self._wheel, None
        if wheel is None or self.geometry.get(wheel["key"]) is None:
            return
        geometry = self.geometry[wheel["key"]]
        factor = _WHEEL_ZOOM_FACTOR ** wheel["notches"]
        self._apply_view(scale_dates_updates(geometry, factor, wheel["x"]), "Zoomed")

    def _shown_for(self, key: str) -> PlotConfig | None:
        """Return the config the chart in tab ``key`` was drawn with (its nation's own values applied)."""
        return self.shown_config.for_nation(key) if self.shown_config is not None else None

    def _apply_view(self, updates: dict[str, str], verb: str, key: str | None = None) -> None:
        """Write zoom/pan results into the fields (undoably) and redraw.

        The axis limits go into the fields of the chart's own nation (tab
        ``key``); the dates are the same for every chart.
        """
        nation = next((nation for nation in NATIONS if nation.key == key), None)
        own = {option.name for option in NATION_OPTIONS}
        updates = {
            nation_choice(nation, by_name(name)) if nation and name in own else name: text for name, text in updates.items()
        }
        self._remember_step()
        self._loading = True
        try:
            for name, text in updates.items():
                self.payload_vars[name].set(text)
        finally:
            self._loading = False
        prefix = f"{nation.name}: " if nation and any(":" in name for name in updates) else ""
        changed = prefix + ", ".join(f"{option_of(name).label} {text or '(today)'}" for name, text in updates.items())
        self._append_log(f"--- {verb.lower()}: {changed}\n")
        self.request_redraw()

    def _remember_step(self, preview: bool = False) -> None:
        """Keep the controls' choices for Back and Unzoom, before a zoom, pan, Unzoom or Reset changes them.

        ``preview``: keep the preview's settings too (a Reset changes them).
        At most ``_HISTORY_LIMIT`` steps; the oldest after the first go, so
        Unzoom still returns to the view before the first zoom.
        """
        self.history.append((self._snapshot(), self._preview_settings() if preview else None))
        if len(self.history) > _HISTORY_LIMIT:
            del self.history[1 : len(self.history) - _HISTORY_LIMIT + 1]

    def _preview_settings(self) -> tuple[str, dict[str, bool]]:
        """The preview's mode ("fit" or "actual") and each size's aspect-ratio lock."""
        return self.zoom.get(), {name: editor.keep_ratio.get() for name, editor in self.size_editors.items()}

    def _set_preview(self, zoom: str, keep_ratio: dict[str, bool]) -> None:
        """Set the preview's mode and the aspect-ratio locks (Reset, and Back after it)."""
        if self.zoom.get() != zoom:
            self.zoom.set(zoom)
            self._refresh_all_views()
        for name, keep in keep_ratio.items():
            editor = self.size_editors[name]
            editor.keep_ratio.set(keep)
            editor.lock_changed()

    def _unzoomed(self) -> bool:
        """True when there is no view before the first zoom to return to, or it is the one shown."""
        return not self.history or self.history[0][0] == self._snapshot()

    def _update_view_buttons(self) -> None:
        """Grey Back and Unzoom while they would do nothing (Terry, 2026-10-08), as the web page does."""
        self.back_button.state(["!disabled"] if self.history else ["disabled"])
        self.unzoom_button.state(["disabled"] if self._unzoomed() else ["!disabled"])

    def _back(self) -> None:
        if not self.history:
            self.status.set("Nothing to go back to.")
            return
        choices, preview = self.history.pop()
        self._load_choices(choices)
        if preview is not None:
            self._set_preview(*preview)
        self.request_redraw()

    def _unzoom(self) -> None:
        """Return to the view before the first zoom: one more step, so Back returns to the zoom."""
        if self._unzoomed():
            self.status.set("Not zoomed.")
            return
        first = self.history[0][0]
        self._remember_step()
        self._load_choices(first)
        self.request_redraw()

    # -- actions ------------------------------------------------------------

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")
        last_line = next((line.strip() for line in reversed(text.splitlines()) if line.strip()), "")
        if last_line and self.rendering:
            self.status.set(last_line)

    def _current_tab_key(self) -> str | None:
        selected = self.notebook.select()
        for key, tab in self.tabs.items():
            if str(tab) == selected:
                return key
        return None

    def _save_png(self) -> None:
        key = self._current_tab_key()
        if key is None or key not in self.pngs:
            self.status.set("Nothing drawn in this tab yet.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save chart as PNG",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            initialfile=saved_png_name(key, self.drawn_config),
        )
        if not path:
            return
        with open(path, "wb") as output:
            output.write(self.pngs[key])
        self.status.set(f"Saved {path}")

    def _save_log(self) -> None:
        """Save the whole message log, as shown, to a text file (Terry, 2026-10-13, batch 15.3).

        Named by the minute of saving (``frontend.saved_log_name``); written
        as UTF-8, with Windows line endings on Windows (text mode).
        """
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save message log",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile=saved_log_name(pd.Timestamp.now()),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as output:
                output.write(self.log.get("1.0", "end-1c"))
        except OSError as exc:
            self.status.set(f"Message log not saved: {exc}")
            return
        self.status.set(f"Saved the message log to {path}")

    def _refresh(self) -> None:
        """Draw again with the latest data: the quotes of the moment, and anything downloaded over an hour ago.

        The intraday quotes are fetched for every drawing anyway; the rest
        of the session's downloads are kept, and those older than
        ``DOWNLOAD_MAX_AGE_SECONDS`` are dropped here so the drawing fetches
        them again, as the web page does for every drawing.
        """
        dropped = http.forget_downloads_older_than(DOWNLOAD_MAX_AGE_SECONDS)
        self._append_log(f"--- refresh: the latest quotes, and {dropped} download(s) over an hour old fetched again\n")
        self.request_redraw(force=True)

    def _reset(self) -> None:
        """Back to the default charts for the nations ticked, and the preview's defaults: "Fit to window", aspect ratio preserved.

        Terry, 2026-10-12: Reset left the preview's two settings as they were.
        Terry, 2026-10-20 (batch 17.5): Reset leaves the nation boxes alone
        (``frontend.reset_choices``). Back undoes all of it.
        """
        self._remember_step(preview=True)
        self._load_choices(reset_choices(self._snapshot()[1]))
        self._set_preview(_DEFAULT_PREVIEW, {name: True for name in self.size_editors})
        self.request_redraw()

    def _copy_command(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.command.get())
        self.status.set("Command line copied.")

    def _window_configured(self, event: tk.Event) -> None:
        """Keep the window's size and place while it is neither maximized nor minimized, and whether it is maximized.

        Windows reports a maximized window's own geometry as the monitor's
        size, its corner just off the screen; remembered as that, it came
        back as a huge plain window. So the size before maximizing is kept,
        and the window is maximized again at the next start.
        """
        if event.widget is not self.root:
            return  # the toplevel's binding also sees every child's events
        state = self.root.state()
        if state == "normal":
            self._normal_geometry = self.root.geometry()
            self._maximized = False
        elif state == "zoomed":
            self._maximized = True

    def _remember(self) -> None:
        """Save the last drawn choices and the window layout for the next session."""
        if self.drawn_choices is None:
            return
        payloads, flags = self.drawn_choices
        geometry = self._normal_geometry or self.root.geometry()
        error = save_state(
            {
                "version": STATE_VERSION,
                "payloads": payloads,
                "flags": flags,
                "zoom": self.zoom.get(),
                "tab": self._current_tab_key(),
                # The size and place before maximizing, and whether it is maximized.
                "geometry": geometry,
                "maximized": self._maximized,
                # The work area of the monitor it is on, so that if that monitor
                # is gone at the next start, the window keeps its place relative
                # to another's corner (batch 15.4). None off Windows.
                "monitor": _window_monitor(geometry),
                "column_width": self._current_column_width(),
                "keep_ratio": {name: editor.keep_ratio.get() for name, editor in self.size_editors.items()},
            }
        )
        if error is not None:
            self._append_log(error + "\n")

    def _close(self) -> None:
        self._remember()
        # Every callback still waiting, or it fires after the window is gone
        # ("invalid command name ..."): the poll, and a view refresh after a
        # resize, a redraw after typing, or a zoom after the wheel stops.
        pending = [self._poll_id, self._text_after_id, *self._resize_after_ids.values()]
        if self._wheel is not None:
            pending.append(self._wheel["after"])
        for after_id in pending:
            if after_id is not None:
                self.root.after_cancel(after_id)
        self.root.destroy()


def _monitor_work_areas() -> list[tuple[int, int, int, int]]:
    """Return each monitor's work area (left, top, right, bottom, without the taskbar) in the window's coordinates.

    Windows only (``EnumDisplayMonitors``), and in the same pixels as Tk's
    geometry, the process being DPI-aware (``_enable_windows_dpi_awareness``).
    Empty elsewhere, or if the call fails.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    areas: list[tuple[int, int, int, int]] = []
    user32 = ctypes.windll.user32

    def found(monitor, _dc, _rect, _data) -> int:
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            areas.append((work.left, work.top, work.right, work.bottom))
        return 1  # go on to the next monitor

    callback = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    try:
        user32.EnumDisplayMonitors(None, None, callback(found), 0)
    except (AttributeError, OSError):
        return []
    return areas


Rect = tuple[int, int, int, int]  # left, top, right, bottom


def _window_frame() -> Rect:
    """Return how far a window's frame reaches beyond its inside: (left, top, right, bottom), in Tk's pixels.

    Tk's geometry ``WxH+X+Y`` gives the inside's size and the frame's
    outer corner (measured on Buddug at 125 %: the frame 9 px a side, its
    title bar 38, of which 8 a side are Windows' invisible resizing
    borders). Windows says how wide the frame is for the process's DPI
    (``AdjustWindowRectEx``, the window's standard style), so it is known
    before the window is shown. Nothing off Windows.
    """
    if sys.platform != "win32":
        return (0, 0, 0, 0)
    import ctypes
    from ctypes import wintypes

    ws_overlappedwindow = 0x00CF0000
    rect = wintypes.RECT(0, 0, 0, 0)
    try:
        if not ctypes.windll.user32.AdjustWindowRectEx(ctypes.byref(rect), ws_overlappedwindow, False, 0):
            return (0, 0, 0, 0)
    except (AttributeError, OSError):
        return (0, 0, 0, 0)
    return (-rect.left, -rect.top, rect.right, rect.bottom)


def _outer_rect(width: int, height: int, x: int, y: int, frame: Rect) -> Rect:
    """The window's whole rectangle, its frame included, from Tk's geometry (``_window_frame``)."""
    return (x, y, x + width + frame[0] + frame[2], y + height + frame[1] + frame[3])


def _gap(a: Rect, b: Rect) -> float:
    """How far apart two rectangles are (0 when they touch or overlap)."""
    across = max(a[0] - b[2], b[0] - a[2], 0)
    down = max(a[1] - b[3], b[1] - a[3], 0)
    return (across * across + down * down) ** 0.5


def _middle(rect: Rect) -> Rect:
    """A rectangle's middle, as a rectangle of no size."""
    across, down = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    return (across, down, across, down)


def _overlap(a: Rect, b: Rect) -> int:
    """The area two rectangles share."""
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _monitor_of(rect: Rect, areas: list[Rect]) -> Rect:
    """The work area holding most of ``rect``, else the nearest one (as Windows' ``MonitorFromRect`` chooses)."""
    return max(areas, key=lambda area: (_overlap(rect, area), -_gap(rect, area)))


def _moved_onto_a_monitor(width: int, height: int, x: int, y: int, areas: list[Rect], own: Rect | None, frame: Rect) -> str:
    """Return a geometry for a window no monitor shows the title bar of, its size kept where it can be.

    Terry, 2026-10-13 (batch 15.4): a window remembered on a monitor no
    longer there came back at the default size and place; it should keep
    its size and place on another monitor, shifted or shrunk only where
    needed so that all of it shows. With its own monitor remembered
    (``own``, a work area), it goes to the remaining one nearest to that,
    at the same place relative to that one's top left corner; without it
    (settings saved before batch 15), to the one nearest the window. Then
    it is moved, and only then shrunk, as little as puts the whole window,
    frame and all, on that monitor's work area (the screen less the
    taskbar). Run on Buddug's three upper monitors unplugged, Terry's
    3456x1944 window across two of them comes back 3456x1944 on the main
    screen, 167 px from its left as it was from its own monitor's.
    """
    outer = _outer_rect(width, height, x, y, frame)
    if own is not None:
        # The nearest; of those touching it, the one whose middle is nearest its middle.
        target = min(areas, key=lambda area: (_gap(area, own), _gap(_middle(area), _middle(own))))
        x, y = target[0] + x - own[0], target[1] + y - own[1]
    else:
        target = _monitor_of(outer, areas)
    left, top, right, bottom = target
    outer_width = min(outer[2] - outer[0], right - left)
    outer_height = min(outer[3] - outer[1], bottom - top)
    x = min(max(x, left), right - outer_width)
    y = min(max(y, top), bottom - outer_height)
    return f"{outer_width - frame[0] - frame[2]}x{outer_height - frame[1] - frame[3]}+{x}+{y}"


def _window_monitor(geometry: str) -> list[int] | None:
    """The work area of the monitor holding most of a window with this geometry, for the remembered settings."""
    match = _GEOMETRY_PATTERN.match(geometry)
    areas = _monitor_work_areas()
    if not match or not areas:
        return None
    return list(_monitor_of(_outer_rect(*map(int, match.groups()), _window_frame()), areas))


def _remembered_monitor(state: dict) -> Rect | None:
    """The work area of the monitor the window was on when its settings were saved, if they say (since batch 15)."""
    monitor = state.get("monitor")
    if isinstance(monitor, list) and len(monitor) == 4 and all(isinstance(value, int) for value in monitor):
        return tuple(monitor)
    return None


def _title_bar_on_screen(width: int, x: int, y: int, areas: list[tuple[int, int, int, int]]) -> bool:
    """True when enough of a window's title bar (``_MIN_TITLE_ON_SCREEN_PX`` of it, half its height) is on one monitor."""
    for left, top, right, bottom in areas:
        across = min(x + width, right) - max(x, left)
        down = min(y + _TITLE_BAR_PX, bottom) - max(y, top)
        if across >= min(_MIN_TITLE_ON_SCREEN_PX, width) and down >= _TITLE_BAR_PX // 2:
            return True
    return False


def _initial_geometry(root: tk.Tk, state: dict) -> str:
    """Return the remembered window geometry if the window can still be reached, else 90 % of the main screen.

    Terry, 2026-10-12: a window made larger than the default, moved to another
    monitor or stretched across several came back at the default size on the
    main screen. The check was against the main screen alone; his remembered
    window, 3456x1944 at (1115, -2149), sat across two of the three monitors
    above it. Now any size and place is kept while enough of the title bar
    is on some monitor to drag the window by (``_title_bar_on_screen``),
    even with part of the window off the screens. Otherwise (its monitor
    since unplugged) it keeps its size on another monitor, moved and
    shrunk as little as shows all of it (``_moved_onto_a_monitor``, batch
    15.4); it was given the default size. Without the monitors' list (not
    Windows), the main screen's old test.
    """
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    match = _GEOMETRY_PATTERN.match(str(state.get("geometry", "")))
    if match:
        width, height, x, y = map(int, match.groups())
        areas = _monitor_work_areas()
        if areas:
            if _title_bar_on_screen(width, x, y, areas):
                return f"{width}x{height}+{x}+{y}"
            return _moved_onto_a_monitor(width, height, x, y, areas, _remembered_monitor(state), _window_frame())
        elif width <= screen_width and height <= screen_height and 0 <= x < screen_width - 100 and 0 <= y < screen_height - 100:
            return f"{width}x{height}+{x}+{y}"
    return f"{round(screen_width * _SCREEN_FRACTION)}x{round(screen_height * _SCREEN_FRACTION)}+20+20"


def run_gui(
    config: PlotConfig, cli_payloads: dict[str, str] | None = None, cli_flags: dict[str, bool] | None = None
) -> None:
    """Open the window and run until it is closed.

    ``config`` is what the command line described; ``cli_payloads`` and
    ``cli_flags`` are the options it named, which override the remembered
    settings (see ``starting_choices``).
    """
    _enable_windows_dpi_awareness()
    http.enable_download_cache()
    http.enable_last_good_copies()  # batch 20: drawn from when a source fails
    state, note, remembered_in = load_state()
    choices, notes = starting_choices(config, cli_payloads or {}, cli_flags or {}, state, remembered_in)
    if note:
        notes.insert(0, note)
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    geometry = _initial_geometry(root, state)
    root.geometry(geometry)
    if state.get("maximized") is True:
        # Maximized on the monitor its remembered size and place are on.
        root.state("zoomed")
    RatesPlotApp(root, choices, notes, state, normal_geometry=geometry)
    root.mainloop()
