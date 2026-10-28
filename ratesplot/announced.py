"""Policy rates as announced (batch 32): a change read from the central bank's own announcement.

Terry, 2026-10-28 (decision 83), the day the Bank of Canada raised its
target to 2.5 %: a change of policy rate is shown on the days it is in
effect, from the fastest source that gives it, "a text announcement read
with care rather than not tried", and a chart whose End is later than today
shows a change already announced for a day in it. Nothing to do with the
intraday quotes (``--cur``).

Why it is needed, measured 2026-10-28: Valet dates a change of Canada's
target on the day after the announcement, when it takes effect, and posts
each day's value the next business day, so the new target reached the chart
a day after it took effect; the Bank of England's database (IUDBEDR) dates a
change on the day the MPC announces it, in effect that day, and had only the
day before at 17:06 UTC, a day behind. FRED's federal funds range has the
day's value by 07:01 Central on the morning it takes effect, so the U.S.
needs nothing (32.3); the ECB's is to be seen at its next change.

The sources, measured 2026-10-28 (both answer in under half a second; their
robots.txt allows both addresses):

* The Bank of Canada's press releases, its RSS 1.0 feed with the central
  banks' RSS-CB extension (12 KB, the last ten releases of every kind).
  Each item is a ``cb:news`` of type ``Announcement`` with its
  ``cb:occurrenceDate``; a rate announcement's description is the release's
  first sentence, in one form in every release read from 2020 to 2026:
  "The Bank of Canada today held its target for the overnight rate at 2.25%,
  with the Bank Rate at 2.5% and the deposit rate at 2.20%", "reduced ... by
  25 basis points to 2.25%", "increased ... to 2½%" (fractions until 2024,
  "½ %" and "¼ percent" before), "lowered ... by 50 basis points to 1 ¼
  percent" (2020). The item's ``dc:date`` is Ottawa's time marked "+00:00"
  (09:47 on 2026-10-28, two minutes after the 09:45 ET announcement), so the
  day is read from ``cb:occurrenceDate``. "As of 2021, a change takes effect
  the day after its announcement" (the Bank's policy interest rate page),
  as Valet dates it. The Bank Rate is the target plus a quarter point in
  every one of them, which checks the reading.
* The Bank of England's news feed, RSS 2.0 (26 KB, about fifty items back
  three months), each MPC decision an item at 12:00 London time on its day,
  titled "Bank Rate maintained at 3.75% - September 2026 Monetary Policy
  Summary and Minutes" ("Bank rate" in some), "Bank Rate reduced to 3.75%",
  "Bank Rate increased to 5.25%" (every title read, 2021 to 2026), linked to
  its Monetary Policy Summary. In effect that day, as IUDBEDR dates it.

A release is read with care: the rate must stand alone in the one place the
form puts it, between 0 and 25 %; the Bank of Canada's Bank Rate, where the
sentence gives it, must be the target plus a quarter point; the direction it
says ("held", "reduced", "increased") and its size where given ("by 25 basis
points") must follow from the rate in force before it. A release that names
the rate but does not read so, or two on one day, is a warning and adds
nothing (``joined``). A change already in the bank's own series is compared
with it, with a warning if the two differ; the series' value is drawn.
"""

from __future__ import annotations

import email.utils
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from .http import canadian_get, uk_get

BOC_PRESS_RELEASES_FEED = "https://www.bankofcanada.ca/content_type/press-releases/feed/"
BOE_NEWS_FEED = "https://www.bankofengland.co.uk/rss/news"
# The Bank of England dates its decisions by London's day.
BOE_TIMEZONE = "Europe/London"
# A rate read outside this range is not a policy rate misprinted but a misreading.
RATE_RANGE = (0.0, 25.0)

_RSS1 = "{http://purl.org/rss/1.0/}"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_CB = "{http://www.cbwiki.net/wiki/index.php/Specification_1.2/}"

# A rate as the releases write it: "2.25%", "2½%", "½ %", "1 ¼ percent", "5 per cent".
_FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75}
_RATE = r"(?:\d+(?:\.\d+)?(?:\s?[¼½¾])?|[¼½¾])\s?(?:%|per\s?cent)"
_DIRECTIONS = {
    "held": 0, "maintained": 0, "kept": 0,
    "increased": 1, "raised": 1,
    "reduced": -1, "lowered": -1, "cut": -1,
}
_VERB = "|".join(_DIRECTIONS)
_BOC_SENTENCE = re.compile(
    rf"The Bank of Canada today (?P<verb>{_VERB}) its target for the overnight rate"
    rf"(?: by (?P<bp>\d+) basis points)? (?:to|at) (?:the effective lower bound of )?(?P<rate>{_RATE})"
    rf"(?:(?=\.|$)|, with the Bank Rate at (?P<bank>{_RATE})(?=[ ,.]|$))"
)
# What makes a release one about the rate, read or not: its sentence names the
# target, or its title says the rate was moved or kept ("raises the policy
# rate", "maintains policy rate", "lowers overnight rate target"), not merely
# named ("publishes its 2027 schedule for policy interest rate announcements").
_BOC_ABOUT_RATE = re.compile(
    r"target for the overnight rate"
    r"|\b(?:rais|increas|lower|reduc|cut|maintain|hold|held|keep|kept)\w* (?:the )?(?:policy (?:interest )?rate|overnight rate target)",
    re.IGNORECASE,
)
_BOE_TITLE = re.compile(rf"Bank Rate (?P<verb>{_VERB}) (?:to|at) (?P<rate>{_RATE})(?=\s+[-–]\s|\s*$)", re.IGNORECASE)
_BOE_ABOUT_RATE = re.compile(r"^\s*Bank Rate\b", re.IGNORECASE)
_BOE_DECISION_LINK = "/monetary-policy-summary-and-minutes/"


@dataclass(frozen=True)
class Announcement:
    """A policy rate as its central bank announced it."""

    announced: pd.Timestamp  # the day it was announced
    effective: pd.Timestamp  # the first day it is in force
    rate: float  # percent
    direction: int  # what the words say: 1 raised, -1 lowered, 0 held
    change: float | None  # the size the words give ("by 25 basis points": 0.25), None where they give none
    words: str  # what was read, for the messages


@dataclass(frozen=True)
class Unread:
    """A release about the rate that could not be read with certainty: its day, the day it would take effect, its words."""

    announced: pd.Timestamp
    effective: pd.Timestamp
    words: str


@dataclass(frozen=True)
class Releases:
    """What a bank's feed says: its rate announcements read, and those about the rate that could not be."""

    bank: str  # "the Bank of Canada"
    found: tuple[Announcement, ...]
    unread: tuple[Unread, ...]


def rate_value(text: str) -> float:
    """The percentage a release writes (``_RATE``): "2.25%" 2.25, "3¼%" 3.25, "½ %" 0.5, "1 ¼ percent" 1.25."""
    number = re.sub(r"\s?(?:%|per\s?cent)$", "", text.strip())
    fraction = _FRACTIONS.get(number[-1:], 0.0)
    whole = number[:-1].strip() if fraction else number
    return (float(whole) if whole else 0.0) + fraction


def _words(text: str | None) -> str:
    return " ".join((text or "").split())


def _plausible(rate: float) -> bool:
    return RATE_RANGE[0] <= rate <= RATE_RANGE[1]


def read_boc_feed(body: bytes, bank_rate_above: float) -> Releases:
    """Read the Bank of Canada's press-release feed (``BOC_PRESS_RELEASES_FEED``): its rate announcements.

    ``bank_rate_above``: the Bank Rate's place above the target, which a
    sentence giving the Bank Rate must show. A change takes effect the day
    after its announcement.
    """
    root = ElementTree.fromstring(body)
    found: list[Announcement] = []
    unread: list[Unread] = []
    for item in root.iter(f"{_RSS1}item"):
        title = _words(item.findtext(f"{_RSS1}title"))
        description = _words(item.findtext(f"{_RSS1}description"))
        news = item.find(f"{_CB}news")
        day = news.findtext(f"{_CB}occurrenceDate") if news is not None else None
        if not (_BOC_ABOUT_RATE.search(title) or _BOC_ABOUT_RATE.search(description)):
            continue
        if day is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day.strip()):
            continue  # undated: nothing could be drawn from it on any day
        announced = pd.Timestamp(day.strip())
        match = _BOC_SENTENCE.match(description)
        rate = rate_value(match["rate"]) if match else None
        bank = rate_value(match["bank"]) if match and match["bank"] else None
        if (
            match is None
            or description.count("target for the overnight rate") != 1
            or not _plausible(rate)
            or (bank is not None and abs(bank - rate - bank_rate_above) > 1e-9)
        ):
            unread.append(Unread(announced, announced + pd.Timedelta(days=1), description or title))
            continue
        found.append(Announcement(
            announced, announced + pd.Timedelta(days=1), rate, _DIRECTIONS[match["verb"].lower()],
            int(match["bp"]) / 100 if match["bp"] else None, description,
        ))
    return Releases("the Bank of Canada", tuple(found), tuple(unread))


def read_boe_feed(body: bytes) -> Releases:
    """Read the Bank of England's news feed (``BOE_NEWS_FEED``): its MPC decisions on Bank Rate, in force the day announced."""
    root = ElementTree.fromstring(body)
    found: list[Announcement] = []
    unread: list[Unread] = []
    for item in root.iter("item"):
        title = _words(item.findtext("title"))
        link = item.findtext("link") or ""
        if not (_BOE_ABOUT_RATE.search(title) or _BOE_DECISION_LINK in link):
            continue
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue  # undated
        if published.tzinfo is None:
            continue  # a time without its zone gives no day for certain
        announced = pd.Timestamp(published).tz_convert(BOE_TIMEZONE).tz_localize(None).normalize()
        match = _BOE_TITLE.match(title)
        rate = rate_value(match["rate"]) if match else None
        if match is None or _BOE_DECISION_LINK not in link or not _plausible(rate):
            unread.append(Unread(announced, announced, title))
            continue
        found.append(Announcement(announced, announced, rate, _DIRECTIONS[match["verb"].lower()], None, title))
    return Releases("the Bank of England", tuple(found), tuple(unread))


def boc_releases(bank_rate_above: float) -> Releases:
    """The Bank of Canada's press releases (``read_boc_feed``), asked once, cached and retried as every source is."""
    return read_boc_feed(canadian_get(BOC_PRESS_RELEASES_FEED).content, bank_rate_above)


def boe_releases() -> Releases:
    """The Bank of England's news (``read_boe_feed``), asked once, cached and retried as every source is."""
    return read_boe_feed(uk_get(BOE_NEWS_FEED).content)


def joined(
    published: pd.Series, releases: Releases, series: str, end: pd.Timestamp, say: Callable[[str], None] = print
) -> tuple[pd.Series, pd.Timestamp | None]:
    """Return ``published`` with the changes announced after its last date, and the first such date (None: none added).

    ``published``: the bank's own series of the rate, date-indexed and
    sorted, a value from each day it changed (or every day). ``series``
    names it in the messages ("Valet's CBC20210"). Each announcement, in the
    order they take effect:

    * in force by the series' last date: the series' value on the first day
      it has from then compared with it, and a warning if they differ (the
      series' is drawn);
    * after it: checked against the rate in force before it (its direction,
      its size where given), then added if it changes the rate (a hold adds
      nothing) and said in a note, which says so if it takes effect after
      ``end``, the chart's last day; one that does not follow, a warning,
      and nothing added.

    Two announcements on one day, or one that could not be read
    (``Releases.unread``) on a day the series does not yet cover, are
    warnings, and add nothing.
    """
    last = published.index[-1]
    bank = releases.bank
    by_day: dict[pd.Timestamp, list[Announcement]] = {}
    for announcement in releases.found:
        by_day.setdefault(announcement.announced, []).append(announcement)
    for unread in releases.unread:
        if unread.effective > last:
            say(f"  Warning: {bank}'s release of {unread.announced:%Y-%m-%d} is about its policy rate but cannot be "
                f"read with certainty (“{unread.words}”); no announced change drawn from it.")
    accepted: list[tuple[pd.Timestamp, float]] = []
    for day in sorted(by_day):
        same_day = by_day[day]
        if len(same_day) > 1:
            if same_day[0].effective > last:
                rates = ", ".join(f"{announcement.rate:.2f}%" for announcement in same_day)
                say(f"  Warning: {bank} announced {len(same_day)} policy rates on {day:%Y-%m-%d} ({rates}); "
                    "none of them drawn.")
            continue
        (announcement,) = same_day
        effective, rate = announcement.effective, announcement.rate
        if effective <= last:
            held = published.loc[published.index >= effective]
            if abs(float(held.iloc[0]) - rate) > 1e-9:
                say(f"  Warning: {bank} announced {rate:.2f}% from {effective:%Y-%m-%d}, but {series} has "
                    f"{float(held.iloc[0]):.2f}% on {held.index[0]:%Y-%m-%d}; the series drawn.")
            continue
        before = accepted[-1][1] if accepted else float(published.iloc[-1])
        moved = rate - before
        direction = 0 if abs(moved) < 1e-9 else (1 if moved > 0 else -1)
        if direction != announcement.direction or (
            announcement.change is not None and abs(abs(moved) - announcement.change) > 1e-9
        ):
            say(f"  Warning: {bank}'s release of {day:%Y-%m-%d} (“{announcement.words}”) does not follow from "
                f"{before:.2f}% in force before it; no announced change drawn.")
            continue
        if direction != 0:
            accepted.append((effective, rate))
            drawn = f"; not yet in {series}" if effective <= end else ", takes effect after the chart ends; not drawn"
            say(f"  Note: {rate:.2f}% from {effective:%Y-%m-%d}, as {bank} announced on {day:%Y-%m-%d}{drawn}.")
    if not accepted:
        return published, None
    added = pd.Series([rate for _date, rate in accepted], index=pd.DatetimeIndex([date for date, _rate in accepted]))
    return pd.concat([published, added]), accepted[0][0]


def announcements_needed(published: pd.Series, end: pd.Timestamp) -> bool:
    """Whether a chart ending ``end`` could show a change the bank's series ``published`` does not have yet."""
    return not published.empty and end > published.index[-1]
