"""The other curves on the yield (left) axis: policy rates, mortgage rates and yield spreads.

They are additive and off by default: each is drawn only when its option is
given (--policy, --mortgages, --spreads), and naming one does not hide the
default curves (they are not under the curve rule of ``options``). Each
country's are fetched by ``rate_curves`` into ``RateCurve`` records, which
``plotting.draw_country`` draws on the yield axis after the yields, in the
yields' legend group; ``plotting.curve_first_dates`` counts them for the
automatic start only when chosen.

Every value is a percentage (a spread, percentage points), dated by the day
it applies from. A source that fails prints a ``Warning:`` and its curve is
left out; nothing is substituted silently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pandas as pd

from .announced import Releases, announcements_needed, boc_releases, boe_releases, joined
from .baked import read_series
from .cdn_data import BOC_VALET_FROM, STATCAN_BAKED_SOURCE, boc_valet_series, statcan_download
from .config import (
    CANADIAN_YIELD_HIST_END,
    CDN_MORTGAGE_HISTORY_TABLE,
    CDN_MORTGAGE_HISTORY_VECTOR,
    DATE_COLUMN,
    MORTGAGE_MARGINS,
    MORTGAGE_OWN_COLORS,
    MORTGAGE_STYLE,
    MORTGAGE_TERMS,
    POLICY_MARKET_STYLE,
    POLICY_RATE_STYLE,
    POLICY_TERMS,
    PRIME_RATE_STYLE,
    SPREAD_COLORS,
    SPREAD_STYLE,
    TERM_COLORS,
    VARIABLE_MORTGAGE_STYLE,
    YIELD_TERMS,
    PlotConfig,
    nation_by_key,
)
from .de_archive_data import EMBEDDED_DE_DISCOUNT_RATE_CHANGES
from .de_data import ecb_series
from .de_data import YIELD_HISTORY_ATTR as DE_YIELD_HISTORY_ATTR
from .http import downloads_of
from .uk_archive_data import EMBEDDED_UK_BANK_RATE_HISTORY, EMBEDDED_UK_MORTGAGE_HISTORY
from .uk_data import YIELD_HISTORY_ATTR, iadb_series
from .us_data import fred_series

# Policy rates (--policy:LIST; batch 9.1, Terry's decision 27, 2026-10-13):
# each central bank's official rate ("target", the default) and the overnight
# market's rate around it ("market"), which moves day to day. Measured
# 2026-10-21.
#
# The market's rate is named as such in the legend, its acronym kept (batch
# 24.5; Terry, 2026-10-24, decision 59): the same first words on every chart
# say what it is, the acronym in brackets is what people search for.
OVERNIGHT_RATE_NAMED = "Overnight Rate ({})"
#
# U.S. target: the Federal Reserve's target for the federal funds rate (FRED
# DFEDTAR, daily 1982-09-27 to 2008-12-15), then its target range (DFEDTARL
# and DFEDTARU, daily from 2008-12-16, a quarter point wide on every day),
# drawn as a band; before the target, the effective rate's monthly average
# (FEDFUNDS, from 1954-07), which equals the daily rate's calendar-day mean
# to within 0.005 points. Market: the effective rate (DFF, daily from
# 1954-07-01), outside the range on 7 days of 6,517 since 2008-12-16.
US_MARKET_SERIES = "DFF"
US_MONTHLY_EFFECTIVE_SERIES = "FEDFUNDS"
US_TARGET_SERIES = "DFEDTAR"
US_TARGET_RANGE_SERIES = ("DFEDTARL", "DFEDTARU")
# A series whose source has stopped is declared with the date of its last
# value, and drawn from its bake alone, with no request and no warning (batch
# 19.3, Terry's decision 51, 2026-10-22; ``baked.with_recent_part``): before
# it, every U.S. chart with --policy asked FRED for DFEDTAR's last two months
# of 2008. The others: the ECB's minimum bid rate and EONIA, below.
US_TARGET_ENDED = pd.Timestamp("2008-12-15")
# Canada's target: the Bank Rate until 1996-02-22, when the Bank of Canada set
# it at the top of its operating band for the overnight rate, a quarter point
# above the target at the band's middle; then that target. The Bank Rate
# monthly from 1935 (V122530: each month's last Wednesday, dated by the
# month's first day, in all 561 months from 1980), weekly (Wednesdays) from
# 1980-01-02 (V80691310). The target daily from 2001 (CBC20210), and before
# that the weekly Bank Rate less a quarter point, which equals the daily
# target on all 1,346 Wednesdays since 2001 (so a change made between
# Wednesdays in 1996-2000 shows from the next Wednesday). Market: the
# Canadian Overnight Repo Rate Average (CORRA), daily from 1997-08-12.
CDN_BANK_RATE_SERIES = "V122530"
CDN_WEEKLY_BANK_RATE_SERIES = "V80691310"
CDN_TARGET_SERIES = "CBC20210"
CDN_TARGET_FROM = pd.Timestamp("1996-02-22")
CDN_BANK_RATE_ABOVE_TARGET = 0.25
CDN_CORRA_SERIES = "AVG.INTWO"

# Mortgage rates (--mortgages), by term (config.MORTGAGE_TERMS). U.S.: Freddie
# Mac's survey averages, weekly, on FRED (30-year from 1971, 15-year from 1991).
# Canada: the chartered banks' posted rates, weekly on Valet (5-year from 1975,
# 3- and 1-year from 1980), the 5-year carried back to 1951 by Statistics
# Canada's monthly CMHC conventional 5-year lending rate (table 34-10-0145);
# and the 5-year variable rate, the brokers' average, from 2011. Spans
# measured by Terry 2026-10-06. The chartered banks' prime rate, weekly on
# Valet from 1975: V80691311 (found by a web search; fetched by
# tools/check_sources.py boc_prime on Terry's machine, 2026-10-06). The U.S.
# banks' prime loan rate (batch 9.4): FRED DPRIME, the Federal Reserve's H.15,
# daily from 1955-08 (7.00 % on 2026-10-02, measured 2026-10-13); by
# convention the top of the fed funds target range plus 3 points.
US_MORTGAGE_SERIES = {"30": "MORTGAGE30US", "15": "MORTGAGE15US", "prime": "DPRIME"}
CDN_MORTGAGE_SERIES = {"5": "V80691335", "3": "V80691334", "1": "V80691333", "5v": "BROKER_AVERAGE_5YR_VRM", "prime": "V80691311"}
# Batch 19.2: each drawing asks Valet for a baked series' last two months
# (config.RECENT_PART_UNREVISED), the rates being announced or observed, not
# revised; the brokers' variable rate, which Valet calls an estimate, for its
# last 24 (RECENT_PART_REVISED), as the UK's quoted rates (survey results).
# None of the 20 changed a value from late September to 2026-10-22 (measured).
_CDN_REVISED_SERIES = {CDN_MORTGAGE_SERIES["5v"]}
# FRED's (us_data.fred_series): the policy and prime rates are announced or
# observed, two months; Freddie Mac's mortgage rates are a survey's, 24, as
# the UK's quoted rates. None of the eight changed a value from the regression
# cache's downloads (2026-10-06 to 2026-10-21) to 2026-10-22 (measured).
_US_REVISED_SERIES = {US_MORTGAGE_SERIES["30"], US_MORTGAGE_SERIES["15"]}
# The UK (batch 3), from the Bank of England's database (IADB), measured from
# Terry's laptop 2026-10-06: Bank Rate daily from 1975, and before it its
# changes since 1833 (the millennium dataset, baked). Mortgages: the Bank's
# quoted rates for new loans at 75 % loan to value, monthly from 1995, the
# standard variable rate carried back to 1939 by the millennium dataset's
# spliced variable mortgage rate (baked). IADB dates a month by its last
# day; here by its first, as Canada's monthly rates are, so its step covers it.
# The UK's market rate (batch 9.1): the Sterling Overnight Index Average
# (SONIA), daily from 1997-01-02.
UK_POLICY_SERIES = "IUDBEDR"
UK_MARKET_SERIES = "IUDSOIA"
# The tracker (batch 9.5, Terry's decision 26) is Bank Rate itself, daily,
# plus a margin (``PlotConfig.tracker_margin``), so no new source: its entry
# here is Bank Rate's code, for messages and the checks (``_uk_tracker``).
UK_MORTGAGE_SERIES = {"2f": "IUMBV34", "3f": "IUMBV37", "5f": "IUMBV42", "svr": "IUMTLMV", "tracker": UK_POLICY_SERIES}
# It is drawn from the first month the Bank of England quoted a tracker
# rate (its lifetime tracker, IUMBV24, 1997-01 to 2025-03, measured
# 2026-10-21): before then a "tracker" would be Bank Rate under another name,
# and Bank Rate is drawn back to 1833 (``uk_policy_target``).
UK_TRACKER_FROM = pd.Timestamp("1997-01-01")
# Germany (batch 4), from the ECB Data Portal, measured from Terry's laptop
# 2026-10-06. Policy: the main refinancing rate, on the days it changed since
# 1999: the fixed rate of the fixed-rate tenders, and from 2000-06-28 to
# 2008-10-14, when the tenders were variable, their minimum bid rate; before
# it, the Bundesbank's discount rate from 1948-07, on the days it changed
# (batch 9.6, baked: ``de_archive_data``). Mortgages:
# the MFI interest rates on new housing loans to households in Germany, by
# initial rate fixation, monthly from 2000 (2000-2002 the ECB's estimates;
# reported from 2003), dated by each month's first day as the UK's are.
DE_POLICY_FIXED = ("FM", "B.U2.EUR.4F.KR.MRR_FR.LEV", "PCPA")
DE_POLICY_MINIMUM_BID = ("FM", "B.U2.EUR.4F.KR.MRR_MBR.LEV", "PCPA")
DE_MINIMUM_BID_ENDED = pd.Timestamp("2008-10-08")  # stopped (batch 19.3: see US_TARGET_ENDED)
# Germany's market rate (batch 9.1), the euro area's: the euro overnight index
# average (EONIA, daily 1999-01-04 to 2021-12-31) until the euro short-term
# rate (€STR) begins, daily from 2019-10-01. EONIA was €STR plus 0.085 points
# on every day both were published, so the line steps down 0.085 at the join.
DE_EONIA = ("EON", "D.EONIA_TO.RATE", "PC")
DE_EONIA_ENDED = pd.Timestamp("2021-12-31")  # stopped (batch 19.3: see US_TARGET_ENDED)
DE_ESTR = ("EST", "B.EU000A2X2A25.WT", "PC")
DE_MORTGAGE_SERIES = {"1-5": "M.DE.B.A2C.I.R.A.2250.EUR.N", "5-10": "M.DE.B.A2C.O.R.A.2250.EUR.N", "over10": "M.DE.B.A2C.P.R.A.2250.EUR.N"}
# The ECB's flow of the MFI interest rate statistics and the unit its mortgage
# rates are given in (a rate per year), for every band of DE_MORTGAGE_SERIES.
DE_MORTGAGE_FLOW = "MIR"
DE_MORTGAGE_UNIT = "PCPA"
# Batch 19.2 (de_data.ecb_series, each call says which): the ECB's key rates
# are announced and EONIA and €STR observed, so a drawing asks for their last
# two months (since 19.3 not EONIA's or the minimum bid rate's: they have
# stopped, and are drawn from their bake alone); the mortgage rates are
# statistics the banks report, which the ECB may revise, so their last 24, as
# the UK's quoted rates and Freddie Mac's.
# None of the seven changed a value from the regression cache's downloads
# (2026-10-07 and 2026-10-21) to 2026-10-22 (measured).
_MORTGAGE_LABELS = {
    "30": "30-Year Mortgage",
    "15": "15-Year Mortgage",
    "5": "5-Year Mortgage (posted)",
    "3": "3-Year Mortgage (posted)",
    "1": "1-Year Mortgage (posted)",
    "5v": "5-Year Variable Mortgage (broker avg.)",
    "prime": "Prime Rate (chartered banks)",  # Canada's; the U.S.' is _US_PRIME_LABEL
    # The UK's and Germany's (batch 10.1, Terry 2026-10-08): no "fixed", as
    # for Canada and the U.S., where it is implied; no "quoted". The UK's
    # "75% LTV" stays: the Bank quotes the same loans at 90 and 95 % too, and
    # they differ (the 2-year 2.79 % at 75 % since 2015, 3.55 at 90, 4.37 at 95).
    "2f": "2-Year Mortgage (75% LTV)",
    "3f": "3-Year Mortgage (75% LTV)",
    "5f": "5-Year Mortgage (75% LTV)",
    "svr": "Standard Variable Rate (SVR)",
    "tracker": "Tracker Mortgage (Bank Rate)",  # its margin inside the brackets (_mortgage_label)
    "1-5": "1–5-Year Mortgage (new loans, avg.)",
    "5-10": "5–10-Year Mortgage (new loans, avg.)",
    "over10": "Over-10-Year Mortgage (new loans, avg.)",
}
# The U.S. prime rate by the name the Federal Reserve's H.15 gives it.
_US_PRIME_LABEL = "Bank Prime Loan Rate"

# How long a value drawn as a step holds (batch 17.3; Terry, decision 44,
# 2026-10-21), declared with its source rather than read from its dates. An
# announced rate (a central bank's rate, a prime rate) holds until it is
# changed, at whatever irregular times: each value to the next, the last to
# the chart's end. An observed one (a market's overnight rate, a survey, an
# average) holds for its own period only, whether or not the next value has
# come (Terry, 2026-10-20: "There is no point extrapolating (even at a
# constant value) beyond what the quotes have implied"). For each observed
# kind: the period its last value is drawn across, and the longest step to the
# next value still drawn as one, so a holiday or a release moved by a day
# breaks nothing. Measured 2026-10-21: the daily sources' longest step 6 days
# (CORRA), the weekly ones' 9 (the U.S. 30-year, released on a Wednesday in a
# holiday week); the monthly ones are dated by each month's first day. The
# 5-year variable rate's missing stretches (28 days from 2013-05-30, 14 from
# 2014-12-04) are breaks.
HELD = "held"
OBSERVED = {
    "daily": (pd.offsets.BDay(1), pd.Timedelta(days=7)),
    "weekly": (pd.Timedelta(days=7), pd.Timedelta(days=10)),
    "monthly": (pd.offsets.MonthBegin(1), pd.Timedelta(days=31)),
}
# An observed value's period is drawn to a second before it ends, so the
# subtitle, which names the last day drawn, names the period's last day (an
# August average: 08-31, not 09-01).
_PERIOD_END_MARGIN = pd.Timedelta(seconds=1)
_MORTGAGE_HOLDS = {"us": "weekly", "cdn": "weekly", "uk": "monthly", "de": "monthly"}


def holding(values: pd.Series, kind: str) -> pd.Series:
    """Return ``kind`` (``HELD`` or a key of ``OBSERVED``) for each of ``values``, as ``RateCurve.holds`` takes it."""
    assert kind == HELD or kind in OBSERVED, kind
    return pd.Series(kind, index=values.index, dtype=object)


def _mortgage_label(term: str, country: str, margin: float) -> str:
    """Return a mortgage term's legend label; a term drawn plus a margin with it, when there is one.

    "Prime Rate + 0.50 (chartered banks)", "Bank Prime Loan Rate – 0.25"
    (batch 9.4, Terry 2026-10-08: the margin "shown in the legend"); the
    tracker's inside its brackets, "Tracker Mortgage (Bank Rate + 1.75)"
    (batch 9.5). Two decimals, three when the margin has a third (an eighth
    of a point). Below the base rate an en dash, as in the spreads' labels:
    the minus sign (U+2212) is not in the Windows code page a redirected
    log is written in, and the labels are printed in messages.
    """
    label = _US_PRIME_LABEL if (term, country) == ("prime", "us") else _MORTGAGE_LABELS[term]
    if margin == 0:
        return label
    size = abs(margin)
    written = f"{size:.2f}" if round(size, 2) == size else f"{size:.3f}".rstrip("0")
    signed = f" {'+' if margin > 0 else '–'} {written}"
    if term == "tracker":
        return label.removesuffix(")") + signed + ")"
    name, _space, whose = label.partition(" (")
    return f"{name}{signed}" + (f" ({whose}" if whose else "")


@dataclass(frozen=True)
class RateCurve:
    """One curve on the yield axis other than the yields themselves."""

    key: str  # what it is, for its style and tests: "policy", "mortgage_30", "spread_10y-2y"
    label: str  # its legend label
    values: pd.Series  # date-indexed, sorted, in percent (a spread: percentage points); no missing values
    style: dict = field(default_factory=dict)  # matplotlib line properties
    # Drawn as steps up to and including this date and as a line after it (the
    # Canadian yields' monthly history before 2001); None: as ``style`` says.
    steps_until: pd.Timestamp | None = None
    # A spread: drawn thick, its inverted stretches (below zero) shaded, and
    # its end label written in basis points ("+47 pts" for 0.47 points).
    spread: bool = False
    title: str = ""  # its phrase in the chart title ("Policy Rate"); curves of a kind share one
    # The yield column whose drawn colour it takes, if that yield is on the
    # chart (a mortgage: its term's yield); its style's colour otherwise.
    color_of: str | None = None
    # How long each value holds (``HELD`` or a key of ``OBSERVED``), one per
    # value, so a curve joined from two sources can have both kinds (the U.S.
    # target: the monthly average, then the announced target); drawn by
    # ``held_steps``. None: the yields' rule, ``in_window`` (the spreads,
    # taken from the yields).
    holds: pd.Series | None = None
    # A band (batch 9.1, the U.S. target range): its upper limits, one per
    # value, ``values`` being its lower; equal to ``values`` where the rate
    # is a single one. Drawn as two step lines, shaded between them.
    upper: pd.Series | None = None
    # A curve joined from several sources: each part's first date, its name
    # alone, and its name after another ("Target" in "Fed Funds Rate (monthly
    # avg.), Target from 1982-09"). The legend names only the parts the
    # window shows (``legend_label``); ``label`` names them all.
    parts: tuple[tuple[pd.Timestamp, str, str], ...] = ()
    # The words the parts' names are written in ("Overnight Rate ({})" around
    # "EONIA, €STR from 2019-10", batch 24.5); "{}": the names alone.
    named_in: str = "{}"
    # A policy rate's first day drawn from its bank's announcement rather than
    # its series (batch 32, ``with_announced``): drawn as a piece of its own,
    # named in the legend ("Announced from 2026-10-29") and the read-out.
    announced: pd.Timestamp | None = None

    @property
    def first(self) -> pd.Timestamp:
        """The first date with a value (the automatic start counts it)."""
        return pd.Timestamp(self.values.index[0])


def _named(parts: tuple[tuple[pd.Timestamp, str, str], ...]) -> str:
    """Return the label of a curve made of ``parts`` (``RateCurve.parts``): "Bank Rate, Overnight Target from 1996-02"."""
    (_date, name, _after), *rest = parts
    return ", ".join([name, *(f"{after} from {date:%Y-%m}" for date, _name, after in rest)])


def legend_label(curve: RateCurve, config: PlotConfig) -> str:
    """Return ``curve``'s legend label: of a curve joined from several sources, the parts the window shows (batch 9.1).

    "Fed Funds Rate (monthly avg.), Target from 1982-09, Range from 2008-12"
    on a chart from 1970, "Fed Funds Target Range" on one from 2015. A part
    is shown from its first date to the next part's (an announced rate's
    last value is in force until then), in the curve's own words
    (``RateCurve.named_in``: "Overnight Rate (€STR)" on a chart from 2022).
    A curve of one source: its label. A change drawn from its bank's
    announcement (batch 32) is named after them as a part, by its day:
    "Official Bank Rate, Announced from 2026-11-05".
    """
    if not curve.parts:
        label = curve.label
    else:
        shown = tuple(
            part
            for position, part in enumerate(curve.parts)
            if part[0] <= config.end and (position + 1 == len(curve.parts) or curve.parts[position + 1][0] > config.start)
        )
        label = curve.named_in.format(_named(shown or curve.parts[-1:]))
    if curve.announced is not None and curve.announced <= config.end:
        label += f", Announced from {curve.announced:%Y-%m-%d}"
    return label


def held_steps(curve: RateCurve, config: PlotConfig, values: pd.Series | None = None) -> pd.Series:
    """Return the points that draw ``curve`` as steps from ``config.start`` to ``config.end``; a NaN breaks the line.

    Each value is drawn from its date to the next value, and, as
    ``curve.holds`` declares it (batch 17.3, decision 44): an announced
    rate's last value on to the chart's end; an observed value only to the
    end of its own period, so a missing stretch is a break and the last value
    stops where its period does. The value in effect at the window's start is
    carried to it if it still applies there: an announced rate's always, so
    it has a line across the whole window however long since it last
    changed, and never an isolated point. Empty when no value applies in the
    window (``plotting.add_rate_lines`` says so). ``values``: the series
    stepped when not the curve's own (a band's upper limits, ``RateCurve.upper``,
    on the same dates, so its points fall on the same dates as the lower's).
    """
    values = curve.values if values is None else values
    holds = curve.holds
    assert holds is not None and holds.index.equals(values.index), curve.label
    start, end = config.start, config.end
    dates = values.index
    first = max(int(dates.searchsorted(start)) - 1, 0)  # the last value before the window, if any
    points: list[tuple[pd.Timestamp, float]] = []
    for position in range(first, len(dates)):
        date = dates[position]
        if date > end:
            break
        after = dates[position + 1] if position + 1 < len(dates) else None
        kind = holds.iloc[position]
        if kind == HELD:
            until = after if after is not None else pd.Timestamp.max
        else:
            period, longest = OBSERVED[kind]
            until = after if after is not None and after - date <= longest else date + period - _PERIOD_END_MARGIN
        if until <= start:
            continue  # it applies only before the window
        value = float(values.iloc[position])
        points.append((max(date, start), value))
        if after is None or after > end:  # the last drawn: on to the end of what it applies to
            stop = min(until, end)
            if stop > points[-1][0]:
                points.append((stop, value))
        elif until < after:  # its period ends before the next value comes
            points.append((until, float("nan")))
    if not points:
        return values.iloc[:0]
    return pd.Series([value for _date, value in points], index=pd.DatetimeIndex([date for date, _value in points]))


def in_window(values: pd.Series, config: PlotConfig) -> pd.Series:
    """Return ``values`` from ``config.start`` to ``config.end``, the value in effect at the start carried to it.

    The yields' rule, for the curves taken from them (the spreads): a window
    starting between two observations begins with the one before it, as the
    right-axis curves do (``us_data.fetch_us_macro``). The rates themselves
    are drawn by ``held_steps``.
    """
    inside = values.loc[(values.index >= config.start) & (values.index <= config.end)]
    before = values.loc[values.index < config.start]
    if before.empty or (not inside.empty and inside.index[0] == config.start):
        return inside
    carried = pd.Series([before.iloc[-1]], index=pd.DatetimeIndex([config.start]))
    return pd.concat([carried, inside])


def _clean(values: pd.Series) -> pd.Series:
    """Return a fetched series as a RateCurve holds it: numeric, date-sorted, without missing values."""
    values = pd.to_numeric(values, errors="coerce").dropna().sort_index()
    return values.set_axis(pd.DatetimeIndex(values.index).normalize())


def _valet(series_code: str) -> pd.Series:
    """Return one whole Bank of Canada Valet series, cleaned (``_clean``): its baked history and recent part (batch 19.2)."""
    return _clean(boc_valet_series(series_code, start=BOC_VALET_FROM, revised=series_code in _CDN_REVISED_SERIES))


def _fred(series_id: str, stopped: pd.Timestamp | None = None) -> pd.Series:
    """Return one whole FRED series, cleaned (``_clean``): its baked history and recent part (batch 19.2); a series ``stopped``, its bake alone (19.3)."""
    frame = fred_series(series_id, revised=series_id in _US_REVISED_SERIES, stopped=stopped)
    return _clean(frame.set_index("DATE")[series_id])


def _parts(*named: tuple[pd.Series, str, str]) -> tuple[tuple[pd.Timestamp, str, str], ...]:
    """Return ``RateCurve.parts`` for a curve joined from ``(values, name, name after another)``, the empty ones left out."""
    return tuple((pd.Timestamp(values.index[0]), name, after) for values, name, after in named if not values.empty)


def us_policy_target() -> RateCurve | None:
    """Return the federal funds target: a band between its range's limits from 2008-12-16, one rate from 1982-09-27, the effective rate's monthly average before.

    Each is its baked history and recent part (batch 19.2): if FRED fails,
    the bake to its last value, with a warning (``us_data.fred_series``).
    For a series neither baked nor answered: None, with a warning, if it is
    the target or either limit of its range (the 2008 target would be
    carried on to today); drawn from the target's first day, with a warning,
    if it is the monthly average.
    """
    low_code, high_code = US_TARGET_RANGE_SERIES
    try:
        target, low, high = _fred(US_TARGET_SERIES, US_TARGET_ENDED), _fred(low_code), _fred(high_code)
    except Exception as exc:
        print(f"  Warning: fed funds target ({US_TARGET_SERIES}, {low_code}, {high_code}) unavailable ({exc}); not drawn.")
        return None
    try:
        monthly = _fred(US_MONTHLY_EFFECTIVE_SERIES)
    except Exception as exc:
        print(f"  Warning: fed funds rate's monthly average ({US_MONTHLY_EFFECTIVE_SERIES}) unavailable ({exc}); "
              f"drawn from {target.index[0]:%Y-%m-%d}, the target's first day.")
        monthly = target.iloc[:0]
    low, high = low.align(high, join="inner")  # the days both limits have (the upper is sometimes a day ahead)
    target = target.loc[target.index < low.index[0]]
    monthly = monthly.loc[monthly.index < target.index[0]]
    # The monthly average is observed across its month (the last month's to
    # the target's first day); the target and its range are announced.
    lower, upper = pd.concat([monthly, target, low]), pd.concat([monthly, target, high])
    holds = pd.concat([holding(monthly, "monthly"), holding(target, HELD), holding(low, HELD)])
    parts = _parts(
        (monthly, "Fed Funds Rate (monthly avg.)", "Monthly Avg."),
        (target, "Fed Funds Target", "Target"),
        (low, "Fed Funds Target Range", "Range"),
    )
    return RateCurve("policy", _named(parts), lower, POLICY_RATE_STYLE, title="Policy Rate", holds=holds, upper=upper, parts=parts)


def us_policy_market(style: dict = POLICY_RATE_STYLE) -> RateCurve | None:
    """Return the effective federal funds rate (FRED DFF); None, with a warning, if it is neither baked nor answered."""
    try:
        values = _fred(US_MARKET_SERIES)
    except Exception as exc:
        print(f"  Warning: effective federal funds rate ({US_MARKET_SERIES}) unavailable ({exc}); not drawn.")
        return None
    # The rate banks paid each other that day: observed, not announced.
    return RateCurve("policy_market", OVERNIGHT_RATE_NAMED.format("Fed Funds, effective"), values, style, title="Policy Rate",
                     holds=holding(values, "daily"))


def cdn_policy_target() -> RateCurve | None:
    """Return the Bank Rate until 1996-02-22, then the target for the overnight rate (``CDN_TARGET_FROM``).

    Each is its baked history and recent part (batch 19.2): if Valet fails,
    the bake to its last date, with a warning (``cdn_data.boc_valet_series``).
    For a series neither baked nor answered: without the weekly Bank Rate,
    None with a warning; without the monthly one, drawn from 1980; without
    the daily target, the weekly Bank Rate less a quarter point to its last
    Wednesday; each with a warning.
    """
    try:
        weekly = _valet(CDN_WEEKLY_BANK_RATE_SERIES)
    except Exception as exc:
        print(f"  Warning: Bank of Canada weekly Bank Rate ({CDN_WEEKLY_BANK_RATE_SERIES}) unavailable ({exc}); "
              "no Canadian target; not drawn.")
        return None
    try:
        monthly = _valet(CDN_BANK_RATE_SERIES)
    except Exception as exc:
        print(f"  Warning: Bank of Canada monthly Bank Rate ({CDN_BANK_RATE_SERIES}) unavailable ({exc}); "
              f"drawn from {weekly.index[0]:%Y-%m-%d}.")
        monthly = weekly.iloc[:0]
    try:
        daily = _valet(CDN_TARGET_SERIES)
    except Exception as exc:
        print(f"  Warning: Bank of Canada target for the overnight rate ({CDN_TARGET_SERIES}) unavailable ({exc}); "
              "the weekly Bank Rate less a quarter point in its place, dated by Wednesdays.")
        daily = weekly.iloc[:0]
    bank = pd.concat([monthly.loc[monthly.index < weekly.index[0]], weekly.loc[weekly.index < CDN_TARGET_FROM]])
    until = daily.index[0] if not daily.empty else pd.Timestamp.max
    implied = weekly.loc[(weekly.index >= CDN_TARGET_FROM) & (weekly.index < until)] - CDN_BANK_RATE_ABOVE_TARGET
    target = pd.concat([implied, daily])
    values = pd.concat([bank, target])
    parts = _parts((bank, "Bank Rate", "Bank Rate"), (target, "Target for the Overnight Rate", "Overnight Target"))
    # Both are announced: each holds until it is changed.
    return RateCurve("policy", _named(parts), values, POLICY_RATE_STYLE, title="Policy Rate", holds=holding(values, HELD),
                     parts=parts)


def cdn_policy_market(style: dict = POLICY_RATE_STYLE) -> RateCurve | None:
    """Return CORRA, the overnight repo market's average (from 1997-08-12); None, with a warning, if it is neither baked nor answered."""
    try:
        values = _valet(CDN_CORRA_SERIES)
    except Exception as exc:
        print(f"  Warning: Bank of Canada CORRA ({CDN_CORRA_SERIES}) unavailable ({exc}); not drawn.")
        return None
    return RateCurve("policy_market", OVERNIGHT_RATE_NAMED.format("CORRA"), values, style, title="Policy Rate",
                     holds=holding(values, "daily"))


def _baked(rows: list[tuple[str, float]]) -> pd.Series:
    """Return a baked list of rates as a cleaned date-indexed series (``_clean``); empty if never baked."""
    return _clean(pd.Series([value for _date, value in rows], index=pd.DatetimeIndex([date for date, _value in rows])))


def _joined(history: pd.Series, live: pd.Series) -> pd.Series:
    """Return ``history`` until ``live`` begins, then ``live``."""
    return pd.concat([history.loc[history.index < live.index[0]], live]) if not live.empty else history


def uk_policy_target() -> RateCurve | None:
    """Return the Bank of England's official Bank Rate: its changes since 1833 (baked), then daily from 1975.

    The daily values are the database's baked history and its recent part
    (batch 19.2): if the database fails, the bake to its last date, with a
    warning (``uk_data.iadb_series``). Only a series neither baked nor
    answered leaves the millennium's changes alone (to 2017), with a
    warning; None if there is neither.
    """
    history = _baked(EMBEDDED_UK_BANK_RATE_HISTORY)
    try:
        live = _clean(iadb_series(UK_POLICY_SERIES))
    except Exception as exc:
        print(f"  Warning: Bank of England Bank Rate ({UK_POLICY_SERIES}) unavailable ({exc}); "
              + ("its baked changes alone, to 2017." if not history.empty else "not drawn."))
        live = history.iloc[:0]
    values = _joined(history, live)
    if values.empty:
        return None
    return RateCurve("policy", "Official Bank Rate", values, POLICY_RATE_STYLE, title="Policy Rate", holds=holding(values, HELD))


def uk_policy_market(style: dict = POLICY_RATE_STYLE) -> RateCurve | None:
    """Return SONIA, the sterling overnight market's average (from 1997-01-02); None, with a warning, if it is neither baked nor answered."""
    try:
        values = _clean(iadb_series(UK_MARKET_SERIES))
    except Exception as exc:
        print(f"  Warning: Bank of England SONIA ({UK_MARKET_SERIES}) unavailable ({exc}); not drawn.")
        return None
    return RateCurve("policy_market", OVERNIGHT_RATE_NAMED.format("SONIA"), values, style, title="Policy Rate",
                     holds=holding(values, "daily"))


def _uk_mortgage(term: str) -> pd.Series:
    """Return one UK mortgage term's monthly rate, dated by each month's first day.

    The standard variable rate is carried back by the baked variable
    mortgage rate (from 1939). Its label says nothing of the join (Terry,
    2026-10-08, batch 10.1: it read "Variable Mortgage Rate, quoted SVR from
    1995-01"): before the 1990s nearly every UK mortgage was at a standard
    variable rate, so "SVR" fits the whole line; --help says where it joins.
    The tracker is Bank Rate itself, daily (``_uk_tracker``). The quoted
    rates are the results of a survey, which the Bank may revise: each
    drawing asks for their last 24 months (batch 19.2), not two.
    """
    if term == "tracker":
        return _uk_tracker()
    monthly = iadb_series(UK_MORTGAGE_SERIES[term], revised=True)
    values = _clean(monthly.set_axis(monthly.index.to_period("M").start_time))
    history = _baked(EMBEDDED_UK_MORTGAGE_HISTORY) if term == "svr" else values.iloc[:0]
    if not history.empty and not values.empty and history.index[0] < values.index[0]:
        values = _joined(history, values)
    return values


def _uk_tracker() -> pd.Series:
    """Return Bank Rate from ``UK_TRACKER_FROM`` on, the rate a tracker follows (its margin is added by ``mortgage_rate``).

    The Bank of England's daily Bank Rate (``UK_POLICY_SERIES``), the value
    in effect on ``UK_TRACKER_FROM`` dated by it. From the database only (its
    baked history and recent part, batch 19.2), not the millennium's changes
    (to 2017): a tracker drawn from them would be carried on from 2017 as an
    announced rate is.
    """
    bank = _clean(iadb_series(UK_POLICY_SERIES))
    before = bank.loc[bank.index <= UK_TRACKER_FROM]
    first = before.iloc[-1:].set_axis(pd.DatetimeIndex([UK_TRACKER_FROM])) if not before.empty else before
    return pd.concat([first, bank.loc[bank.index > UK_TRACKER_FROM]])


def de_policy_target() -> RateCurve | None:
    """Return Germany's official rate: the Bundesbank's discount rate, then the ECB's main refinancing rate from 1999.

    The ECB's: fixed, the minimum bid while the tenders were variable, fixed
    again. Both series hold only the days the rate changed: each value is
    carried daily to the next change, and the last to today (it holds until
    changed). If the minimum bid rate fails, the fixed rate alone, with a
    warning (wrong 2000-2008); None if the fixed rate fails (the discount
    rate alone would be carried on from 1998, as an announced rate is).
    Before the ECB's first day, the Bundesbank's discount rate on the days
    it changed, from 1948-07 (baked, batch 9.6; Terry's 2026-10-13 request,
    labelled for its years as the U.S. line is for its years before the
    target). The Lombard rate, its ceiling, is not drawn: its special rate
    stood in for it in 1973-74 and 1981-82, it lay one to three points
    above, and the ECB's corridor is not drawn after 1999 either.
    """
    try:
        fixed = _clean(ecb_series(*DE_POLICY_FIXED, revised=False))
    except Exception as exc:
        print(f"  Warning: ECB main refinancing rate ({DE_POLICY_FIXED[1]}) unavailable ({exc}); not drawn.")
        return None
    try:
        bid = _clean(ecb_series(*DE_POLICY_MINIMUM_BID, revised=False, stopped=DE_MINIMUM_BID_ENDED))
    except Exception as exc:
        print(f"  Warning: ECB minimum bid rate ({DE_POLICY_MINIMUM_BID[1]}) unavailable ({exc}); "
              "the fixed rate alone, wrong while the tenders were variable (2000-2008).")
        bid = fixed.iloc[:0]
    values = fixed
    if not bid.empty:
        # The fixed rate's first change after the variable tenders began ends them.
        resumed = fixed.loc[fixed.index > bid.index[0]]
        end = resumed.index[0] if not resumed.empty else pd.Timestamp.max
        values = pd.concat([fixed.loc[fixed.index < bid.index[0]], bid.loc[bid.index < end], resumed])
    # Each day's rate, carried from its change to the next and on to today.
    # (Since batch 17.3 ``held_steps`` carries an announced rate on to the
    # chart's end anyway; the daily values are kept, so the points drawn are
    # those drawn before.)
    today = pd.Timestamp.today().normalize()
    values = values.reindex(pd.date_range(values.index[0], max(today, values.index[-1]), freq="D")).ffill()
    discount = _baked(EMBEDDED_DE_DISCOUNT_RATE_CHANGES)
    discount = discount.loc[discount.index < values.index[0]]
    parts = _parts(
        (discount, "Bundesbank Discount Rate", "Bundesbank Discount Rate"),
        (values, "ECB Main Refinancing Rate", "ECB Main Refinancing Rate"),
    )
    values = pd.concat([discount, values])
    return RateCurve("policy", _named(parts), values, POLICY_RATE_STYLE, title="Policy Rate", holds=holding(values, HELD),
                     parts=parts)


def de_policy_market(style: dict = POLICY_RATE_STYLE) -> RateCurve | None:
    """Return the euro area's overnight rate: EONIA until €STR begins, then €STR (``DE_ESTR``); None if both fail.

    Either alone is drawn, with a warning, if the other fails (EONIA ends
    2021-12-31, €STR begins 2019-10-01).
    """
    found: dict[str, pd.Series] = {}
    for name, source, stopped in (("EONIA", DE_EONIA, DE_EONIA_ENDED), ("€STR", DE_ESTR, None)):
        try:
            found[name] = _clean(ecb_series(*source, revised=False, stopped=stopped))
        except Exception as exc:
            print(f"  Warning: ECB {name} ({source[0]}.{source[1]}) unavailable ({exc}).")
    if not found:
        print("  Warning: no euro area overnight rate; not drawn.")
        return None
    empty = next(iter(found.values())).iloc[:0]
    eonia, estr = found.get("EONIA", empty), found.get("€STR", empty)
    if not estr.empty:
        eonia = eonia.loc[eonia.index < estr.index[0]]
    values = pd.concat([eonia, estr])
    parts = _parts((eonia, "EONIA", "EONIA"), (estr, "€STR", "€STR"))
    return RateCurve("policy_market", OVERNIGHT_RATE_NAMED.format(_named(parts)), values, style, title="Policy Rate",
                     holds=holding(values, "daily"), parts=parts, named_in=OVERNIGHT_RATE_NAMED)


def _de_mortgage(term: str) -> pd.Series:
    """Return one German mortgage band's monthly rate, dated by each month's first day."""
    monthly = ecb_series(DE_MORTGAGE_FLOW, DE_MORTGAGE_SERIES[term], DE_MORTGAGE_UNIT, revised=True)
    return _clean(monthly.set_axis(monthly.index.to_period("M").start_time))


def cdn_mortgage_history() -> pd.Series:
    """Return the CMHC conventional 5-year mortgage lending rate, monthly from 1951 (StatCan 34-10-0145).

    Batch 19.2: drawn from its bake alone (``ratesplot/data/statcan/``),
    with no request. The chart draws it only before Canada's posted 5-year
    rate begins (Valet's, 1975-01-01, ``mortgage_rate``), so a recent part
    would never be drawn; the daily job re-bakes it, as every series. Not
    baked: the table's Canada rows, checked, not trusted
    (``cdn_data.statcan_download``): the one vector declared, in percent,
    one row per month; anything else raises (and the caller warns). Each
    month is dated by its first day.
    """
    values = read_series(STATCAN_BAKED_SOURCE, CDN_MORTGAGE_HISTORY_VECTOR)
    if values is None:
        values = statcan_download(CDN_MORTGAGE_HISTORY_TABLE)[CDN_MORTGAGE_HISTORY_VECTOR]
    return _clean(values.rename(None).rename_axis(None))


def _mortgage_style(term: str) -> dict:
    """Return a mortgage term's line style, coloured as its yield term (or its own colour)."""
    yield_term = MORTGAGE_TERMS[term][1]
    colour = TERM_COLORS[yield_term] if yield_term is not None else MORTGAGE_OWN_COLORS[term]
    if term == "prime":
        return PRIME_RATE_STYLE | {"color": colour}
    variable = term.endswith("v") or term == "tracker"
    return (VARIABLE_MORTGAGE_STYLE if variable else MORTGAGE_STYLE) | {"color": colour}


def mortgage_rate(term: str, country: str | None = None, margin: float = 0.0) -> RateCurve | None:
    """Return one mortgage term's rate (``config.MORTGAGE_TERMS``) for ``country``, or None with a warning if its source fails.

    A baked series (the Bank of England's, the Bank of Canada's, FRED's:
    batch 19.2) is drawn from its bake when its source fails, with the
    bake's warning.
    ``country``: one of the term's countries, its only one when not given
    (the prime rate is Canada's and the U.S.'). Canada's 5-year: the posted
    weekly rate, carried back before it begins by the monthly CMHC rate
    (with a warning, and from 1975 only, if that fails). A term of
    ``config.MORTGAGE_MARGINS`` is drawn plus ``margin`` points (the prime
    rate: ``PlotConfig.prime_margin``, batch 9.4; the UK tracker, Bank Rate
    plus ``PlotConfig.tracker_margin``, batch 9.5); the others take none.
    """
    assert margin == 0 or term in MORTGAGE_MARGINS, (term, margin)
    countries, yield_term = MORTGAGE_TERMS[term]
    if country is None:
        (country,) = countries
    label = _mortgage_label(term, country, margin)
    code = {"us": US_MORTGAGE_SERIES, "cdn": CDN_MORTGAGE_SERIES, "uk": UK_MORTGAGE_SERIES, "de": DE_MORTGAGE_SERIES}[country][term]
    try:
        if country == "uk":
            values = _uk_mortgage(term)
        elif country == "de":
            values = _de_mortgage(term)
        else:
            values = _fred(code) if country == "us" else _valet(code)
    except Exception as exc:
        print(f"  Warning: {label} ({code}) unavailable ({exc}); not drawn.")
        return None
    # The prime rates are announced, and so is the tracker (Bank Rate's
    # changes); the mortgage rates are surveys and averages, observed weekly
    # or monthly.
    holds = holding(values, HELD if term in ("prime", "tracker") else _MORTGAGE_HOLDS[country])
    if country == "cdn" and term == "5":
        try:
            history = cdn_mortgage_history()
        except Exception as exc:
            print(
                f"  Warning: StatCan {CDN_MORTGAGE_HISTORY_TABLE} (5-year mortgage rate before "
                f"{values.index[0]:%Y-%m-%d}) unavailable ({exc}); drawn from then only."
            )
        else:
            history = history.loc[history.index < values.index[0]]
            values = pd.concat([history, values])
            holds = pd.concat([holding(history, "monthly"), holds])
    if margin:
        values = values + margin
    color_of = YIELD_TERMS[yield_term] if yield_term is not None else None
    return RateCurve(f"mortgage_{term}", label, values, _mortgage_style(term), title="Mortgage Rates", color_of=color_of,
                     holds=holds)


def warn_none_drawn(country: str, curve: str, why: str) -> None:
    """Warn that a nation's chart draws no ``curve`` of a chosen list, ``why`` naming what it has.

    Terry, 2026-10-07, of a list for every chart that leaves a shown nation
    none of its terms (``-c --yields:7,20``): "plot no yields in that case,
    but issue a warning message". The same words for a nation's own list
    of none (``--cdn:yields:none``), which is how the window and the page
    hold that case, so the command line's log and theirs read alike.
    """
    print(f"  Warning: no {curve} on the {nation_by_key(country).adjective} chart: {why}.")


def spread_label(pair: tuple[str, str]) -> str:
    """Return a spread's legend label: ``("10y", "2y")`` -> "10Y–2Y Spread"."""
    return f"{pair[0].upper()}–{pair[1].upper()} Spread"


def yield_spreads(country: str, yields: pd.DataFrame, config: PlotConfig) -> list[RateCurve]:
    """Return the chosen spreads (``config.spread_pairs``), each the first term's yield less the second's.

    Taken from the country's prepared yields, so with --cur they run on to
    the day's quotes. A value is drawn where both terms have one. Canada's
    yields are monthly before 2001, so its spreads are steps there, as its
    yields are. A pair with a term the country has no yield for is named and
    left out, and the colours go to the pairs drawn, in order; with none of
    the pairs its terms make, one warning says so.
    """
    nation = nation_by_key(country)
    if not nation.view("spread_pairs", config.spread_pairs):
        warn_none_drawn(country, "spread", f"no spread chosen is of two of its yield terms ({','.join(nation.yield_terms)})")
        return []
    if yields.empty:
        return []
    frame = yields.set_index(DATE_COLUMN) if DATE_COLUMN in yields.columns else yields
    curves = []
    for pair in config.spread_pairs:
        first, second = (YIELD_TERMS[term] for term in pair)
        if first not in frame.columns or second not in frame.columns:
            name = nation_by_key(country).adjective
            print(f"  Note: no {name} {first if first not in frame.columns else second} yield; no {spread_label(pair)} on this chart.")
            continue
        values = _clean(frame[first] - frame[second])
        # Coloured by its place among the spreads drawn, so a pair left off
        # takes no colour: Canada's chart of 7y-1m,10y-2y draws its 10y-2y
        # as its chart of 10y-2y alone does (options.nation_view).
        style = SPREAD_STYLE | {"color": SPREAD_COLORS[len(curves) % len(SPREAD_COLORS)]}
        steps_until = CANADIAN_YIELD_HIST_END if country == "cdn" else _steps_until(yields, (first, second))
        key = f"spread_{pair[0]}-{pair[1]}"
        curves.append(RateCurve(key, spread_label(pair), values, style, steps_until, spread=True, title="Spreads"))
    return curves


def _steps_until(yields: pd.DataFrame, columns: tuple[str, str]) -> pd.Timestamp | None:
    """Return the last date a spread is monthly: where the later of its two terms' monthly history ends (None: neither has one).

    The UK's 10- and 20-year are monthly averages before their daily par
    yields begin (``uk_data.fetch_uk_yields``), and Germany's terms are
    end-of-month values before their daily ones (``de_data.fetch_de_yields``),
    so a spread of them is too. Empty for the U.S., whose yields carry no
    such record.
    """
    assert YIELD_HISTORY_ATTR == DE_YIELD_HISTORY_ATTR  # one record, read alike for both nations
    through = [date for column, date in yields.attrs.get(YIELD_HISTORY_ATTR, {}).items() if column in columns]
    return max(through) if through else None


# Each nation whose policy target is read from its bank's announcements too
# (batch 32, decision 83): its releases, what they are called when they fail,
# and its own series as the messages name it. The U.S. needs none: FRED's
# range has a change's day on the morning it takes effect (measured
# 2026-10-28, 32.3). The ECB's is to be seen at its next change.
_ANNOUNCING: dict[str, tuple[Callable[[], Releases], str, str]] = {
    "cdn": (lambda: boc_releases(CDN_BANK_RATE_ABOVE_TARGET), "Bank of Canada press releases", f"Valet's {CDN_TARGET_SERIES}"),
    "uk": (boe_releases, "Bank of England news", f"the Bank of England's {UK_POLICY_SERIES}"),
}


def with_announced(country: str, curve: RateCurve | None, end: pd.Timestamp) -> RateCurve | None:
    """Return ``curve``, a nation's policy target, with the changes its bank has announced and its series does not have yet (batch 32).

    Asked only where a chart ending ``end`` reaches past the series' last
    day (``announced.announcements_needed``), for a nation in
    ``_ANNOUNCING``; each change added holds until changed, as the series'
    values do, and is drawn from the day it takes effect whenever the End
    reaches it (``announced.joined`` says what is read and checked). If the
    releases cannot be had, the series alone, with a warning.
    """
    if curve is None or country not in _ANNOUNCING or not announcements_needed(curve.values, end):
        return curve
    assert curve.upper is None and curve.holds is not None, curve.label  # Canada's and the UK's targets: one rate each day
    releases, called, series = _ANNOUNCING[country]
    try:
        found = releases()
    except Exception as exc:
        print(f"  Warning: {called} unavailable ({exc}); a change announced since "
              f"{curve.values.index[-1]:%Y-%m-%d} is not drawn.")
        return curve
    values, first = joined(curve.values, found, series, end)
    if first is None:
        return curve
    added = values.loc[values.index >= first]
    return replace(curve, values=values, holds=pd.concat([curve.holds, holding(added, HELD)]), announced=first)


# Each nation's policy terms (batch 9.1).
_POLICY_TARGETS = {"us": us_policy_target, "cdn": cdn_policy_target, "uk": uk_policy_target, "de": de_policy_target}
_POLICY_MARKETS = {"us": us_policy_market, "cdn": cdn_policy_market, "uk": uk_policy_market, "de": de_policy_market}

# How far ahead a blank End looks for a policy target's value (batch 32.4):
# a change takes effect on the day of its announcement (the Bank of
# England's) or the day after (the Bank of Canada's), so a year holds every
# change announced, and none is announced that far ahead.
_TARGET_LOOK_AHEAD = pd.Timedelta(days=366)


def draws_policy_target(config: PlotConfig) -> bool:
    """Whether a nation's chart (``config``, its ``PlotConfig.for_nation``) draws its policy target (``rate_curves``)."""
    return config.policy_rates and "target" in config.policy_terms


def policy_target_last(country: str) -> pd.Timestamp | None:
    """Return the last day nation ``country``'s policy target holds a value, the changes its bank has announced with it (batch 32.4).

    The day a blank End reaches (``plotting.resolve_end``): later than today
    only for a change announced to take effect after it (``with_announced``),
    or a bank's own series dated ahead. None where the target has no values.
    """
    today = pd.Timestamp.today().normalize()
    curve = with_announced(country, _POLICY_TARGETS[country](), today + _TARGET_LOOK_AHEAD)
    return None if curve is None or curve.values.empty else curve.values.index[-1]


def rate_curves(country: str, yields: pd.DataFrame, config: PlotConfig) -> list[RateCurve]:
    """Return one country's chosen curves for the yield axis ("cdn", "us", "uk" or "de"), in drawing order.

    ``yields`` is the country's prepared yield frame (date-indexed for
    Canada, the UK and Germany, a ``DATE`` column for the U.S.), which the spreads are taken from.
    Each curve is fetched whole (from its first observation) and cut to the
    window when drawn, so the automatic start sees where it begins.
    """
    curves: list[RateCurve | None] = []
    adjective = nation_by_key(country).adjective
    if config.policy_rates and not config.policy_terms:
        warn_none_drawn(country, "policy rate", f"none of its policy terms ({','.join(POLICY_TERMS)}) is chosen")
    elif config.policy_rates:
        with downloads_of(f"{adjective} policy rate"):
            # The market rate first, so the target's steps are drawn over its
            # daily moves (the legend lists the target first); drawn as the
            # policy rate was before batch 9.1 when it is drawn alone.
            if "market" in config.policy_terms:
                style = POLICY_MARKET_STYLE if "target" in config.policy_terms else POLICY_RATE_STYLE
                curves.append(_POLICY_MARKETS[country](style))
            if "target" in config.policy_terms:
                curves.append(with_announced(country, _POLICY_TARGETS[country](), config.end))
    if config.mortgages:
        terms = [term for term in config.mortgage_terms if country in MORTGAGE_TERMS[term][0]]
        if not terms:
            own = ",".join(nation_by_key(country).mortgage_terms)
            warn_none_drawn(country, "mortgage rate", f"none of its mortgage terms ({own}) is chosen")
        else:
            with downloads_of(f"{adjective} mortgage rates"):
                curves += [
                    mortgage_rate(term, country, getattr(config, MORTGAGE_MARGINS[term]) if term in MORTGAGE_MARGINS else 0.0)
                    for term in terms
                ]
    if config.spreads:
        curves += yield_spreads(country, yields, config)
    chosen = []
    for curve in curves:
        if curve is None:
            continue
        if curve.values.empty:
            print(f"  Warning: {curve.label}: the source returned no values; not drawn.")
        elif curve.first > config.end:
            print(f"  Note: {curve.label} begins {curve.first:%Y-%m-%d}, after the chart ends; not drawn.")
        else:
            chosen.append(curve)
    return chosen
