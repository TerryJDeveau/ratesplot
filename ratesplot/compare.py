"""The comparison chart (batch 26, a prototype): one measure, a curve for each nation ticked, on a chart after theirs.

Terry, 2026-11-11 (decision 146), choosing batch 26 from the plan's Later
batches: "Let's try your proposals. It will be like a prototype. I don't have
a clear vision of how to design it." The proposals: a tab "Compare" after the
nations' tabs, in the window and on the page; ``--compare:MEASURE`` on the
command line; the measures that share a unit across nations
(``config.COMPARE_MEASURES``): a yield term, the policy rate, inflation; debt,
GDP and interest, as amounts in one currency or as % of GDP under -r; the
population.

How it is drawn. Each nation ticked is prepared by its own ``prepare_*``
(``plotting.COUNTRIES``) with every curve off but the one compared
(``solo_config``), and that curve drawn by its own chart's drawer: a yield
term by the nation's yield drawer, the policy rate and inflation by
``plotting.add_rate_lines``, an amount or the population by
``plotting.add_macro_line``. So each is drawn as on the nation's own chart:
its monthly history in steps, its daily values, its projection to today
(faint), the U.S. target range as a band. Its lines are then given the
nation's colour (``config.COMPARE_COLOURS``) and named for it: "Canada" in
the legend, "Canada: 10-Year Yield" in Export chart and the hover read-out.
The axes, the legend, the title, -l and --reg are those of the nations'
charts (``axes.apply_axes_formatting``, ``legend.finish_legend_and_title``,
``regression.add_regression_segments``). The downloads are the nations'
charts' own, kept for the drawing by the window and the page, so the chart
asks no source for anything new.

What a nation's chart chooses for itself (its panel: its terms, its limits,
its levels) does not reach this chart, which compares one measure on the
choices shared by every chart. Min, Max, Top and Bottom are the nations', so
this chart's axes are fitted to its curves and a zoom or a pan on it moves
the dates alone (``export.mark_dates_only``). The amounts are the aggregate
(general government) gross debt and its interest, per person under -p, at
constant prices under --constant (each nation's at its own prices), in the
master currency or the U.S. dollar where none is chosen, each nation's
converted at the rate of the End date (``fx.rate``, as batch 30 converts a
chart), each rate said in the message log. GDP under -r, which divides by it,
is compared as an amount. The population is a count, the same under every
measure. A nation that lacks the measure (the UK has no 2-year yield), or
whose source fails, is left off with a line in the log saying why.

The front ends draw this chart after the nations' as one more of ``CHARTS``,
by ``build_chart``; ``PlotConfig.show_compare`` chooses it as ``show_cdn``
chooses Canada's.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import partial

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from . import http
from .axes import ExtraAxis, apply_axes_formatting, format_currency, format_percent, format_population, format_yield
from .baked import chart_ending
from .endlabels import ValueFormatter
from .config import (
    CANVAS_DPI,
    CDN,
    COMPARE_COLOURS,
    COMPARE_DEFAULT_CURRENCY,
    COMPARE_KEY,
    CURRENCY_SYMBOLS,
    DATE_COLUMN,
    DE,
    DEFAULT_DEBT_AGGREGATES,
    MACRO_PLOT_STYLES,
    MARKET_TIMEZONE,
    PROJECTION_ALPHA,
    PROJECTION_KEY_COLOR,
    PROJECTION_LABEL,
    PROJECTION_LABEL_PREFIX,
    SERIES_KINDS,
    UK,
    US,
    YIELD_TERMS,
    CountryMetadata,
    MasterConversion,
    Nation,
    PlotConfig,
    compare_kind,
    compare_title,
    measure_title_suffix,
    nation_by_key,
)
from .export import YIELD_AXIS, mark_amounts_currency, mark_dates_only, mark_price_base, mark_series, series_of
from .frames import filter_to_date_range
from .fx import rate
from .hover import attach as attach_hover
from .hover import mark_quote, rounded
from .hover import remark as remark_reading
from .latest import PROJECTION_ATTR, QUOTE_TIME_ATTR
from .legend import finish_legend_and_title
from .measures import PRICE_BASE_ATTR
from .plotting import (
    COUNTRIES,
    EXTRA_CURVE_ATTR,
    Country,
    ExtraCurve,
    add_macro_line,
    add_rate_lines,
    drawn_date_span,
    last_piece,
    yield_axis_legend,
)
from .plotting import build_figure as build_nation_figure
# The nations' charts' own helpers, shared rather than copied: how a rate's end
# label is written (a band as its range), and a plain window kept on its monitor.
from .plotting import _end_label_format, _kept_on_its_monitor
from .rates import cut_to, filled_through
from .regression import RateLabel, add_regression_segments
from .regression import legend_entry as regression_legend_entry


@dataclass(frozen=True)
class CompareChart:
    """The comparison chart as the front ends' loops take a chart: its key (its tab's, ``frontend.TAB_TITLES``) and the PlotConfig field that chooses it."""

    key: str = COMPARE_KEY
    show_field: str = "show_compare"


CHART = CompareChart()
# Every chart a drawing can show, in tab order: the nations', then the comparison chart.
CHARTS: tuple[Country | CompareChart, ...] = (*COUNTRIES, CHART)

# Every curve of the nations' charts, off: the comparison chart turns one on (``solo_config``).
_EVERY_CURVE_OFF = dict(
    include_yield=False, policy_rates=False, inflation=False, mortgages=False, spreads=False,
    include_debt=False, include_gdp=False, include_interest=False, payments=False, price_index=False,
    population=False,
)
# Every curve solid on this chart, where each is one measure and its colour says
# whose: inflation's dots, GDP's and interest's dashes and the real yields'
# (which tell them from the yields on a nation's chart) would only blur four
# curves together. Canada's federal debt alone before its aggregate keeps its
# dots, which mark a change of what is counted, as on Canada's chart.
_SOLID = {"linestyle": "-"}
# The nations' metadata by key (their words in the title), and by currency (the
# right axis's label and its ticks' symbol for amounts in that currency).
_METADATA = {metadata.key: metadata for metadata in (CDN, US, UK, DE)}
_METADATA_BY_CURRENCY = {nation_by_key(metadata.key).currency: metadata for metadata in _METADATA.values()}


def build_chart(chart: Country | CompareChart, config: PlotConfig) -> Figure:
    """Draw one of ``CHARTS`` on a new Agg figure: a nation's (``plotting.build_figure``) or the comparison chart (``build_figure``)."""
    if isinstance(chart, CompareChart):
        return build_figure(config)
    return build_nation_figure(chart, config)


def build_figure(config: PlotConfig) -> Figure:
    """Fetch, prepare and draw the comparison chart on a new Agg figure, without pyplot, as ``plotting.build_figure`` draws a nation's."""
    figure = Figure(figsize=config.figsize_inches, dpi=CANVAS_DPI)
    FigureCanvasAgg(figure)
    draw_compare(figure.subplots(), config)
    return figure


def run_compare(config: PlotConfig) -> None:
    """Show the comparison chart in a matplotlib window (``--no-gui``), with the hover read-out unless --no-hover.

    No automatic refresh (--auto-refresh) in this prototype: it is drawn once.
    """
    figure, ax_yield = plt.subplots(figsize=config.figsize_inches)
    config = _kept_on_its_monitor(figure, config)
    draw_compare(ax_yield, config)
    if config.hover:
        attach_hover(figure)
    plt.show()
    print("Comparison chart finished.\n")


def solo_config(config: PlotConfig) -> PlotConfig:
    """The choices every nation is prepared with for the comparison chart: the shared ones, with the measure's curve the only one on.

    No nation's own choices (``nation_settings``) and no axis limits; the
    aggregate gross debt (no levels of government); no master currency, the
    amounts being converted by ``_in_currency``. -r, -p and --constant are
    kept for the amounts alone: GDP under -r is compared as an amount, and
    the rates and the population are drawn without them, so no population
    or price index is read for them.
    """
    measure = config.compare_measure
    kind = compare_kind(measure)
    curves = dict(_EVERY_CURVE_OFF)
    if kind == "yield":
        curves |= {"include_yield": True, "yield_terms": (measure,)}
    elif measure == "policy":
        curves |= {"policy_rates": True, "policy_terms": ("target",)}
    elif measure == "inflation":
        curves |= {"inflation": True}
    elif kind == "amount":
        curves |= {f"include_{measure}": True}
    else:
        curves |= {"population": True}
    amounts = {} if kind == "amount" else {"relative": False, "per_capita": False, "constant_prices": False}
    if measure == "gdp":
        amounts = {"relative": False}
    return replace(
        config,
        **curves,
        **amounts,
        nation_settings=(),
        components="",
        debt_aggregates=DEFAULT_DEBT_AGGREGATES,
        master_currency=None,
        master_conversion=None,
        yield_ymin=None,
        yield_ymax=None,
        macro_bottom=None,
        macro_top=None,
        macro_bottom_currency=None,
        macro_top_currency=None,
    )


def compared_currency(config: PlotConfig) -> str | None:
    """The currency the comparison chart's amounts are in: the master's, else ``COMPARE_DEFAULT_CURRENCY``; None where it draws no amount, or a share of GDP."""
    solo = solo_config(config)
    if compare_kind(config.compare_measure) != "amount" or solo.relative:
        return None
    return config.master_currency or COMPARE_DEFAULT_CURRENCY


def _in_currency(solo: PlotConfig, nation: Nation, currency: str) -> PlotConfig | None:
    """``solo`` with nation ``nation``'s amounts converted to ``currency`` at the End's rate (``fx.rate``), as batch 30's master currency is; None where no rate is known by the End.

    ``plotting.in_master_currency`` converts only while the master has effect
    on the nations' charts (``PlotConfig.master_for``); here every nation not
    already in ``currency`` is converted, whichever nations are ticked.
    """
    if nation.currency == currency:
        return solo
    # A chart that ended long ago asks nothing for the recent part (19.2 (b)).
    with chart_ending(solo.end):
        found = rate(nation.currency, currency, solo.end)
    if found is None:
        print(f"  Warning: no {nation.currency} to {currency} rate on or before {solo.end:%Y-%m-%d}; {nation.name} is left off the comparison.")
        return None
    print(f"  {nation.name} in {currency}: {found.value:.5g} {currency} per {nation.currency} on {found.dated:%Y-%m-%d} ({found.source}).")
    return replace(solo, master_conversion=MasterConversion(currency, nation.currency, found.value, found.dated, found.source))


@dataclass
class _Drawn:
    """One nation's curve on the comparison chart, as drawn: what the legend, -l and --reg need of it."""

    nation: Nation
    handles: list[Artist]  # its legend entry: its first line (a rate's is made once it has its colour, from ``pairs``)
    end_labels: list[tuple[Line2D, ValueFormatter]]  # (line, formatter) for -l
    config: PlotConfig  # the nation's, as prepared
    fitted: list[tuple[Line2D, str]] = field(default_factory=list)  # (line, column) for --reg: an amount's or the population's
    frame: pd.DataFrame | None = None  # the frame --reg fits ``fitted`` from
    projected: dict = field(default_factory=dict)  # column -> its data's last date (--projections)
    pairs: list = field(default_factory=list)  # a rate's (line, RateCurve), as ``plotting.add_rate_lines`` gives them
    artists: set = field(default_factory=set)  # every line and band it drew (batch 26.3: each made a difference from the base's)


def draw_compare(ax_yield: Axes, config: PlotConfig) -> None:
    """Draw the comparison chart (lines, axes, title, legend) onto ``ax_yield``'s figure: one curve for each nation ticked, of ``config.compare_measure``.

    As ``plotting.draw_country``, on any figure: a pyplot one (``run_compare``)
    or a bare Agg one (``build_figure``). See the module's docstring.
    """
    figure = ax_yield.figure
    measure = config.compare_measure
    kind = compare_kind(measure)
    solo = solo_config(config)
    currency = compared_currency(config)
    ax_macro = ax_yield.twinx()
    on_left = kind in ("yield", "rate")
    print(f"--- the comparison chart: {compare_title(measure)}")
    drawn: list[_Drawn] = []
    quotes: list[pd.Timestamp] = []
    price_base: pd.Timestamp | None = None
    extra_axis: ExtraAxis | None = None
    # A base nation (batch 26.3): drawn first, ticked or not, and every curve on the yield axis, in percent; one that
    # cannot be drawn leaves the comparison drawn without a base.
    base_key = config.base_nation

    def draw_one(country: Country, macro_axis: Axes) -> _Drawn | None:
        """One nation's curve of the measure, drawn, coloured and named for it; None, with a note, where it has none."""
        nonlocal price_base, extra_axis
        nation = nation_by_key(country.key)
        if kind == "yield" and measure not in nation.yield_terms:
            print(f"  Note: {nation.name} has no {YIELD_TERMS[measure]} yield; it is left off the comparison.")
            return None
        own = solo if currency is None else _in_currency(solo, nation, currency)
        if own is None:
            return None
        try:
            yields, macro, rates = country.prepare(own)
        except Exception as exc:  # that nation alone; the others are drawn
            why, trace = http.not_drawn(exc)
            if trace is not None:
                print(trace)
            print(f"  Warning: {nation.name} is left off the comparison: {why}")
            return None
        before = _artists(ax_yield, ax_macro)
        if kind == "yield":
            curve = _draw_yield(country, ax_yield, yields, own, nation)
            quote_time = yields.attrs.get(QUOTE_TIME_ATTR)
            if curve is not None and quote_time is not None:
                quotes.append(quote_time)
        elif kind == "rate":
            curve = _draw_rate(ax_yield, rates, own, nation)
        elif kind == "amount":
            curve = _draw_amount(macro_axis, macro, own, nation, country.metadata, currency)
            if price_base is None:  # --constant: the month the amounts are in, the same for every nation
                price_base = macro.attrs.get(PRICE_BASE_ATTR)
        else:
            curve, extra = _draw_count(macro_axis, macro, own, nation)
            if curve is not None and extra_axis is None and macro_axis is ax_macro:
                extra_axis = ExtraAxis(ax_macro, extra.axis_label, extra.tick_format)
        if curve is None:
            print(f"  Note: {nation.name} has no {compare_title(measure).lower()} in the window; it is left off the comparison.")
            return None
        curve.artists = _artists(ax_yield, ax_macro) - before
        _as_nation(curve.artists, nation)
        if curve.pairs:
            # A rate's legend entry made now, in the nation's colour: the U.S. target range's a band's key.
            curve.handles = yield_axis_legend([], curve.pairs[:1])
        for handle in curve.handles:
            handle.set_label(nation.name)
        return curve

    if base_key is not None:
        base_country = next(country for country in COUNTRIES if country.key == base_key)
        base_curve = draw_one(base_country, ax_yield)
        if base_curve is None:
            print(f"  Note: {nation_by_key(base_key).name}, the base nation, cannot be drawn; the comparison is drawn without a base.")
            base_key = None
        else:
            drawn.append(base_curve)
    for country in COUNTRIES:
        if getattr(config, country.show_field) and country.key != base_key:
            curve = draw_one(country, ax_yield if base_key else ax_macro)
            if curve is not None:
                drawn.append(curve)
    if base_key is not None:
        on_left = True
        points = kind in ("yield", "rate") or (kind == "amount" and solo.relative)
        _against_base(ax_yield, drawn, points)

    # The axes as the nations' charts set them, for the one family of curves drawn; against a base, the yield axis
    # alone, in percent, its label saying from what.
    measured = replace(solo, price_base=price_base)
    mark_amounts_currency(figure, None if base_key else currency)
    mark_price_base(figure, price_base)
    mark_dates_only(figure)
    metadata = _METADATA_BY_CURRENCY[currency] if currency is not None else US
    if currency is not None:
        metadata = replace(metadata, currency_prefix=CURRENCY_SYMBOLS[currency])
    if base_key is None:
        apply_axes_formatting(ax_yield, ax_macro, measured, metadata, None, extra_axis)
    else:
        on_yield_axis = replace(measured, **(_EVERY_CURVE_OFF | {"include_yield": True, "yield_terms": ("10y",)}))
        apply_axes_formatting(ax_yield, ax_macro, on_yield_axis, metadata, _base_axis_label(drawn[0].nation, points), None)
    # --reg: each nation's amount or population fitted by straight pieces, now that the axis limits are set; none
    # against a base, whose curves are differences, not the series the segments fit.
    rate_labels: list[RateLabel] = []
    if measured.regression and base_key is not None and kind in ("amount", "count"):
        print("  Note: --reg draws no segments on a comparison against a base nation.")
    if measured.regression and not on_left:
        for curve in drawn:
            rate_labels += add_regression_segments(ax_macro, curve.frame, curve.fitted, curve.projected, curve.config)
    handles = [handle for curve in drawn for handle in curve.handles]
    if any(column in curve.projected for curve in drawn for _line, column in curve.fitted) and kind == "amount":
        width = max(style["linewidth"] for style in MACRO_PLOT_STYLES.values()) * measured.line_scale
        handles.append(Line2D([], [], color=PROJECTION_KEY_COLOR, linewidth=width, alpha=PROJECTION_ALPHA, label=PROJECTION_LABEL))
    if rate_labels:
        handles.append(regression_legend_entry(measured))
    quote_time = max(quotes) if quotes else None
    if quote_time is not None:
        mark_quote(figure, quote_time, MARKET_TIMEZONE)
    title, short_title = _titles(drawn, measure, measured, drawn[0].nation if base_key else None)
    finish_legend_and_title(
        ax_yield,
        [handles, []] if on_left else [[], handles],
        title,
        measured,
        drawn_date_span((ax_yield, ax_macro)),
        [label for curve in drawn for label in curve.end_labels] if measured.end_labels else [],
        quote_time,
        rate_labels,
        MARKET_TIMEZONE,
        short_title,
        None,
    )


def _artists(*axes: Axes) -> set[Artist]:
    """The lines and filled areas on ``axes``: those a nation's drawing adds are recoloured for it (``_as_nation``)."""
    return {artist for ax in axes for artist in (*ax.get_lines(), *ax.collections)}


def _as_nation(added: set[Artist], nation: Nation) -> None:
    """Give the lines and bands a nation's curve added its colour, and its name where it is exported and read out ("Canada: 10-Year Yield").

    Its legend entry is named after this (``draw_compare``); every other
    label is hidden from the legend, which has one entry for each nation.
    """
    colour = COMPARE_COLOURS[nation.key]
    for artist in added:
        artist.set_color(colour)
        if isinstance(artist, Line2D):
            if not artist.get_label().startswith("_"):
                artist.set_label("_nolegend_")
            marked = series_of(artist)
            if marked is not None:
                mark_series(artist, f"{nation.name}: {marked[0]}", marked[1])


def _draw_yield(country: Country, ax: Axes, yields: pd.DataFrame, own: PlotConfig, nation: Nation) -> _Drawn | None:
    """A yield term, by the nation's own yield drawer (its monthly history in steps, its daily data as a line), solid (``_SOLID``)."""
    before = len(ax.get_lines())
    lines = country.draw_yield_lines(ax, yields, own)
    if not lines:
        return None
    for line in ax.get_lines()[before:]:
        line.set_linestyle(_SOLID["linestyle"])
    return _Drawn(nation, lines[:1], [(lines[0], format_yield)], own)


def _draw_rate(ax: Axes, rates: list, own: PlotConfig, nation: Nation) -> _Drawn | None:
    """The policy rate or inflation, by ``plotting.add_rate_lines``: held in steps, a change announced drawn from its day, the U.S. target range a band; solid (``_SOLID``)."""
    pairs = add_rate_lines(ax, [replace(curve, style=curve.style | _SOLID) for curve in rates], own)
    if not pairs:
        return None
    line, curve = pairs[0]
    return _Drawn(nation, [], [(last_piece(line), _end_label_format(curve, own))], own, pairs=pairs)


def _draw_amount(
    ax: Axes, macro: pd.DataFrame, own: PlotConfig, nation: Nation, metadata: CountryMetadata, currency: str | None
) -> _Drawn | None:
    """Debt, GDP or interest, by ``plotting.add_macro_line``, as the nation's chart draws it but solid (``_SOLID``): Canada's federal debt alone before its aggregate dotted, the projection faint."""
    measure = own.compare_measure
    keys = {"debt": ("debt", "federal_debt"), "gdp": ("gdp",), "interest": ("interest",)}[measure]
    macro_format = format_percent if own.relative else partial(format_currency, prefix=CURRENCY_SYMBOLS[currency])
    projected = macro.attrs.get(PROJECTION_ATTR, {})
    in_range = filter_to_date_range(macro, DATE_COLUMN, own)
    aggregate_debt = metadata.debt_column in macro.columns
    lines: list[tuple[Line2D, str]] = []
    for style_key, enabled, column, label in metadata.macro_specs(own, aggregate_debt=aggregate_debt):
        if style_key not in keys:
            continue
        line = add_macro_line(
            ax,
            in_range,
            enabled=enabled,
            column=column,
            label=label,
            style=MACRO_PLOT_STYLES[style_key] | ({} if style_key == "federal_debt" else _SOLID),
            value_format=macro_format,
            projected_from=projected.get(column),
            filled=own.daily and SERIES_KINDS[style_key].filled_in,
            # A change in the read-out (batch 44), as on the nation's chart: in the amounts' currency, under -r in bp or pp.
            amount=None if own.relative else macro_format,
        )
        if line is not None:
            lines.append((line, column))
    if not lines:
        return None
    end_labels = [
        (line, (lambda value, fmt=macro_format: PROJECTION_LABEL_PREFIX + fmt(value)) if column in projected else macro_format)
        for line, column in lines
    ]
    return _Drawn(nation, [lines[0][0]], end_labels, own, fitted=lines, frame=macro, projected=projected)


def _draw_count(ax: Axes, macro: pd.DataFrame, own: PlotConfig, nation: Nation) -> tuple[_Drawn | None, ExtraCurve | None]:
    """The population, by ``plotting.add_macro_line``, as the nation's chart draws it on its extra axis: through its points, filled in with daily values."""
    extra: ExtraCurve | None = macro.attrs.get(EXTRA_CURVE_ATTR)
    if extra is None:
        return None, None
    kind = SERIES_KINDS[extra.kind]
    filled = own.daily and kind.filled_in
    frame = pd.DataFrame({DATE_COLUMN: extra.values.index, extra.label: extra.values.to_numpy()})  # its observations, --reg's
    if filled:
        points = (
            filled_through(extra.values, extra.kind, own) if kind.period is not None
            else cut_to(extra.values.dropna().sort_index(), own.start, own.end)
        )
        in_range = pd.DataFrame({DATE_COLUMN: points.index, extra.label: points.to_numpy()})
    else:
        in_range = filter_to_date_range(frame, DATE_COLUMN, own)
    line = add_macro_line(
        ax, in_range, enabled=True, column=extra.label, label=extra.label, style=extra.style,
        value_format=extra.value_format, axis=extra.export_axis, filled=filled,
        amount=format_population,  # a change in the read-out (batch 44), as on the nation's chart
    )
    if line is None:
        return None, extra
    return _Drawn(nation, [line], [(line, extra.value_format)], own, fitted=[(line, extra.label)], frame=frame), extra


def _titles(drawn: list[_Drawn], measure: str, config: PlotConfig, base: Nation | None = None) -> tuple[str, str]:
    """The chart's title and its short form: "Canadian, US, UK & German 10-Year Yields", "CDN, US, UK & DEU 10-Year Yields" (decision 50's words for each nation).

    Against a base nation (batch 26.3) the others are named, then the base:
    "Canadian, UK & German 10-Year Yields (base: United States)", short
    "(base: US)"; the base alone where no other is drawn.
    """
    phrase = compare_title(measure) + (measure_title_suffix(config) if compare_kind(measure) == "amount" else "")
    if not drawn:
        return f"{phrase} compared: none of the nations ticked has it", f"{phrase} compared: none of the nations ticked has it"

    def joined(words: list[str]) -> str:
        return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} & {words[-1]}"

    named = [curve for curve in drawn if base is None or curve.nation.key != base.key] or drawn
    long = [_METADATA[curve.nation.key].title_nation for curve in named]
    short = [_METADATA[curve.nation.key].title_short or _METADATA[curve.nation.key].title_nation for curve in named]
    if base is None:
        return f"{joined(long)} {phrase}", f"{joined(short)} {phrase}"
    own = _METADATA[base.key]
    return f"{joined(long)} {phrase} (base: {base.name})", f"{joined(short)} {phrase} (base: {own.title_short or own.title_nation})"


# ---------------------------------------------------------------------------
# Against a base nation (batch 26.3; Terry, 2026-11-12, decision 147: "That
# nations data would then be a flat line at 0% on the chart, and all the others
# would be % plus or minus around it")
# ---------------------------------------------------------------------------

# A band's upper limits (the U.S. target range, ``plotting._add_band``), told by how they are exported.
_UPPER_LIMIT = ", upper limit"


def _upper(line: Line2D) -> bool:
    marked = series_of(line)
    return marked is not None and marked[0].endswith(_UPPER_LIMIT)


def _drawn_lines(curve: _Drawn) -> list[Line2D]:
    """A curve's lines with data still drawn, in the order they start."""
    lines = [
        artist for artist in curve.artists
        if isinstance(artist, Line2D) and artist.axes is not None and np.isfinite(np.asarray(artist.get_xydata(), dtype=float)[:, 0]).any()
    ]
    return sorted(lines, key=lambda line: float(np.nanmin(np.asarray(line.get_xydata(), dtype=float)[:, 0])))


def _pieces(lines: list[Line2D]) -> list[tuple[np.ndarray, np.ndarray, bool]]:
    """Each line's points and whether it is stepped, copied: what ``_value_at`` reads, unchanged when the lines are."""
    pieces = []
    for line in lines:
        xy = np.array(line.get_xydata(), dtype=float)
        pieces.append((xy[:, 0], xy[:, 1], line.get_drawstyle().startswith("steps")))
    return pieces


def _value_at(lines: list[Line2D] | list[tuple[np.ndarray, np.ndarray, bool]], x: np.ndarray) -> np.ndarray:
    """What ``lines``, the pieces of one curve (or their ``_pieces``), draw at each date ``x`` (day numbers): NaN where none does.

    A stepped piece holds each value to the next (the value in force), any
    other runs straight between its points (its daily values, a projection);
    a later piece wins where two meet. A break (NaN) stays one.
    """
    out = np.full(len(x), np.nan)
    pieces = _pieces(lines) if lines and isinstance(lines[0], Line2D) else lines
    for xs, ys, stepped in pieces:
        inside = (x >= xs[0]) & (x <= xs[-1])
        if not inside.any():
            continue
        if stepped:
            values = ys[np.searchsorted(xs, x[inside], side="right") - 1]
        else:
            values = np.interp(x[inside], xs, ys)  # NaN beside a break, as drawn
        out[inside] = np.where(np.isfinite(values), values, out[inside])
    return out


def _signed_percent(value: float, places: int) -> str:
    """A difference as the chart writes it: "+0.85%", "−12.3%" (a true minus, decision 129), rounded half away from zero (decision 130)."""
    figure = rounded(value, places)
    sign = "+" if figure > 0 else "−" if figure < 0 else ""
    return f"{sign}{abs(figure):.{places}f}%"


def _base_axis_label(base: Nation, points: bool) -> str:
    """The yield axis's label against a base nation: "Difference from United States (percentage points)", "% above or below Germany"."""
    return f"Difference from {base.name} (percentage points)" if points else f"% above or below {base.name}"


def _against_base(ax: Axes, drawn: list[_Drawn], points: bool) -> None:
    """Make every curve of ``drawn`` its difference from the first's, the base nation's, which is drawn flat at 0.

    ``points``: a measure in percent (a yield, a rate, a share of GDP under
    -r), its difference in percentage points; otherwise (an amount in a
    currency, GDP, the population) the percentage above or below the base's.
    At each date a curve's value less the base's then in force; before the
    base's first value, or past its last, nothing. Each curve keeps its
    pieces and their steps: a piece is given the base's dates within its own,
    so a change of the base's shows where it falls. The U.S. target range as
    the base: its midpoint; as another's curve, both limits made differences
    and the band between them shaded again. The read-out, Export chart and
    the line labels write the differences ("+0.85%", "Canada: 10-Year Yield,
    less United States").
    """
    base = drawn[0]
    base_lines = _drawn_lines(base)
    # The base's values copied before any line is changed: its own are made 0 first.
    lower = _pieces([line for line in base_lines if not _upper(line)])
    upper = _pieces([line for line in base_lines if _upper(line)])
    base_dates = np.unique(np.concatenate([xs for xs, _ys, _stepped in lower]))

    def base_at(x: np.ndarray) -> np.ndarray:
        low = _value_at(lower, x)
        high = _value_at(upper, x) if upper else np.full(len(x), np.nan)
        return np.where(np.isfinite(high), (low + high) / 2.0, low)

    places = 2 if points else 1
    writer = partial(_signed_percent, places=places)
    phrase = "less" if points else "% above or below"
    for curve in drawn:
        shading = [artist for artist in curve.artists if not isinstance(artist, Line2D)]
        uppers = {line for line in _drawn_lines(curve) if _upper(line)}  # told before their names change below
        for line in _drawn_lines(curve):
            if curve is base and line in uppers:
                line.remove()  # the base is one line, at its midpoint
                continue
            xy = np.asarray(line.get_xydata(), dtype=float)
            if curve is base:
                x = xy[:, 0]
                y = np.where(np.isfinite(xy[:, 1]) & np.isfinite(base_at(x)), 0.0, np.nan)
            else:
                x = np.union1d(xy[:, 0], base_dates[(base_dates >= xy[0, 0]) & (base_dates <= xy[-1, 0])])
                own, at_base = _value_at([line], x), base_at(x)
                with np.errstate(invalid="ignore", divide="ignore"):
                    y = own - at_base if points else np.where(at_base > 0, (own / at_base - 1.0) * 100.0, np.nan)
            line.set_data(x, y)
            remark_reading(line, writer)
            marked = series_of(line)
            if marked is not None:
                said = "the base" if curve is base else f"{phrase} {base.nation.name}"
                name = marked[0].replace(", lower limit", ", midpoint") if curve is base and uppers else marked[0]  # a range as base
                mark_series(line, f"{name}, {said}", YIELD_AXIS)
        for band in shading:  # a band's shading (the U.S. target range), drawn again between its limits as they now are
            colour, alpha = band.get_facecolor()[0][:3], band.get_alpha()
            band.remove()
            if curve is base:
                continue
            lines = _drawn_lines(curve)
            limits = [line for line in lines if line in uppers]
            if not limits:
                continue
            lows = [line for line in lines if line not in uppers]
            x = np.unique(np.concatenate([np.asarray(line.get_xydata(), dtype=float)[:, 0] for line in lines]))
            low, high = _value_at(lows, x), _value_at(limits, x)
            ax.fill_between(x, low, high, where=np.isfinite(high), step="post", color=colour, alpha=alpha,
                            linewidth=0, label="_nolegend_")
        # The line labels write the differences, a projected amount's still marked "≈" (PROJECTION_LABEL_PREFIX).
        curve.end_labels = [
            (line, (lambda value: PROJECTION_LABEL_PREFIX + writer(value)) if _says_projected(formatter) else writer)
            for line, formatter in curve.end_labels if line.axes is not None
        ]
    # The base's legend entry a plain line in its colour (a band's key no longer stands for anything drawn).
    first = next((line for line in _drawn_lines(base)), None)
    if first is not None:
        base.handles = [Line2D([], [], color=first.get_color(), linewidth=first.get_linewidth(), label=base.nation.name)]


def _says_projected(formatter) -> bool:
    """True for a line label's formatter that marks a projection to today (``_draw_amount``'s, "≈" first)."""
    try:
        return formatter(1.0).startswith(PROJECTION_LABEL_PREFIX)
    except Exception:  # noqa: BLE001 - a formatter that takes no plain number marks nothing
        return False
