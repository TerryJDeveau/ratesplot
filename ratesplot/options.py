"""The table of command-line options: one declaration per option.

Every option is described once, in ``OPTIONS``: how it is recognised on the
command line, which ``PlotConfig`` field(s) it sets, how its value is parsed
and checked, and its line in ``--help``. ``cli.parse_args`` is driven entirely
by this table, the ``--help`` epilog is generated from it, and the GUI builds
its controls from it, so adding an option here adds it everywhere.

How a token is matched (``cli.match_token``). Leading dashes are optional
and case does not matter. A token spells an option when the word after the
dashes (and after ``no-``, for the options that have an off form) is a
leading part of one of the option's ``names``, at least ``shortest`` letters
long; hyphens inside a name may be left out (``--percapita``). So ``-r``,
``--rel`` and ``--ratio`` are all ``--relative``, and ``--reg`` is the
regression. Nothing is matched by its first letter alone any more (Terry,
2026-09-29: "--reg must never invoke -r"): ``--yes`` is not the yield curve,
``--dept`` is not debt, and ``--dimensions`` without a value is not debt.

* A ``KEY:VALUE`` token is matched against the ``VALUE`` options only, and
  any other token against the rest. A value given to an option that takes
  none (``-r:1``, ``--cur:1``) is an error, never another option that shares
  its first letter; so is a ``VALUE`` option named without a value.
* ``no-`` is accepted by ``FLAG`` and ``TOGGLE`` options, and before the
  value of a ``VALUE`` option that takes its list out of a field
  (``Option.removes``: ``--no-yields:30`` drops the 30-year yield).
* A token that spells two options is an error (``--m:5``: --min or --max).
  ``shortest`` keeps apart the names that share a first letter: "c" is
  Canada and "cur" the latest values, "r" the measure and "reg" the
  regression, "g" the GDP curve and "gui" (in full) the window.
* A nation's code in front (``--us:top:20t``, ``--cdn:no-y:30``) sets a
  value for that nation's chart only (``cli.match_prefixed``). Only the
  value options whose fields are all ``config.PER_NATION_FIELDS`` take one
  (``per_nation``), and only the exact codes ("ca", "cdn", "us"): a code is
  not a name, so no leading part of it is accepted. Such a choice is kept
  under the key "NATION:OPTION" ("us:top").

Anything unmatched goes to argparse, which prints ``--help`` or reports it
as unrecognised.

Value parsers raise ``ValueError`` with a user-facing message; ``cli`` turns
that into an argparse error (exit status 2).
"""

from __future__ import annotations

import calendar
import dataclasses
import re
import textwrap
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Callable, Mapping

import pandas as pd

from .config import (
    COMPONENT_LETTERS,
    COMPONENT_SYNONYMS,
    CURRENCY_SYMBOLS,
    DEBT_AGGREGATES,
    DEFAULT_AUTO_REFRESH_MINUTES,
    DEFAULT_REGRESSION_TOLERANCE_PCT,
    DEFAULT_MORTGAGE_TERMS,
    DEFAULT_TRACKER_MARGIN,
    DEFAULT_SPREADS,
    DEFAULT_START_FLOOR,
    DEFAULT_YIELD_TERMS,
    EARLIEST_DATA_START,
    MAX_AUTO_REFRESH_MINUTES,
    MIN_AUTO_REFRESH_MINUTES,
    MIN_CANVAS_PX,
    MIN_REGRESSION_TOLERANCE_PCT,
    MIN_WINDOW_DAYS,
    MORTGAGE_MARGINS,
    MORTGAGE_TERMS,
    NATIONS,
    PER_NATION_FIELDS,
    POLICY_TERMS,
    YIELD_TERMS,
    Nation,
    PlotConfig,
)
from .export import FORMATS, format_of

_DOLLAR_SUFFIX_MULTIPLIERS = {"t": 1e12, "b": 1e9, "m": 1e6, "k": 1e3}
_DEFAULT_DOLLAR_MULTIPLIER = 1e9

_DATE_SPEC = re.compile(r"^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$")

# --start's help, from the floor (plotting.resolve_start); a floor before the
# data begin never applies, and the help then reads as before 2026-10-06.
_START_HELP = (
    "first date (default: the first date on\nwhich every chosen curve has data)"
    if DEFAULT_START_FLOOR < EARLIEST_DATA_START
    else f"first date (default: {DEFAULT_START_FLOOR:%Y-%m-%d}, or the\nfirst date on which every chosen curve\nhas data, if later)"
)


# ---------------------------------------------------------------------------
# Value parsers (each raises ValueError with a user-facing message)
# ---------------------------------------------------------------------------


def parse_date_spec(spec: str, *, kind: str) -> pd.Timestamp:
    """Parse ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` (``/`` also accepted) to a Timestamp.

    Omitted month/day default to 1. ``kind`` ("start"/"end") is used in messages.
    """
    value = spec.strip()
    if not value:
        raise ValueError(f"empty {kind} date spec")

    match = _DATE_SPEC.match(value)
    if not match:
        raise ValueError(f"invalid {kind} date {spec!r}: expected YYYY, YYYY-MM or YYYY-MM-DD")

    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    if not 1 <= month <= 12:
        raise ValueError(f"invalid {kind} month {month}: must be 1–12")
    max_day = calendar.monthrange(year, month)[1]
    if not 1 <= day <= max_day:
        raise ValueError(f"invalid {kind} day {day} for {year}-{month:02d}: month has only {max_day} days")
    return pd.Timestamp(year=year, month=month, day=day)


def parse_dimensions_spec(spec: str) -> tuple[int, int]:
    """Parse ``W``, ``xH`` or ``WxH`` into ``(width, height)`` pixels, assuming 4:3 if needed."""
    value = spec.strip().lower()
    if not value:
        raise ValueError("empty dimensions spec")

    if value.startswith("x"):
        if not value[1:].isdigit():
            raise ValueError(f"dimensions height must be digits only, got {spec!r}")
        height = int(value[1:])
        width = round(height * 4 / 3)
    elif "x" in value:
        width_text, height_text = value.split("x", 1)
        if not (width_text.isdigit() and height_text.isdigit()):
            raise ValueError(f"dimensions must be digits around 'x', got {spec!r}")
        width, height = int(width_text), int(height_text)
    else:
        if not value.isdigit():
            raise ValueError(f"dimensions width must be digits only, got {spec!r}")
        width = int(value)
        height = round(width * 3 / 4)

    if min(width, height) < MIN_CANVAS_PX:
        raise ValueError(f"canvas {width}x{height} px is below minimum size of {MIN_CANVAS_PX} px")
    return width, height


def parse_yield_bound(spec: str, *, kind: str) -> float:
    """Parse a yield-axis bound in percent, allowed range ``(-100, 100)``.

    Negative since 2026-10-06 (Terry): spreads (--spreads) go below zero
    when the curve inverts, and some yields have, so a zoom must reach there.
    """
    value = spec.strip()
    if not value:
        raise ValueError(f"empty {kind} yield bound")
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"invalid {kind} yield bound {spec!r}: must be a decimal number") from None
    if not -100 < parsed < 100:
        raise ValueError(f"{kind} yield bound must be above -100 and below 100, got {parsed}")
    return parsed


def parse_regression_tolerance(spec: str) -> float:
    """Parse the regression tolerance, a percentage of the right axis's height: ``1.5`` or ``1.5%``."""
    value = spec.strip()
    if value.endswith("%"):
        value = value[:-1].strip()
    if not value:
        raise ValueError("empty --reg tolerance: give a percentage of the axis height, e.g. --reg:1.5")
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"invalid --reg tolerance {spec!r}: must be a percentage of the axis height, e.g. 1.5") from None
    if not 0 < parsed <= 100:
        raise ValueError(f"--reg tolerance must be above 0 and at most 100 (% of the axis height), got {spec.strip()}")
    return parsed


def parse_auto_refresh_minutes(spec: str) -> int:
    """Parse the minutes between automatic refreshes (batch 11.3): a whole number, ``MIN_AUTO_REFRESH_MINUTES`` to ``MAX_AUTO_REFRESH_MINUTES``.

    Never more often than every 5 minutes (Terry, 2026-10-08, decision 23):
    a smaller number is refused, not raised to 5, as every value out of
    range is.
    """
    value = spec.strip()
    if not value.isdigit():
        raise ValueError(f"invalid --auto-refresh minutes {spec.strip()!r}: give a whole number of minutes, e.g. --au:10")
    minutes = int(value)
    if not MIN_AUTO_REFRESH_MINUTES <= minutes <= MAX_AUTO_REFRESH_MINUTES:
        raise ValueError(
            f"--auto-refresh minutes must be at least {MIN_AUTO_REFRESH_MINUTES} and at most "
            f"{MAX_AUTO_REFRESH_MINUTES} (a day), got {minutes}"
        )
    return minutes


# A margin's limits (config.MORTGAGE_MARGINS), in points either way: a margin
# the size of the rate itself is a typing error, not a mortgage.
MAX_MARGIN = 10.0


def parse_margin(spec: str, *, spelling: str, base: str, examples: tuple[str, str]) -> float:
    """Parse a margin, in points above (or, negative, below) ``base``: ``0.5``, ``-0.25``, ``+1``.

    ``spelling`` names the option in messages ("--prime"), ``examples`` two
    margins to suggest. A "+" written in the web page's address arrives as
    a space, which is ignored, so ``--prime:+0.5`` there means 0.5 as on
    the command line.
    """
    value = spec.strip()
    first, second = examples
    if not value:
        raise ValueError(f"empty {spelling} margin: give points above or below {base}, e.g. {spelling}:{first} or {spelling}:{second}")
    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"invalid {spelling} margin {value!r}: give points above or below {base}, e.g. {first} or {second}") from None
    if not -MAX_MARGIN <= parsed <= MAX_MARGIN:
        raise ValueError(f"{spelling} margin must be within {MAX_MARGIN:g} points of {base}, got {value}")
    return parsed + 0.0  # -0 is 0


# The prime margin (batch 9.4), in points above or below the prime rate.
parse_prime_margin = partial(parse_margin, spelling="--prime", base="the prime rate", examples=("0.5", "-0.25"))
# The UK tracker's margin (batch 9.5), in points above (or below) Bank Rate.
parse_tracker_margin = partial(parse_margin, spelling="--tracker", base="Bank Rate", examples=("1.75", "1"))


_TERM_SPEC = re.compile(r"^(\d+)\s*([my]?)$")


def parse_term(spec: str, *, kind: str) -> str:
    """Parse one yield term, ``3m``, ``2``, ``5y`` or ``10``, to its key in ``YIELD_TERMS`` ("3m", "2y" …).

    Years unless ``m`` (months) is given. ``kind`` names the option in messages.
    """
    match = _TERM_SPEC.match(spec.strip().lower())
    key = f"{int(match.group(1))}{match.group(2) or 'y'}" if match else None
    if key not in YIELD_TERMS:
        terms = ", ".join(YIELD_TERMS)
        raise ValueError(f"invalid {kind} term {spec.strip()!r}: use {terms} (y may be left out)")
    return key


# A nation's own list that draws none of its items (Terry, 2026-10-07: a list
# for every chart leaving a nation none of its terms draws none of them, with
# a warning). Written so in that nation's field, its boxes all unticked, and
# after its code (--cdn:yields:none); a list for every chart cannot be "none"
# (``config_from_choices``): its curves have their own --no- switch.
NONE_ITEM = "none"


def _is_none(spec: str) -> bool:
    """True for the list that names no item (``NONE_ITEM``)."""
    return spec.strip().lower() == NONE_ITEM


def parse_terms(spec: str, *, kind: str) -> tuple[str, ...]:
    """Parse a comma-separated list of yield terms into ``YIELD_TERMS`` keys, in that order (repeats are harmless); "none" is none."""
    if _is_none(spec):
        return ()
    items = [item for item in spec.split(",") if item.strip()]
    if not items:
        raise ValueError(f"empty {kind} list: name terms such as 3m,2,10")
    chosen = {parse_term(item, kind=kind) for item in items}
    return tuple(term for term in YIELD_TERMS if term in chosen)


def format_terms(values: tuple, _config: PlotConfig) -> str:
    """Format yield terms as the command line writes them: ``3m,2y,5y,10y,30y``; none as "none"."""
    return ",".join(values[0]) or NONE_ITEM


def parse_mortgage_terms(spec: str) -> tuple[str, ...]:
    """Parse ``--mortgages:LIST``: terms of ``MORTGAGE_TERMS`` (30 15 U.S.; 5 3 1 5v Canada; prime both; 2f 3f 5f svr tracker UK; 1-5 5-10 over10 Germany), in that order.

    A "y" after the years is accepted ("30y"), and repeats are harmless; "none" is none.
    """
    if _is_none(spec):
        return ()
    items = [item.strip().lower() for item in spec.split(",") if item.strip()]
    if not items:
        raise ValueError("empty --mortgages list: name terms such as 30,5")
    chosen = set()
    for item in items:
        term = item[:-1] if item.endswith("y") else item.replace("yv", "v")
        if term not in MORTGAGE_TERMS:
            raise ValueError(
                f"invalid --mortgages term {item!r}: use 30 or 15 (U.S.), 5, 3, 1 or 5v (Canada, 5v the "
                "5-year variable), prime (Canada and the U.S.: the banks' prime rate), 2f, 3f, 5f, svr or "
                "tracker (UK, fixed for 2, 3 or 5 years; svr the standard variable rate; tracker Bank Rate "
                "plus a margin), 1-5, 5-10 or over10 "
                "(Germany, fixed for over 1 to 5, over 5 to 10, or over 10 years)"
            )
        chosen.add(term)
    return tuple(term for term in MORTGAGE_TERMS if term in chosen)


def parse_policy_terms(spec: str) -> tuple[str, ...]:
    """Parse ``--policy:LIST``: ``target`` (the central bank's official rate) and ``market`` (the overnight market's), in that order.

    Repeats are harmless; "none" is none (a nation's own list).
    """
    if _is_none(spec):
        return ()
    items = [item.strip().lower() for item in spec.split(",") if item.strip()]
    if not items:
        raise ValueError("empty --policy list: name target, market or both")
    unknown = [item for item in items if item not in POLICY_TERMS]
    if unknown:
        raise ValueError(
            f"invalid --policy term {unknown[0]!r}: use target (the central bank's official rate) "
            "or market (the overnight market's rate around it), or both"
        )
    return tuple(term for term in POLICY_TERMS if term in items)


def parse_debt_aggregates(spec: str) -> tuple[str, ...]:
    """Parse ``--aggregate:LIST``: ``gross`` (general government gross debt) and ``net`` (the UK's public sector net debt), in that order.

    Repeats are harmless. Never none, not even a nation's own: drawing no
    debt is --no-debt's job (batch 10.4).
    """
    items = [item.strip().lower() for item in spec.split(",") if item.strip()]
    if not items or _is_none(spec):
        raise ValueError("--aggregate names gross, net or both; to draw no debt use --no-debt")
    unknown = [item for item in items if item not in DEBT_AGGREGATES]
    if unknown:
        raise ValueError(
            f"invalid --aggregate debt {unknown[0]!r}: use gross (general government gross debt) "
            "or net (the UK's public sector net debt, ex banks), or both"
        )
    return tuple(item for item in DEBT_AGGREGATES if item in items)


def parse_spreads(spec: str) -> tuple[tuple[str, str], ...]:
    """Parse ``--spreads:LIST``: pairs of yield terms such as ``10y-2y,10-3m``, each the first less the second.

    Kept in the order given (it sets their colours); a repeated pair is drawn once; "none" is none.
    """
    if _is_none(spec):
        return ()
    items = [item.strip() for item in spec.split(",") if item.strip()]
    if not items:
        raise ValueError("empty --spreads list: name pairs such as 10y-2y,10y-3m")
    pairs: list[tuple[str, str]] = []
    for item in items:
        legs = item.split("-")
        if len(legs) != 2:
            raise ValueError(f"invalid --spreads pair {item!r}: write two terms joined by '-', e.g. 10y-2y")
        pair = (parse_term(legs[0], kind="--spreads"), parse_term(legs[1], kind="--spreads"))
        if pair[0] == pair[1]:
            raise ValueError(f"invalid --spreads pair {item!r}: the two terms must differ")
        if pair not in pairs:
            pairs.append(pair)
    return tuple(pairs)


def parse_nations(spec: str) -> tuple[str, ...]:
    """Parse ``--nations:LIST``: nations' codes (ca or cdn, us, gb or uk, de, ger or deu), to their keys in ``NATIONS`` order."""
    codes = [item.strip().lower() for item in spec.split(",") if item.strip()]
    if not codes:
        raise ValueError("empty --nations list: name nations' codes such as ca,us")
    known = {code: nation.key for nation in NATIONS for code in nation.codes}
    unknown = [code for code in codes if code not in known]
    if unknown:
        listed = ", ".join(code for nation in NATIONS for code in nation.codes)
        raise ValueError(f"--nations:{spec.strip()}: {unknown[0]} is not a nation's code (codes: {listed})")
    return tuple(nation.key for nation in NATIONS if nation.key in {known[code] for code in codes})


def parse_save_file(spec: str) -> str:
    """Parse ``--save:FILE`` (batch 11.1): a file name whose extension names a format ``export`` writes."""
    path = spec.strip()
    if not path:
        raise ValueError("--save needs a file name: --save:rates.png")
    if format_of(path) is None:
        raise ValueError(f"--save:{path}: the file's extension names its format, one of {', '.join(FORMATS)}")
    return path


def format_spreads(values: tuple, _config: PlotConfig) -> str:
    """Format spread pairs as the command line writes them: ``10y-2y,10y-3m,30y-10y``; none as "none"."""
    return ",".join(f"{first}-{second}" for first, second in values[0]) or NONE_ITEM


def is_percent_bound(spec: str) -> bool:
    """True when a right-axis bound is written as a percentage (``150%``), as ``-r`` requires."""
    return spec.strip().endswith("%")


# The marks an amount may be given in another currency with (batch 18.3,
# decision 41: "--top:US$20t; C$, US$, £, €; the spelling settled when
# built"): each currency's ISO 4217 code, which is what the program writes,
# and its symbol. The code, since a bare "$" on a command line is a variable
# to PowerShell and bash (--top:US$20t reaches the program as --top:US there);
# the symbols are accepted as typed. Letters in either case.
CURRENCY_MARKS = {
    **{code: code for code in CURRENCY_SYMBOLS},
    "US$": "USD", "C$": "CAD", CURRENCY_SYMBOLS["GBP"]: "GBP", CURRENCY_SYMBOLS["EUR"]: "EUR",
}


def _currency_mark(spec: str) -> tuple[str | None, str]:
    """Split an amount's currency mark off its front: ``"USD20t"`` -> ``("USD", "20t")``; none -> ``(None, spec)``."""
    for mark in sorted(CURRENCY_MARKS, key=len, reverse=True):  # "US$" before a mark it might begin
        if spec.upper().startswith(mark.upper()):
            return CURRENCY_MARKS[mark], spec[len(mark):].strip()
    return None, spec


def parse_macro_bound(spec: str, *, kind: str) -> tuple[float, str | None]:
    """Parse a right-axis bound: an amount, or with a ``%`` sign a percentage (for ``-r``); return it and its currency.

    An amount: ``k/m/b/t`` suffixes scale, unsuffixed means billions, in the
    chart's own currency, or in the one its mark names (``USD20t``,
    ``C$5t``; ``CURRENCY_MARKS``; batch 18.3), returned as its ISO code: the
    chart converts it when it is drawn. A percentage is returned as the
    number of percent (``150%`` -> 150.0), with no currency. Which of the
    two the chart needs is checked in ``config_from_choices``, once ``-r``
    is known.
    """
    value = spec.strip().lower()
    if not value:
        raise ValueError(f"empty {kind} limit")
    currency, value = _currency_mark(value)
    if value.startswith("$"):
        raise ValueError(f"{kind} limit {spec.strip()!r}: say whose dollars, USD{value[1:]} or CAD{value[1:]}")

    if value.endswith("%"):
        if currency is not None:
            raise ValueError(f"{kind} limit {spec.strip()!r}: a percentage of GDP takes no currency")
        try:
            parsed = float(value[:-1].strip())
        except ValueError:
            raise ValueError(f"invalid {kind} percentage {spec!r}: must be a positive decimal value") from None
        if parsed <= 0:
            raise ValueError(f"{kind} percentage must be positive, got {parsed}")
        return parsed, None

    multiplier = _DOLLAR_SUFFIX_MULTIPLIERS.get(value[-1])
    if multiplier is not None:
        value = value[:-1].strip()
    else:
        multiplier = _DEFAULT_DOLLAR_MULTIPLIER

    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(f"invalid {kind} dollar limit {spec!r}: must be a positive decimal value") from None
    if parsed <= 0:
        raise ValueError(f"{kind} dollar limit must be positive, got {parsed}")
    return parsed * multiplier, currency


# ---------------------------------------------------------------------------
# Value formatters: field value(s) -> text the matching parser accepts
# ---------------------------------------------------------------------------
# Used to fill the GUI's text fields from a PlotConfig. Each receives the
# option's field values as a tuple, and the whole config (a right-axis bound
# is a percentage under -r), and returns "" for "not set".


def format_date(values: tuple, _config: PlotConfig) -> str:
    """Format a date field as ``YYYY-MM-DD``; blank for the automatic start (None)."""
    return "" if values[0] is None else f"{values[0]:%Y-%m-%d}"


def format_dimensions(values: tuple, _config: PlotConfig) -> str:
    """Format ``(width_px, height_px)`` as ``WxH``."""
    return f"{values[0]}x{values[1]}"


def format_yield_bound(values: tuple, _config: PlotConfig) -> str:
    """Format a yield bound in percent; blank when unset."""
    return "" if values[0] is None else f"{values[0]:g}"


def format_dollar_bound(values: tuple) -> str:
    """Format a dollar bound with the largest k/m/b/t suffix that keeps it ≥ 1; blank when unset."""
    value = values[0]
    if value is None:
        return ""
    for suffix, multiplier in _DOLLAR_SUFFIX_MULTIPLIERS.items():  # t, b, m, k: largest first
        if value >= multiplier:
            return f"{value / multiplier:g}{suffix}"
    return f"{value / _DOLLAR_SUFFIX_MULTIPLIERS['k']:g}k"


def format_macro_bound(values: tuple, config: PlotConfig) -> str:
    """Format a right-axis bound, ``(amount, currency)``: a percentage under -r, otherwise the amount after its currency's code, if any (``USD20t``); blank when unset."""
    if values[0] is None:
        return ""
    if config.relative:
        return f"{values[0]:g}%"
    currency = values[1] if len(values) > 1 else None
    return (currency or "") + format_dollar_bound(values)


def format_regression_tolerance(values: tuple, _config: PlotConfig) -> str:
    """Format the regression tolerance in percent (the window's label gives the unit); blank when unset."""
    return "" if values[0] is None else f"{values[0]:g}"


def format_auto_refresh_minutes(values: tuple, _config: PlotConfig) -> str:
    """Format the minutes between automatic refreshes; blank when unset (the default, shown in grey)."""
    return "" if values[0] is None else str(values[0])


def field_default(name: str) -> object:
    """Return the default of the PlotConfig field ``name`` (one with a plain default, not a factory)."""
    return next(field.default for field in dataclasses.fields(PlotConfig) if field.name == name)


def format_margin(values: tuple, _config: PlotConfig, *, field: str) -> str:
    """Format a margin (the PlotConfig ``field``) in points; blank at its default (shown in grey)."""
    return "" if values[0] == field_default(field) else f"{values[0]:g}"


# ---------------------------------------------------------------------------
# Checks that involve more than one option
# ---------------------------------------------------------------------------
# Each receives the field values gathered so far (PlotConfig defaults plus
# everything parsed up to this option) and raises ValueError if they conflict.


def check_date_range(values: Mapping[str, object]) -> None:
    """Reject reversed ranges and windows shorter than seven days.

    Without --start there is nothing to check yet: the automatic start is
    found from the data, and always leaves the minimum window
    (``plotting.resolve_start``).
    """
    start, end = values["start"], values["end"]
    if start is None:
        return
    if end < start:
        raise ValueError(f"end date {end.date()} is before start date {start.date()}")
    if (end - start).days < MIN_WINDOW_DAYS:
        raise ValueError(f"end date {end.date()} is less than {MIN_WINDOW_DAYS} days after start date {start.date()}")


def check_yield_bounds(values: Mapping[str, object]) -> None:
    """Require min < max when both yield bounds are given."""
    low, high = values["yield_ymin"], values["yield_ymax"]
    if low is not None and high is not None and low >= high:
        raise ValueError(f"yield min ({low}) must be less than max ({high})")


def check_macro_bounds(values: Mapping[str, object]) -> None:
    """Require bottom < top when both right-axis bounds are given.

    The message gives no numbers: parsed, they are dollars (5e+12 for "5t")
    or percentages, which is known only once the flags are; the fields and
    the command line show what was typed. Two in different currencies are
    compared once converted, when the chart is drawn (``plotting``; batch 18.3).
    """
    top, bottom = values["macro_top"], values["macro_bottom"]
    same_currency = values["macro_top_currency"] == values["macro_bottom_currency"]
    if top is not None and bottom is not None and same_currency and bottom >= top:
        raise ValueError("bottom limit must be less than top limit")


def parse_components(spec: str, *, kind: str) -> str:
    """Parse ``--debt:``/``--interest:`` sub-option letters into ``COMPONENT_LETTERS`` order.

    Any of f, n, p, m in any order and combination; "s" (state) means "p";
    repeats are harmless. ``kind`` names the option in messages.
    """
    value = spec.strip().lower()
    if not value:
        raise ValueError(f"empty --{kind} sub-options: use letters from f, n, p (or s), m")
    unknown = sorted(set(value) - set(COMPONENT_LETTERS) - set(COMPONENT_SYNONYMS))
    if unknown:
        # A size written the old way ("--d:1100", "--d:x600") gets pointed at --dim.
        hint = "; the canvas size is --dim:WxH" if kind == "debt" and re.match(r"x?\d", value) else ""
        raise ValueError(
            f"invalid --{kind} sub-option {spec!r}: use letters f federal, n non-federal, "
            f"p or s provincial/state, m municipal{hint}"
        )
    letters = {COMPONENT_SYNONYMS.get(letter, letter) for letter in value}
    return "".join(letter for letter in COMPONENT_LETTERS if letter in letters)


def format_components(values: tuple, _config: PlotConfig) -> str:
    """Format the component letters (already in canonical order); blank for the aggregates."""
    return values[0]


def check_single_measure(values: Mapping[str, object]) -> None:
    """Reject -r with -p: a curve is either a share of GDP or an amount per person."""
    if values["relative"] and values["per_capita"]:
        raise ValueError("-r (% of GDP) and -p (per capita) cannot be combined; choose one")


def check_macro_bound_units(payloads: Mapping[str, str], values: Mapping[str, object]) -> None:
    """Require right-axis bounds as percentages under -r, and in dollars otherwise.

    Run once the flags are known: the same text means different things in
    the two measures, so it is rejected rather than reinterpreted. Not with
    no right-axis curve, where the bounds change nothing (``idle_options``):
    -r has no effect then either, and its percentages were valid before -r
    lost its effect there (2026-10-13).
    """
    if "top" in idle_options(values["include_debt"], values["include_gdp"], values["include_interest"]):
        return
    for name in ("top", "bottom"):
        if name not in payloads:
            continue
        spec = payloads[name].strip()
        if values["relative"] and not is_percent_bound(spec):
            raise ValueError(f"with -r the --{name} limit is a percentage of GDP, e.g. --{name}:150%")
        if not values["relative"] and is_percent_bound(spec):
            raise ValueError(f"--{name}:{spec} is a percentage, which needs -r with debt or interest (as % of GDP)")


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


class Kind(Enum):
    FLAG = "flag"      # on/off with a "no-" form, sets its field directly (--cur, --reg, --gui)
    VALUE = "value"    # KEY:VALUE
    TOGGLE = "toggle"  # curve on/off with a "no-" form, under the curve rule
    SWITCH = "switch"  # on only; also an argparse store_true flag (``flag``), for usage and --help


@dataclass(frozen=True)
class Option:
    """One command-line option. See the module docstring for how a token is matched."""

    name: str  # canonical name, used by the GUI and in messages
    kind: Kind
    fields: tuple[str, ...]  # PlotConfig field(s) the option sets
    group: str  # key into GROUPS, for the help listing
    usage: str  # left-hand column of the help listing: the spellings
    help: str  # right-hand column; "\n" starts a continuation line
    names: tuple[str, ...] = ()  # lower case; any leading part of one spells the option
    shortest: int = 1  # the fewest letters a spelling may have
    parse: Callable[[str], object] | None = None  # VALUE: payload -> value (a tuple if several fields)
    check: Callable[[Mapping[str, object]], None] | None = None  # VALUE: run after this option is parsed
    turns_on: str | None = None  # VALUE: the FLAG option that giving this value turns on (--reg:TOL is --reg)
    # VALUE: spelled after "no-" (--no-yields:LIST); its list is taken out of
    # its field (the default, or what the option before it in the table gave).
    removes: bool = False
    flag: str | None = None  # SWITCH: the argparse flag
    # False: not on the command line at all (no spelling matches it, no
    # argparse flag, not in --help); the window and the page still show its
    # control. The nations other than Canada and the U.S. (Terry, 2026-10-07:
    # "--usa and --canada ... are allowed as base-level CLI switches ...
    # other national base-level CLI options (such as --uk, --ger, --deu, etc.)
    # should not be allowed"): those are chosen with --nations:LIST only.
    command_line: bool = True
    flag_help: str | None = None  # SWITCH: argparse's own one-line help
    # GUI. ``label`` is the caption beside the control. ``format`` turns the
    # field value(s) back into text a parser accepts, given the rest of the
    # config (VALUE only). Options with ``in_gui=False`` get no control: they
    # choose the interface rather than shape the chart.
    label: str = ""
    format: Callable[[tuple, PlotConfig], str] | None = None
    in_gui: bool = True
    # GUI editor for a VALUE option: None = a plain text field; "date" = text
    # field plus calendar button; "size" = width and height boxes with an
    # aspect-ratio lock (for a "WxH" option such as the canvas size);
    # "choices" = a tick box per item of a list (``choices``).
    editor: str | None = None
    # GUI editor "choices": the tick boxes offered, in rows, each row a caption
    # ("" for none) and its (value, box caption) pairs. The values are the
    # items of the option's list as ``format`` writes them ("10y", "5v",
    # "10y-2y"); a value given on the command line that is not offered gets a
    # box of its own (``frontend.choice_rows``). Terry, 2026-10-06: tick boxes
    # show what can be chosen.
    choices: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    # GUI: the block of the control column the control is shown in (a key of
    # ``frontend.CONTROL_BLOCKS``), when not its help group's. --help keeps
    # its sections; the window and the page arrange the blocks as Terry
    # asked on 2026-10-08 (batch 7): the yields, spreads, policy rate and
    # mortgages ticked in one block, the regression segments in a block of
    # their own under the measure, the latest data with the line labels.
    panel: str | None = None


# The tick boxes of the list options (Option.choices). Yield terms: the five
# drawn by default, then the others in term order (each nation's panel offers
# those it has: Canada all but the 20-year since batch 9.3, the U.S. all but
# the 3-year). Mortgage terms by country. Spreads: the usual pairs (the defaults first); any other pair
# named on the command line gets a box of its own.
_YIELD_CHOICES = (
    ("", tuple((term, term) for term in DEFAULT_YIELD_TERMS)),
    ("more", tuple((term, term) for term in YIELD_TERMS if term not in DEFAULT_YIELD_TERMS)),
)
_MORTGAGE_CHOICES = (
    ("U.S.", (("30", "30y"), ("15", "15y"))),
    ("Canada", (("5", "5y"), ("3", "3y"), ("1", "1y"), ("5v", "5y var."))),
    # Both nations' (batch 9.4), on a row of its own so that each nation's
    # panel has its box once, with the margin's field beside it.
    ("Canada and U.S.", (("prime", "prime"),)),
    # Without "fixed", as the legends are (batch 10.1).
    ("UK", (("2f", "2y"), ("3f", "3y"), ("5f", "5y"), ("svr", "SVR"))),
    # On a row of its own, as the prime rate is, with its margin's field (batch 9.5).
    ("UK, plus a margin", (("tracker", "tracker"),)),
    ("Germany", (("1-5", "1–5y"), ("5-10", "5–10y"), ("over10", "over 10y"))),
)
# Every nation has both policy terms (batch 9.1).
_POLICY_CHOICES = (("", tuple((term, term) for term in POLICY_TERMS)),)
_SPREAD_CHOICES = (
    ("", tuple((f"{a}-{b}", f"{a}–{b}") for a, b in DEFAULT_SPREADS)),
    ("", tuple((f"{a}-{b}", f"{a}–{b}") for a, b in (("2y", "3m"), ("5y", "2y"), ("30y", "2y")))),
    # The UK has only the 5-, 10- and 20-year (batch 3); the U.S. has them too.
    ("", tuple((f"{a}-{b}", f"{a}–{b}") for a, b in (("10y", "5y"), ("20y", "10y"), ("20y", "5y")))),
)
# The aggregate debts (batch 10.4), one to a row: only the UK's panel shows
# them, the only nation with two (Terry, 2026-10-13: "a pair of tick boxes").
_AGGREGATE_CHOICES = (
    ("", (("gross", "Gross (general government)"),)),
    ("", (("net", "Net (public sector, ex banks)"),)),
)

# Help-listing sections, in display order: key -> heading (and any notes).
# The GUI titles its panels with the heading up to the first " (" or ":".
GROUPS: dict[str, str] = {
    "country": "Country selection:",
    "curves": (
        "Curve selection (naming any curve positively shows *only* the named curves;\n"
        "``--no-`` forms hide curves from the default set of all four):"
    ),
    "rates": (
        'Rates on the yield axis (policy, mortgages, spreads; each only when asked\n'
        'for, hiding nothing; at least "po", "mo", "sp"):'
    ),
    "units": "Measure of debt, GDP, and interest:",
    "labels": "Line labels and regression segments (--reg needs at least \"reg\"):",
    "dates": "Date window (YYYY, YYYY-MM or YYYY-MM-DD; '/' also accepted):",
    "latest": "Latest data (at least \"cur\"; --auto-refresh \"au\"):",
    "canvas": "Final canvas size in pixels (4:3 assumed when only one dimension is given):",
    "yield": "Yield-axis limits (percent):",
    "dollar": (
        "Right-axis limits (suffixes k/m/b/t; unsuffixed values are billions;\n"
        "with -r, percentages such as 150%):"
    ),
    "interface": 'Interface (--gui spelled in full; --save at least "sa", --hover "ho"):',
}

OPTIONS: tuple[Option, ...] = (
    # Country selection: argparse store_true flags; no flag at all means both.
    Option(
        "cdn", Kind.SWITCH, ("show_cdn",), "country", "--C / -C / --canada / --cdn", "Canadian chart only",
        names=("canada", "cdn"), flag="--C", flag_help="Canadian chart only", label="Canada",
    ),
    Option(
        "us", Kind.SWITCH, ("show_us",), "country", "--U / -U / --us / --usa", "U.S. chart only",
        names=("us", "usa"), flag="--U", flag_help="U.S. chart only", label="United States",
    ),
    # The other nations (batch 3 the UK, batch 4 Germany): drawn only when
    # named, and named only by --nations:LIST (Terry, 2026-10-07; batch 3 had
    # --uk / --gb, batch 4's draft --ger). Switches still, so the window and
    # the page have a tick box for each; ``command_line=False`` keeps them off
    # the command line, which writes them as --nations:LIST
    # (``command_line_tokens``). Their names are kept for that tick box's
    # key and for messages; ``switch_of`` relates a nation to its switch.
    Option(
        "uk", Kind.SWITCH, ("show_uk",), "country", "--nations:gb",
        "the UK's chart (only when named; with\n-c or -u, those too)",
        names=("uk", "gb"), shortest=2, label="United Kingdom", command_line=False,
    ),
    Option(
        "germany", Kind.SWITCH, ("show_de",), "country", "--nations:de",
        "Germany's chart (only when named; with\n-c or -u, those too)",
        names=("germany",), shortest=3, label="Germany", command_line=False,
    ),
    # The same by the nations' codes, for when there are more than two
    # (batch 2). The command line turns it into the switches of the nations it
    # names (``cli.sort_tokens``), so it sets no field of its own and has no
    # control: the window and the page show the switches.
    Option(
        "nations", Kind.VALUE, (), "country", "--nations:LIST / --na:LIST",
        "the charts of these nations only, by\ncode: ca or cdn, us, gb or uk, de, ger\nor deu (--nations:ca,us,gb,de); the only\nway to name the UK's and Germany's",
        names=("nations",), shortest=2, parse=parse_nations, in_gui=False,
    ),
    # Curves. The listing order here is the help order; the selection rule is
    # in ``config_from_choices``.
    Option(
        "gdp", Kind.TOGGLE, ("include_gdp",), "curves", "--GDP / --no-GDP", "TTM nominal GDP",
        names=("gdp",), label="TTM nominal GDP",
    ),
    Option(
        "debt", Kind.TOGGLE, ("include_debt",), "curves", "--debt / --no-debt", "aggregate public debt",
        names=("debt",), label="Aggregate public debt",
    ),
    Option(
        "interest", Kind.TOGGLE, ("include_interest",), "curves", "--interest / --no-interest", "TTM interest outlays",
        names=("interest",), label="TTM interest outlays",
    ),
    # Curve sub-options: debt and interest by level of government ("--d:" is
    # debt; the size needs at least "dim"). They set one field; see
    # ``config_from_choices`` for how they name their curves. Per nation
    # since batch 10.5 (--cdn:debt:fp): the window and the page have one
    # control for both in each nation's panel, its boxes named for its
    # governments (``Nation.level_boxes``; Terry, 2026-10-13); until then one
    # in the column for every chart, under the debt and interest boxes.
    Option(
        "debt-parts", Kind.VALUE, ("components",), "curves", "--debt:LETTERS / --d:LETTERS",
        "debt and interest by level instead of\nin total: f federal, n non-federal,\n"
        "p or s provincial/state, m municipal;\nthe UK's f central, m (or n) local",
        names=("debt",), parse=partial(parse_components, kind="debt"),
        label="By level", format=format_components, editor="levels",
    ),
    Option(
        "interest-parts", Kind.VALUE, ("components",), "curves", "--interest:LETTERS / --i:LETTERS",
        "the same letters; given on both --debt\nand --interest they must agree",
        names=("interest",), parse=partial(parse_components, kind="interest"), in_gui=False,
    ),
    # The aggregate debts (batch 10.4, decision 33): gross, and the UK's net
    # too; gross alone by default. The debt curve's lines, as the yield terms
    # are the yield curve's: the list names no curve under the curve rule, and
    # --no-debt hides whichever are chosen. Per nation (--uk:aggregate:net); a
    # nation with gross debt alone draws it whatever the list names
    # (``Nation.view``). At least "agg", as the plan has it.
    Option(
        "aggregate", Kind.VALUE, ("debt_aggregates",), "curves", "--aggregate:LIST / --agg:LIST",
        "the aggregate debt drawn: gross (general\ngovernment, the default), net (the UK's\n"
        "public sector net debt, ex banks), or\nboth; only the UK has net debt (the\nothers draw their gross debt)",
        names=("aggregate",), shortest=3, parse=parse_debt_aggregates, label="Aggregate debts", format=format_terms,
        editor="choices", choices=_AGGREGATE_CHOICES,
    ),
    Option(
        "yield", Kind.TOGGLE, ("include_yield",), "curves", "--yield / --no-yield", "bond yields",
        names=("yield", "yields"), label="Bond yields", panel="rates",
    ),
    # The yield terms (config.YIELD_TERMS): named, or dropped from the default
    # five. They choose which yield lines the curve draws; they do not name a
    # curve under the curve rule, so the other curves stay. The window has the
    # one field; --no-yields:LIST is a command-line convenience (Terry,
    # 2026-10-06: drop a few defaults rather than list all the wanted ones).
    Option(
        "yields", Kind.VALUE, ("yield_terms",), "curves", "--yields:LIST / --y:LIST",
        "the yield terms drawn: 1m 3m 6m 1 2 3 5\n7 10 20 30 (years unless m; default\n"
        f"{','.join(DEFAULT_YIELD_TERMS)}); Canada has all but 20\n(1m 6m 1 3 7 from 2001), the U.S. all but\n3, "
        "the UK 5 10 20 (its default),\nGermany 1 2 5 7 10 20 30 (its default\n2 5 10 30)",
        names=("yields",), parse=partial(parse_terms, kind="--yields"), label="Yield terms", format=format_terms,
        editor="choices", choices=_YIELD_CHOICES,
    ),
    Option(
        "no-yields", Kind.VALUE, ("yield_terms",), "curves", "--no-yields:LIST / --no-y:LIST",
        "drop these terms from the default five\n(or from --yields:LIST)",
        names=("yields",), parse=partial(parse_terms, kind="--no-yields"), removes=True, in_gui=False,
    ),
    # The yield axis's other curves (ratesplot.rates). Flags, not curves under
    # the curve rule: each adds its curve and hides nothing. At least "po", so
    # "-p" stays per capita.
    Option(
        "policy", Kind.FLAG, ("policy_rates",), "rates", "--policy / --no-policy",
        "each country's policy rate, the central\nbank's official rate: the fed funds\n"
        "target (a range from 2008, the monthly\naverage before 1982-09); the Bank Rate,\n"
        "the overnight target from 1996; the UK's\nBank Rate; Germany's: the Bundesbank's\ndiscount rate, the ECB's main\nrefinancing rate from 1999",
        names=("policy-rates",), shortest=2, label="Policy rate",
    ),
    # Batch 9.1 (Terry, decision 27): the official rate by default, the
    # market's overnight rate a second term. Per nation (--us:policy:market).
    Option(
        "policy-terms", Kind.VALUE, ("policy_terms",), "rates", "--policy:LIST / --po:LIST",
        "target (the official rate, the default),\nmarket (the overnight market's rate: the\n"
        "effective fed funds rate, CORRA from\n1997, SONIA from 1997, EONIA from 1999\nthen €STR), or both; turns --policy on",
        names=("policy-rates",), shortest=2, parse=parse_policy_terms, turns_on="policy",
        label="Policy rates", format=format_terms, editor="choices", choices=_POLICY_CHOICES,
    ),
    # At least "mo": "--m:" stays ambiguous (--min or --max).
    Option(
        "mortgages", Kind.FLAG, ("mortgages",), "rates", "--mortgages / --no-mortgages",
        "mortgage rates, dashed in the colour of\nthe yield of their term: U.S. survey\n"
        "averages; Canadian posted rates; UK\nquoted rates; German averages of new\nloans",
        names=("mortgages",), shortest=2, label="Mortgage rates",
    ),
    Option(
        "mortgage-terms", Kind.VALUE, ("mortgage_terms",), "rates", "--mortgages:LIST / --mo:LIST",
        "the terms: 30 15 (U.S.), 5 3 1 5v\n(Canada; 5v variable, broker average),\nprime (Canada and the U.S.: the banks'\nprime rate),\n"
        "2f 3f 5f svr tracker (UK: fixed 2, 3, 5\nyears; svr the standard variable rate,\nquoted from 1995, the millennium\n"
        "dataset's variable mortgage rate from\n1939; tracker Bank Rate plus a margin,\nfrom 1997),\n"
        "1-5 5-10 over10 (Germany: fixed over 1\nto 5, over 5 to 10, over 10 years);\n"
        f"default {','.join(DEFAULT_MORTGAGE_TERMS)} (the UK's and Germany's: all\ntheir terms); turns --mortgages on",
        names=("mortgages",), shortest=2, parse=parse_mortgage_terms, turns_on="mortgages",
        label="Mortgage terms", format=format_terms, editor="choices", choices=_MORTGAGE_CHOICES,
    ),
    # Batch 9.4 (Terry, 2026-10-08, decision 20): a Canadian "prime" mortgage
    # is more often prime plus a margin, so a margin for the prime term, shown
    # in the legend; the U.S. prime rate with the same box. Per nation
    # (--cdn:prime:-0.25). At least "pr": "--p" is per capita, "--po" the
    # policy rate. Giving it turns --mortgages on (``turns_on``) and adds the
    # prime term, unless a list of terms is given (``config_from_choices``).
    # Not "--mo:prime+0.5": a "+" in the web page's address reads as a space.
    Option(
        "prime-margin", Kind.VALUE, ("prime_margin",), "rates", "--prime:MARGIN / --pr:MARGIN",
        "the prime rate plus MARGIN points\n(negative allowed; default 0), as in\n\"Prime Rate + 0.50\"; turns --mortgages\n"
        "and the prime term on, unless a list\nof terms is given",
        names=("prime",), shortest=2, parse=parse_prime_margin, turns_on="mortgages",
        label="Prime margin (points)", format=partial(format_margin, field="prime_margin"),
    ),
    # Batch 9.5 (Terry, 2026-10-13, decision 26): the UK tracker, Bank Rate
    # plus a margin, by default 1.75 points (config.DEFAULT_TRACKER_MARGIN).
    # Per nation (--uk:tracker:2); only the UK has a tracker. At least "tr":
    # "--t:" stays the right axis's Top. The tracker is in the UK's own
    # default list, so with no list given its margin needs to name nothing;
    # with a list given, the list says whether it is drawn.
    Option(
        "tracker-margin", Kind.VALUE, ("tracker_margin",), "rates", "--tracker:MARGIN / --tr:MARGIN",
        "the UK's tracker mortgage: Bank Rate\nplus MARGIN points (negative allowed;\n"
        f"default {DEFAULT_TRACKER_MARGIN:g}), from 1997; turns --mortgages on",
        names=("tracker",), shortest=2, parse=parse_tracker_margin, turns_on="mortgages",
        label="Tracker margin (points)", format=partial(format_margin, field="tracker_margin"),
    ),
    # At least "sp": "--s:" stays the start date.
    Option(
        "spreads", Kind.FLAG, ("spreads",), "rates", "--spreads / --no-spreads",
        "yield spreads in percentage points, drawn\nthick, their inverted stretches shaded",
        names=("spreads",), shortest=2, label="Yield spreads", panel="rates",
    ),
    Option(
        "spread-pairs", Kind.VALUE, ("spread_pairs",), "rates", "--spreads:LIST / --sp:LIST",
        "pairs of yield terms, the first less the\nsecond (default "
        f"{format_spreads((DEFAULT_SPREADS,), PlotConfig())};\nthe UK's: 10y-5y,20y-10y; Germany's:\n10y-2y,30y-10y); turns --spreads on",
        names=("spreads",), shortest=2, parse=parse_spreads, turns_on="spreads",
        label="Spreads", format=format_spreads, editor="choices", choices=_SPREAD_CHOICES, panel="rates",
    ),
    # Measure of the right-axis curves: argparse store_true flags, like the
    # countries.
    Option(
        "relative", Kind.SWITCH, ("relative",), "units", "--R / -r / --relative",
        "debt and interest as % of TTM GDP (log\npercent axis); GDP itself is not drawn;\nno effect without debt or interest",
        names=("relative",), flag="--R", flag_help="debt and interest as a percentage of GDP", label="As % of GDP",
    ),
    Option(
        "per-capita", Kind.SWITCH, ("per_capita",), "units", "--P / -p / --per-capita",
        "GDP, debt and interest per person (log\ndollar axis); not with -r",
        names=("per-capita",), flag="--P", flag_help="GDP, debt and interest per person", label="Per capita",
    ),
    # Value labels at the line ends: a switch like the measures, but in a
    # group of its own, since it combines with either. The tick's wording is
    # Terry's (2026-10-13, batch 15.1); --help keeps its own.
    Option(
        "label", Kind.SWITCH, ("end_labels",), "labels", "--L / -l / --label",
        "each line's last value at its end, in\nthe line's colour; the date axis is\nwidened to make room",
        names=("label", "labels"), flag="--L", flag_help="label each line's end with its last value",
        label="Show latest value for each line",
    ),
    # Regression segments on the right-axis curves (ratesplot.regression), in
    # the same group, so the window keeps one panel for both. At least "reg",
    # so it is never -r: "-r", "--re" and "--rel" are --relative.
    Option(
        "regression", Kind.FLAG, ("regression",), "labels", "--reg / --regression / --no-reg",
        "each right-axis curve fitted by the fewest\nstraight pieces on its log axis, each\n"
        "labelled with its growth in %/yr:\ncompounded on a piece of a year or more,\n"
        "the log slope on a shorter one",
        names=("regression",), shortest=3, label="Regression segments", panel="regression",
    ),
    # Its tolerance. Giving it turns --reg on, as --debt:LETTERS names the
    # debt curve (``config_from_choices``); in the window the field is greyed
    # while --reg is off.
    Option(
        "regression-tolerance", Kind.VALUE, ("regression_tolerance",), "labels", "--reg:TOL / --regression:TOL",
        "how far a piece may stray from the\ncurve's points, in % of the axis height\n"
        f"(default {DEFAULT_REGRESSION_TOLERANCE_PCT:g}; never less than {MIN_REGRESSION_TOLERANCE_PCT:g} % of the\n"
        "value); turns --reg on",
        names=("regression",), shortest=3, parse=parse_regression_tolerance, turns_on="regression",
        label="tolerance, % of axis", format=format_regression_tolerance, panel="regression",
    ),
    # Values. Table order is parse order, so it decides which error is reported
    # first when several values are bad; each ``check`` runs once both of its
    # fields are known.
    Option(
        "dimensions", Kind.VALUE, ("width_px", "height_px"), "canvas", "--dimensions:WxH / --dim:W / --dim:xH",
        f"(minimum {MIN_CANVAS_PX} px each way)", names=("dimensions",), shortest=3, parse=parse_dimensions_spec,
        label="Size", format=format_dimensions, editor="size",
    ),
    Option(
        "start", Kind.VALUE, ("start",), "dates", "--start:DATE / --s:DATE",
        _START_HELP,
        names=("start",), parse=partial(parse_date_spec, kind="start"), label="Start", format=format_date,
        editor="date",
    ),
    Option(
        "end", Kind.VALUE, ("end",), "dates", "--end:DATE / --e:DATE", "last date (default today)",
        names=("end",), parse=partial(parse_date_spec, kind="end"), check=check_date_range,
        label="End", format=format_date, editor="date",
    ),
    # "--m:" could be either, so it is refused as ambiguous. The labels have
    # no "%" since batch 18.1: the window and the page show it right of the
    # box (``frontend.limit_unit``; Terry, 2026-10-14).
    Option(
        "min", Kind.VALUE, ("yield_ymin",), "yield", "--min:VAL / --mn:VAL", "lower bound",
        names=("minimum", "mn"), parse=partial(parse_yield_bound, kind="min"), label="Min", format=format_yield_bound,
    ),
    Option(
        "max", Kind.VALUE, ("yield_ymax",), "yield", "--max:VAL / --mx:VAL", "upper bound",
        names=("maximum", "mx"), parse=partial(parse_yield_bound, kind="max"), check=check_yield_bounds,
        label="Max", format=format_yield_bound,
    ),
    # Batch 18.3 (decision 41): an amount may name its currency, converted
    # at the rate of the chart's end date when each chart is drawn.
    Option(
        "top", Kind.VALUE, ("macro_top", "macro_top_currency"), "dollar", "--top:VAL / --t:VAL",
        "upper bound; in another currency with\nits code first (USD20t; CAD, GBP, EUR, or\nUS$ C$ £ €), converted at the rate of\n"
        "the chart's end date",
        names=("top",), parse=partial(parse_macro_bound, kind="top"), label="Top", format=format_macro_bound,
    ),
    Option(
        "bottom", Kind.VALUE, ("macro_bottom", "macro_bottom_currency"), "dollar", "--bottom:VAL / --b:VAL", "lower bound, likewise",
        names=("bottom",), parse=partial(parse_macro_bound, kind="bottom"), check=check_macro_bounds,
        label="Bottom", format=format_macro_bound,
    ),
    # The latest values (ratesplot.latest), on by default. At least "cur", so
    # it is never Canada ("-c", "--ca", "--cdn"). The tick's wording is
    # Terry's (2026-10-14, batch 15.1): it was "Latest values, with intraday
    # quotes", which read like the -l tick above it once that said "latest".
    Option(
        "current", Kind.FLAG, ("current",), "latest", "--cur / --current / --no-cur",
        "on by default: U.S. Treasury daily yields\nand debt, and the day's intraday yield\n"
        "quotes (CNBC), past the regular sources",
        names=("current",), shortest=3, label="Intraday quotes on end date", panel="labels",
    ),
    # The automatic refresh (batch 11.3, ratesplot.refresh; Terry, 2026-10-08
    # and 2026-10-12), off by default. At least "au": no other name begins so.
    # Greyed in the window and on the page where it can bring nothing new
    # (``PlotConfig.refresh_brings_nothing``); its box, with the minutes on its row,
    # in the block with the line labels and the latest data.
    Option(
        "auto-refresh", Kind.FLAG, ("auto_refresh",), "latest", "--au / --auto-refresh / --no-au",
        f"off by default: every {DEFAULT_AUTO_REFRESH_MINUTES} minutes what\n"
        "Refresh does; outside market hours only\nwhen a quote has changed. With --save the\nfiles are written again until Ctrl-C",
        names=("auto-refresh",), shortest=2, label="Automatic refresh", panel="labels",
    ),
    Option(
        "auto-refresh-minutes", Kind.VALUE, ("auto_refresh_minutes",), "latest", "--au:MIN / --auto-refresh:MIN",
        f"the minutes between refreshes (default {DEFAULT_AUTO_REFRESH_MINUTES},\n"
        f"at least {MIN_AUTO_REFRESH_MINUTES}); turns --au on",
        names=("auto-refresh",), shortest=2, parse=parse_auto_refresh_minutes, turns_on="auto-refresh",
        label="interval, minutes", format=format_auto_refresh_minutes, panel="labels",
    ),
    # The projection to today (ratesplot.latest.project_to_now), on by
    # default, a switch of its own since batch 11 (Terry, 2026-10-26, decision
    # 68: "there is not currently a tick-box to turn off projections";
    # 2026-10-27, decision 72: no connection with --cur). At least "pro":
    # "pr" is shared with --prime-margin.
    Option(
        "projections", Kind.FLAG, ("projections",), "latest", "--pro / --projections / --no-pro",
        "on by default: each right-axis curve\ncarried from its last value to today at\nits past year's pace, drawn faint",
        names=("projections",), shortest=3, label="Projections to today", panel="labels",
    ),
    # The hover read-out (batch 11.2, ratesplot.hover), on by default with a
    # box and a switch of its own (Terry, 2026-10-26, decision 68: "a tick-box
    # to turn off the hover read-out ..., as some people won't like it"). At
    # least "ho": "--h" is argparse's --help. Its box is in the block with the
    # line labels; --help lists it with the interface.
    Option(
        "hover", Kind.FLAG, ("hover",), "interface", "--ho / --hover / --no-ho",
        "on by default: the pointer resting on a\nline shows its name, date and value",
        names=("hover",), shortest=2, label="Hover read-out", panel="labels",
    ),
    # Interface. Spelled in full (Terry, 2026-09-24): "--g" is the GDP curve,
    # and "--gu" nothing.
    Option(
        "gui", Kind.FLAG, ("gui",), "interface", "--gui / --no-gui",
        "interactive window (default); --no-gui\ndraws plain matplotlib windows instead",
        names=("gui",), shortest=3, in_gui=False,
    ),
    # Export chart from the command line (batch 11.1, decision 46): the
    # charts written to a file, the format by its extension, and no window.
    # At least "sa": "--s:" is the start.
    Option(
        "save", Kind.VALUE, ("save",), "interface", "--save:FILE / --sa:FILE",
        "write the charts to FILE, open no window:\nan image (.png .jpg .pdf .svg) or the data\n"
        "(.csv .tsv) a file per chart, named with\nits nation's code (rates_ca.png ...); .xlsx\n"
        "one workbook, a sheet per chart",
        names=("save",), shortest=2, parse=parse_save_file, in_gui=False,
    ),
    # The version (batch 11.7), printed, nothing drawn. In the table, not
    # argparse's own, so it is spelled as the others are: at least "ver" (no
    # other name begins so), never "--v".
    Option(
        "version", Kind.FLAG, ("version",), "interface", "--ver / --version",
        "print the program's version and the commit\nit is at, and exit",
        names=("version",), shortest=3, in_gui=False,
    ),
    # Baking the historical data into the code is not an option of the program:
    # it is a maintenance step run from tools/bake_archives.py when an
    # extraction changes (Terry, 2026-09-27).
)


def options_of(kind: Kind) -> list[Option]:
    """Return the options of one kind, in table order."""
    return [option for option in OPTIONS if option.kind is kind]


def options_in(group: str) -> list[Option]:
    """Return the options of one help group (a key of ``GROUPS``), in table order."""
    return [option for option in OPTIONS if option.group == group]


# Groups whose options are chosen together: naming one curve on the command
# line means "only the named curves", naming one country "only the named
# countries", and a measure is one choice however many switches offer it (see
# ``config_from_choices``). So the GUI lets the command line override its
# remembered choices a whole group at a time.
GROUPS_CHOSEN_TOGETHER = ("curves", "country", "units")


def by_name(name: str) -> Option:
    """Return the option called ``name``."""
    for option in OPTIONS:
        if option.name == name:
            return option
    raise KeyError(name)


def per_nation(option: Option) -> bool:
    """True for a value option a nation's code may be put in front of (``--us:top:20t``)."""
    return option.kind is Kind.VALUE and bool(option.fields) and set(option.fields) <= set(PER_NATION_FIELDS)


def nation_choice(nation: Nation, option: Option) -> str:
    """Return the key a nation's own value of ``option`` is kept under in the payloads ("us:top")."""
    return f"{nation.key}:{option.name}"


def group_title(group: str) -> str:
    """Return a group's short title: its help heading up to the first " (" or ":"."""
    return GROUPS[group].split(" (")[0].split(":")[0]


def _letters(text: str) -> str:
    """Return ``text`` without hyphens or underscores, which may be left out of a name."""
    return text.replace("-", "").replace("_", "")


def spells(option: Option, word: str) -> bool:
    """True when ``word`` (lower case) is a leading part of one of the option's names.

    It must have at least ``option.shortest`` letters. ``per``, ``percap``
    and ``per_capita`` all spell ``per-capita``; ``pizza`` spells nothing.
    """
    letters = _letters(word)
    return len(letters) >= option.shortest and any(_letters(name).startswith(letters) for name in option.names)


# ---------------------------------------------------------------------------
# Choices <-> PlotConfig (shared by the command line and the GUI)
# ---------------------------------------------------------------------------

# The curve sub-options and the curve each belongs to (and is written as).
_PART_OPTIONS = {"debt-parts": "debt", "interest-parts": "interest"}
# "Choices" are what a user expressed, keyed by option name:
#   payloads: VALUE option -> its text (absent = not given, so the default)
#   flags:    FLAG / TOGGLE / SWITCH option -> True or False (absent = not given)
# The fields holding a list of items (terms, pairs, debts), which a nation's
# chart draws as far as it has them (``nation_view``) and which may be none
# (the aggregate debts never: ``parse_debt_aggregates``).
_LIST_FIELDS = ("yield_terms", "mortgage_terms", "spread_pairs", "policy_terms", "debt_aggregates")


def list_switch(option: Option) -> Option:
    """Return the switch that draws a list's curves: the flag the list turns on (--mortgages); for the yield terms the yield curve, for the aggregate debts the debt curve."""
    if option.fields == ("debt_aggregates",):
        return by_name("debt")
    return by_name(option.turns_on or "yield")


def _removed(option: Option, spec: str, current: tuple) -> tuple:
    """Return ``current`` without the items ``spec`` names (``option.removes``); raise if it names none, one is not there or none is left."""
    dropped = option.parse(spec)
    spelling = option.usage.split(":")[0]
    if not dropped:
        raise ValueError(f"{spelling}:{spec.strip()} drops nothing; name the terms to drop, such as 30")
    absent = [item for item in dropped if item not in current]
    if absent:
        raise ValueError(f"{spelling}:{spec.strip()}: {','.join(absent)} is not drawn anyway (drawn: {','.join(current)})")
    left = tuple(item for item in current if item not in dropped)
    if not left:
        raise ValueError(f"{spelling}:{spec.strip()} drops every term; to hide the yield curves use --no-yield")
    return left


def _check_nation_terms(nation: Nation, field: str, values: Mapping[str, object]) -> None:
    """Reject a nation's own terms in ``field`` that its chart cannot draw (a yield or mortgage term it lacks, net debt, a level)."""
    if field == "components":
        lacking = [letter for letter in values[field] if letter not in nation.level_letters]
        if lacking:
            # As the boxes name them: "Länder" keeps its capital.
            levels = ", ".join(f"{letter} {caption}" for letter, caption in nation.level_boxes)
            raise ValueError(f"{nation.name} has no level {lacking[0]} (its levels: {levels})")
        return
    if field == "debt_aggregates":
        foreign = [item for item in values[field] if item not in nation.debt_aggregates]
        if foreign:
            raise ValueError(f"{nation.name} has no {foreign[0]} debt (its aggregate debt: {','.join(nation.debt_aggregates)})")
        return
    if field == "mortgage_terms":
        foreign = [term for term in values[field] if term not in nation.mortgage_terms]
        if foreign:
            raise ValueError(
                f"{foreign[0]} is not a mortgage term of {nation.name} (its terms: {','.join(nation.mortgage_terms)})"
            )
        return
    terms = values[field] if field == "yield_terms" else [term for pair in values[field] for term in pair]
    lacking = [term for term in terms if term not in nation.yield_terms]
    if lacking:
        raise ValueError(f"{nation.name} has no {lacking[0]} yield (its terms: {','.join(nation.yield_terms)})")


def margin_options() -> dict[str, Option]:
    """Return the options of the mortgage terms drawn plus a margin (``config.MORTGAGE_MARGINS``): term -> option ("prime" -> --prime:MARGIN)."""
    return {term: next(option for option in OPTIONS if option.fields == (field,)) for term, field in MORTGAGE_MARGINS.items()}


# What a nation without a margin's term lacks, for the message refusing its
# margin ("--uk:prime:0.5").
_MARGIN_TERM_LACKED = {
    "prime": "no prime rate (the prime term is Canada's and the U.S.')",
    "tracker": "no tracker mortgage (the tracker term is the UK's)",
}


def _with_term(terms: tuple[str, ...], added: str) -> tuple[str, ...]:
    """Return mortgage terms with ``added`` among them, in MORTGAGE_TERMS order."""
    return tuple(term for term in MORTGAGE_TERMS if term in terms or term == added)


def idle_margins(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the keys of the nations' margins that change nothing ("cdn:prime-margin"): their charts draw no such term.

    A margin (``margin_options``: the prime rate's) is idle while the
    mortgages are off, or while its term is not among the nation's mortgage
    terms (its own list, else the list for every chart, else the default),
    as for a nation that has no such term (the UK and Germany have no prime
    rate). The window and the page grey such a field, keeping its text,
    and the written command line leaves it out: written, ``--cdn:prime:0.5``
    would add the prime term to Canada's chart (``config_from_choices``).
    """
    terms = by_name("mortgage-terms")
    idle = set()
    for nation in NATIONS:
        text = payloads.get(nation_choice(nation, terms), "").strip() or payloads.get(terms.name, "").strip()
        try:
            chosen = terms.parse(text) if text else DEFAULT_MORTGAGE_TERMS
        except ValueError:
            chosen = ()
        for term, margin in margin_options().items():
            if not flags.get(terms.turns_on, False) or term not in nation.view("mortgage_terms", chosen):
                idle.add(nation_choice(nation, margin))
    return frozenset(idle)


def idle_aggregates(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the keys of the nations' aggregate debts that change nothing ("uk:aggregate"): no aggregate debt is drawn.

    While debt is off, or while the nation's levels of government are
    chosen (its own, else those for every chart), which replace the
    aggregate lines (``CountryMetadata.macro_specs``); and for a nation with
    gross debt alone, which draws it whatever the list names
    (``Nation.view``). The window and the page grey the UK's boxes, keeping
    their ticks, and the written command line leaves the list out
    (batch 10.4), as for a margin (``idle_margins``).
    """
    option = by_name("aggregate")

    def has_levels(nation: Nation) -> bool:
        """Its chart draws levels: some of those chosen are its own (``Nation.view``); a text that does not parse counts."""
        for name in _PART_OPTIONS:
            text = payloads.get(nation_choice(nation, by_name(name)), payloads.get(name, "")).strip()
            if text:
                try:
                    return bool(nation.view("components", by_name(name).parse(text)))
                except ValueError:
                    return True
        return False

    return frozenset(
        nation_choice(nation, option)
        for nation in NATIONS
        if not flags.get("debt", True) or has_levels(nation) or len(nation.debt_aggregates) < 2
    )


def _nation_settings(payloads: Mapping[str, str], values: Mapping[str, object]) -> tuple:
    """Return ``PlotConfig.nation_settings`` for the choices given with a nation's code; raise ValueError.

    Each nation starts from ``values`` (the choices for every chart) and takes
    its own values in table order, so ``--us:no-yields:30`` takes the 30-year
    out of what ``--yields:LIST`` chose. The checks run on each nation's own
    result: its terms (``_check_nation_terms``), min < max, bottom < top,
    and the right-axis units. Only fields whose chart ends up different are
    kept (``nation_view``).
    """
    settings = []
    for nation in NATIONS:
        own = dict(values)
        given: dict[str, str] = {}
        try:
            for option in options_of(Kind.VALUE):
                if not per_nation(option):
                    continue
                key = nation_choice(nation, option)
                if key in payloads and option.removes:
                    # Taken out of what the nation draws: its own default
                    # while the list is at the default for every chart.
                    field = option.fields[0]
                    current = dict(nation.own_defaults).get(field, own[field]) if own[field] == getattr(PlotConfig(), field) else own[field]
                    own[field] = _removed(option, payloads[key], current)
                elif key in payloads:
                    parsed = option.parse(payloads[key])
                    own.update(zip(option.fields, parsed if len(option.fields) > 1 else (parsed,)))
                else:
                    continue
                given[option.name] = payloads[key]
                if option.fields[0] in ("yield_terms", "spread_pairs", "mortgage_terms", "debt_aggregates", "components"):
                    _check_nation_terms(nation, option.fields[0], own)
            # A nation's own debt and interest levels are one field, as for
            # every chart: given on both, they must agree (batch 10.5).
            own_parts = {name: by_name(name).parse(given[name]) for name in _PART_OPTIONS if name in given}
            if len(set(own_parts.values())) > 1:
                raise ValueError(
                    f"--debt:{own_parts['debt-parts']} and --interest:{own_parts['interest-parts']} choose different levels; "
                    "give the letters once, or the same on both"
                )
            # A margin names its term too, unless a list of terms is given:
            # one for every chart on each nation that has the term, one of
            # the nation's own on it (a nation without the term refuses
            # that), added to the nation's list where that does not draw it.
            # Not to the list for every chart: that would no longer be the
            # default, and a nation with its own default would lose it
            # (`--na:gb --prime:0.5` drew no UK mortgage until 2026-10-21).
            lists = by_name("mortgage-terms")
            for term, margin in margin_options().items():
                own_margin = nation_choice(nation, margin) in payloads
                if own_margin and term not in nation.mortgage_terms:
                    raise ValueError(f"{nation.name} has {_MARGIN_TERM_LACKED[term]}")
                if (
                    (own_margin or margin.name in payloads)
                    and term in nation.mortgage_terms
                    and lists.name not in payloads
                    and nation_choice(nation, lists) not in payloads
                    and term not in nation.view("mortgage_terms", own["mortgage_terms"])
                ):
                    own["mortgage_terms"] = _with_term(own["mortgage_terms"], term)
            if given:
                check_yield_bounds(own)
                check_macro_bounds(own)
                check_macro_bound_units(given, own)
        except ValueError as exc:
            raise ValueError(f"{exc} (--{nation.prefix}: {nation.name} only)") from None
        # Kept only where the nation's chart differs: Canada's own mortgage
        # terms "5" draw what the default "30,5" draws on its chart; a limit's
        # currency, the U.S.' "USD" what none draws on its (``Nation.view``).
        overrides = tuple(
            (field, own[field]) for field in PER_NATION_FIELDS if nation.view(field, own[field]) != nation.view(field, values[field])
        )
        if overrides:
            settings.append((nation.key, overrides))
    return tuple(settings)


def config_from_choices(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> PlotConfig:
    """Build the PlotConfig the choices describe; raise ValueError naming the first problem.

    Starts from PlotConfig's defaults (the default end date is today). VALUE
    options are parsed in table order and each option's ``check`` runs straight
    after it, against everything gathered so far. Two rules span several options:

    * Curves: if any curve is chosen positively, only the positively chosen
      curves are drawn; otherwise all four are, minus any switched off. (With
      every curve given explicitly, as the GUI does, this is simply "draw the
      ones switched on".)
    * Countries: no country chosen means both charts.
    * Curve sub-options: --debt:LETTERS and --interest:LETTERS set the same
      levels, so given on both they must agree. Each also names its curve,
      as --debt and --interest do, unless that curve's flag was given
      explicitly (the window gives every flag, so there it names nothing);
      a nation's own (--cdn:debt:fp, batch 10.5) too, on every chart.
    * A value option that removes (``--no-yields:LIST``) takes its items out
      of its field as the options before it left it; an item not there, or
      none left, is an error.
    * A list for every chart names at least one item: "none" is a nation's
      own (``--cdn:yields:none``), and every chart's curves of a list have
      their own switch (--no-yield, --no-mortgages, --no-spreads).
    * A value that belongs to a flag (``turns_on``: --reg:TOL) turns it on,
      unless the flag was given explicitly (--reg:2 --no-reg is off); given
      for one nation (--us:sp:10-2) too, for both charts.
    * A margin (``margin_options``: --prime:MARGIN, batch 9.4) also names
      its term, on each chart that has the term (given for every chart) or
      on its nation's (given for one), in that nation's own list, unless a
      list of mortgage terms is given there: then the list says what is
      drawn (--mo:5 --prime:0.5 draws no prime rate, its margin idle). The
      window and the page always give the lists, so there it never adds one
      (``_nation_settings``).
    * A value given for one nation (key "us:top") applies to its chart only
      (``_nation_settings``).
    * Measure: -r and -p exclude each other (``check_single_measure``); -r
      without debt or interest has no effect (``idle_options``).
    * Right-axis limits are percentages under -r and dollars otherwise
      (``check_macro_bound_units``, once the flags are known).
    """
    values = dataclasses.asdict(PlotConfig())
    for option in options_of(Kind.VALUE):
        if option.name in payloads and option.removes:
            values[option.fields[0]] = _removed(option, payloads[option.name], values[option.fields[0]])
        elif option.name in payloads:
            parsed = option.parse(payloads[option.name])
            if option.fields[0] in _LIST_FIELDS and not parsed:
                raise ValueError(
                    f"{option.usage.split(':')[0]}:{payloads[option.name].strip()} draws none on every chart; "
                    f"use --no-{list_switch(option).name} (a nation's own list may be none: --cdn:{option.names[0]}:none)"
                )
            values.update(zip(option.fields, parsed if len(option.fields) > 1 else (parsed,)))
        if option.check is not None:
            option.check(values)

    given_parts = {curve: by_name(name).parse(payloads[name]) for name, curve in _PART_OPTIONS.items() if name in payloads}
    if len(set(given_parts.values())) > 1:
        raise ValueError(
            f"--debt:{given_parts['debt']} and --interest:{given_parts['interest']} choose different levels; "
            "give the letters once, or the same on both"
        )
    turned_on = {
        option.turns_on: True
        for option in options_of(Kind.VALUE)
        if option.turns_on
        and (option.name in payloads or any(nation_choice(nation, option) in payloads for nation in NATIONS))
    }
    # A nation's own levels name their curve too, on every chart, as a value
    # given for one nation turns its flag on for both (batch 10.5).
    named_parts = set(given_parts) | {
        curve for name, curve in _PART_OPTIONS.items() if any(nation_choice(nation, by_name(name)) in payloads for nation in NATIONS)
    }
    flags = {**{curve: True for curve in named_parts}, **turned_on, **flags}

    for option in options_of(Kind.FLAG):
        if option.name in flags:
            values[option.fields[0]] = flags[option.name]

    curves = {option.fields[0]: flags.get(option.name) for option in options_of(Kind.TOGGLE)}
    if any(chosen is True for chosen in curves.values()):
        values.update({field: chosen is True for field, chosen in curves.items()})
    else:
        values.update({field: chosen is not False for field, chosen in curves.items()})

    for option in options_of(Kind.SWITCH):
        values[option.fields[0]] = flags.get(option.name, False)
    # No nation chosen: those drawn by default (Canada and the U.S.).
    if not any(values[nation.show_field] for nation in NATIONS):
        values.update({nation.show_field: nation.shown_by_default for nation in NATIONS})

    check_single_measure(values)
    # -r divides debt and interest by GDP. With neither drawn it has nothing
    # to act on, and GDP, if chosen, is drawn in dollars, as without -r
    # (before 2026-10-13 -r hid it, leaving the right axis empty). The window
    # and the page grey -r out then (``idle_options``), and a greyed control
    # changes nothing.
    if values["relative"] and "relative" in idle_options(values["include_debt"], values["include_gdp"], values["include_interest"]):
        values["relative"] = False
    check_macro_bound_units(payloads, values)
    values["nation_settings"] = _nation_settings(payloads, values)
    return PlotConfig(**values)


def idle_options(debt: bool, gdp: bool, interest: bool) -> frozenset[str]:
    """Return the options that change nothing on any chart while these right-axis curves are chosen.

    Terry, 2026-10-08: grey out "Regression segments", "By level", "% of GDP"
    and "Per capita" when none of the series they apply to is chosen. The
    window and the web page grey these out, keeping their ticks and texts
    (choosing a curve again brings the chart back as it was); a value among
    them is ignored, as the regression tolerance is while --reg is off.

    * -r and the levels of government apply to debt and interest (GDP is
      only -r's divisor), so they need one of the two;
    * -p, the regression segments, the right axis's Top and Bottom and the
      projections to today (batch 11) apply to any right-axis curve, so they
      need debt, GDP or interest (under -r GDP is not drawn, but -r then
      needs debt or interest, which draw).

    Each was checked on 2026-10-13 to draw a byte-identical chart when idle,
    -r excepted: it hid GDP, which ``config_from_choices`` now stops.
    """
    idle: set[str] = set()
    if not (debt or interest):
        idle |= {"relative", "debt-parts", "interest-parts"}
    if not (debt or gdp or interest):
        idle |= {"per-capita", "regression", "regression-tolerance", "top", "bottom", "projections"}
    return frozenset(idle)


# The automatic refresh's controls (batch 11.3), greyed together where it can
# bring nothing new (``auto_refresh_idle``).
AUTO_REFRESH_OPTIONS = frozenset({"auto-refresh", "auto-refresh-minutes"})


def auto_refresh_idle(texts: Mapping[str, str], flags: Mapping[str, bool]) -> bool:
    """Whether the automatic refresh can bring nothing new to the charts these choices draw (``PlotConfig.refresh_brings_nothing``).

    ``texts`` are the fields a drawing takes (the window's and the page's
    ``frontend.drawn_payloads``); its own minutes are left out, so the rule
    never depends on them. False where the choices draw nothing (a field in
    the wrong, marked as such): the box stays as it is.
    """
    return AUTO_REFRESH_OPTIONS <= latest_idle(texts, flags)


def latest_idle(texts: Mapping[str, str], flags: Mapping[str, bool]) -> frozenset[str]:
    """Return the latest values' controls that can change nothing on the charts these choices draw, judged on the texts too.

    The automatic refresh's (``AUTO_REFRESH_OPTIONS``, batch 11.3:
    ``PlotConfig.refresh_brings_nothing``); and since batch 28.1 the
    intraday quotes (``PlotConfig.current_brings_nothing``) and the
    projections to today, which only a window the day's quotes can reach
    takes (``PlotConfig.quotes_can_reach``; Terry, plan 28.1: greyed "while
    End is before today, when there is no quote and no projection").
    ``texts`` as for ``auto_refresh_idle``; none where the choices draw
    nothing.
    """
    own = {key: text.strip() for key, text in texts.items() if key not in AUTO_REFRESH_OPTIONS and text.strip()}
    try:
        config = config_from_choices(own, flags)
    except ValueError:
        return frozenset()
    idle: set[str] = set()
    if config.refresh_brings_nothing is not None:
        idle |= AUTO_REFRESH_OPTIONS
    if config.current_brings_nothing is not None:
        idle.add("current")
    if not config.quotes_can_reach:
        idle.add("projections")
    return frozenset(idle)


def choices_from_config(config: PlotConfig) -> tuple[dict[str, str], dict[str, bool]]:
    """Return ``(payloads, flags)`` describing ``config``, for filling the GUI's controls.

    Every GUI option is included; one that can differ by nation
    (``per_nation``) once for each nation, under "NATION:OPTION" ("us:top"),
    and never for both charts. An unset value (a blank yield or dollar
    bound) comes back as "", which the GUI treats as "use the default".
    So does a value equal to a *moving* default (one PlotConfig computes
    afresh, such as the end date "today"): written out as a date it would be
    remembered and frozen, and tomorrow's chart would stop at yesterday.
    """
    defaults = PlotConfig()
    moving = {field.name for field in dataclasses.fields(PlotConfig) if field.default_factory is not dataclasses.MISSING}
    payloads: dict[str, str] = {}
    flags: dict[str, bool] = {}
    for option in OPTIONS:
        if not option.in_gui:
            continue
        field_values = tuple(getattr(config, field) for field in option.fields)
        if per_nation(option):
            # Each nation's own field (the panel under its tab): its value, as
            # far as its chart can draw it (``nation_view``), with the option's
            # other fields as they are (Top's currency: "USD20t" shows as given
            # in every box, the U.S.' too, batch 18.3).
            for nation in NATIONS:
                own = config.for_nation(nation.key)
                value = nation_view(nation, option, getattr(own, option.fields[0]))
                others = tuple(getattr(own, field) for field in option.fields[1:])
                payloads[nation_choice(nation, option)] = option.format((value, *others), own)
        elif option.kind is Kind.VALUE:
            at_moving_default = any(field in moving for field in option.fields) and field_values == tuple(
                getattr(defaults, field) for field in option.fields
            )
            payloads[option.name] = "" if at_moving_default else option.format(field_values, config)
        else:
            flags[option.name] = bool(field_values[0])
    return payloads, flags


def _shorter_as_removal(option: Option, text: str, default: tuple | None = None) -> str | None:
    """Return the option's value written as what it drops from the default, when that is shorter; else None.

    ``--no-yields:30y`` rather than ``--yields:3m,2y,5y,10y`` (an option
    with a remover, ``Option.removes``, on its field). None also when the
    text does not parse; the caller then writes it as it is. "" when it
    is the default, spelled another way: nothing need be written.
    ``default``: the list the removal is taken from, when not the default
    for every chart (a nation's own default: Germany's has no 3-month).
    """
    remover = next((other for other in options_of(Kind.VALUE) if other.removes and other.fields == option.fields), None)
    if remover is None:
        return None
    try:
        chosen = option.parse(text)
    except ValueError:
        return None
    if not chosen:
        return None  # "none": dropping every term is refused (``_removed``)
    default = getattr(PlotConfig(), option.fields[0]) if default is None else default
    dropped = [item for item in default if item not in chosen]
    if tuple(chosen) == tuple(default):
        return ""
    if not dropped or not set(chosen) <= set(default):
        return None
    removal = f"{remover.usage.split(':')[0]}:{','.join(dropped)}"
    return removal if len(removal) < len(f"{option.usage.split(':')[0]}:{text}") else None


def nation_view(nation: Nation, option: Option, value: object) -> object:
    """Return what a value of ``option`` draws on ``nation``'s chart (``config.Nation.view``)."""
    return nation.view(option.fields[0], value)


def drawn_config(config: PlotConfig, key: str) -> PlotConfig:
    """Return what nation ``key``'s chart is drawn from: its own values applied, its terms as far as it has them.

    Two configs with the same ``drawn_config`` for every nation draw the same
    charts, though one gives a list for both charts and the other each
    nation's own (the window's command line, ``--yields:3m,2y,7y`` for
    "3m,2y" in Canada's panel and "3m,2y,7y" in the U.S.'s).
    """
    nation = next(nation for nation in NATIONS if nation.key == key)
    own = config.for_nation(key)
    viewed = {
        option.fields[0]: nation_view(nation, option, getattr(own, option.fields[0]))
        for option in options_of(Kind.VALUE)
        if per_nation(option) and not option.removes
    }
    # The options' other fields: a limit in the nation's own currency is one
    # without (batch 18.3).
    for field in PER_NATION_FIELDS:
        viewed.setdefault(field, nation.view(field, getattr(own, field)))
    # A margin with its term not drawn draws nothing (``idle_margins``).
    for term, field in MORTGAGE_MARGINS.items():
        if not own.mortgages or term not in viewed["mortgage_terms"]:
            viewed[field] = field_default(field)
    # Nor the aggregate debts without debt, or with levels (``idle_aggregates``).
    if not own.include_debt or viewed["components"]:
        viewed["debt_aggregates"] = field_default("debt_aggregates")
    return dataclasses.replace(own, nation_settings=(), **viewed)


def _one_amount(option: Option, texts: dict[str, str], nations: Mapping[str, Nation]) -> str | None:
    """Return the text a Top or Bottom is written once with, for every chart, when each nation's gives the same amount; else None.

    Batch 18.3: the "All" tick copies the U.S.' "20t" as "USD20t" into the
    other nations' boxes, so the texts differ, but each nation's draws 20
    trillion U.S. dollars, an unmarked amount being in the nation's own
    currency; one of the marked texts says so for every chart
    (``--top:USD20t``). Not when a box is blank, a text does not parse, or
    none is marked (equal texts are written once already).
    """
    if not texts or not all(texts.values()):
        return None
    try:
        parsed = {key: option.parse(text) for key, text in texts.items()}
    except ValueError:
        return None
    amounts = {(value, currency or nations[key].currency) for key, (value, currency) in parsed.items()}
    marked = [texts[key] for key, (_value, currency) in parsed.items() if currency is not None]
    return marked[0] if len(amounts) == 1 and marked else None


def _nation_tokens(option: Option, texts: dict[str, str], spelling: str) -> list[str]:
    """Return the tokens for a value that differs by nation (``texts``: nation key -> its text; "" the default).

    A list is written once, for every chart, when one list draws each
    nation's own (``nation_view``): for the yield and mortgage terms the
    terms of all of them, as before there were nations
    (``--yields:3m,2y,5y,7y,10y,30y``); else one nation's own list (the U.S.'s
    spreads "10y-2y,7y-1m" draw Canada's "10y-2y"). Otherwise each nation's
    own value is written after its code (``--us:max:8``), and a nation at the
    default needs none. A list for every chart names at least one item, so
    nations left none of it all are each written ``--cdn:yields:none``.
    """
    default = getattr(PlotConfig(), option.fields[0])
    nations = {nation.key: nation for nation in NATIONS}
    if option.fields[0] in _LIST_FIELDS:
        try:
            own = {key: option.parse(text) if text else default for key, text in texts.items()}
        except ValueError:
            own = {}
        # The default first: every nation at its own default (the UK's
        # differs from the others') needs nothing written.
        candidates = [value for value in (default, *own.values()) if value]
        union = [item for value in own.values() for item in value]
        if union and option.fields[0] != "spread_pairs":
            candidates.insert(1, option.parse(",".join(union)))
        for candidate in candidates:
            if own and all(
                nation_view(nations[key], option, candidate) == nation_view(nations[key], option, value)
                for key, value in own.items()
            ):
                if candidate == default:
                    return []
                text = option.format((candidate,), PlotConfig())
                return [_shorter_as_removal(option, text) or f"{spelling}:{text}"]
    if option.fields[0] == "components":
        # The levels (batch 10.5) as a list: written once, for every chart,
        # when one set of letters draws each nation's own (the UK has no "p",
        # so --debt:fp draws its "f"), the default ("": the aggregate lines)
        # first, then the letters of them all.
        try:
            own = {key: option.parse(text) if text else default for key, text in texts.items()}
        except ValueError:
            own = {}
        union = "".join(letter for letter in COMPONENT_LETTERS if any(letter in value for value in own.values()))
        for candidate in dict.fromkeys((default, union, *own.values())):
            if own and all(
                nation_view(nations[key], option, candidate) == nation_view(nations[key], option, value)
                for key, value in own.items()
            ):
                return [] if candidate == default else [f"{spelling}:{candidate}"]
    if option.fields[0] in ("macro_top", "macro_bottom"):
        once = _one_amount(option, texts, nations)
        if once is not None:
            return [f"{spelling}:{once}"]
    tokens = []
    for key, text in texts.items():
        try:
            at_default = not text or nation_view(nations[key], option, option.parse(text)) == nation_view(
                nations[key], option, default
            )
        except ValueError:
            at_default = False
        if not at_default:
            # Shortened from the nation's own default, which is what its
            # removal is taken from (Germany's 2 5 10 30 has no 3-month).
            shorter = _shorter_as_removal(option, text, dict(nations[key].own_defaults).get(option.fields[0], default))
            if shorter != "":
                # The nation's prefix, not its key: Germany's key "de" would be --debt.
                tokens.append(f"--{nations[key].prefix}:{(shorter or f'{spelling}:{text}').lstrip('-')}")
    return tokens


def switch_of(nation: Nation) -> str:
    """Return the name of the switch that chooses ``nation``'s chart ("uk", "germany")."""
    return next(option.name for option in options_in("country") if option.fields == (nation.show_field,))


def command_line_tokens(payloads: Mapping[str, str], flags: Mapping[str, bool]) -> list[str]:
    """Return the shortest command line (after the script name) that reproduces the GUI choices.

    Options left at their defaults are omitted. The GUI passes every option,
    blanks included; blank values are omitted too, and so are values that
    change nothing on any chart (``idle_options``: Top and Bottom, the levels
    and the tolerance with no curve to act on), whose fields the window and
    the page grey out and keep for when a curve is chosen again.
    """
    defaults, default_flags = choices_from_config(PlotConfig())
    tokens: list[str] = []
    idle = idle_options(flags.get("debt", True), flags.get("gdp", True), flags.get("interest", True))
    idle_keys = idle_margins(payloads, flags) | idle_aggregates(payloads, flags)
    payloads = {key: text for key, text in payloads.items() if key.split(":")[-1] not in idle and key not in idle_keys}
    # The automatic refresh's minutes are greyed where it brings nothing new
    # (batch 11.3); its box is written, as every greyed tick is.
    if payloads.get("auto-refresh-minutes", "").strip() and auto_refresh_idle(payloads, flags):
        del payloads["auto-refresh-minutes"]

    # The nations' switches, unless the ones chosen are those drawn by default.
    countries = [option for option in options_in("country") if option.in_gui]
    chosen = [option for option in countries if flags.get(option.name)]
    by_default = [option for option in countries if option.fields[0] in {n.show_field for n in NATIONS if n.shown_by_default}]
    if chosen and chosen != by_default:
        if all(option.command_line for option in chosen):
            tokens += [option.flag for option in chosen]
        else:
            # A nation with no switch on the command line: every chosen nation
            # by its code (its first: ca, us, gb, de), "--nations:ca,gb".
            nations = {nation.show_field: nation for nation in NATIONS}
            tokens.append("--nations:" + ",".join(nations[option.fields[0]].codes[0] for option in chosen))

    # Curves: name the ones on, or negate the ones off, whichever is shorter
    # (both mean the same under the curve rule; all off needs every "--no-").
    # With levels chosen every curve is written out, because --debt:LETTERS
    # would otherwise name debt and hide the curves left unnamed.
    curves = options_of(Kind.TOGGLE)
    on = [option for option in curves if flags.get(option.name, True)]
    off = [option for option in curves if option not in on]
    # A nation drawn only when asked for, and not asked for, writes nothing
    # (its fields stay in the window for when it is).
    written_for = [n for n in NATIONS if n.shown_by_default or flags.get(switch_of(n), False)]
    with_levels = any(
        payloads.get(nation_choice(nation, by_name(name)), payloads.get(name, "")).strip()
        for nation in written_for
        for name in _PART_OPTIONS
    )
    if with_levels:
        tokens += [f"--{option.name}" if option in on else f"--no-{option.name}" for option in curves]
    elif off and (not on or len(off) <= len(on)):
        tokens += [f"--no-{option.name}" for option in off]
    elif off:
        tokens += [f"--{option.name}" for option in on]

    # The measure and the line labels: each switch that is on, spelled out.
    tokens += [
        f"--{option.name}" for option in options_of(Kind.SWITCH) if option.group != "country" and flags.get(option.name)
    ]
    # Values, each by the first spelling the help shows (--dimensions:,
    # --reg:). The levels are written on a curve that is shown: --debt:fp, or
    # --interest:fp when debt is off (both mean the same). A value that turns
    # a flag on (--reg:TOL) is left out while that flag is off, where it has
    # no effect, and otherwise stands for the flag too.
    # A value that differs by nation (the window's panel under each tab, keys
    # "us:top") is written once when it can be, else after each nation's
    # code (``_nation_tokens``).
    level_key = "interest" if not flags.get("debt", True) and flags.get("interest", True) else "debt"
    values: list[str] = []
    stood_for: set[str] = set()
    for option in options_of(Kind.VALUE):
        text = payloads.get(option.name, "").strip()
        texts = {}
        # The levels on a curve that is shown (--debt:fp, or --interest:fp).
        spelling = f"--{level_key}" if option.name in _PART_OPTIONS else option.usage.split(":")[0]
        if per_nation(option):
            texts = {nation.key: payloads.get(nation_choice(nation, option), text).strip() for nation in written_for}
            text = text if len(set(texts.values())) > 1 else next(iter(texts.values()))
        # "none" in every nation's field is written for each: a list for every chart is never none.
        if len(set(texts.values())) > 1 or (texts and _is_none(text)):
            if option.turns_on and not flags.get(option.turns_on, default_flags.get(option.turns_on)):
                continue
            written = _nation_tokens(option, texts, spelling)
            if written and option.turns_on:
                stood_for.add(option.turns_on)
            values += written
            continue
        default = defaults.get(option.name)
        if default is None and per_nation(option) and option.format:
            default = option.format((getattr(PlotConfig(), option.fields[0]),), PlotConfig())
        if not text or text == default:
            continue
        if option.turns_on:
            if not flags.get(option.turns_on, default_flags.get(option.turns_on)):
                continue
            stood_for.add(option.turns_on)
        shorter = _shorter_as_removal(option, text)
        if shorter != "":  # "": the default, spelled another way ("3m,2,5,10,30")
            values.append(shorter or f"{spelling}:{text}")

    # On/off flags in the window (--cur, --reg): only when not at their default.
    for option in options_of(Kind.FLAG):
        if option.name in stood_for:
            continue
        if option.in_gui and option.name in flags and flags[option.name] != default_flags[option.name]:
            tokens.append(f"--{option.name}" if flags[option.name] else f"--no-{option.name}")
    return tokens + values


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

_HELP_INDENT = "    "
_HELP_COLUMN = 36  # width of the spellings column (fits "--interest:LETTERS / --i:LETTERS")
_HELP_MIN_GAP = 3  # a spelling longer than the column still gets this many spaces
_HELP_INTRO = """\
Run with no flags to open the interactive window with both charts (Canadian,
then U.S.; the UK's and Germany's when asked for, --nations:gb or --nations:de,
which -c and -u may join). Flags set the window's starting values.

Names are case-insensitive, the dashes in front are optional, and any leading
part of a name will do: -r, --rel and --relative are the same. A name is never
matched by its first letter alone (--reg is not -r, --yes is not --yield). An
option that takes a value is written NAME:VALUE, and one that takes none must
not be given one (-r:1 is an error).

{per_nation}
"""
_HELP_NATIONS = (
    "A nation's code in front sets a value for its chart only: --us:top:20t, --cdn:yields:2,10, "
    "--us:no-y:30 (codes ca or cdn, us, gb or uk, and ger or deu, written in full; Germany's de only in "
    "--nations, since --de is --debt). It goes on {names}; the nation's own value replaces the one for both charts. "
    "A nation's own list may be none (--cdn:yields:none). A list for every chart draws on each chart the items that "
    "nation has; a chart left none of them draws none, with a warning (-c --yields:7,20)."
)


def help_epilog() -> str:
    """Return the option reference printed after argparse's own ``--help`` output."""
    names = [option.usage.split(":")[0] for option in OPTIONS if per_nation(option)]
    nations = _HELP_NATIONS.format(names=", ".join(names[:-1]) + " and " + names[-1])
    intro = _HELP_INTRO.format(per_nation=textwrap.fill(nations, width=79, break_on_hyphens=False))
    lines = intro.split("\n")
    for group, heading in GROUPS.items():
        lines.append(heading)
        for option in OPTIONS:
            if option.group != group or not option.command_line:
                continue
            width = max(_HELP_COLUMN, len(option.usage) + _HELP_MIN_GAP)
            first, *rest = option.help.split("\n")
            lines.append(f"{_HELP_INDENT}{option.usage:<{width}}{first}")
            lines.extend(f"{_HELP_INDENT}{'':<{width}}{line}" for line in rest)
        lines.append("")
    return "\n".join(lines)
