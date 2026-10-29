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
* a blank End (32.4), and the curves that follow the target (32.5,
  ``rates.with_followed``): Canada's prime rate 2.20 above it and the UK
  tracker, a change carried until their own series have it, asked only when
  the End passes their last day, refused where the prime no longer stands
  2.20 above, each note said once with the target drawn too;
* the drawing (``plotting.add_rate_lines``): the announced stretch a piece
  of its own with its riser, the hover read-out's "(announced)" on it alone,
  Export chart's values day by day.

The live check of the same feeds is ``tools/check_sources.py``.

Usage (from the project root)::

    python tools/check_announced.py

Exit code 1 if any check fails.
"""

from __future__ import annotations

import contextlib
import io
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import verify_charts  # noqa: E402,F401  (unused but first: it sets the Agg backend before pyplot is imported)

del verify_charts
import matplotlib.dates as mdates  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from ratesplot import announced, cli, endlabels, export, hover, plotting, rates  # noqa: E402
from ratesplot.config import POLICY_RATE_STYLE, PlotConfig  # noqa: E402
from ratesplot.axes import format_yield  # noqa: E402

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
    """``canadian_get`` (or ``uk_get``) replaced: the saved feed for its address (or ``body``), counted."""

    def __init__(self, fail: bool = False, body: bytes | None = None, url: str = announced.BOC_PRESS_RELEASES_FEED) -> None:
        self.asked: list[str] = []
        self.fail = fail
        self.body = body if body is not None else (FIXTURES / "boc_press_releases.xml").read_bytes()
        self.url = url

    def __call__(self, url: str, params: dict | None = None, **_kwargs: object) -> object:
        self.asked.append(url)
        if self.fail:
            raise ConnectionError("refused")
        assert url == self.url, url
        return type("Response", (), {"content": self.body})()


def target_curve() -> rates.RateCurve:
    values = series(("2025-10-30", 2.25), ("2026-10-27", 2.25))
    return rates.RateCurve("policy", "Target for the Overnight Rate", values, POLICY_RATE_STYLE, title="Policy Rate",
                           holds=rates.holding(values, rates.HELD))


class _Published:
    """``rates._ANNOUNCING[nation].published`` replaced for a block: ``values`` (or a failure), each call counted."""

    def __init__(self, nation: str, values: pd.Series | None) -> None:
        self.nation, self.values, self.asked = nation, values, 0
        self.real = rates._ANNOUNCING[nation]

    def __call__(self) -> pd.Series:
        self.asked += 1
        if self.values is None:
            raise ConnectionError("refused")
        return self.values

    def __enter__(self) -> _Published:
        rates._ANNOUNCING[self.nation] = self.real._replace(published=self)
        return self

    def __exit__(self, *_exc: object) -> None:
        rates._ANNOUNCING[self.nation] = self.real


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


def check_blank_end() -> None:
    """A blank End (batch 32.4): today, or the last day a policy target drawn holds."""
    today = DAY("2026-10-28")  # the day the feed was saved: the change takes effect the day after

    def parsed(*tokens: str) -> PlotConfig:
        config = cli.parse_args(["--no-gui", *tokens])
        return replace(config, end=today) if config.end_blank else config

    real_get, real_targets = announced.canadian_get, dict(rates._POLICY_TARGETS)
    # Canada's target read for a blank End is its last part alone (32.5): the series replaced is that.
    published = _Published("cdn", target_curve().values)
    try:
        feed = announced.canadian_get = _Feed()
        rates._POLICY_TARGETS.update(cdn=target_curve, us=target_curve)
        published.__enter__()
        check("no End given: end_blank; one given: not", parsed("-c").end_blank and not parsed("-c", "--e:2026-10-01").end_blank)
        check("a PlotConfig built directly keeps its End", not PlotConfig().end_blank)
        resolved = plotting.resolve_end(parsed("-c", "--policy"))
        check("blank, Canada's target drawn: the End is the announced day, 2026-10-29",
              resolved.end == DAY("2026-10-29") and feed.asked == [announced.BOC_PRESS_RELEASES_FEED], (resolved.end, feed.asked))
        feed.asked.clear()
        given = parsed("-c", "--policy", "--e:2026-10-28")
        check("an End given: kept, nothing asked", plotting.resolve_end(given).end == DAY("2026-10-28") and not feed.asked,
              feed.asked)
        check("no policy rate drawn: today, nothing asked",
              plotting.resolve_end(parsed("-c")).end == today and not feed.asked, feed.asked)
        check("Canada's market rate alone, not its target: today, nothing asked",
              plotting.resolve_end(parsed("-c", "--policy:market")).end == today and not feed.asked, feed.asked)
        check("the U.S. alone: its target holds nothing after today, and Canada's feed is not asked",
              plotting.resolve_end(parsed("-u", "--policy")).end == today and not feed.asked, feed.asked)
        both = plotting.resolve_end(parsed("-c", "-u", "--policy"))
        check("Canada and the U.S. shown: one End for both, 2026-10-29", both.end == DAY("2026-10-29")
              and both.for_nation("us").end == both.for_nation("cdn").end == DAY("2026-10-29"), both.end)
        check("resolve_start finds the End first, a Start given", plotting.resolve_start(
              parsed("-c", "--policy", "-s:2026-06-01")).end == DAY("2026-10-29"))
        feed.asked.clear()
        published.asked = 0
        prime = plotting.resolve_end(parsed("-c", "--mortgages:prime"))
        check("Canada's prime rate alone, which follows the target (32.5): 2026-10-29, the target's last part read",
              prime.end == DAY("2026-10-29") and published.asked == 1 and len(feed.asked) == 1, (prime.end, published.asked))
        feed.asked.clear()
        check("Canada's 5-year mortgage alone: today, nothing asked",
              plotting.resolve_end(parsed("-c", "--mortgages:5")).end == today and not feed.asked, feed.asked)
        check("the U.S. prime rate alone, which follows nothing read: today, nothing asked",
              plotting.resolve_end(parsed("-u", "--mortgages:prime")).end == today and not feed.asked, feed.asked)
        announced.canadian_get = _Feed(fail=True)
        check("the feed failing: today", plotting.resolve_end(parsed("-c", "--policy")).end == today)
    finally:
        announced.canadian_get = real_get
        rates._POLICY_TARGETS.clear()
        rates._POLICY_TARGETS.update(real_targets)
        published.__exit__()


def prime_curve(*pairs: tuple[str, float], margin: float = 0.0) -> rates.RateCurve:
    """Canada's prime rate as ``rates.mortgage_rate`` returns it, its values ``pairs`` plus ``margin``."""
    values = series(*pairs) + margin
    return rates.RateCurve("mortgage_prime", rates._mortgage_label("prime", "cdn", margin), values,
                           rates._mortgage_style("prime"), title="Mortgage Rates", holds=rates.holding(values, rates.HELD))


def follow(nation: str, term: str, curve: rates.RateCurve, margin: float = 0.0, end: str = "2026-11-01",
           target_drawn: bool = False) -> tuple[rates.RateCurve, list[str]]:
    """``rates.with_followed``, and what it said."""
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        followed = rates.with_followed(nation, term, curve, margin, DAY(end), target_drawn)
    return followed, said.getvalue().splitlines()


PRIME = (("2026-10-14", 4.45), ("2026-10-21", 4.45))
PRIME_NOTE = ("  Note: Prime Rate (chartered banks): 4.70% from 2026-10-29, the policy target's change carried to it; "
              "not yet in Valet's V80691311.")


def check_followed() -> None:
    """The curves that follow the policy target (32.5): Canada's prime rate and the UK tracker."""
    real_cdn, real_uk = announced.canadian_get, announced.uk_get
    try:
        feed = announced.canadian_get = _Feed()
        with _Published("cdn", target_curve().values) as published:
            curve, said = follow("cdn", "prime", prime_curve(*PRIME))
            check("Canada's prime: the target's change carried, 2.20 above it, from 2026-10-29",
                  curve.announced == DAY("2026-10-29") and curve.values.index[-1] == DAY("2026-10-29")
                  and abs(curve.values.iloc[-1] - 4.70) < 1e-9 and curve.holds.iloc[-1] == rates.HELD, curve.values.tail(2))
            check("… the bank's note and the prime's, the target not drawn", len(said) == 2
                  and said[0].startswith("  Note: 2.50% from 2026-10-29, as the Bank of Canada") and said[1] == PRIME_NOTE, said)
            late = PlotConfig(start=DAY("2026-06-01"), end=DAY("2026-11-01"))
            check("… named in the legend as announced", rates.legend_label(curve, late)
                  == "Prime Rate (chartered banks), Announced from 2026-10-29", rates.legend_label(curve, late))
            _curve, said = follow("cdn", "prime", prime_curve(*PRIME), target_drawn=True)
            check("… the target drawn too: only the prime's note (the bank's is the target's)", said == [PRIME_NOTE], said)
            curve, said = follow("cdn", "prime", prime_curve(*PRIME, margin=0.5), margin=0.5)
            check("… with a margin of 0.50: 5.20%, the margin kept", abs(curve.values.iloc[-1] - 5.20) < 1e-9
                  and said[-1].startswith("  Note: Prime Rate + 0.50 (chartered banks): 5.20% from 2026-10-29"), said)
            curve, said = follow("cdn", "prime", prime_curve(*PRIME), end="2026-10-28")
            check("… an End before the change: added, the note saying it takes effect after the chart ends",
                  curve.announced == DAY("2026-10-29") and said[-1].endswith("takes effect after the chart ends; not drawn."), said)
            feed.asked.clear()
            published.asked = 0
            original = prime_curve(*PRIME)
            curve, said = follow("cdn", "prime", original, end="2026-10-21")
            check("an End on the prime's last day: nothing asked, nothing said", curve is original and not said
                  and published.asked == 0 and not feed.asked, (published.asked, feed.asked))
            curve, said = follow("cdn", "prime", original, end="2026-10-25")
            check("an End before the target's last day: the target's series asked, not the feed; no change, nothing said",
                  curve is original and not said and published.asked == 1 and not feed.asked, (published.asked, feed.asked))
            for nation, term in (("us", "prime"), ("cdn", "5")):
                curve, said = follow(nation, term, original)
                check(f"{nation}'s {term}, which follows nothing read: as it is, nothing asked",
                      curve is original and not said and published.asked == 1, said)
            stray = prime_curve(("2026-10-21", 4.40))
            curve, said = follow("cdn", "prime", stray)
            check("a prime not 2.20 above the target on its last day: a warning, nothing carried", curve is stray
                  and said[-1].startswith("  Warning: Prime Rate (chartered banks) stood 2.15 above the policy target on "
                                          "2026-10-21, not 2.20"), said)
        with _Published("cdn", series(("2026-10-27", 2.25), ("2026-10-29", 2.5))):
            curve, said = follow("cdn", "prime", prime_curve(("2026-10-28", 4.45)))
            check("the target's series has the change, the prime's not yet: carried, said once",
                  curve.announced == DAY("2026-10-29") and said == [PRIME_NOTE], said)
        with _Published("cdn", series(("2026-10-27", 2.25), ("2026-10-29", 2.5), ("2026-11-04", 2.5))):
            caught_up = prime_curve(("2026-10-28", 4.45), ("2026-11-04", 4.70))
            curve, said = follow("cdn", "prime", caught_up, end="2026-11-05")
            check("the prime's series has it: as it is, nothing said", curve is caught_up and not said, said)
        with _Published("cdn", None):
            original = prime_curve(*PRIME)
            curve, said = follow("cdn", "prime", original)
            check("the target's series failing: a warning, the prime alone", curve is original and len(said) == 1
                  and said[0].startswith("  Warning: Valet's CBC20210 unavailable (refused)"), said)
        announced.canadian_get = _Feed(fail=True)
        with _Published("cdn", target_curve().values):
            curve, said = follow("cdn", "prime", original)
            check("the feed failing, the target not drawn: its warning, nothing carried", curve is original
                  and len(said) == 1 and said[0].startswith("  Warning: Bank of Canada press releases unavailable"), said)
        cut = boe_feed(("Thu, 05 Nov 2026 12:00:00 Z", "Bank Rate reduced to 3.5% - November 2026 Monetary Policy Summary "
                        "and Minutes", DECISION))
        announced.uk_get = _Feed(body=cut, url=announced.BOE_NEWS_FEED)
        bank_rate = series(("2025-12-18", 3.75), ("2026-11-04", 3.75))
        with _Published("uk", bank_rate):
            values = bank_rate + 1.75
            tracker = rates.RateCurve("mortgage_tracker", rates._mortgage_label("tracker", "uk", 1.75), values,
                                      rates._mortgage_style("tracker"), title="Mortgage Rates",
                                      holds=rates.holding(values, rates.HELD))
            curve, said = follow("uk", "tracker", tracker, margin=1.75, end="2026-11-05")
            check("the UK tracker: Bank Rate's cut carried the day it is announced, its margin kept",
                  curve.announced == DAY("2026-11-05") and abs(curve.values.iloc[-1] - 5.25) < 1e-9
                  and rates.legend_label(curve, PlotConfig(start=DAY("2026-06-01"), end=DAY("2026-11-05")))
                  == "Tracker Mortgage (Bank Rate + 1.75), Announced from 2026-11-05", curve.values.tail(2))
            check("… said: the bank's note, then the tracker's", len(said) == 2 and said[1] == (
                "  Note: Tracker Mortgage (Bank Rate + 1.75): 5.25% from 2026-11-05, the policy target's change carried "
                "to it; not yet in the Bank of England's IUDBEDR."), said)
    finally:
        announced.canadian_get, announced.uk_get = real_cdn, real_uk


def check_rate_curves() -> None:
    """``rates.rate_curves``: the target and the prime drawn together, each change said once."""
    real_get, real_mortgage, real_targets = announced.canadian_get, rates.mortgage_rate, dict(rates._POLICY_TARGETS)
    try:
        announced.canadian_get = _Feed()
        rates.mortgage_rate = lambda term, country=None, margin=0.0: prime_curve(*PRIME, margin=margin)
        rates._POLICY_TARGETS["cdn"] = target_curve
        with _Published("cdn", target_curve().values):
            for tokens, notes in ((("--policy", "--mortgages:prime"), 2), (("--mortgages:prime",), 2)):
                config = replace(cli.parse_args(["--no-gui", "-c", *tokens]).for_nation("cdn"), end=DAY("2026-11-01"))
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    curves = rates.rate_curves("cdn", pd.DataFrame(), config)
                lines = [line for line in said.getvalue().splitlines() if "Note:" in line]
                check(f"{' '.join(tokens)}: every curve announced from 2026-10-29, each note said once",
                      [curve.announced for curve in curves] == [DAY("2026-10-29")] * len(curves) and len(lines) == notes
                      and sum(PRIME_NOTE == line for line in lines) == 1, lines)
    finally:
        announced.canadian_get, rates.mortgage_rate = real_get, real_mortgage
        rates._POLICY_TARGETS.clear()
        rates._POLICY_TARGETS.update(real_targets)


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

    # The end label (-l) on a chart ending the day the change takes effect
    # (Terry, 2026-10-29: it stood at the riser's foot and read 2.25): both
    # pieces end that day, and the label is the announced piece's.
    try:
        announced.canadian_get = _Feed()
        curve = rates.with_announced("cdn", target_curve(), joint)
    finally:
        announced.canadian_get = real
    config = PlotConfig(start=DAY("2026-10-01"), end=joint, end_labels=True)
    figure = Figure(figsize=(8, 4), dpi=100)
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    ax.set_xlim(mdates.date2num(config.start), mdates.date2num(config.end))
    ax.set_ylim(2.0, 2.75)
    drawn = plotting.add_rate_lines(ax, [curve], config)
    lines = ax.get_lines()
    check("ending the day it takes effect: both pieces end on it, the announced piece its riser alone",
          len(lines) == 2 and list(lines[0].get_xdata())[-1] == joint and list(lines[1].get_xdata()) == [joint, joint]
          and list(lines[1].get_ydata()) == [2.25, 2.5], [(list(line.get_xdata()), list(line.get_ydata())) for line in lines])
    first = drawn[0][0]
    check("the legend's line gives its last piece for the end label", plotting.last_piece(first) is lines[1])
    endlabels.add_end_labels(ax, [(plotting.last_piece(first), format_yield)], config)
    figure.canvas.draw()
    texts = [(text.get_text(), round(float(ax.transData.inverted().transform(text.get_window_extent().get_points().mean(axis=0))[1]), 3))
             for text in ax.texts]
    check("its end label reads 2.50%, at the riser's top", [text for text, _y in texts] == ["2.50%"]
          and all(abs(y - 2.5) < 0.03 for _text, y in texts), texts)


def main() -> int:
    for group in (check_saved_feeds, check_wordings, check_joined, check_with_announced, check_blank_end, check_followed,
                  check_rate_curves, check_drawing):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group()
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[announced] {sum(RESULTS)} of {len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
