#!/usr/bin/env python3
"""Check the policy rates read from the central banks' announcements (batch 32); offline, in seconds.

* the two readers (``announced.read_boc_feed``, ``read_boe_feed``) against
  the feeds saved on 2026-10-28, the day the Bank of Canada raised its
  target to 2.5 % (``tools/announced_fixtures``);
* every wording read from the releases of 2020 to 2026 (Canada's first
  sentence, the Bank of England's titles), put in a made-up feed of each
  bank's form, and the ones a careful reading must refuse: two rates, a Bank
  Rate not a quarter point above the target, a rate outside 0 to 25 %, a
  decision without its summary's link, a release about the rate in another
  form;
* the join to a bank's own series (``announced.joined``): a change after
  its last day added and noted, one it has compared, a hold adding nothing,
  a change that does not follow from the rate before it refused, two on a
  day refused, an unread release warned of only while it could matter;
* the policy target through ``rates.with_announced``, with the feed read
  from the fixture: asked only when the End passes the series' last day, the
  legend's "Announced from", a feed that fails;
* the drawing (``plotting.add_rate_lines``): the announced stretch a piece
  of its own with its riser, the hover read-out's "(announced)" on it alone,
  Export chart's values day by day.

The live check of the same feeds is ``tools/check_sources.py``.

Usage (from the project root)::

    python tools/check_announced.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import verify_charts  # noqa: E402,F401  (unused but first: it sets the Agg backend before pyplot is imported)

del verify_charts
import matplotlib.dates as mdates  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from ratesplot import announced, export, hover, plotting, rates  # noqa: E402
from ratesplot.config import POLICY_RATE_STYLE, PlotConfig  # noqa: E402

FIXTURES = ROOT / "tools" / "announced_fixtures"
RESULTS: list[bool] = []
DAY = pd.Timestamp


def check(label: str, condition: bool, detail: object = "") -> None:
    RESULTS.append(bool(condition))
    shown = f"  [{detail}]" if not condition and detail != "" else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)


def boc_feed(*items: tuple[str, str, str]) -> bytes:
    """A feed of the Bank of Canada's form with ``(day, title, description)`` items."""
    entries = "".join(
        f'<item rdf:about="x"><title>{title}</title><description>{description}</description>'
        f'<cb:news rdf:parseType="Resource"><cb:occurrenceDate>{day}</cb:occurrenceDate></cb:news></item>'
        for day, title, description in items
    )
    return (
        '<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns="http://purl.org/rss/1.0/" xmlns:cb="http://www.cbwiki.net/wiki/index.php/Specification_1.2/">'
        f"<channel><title>Press Releases</title></channel>{entries}</rdf:RDF>"
    ).encode("utf-8")


def boe_feed(*items: tuple[str, str, str]) -> bytes:
    """A feed of the Bank of England's form with ``(pubDate, title, link)`` items."""
    entries = "".join(
        f"<item><link>{link}</link><title>{title}</title><pubDate>{when}</pubDate></item>"
        for when, title, link in items
    )
    return f'<rss version="2.0"><channel><title>News</title>{entries}</channel></rss>'.encode("utf-8")


DECISION = "https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/november-2026"


def check_saved_feeds() -> None:
    """The two feeds saved on 2026-10-28."""
    boc = announced.read_boc_feed((FIXTURES / "boc_press_releases.xml").read_bytes(), 0.25)
    read = [(a.announced, a.effective, a.rate, a.direction, a.change) for a in boc.found]
    check("Bank of Canada: four rate announcements, the 2026-10-28 rise first", read == [
        (DAY("2026-10-28"), DAY("2026-10-29"), 2.5, 1, 0.25),
        (DAY("2026-09-02"), DAY("2026-09-03"), 2.25, 0, None),
        (DAY("2026-07-15"), DAY("2026-07-16"), 2.25, 0, None),
        (DAY("2026-06-10"), DAY("2026-06-11"), 2.25, 0, None),
    ], read)
    check("Bank of Canada: the release of its 2027 schedule is not one about the rate", boc.unread == (), boc.unread)
    boe = announced.read_boe_feed((FIXTURES / "boe_news.xml").read_bytes())
    read = [(a.announced, a.effective, a.rate, a.direction) for a in boe.found]
    check("Bank of England: the September and July holds at 3.75%, in force the day announced", read == [
        (DAY("2026-09-17"), DAY("2026-09-17"), 3.75, 0), (DAY("2026-07-30"), DAY("2026-07-30"), 3.75, 0),
    ], read)
    check("Bank of England: the MPC's remit letter and the rest are not about the rate", boe.unread == (), boe.unread)


# Each Bank of Canada first sentence read from its releases, 2020 to 2025: (sentence, rate, direction, change).
BOC_SENTENCES = (
    ("The Bank of Canada today held its target for the overnight rate at 2.25%, with the Bank Rate at 2.5% and the "
     "deposit rate at 2.20%.", 2.25, 0, None),
    ("The Bank of Canada today reduced its target for the overnight rate by 25 basis points to 2.25%, with the Bank "
     "Rate at 2.5% and the deposit rate at 2.20%.", 2.25, -1, 0.25),
    ("The Bank of Canada today reduced its target for the overnight rate to 3¼%, with the Bank Rate at 3½% and the "
     "deposit rate at 3¼%.", 3.25, -1, None),
    ("The Bank of Canada today reduced its target for the overnight rate to 4¾%, with the Bank Rate at 5% and the "
     "deposit rate at 4¾%.", 4.75, -1, None),
    ("The Bank of Canada today increased its target for the overnight rate to 5%, with the Bank Rate at 5¼% and the "
     "deposit rate at 5%.", 5.0, 1, None),
    ("The Bank of Canada today increased its target for the overnight rate to ½ %, with the Bank Rate at ¾ % and the "
     "deposit rate at ½ %.", 0.5, 1, None),
    ("The Bank of Canada today held its target for the overnight rate at the effective lower bound of ¼ percent, with "
     "the Bank Rate at ½ percent and the deposit rate at ¼ percent.", 0.25, 0, None),
    ("The Bank of Canada today lowered its target for the overnight rate by 50 basis points to 1 ¼ percent.", 1.25, -1, 0.5),
)
BOC_REFUSED = (
    ("two rates", "The Bank of Canada today reduced its target for the overnight rate to 2.25% and then to 2%, with "
     "the Bank Rate at 2.5%."),
    ("a Bank Rate not a quarter point above", "The Bank of Canada today held its target for the overnight rate at "
     "2.25%, with the Bank Rate at 2.75% and the deposit rate at 2.20%."),
    ("a rate above 25 %", "The Bank of Canada today increased its target for the overnight rate to 30%."),
    ("another form", "The Bank of Canada today announced that its target for the overnight rate will be 2.5%."),
)
# Each Bank of England title read, 2021 to 2026: (title, rate, direction).
BOE_TITLES = (
    ("Bank Rate reduced to 3.75% - December 2025 Monetary Policy Summary and Minutes", 3.75, -1),
    ("Bank Rate maintained at 4% - November 2025 Monetary Policy Summary and Minutes", 4.0, 0),
    ("Bank rate maintained at 3.75% - September 2026 Monetary Policy Summary and Minutes", 3.75, 0),
    ("Bank Rate increased to 5.25% - August 2023", 5.25, 1),
    ("Bank Rate increased to 0.25% - December 2021", 0.25, 1),
)


def check_wordings() -> None:
    """Every wording read from the releases, and the ones refused."""
    for sentence, rate, direction, change in BOC_SENTENCES:
        read = announced.read_boc_feed(boc_feed(("2026-12-09", "Bank of Canada maintains policy rate", sentence)), 0.25)
        got = [(a.rate, a.direction, a.change, a.effective) for a in read.found]
        check(f"Canada: {sentence[33:90]}…", got == [(rate, direction, change, DAY("2026-12-10"))] and not read.unread, got)
    for why, sentence in BOC_REFUSED:
        read = announced.read_boc_feed(boc_feed(("2026-12-09", "Bank of Canada raises policy rate", sentence)), 0.25)
        check(f"Canada refuses {why}, as a release it could not read", not read.found and len(read.unread) == 1, read)
    unrelated = announced.read_boc_feed(boc_feed(("2026-12-09", "Bank of Canada unveils new $20 note", "A note.")), 0.25)
    check("Canada: a release not about the rate is passed over", unrelated.found == () and unrelated.unread == ())
    for title, rate, direction in BOE_TITLES:
        read = announced.read_boe_feed(boe_feed(("Thu, 05 Nov 2026 12:00:00 Z", title, DECISION)))
        got = [(a.rate, a.direction, a.effective) for a in read.found]
        check(f"UK: {title[:45]}", got == [(rate, direction, DAY("2026-11-05"))] and not read.unread, got)
    late = announced.read_boe_feed(boe_feed(("Thu, 05 Nov 2026 23:30:00 -0500", BOE_TITLES[0][0], DECISION)))
    check("UK: dated by London's day (23:30 in New York is the next day there)",
          [a.announced for a in late.found] == [DAY("2026-11-06")], late)
    for why, title, link in (
        ("a decision without its summary's link", "Bank Rate reduced to 3.5% - November 2026", "https://x/news/1"),
        ("a summary in another form", "Monetary Policy Summary, November 2026", DECISION),
        ("a rate above 25 %", "Bank Rate increased to 26% - November 2026", DECISION),
    ):
        read = announced.read_boe_feed(boe_feed(("Thu, 05 Nov 2026 12:00:00 Z", title, link)))
        check(f"UK refuses {why}", not read.found and len(read.unread) == 1, read)


def releases(*found: tuple[str, str, float, int, float | None], unread: tuple[tuple[str, str], ...] = ()) -> announced.Releases:
    """A bank's releases: ``(announced, effective, rate, direction, change)`` read, ``(announced, effective)`` unread."""
    return announced.Releases(
        "the Bank of Canada",
        tuple(announced.Announcement(DAY(a), DAY(e), rate, direction, change, "words") for a, e, rate, direction, change in found),
        tuple(announced.Unread(DAY(a), DAY(e), "words") for a, e in unread),
    )


def series(*pairs: tuple[str, float]) -> pd.Series:
    return pd.Series([value for _day, value in pairs], index=pd.DatetimeIndex([day for day, _value in pairs]))


def join(published: pd.Series, found: announced.Releases, end: str = "2026-11-01") -> tuple[pd.Series, pd.Timestamp | None, list[str]]:
    said: list[str] = []
    values, first = announced.joined(published, found, "the series", DAY(end), said.append)
    return values, first, said


def check_joined() -> None:
    """The join to the bank's own series."""
    valet = series(("2025-10-30", 2.25), ("2026-10-27", 2.25))
    rise = ("2026-10-28", "2026-10-29", 2.5, 1, 0.25)
    values, first, said = join(valet, releases(rise))
    check("a change after the series' last day is added from the day it takes effect",
          first == DAY("2026-10-29") and values.iloc[-1] == 2.5 and values.index[-1] == DAY("2026-10-29"), values)
    check("… and noted as not yet in the series", len(said) == 1 and said[0].startswith("  Note: 2.50% from 2026-10-29")
          and "not yet in the series" in said[0], said)
    _values, first, said = join(valet, releases(rise), end="2026-10-28")
    check("… with an End before it: added (not drawn), the note saying it takes effect after the chart ends",
          first == DAY("2026-10-29") and "takes effect after the chart ends; not drawn" in said[0], said)
    published = series(("2026-10-27", 2.25), ("2026-10-29", 2.5))
    values, first, said = join(published, releases(rise))
    check("once the series has the day: nothing added, nothing said", first is None and values.equals(published) and not said, said)
    values, first, said = join(series(("2026-10-27", 2.25), ("2026-10-29", 2.25)), releases(rise))
    check("the series differing from the announcement: a warning, the series kept",
          first is None and len(said) == 1 and "but the series has 2.25% on 2026-10-29" in said[0], said)
    weekend = series(("2026-10-29", 2.25), ("2026-11-02", 2.5))
    _values, _first, said = join(weekend, releases(("2026-10-30", "2026-10-31", 2.5, 1, 0.25)))
    check("compared on the series' first day from the announced one (a Saturday's change, the Monday's value)", not said, said)
    _values, first, said = join(valet, releases(("2026-10-28", "2026-10-29", 2.25, 0, None)))
    check("a hold after the series' last day adds nothing and says nothing", first is None and not said, said)
    for why, found in (
        ("a rise to a rate below the one in force", ("2026-10-28", "2026-10-29", 2.0, 1, None)),
        ("a hold at another rate", ("2026-10-28", "2026-10-29", 2.5, 0, None)),
        ("a size the change does not have", ("2026-10-28", "2026-10-29", 2.5, 1, 0.5)),
    ):
        _values, first, said = join(valet, releases(found))
        check(f"refused, with a warning: {why}", first is None and len(said) == 1 and "does not follow from 2.25%" in said[0], said)
    values, first, said = join(valet, releases(rise, ("2026-12-09", "2026-12-10", 2.75, 1, 0.25)))
    check("two changes in turn: the second follows from the first", first == DAY("2026-10-29")
          and list(values.iloc[-2:]) == [2.5, 2.75] and len(said) == 2, said)
    _values, first, said = join(valet, releases(rise, ("2026-10-28", "2026-10-29", 2.75, 1, 0.5)))
    check("two rates announced on one day: neither added, a warning", first is None and len(said) == 1
          and "announced 2 policy rates on 2026-10-28 (2.50%, 2.75%)" in said[0], said)
    _values, first, said = join(valet, releases(unread=(("2026-10-28", "2026-10-29"),)))
    check("an unread release the series does not yet cover: a warning", first is None and len(said) == 1
          and "cannot be read with certainty" in said[0], said)
    _values, first, said = join(valet, releases(unread=(("2026-09-02", "2026-09-03"),)))
    check("an unread release the series covers: nothing said", first is None and not said, said)


class _Feed:
    """``canadian_get`` replaced: the saved feed for its address, counted."""

    def __init__(self, fail: bool = False) -> None:
        self.asked: list[str] = []
        self.fail = fail

    def __call__(self, url: str, params: dict | None = None, **_kwargs: object) -> object:
        self.asked.append(url)
        if self.fail:
            raise ConnectionError("refused")
        assert url == announced.BOC_PRESS_RELEASES_FEED, url
        return type("Response", (), {"content": (FIXTURES / "boc_press_releases.xml").read_bytes()})()


def target_curve() -> rates.RateCurve:
    values = series(("2025-10-30", 2.25), ("2026-10-27", 2.25))
    return rates.RateCurve("policy", "Target for the Overnight Rate", values, POLICY_RATE_STYLE, title="Policy Rate",
                           holds=rates.holding(values, rates.HELD))


def check_with_announced() -> None:
    """The policy target through ``rates.with_announced``, the feed read from the fixture."""
    real = announced.canadian_get
    try:
        feed = announced.canadian_get = _Feed()
        curve = rates.with_announced("cdn", target_curve(), DAY("2026-10-27"))
        check("an End on the series' last day asks nothing", not feed.asked and curve.announced is None, feed.asked)
        curve = rates.with_announced("us", target_curve(), DAY("2026-11-01"))
        check("a nation without announcements read asks nothing", not feed.asked and curve.announced is None, feed.asked)
        curve = rates.with_announced("cdn", target_curve(), DAY("2026-11-01"))
        check("an End past it asks the feed once", feed.asked == [announced.BOC_PRESS_RELEASES_FEED], feed.asked)
        check("… and the change is held from 2026-10-29", curve.announced == DAY("2026-10-29")
              and curve.values.iloc[-1] == 2.5 and list(curve.holds.iloc[-2:]) == [rates.HELD] * 2, curve.values.tail(2))
        late = PlotConfig(start=DAY("2026-06-01"), end=DAY("2026-11-01"))
        early = PlotConfig(start=DAY("2026-06-01"), end=DAY("2026-10-28"))
        check("the legend names it from its day", rates.legend_label(curve, late)
              == "Target for the Overnight Rate, Announced from 2026-10-29", rates.legend_label(curve, late))
        check("… and not on a chart ending before it", rates.legend_label(curve, early) == "Target for the Overnight Rate",
              rates.legend_label(curve, early))
        announced.canadian_get = _Feed(fail=True)
        curve = rates.with_announced("cdn", target_curve(), DAY("2026-11-01"))
        check("a feed that fails leaves the series alone", curve.announced is None and curve.values.iloc[-1] == 2.25)
    finally:
        announced.canadian_get = real


def check_drawing() -> None:
    """The drawing: its pieces, the read-out and Export chart."""
    real = announced.canadian_get
    try:
        announced.canadian_get = _Feed()
        curve = rates.with_announced("cdn", target_curve(), DAY("2026-11-01"))
    finally:
        announced.canadian_get = real
    config = PlotConfig(start=DAY("2026-10-01"), end=DAY("2026-11-01"))
    figure = Figure(figsize=(8, 4), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    ax.set_xlim(mdates.date2num(config.start), mdates.date2num(config.end))
    ax.set_ylim(2.0, 2.75)
    plotting.add_rate_lines(ax, [curve], config)
    lines = ax.get_lines()
    pieces = [(list(line.get_xdata()), list(line.get_ydata()), line.get_label()) for line in lines]
    joint = DAY("2026-10-29")
    check("two pieces: to the change, then from it with its riser", len(lines) == 2
          and pieces[0][0][-1] == joint and pieces[0][1][-1] == 2.25
          and pieces[1][0][:2] == [joint, joint] and pieces[1][1][:3] == [2.25, 2.5, 2.5]
          and pieces[1][0][-1] == config.end, pieces)
    check("one legend entry, in one colour", [label for *_xy, label in pieces][1] == "_nolegend_"
          and lines[0].get_color() == lines[1].get_color(), pieces)
    figure.canvas.draw()
    chart = hover.chart_lines(figure)

    def read(day: str, value: float) -> tuple[str, ...] | None:
        x, y = ax.transData.transform((mdates.date2num(DAY(day)), value))
        found = chart.reading(x, figure.bbox.height - y, hover.REACH_PX)
        return found.lines if found is not None else None

    # Carried to the window's start, the value is dated by it (rates.held_steps).
    check("the read-out on 2026-10-15: the series' value", read("2026-10-15", 2.25)
          == ("Target for the Overnight Rate, Announced from 2026-10-29", "2.25%  2026-10-15 (observed 2026-10-01)"),
          read("2026-10-15", 2.25))
    on = read("2026-10-31", 2.5)
    check("… on 2026-10-31: announced", on is not None and on[1].startswith("2.50% (announced)  2026-10-3"), on)
    near_end = read("2026-11-01", 2.5)
    check("… to the chart's end", near_end is not None and "(announced)" in near_end[1], near_end)
    data = export.chart_data(figure, config, "cdn")
    by_day = dict(zip(data.dates, (row[0] for row in data.values)))
    # A row for each day a piece has a point: the series' last, the change, the end.
    check("Export chart: 2.25% to 2026-10-27, 2.50% from 2026-10-29 to the end", list(by_day.items())[1:] == [
        (DAY("2026-10-27"), 2.25), (joint, 2.5), (config.end, 2.5)], by_day)


def main() -> int:
    for group in (check_saved_feeds, check_wordings, check_joined, check_with_announced, check_drawing):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group()
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[announced] {sum(RESULTS)} of {len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
