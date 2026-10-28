"""What the window and the web page share, without a GUI toolkit.

The desktop window (``gui``, tkinter) and the web page (``web``, Streamlit)
are two front ends over the same option table and the same drawing
(``plotting.build_figure``). This module holds the parts of a front end that
need neither toolkit, so that the web page never imports tkinter (a server
may not have it) and the two cannot drift apart:

* ``Choices``: what a user chose, as ``(payloads, flags)`` keyed by option
  name (see ``options``);
* the starting choices: defaults, remembered settings and the command line
  combined (``starting_choices``), and the window's remembered settings file;
  the words of the "Remember my settings" box (``REMEMBER_LABEL``, batch 24.6);
  the tips of the buttons both have (``REFRESH_HELP`` and the rest, batch 31.6);
* each nation's own controls (``NATION_OPTIONS``, under its tab in the window
  and in its own sidebar section on the page), keyed "NATION:OPTION";
* each option's help as the controls show it (``option_help_lines``);
* the drawn chart as PNG bytes (``png_bytes``) and the file name it is saved
  under (``saved_png_name``), and the message log's (``saved_log_name``);
  the tab titles;
* zoom and pan: where the axes sit in a chart image (``ChartGeometry``) and
  the field texts a zoom to a box, a pan or a change of the dates' scale
  gives (``zoom_updates``, ``pan_updates``, ``scale_dates_updates``). The
  window's mouse and the web page's drag use the same rules; the page's
  buttons move the dates by ``move_dates_updates``;
* what a blank field shows in grey: the value in effect (``field_hints``);
  a typed number's 0 before its point (``with_leading_zero``);
* the nation boxes: what Reset leaves of them (``reset_choices``), and which
  tab is made current after a drawing (``current_tab``);
* each nation's axis limits: the unit symbol right of each box
  (``limit_unit``), and the "All" tick that copies a limit to every nation
  (``all_tick_offered``, ``limit_copies``, ``settled_all_ticks``; batch 18).
"""

from __future__ import annotations

import contextlib
import ctypes
import io
import json
import math
import os
import re
import sys
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

from . import __version__
from .config import (
    COMPONENT_LETTERS,
    COMPONENT_SYNONYMS,
    DEFAULT_AUTO_REFRESH_MINUTES,
    DEFAULT_REGRESSION_TOLERANCE_PCT,
    EARLIEST_DATE,
    MIN_CANVAS_PX,
    MIN_WINDOW_DAYS,
    NATIONS,
    Nation,
    PlotConfig,
)
from .options import (
    AUTO_REFRESH_OPTIONS,
    GROUPS,
    GROUPS_CHOSEN_TOGETHER,
    OPTIONS,
    Kind,
    NONE_ITEM,
    Option,
    auto_refresh_idle,
    by_name,
    choices_from_config,
    config_from_choices,
    format_dollar_bound,
    group_title,
    field_default,
    idle_aggregate_reasons,
    idle_margin_reasons,
    idle_option_reasons,
    is_percent_bound,
    latest_idle_reasons,
    margin_options,
    list_switch,
    nation_choice,
    nation_view,
    options_in,
    options_of,
    per_nation,
    switch_of,
    unticked,
)

# The start date written out before it became automatic (Terry, 2026-09-29):
# a remembered Start with this text was the old default, not a choice, and is
# read as blank, the automatic start.
_FORMER_DEFAULT_START = "1966-01-01"
# Same PNG metadata as tools/verify_charts.py, so saved files hash identically.
PNG_METADATA = {"Software": None}
TAB_TITLES = {nation.key: nation.name for nation in NATIONS}
# The format of the window's remembered-settings file; a file of another version is ignored.
STATE_VERSION = 1

Choices = tuple[dict[str, str], dict[str, bool]]
# The options each nation has its own control for (batch 2, Terry 2026-10-06:
# the tick boxes of a nation's terms, and its axis limits, under its tab). The
# window and the page show none of them for both charts at once.
NATION_OPTIONS = tuple(option for option in OPTIONS if per_nation(option) and option.in_gui)
# The order of a nation's lists under its tab, by field: the spreads next to
# the yield terms, as in the column (Terry, 2026-10-06); the policy terms
# (batch 9.1) before the mortgages, as the column has the policy rate before
# them; the aggregate debts (batch 10.4), then the levels of government that
# replace them (batch 10.5: "By level", one control for --debt: and
# --interest:, which take the same letters), beside the axis limits.
_PANEL_LISTS = ("yield_terms", "spread_pairs", "policy_terms", "mortgage_terms", "debt_aggregates", "components")
# The control column's blocks, top to bottom: key (an option's ``panel``, or
# its help group), title (None: no title) and the options to put first, in
# that order (the rest follow in table order). Terry, 2026-10-08 (batch 7):
# the measure just under "By level" (under the curves since By level went
# to each nation's panel, batch 10.5), the regression segments just under the
# measure, the yields, spreads, policy rate and mortgages ticked in one
# block, "Line labels" and "Latest data" one block without a title. --help
# keeps its sections (``options.GROUPS``), which say what each option is.
CONTROL_BLOCKS: tuple[tuple[str, str | None, tuple[str, ...]], ...] = (
    ("country", group_title("country"), ()),
    ("curves", group_title("curves"), ()),
    ("units", group_title("units"), ()),
    ("regression", None, ()),
    ("rates", group_title("rates"), ("yield", "spreads", "policy", "mortgages")),
    ("labels", None, ()),
    ("dates", group_title("dates"), ()),
    ("canvas", group_title("canvas"), ()),
)
# Each nation's axis limits as laid out under its tab: a column per axis,
# Max above Min, Top above Bottom (Terry, 2026-10-12).
LIMIT_COLUMNS = (("max", "min"), ("top", "bottom"))
# The limits in that order (Max, Min, Top, Bottom), and the yield axis's.
LIMITS = tuple(name for column in LIMIT_COLUMNS for name in column)
_YIELD_LIMITS = LIMIT_COLUMNS[0]


def control_blocks() -> list[tuple[str, str | None, list[Option]]]:
    """Return the control column's blocks in order: each key, title and options (a nation's own left out).

    An option is in the block of its ``panel``, or of its help group. A
    group with no block of its own (an option added later) gets one after
    the others, titled as in --help, so a new option still gets a control
    with no change here.
    """
    shown = [option for option in OPTIONS if option.in_gui and option not in NATION_OPTIONS]
    blocks: list[tuple[str, str | None, list[Option]]] = []
    keys = [key for key, _title, _first in CONTROL_BLOCKS]
    for key, title, first in CONTROL_BLOCKS:
        members = [option for option in shown if (option.panel or option.group) == key]
        members.sort(key=lambda option: first.index(option.name) if option.name in first else len(first))
        if members:
            blocks.append((key, title, members))
    for group in GROUPS:
        members = [option for option in shown if (option.panel or option.group) == group and group not in keys]
        if members:
            blocks.append((group, group_title(group), members))
    return blocks


# ---------------------------------------------------------------------------
# Remembered settings (the window's; the web page keeps a chart's choices in
# its address instead) and the starting choices
# ---------------------------------------------------------------------------


# Several windows at once (Terry, 2026-10-12): each command window has its
# own settings file, so two windows started from two command windows no
# longer overwrite each other's settings. The file is named by the command
# window itself (its console's window handle, the same for its whole life;
# in Windows Terminal, for each tab), not by a process number: ``python``
# here is the install manager's launcher, which starts the real Python as a
# new process on every run (measured 2026-10-13: Python's parent is the
# launcher, whose parent is cmd.exe). A first run in a command window starts
# from whichever settings file was written last; a window started without
# one (a shortcut, pythonw) uses the shared file, as every window did
# before. Files of command windows not written for STATE_FILE_MAX_AGE_DAYS
# (long closed) are removed when a window starts.
_STATE_STEM = "gui_state"
STATE_FILE_MAX_AGE_DAYS = 30
# Windows refuses to replace a file another window is reading at that
# moment: the save is tried once more after this pause.
_REPLACE_RETRY_SECONDS = 0.25


def _state_dir() -> Path:
    """``%APPDATA%\\ratesplot`` on Windows (``~/.config/ratesplot`` elsewhere)."""
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / "ratesplot"


def console_window() -> int:
    """Return the handle of the command window this process runs in; 0 if none (or not on Windows)."""
    if sys.platform != "win32":
        return 0
    try:
        return int(ctypes.windll.kernel32.GetConsoleWindow() or 0)
    except (AttributeError, OSError):
        return 0


def state_path() -> Path:
    """Return where this window's settings are remembered: its command window's own file, else the shared one."""
    console = console_window()
    return _state_dir() / (f"{_STATE_STEM}_{console:x}.json" if console else f"{_STATE_STEM}.json")


def _state_files() -> list[Path]:
    """Every remembered-settings file, the shared one and each command window's."""
    return [path for path in _state_dir().glob(f"{_STATE_STEM}*.json") if path.is_file()]


def _remove_old_state_files(keep: Path) -> None:
    """Remove the files of command windows not written for ``STATE_FILE_MAX_AGE_DAYS``, and their stray temporary files.

    Never the shared file, nor ``keep`` (this window's own).
    """
    cutoff = time.time() - STATE_FILE_MAX_AGE_DAYS * 86400
    stale = [path for path in _state_files() if path.name != f"{_STATE_STEM}.json"]
    stale += list(_state_dir().glob(f"{_STATE_STEM}*.tmp"))
    for path in stale:
        try:
            if path != keep and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass  # another window's, in use or already gone: tried again at the next start


def load_state() -> tuple[dict, str | None, Path | None]:
    """Return the remembered state (empty if none), a note to log if it could not be read, and the file read.

    This window's own file (``state_path``) if it has one; otherwise the
    file written last (a first run in a new command window).
    """
    own = state_path()
    if own.parent.is_dir():
        _remove_old_state_files(keep=own)
    files = _state_files() if own.parent.is_dir() else []
    path = own if own in files else max(files, key=lambda file: file.stat().st_mtime, default=None)
    if path is None:
        return {}, None, None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"Remembered settings in {path} could not be read ({exc}); starting from defaults.", None
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return {}, f"Remembered settings in {path} are from another version; starting from defaults.", None
    return state, None, path


def save_state(state: dict) -> str | None:
    """Write ``state`` to this window's file atomically; return an error message or None.

    Through a temporary file of this process's own (two windows saving at
    the same moment once shared one, ``gui_state.tmp``), then a replace,
    tried once more after a moment if Windows refuses it (another window
    reading the file).
    """
    path = state_path()
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        try:
            os.replace(temporary, path)
        except PermissionError:
            time.sleep(_REPLACE_RETRY_SECONDS)
            os.replace(temporary, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temporary.unlink()
        return f"Settings could not be remembered ({exc})."
    return None


def nation_text(nation: Nation, option: Option, text: str) -> str:
    """Return a value for both charts as ``nation``'s own field shows it: its own terms and pairs only.

    Blank stays blank (the default); a list the nation has none of is
    "none", which its chart draws (Terry, 2026-10-07); a text that does not
    parse is kept as it is, for the field to report.
    """
    if not text.strip() or option.fields[0] not in _PANEL_LISTS:
        return text
    try:
        value = nation_view(nation, option, option.parse(text))
    except ValueError:
        return text
    return option.format((value,), PlotConfig())


def spread_to_nations(payloads: dict[str, str]) -> dict[str, str]:
    """Return ``payloads`` with each value for both charts moved into every nation's own field.

    Settings remembered before there were nations ("max": "8", "yields":
    "3m,2y,7y") become "cdn:max" and "us:max", and so on (``nation_text``);
    a nation's own field already there is kept.
    """
    moved = {name: text for name, text in payloads.items() if name not in {option.name for option in NATION_OPTIONS}}
    for option in NATION_OPTIONS:
        for nation in NATIONS:
            key = nation_choice(nation, option)
            if key in payloads:
                moved[key] = payloads[key]
            elif option.name in payloads:
                moved[key] = nation_text(nation, option, payloads[option.name])
    return moved


def starting_choices(
    config: PlotConfig,
    cli_payloads: dict[str, str],
    cli_flags: dict[str, bool],
    state: dict,
    remembered_in: Path | None = None,
) -> tuple[Choices, list[str]]:
    """Combine defaults, remembered choices and the command line; return the choices and notes to log.

    ``config`` is what the command line alone describes; ``cli_payloads`` and
    ``cli_flags`` are the options it named; ``remembered_in`` is the file
    ``state`` was read from (``load_state``). If the combination is not valid
    (e.g. a remembered start date after a new command-line end date), the
    remembered choices are dropped and the reason logged.
    """
    notes: list[str] = []
    cli_config_payloads, cli_config_flags = choices_from_config(config)
    if state.get("payloads", {}).get("start") == _FORMER_DEFAULT_START:
        state = {**state, "payloads": {**state["payloads"], "start": ""}}
        notes.append(f"The remembered Start {_FORMER_DEFAULT_START} was the former default: now blank, the automatic start.")

    def combine(use_state: bool) -> Choices:
        payloads, flags = choices_from_config(PlotConfig())
        flags.update(dict.fromkeys(ALL_TICKS, False))  # the "All" ticks (batch 18.2), remembered with the flags
        if use_state:
            remembered = {name: text for name, text in state.get("payloads", {}).items() if isinstance(text, str)}
            for name, text in spread_to_nations(remembered).items():
                if name in payloads:
                    payloads[name] = text
            for name, value in state.get("flags", {}).items():
                if name in flags and isinstance(value, bool):
                    flags[name] = value
        for name, text in cli_payloads.items():
            if name in payloads:
                payloads[name] = text
        # The levels (--debt:LETTERS, --interest:LETTERS, for every chart or
        # for one nation) name their curves, as --debt would; each nation's
        # one control (the debt one) is set below with the other nations' own.
        levels_given = any(
            name in cli_payloads or nation_choice(nation, by_name(name)) in cli_payloads
            for name in ("debt-parts", "interest-parts")
            for nation in NATIONS
        )
        # A list taken out of a field (--no-yields:30y) has no control of its
        # own: the field's control shows what the command line left.
        for option in options_of(Kind.VALUE):
            if option.removes and option.name in cli_payloads:
                for shown in options_of(Kind.VALUE):
                    if shown.in_gui and shown.fields == option.fields and shown.name in cli_config_payloads:
                        payloads[shown.name] = cli_config_payloads[shown.name]
        # Each nation's own fields: what the command line gave for both charts
        # (--max:8, --no-y:30), or for that nation (--us:max:8), as the
        # resolved config has it for that nation.
        for option in NATION_OPTIONS:
            given = [other for other in options_of(Kind.VALUE) if other.fields == option.fields]
            if option.fields == ("mortgage_terms",):
                given += margin_options().values()  # a margin names its term too (batch 9.4)
            for nation in NATIONS:
                key = nation_choice(nation, option)
                if any(other.name in cli_payloads or nation_choice(nation, other) in cli_payloads for other in given):
                    payloads[key] = cli_config_payloads[key]
        # Curves, and countries, are overridden as a group: on the command line
        # "--gdp" means "GDP only", which the resolved config already reflects.
        # The measure as given: -r without debt or interest has no effect
        # (``options.idle_options``), and stays ticked, greyed, as in the window.
        for group_name in GROUPS_CHOSEN_TOGETHER:
            group = [option.name for option in options_in(group_name) if option.name in flags]
            if any(name in cli_flags for name in group) or (group_name == "curves" and levels_given):
                for name in group:
                    flags[name] = bool(cli_flags.get(name, False)) if group_name == "units" else cli_config_flags[name]
        for option in OPTIONS:
            if option.group in GROUPS_CHOSEN_TOGETHER or option.kind is Kind.VALUE:
                continue
            if option.name in flags and option.name in cli_flags:
                flags[option.name] = cli_flags[option.name]
        # A value given on the command line that turns its flag on (--reg:TOL)
        # does so over the remembered flag too.
        for option in options_of(Kind.VALUE):
            named = [option.name] + [nation_choice(nation, option) for nation in NATIONS]
            if option.turns_on in flags and any(name in cli_payloads for name in named):
                flags[option.turns_on] = cli_config_flags[option.turns_on]
        # Remembered Top/Bottom are in the remembered measure's units (dollars,
        # percent, dollars per person). If the command line chose a different
        # measure they no longer apply, unless it gave them too; the other
        # remembered settings are kept.
        if use_state:
            remembered = state.get("flags", {})
            measure = [option.name for option in options_in("units") if option.name in flags]
            if any(flags[name] != bool(remembered.get(name, False)) for name in measure):
                for bound in bound_keys():
                    if bound in payloads and bound not in cli_payloads and bound.split(":")[-1] not in cli_payloads:
                        payloads[bound] = ""
        # A limit given for every chart (--max:8) is what a ticked "All"
        # writes (batch 18.2), so it ticks its "All" where every nation's box
        # shows it; one given for a nation (--us:max:9) unticks a remembered
        # one, whose boxes it changed. Then the rules (``settled_all_ticks``).
        for name in LIMITS:
            keys = [nation_choice(nation, by_name(name)) for nation in NATIONS]
            if name in cli_payloads:
                flags[all_tick(name)] = len({payloads[key] for key in keys}) == 1
            elif any(key in cli_payloads for key in keys):
                flags[all_tick(name)] = False
        flags.update(settled_all_ticks(payloads, flags))
        return payloads, flags

    choices = combine(use_state=bool(state))
    if state:
        try:
            config_from_choices({k: v for k, v in choices[0].items() if v.strip()}, choices[1])
            notes.append(f"Restored the settings remembered in {remembered_in or state_path()}.")
        except ValueError as exc:
            notes.append(f"Remembered settings not used ({exc}); starting from the command line and defaults.")
            choices = combine(use_state=False)
    return choices, notes


# ---------------------------------------------------------------------------
# The nation boxes: Reset, and the tab made current
# ---------------------------------------------------------------------------


def nation_boxes() -> dict[str, str]:
    """Return each nation's box in the window and on the page: its option's name -> the nation's key ("germany": "de")."""
    return {switch_of(nation): nation.key for nation in NATIONS}


def reset_choices(flags: Mapping[str, bool]) -> Choices:
    """Return the choices Reset gives: every default, but the nation boxes as they are (batch 17.5).

    Terry, 2026-10-20: "Pressing “Reset” should not tick or untick any nation
    tick-boxes." Each nation's own controls are reset with the rest.
    """
    payloads, defaults = choices_from_config(PlotConfig())
    kept = {name: bool(flags[name]) for name in nation_boxes() if name in flags}
    # Every limit blank, so no "All" ticked (batch 18.2).
    return payloads, {**defaults, **dict.fromkeys(ALL_TICKS, False), **kept}


def reset_changes_nothing(choices: Choices) -> bool:
    """True when Reset would leave every one of these choices as it is (``reset_choices``): the window and the page grey it then (batch 28.1).

    Text by text, the controls ``choices`` holds: ``reset_choices`` names
    every nation's every field, and a front end has only those each nation
    has (the window no aggregate debts but the UK's). A greyed field's
    text counts, since Reset clears it too. The preview's settings, which
    Reset also sets, are each front end's to add.
    """
    payloads, flags = choices
    reset_payloads, reset_flags = reset_choices(flags)
    if any(text.strip() != reset_payloads.get(key, "").strip() for key, text in payloads.items()):
        return False
    return all(bool(value) == reset_flags.get(name, False) for name, value in flags.items() if name in reset_flags)


def unzoom_target(history: Sequence[tuple[Choices, object]]) -> int | None:
    """Return the index of the step Unzoom goes back to in the window's or the page's history, or None for none (batch 28.2).

    Each step is (the choices before it, the preview's settings or None).
    Only a Reset's step keeps the preview's settings, so a step with them
    is a Reset's and every other one a zoom's or a move's (a drag, the
    wheel, the date buttons, Unzoom's own). Unzoom goes back to the choices
    before the first zoom or move since the last Reset; None while none
    has followed it, when the button is greyed. Until batch 28.2 it went
    back to the first step whatever came after, so after a Reset it
    brought back the chart from before the Reset (found 2026-10-25).
    """
    resets = [index for index, (_choices, preview) in enumerate(history) if preview is not None]
    first = resets[-1] + 1 if resets else 0
    return first if first < len(history) else None


def trim_history(history: list, limit: int) -> None:
    """Drop the oldest steps of ``history`` past ``limit``, never Unzoom's target or the last Reset it is counted from (batch 28.2).

    With no Reset, the oldest after the first go, as before batch 28.2.
    """
    resets = [index for index, (_choices, preview) in enumerate(history) if preview is not None]
    kept = {resets[-1], resets[-1] + 1} if resets else {0}
    doomed = [index for index in range(len(history)) if index not in kept][: max(0, len(history) - limit)]
    for index in reversed(doomed):
        del history[index]


def current_tab(shown: Sequence[str], current: str | None, ticked: str | None = None) -> str | None:
    """Return the tab (a nation's key) to make current among those ``shown`` after a drawing (batch 17.4).

    A newly ticked nation's (``ticked``), once its chart is drawn (Terry,
    2026-10-20: "once the tab for country Y is built and ready, that new tab
    should become the new current tab"); else the current one while it is
    shown; else, its nation unticked, the first. None if no tab is shown.
    """
    for key in (ticked, current):
        if key is not None and key in shown:
            return key
    return shown[0] if shown else None


# ---------------------------------------------------------------------------
# The axis limits under each tab: unit symbols and the "All" tick (batch 18)
# ---------------------------------------------------------------------------


def _relative_in_effect(flags: Mapping[str, bool]) -> bool:
    """True when the right axis is a percentage of GDP: -r ticked, with debt or interest to act on (``idle_controls``)."""
    return flags.get("relative", False) and "relative" not in idle_controls(flags)


def limit_unit(nation: Nation, name: str, flags: Mapping[str, bool]) -> str:
    """Return the unit symbol shown right of ``nation``'s limit box ``name`` (batch 18.1): "%", its currency's ("C$"), or "".

    Terry, 2026-10-14: "include a units symbol immediately to the right of
    any of these axis limit value-boxes that has an associated unit
    symbol": the yield axis's "%", moved there from the left of Max and
    Min, and right of Top and Bottom the nation's currency, per capita too.
    "For other axis units that have no useful symbol, like CPI or
    debt-to-GDP ratio, ... leave the symbol blank": Top and Bottom under -r,
    where a value is a percentage of GDP typed with its own "%" ("150%").
    """
    if name in _YIELD_LIMITS:
        return "%"
    return "" if _relative_in_effect(flags) else nation.currency_symbol


def all_tick(name: str) -> str:
    """Return the flag key of limit ``name``'s "All" tick ("all-max"): one tick, shown beside every nation's box of the limit (batch 18.2).

    Kept with the flags, so Back, Reset and the window's remembered settings
    keep it. No option has the name, so nothing reads it as one; nor does a
    chart or the command line depend on it: the boxes it fills say what is
    drawn, and a limit every nation's box shows alike is written once, for
    every chart (``--max:8``, ``options.command_line_tokens``).
    """
    return f"all-{name}"


ALL_TICKS = tuple(all_tick(name) for name in LIMITS)


def nations_ticked(flags: Mapping[str, bool]) -> int:
    """Return how many nation boxes are ticked."""
    return sum(1 for name in nation_boxes() if flags.get(name, False))


def all_tick_offered(payloads: Mapping[str, str], flags: Mapping[str, bool], key: str, blanked: Collection[str] = ()) -> bool:
    """True when the "All" box beside a nation's limit box ``key`` ("us:max") can be ticked; greyed otherwise.

    Terry, 2026-10-14: greyed "unless the corresponding value-box is
    non-blank (non-auto-generated) and there is more than one nation
    selected". A box blanked by typing (``blanked``) counts as not blank
    until Return is typed in it or it is left (decision 47). Greyed too
    while its box is (Top and Bottom with no right-axis curve), and since
    batch 28.1 while its text is one the box's own parser refuses, which
    ticking would copy to every nation (``field_problems``). Top and
    Bottom in amounts are copied with their currency since batch 18.3
    (``limit_copies``); until then they took "All" only as percentages of GDP.
    """
    return not all_tick_reason(payloads, flags, key, blanked)


def all_tick_reason(payloads: Mapping[str, str], flags: Mapping[str, bool], key: str, blanked: Collection[str] = ()) -> str:
    """Return why the "All" box beside ``key`` is greyed (``all_tick_offered``), a clause to follow "Greyed because"; "" while it is offered (batch 29.1)."""
    option = option_of(key)
    text = payloads.get(key, "").strip()
    if not (text or key in blanked):
        return f"the {option.label} box is blank"
    if text:
        try:
            option.parse(text)
        except ValueError:
            return f"the {option.label} box's text is not a value it takes"
    if nations_ticked(flags) < 2:
        return "only one nation is ticked"
    return idle_control_reasons(flags).get(option.name, "")


def limit_copies(updates: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """Return the texts the other nations' boxes take from the limits in ``updates`` (key -> text) whose "All" is ticked.

    Terry, 2026-10-14: "when on, anything entered in the respective
    value-box would instantly override anything in the corresponding
    value-box on all the other national pages". Every nation's box, its
    chart drawn or not, so that the limit is written once, for every chart.
    A blank is not copied: blanking a box unticks its "All" instead, and
    leaves the others' values (``settled_all_ticks``). An amount in the
    nation's own currency is copied with that currency's code in front
    ("20t" from the U.S.' box as "USD20t"), which each other chart converts
    at the rate of its end date (batch 18.3, decision 41; Terry: "a currency
    conversion will be necessary to get the correct values cross-populated");
    a percentage of GDP, an amount already marked, or a text that does not
    parse, as it is.
    """
    copies: dict[str, str] = {}
    for key, text in updates.items():
        nation, option = nation_of(key), option_of(key)
        if nation is None or option.name not in LIMITS or not text.strip() or not flags.get(all_tick(option.name), False):
            continue
        copied = text.strip()
        if option.name not in _YIELD_LIMITS and not is_percent_bound(copied):
            try:
                _amount, currency = option.parse(copied)
            except ValueError:
                currency = ""
            if currency is None:
                copied = nation.currency + copied
        copies.update({nation_choice(other, option): copied for other in NATIONS if other is not nation})
    return copies


def settled_all_ticks(payloads: Mapping[str, str], flags: Mapping[str, bool], blanked: Collection[str] = ()) -> dict[str, bool]:
    """Return every "All" tick after a change: unticked where its rule no longer holds (batch 18.2).

    A tick stays while more than one nation is ticked and every nation's
    box of its limit holds a value (a box blanked by typing, ``blanked``,
    counting as not blank until Return is typed in it or it is left,
    decision 47); a greyed limit keeps its tick, as a greyed field keeps
    its text. Terry, 2026-10-14: "Blanking out one value-box automatically
    unticks the corresponding “All” tick-box ... and unticks it on all the
    other nations too, but it doesn't blank out the corresponding
    value-boxes of the other nations". A change of measure clears Top and
    Bottom, and so unticks theirs. (Until batch 18.3, Top's and Bottom's
    were unticked too when they were amounts.)
    """
    ticks: dict[str, bool] = {}
    for name in LIMITS:
        keys = [nation_choice(nation, by_name(name)) for nation in NATIONS]
        filled = all(payloads.get(key, "").strip() or key in blanked for key in keys)
        ticks[all_tick(name)] = bool(flags.get(all_tick(name), False)) and filled and nations_ticked(flags) >= 2
    return ticks


# ---------------------------------------------------------------------------
# Levels, help text, and the drawn chart as a file
# ---------------------------------------------------------------------------


def idle_controls(flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the options greyed out for these choices, by name.

    Those that change nothing on any chart (``options.idle_options``), and
    GDP under -r, where it is the divisor and is not drawn. Since batch
    28.1, from the plan's measurements of the page (2026-10-25): the yield
    terms while the yields are off, as the spread, policy and mortgage boxes
    are while their switch is; and Min and Max while nothing is drawn on
    the yield axis, neither yields nor spreads, policy or mortgage rates
    (``PlotConfig.has_left_axis_series``), which then takes the right
    axis's range. A blank flag is its default (every curve on, the rates
    off).
    """
    return frozenset(idle_control_reasons(flags))


def idle_control_reasons(flags: Mapping[str, bool]) -> dict[str, str]:
    """Return ``idle_controls``' names, each with why it is greyed, a clause to follow "Greyed because" (batch 29.1).

    Each rule gives its reason where it greys, so that the reason the
    window's ⓘ panel and the page's "?" tip give cannot part from the rule.
    """
    reasons = idle_option_reasons(flags.get("debt", True), flags.get("gdp", True), flags.get("interest", True))
    if flags.get("relative", False) and "relative" not in reasons:
        reasons["gdp"] = "under % of GDP, GDP is the divisor and is not drawn"
    if not flags.get("yield", True):
        reasons["yields"] = unticked("yield")
        if not any(flags.get(name, False) for name in _LEFT_AXIS_RATES):
            reasons |= dict.fromkeys(("min", "max"), "nothing is drawn on the yield axis: no yields, spreads, policy or mortgage rates")
    return reasons


# The switches of the curves of ``ratesplot.rates``, drawn on the yield axis
# with the yields (``PlotConfig.has_left_axis_series``).
_LEFT_AXIS_RATES = ("policy", "mortgages", "spreads")


def idle_choices(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the options greyed out for these choices: ``idle_controls``, and the latest values' where they can bring nothing new.

    The automatic refresh's (batch 11.3), the intraday quotes and the
    projections to today (batch 28.1, by the End date) turn on the fields
    too, so they are judged on the texts a drawing takes
    (``options.latest_idle``).
    """
    return frozenset(idle_choice_reasons(payloads, flags))


def idle_choice_reasons(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """Return ``idle_choices``' names, each with why it is greyed; one greyed by both gives ``idle_control_reasons``' (batch 29.1)."""
    return latest_idle_reasons(_texts_in_effect(payloads, flags), flags) | idle_control_reasons(flags)


# Every option ``idle_controls`` and ``idle_choices`` can grey out: those idle
# with no right-axis curve chosen, and GDP (under -r); the yield terms, Min
# and Max (batch 28.1); the latest values' (``options.latest_idle``); and a
# nation's aggregate debts, by its key (``idle_nation_keys``).
GREYABLE_OPTIONS = (
    frozenset(idle_option_reasons(False, False, False))
    | {"gdp", "aggregate", "yields", "min", "max", "current"}
    | AUTO_REFRESH_OPTIONS
)


def idle_nation_keys(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the keys of the nations' own fields that change nothing: a margin whose term is not drawn, aggregate debts not drawn.

    ``options.idle_margins`` (the prime rate's, the tracker's) and
    ``options.idle_aggregates`` (batch 10.4).
    """
    return frozenset(idle_nation_key_reasons(payloads, flags))


def idle_nation_key_reasons(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """Return ``idle_nation_keys``' keys, each with why it is greyed, a clause to follow "Greyed because" (batch 29.1)."""
    return idle_margin_reasons(payloads, flags) | idle_aggregate_reasons(payloads, flags)


def greyed_reason(key: str, payloads: Mapping[str, str], flags: Mapping[str, bool]) -> str:
    """Return why the control ``key`` (an option's name, or a nation's own field: "us:max") is greyed now, or "" while it is not (batch 29.1).

    The window's rule and the page's (``gui._update_dependent_controls``,
    ``web._value_control``): what changes nothing on any chart
    (``idle_choices``), a value whose box is unticked (the tolerance without
    the regression segments), and a nation's field that changes nothing on
    its chart (``idle_nation_keys``). Shown in the window's ⓘ panel and the
    page's "?" tip as "Greyed because …" (``greyed_line``), so that the rule
    that greys what has no effect explains itself.
    """
    return greyed_reasons((key,), payloads, flags).get(key, "")


def greyed_reasons(keys: Collection[str], payloads: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """Return ``greyed_reason`` for each of ``keys`` that is greyed, the rules judged once (the page asks for every control as it lays them out).

    The "All" ticks (``ALL_TICKS``) are kept with the flags but name no
    option; ``all_tick_reason`` gives theirs, so they are passed over here.
    """
    idle = idle_choice_reasons(payloads, flags)
    nations = idle_nation_key_reasons(payloads, flags)
    reasons: dict[str, str] = {}
    for key in keys:
        if key in ALL_TICKS:
            continue
        option = option_of(key)
        if option.name in idle:
            reasons[key] = idle[option.name]
        elif option.turns_on is not None and not flags.get(option.turns_on, False):
            reasons[key] = unticked(option.turns_on)
        elif key in nations:
            reasons[key] = nations[key]
    return reasons


def greyed_line(reason: str) -> str:
    """The line a greyed control's help gains: "Greyed because “Bond yields” is unticked." ("" for no reason)."""
    return f"Greyed because {reason}." if reason else ""


# A number typed without the 0 before its point: ".3", "-.25", "+.5t".
_BARE_POINT = re.compile(r"^(\s*[+-]?)\.(?=\d)")


def with_leading_zero(text: str) -> str:
    """Return a field's text with a 0 before the point of a number typed without one: ".3" → "0.3", "-.25%" → "-0.25%".

    Terry, 2026-10-13 (batch 15.5): every value the program writes has its
    0, but a typed one was kept as typed, and so written on the command
    line (``--reg:.3``). Both front ends rewrite a field this way when
    Enter is pressed in it or it is left; the command line still accepts
    ``.3``, which parses as ``0.3`` does, so no chart changes. Any other
    text is returned as it is.
    """
    return _BARE_POINT.sub(r"\g<1>0.", text)


def drawn_payloads(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """Return the field texts a drawing takes: blanks left out, and every greyed field's text.

    A greyed field changes nothing, so a bad text left in it must not stop
    the drawing: a value whose flag is off (the tolerance without --reg), and
    one with no curve to act on (``idle_controls``: Top and Bottom, the
    levels, the tolerance; a nation's margin while its chart draws not its
    term, the prime rate, and its aggregate debts while none is drawn,
    ``idle_nation_keys``); and the automatic refresh's minutes where it can
    bring nothing new (``idle_choices``). The field keeps its text for when
    it applies again, and the written command line leaves it out
    (``options.command_line_tokens``).
    """
    drawn = _texts_in_effect(payloads, flags)
    if "auto-refresh-minutes" in drawn and auto_refresh_idle(drawn, flags):
        del drawn["auto-refresh-minutes"]
    return drawn


def _texts_in_effect(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> dict[str, str]:
    """``drawn_payloads`` but for the automatic refresh's rule, which is judged on these (``idle_choices``)."""
    idle = idle_controls(flags)
    idle_keys = idle_nation_keys(payloads, flags)
    drawn: dict[str, str] = {}
    for key, text in payloads.items():
        option = option_of(key)
        off = option.turns_on in flags and not flags[option.turns_on]
        if text.strip() and not off and option.name not in idle and key not in idle_keys:
            drawn[key] = text.strip()
    return drawn


def bounds_in_other_units(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> list[str]:
    """Return the Top and Bottom fields whose text is in the other unit from the measure in effect.

    A percentage while -r has no effect, or dollars while it has. -r loses
    its effect when debt and interest are both unticked, and regains it when
    one is ticked again (``options.idle_options``), so GDP then changes from
    dollars to nothing drawn or back; the window and the page clear such
    fields, as a change of measure clears them. Not while no right-axis curve
    is chosen: the fields are idle then, and kept for when one is chosen.
    """
    idle = idle_controls(flags)
    if "top" in idle:
        return []
    relative = flags.get("relative", False) and "relative" not in idle
    return [key for key in bound_keys() if payloads.get(key, "").strip() and is_percent_bound(payloads[key]) != relative]


def bound_keys() -> list[str]:
    """Return the keys of the right-axis limits, whose units the measure sets: each nation's Top and Bottom."""
    return [nation_choice(nation, by_name(bound)) for bound in ("top", "bottom") for nation in NATIONS]


def field_problems(payloads: Mapping[str, str], flags: Mapping[str, bool], changed: Sequence[str] = ()) -> dict[str, str]:
    """Return the message for each field to be marked wrong (its label and its text red), by key.

    ``payloads`` are the texts a drawing takes (``drawn_payloads``: a greyed
    field is never wrong). A text its option's parser rejects is wrong by
    itself (a Top or Bottom at or below zero among them). Otherwise a
    problem between fields (Min not below Max, Bottom not below Top, a
    limit in the other unit from the measure, End before Start) is put on
    the field changed last among those it involves (``changed``, oldest
    first): Terry, 2026-10-12, "the last box to be altered would be
    considered the offending box". The fields involved are those whose
    removal makes it go away; when none of them was changed by hand (all
    came from the command line, the remembered settings or a zoom), each is
    marked. A problem no field is involved in (-r with -p) marks none, and
    the caller reports it alone.
    """
    problems: dict[str, str] = {}
    for key, text in payloads.items():
        try:
            option_of(key).parse(text)
        except ValueError as exc:
            problems[key] = str(exc)
    if problems:
        return problems
    message = _problem(payloads, flags)
    if message is None:
        return {}
    involved = [key for key in payloads if _problem({k: v for k, v in payloads.items() if k != key}, flags) != message]
    order = {key: index for index, key in enumerate(changed)}
    latest = max((key for key in involved if key in order), key=order.__getitem__, default=None)
    return {key: message for key in ([latest] if latest is not None else involved)}


def problem_text(key: str, message: str) -> str:
    """Name the field a problem is in, for the "Not drawn" line: "Canada, Max: ..."."""
    nation = nation_of(key)
    return f"{nation.name + ', ' if nation else ''}{option_of(key).label}: {message}"


def _problem(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> str | None:
    """The message of the first problem the choices have (``config_from_choices``), or None."""
    try:
        config_from_choices(payloads, flags)
    except ValueError as exc:
        return str(exc)
    return None


def size_boxes_at_fault(text: str) -> tuple[bool, bool]:
    """Return which of the width and height boxes a wrong ``WxH`` text is wrong in: (width, height).

    A box is wrong when it holds something other than digits, or a size
    below the minimum; if neither is wrong by itself (a text the boxes do
    not show), both are marked.
    """
    width, _x, height = text.strip().lower().partition("x")

    def wrong(part: str) -> bool:
        part = part.strip()
        return bool(part) and (not part.isdigit() or int(part) < MIN_CANVAS_PX)

    faults = (wrong(width), wrong(height))
    return faults if any(faults) else (True, True)


def option_of(key: str) -> Option:
    """Return the option a choice's key names: "us:top" and "top" are both --top."""
    return by_name(key.split(":")[-1])


def nation_of(key: str) -> Nation | None:
    """Return the nation a choice's key is for ("us:top"), or None for both charts."""
    code = key.partition(":")[0] if ":" in key else ""
    return next((nation for nation in NATIONS if nation.key == code), None)


def level_letters(text: str, nation: Nation | None = None) -> set[str]:
    """Return the levels a ``--debt:`` text names, synonyms resolved: ``"fs"`` -> ``{"f", "p"}``.

    With ``nation``, its own synonyms too, so the boxes of its panel tick:
    the UK's ``"n"`` is its local level, ``"m"`` (batch 10.5). Lenient, for
    ticking the level boxes: letters that are not levels are ignored here
    (the option's parser reports them when the chart is drawn).
    """
    own = dict(nation.level_synonyms) if nation else {}
    resolved = (COMPONENT_SYNONYMS.get(letter, letter) for letter in text.strip().lower())
    return {own.get(letter, letter) for letter in resolved}


def level_text(ticked: set[str] | list[str]) -> str:
    """Return the levels' text for the boxes ticked, as the command line writes it: in ``COMPONENT_LETTERS`` order ("" for none)."""
    return "".join(letter for letter in COMPONENT_LETTERS if letter in ticked)


# ---------------------------------------------------------------------------
# Tick boxes for a list option (Option.editor == "choices")
# ---------------------------------------------------------------------------
# The option's text (its command-line value, "10y-2y,10y-3m") stays the one
# source of truth, as for the levels and the size: the boxes are a view of it
# and write it back. The window and the web page share these rules.


def choice_values(option: Option, text: str, nation: Nation | None = None) -> list[str]:
    """Return the list items ``text`` names, as the option writes them ("2", "10" -> ["2y", "10y"]).

    A blank text is the option's default; for a nation's own field, as far as
    its chart draws it (``nation_view``: Canada's mortgage terms by default
    are "5"). "none" names nothing, so no box is ticked. Lenient, for
    ticking the boxes: a text that does not parse names nothing here (the
    option's parser reports it when the chart is drawn).
    """
    default = PlotConfig()
    try:
        value = option.parse(text) if text.strip() else getattr(default, option.fields[0])
    except ValueError:
        return []
    if nation is not None and not text.strip():
        value = nation_view(nation, option, value)
    if not value:
        return []
    written = option.format((value,), default)
    return [item for item in written.split(",") if item]


def _offers(nation: Nation, option: Option, value: str) -> bool:
    """True when ``nation``'s chart can draw a box's item: a term it has, a spread of two of them, an aggregate debt it has; either policy term."""
    if option.fields[0] == "policy_terms":
        return True
    if option.fields[0] == "debt_aggregates":
        return value in nation.debt_aggregates
    if option.fields[0] == "mortgage_terms":
        return value in nation.mortgage_terms
    terms = value.split("-") if option.fields[0] == "spread_pairs" else [value]
    return all(term in nation.yield_terms for term in terms)


def _nation_box(nation: Nation, option: Option, box: tuple[str, str]) -> tuple[str, str]:
    """Return ``box`` as ``nation``'s panel captions it: the "market" policy box named for its rate, "market (CORRA)" (batch 24.5)."""
    value, caption = box
    if option.fields[0] == "policy_terms" and value == "market" and nation.overnight_rate:
        return value, f"{caption} ({nation.overnight_rate})"
    return box


def choice_rows(option: Option, text: str, nation: Nation | None = None) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return the option's rows of boxes, ``(caption, [(value, box caption), ...])``.

    The offered rows (``Option.choices``), then a row "other" for any item
    ``text`` names that none of them offers (a spread typed on the command
    line), so nothing chosen is hidden. For a nation's own field, only the
    boxes its chart can draw, without the rows' captions ("U.S. only",
    "Canada"), which say whose they are, and in its own words where it has
    them ("market (SONIA)", ``_nation_box``).
    """
    rows = [(caption, list(boxes)) for caption, boxes in option.choices]
    if nation is not None:
        rows = [
            ("", [_nation_box(nation, option, box) for box in boxes if _offers(nation, option, box[0])])
            for _caption, boxes in rows
        ]
        rows = [row for row in rows if row[1]]
    offered = {value for _caption, boxes in rows for value, _box in boxes}
    others = [(value, value.replace("-", "–")) for value in choice_values(option, text, nation) if value not in offered]
    return rows + ([("other", others)] if others else [])


def panel_lists(nation: Nation) -> list[Option]:
    """Return the lists under a nation's tab, in their order (``_PANEL_LISTS``): those offering it a choice, two boxes or more.

    The tick-box lists (``Option.editor`` "choices") and the levels
    ("levels", the nation's own ``level_boxes``, batch 10.5). The aggregate
    debts only for the UK, the only nation with two (batch 10.4); a nation
    without the choice draws its gross debt.
    """
    lists = sorted(
        (option for option in NATION_OPTIONS if option.editor in ("choices", "levels")),
        key=lambda option: _PANEL_LISTS.index(option.fields[0]),
    )

    def boxes(option: Option) -> int:
        if option.editor == "levels":
            return len(nation.level_boxes)
        return sum(len(row) for _caption, row in choice_rows(option, "", nation))

    return [option for option in lists if boxes(option) >= 2]


def choices_text(option: Option, ticked: list[str]) -> str:
    """Return the option's text for the ticked items, written as the command line writes it.

    The yield terms in term order ("3m,2y,7y,10y", wherever 7y's box is), the
    spreads in box order (which sets their colours); "none" when none is
    ticked, which a nation's field shows when a list for every chart leaves
    it none of its items (a blank field would be its default).
    """
    joined = ",".join(ticked)
    return ",".join(choice_values(option, joined)) if joined else NONE_ITEM


def choice_refusal(option: Option) -> str:
    """Say why a list's last ticked box stays ticked, and which box draws none of it.

    Drawing none is the job of the curve's own box (Terry, 2026-10-06:
    "that is what --no-y is for"): the flag a list belongs to, or for the
    yield terms the yield curve's (``options.list_switch``). A field shows
    no box ticked only when the command line left that nation none of a list.
    """
    return f"At least one of the {option.label.lower()} stays ticked; to draw none, untick “{list_switch(option).label}”."


def option_help_lines(option: Option) -> tuple[str, str, str]:
    """Return an option's group notes, its help text and its command-line spelling."""
    return (
        f"{' '.join(GROUPS[option.group].split())}",
        f"{option.label}: {' '.join(option.help.split())}",
        f"Command line: {option.usage}",
    )


# ---------------------------------------------------------------------------
# The long help (batch 29.1, decision 76)
# ---------------------------------------------------------------------------

# One Markdown file per topic an option names (``Option.topic``), kept in the
# repository with the code it describes. The window's More opens it in a
# window of its own (``help_blocks``); the page opens it alone in a new tab,
# at its address with ``?help=TOPIC`` (``HELP_KEY``).
HELP_DIR = Path(__file__).resolve().parent.parent / "docs" / "help"
HELP_KEY = "help"


def help_address(topic: str) -> str:
    """The address of topic ``topic``'s help view, relative to the page: ``?help=TOPIC``, the query replaced whole.

    The page's More links to it (batch 29.1), and since batch 29.2 a topic
    links to another the same way: the page follows the link as it is, the
    window opens that topic's own window (``help_link_topic``).
    """
    return f"?{HELP_KEY}={topic}"


def help_link_topic(url: str) -> str | None:
    """The topic a help link names, written as ``help_address`` writes it; None for a link to another site."""
    prefix = help_address("")
    return url[len(prefix):] if url.startswith(prefix) else None


def help_topics() -> dict[str, tuple[Option, ...]]:
    """Return every topic the options name, each with the options that name it, in the table's order."""
    topics: dict[str, list[Option]] = {}
    for option in OPTIONS:
        if option.topic:
            topics.setdefault(option.topic, []).append(option)
    return {topic: tuple(named) for topic, named in topics.items()}


def help_text(topic: str) -> str:
    """Return topic ``topic``'s Markdown; KeyError for a name no option gives (the page's address may hold anything)."""
    if topic not in help_topics():
        raise KeyError(topic)
    return (HELP_DIR / f"{topic}.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class HelpSpan:
    """A piece of a help block's text: plain, bold, code, or a link to ``url``."""

    text: str
    style: str = ""  # "", "bold", "code" or "link"
    url: str = ""


@dataclass(frozen=True)
class HelpBlock:
    """A heading (``level`` 1 for "#"), a paragraph or a list item of a help topic, as its spans."""

    kind: str  # "heading", "paragraph" or "item"
    spans: tuple[HelpSpan, ...]
    level: int = 0


_HELP_HEADING = re.compile(r"(#{1,6})\s+(.*)")
_HELP_ITEM = re.compile(r"[-*]\s+(.*)")
_HELP_INLINE = re.compile(r"\*\*(?P<bold>.+?)\*\*|`(?P<code>[^`]+)`|\[(?P<link>[^\]]+)\]\((?P<url>[^)\s]+)\)")


def help_blocks(markdown: str) -> list[HelpBlock]:
    """Return a topic's Markdown as the window shows it: headings, paragraphs and list items, each in spans.

    Tk shows no Markdown, so the window renders this much of it in a Text
    widget (the plan's note to 29.1); the page shows the Markdown itself. A
    blank line ends a paragraph or an item, whose lines are joined; "#" to
    "######" start a heading, "- " or "* " an item; within a block,
    **bold**, `code` and [text](url).
    """
    blocks: list[HelpBlock] = []
    lines: list[str] = []
    kind = "paragraph"

    def finish() -> None:
        if lines:
            blocks.append(HelpBlock(kind, _help_spans(" ".join(lines))))
            lines.clear()

    for line in (raw.strip() for raw in markdown.splitlines()):
        heading, item = _HELP_HEADING.fullmatch(line), _HELP_ITEM.fullmatch(line)
        if not line:
            finish()
            kind = "paragraph"
        elif heading:
            finish()
            blocks.append(HelpBlock("heading", _help_spans(heading.group(2)), len(heading.group(1))))
            kind = "paragraph"
        elif item:
            finish()
            kind = "item"
            lines.append(item.group(1))
        else:
            lines.append(line)
    finish()
    return blocks


def _help_spans(text: str) -> tuple[HelpSpan, ...]:
    """``text``'s plain, bold, code and link pieces, in order."""
    spans: list[HelpSpan] = []
    place = 0
    for found in _HELP_INLINE.finditer(text):
        if found.start() > place:
            spans.append(HelpSpan(text[place:found.start()]))
        if found["bold"] is not None:
            spans.append(HelpSpan(found["bold"], "bold"))
        elif found["code"] is not None:
            spans.append(HelpSpan(found["code"], "code"))
        else:
            spans.append(HelpSpan(found["link"], "link", found["url"]))
        place = found.end()
    if place < len(text):
        spans.append(HelpSpan(text[place:]))
    return tuple(spans)


def png_bytes(figure: Figure) -> bytes:
    """Return ``figure`` as PNG bytes at its own DPI, exactly as the command line saves it."""
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=figure.dpi, metadata=PNG_METADATA)
    return buffer.getvalue()


def saved_png_name(key: str, drawn: PlotConfig | None) -> str:
    """Return the file name a chart is saved under: ``cdn_rates_1981-09-01_2026-09-29.png``.

    Named by the dates drawn (an automatic start as found); without them
    (nothing drawn yet) just ``cdn_rates.png``.
    """
    dates = "" if drawn is None else f"_{drawn.start:%Y-%m-%d}_{drawn.end:%Y-%m-%d}"
    return f"{key}_rates{dates}.png"


def saved_export_name(key: str, drawn: PlotConfig | None, extension: str, every: bool = False) -> str:
    """Return the file name a chart is exported under (batch 11.1): ``saved_png_name``'s with ``extension``.

    A workbook of every chart (``every``) drops the nation's key:
    ``rates_1981-09-01_2026-09-29.xlsx``.
    """
    name = saved_png_name(key, drawn).removesuffix(".png")
    return f"{name.removeprefix(f'{key}_') if every else name}{extension}"


def saved_log_name(when: pd.Timestamp) -> str:
    """Return the file name the message log is saved under: ``ratesplot_log_2026-10-14_1015.txt``.

    Named by the minute ``when`` (Terry, 2026-10-14, batch 15.3): the
    window's time of saving, the page's time of its drawing, whose log it
    is. The window's log runs over many drawings, so no chart's dates.
    """
    return f"ratesplot_log_{when:%Y-%m-%d_%H%M}.txt"


# The program's own folder: the repository's working folder when it is run from a clone (batch 11.5).
PROGRAM_FOLDER = Path(__file__).resolve().parents[1]


def _started_commit(folder: Path) -> str | None:
    """The commit ``folder``'s git checkout is at, abbreviated (``.git/HEAD``, a branch's ref or packed-refs); None without one.

    Read once, when the program starts: the web page's server pulls the
    daily job's commits without loading their code again, so the commit it
    started from is the one its code is.
    """
    git = folder / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="ascii").strip()
        if not head.startswith("ref: "):
            return head[:7] or None
        ref = head.removeprefix("ref: ")
        if (git / ref).is_file():
            return (git / ref).read_text(encoding="ascii").strip()[:7] or None
        for line in (git / "packed-refs").read_text(encoding="ascii").splitlines():
            if line.endswith(" " + ref):
                return line[:7]
    except (OSError, UnicodeDecodeError):
        pass
    return None


_STARTED_COMMIT = _started_commit(PROGRAM_FOLDER)


def version_text() -> str:
    """The version as the window and the page show it (batch 11.7): "v6.5 · 8c3e41b", the commit left off where there is no checkout."""
    return f"v{__version__} · {_STARTED_COMMIT}" if _STARTED_COMMIT else f"v{__version__}"
# Windows' known folder for Documents (FOLDERID_Documents), which a user may have moved.
_DOCUMENTS_GUID = (0xFDD39AD0, 0x238F, 0x46AF, (0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort), ("data4", ctypes.c_ubyte * 8)]


def documents_folder() -> Path:
    """The user's Documents folder: Windows' own, wherever it was moved; elsewhere ~/Documents; failing both, the home folder."""
    if sys.platform == "win32":
        first, second, third, rest = _DOCUMENTS_GUID
        found = ctypes.c_wchar_p()
        guid = _Guid(first, second, third, (ctypes.c_ubyte * 8)(*rest))
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(found)) == 0:
            path = Path(found.value)
            ctypes.windll.ole32.CoTaskMemFree(found)
            if path.is_dir():
                return path
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def save_dialog_folder(remembered: str | None) -> str:
    """Where the window's save dialogs open (batch 11.5): the folder last saved to, else the Documents folder.

    Never the working folder, nor the program's own folder or one inside it:
    started from the repository's folder, a dialog given no folder opened
    there, and what was saved became an untracked file of the public
    repository (Terry, 2026-10-26: "these other files are not even written
    where the repository would see them"). A folder saved to there by choice
    is used that once; the next dialog opens in Documents.
    """
    if remembered:
        folder = Path(remembered)
        try:
            resolved = folder.resolve()
            inside = resolved == Path.cwd().resolve() or resolved == PROGRAM_FOLDER or PROGRAM_FOLDER in resolved.parents
        except OSError:
            inside = True
        if folder.is_dir() and not inside:
            return str(folder)
    return str(documents_folder())


# The "Remember my settings" box, in the window and on the page (batch 24.6;
# Terry, decisions 60, 69 and 74): for charts that should leave the settings
# kept alone. Ticked at every start or visit, its off state never saved.
# Unticked, what is remembered is left as it was, neither written nor
# cleared; ticked again, the settings shown are kept. Reset gives the
# defaults, which the next drawing keeps while the box is ticked.
REMEMBER_LABEL = "Remember my settings"
REMEMBER_HELP = (
    "Ticked, as at every start, each drawing's settings are kept for next time. Unticked, the settings kept are left as "
    "they are, neither written nor cleared, so the charts drawn meanwhile do not replace them; ticked again, the settings "
    "shown are kept."
)

# The buttons the window and the page both have, and their tips, from one
# place so that the two read alike (batch 31.6; Terry, 2026-10-28: "Some
# controls (buttons, etc.) don't have working "hover over" help on the
# Windows version, even though they do on the Web version"). The page's
# download button is named as the window's button (batch 31.4).
REFRESH_HELP = "Draw again with the latest data: the intraday quotes of the moment, and anything downloaded over an hour ago."
RESET_HELP = "Back to the default charts."
BACK_HELP = "Undo the last zoom, move of the dates, Unzoom or Reset."
UNZOOM_HELP = "Back to the charts before the first zoom or move since the last Reset (Back undoes it)."
EXPORT_LABEL = "Export chart"
EXPORT_HELP = "The chart as an image, or the data it shows: each line's value on each date in the window."
# What a blank date field means, in its grey value on the page and in the tip
# of the calendar's "Blank (default)" in both ("Today when blank.").
BLANK_DATE_WORDS = {"start": "automatic", "end": "today"}


# ---------------------------------------------------------------------------
# Zoom and pan: chart geometry (image pixels <-> data values) and the fields' texts
# ---------------------------------------------------------------------------

# A drag shorter than this (image pixels) on an axis does not change that axis.
_MIN_DRAG_PX = 8
# The command line insists on at least seven days between start and end.
_MIN_SPAN_DAYS = MIN_WINDOW_DAYS
# The wheel over a chart: the notches are collected and the zoom applied once
# the wheel has been still this long, one redraw per gesture; each notch away
# from the person scales the dates' span by the factor, about the pointer.
WHEEL_DELAY_MS = 350
WHEEL_ZOOM_FACTOR = 0.8
# The words on either side of the zoom shown while the wheel turns (the
# page's script writes them too).
WHEEL_ZOOM_WORDS = ("Zoom ×", " (applies when the wheel stops) …")


def wheel_zoom_text(notches: float) -> str:
    """What is shown while the wheel turns over a chart, before its zoom is applied: "Zoom ×1.56 (applies …) …".

    Below a hundredth (21 notches out at once) "<0.01", where two decimals said 0.00.
    """
    before, after = WHEEL_ZOOM_WORDS
    zoom = WHEEL_ZOOM_FACTOR ** -notches
    return f"{before}{zoom:.2f}{after}" if zoom >= 0.01 else f"{before}<0.01{after}"


@dataclass(frozen=True)
class ChartGeometry:
    """Where the axes sit in a rendered chart image, and their limits.

    ``box`` is (left, top, right, bottom) in image pixels, origin top-left.
    x limits are matplotlib date numbers. "left"/"right" are the two y axes:
    the yield axis and its twin carrying the macro series (dollars, or % of GDP).
    ``window`` is the requested Start and End, also as date numbers: the axis
    is wider (a small pad each side, and with -l room for the value labels).
    """

    box: tuple[float, float, float, float]
    xlim: tuple[float, float]
    window: tuple[float, float]
    left_ylim: tuple[float, float]
    right_ylim: tuple[float, float]
    left_log: bool
    right_log: bool

    @classmethod
    def from_figure(cls, figure: Figure, config: PlotConfig) -> ChartGeometry | None:
        """Measure a figure drawn for ``config`` (axes[0] is the yield axis, axes[1] its twin)."""
        if len(figure.axes) < 2:
            return None
        left, right = figure.axes[0], figure.axes[1]
        height = figure.bbox.height
        extent = left.get_window_extent()
        return cls(
            box=(extent.x0, height - extent.y1, extent.x1, height - extent.y0),
            xlim=tuple(left.get_xlim()),
            window=(float(mdates.date2num(config.start)), float(mdates.date2num(config.end))),
            left_ylim=tuple(left.get_ylim()),
            right_ylim=tuple(right.get_ylim()),
            left_log=left.get_yscale() == "log",
            right_log=right.get_yscale() == "log",
        )

    def date_at(self, x: float) -> pd.Timestamp:
        """Return the date at image x (not clamped: pans may run past the axes)."""
        left, _top, right, _bottom = self.box
        low, high = self.xlim
        number = low + (x - left) / (right - left) * (high - low)
        return pd.Timestamp(mdates.num2date(number).replace(tzinfo=None)).normalize()

    def window_x(self) -> tuple[float, float]:
        """Return the image x of the requested Start and End (inside the axes, which are wider)."""
        return tuple(self.x_at_number(number) for number in self.window)

    def x_at_number(self, number: float) -> float:
        """Return the image x of a matplotlib date number (not clamped)."""
        left, _top, right, _bottom = self.box
        low, high = self.xlim
        return left + (number - low) / (high - low) * (right - left)

    def value_at(self, y: float, side: str) -> float:
        """Return the value at image y on the ``"left"`` or ``"right"`` y axis."""
        _left, top, _right, bottom = self.box
        low, high = self.left_ylim if side == "left" else self.right_ylim
        log = self.left_log if side == "left" else self.right_log
        fraction = (bottom - y) / (bottom - top)
        if log:
            return 10 ** (math.log10(low) + fraction * (math.log10(high) - math.log10(low)))
        return low + fraction * (high - low)


def _format_percent(value: float) -> str:
    """Two decimals at most, no trailing zeros: 2.5, 3.14, 4, -0.5 (and 0, never "-0")."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _format_dollars(value: float) -> str:
    """Three significant figures with a k/m/b/t suffix: 1.25t, 380b."""
    rounded = float(f"{value:.3g}")
    return format_dollar_bound((rounded,))


def _format_relative(value: float) -> str:
    """A percentage of GDP (-r), three significant figures: 0.85%, 12.5%, 140%."""
    return f"{float(f'{value:.3g}'):g}%"


def _date_range_texts(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, str]:
    """Return Start/End texts for a zoom or pan.

    The span is widened about its middle to the seven-day minimum if needed.
    There is no data after today, so the end is capped at today, and an end
    of today is written blank: the "today" default then keeps moving, as it
    would if the user had never touched the field.
    """
    today = pd.Timestamp.today().normalize()
    if end < start:
        start, end = end, start
    if (end - start).days < _MIN_SPAN_DAYS:
        middle = start + (end - start) / 2
        start = (middle - pd.Timedelta(days=_MIN_SPAN_DAYS / 2)).normalize()
        end = start + pd.Timedelta(days=_MIN_SPAN_DAYS)
    if end >= today:
        end = today
        start = min(start, today - pd.Timedelta(days=_MIN_SPAN_DAYS))
    return {"start": f"{start:%Y-%m-%d}", "end": "" if end == today else f"{end:%Y-%m-%d}"}


def axis_updates(geometry: ChartGeometry, config: PlotConfig | None, top_y: float, bottom_y: float) -> dict[str, str]:
    """Return field texts pinning the drawn y axes to image rows ``top_y``..``bottom_y``.

    ``config`` is the one the chart was drawn for (None: nothing drawn, no texts).
    """
    updates: dict[str, str] = {}
    if config is None:
        return updates
    if config.has_left_axis_series:
        # Below zero too: a spread (--spreads) is negative where the curve inverts.
        low = max(-99.99, geometry.value_at(bottom_y, "left"))
        high = min(99.99, geometry.value_at(top_y, "left"))
        if high - low >= 0.01:
            updates.update({"min": _format_percent(low), "max": _format_percent(high)})
    if config.has_macro_series:
        low, high = geometry.value_at(bottom_y, "right"), geometry.value_at(top_y, "right")
        if 0 < low < high:
            bound_text = _format_relative if config.relative else _format_dollars
            updates.update({"bottom": bound_text(low), "top": bound_text(high)})
    return updates


def field_hints(drawn: PlotConfig | None, geometries: Mapping[str, ChartGeometry | None]) -> dict[str, str]:
    """Return what each field shows in grey while it is blank: the value in effect, by key.

    Terry, 2026-10-08 (decision 18): a blank field shows its default or
    automatic value in grey, a typed value in black. The regression
    tolerance's default always, and the automatic refresh's minutes (batch
    11.3); once charts are drawn (``drawn``, with the
    start found), the dates they were drawn for (the automatic start, today's
    end) and the axis limits of each chart drawn (``geometries``, by nation),
    as ``"us:max"`` and so on, written as the field would take them (the
    zoom's formats, ``axis_updates``, for the whole axis). A grey value is
    never a field's text: the field stays blank, so it is left off the
    command line and the automatic values keep following the dates and the
    curves. The front ends show a hint only while the field is blank and not
    greyed.
    """
    hints = {
        "regression-tolerance": f"{DEFAULT_REGRESSION_TOLERANCE_PCT:g}",
        "auto-refresh-minutes": f"{DEFAULT_AUTO_REFRESH_MINUTES}",
    }
    # Each nation's margins at their defaults: the prime margin's 0, the prime
    # rate itself (batch 9.4).
    for margin in margin_options().values():
        hints.update({nation_choice(nation, margin): f"{field_default(margin.fields[0]):g}" for nation in NATIONS})
    if drawn is None:
        return hints
    hints["start"] = f"{drawn.start:%Y-%m-%d}"
    hints["end"] = f"{drawn.end:%Y-%m-%d}"
    for nation in NATIONS:
        geometry = geometries.get(nation.key)
        if geometry is None:
            continue
        _left, top, _right, bottom = geometry.box
        texts = axis_updates(geometry, drawn.for_nation(nation.key), top, bottom)
        hints.update({nation_choice(nation, by_name(name)): text for name, text in texts.items()})
    return hints


def zoom_updates(
    geometry: ChartGeometry, config: PlotConfig | None, x0: float, y0: float, x1: float, y1: float
) -> dict[str, str]:
    """Return field texts that zoom to the box (x0, y0)-(x1, y1) in image pixels (x0 <= x1, y0 <= y1).

    Its width sets Start and End, its height the yield Min and Max and the
    right axis's Top and Bottom, of whichever axes are drawn. A side shorter
    than ``_MIN_DRAG_PX`` leaves its axis alone, so a flat box zooms the dates only.
    """
    updates: dict[str, str] = {}
    if x1 - x0 >= _MIN_DRAG_PX:
        updates.update(_date_range_texts(geometry.date_at(x0), geometry.date_at(x1)))
    if y1 - y0 >= _MIN_DRAG_PX:
        updates.update(axis_updates(geometry, config, y0, y1))
    return updates


def pan_updates(geometry: ChartGeometry, config: PlotConfig | None, dx: float, dy: float) -> dict[str, str]:
    """Return field texts that shift the view so the point under the pointer moves by (dx, dy) image pixels."""
    _left, top, _right, bottom = geometry.box
    updates: dict[str, str] = {}
    if abs(dx) >= _MIN_DRAG_PX:
        # The requested window moves, not the whole axis: its pad (and the
        # -l label room) would otherwise be added to the window at every pan.
        start_x, end_x = geometry.window_x()
        updates.update(_date_range_texts(geometry.date_at(start_x - dx), geometry.date_at(end_x - dx)))
    if abs(dy) >= _MIN_DRAG_PX:
        updates.update(axis_updates(geometry, config, top - dy, bottom - dy))
    return updates


def scale_dates_updates(geometry: ChartGeometry, factor: float, anchor_x: float) -> dict[str, str]:
    """Return Start and End texts for the requested window scaled by ``factor`` about image x ``anchor_x``.

    A factor below 1 zooms in, above 1 out; the date under ``anchor_x`` stays put.
    The window is cut at the earliest date a chart shows (``EARLIEST_DATE``,
    1600-01-01 since batch 28.3; the first data, 1680, before) as its end
    is at today (``_date_range_texts``), and before the image x is turned
    into a date: thirty notches of the wheel out at once (a fast spin, a
    trackpad's fling) ran past the year 1, which matplotlib's dates cannot
    hold (batch 24.7).
    """
    start_x, end_x = geometry.window_x()  # the requested window, as for a pan
    first_x = geometry.x_at_number(mdates.date2num(EARLIEST_DATE))
    today_x = geometry.x_at_number(mdates.date2num(pd.Timestamp.today().normalize()))
    new_left = max(anchor_x - (anchor_x - start_x) * factor, first_x)
    new_right = min(anchor_x + (end_x - anchor_x) * factor, today_x)
    # Rounding can put the earliest date's x a hair before it.
    return _date_range_texts(max(geometry.date_at(new_left), EARLIEST_DATE), geometry.date_at(new_right))


def move_dates_updates(start: pd.Timestamp, end: pd.Timestamp, *, shift: float = 0.0, scale: float = 1.0) -> dict[str, str]:
    """Return Start and End texts for the window ``start``..``end`` moved or rescaled (the web page's buttons).

    ``shift`` moves the window by that fraction of its span (negative:
    earlier); ``scale`` multiplies the span about its middle (2: zoom out).
    The window is kept between the earliest date a chart shows
    (``EARLIEST_DATE``, 1600-01-01 since batch 28.3) and today by moving it back inside rather than cutting it, so "Later" on a
    window that nearly reaches today keeps its span, where a pan by pixels
    would shorten it (``_date_range_texts`` caps the end at today). Whole
    days throughout: half a window of an odd number of days would otherwise
    lose its half day to the date's format, and the span a day per step.
    """
    today = pd.Timestamp.today().normalize()
    days = (end - start).days
    # Never longer than the earliest date allows. Days are added as a date
    # offset, not a pandas Timedelta, which ends at 292 years in nanoseconds
    # (the earliest date is 426 years back).
    new_days = min(round(days * scale), (today - EARLIEST_DATE).days)
    new_start = start + pd.offsets.Day(round(days * shift) - (new_days - days) // 2)
    new_end = new_start + pd.offsets.Day(new_days)
    if new_end > today:
        new_start, new_end = new_start - (new_end - today), today
    if new_start < EARLIEST_DATE:
        new_start, new_end = EARLIEST_DATE, min(today, new_end + (EARLIEST_DATE - new_start))
    return _date_range_texts(new_start, new_end)
