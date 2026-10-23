"""Chart construction: line drawing, per-country plot assembly, and run drivers.

Both country charts share one layout: yield curves on the left (linear %)
axis, the three macro curves on a right log twin axis (dollars; with -r debt
and interest as % of GDP; with -p dollars per person; see ``measures``; with
--debt:LETTERS one debt and one interest line per level of government), an auto-placed
legend, a title and a subtitle naming the dates the drawn data cover (which
can be narrower than the axis), with -l each line's last value at its
end, and with --reg straight pieces fitted to the right-axis curves, each
labelled with its growth in %/yr. With --policy, --mortgages and --spreads
the yield axis has their curves too (``ratesplot.rates``, ``add_rate_lines``).
Only the yield-line style differs: the Canadian pre-2001 history is monthly
and drawn as steps.

Without --start the charts begin on ``config.DEFAULT_START_FLOOR``, or
on the first date on which every chosen curve has data if that is later
(``resolve_start``), the same date for both countries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import partial, wraps
from typing import Callable, Iterable

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from .axes import apply_axes_formatting, format_currency, format_percent, format_spread, format_yield
from .baked import chart_ending
from .cdn_data import (
    align_cdn_macro,
    cdn_series_earliest,
    fetch_cdn_components,
    fetch_cdn_debt,
    fetch_cdn_gdp,
    fetch_cdn_interest,
    fetch_cdn_population,
    fetch_cdn_yields,
)
from .config import (
    CANADIAN_YIELD_HIST_END,
    CANVAS_DPI,
    CDN,
    DATE_COLUMN,
    DEFAULT_START_FLOOR,
    DEFAULT_YIELD_TERMS,
    EARLIEST_DATA_START,
    MACRO_PLOT_STYLES,
    MIN_WINDOW_DAYS,
    MORTGAGE_LEGEND_ORDER,
    NATIONS,
    POLICY_BAND_ALPHA,
    PROJECTION_ALPHA,
    PROJECTION_KEY_COLOR,
    PROJECTION_LABEL,
    PROJECTION_LABEL_PREFIX,
    PROJECTION_LABEL_STEERED,
    SPREAD_AXIS_LABEL,
    SPREAD_INVERSION_ALPHA,
    TERM_COLORS,
    DE,
    UK,
    US,
    YIELD_LINE_STYLE,
    YIELD_TERMS,
    CountryMetadata,
    PlotConfig,
    nation_by_key,
)
from .console import this_thread_output_to
from .endlabels import ValueFormatter
from .frames import filter_to_date_range
from .http import download_cache_on, in_parallel
from .joins import align_macro
from .latest import (
    PROJECTION_ATTR,
    QUOTE_TIME_ATTR,
    STEERED_ATTR,
    extend_cdn_yields,
    extend_us_yields,
    market_debt_for_projection,
    observed_through,
    project_to_now,
)
from .legend import finish_legend_and_title
from .measures import express
from .rates import RateCurve, held_steps, in_window, legend_label, rate_curves, warn_none_drawn
from .regression import RateLabel, add_regression_segments
from .regression import legend_entry as regression_legend_entry
from .de_data import (
    fetch_de_components,
    fetch_de_debt,
    fetch_de_gdp,
    fetch_de_interest,
    fetch_de_population,
    fetch_de_yields,
    de_series_earliest,
)
from .uk_data import (
    YIELD_HISTORY_ATTR,
    fetch_uk_components,
    fetch_uk_debt,
    fetch_uk_gdp,
    fetch_uk_interest,
    fetch_uk_population,
    fetch_uk_yields,
    uk_series_earliest,
)
from .us_data import fetch_us_macro, fetch_us_population, fetch_us_yields, us_series_earliest

YieldLineDrawer = Callable[[Axes, pd.DataFrame, PlotConfig], list[Line2D]]


# ---------------------------------------------------------------------------
# Console warnings about coverage
# ---------------------------------------------------------------------------


def warn_series_coverage(start_date: pd.Timestamp, series_earliest: dict[str, pd.Timestamp]) -> None:
    """Warn when the requested start precedes a source's first observation."""
    late_series = [(name, earliest) for name, earliest in series_earliest.items() if start_date < earliest]
    if not late_series:
        return

    print(f"  Warning: requested start {start_date.date()} is earlier than the first available observation for:")
    for name, earliest in late_series:
        print(f"    • {name} begins {earliest.date()}")


def warn_macro_limits_coverage(
    df_macro: pd.DataFrame, macro_columns: Iterable[str], config: PlotConfig
) -> None:
    """Warn when explicit ``--top``/``--bottom`` limits hide all or part of a right-axis curve."""
    if df_macro.empty or not config.has_explicit_macro_limits:
        return

    def limit_text(value: float | None) -> str:
        if value is None:
            return "None"
        return format_percent(value) if config.relative else format_currency(value, "")

    limits_text = f"--bottom:{limit_text(config.macro_bottom)}, --top:{limit_text(config.macro_top)}"
    bottom = config.macro_bottom if config.macro_bottom is not None else float("-inf")
    top = config.macro_top if config.macro_top is not None else float("inf")

    for column in macro_columns:
        series = df_macro[column].dropna() if column in df_macro.columns else pd.Series(dtype=float)
        if series.empty:
            continue
        low, high = series.min(), series.max()
        if low > top or high < bottom:
            print(f"  Warning: Right-axis curve '{column}' cannot be shown at all within limits {limits_text}.")
        elif low < bottom or high > top:
            print(f"  Warning: Right-axis curve '{column}' is only shown for part of its range due to limits {limits_text}.")


# ---------------------------------------------------------------------------
# Line drawing
# ---------------------------------------------------------------------------


def add_macro_line(
    ax: Axes,
    data: pd.DataFrame,
    *,
    enabled: bool,
    column: str,
    label: str,
    style: dict,
    projected_from: pd.Timestamp | None = None,
) -> Line2D | None:
    """Plot one macro series if it is enabled and has data; return the (legend) line or ``None``.

    With ``projected_from`` (--cur, ``latest.project_to_now``) the rows after
    that date are a projection, not data: they are drawn as a straight,
    fainter continuation, hidden from the legend, after the curve's steps.
    """
    if not enabled or data.empty or column not in data.columns or not data[column].notna().any():
        return None
    if projected_from is None:
        (line,) = ax.plot(data[DATE_COLUMN], data[column], label=label, **style)
        return line

    observed = data.loc[data[DATE_COLUMN] <= projected_from]
    ahead = data.loc[data[DATE_COLUMN] >= projected_from]
    faint = {key: value for key, value in style.items() if key != "drawstyle"} | {"alpha": PROJECTION_ALPHA}
    if not observed[column].notna().any():
        # The window lies wholly in the projection.
        (line,) = ax.plot(ahead[DATE_COLUMN], ahead[column], label=label, **faint)
        return line
    (line,) = ax.plot(observed[DATE_COLUMN], observed[column], label=label, **style)
    ax.plot(ahead[DATE_COLUMN], ahead[column], label="_projection", **faint)
    return line


def _yield_style(column: str, config: PlotConfig, nation_key: str) -> dict:
    """Return the line style of one yield column: its term's own colour, unless the nation draws the default five.

    With the default terms (no --yields:LIST) the lines take matplotlib's
    colour cycle in drawing order, as they always have, so those charts are
    unchanged; the cycle's colours are the default terms' ``TERM_COLORS``
    when all five are drawn. With terms chosen, each term has its own
    colour, so the 10-year is red however few are drawn. The terms are
    those the nation has (Canada's chart of ``--yields:3m,2,5,10,20,30``
    draws the default five), so a chart is coloured alike whether its terms
    were chosen for both charts or for it alone (``options.nation_view``).
    """
    own = next(nation.yield_terms for nation in NATIONS if nation.key == nation_key)
    if tuple(term for term in config.yield_terms if term in own) == DEFAULT_YIELD_TERMS:
        return YIELD_LINE_STYLE
    term = next(key for key, name in YIELD_TERMS.items() if name == column)
    return YIELD_LINE_STYLE | {"color": TERM_COLORS[term]}


def add_canadian_yield_lines(ax: Axes, yields: pd.DataFrame, config: PlotConfig) -> list[Line2D]:
    """Plot Canadian yield curves: monthly history as steps, daily live data as lines.

    ``yields`` is date-indexed. Each tenor is split at ``CANADIAN_YIELD_HIST_END``
    (``add_stepped_yield_lines``).
    """
    return add_stepped_yield_lines(ax, yields, config, "cdn", lambda _column: CANADIAN_YIELD_HIST_END)


def add_uk_yield_lines(ax: Axes, yields: pd.DataFrame, config: PlotConfig) -> list[Line2D]:
    """Plot the UK's yields: each term's monthly history as steps, then its daily par yield (``uk_data.fetch_uk_yields``)."""
    through = dict(yields.attrs.get(YIELD_HISTORY_ATTR, {}))
    return add_stepped_yield_lines(ax, yields, config, "uk", through.get)


def add_de_yield_lines(ax: Axes, yields: pd.DataFrame, config: PlotConfig) -> list[Line2D]:
    """Plot Germany's yields: each term's monthly values as steps, then its daily ones (``de_data.fetch_de_yields``)."""
    through = dict(yields.attrs.get(YIELD_HISTORY_ATTR, {}))
    return add_stepped_yield_lines(ax, yields, config, "de", through.get)


def add_stepped_yield_lines(
    ax: Axes,
    yields: pd.DataFrame,
    config: PlotConfig,
    nation_key: str,
    history_through: Callable[[str], pd.Timestamp | None],
) -> list[Line2D]:
    """Plot one nation's date-indexed yields: each column's monthly history as steps, its daily data as a line.

    ``history_through(column)`` is the last date of that column's monthly
    history (None: it has none). The daily segment reuses the history
    segment's colour and is hidden from the legend so each tenor appears once.
    """
    if not config.yield_columns or yields.empty:
        return []

    data = filter_to_date_range(yields.reset_index(), DATE_COLUMN, config).set_index(DATE_COLUMN)
    if data.empty:
        return []

    legend_lines: list[Line2D] = []
    for column in config.yield_columns:
        if column not in data.columns:
            continue
        series = data[column].dropna()
        through = history_through(column)
        historical = series.loc[:through] if through is not None else series.iloc[:0]
        current = series.loc[series.index > through] if through is not None else series
        label = f"{column} Yield"
        color = None

        if not historical.empty:
            (line,) = ax.plot(
                historical.index, historical.values, label=label, drawstyle="steps-post", **_yield_style(column, config, nation_key)
            )
            color = line.get_color()
            legend_lines.append(line)

        if not current.empty:
            (line,) = ax.plot(
                current.index,
                current.values,
                label="_nolegend_" if color is not None else label,
                **(_yield_style(column, config, nation_key) | ({"color": color} if color is not None else {})),
            )
            if color is None:
                legend_lines.append(line)

    return legend_lines


def add_us_yield_lines(ax: Axes, yields: pd.DataFrame, config: PlotConfig) -> list[Line2D]:
    """Plot U.S. yield curves as ordinary daily time-series lines.

    ``yields`` has a ``DATE`` column (FRED frames are not date-indexed).
    """
    if not config.yield_columns or yields.empty:
        return []

    data = filter_to_date_range(yields, DATE_COLUMN, config)
    lines: list[Line2D] = []
    for column in config.yield_columns:
        if column in data.columns:
            (line,) = ax.plot(data[DATE_COLUMN], data[column], label=f"{column} Yield", **_yield_style(column, config, "us"))
            lines.append(line)
    return lines


def add_rate_lines(
    ax: Axes, rates: Iterable[RateCurve], config: PlotConfig, yield_lines: Iterable[Line2D] = ()
) -> list[tuple[Line2D, RateCurve]]:
    """Plot the yield axis's other curves (``ratesplot.rates``); return each drawn curve's legend line with it.

    A rate is drawn as ``rates.held_steps`` says (batch 17.3): each value
    across what it applies to, an announced rate on to the chart's end; a
    rate with no value applying in the window is left off with a note. A
    spread is drawn from the value in effect at the window's start
    (``rates.in_window``). Where ``steps_until`` is set, the part up to it is
    drawn as steps and the rest as a line in the same colour, as the Canadian
    yields are. A spread's stretches below zero (an inverted curve) are
    shaded between it and zero, in its colour. A curve with ``color_of`` (a
    mortgage) takes the colour of that yield's line among ``yield_lines``
    when it is drawn, so the two match whatever colour the yield was given.
    A band (``RateCurve.upper``, the U.S. target range) gets its upper
    limits drawn and the space between shaded (``_add_band``). The legend
    names the parts of a joined curve the window shows (``rates.legend_label``).
    """
    yield_colours = {line.get_label(): line.get_color() for line in yield_lines}
    drawn: list[tuple[Line2D, RateCurve]] = []
    for curve in rates:
        values = in_window(curve.values, config) if curve.holds is None else held_steps(curve, config)
        if values.empty:
            before = curve.values.loc[curve.values.index < config.start]
            if curve.holds is not None and not before.empty:
                print(f"  Note: {curve.label}: no value applies in the window; its last before it is "
                      f"{format_yield(before.iloc[-1])} on {before.index[-1]:%Y-%m-%d}; not drawn.")
            continue
        style = curve.style
        if curve.color_of is not None and f"{curve.color_of} Yield" in yield_colours:
            style = style | {"color": yield_colours[f"{curve.color_of} Yield"]}
        if curve.steps_until is None:
            parts = [(values, style)]
        else:
            monthly = values.loc[values.index <= curve.steps_until]
            daily = values.loc[values.index > curve.steps_until]
            parts = [(monthly, style | {"drawstyle": "steps-post"}), (daily, style)]
        first: Line2D | None = None
        for part, part_style in parts:
            if part.empty:
                continue
            # The second part in the first's colour, and only the first in the legend.
            colour = {} if first is None else {"color": first.get_color()}
            label = legend_label(curve, config) if first is None else "_nolegend_"
            (drawn_line,) = ax.plot(part.index, part.to_numpy(), label=label, **(part_style | colour))
            first = first or drawn_line
            if curve.spread:
                as_steps = part_style.get("drawstyle") == "steps-post"
                ax.fill_between(
                    part.index, part.to_numpy(), 0.0, where=part.to_numpy() < 0, interpolate=not as_steps,
                    step="post" if as_steps else None, color=drawn_line.get_color(), alpha=SPREAD_INVERSION_ALPHA,
                    linewidth=0, label="_nolegend_",
                )
        if first is not None and curve.upper is not None:
            _add_band(ax, curve, values, config, style | {"color": first.get_color()})
        if first is not None:
            drawn.append((first, curve))
    return drawn


def _add_band(ax: Axes, curve: RateCurve, lower: pd.Series, config: PlotConfig, style: dict) -> None:
    """Draw a band's upper limits as a step line in ``style`` and shade it (batch 9.1, the U.S. target range).

    ``lower`` is the curve as drawn (``rates.held_steps``); the upper limits
    are stepped on the same dates. The upper line is drawn only where the two
    differ, and from the point before each such stretch, so it leaves the
    lower line where the band begins; where they are equal (a single target)
    the shading has no height. Neither is in the legend.
    """
    upper = held_steps(curve, config, curve.upper)
    apart = ((upper - lower).abs() > 1e-9).to_numpy()  # NaN (a break) is not apart
    if not apart.any():
        return
    edge = apart | np.append(apart[1:], False)
    ax.plot(upper.index, upper.where(edge).to_numpy(), label="_nolegend_", **style)
    ax.fill_between(
        upper.index, lower.to_numpy(), upper.to_numpy(), step="post", color=style["color"], alpha=POLICY_BAND_ALPHA,
        linewidth=0, label="_nolegend_",
    )


def _end_label_format(curve: RateCurve, config: PlotConfig) -> ValueFormatter:
    """Return how a rate curve's end label (-l) writes its last value: a spread in points, a band as its range ("3.75–4.00%").

    The label stands at the band's lower limit, the end of its legend line.
    """
    if curve.spread:
        return format_spread
    if curve.upper is not None:
        upper = held_steps(curve, config, curve.upper).dropna()
        lower = held_steps(curve, config).dropna()
        if not upper.empty and abs(upper.iloc[-1] - lower.iloc[-1]) > 1e-9:
            top = float(upper.iloc[-1])
            return lambda value: f"{format_yield(value).removesuffix('%')}–{format_yield(top)}"
    return format_yield


def yield_axis_legend(yield_lines: list[Line2D], rate_lines: list[tuple[Line2D, RateCurve]]) -> list[Line2D]:
    """Return the yield axis's legend entries: the yields longest term first, the policy rate, the mortgages, the spreads.

    Batch 17.2 (Terry, 2026-10-15): the longer terms higher in the legend,
    "sorting downward to the shorter terms. Most of the time, this would echo
    the vertical placement of the curves in the plot". The mortgages likewise
    (``config.MORTGAGE_LEGEND_ORDER``). The spreads keep their order, since
    each one's colour goes by its place (``rates.yield_spreads``). Only the
    legend is ordered: the lines are drawn as before, so where they cross,
    the same one is on top.
    """
    longest_first = {f"{name} Yield": rank for rank, name in enumerate(reversed(YIELD_TERMS.values()))}
    yields = sorted(yield_lines, key=lambda line: longest_first.get(line.get_label(), len(longest_first)))

    def place(item: tuple[Line2D, RateCurve]) -> tuple[int, int]:
        key = item[1].key
        if key.startswith("mortgage_"):
            return 1, MORTGAGE_LEGEND_ORDER.index(key.removeprefix("mortgage_"))
        if key.startswith("policy"):
            return 0, int(key == "policy_market")  # the target, then the market rate (batch 9.1)
        return 2, 0

    return yields + [line for line, _curve in sorted(rate_lines, key=place)]


def drawn_date_span(axes: Iterable[Axes]) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Return the first and last dates at which any line on ``axes`` has a value, or None if none does.

    This is the span the subtitle names. It can be narrower than the axis
    (``--start``/``--end``), which is kept as requested: e.g. ``-s:1900`` on
    a series that begins in 1919 shows 1900 onwards but reports 1919.
    """
    first, last = math.inf, -math.inf
    for ax in axes:
        for line in ax.get_lines():
            xy = np.asarray(line.get_xydata(), dtype=float)  # dates already converted to numbers
            xy = xy[np.isfinite(xy).all(axis=1)]
            if len(xy):
                first, last = min(first, xy[:, 0].min()), max(last, xy[:, 0].max())
    if first > last:
        return None
    return tuple(pd.Timestamp(mdates.num2date(value).replace(tzinfo=None)).normalize() for value in (first, last))


# ---------------------------------------------------------------------------
# Chart assembly
# ---------------------------------------------------------------------------


def draw_country(
    ax_yield: Axes,
    yields: pd.DataFrame,
    macro: pd.DataFrame,
    rates: list[RateCurve],
    config: PlotConfig,
    metadata: CountryMetadata,
    draw_yield_lines: YieldLineDrawer,
) -> None:
    """Draw one country's complete chart (lines, axes, title, legend) onto ``ax_yield``'s figure.

    Works on any figure: a pyplot one (``plot_country``) or a bare Agg one
    (``build_figure``), so the window and the GUI draw identical charts.
    """
    quote_time = yields.attrs.get(QUOTE_TIME_ATTR)  # --cur: when the day's quotes were taken, if any
    projected = macro.attrs.get(PROJECTION_ATTR, {})  # --cur: {column: date its data end}
    yield_lines = draw_yield_lines(ax_yield, yields, config)
    # Policy and mortgage rates and spreads (ratesplot.rates): on the yield
    # axis, listed with the yields.
    rate_lines = add_rate_lines(ax_yield, rates, config, yield_lines)

    ax_macro = ax_yield.twinx()
    macro_in_range = filter_to_date_range(macro, DATE_COLUMN, config)
    macro_lines: list[Line2D] = []
    macro_keys_drawn: list[str] = []
    macro_columns_drawn: list[str] = []
    # The aggregate debt's column is missing only when its source failed; in
    # a window before it begins (the UK's to 1900) it is there, empty.
    aggregate_debt = metadata.debt_column in macro.columns
    for style_key, enabled, column, label in metadata.macro_specs(config, aggregate_debt=aggregate_debt):
        line = add_macro_line(
            ax_macro,
            macro_in_range,
            enabled=enabled,
            column=column,
            label=label,
            style=MACRO_PLOT_STYLES[style_key],
            projected_from=projected.get(column),
        )
        if line is not None:
            macro_lines.append(line)
            macro_keys_drawn.append(style_key)
            macro_columns_drawn.append(column)

    # The left axis says "Spread" when one is drawn.
    left_label = SPREAD_AXIS_LABEL if any(curve.spread for _line, curve in rate_lines) else None
    apply_axes_formatting(ax_yield, ax_macro, config, metadata, left_label)
    warn_macro_limits_coverage(macro_in_range, macro_columns_drawn, config)
    # --reg: each right-axis curve fitted by straight pieces on its log axis,
    # drawn now that the axis limits (which set the tolerance) are known; their
    # rate labels wait for the final layout (ratesplot.regression).
    rate_labels: list[RateLabel] = []
    if config.regression:
        rate_labels = add_regression_segments(ax_macro, macro, zip(macro_lines, macro_columns_drawn), projected, config)
    # -l: every drawn curve gets its last value at its end, written as its
    # axis writes values: yields in percent, right-axis curves as the tick
    # labels there (dollars, or percent of GDP under -r); a projected value
    # (--cur) reads "≈".
    end_labels: list[tuple[Line2D, ValueFormatter]] = []
    if config.end_labels:
        macro_format = format_percent if config.relative else partial(format_currency, prefix=metadata.currency_prefix)
        end_labels = [(line, format_yield) for line in yield_lines] + [
            (line, _end_label_format(curve, config)) for line, curve in rate_lines
        ] + [
            (line, (lambda value, fmt=macro_format: PROJECTION_LABEL_PREFIX + fmt(value)) if column in projected else macro_format)
            for line, column in zip(macro_lines, macro_columns_drawn)
        ]
    # One legend entry says what the faint stretches are. Made after the line
    # widths are scaled (apply_axes_formatting), so it matches them.
    legend_macro = list(macro_lines)
    if any(column in projected for column in macro_columns_drawn):
        width = max(style["linewidth"] for style in MACRO_PLOT_STYLES.values()) * config.line_scale
        steered = set(macro.attrs.get(STEERED_ATTR, [])) & set(macro_columns_drawn)
        label = PROJECTION_LABEL_STEERED if steered else PROJECTION_LABEL
        legend_macro.append(Line2D([], [], color=PROJECTION_KEY_COLOR, linewidth=width, alpha=PROJECTION_ALPHA, label=label))
    if rate_labels:
        legend_macro.append(regression_legend_entry(config))
    # The title names only what is on the chart, and the subtitle only the
    # dates it covers; the legend keeps yields and macro curves as separate
    # column groups. In the title the spreads come straight after the yields
    # they are taken from (Terry, 2026-10-12), then the policy and mortgage
    # rates in their drawing order (a stable sort). The title names the
    # nation by its adjective; the form with its short name ("CDN") is drawn
    # only where the first would shrink a lot (batch 22, finish_legend_and_title).
    title_parts = dict(
        yields_drawn=bool(yield_lines),
        macro_keys_drawn=macro_keys_drawn,
        config=config,
        rate_titles=[curve.title for _line, curve in sorted(rate_lines, key=lambda item: not item[1].spread)],
    )
    title = metadata.title_for(**title_parts)
    short_title = metadata.title_for(**title_parts, short=True)
    finish_legend_and_title(
        ax_yield,
        [yield_axis_legend(yield_lines, rate_lines), legend_macro],
        title,
        config,
        drawn_date_span((ax_yield, ax_macro)),
        end_labels,
        quote_time if yield_lines else None,
        rate_labels,
        nation_by_key(metadata.key).market_timezone,
        short_title,
    )


def plot_country(
    yields: pd.DataFrame,
    macro: pd.DataFrame,
    rates: list[RateCurve],
    config: PlotConfig,
    metadata: CountryMetadata,
    draw_yield_lines: YieldLineDrawer,
) -> None:
    """Build one country's chart on a pyplot figure and show it in a matplotlib window."""
    _figure, ax_yield = plt.subplots(figsize=config.figsize_inches)
    draw_country(ax_yield, yields, macro, rates, config, metadata, draw_yield_lines)
    plt.show()


# ---------------------------------------------------------------------------
# Data preparation and run drivers
# ---------------------------------------------------------------------------


def _with_chart_end(
    prepare: Callable[[PlotConfig], tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]],
) -> Callable[[PlotConfig], tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]]:
    """``prepare`` with its chart's end in force (``baked.chart_ending``): a recent part beginning more than a year after the chart ends is not asked for.

    Plan 19.2 (b): "A chart ending before that part fetches nothing." Every
    caller of a nation's preparation gets it: each drawing, the automatic
    start's trial pass and the downloads made side by side.
    """

    @wraps(prepare)
    def prepared(config: PlotConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]:
        with chart_ending(config.end):
            return prepare(config)

    return prepared


@_with_chart_end
def prepare_cdn(config: PlotConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]:
    """Fetch and align all selected Canadian inputs, in the configured measure; return ``(yields, macro, rates)``.

    With --cur the yields run on to the day's quotes, and the macro curves
    with them; the quotes' time is in ``yields.attrs[QUOTE_TIME_ATTR]``.
    ``rates`` are the yield axis's other chosen curves (``ratesplot.rates``).
    """
    _require_start(config)
    _warn_no_yields("cdn", config)
    _note_gross_debt_drawn("cdn", config)
    warn_series_coverage(config.start, cdn_series_earliest(config))
    yields, quote_time = extend_cdn_yields(fetch_cdn_yields(config), config)
    rates = rate_curves("cdn", yields, config)
    # A spread is cut where its yields are (from the start): their own coverage is the one warned about.
    warn_series_coverage(config.start, {curve.label: curve.first for curve in rates if not curve.spread})
    if _levels_drawn("cdn", config):
        # Debt and interest by level of government replace the aggregate lines.
        series = (fetch_cdn_components(config), fetch_cdn_gdp(config))
    else:
        series = (fetch_cdn_debt(config), fetch_cdn_gdp(config), fetch_cdn_interest(config))
    # --cur on a chart reaching today: each curve carried on from its last data,
    # debt steered by the Government of Canada's market debt (ratesplot.latest).
    parts = [part for part in series if part is not None]
    observed = {column: observed_through(part[column].dropna().index) for part in parts for column in part.columns}
    history = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    market = market_debt_for_projection(observed, config)
    macro = project_to_now(align_cdn_macro(yields, series, config), observed, config, history, market)
    projected = macro.attrs.get(PROJECTION_ATTR, {})
    steered = macro.attrs.get(STEERED_ATTR, [])
    population = fetch_cdn_population() if config.per_capita else None
    yields.attrs[QUOTE_TIME_ATTR] = quote_time
    expressed = express(macro, config, CDN, population)
    expressed.attrs[PROJECTION_ATTR] = projected
    expressed.attrs[STEERED_ATTR] = steered
    return yields, expressed, rates


@_with_chart_end
def prepare_us(config: PlotConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]:
    """Fetch all selected U.S. inputs, trimmed to the end date, in the configured measure; return ``(yields, macro, rates)``.

    With --cur the yields run on to the day's quotes and federal debt daily
    (see ``ratesplot.latest``); the quotes' time is in ``yields.attrs[QUOTE_TIME_ATTR]``.
    ``rates`` are the yield axis's other chosen curves (``ratesplot.rates``).
    """
    _require_start(config)
    _warn_no_yields("us", config)
    _note_gross_debt_drawn("us", config)
    warn_series_coverage(config.start, us_series_earliest(config))
    yields, quote_time = extend_us_yields(fetch_us_yields(config), config)
    if not yields.empty:
        yields = yields.loc[yields[DATE_COLUMN] <= config.end]
    last_yield_date = yields[DATE_COLUMN].max() if not yields.empty else config.end
    rates = rate_curves("us", yields, config)
    # A spread is cut where its yields are (from the start): their own coverage is the one warned about.
    warn_series_coverage(config.start, {curve.label: curve.first for curve in rates if not curve.spread})

    macro = fetch_us_macro(config, last_yield_date)
    projected = macro.attrs.get(PROJECTION_ATTR, {})
    if not macro.empty:
        macro = macro.loc[macro[DATE_COLUMN] <= config.end]
    population = fetch_us_population() if config.per_capita else None
    yields.attrs[QUOTE_TIME_ATTR] = quote_time
    expressed = express(macro, config, US, population)
    expressed.attrs[PROJECTION_ATTR] = projected
    return yields, expressed, rates


@_with_chart_end
def prepare_uk(config: PlotConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]:
    """Fetch and align all selected UK inputs, in the configured measure; return ``(yields, macro, rates)``.

    As ``prepare_cdn``: date-indexed yields (each term's monthly history
    recorded in ``attrs[uk_data.YIELD_HISTORY_ATTR]``), run on with --cur
    to the day's quotes; the macro curves aligned on their dates and
    projected to a chart's last day as a debt clock is (no market debt
    steers the UK's).
    """
    _require_start(config)
    _warn_no_yields("uk", config)
    _note_gross_debt_drawn("uk", config)
    warn_series_coverage(config.start, uk_series_earliest(config))
    yields, quote_time = extend_cdn_yields(fetch_uk_yields(config), config, "uk", "UK")
    rates = rate_curves("uk", yields, config)
    warn_series_coverage(config.start, {curve.label: curve.first for curve in rates if not curve.spread})
    if _levels_drawn("uk", config):
        series = (fetch_uk_components(config), fetch_uk_gdp(config))
    else:
        series = (fetch_uk_debt(config), fetch_uk_gdp(config), fetch_uk_interest(config))
    parts = [part for part in series if part is not None]
    observed = {column: observed_through(part[column].dropna().index) for part in parts for column in part.columns}
    history = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    aligned = align_macro(yields, series, config)
    # The national debt alone is kept only until general government debt
    # begins, as Canada's federal debt is (cdn_data.align_cdn_macro).
    if UK.federal_debt_column in aligned.columns and UK.debt_column in aligned.columns:
        aligned.loc[aligned[UK.debt_column].notna(), UK.federal_debt_column] = np.nan
    macro = project_to_now(aligned, observed, config, history)
    projected = macro.attrs.get(PROJECTION_ATTR, {})
    population = fetch_uk_population() if config.per_capita else None
    yields.attrs[QUOTE_TIME_ATTR] = quote_time
    expressed = express(macro, config, UK, population)
    expressed.attrs[PROJECTION_ATTR] = projected
    return yields, expressed, rates


@_with_chart_end
def prepare_de(config: PlotConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]:
    """Fetch and align all selected German inputs, in the configured measure; return ``(yields, macro, rates)``.

    As ``prepare_uk``: date-indexed yields (each term's monthly part
    recorded in ``attrs[de_data.YIELD_HISTORY_ATTR]``), run on with --cur
    to the day's quotes; the macro curves aligned on their dates and
    projected to a chart's last day as a debt clock is (no market debt
    steers Germany's).
    """
    _require_start(config)
    _warn_no_yields("de", config)
    _note_gross_debt_drawn("de", config)
    warn_series_coverage(config.start, de_series_earliest(config))
    yields, quote_time = extend_cdn_yields(fetch_de_yields(config), config, "de", "German")
    rates = rate_curves("de", yields, config)
    warn_series_coverage(config.start, {curve.label: curve.first for curve in rates if not curve.spread})
    if _levels_drawn("de", config):
        series = (fetch_de_components(config), fetch_de_gdp(config))
    else:
        series = (fetch_de_debt(config), fetch_de_gdp(config), fetch_de_interest(config))
    parts = [part for part in series if part is not None]
    observed = {column: observed_through(part[column].dropna().index) for part in parts for column in part.columns}
    history = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    aligned = align_macro(yields, series, config)
    macro = project_to_now(aligned, observed, config, history)
    projected = macro.attrs.get(PROJECTION_ATTR, {})
    population = fetch_de_population() if config.per_capita else None
    yields.attrs[QUOTE_TIME_ATTR] = quote_time
    expressed = express(macro, config, DE, population)
    expressed.attrs[PROJECTION_ATTR] = projected
    return yields, expressed, rates


@dataclass(frozen=True)
class Country:
    """Everything needed to produce one country's chart."""

    key: str  # short name, as used for its tab and output file
    show_field: str  # PlotConfig field that selects it
    metadata: CountryMetadata
    prepare: Callable[[PlotConfig], tuple[pd.DataFrame, pd.DataFrame, list[RateCurve]]]
    draw_yield_lines: YieldLineDrawer


# In drawing order (Canadian, then U.S., then the UK's, then Germany's), as the command line always has.
COUNTRIES: tuple[Country, ...] = (
    Country("cdn", "show_cdn", CDN, prepare_cdn, add_canadian_yield_lines),
    Country("us", "show_us", US, prepare_us, add_us_yield_lines),
    Country("uk", "show_uk", UK, prepare_uk, add_uk_yield_lines),
    Country("de", "show_de", DE, prepare_de, add_de_yield_lines),
)


# ---------------------------------------------------------------------------
# The automatic start (no --start)
# ---------------------------------------------------------------------------


def _require_start(config: PlotConfig) -> None:
    """Refuse a config whose automatic start has not been found yet (``resolve_start``)."""
    if config.start is None:
        raise ValueError("the start date is automatic: call plotting.resolve_start(config) before preparing a chart")


def _note_gross_debt_drawn(country: str, config: PlotConfig) -> None:
    """Note a chart drawing its gross debt where none of the aggregate debts chosen is its own (``--aggregate:net`` on Canada's; batch 10.4)."""
    nation = nation_by_key(country)
    levels = nation.view("components", config.components)
    if config.include_debt and not levels and not set(config.debt_aggregates) & set(nation.debt_aggregates):
        print(f"  Note: {nation.name} has no {' or '.join(config.debt_aggregates)} debt; its gross debt is drawn.")


def _levels_drawn(country: str, config: PlotConfig) -> str:
    """Return the levels of government a chart draws (``Nation.view``): those chosen that it has.

    None where it has none of them, so its aggregate lines are drawn, with
    a note (batch 10.5: the UK and "p", where it drew nothing for debt and
    interest before).
    """
    nation = nation_by_key(country)
    levels = nation.view("components", config.components)
    if config.components and not levels:
        print(f"  Note: {nation.name} has none of the levels chosen ({config.components}); its aggregate lines are drawn.")
    return levels


def _warn_no_yields(country: str, config: PlotConfig) -> None:
    """Warn when the yield curves are on but the chart has none of the chosen terms (``rates.warn_none_drawn``).

    A chosen term it lacks among others is the fetcher's note; this is the
    case where none is left, so the chart draws no yield.
    """
    nation = nation_by_key(country)
    if config.include_yield and not nation.view("yield_terms", config.yield_terms):
        warn_none_drawn(country, "yield", f"none of its yield terms ({','.join(nation.yield_terms)}) is chosen")


def curve_first_dates(
    yields: pd.DataFrame, macro: pd.DataFrame, rates: list[RateCurve], config: PlotConfig, metadata: CountryMetadata
) -> dict[str, pd.Timestamp]:
    """Return the first date on which each curve ``draw_country`` would draw has a value, by its legend label.

    ``yields`` and ``macro`` are as ``prepare_*`` returns them (the Canadian
    yields are date-indexed, the other frames have a ``DATE`` column). The
    curves are every yield tenor, if yields are chosen, and each chosen
    right-axis curve (``metadata.macro_specs``) in the chosen measure: under
    -r debt begins where both debt and GDP do; and the yield axis's other
    curves (``rates``), which are there only when chosen.
    """
    firsts: dict[str, pd.Timestamp] = {}

    def note(frame: pd.DataFrame, dates: pd.DatetimeIndex, column: str, label: str) -> None:
        if column in frame.columns:
            has_value = frame[column].notna().to_numpy()
            if has_value.any():
                firsts[label] = dates[has_value][0]

    if config.yield_columns and not yields.empty:
        dates = pd.DatetimeIndex(yields[DATE_COLUMN] if DATE_COLUMN in yields.columns else yields.index)
        for column in config.yield_columns:
            note(yields, dates, column, f"{column} Yield")
    if not macro.empty:
        dates = pd.DatetimeIndex(macro[DATE_COLUMN])
        for _key, enabled, column, label in metadata.macro_specs(config):
            if enabled:
                note(macro, dates, column, label)
    for curve in rates:
        firsts[curve.label] = curve.first
    return firsts


def resolve_start(config: PlotConfig) -> PlotConfig:
    """Return ``config`` with its automatic start found; as it is when --start was given.

    Terry, 2026-09-29: without -s the start is "the oldest date that fully
    populates the curves that were specified", with no curve missing at the
    left; from that country's curves under -u or -c alone, otherwise from
    both countries' together. So each chosen country is prepared from
    ``EARLIEST_DATA_START``, the first date of each curve it would draw is
    read off (``curve_first_dates``), and the start is the latest of them.
    Terry, 2026-10-06: the start is then no earlier than
    ``DEFAULT_START_FLOOR``, unless the chart ends less than
    ``MIN_WINDOW_DAYS`` after that date; set to a date before
    ``EARLIEST_DATA_START``, the floor never applies and this is the rule of
    2026-09-29. The charts are then
    prepared from the start exactly as with -s set to it (the command line
    and the window keep the downloads for that second pass).

    The trial pass still begins at ``EARLIEST_DATA_START``, not at the floor:
    prepared from the floor, every curve would seem to begin there (the frames
    open with a row carrying the value then in effect), and the U.S. yields on
    the first trading day after it.

    The trial pass runs without --cur, which only adds values after the data
    end. It prints nothing: the real pass fetches the same data and prints
    the same progress and warnings. Only the calling thread's output is
    discarded (``console``): the window's main thread, or another visitor's
    drawing on the web page, prints as before. A curve that begins within
    ``MIN_WINDOW_DAYS`` of the end, or after it, cannot be whole in any
    window: it is left out of the choice (and said so), and drawn from where
    it begins, if at all. A country whose data cannot be prepared at all (a
    source down, 2026-10-21) is left out of the choice, with a warning; its
    chart's own drawing then fails and says why, and the others are drawn.

    The trial pass prepares the chosen nations side by side (batch 19.1,
    ``http.in_parallel``): it makes a drawing's first downloads, which
    mostly wait on the network, and the nations' sources are different
    hosts. Each host still gets one request at a time. With the start given
    there is no trial pass, and the downloads are made side by side all the
    same (``_download_side_by_side``).
    """
    if config.start is not None:
        _download_side_by_side(config)
        return config
    trial = replace(config, start=EARLIEST_DATA_START, current=False)
    firsts: dict[tuple[str, str], pd.Timestamp] = {}  # (country, curve label) -> first date
    unprepared: list[str] = []
    chosen = [country for country in COUNTRIES if getattr(config, country.show_field)]
    with this_thread_output_to(None):
        prepared = in_parallel([partial(country.prepare, trial.for_nation(country.key)) for country in chosen])
        for country, outcome in zip(chosen, prepared):
            if isinstance(outcome, Exception):  # warned of below, out of the silenced pass
                unprepared.append(f"{country.metadata.country_name} ({type(outcome).__name__}: {outcome})")
                continue
            yields, macro, rates = outcome
            own = trial.for_nation(country.key)
            for label, first in curve_first_dates(yields, macro, rates, own, country.metadata).items():
                firsts[(country.metadata.country_name, label)] = first
    for which in unprepared:
        print(f"  Warning: no data could be prepared for the chart of {which}; the start is found without it.")

    def named(curves: list[tuple[str, str]]) -> str:
        """``5-Year Yield and 10-Year Yield (Canada)``, one bracket per country."""
        countries = dict.fromkeys(country for country, _label in curves)
        return "; ".join(
            f"{' and '.join(label for c, label in curves if c == country)} ({country})" for country in countries
        )

    latest_start = config.end - pd.Timedelta(days=MIN_WINDOW_DAYS)
    whole = {curve: first for curve, first in firsts.items() if first <= latest_start}
    late = [curve for curve, first in firsts.items() if first > latest_start]
    left_out = f"; beginning after {latest_start:%Y-%m-%d}, too late to count for this end: {named(late)}" if late else ""
    if not whole:
        print(f"  Warning: no chosen curve begins by {latest_start:%Y-%m-%d}; the chart shows the last {MIN_WINDOW_DAYS} days{left_out}.")
        return replace(config, start=latest_start)
    start = max(whole.values())
    if start < DEFAULT_START_FLOOR <= latest_start:
        print(f"Start {DEFAULT_START_FLOOR:%Y-%m-%d}, the default start; every chosen curve has data by then{left_out}.")
        return replace(config, start=DEFAULT_START_FLOOR)
    # The curves begin after the floor, or the chart ends too soon after it.
    before_floor = ""
    if DEFAULT_START_FLOOR > latest_start:
        when = "before" if DEFAULT_START_FLOOR > config.end else f"less than {MIN_WINDOW_DAYS} days after"
        before_floor = f" (the chart ends {when} the default start, {DEFAULT_START_FLOOR:%Y-%m-%d})"
    last = [curve for curve, first in whole.items() if first == start]
    print(f"Start {start:%Y-%m-%d}, the first date on which every chosen curve has data{before_floor}; the last to begin: {named(last)}{left_out}.")
    return replace(config, start=start)


def _download_side_by_side(config: PlotConfig) -> None:
    """Make the chosen nations' downloads side by side, before their charts are drawn one after another (batch 19.1).

    For a start given (-s, a shared link's address): without a trial pass,
    each chart would wait on its own downloads in turn. So the nations are
    prepared now, side by side and silently, as the trial pass does, and the
    charts then find their downloads in the cache; a failure is not asked
    for again in the same drawing (``http._cached``). Only with two nations
    or more, and with the download cache on (the window, the web page): a
    command line with -s keeps no downloads, and would make them all twice.
    Without --cur, whose quotes of the moment are never cached.
    """
    chosen = [country for country in COUNTRIES if getattr(config, country.show_field)]
    if len(chosen) < 2 or not download_cache_on():
        return
    quiet = replace(config, current=False)
    with this_thread_output_to(None):
        in_parallel([partial(country.prepare, quiet.for_nation(country.key)) for country in chosen])


def build_figure(country: Country, config: PlotConfig) -> Figure:
    """Fetch, prepare and draw one country's chart on a new Agg figure, without pyplot.

    pyplot keeps global state and drives GUI windows, so it must not be used
    from a worker thread; a bare ``Figure`` with an Agg canvas is safe there
    as long as one thread uses it at a time. The DPI is pinned to
    ``CANVAS_DPI`` so the pixel size is exactly ``width_px`` x ``height_px``.
    An automatic start must be found first (``resolve_start``), once for all
    the charts drawn together.
    """
    config = config.for_nation(country.key)  # its own choices over the shared ones
    figure = Figure(figsize=config.figsize_inches, dpi=CANVAS_DPI)
    FigureCanvasAgg(figure)
    ax_yield = figure.subplots()
    yields, macro, rates = country.prepare(config)
    draw_country(ax_yield, yields, macro, rates, config, country.metadata, country.draw_yield_lines)
    return figure


def run_cdn(config: PlotConfig) -> None:
    """Fetch all selected Canadian inputs and show the Canadian chart in a matplotlib window."""
    config = config.for_nation(CDN.key)
    yields, macro, rates = prepare_cdn(config)
    plot_country(yields, macro, rates, config, CDN, add_canadian_yield_lines)
    print("CDN chart finished.\n")


def run_us(config: PlotConfig) -> None:
    """Fetch all selected U.S. inputs and show the U.S. chart in a matplotlib window."""
    config = config.for_nation(US.key)
    yields, macro, rates = prepare_us(config)
    plot_country(yields, macro, rates, config, US, add_us_yield_lines)
    print("US chart finished.\n")


def run_uk(config: PlotConfig) -> None:
    """Fetch all selected UK inputs and show the UK's chart in a matplotlib window."""
    config = config.for_nation(UK.key)
    yields, macro, rates = prepare_uk(config)
    plot_country(yields, macro, rates, config, UK, add_uk_yield_lines)
    print("UK chart finished.\n")


def run_de(config: PlotConfig) -> None:
    """Fetch all selected German inputs and show Germany's chart in a matplotlib window."""
    config = config.for_nation(DE.key)
    yields, macro, rates = prepare_de(config)
    plot_country(yields, macro, rates, config, DE, add_de_yield_lines)
    print("German chart finished.\n")
