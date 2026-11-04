"""How long a drawing should still take, for the line the window and the page show while one draws (batch 35.1).

Terry, 2026-11-03 (decision 101): "Please wait about N s (M s so far)", the
time still expected first, "how much additional time is expected before
waiting is over, not the grand total", worked out by "an internal algorithm",
"updating the algorithm's parameters on the fly"; the time taken as measured
second. This module holds the sum and the words; each front end shows them
(``web._await_drawing``, ``gui._show_wait``). It imports no front end.

The time still expected is the sum of the parts, each from the drawings before:

- the drawings ahead, what is left of each one's own estimate (the page:
  drawings are made one at a time, ``web._take_turn``), and a drawing queued
  behind this one (the window: its "Will redraw with the new settings ...");
- the downloads: each request a nation asked for at its last drawing of the same
  kind whose kept copy is no longer used (``http.download_is_kept``), at its own
  last time, or its host's. The kinds are a chart reaching today and one ending
  before it, since a chart ending before the baked history's end asks for
  nothing (batch 19.2 (b); found 2026-11-04, a chart ending in 2020 promised
  50 s, the starting figures, and took 6). Hosts are asked side by side and each host's requests in turn
  (``http.host_turn``, ``plotting._download_side_by_side``), so this part is
  the longest host's sum, not the sum of them all: measured 2026-11-04 on
  Buddug, four nations with their rates took 92 s of which the Bank of England
  alone 91 s, the other six hosts 22 s together;
- the automatic start's own work, what the first pass does beyond waiting;
- each chart, a time scaled by its size in pixels; with the quotes of the
  moment (``late``, what a chart asks for beyond the first pass) when they can
  reach it (``PlotConfig.refresh_brings_nothing``).

After each drawing each part's figure moves towards what was measured, the
newest weighing about a third (``_towards``). A drawing stopped, or a source
that failed, teaches nothing of what it spoiled. During a drawing the sum is
worked out again as each request and chart ends, and counts down between them;
a step that overruns leaves "nearly done", never 0 or less (``wait_text``).
The figure shown counts down steadily and rises only on a real jump
(``Wait.line``), so it does not flicker.

The figures are kept by each front end (``Figures``): in the server's memory on
the page, so a Reboot or a sleep starts again from the starting figures; in the
settings file in the window (``Figures.saved``, not the requests themselves,
which a new run of the window has none kept of anyway).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING

import pandas as pd

from .config import DEFAULT_CANVAS_PX, PlotConfig
from .http import asking_for, download_is_kept, host_of

if TYPE_CHECKING:
    from .http import _Drawing

# The newest measurement's weight in a figure (the plan: "about a third").
_NEWEST_WEIGHT = 1 / 3

# The starting figures, measured on Buddug 2026-11-04 (the plan's "measured
# before building"), a chart at the default size with no download in it: a
# nation's chart built and saved in 0.8 to 1.0 s with its default curves, up to
# 2.2 s with its rates; the first pass's own work about 0.1 s for each nation;
# one nation's quotes about 0.2 s. On a server slower: the first drawing's
# measurement moves them.
STARTING_CHART_SECONDS = 1.0
STARTING_START_SECONDS = 0.1
STARTING_LATE_SECONDS = 0.2
# A chart's time against its size, measured the same day: 0.85 s at 0.8
# megapixels, 1.0 s at the default 3.1, 1.75 s at 12.6, so about a constant and
# a part that grows with the pixels.
_CHART_CONSTANT_SECONDS = 0.75
_CHART_SECONDS_PER_MEGAPIXEL = 0.08
# Each host's request, from the same day's cold drawings, the first request to
# each (a stall of about 11 s on Buddug, seen at one host or more of each
# drawing's first) averaged in, so a first drawing is not promised too soon.
_STARTING_HOST_SECONDS = {
    "fred.stlouisfed.org": 1.0,
    "home.treasury.gov": 0.5,
    "api.fiscaldata.treasury.gov": 0.5,
    "www.bankofcanada.ca": 1.0,
    "www150.statcan.gc.ca": 1.0,
    "www.bankofengland.co.uk": 15.0,
    "www.ons.gov.uk": 1.0,
    "api.statistiken.bundesbank.de": 0.5,
    "data-api.ecb.europa.eu": 0.5,
    "ec.europa.eu": 1.5,
}
_UNKNOWN_HOST_SECONDS = 1.0
# How many requests each nation's default chart asks of each host, counted cold
# on 2026-11-04; a nation's own last drawing replaces its row.
_STARTING_ASKED = {
    "cdn": {"www.bankofcanada.ca": 6, "www150.statcan.gc.ca": 3},
    "us": {"fred.stlouisfed.org": 9, "home.treasury.gov": 1, "api.fiscaldata.treasury.gov": 1},
    "uk": {"www.bankofengland.co.uk": 3, "www.ons.gov.uk": 3},
    "de": {"api.statistiken.bundesbank.de": 8, "data-api.ecb.europa.eu": 1, "ec.europa.eu": 4},
}
# Below this the words change: "nearly done" rather than "about 0 s".
_NEARLY_DONE_SECONDS = 1.0
# Seconds below this, minutes from it (the plan: "seconds below about 90 s").
_SECONDS_UP_TO = 90
# Whole seconds up to this; above it, rounded to 5 (the plan), since no estimate is that sure.
_EXACT_SECONDS_UP_TO = 20
# A figure shown rises only by more than this: the larger of these seconds and
# this share of what is shown (the plan: "rises only on a real jump").
_JUMP_SECONDS = 3.0
_JUMP_SHARE = 0.3


def _towards(old: float, measured: float) -> float:
    """A figure moved towards what was measured, the newest weighing about a third."""
    return old + (measured - old) * _NEWEST_WEIGHT


def _size_factor(pixels: int) -> float:
    """A chart's time at ``pixels`` against its time at the default size."""
    default = DEFAULT_CANVAS_PX[0] * DEFAULT_CANVAS_PX[1]
    return (_CHART_CONSTANT_SECONDS + _CHART_SECONDS_PER_MEGAPIXEL * pixels / 1e6) / (
        _CHART_CONSTANT_SECONDS + _CHART_SECONDS_PER_MEGAPIXEL * default / 1e6
    )


def _seconds_figure(value: object) -> float | None:
    """``value`` if it is a time a figure can be (from a settings file, which may have been edited), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0.0 <= value < 86400.0 else None


class Figures:
    """What the drawings so far have taught, one set per process (the page) or per window; safe across threads.

    ``saved`` (``to_saved``): the figures as the settings file keeps them; what
    cannot be read is left at its starting figure.
    """

    def __init__(self, saved: object = None) -> None:
        self._lock = threading.Lock()
        self.chart = STARTING_CHART_SECONDS  # seconds for one chart at the default size, its downloads and quotes aside
        self.start = STARTING_START_SECONDS  # seconds for the first pass's own work, for each nation
        self.late = STARTING_LATE_SECONDS  # seconds a chart spends on its quotes and any request of its own
        self.hosts = dict(_STARTING_HOST_SECONDS)  # host -> seconds a request takes
        self.asked = {nation: dict(hosts) for nation, hosts in _STARTING_ASKED.items()}  # nation -> host -> requests
        # (nation, whether its chart reaches today) -> the requests it last asked for (not saved).
        self._keys: dict[tuple[str, bool], set[tuple]] = {}
        self._request_seconds: dict[tuple, float] = {}  # request -> its last time (not saved)
        if isinstance(saved, Mapping):
            self._read(saved)

    def _read(self, saved: Mapping) -> None:
        """Take the figures ``to_saved`` wrote; anything else in the file is left out."""
        for name in ("chart", "start", "late"):
            figure = _seconds_figure(saved.get(name))
            if figure is not None:
                setattr(self, name, figure)
        hosts = saved.get("hosts")
        if isinstance(hosts, Mapping):
            for host, seconds in hosts.items():
                figure = _seconds_figure(seconds)
                if isinstance(host, str) and figure is not None:
                    self.hosts[host] = figure
        asked = saved.get("asked")
        if isinstance(asked, Mapping):
            for nation, hosts in asked.items():
                if isinstance(nation, str) and isinstance(hosts, Mapping):
                    counts = {host: count for host, count in hosts.items() if isinstance(host, str) and isinstance(count, int) and 0 < count < 1000}
                    if counts:
                        self.asked[nation] = counts

    def to_saved(self) -> dict:
        """The figures as the settings file keeps them (plain numbers and names)."""
        with self._lock:
            return {
                "chart": round(self.chart, 3),
                "start": round(self.start, 3),
                "late": round(self.late, 3),
                "hosts": {host: round(seconds, 3) for host, seconds in self.hosts.items()},
                "asked": {nation: dict(hosts) for nation, hosts in self.asked.items()},
            }

    def chart_seconds(self, pixels: int) -> float:
        """One chart's expected time at ``pixels``, its downloads and quotes aside."""
        return self.chart * _size_factor(pixels)

    def expected_requests(self, nations: Iterable[str], live: bool = True) -> dict[str, list[tuple[tuple | None, float]]]:
        """The requests the nations' charts should make now, by host: [(its key or None where only a count is known, seconds)].

        A nation drawn in this run: the requests of its last drawing of this
        kind (``live``: its chart reaches today) no longer kept. A nation not
        yet drawn: the count last saved, or the starting one, every request
        to be made, if its chart reaches today; else none, from the baked history.
        """
        with self._lock:
            expected: dict[str, list[tuple[tuple | None, float]]] = {}
            seen: set[tuple] = set()
            for nation in nations:
                keys = self._keys.get((nation, live))
                if keys is None:
                    for host, count in (self.asked.get(nation, {}) if live else {}).items():
                        seconds = self.hosts.get(host, _UNKNOWN_HOST_SECONDS)
                        expected.setdefault(host, []).extend([(None, seconds)] * count)
                    continue
                for key in keys:
                    if key in seen or download_is_kept(key):
                        continue
                    seen.add(key)
                    host = host_of(key)
                    seconds = self._request_seconds.get(key, self.hosts.get(host, _UNKNOWN_HOST_SECONDS))
                    expected.setdefault(host, []).append((key, seconds))
            return expected

    def learn(
        self,
        requests: Iterable[tuple[str | None, tuple, float]],
        asked: Mapping[str, set[tuple]],
        start: float | None,
        charts: Iterable[float],
        lates: Iterable[float],
        *,
        nations: Iterable[str] = (),
        live: bool = True,
    ) -> None:
        """Move each figure towards one drawing's measurements.

        ``asked``: each nation's requests, a nation of ``nations`` not named
        there having asked for none; ``start``: its first pass's own work for
        each nation, None where a failure spoiled it; ``charts``: each chart
        drawn, at the default size; ``lates``: each chart's quotes and requests
        of its own; ``live``: whether its charts reach today. Only such a
        drawing's requests are saved: a new run of the window starts with none kept.
        """
        with self._lock:
            for _nation, key, seconds in requests:
                host = host_of(key)
                self.hosts[host] = _towards(self.hosts.get(host, _UNKNOWN_HOST_SECONDS), seconds)
                self._request_seconds[key] = seconds
            for nation in {*nations, *asked}:
                keys = asked.get(nation, set())
                self._keys[(nation, live)] = set(keys)
                counts: dict[str, int] = {}
                for key in keys:
                    host = host_of(key)
                    counts[host] = counts.get(host, 0) + 1
                if live and counts:
                    self.asked[nation] = counts
            if start is not None:
                self.start = _towards(self.start, start)
            for chart in charts:
                self.chart = _towards(self.chart, chart)
            for late in lates:
                self.late = _towards(self.late, late)


def expected_text(seconds: float) -> str:
    """The time still expected, in Terry's words: "12 s", "45 s" (to 5 above 20 s), "2 min" (from about 90 s)."""
    if seconds >= _SECONDS_UP_TO:
        return f"{round(seconds / 60)} min"
    if seconds > _EXACT_SECONDS_UP_TO:
        return f"{5 * round(seconds / 5)} s"
    return f"{max(round(seconds), 1)} s"


def taken_text(seconds: float) -> str:
    """The time taken as measured: "5 s", then "1 min 35 s" (each second counts, as on a clock)."""
    whole = int(seconds)
    return f"{whole} s" if whole < _SECONDS_UP_TO else f"{whole // 60} min {whole % 60} s"


def wait_text(left: float, taken: float) -> str:
    """The line itself: "Please wait about 12 s (5 s so far)", or "nearly done" once the time expected has run out."""
    if left < _NEARLY_DONE_SECONDS:
        return f"Please wait, nearly done ({taken_text(taken)} so far)"
    return f"Please wait about {expected_text(left)} ({taken_text(taken)} so far)"


class Wait:
    """One drawing's wait, from before its turn to its last chart: what is left of it, and the line that says so.

    The worker drawing it calls ``began_work``, ``start_ended``, ``chart_begun``
    and ``chart_ended`` for each chart, and ``finished`` if it was not stopped.
    A front end's own thread calls ``line`` and ``remaining`` meanwhile.
    ``ahead``: what is left of the drawings before this one (the page);
    ``began``: when the wait began, where it began before this drawing (the
    window's queued one, ``then`` on the one before it).
    """

    def __init__(
        self,
        figures: Figures,
        nations: Iterable[str],
        pixels: int,
        *,
        quotes: bool = False,
        side_by_side: bool = True,
        live: bool = True,
        ahead: Callable[[], float] | None = None,
        began: float | None = None,
    ) -> None:
        self.began = time.monotonic() if began is None else began
        self.then: Callable[[], float] | None = None  # what is left of a drawing queued behind this one (the window)
        self._figures = figures
        self._nations = list(nations)
        self._pixels = pixels
        self._quotes = quotes
        # With the requests made in a first pass of their own, a chart finds
        # them kept; else (one nation, its start given, ``plotting._download_side_by_side``) each chart makes them itself.
        self._side_by_side = side_by_side
        self._live = live
        self._ahead = ahead
        self._lock = threading.Lock()
        self._expected = figures.expected_requests(self._nations, live)
        self._start_own = figures.start * len(self._nations)
        self._charts_left = len(self._nations)
        self._chart_time = figures.chart_seconds(pixels) + (figures.late if quotes else 0.0)
        self._downloads: _Drawing | None = None
        self._seen = 0  # requests of ``_downloads`` already taken off ``_expected``
        self._in_start = False
        self._in_chart = False
        self._step_began = 0.0  # when the start or the chart under way began
        self._progress_at = 0.0  # when the last request or step ended
        self._step_requests = 0.0  # seconds of requests in the chart under way
        self._step_quotes = 0.0  # the drawing's quote seconds when the chart under way began
        self._step_requests_seen = 0
        self._measured_start: float | None = None
        self._measured_charts: list[float] = []
        self._measured_lates: list[float] = []
        self._shown: float | None = None
        self._shown_at = 0.0

    @classmethod
    def of_config(
        cls,
        figures: Figures,
        config: PlotConfig,
        nations: Iterable[str],
        *,
        ahead: Callable[[], float] | None = None,
        began: float | None = None,
    ) -> Wait:
        """The wait for drawing ``config``, the charts of ``nations``: the quotes by the refresh's own rule (they reach the chart or not)."""
        nations = list(nations)
        return cls(
            figures,
            nations,
            config.width_px * config.height_px,
            quotes=config.refresh_brings_nothing is None,
            side_by_side=config.start is None or len(nations) >= 2,
            live=config.end >= pd.Timestamp.today().normalize(),
            ahead=ahead,
            began=began,
        )

    # -- what the worker reports ---------------------------------------------

    def began_work(self, downloads: _Drawing) -> None:
        """The drawing's turn has come: what it should download is judged again, a drawing before it having perhaps kept them."""
        expected = self._figures.expected_requests(self._nations, self._live)
        now = time.monotonic()
        with self._lock:
            self._expected = expected
            self._downloads = downloads
            self._seen = 0
            self._in_start = True
            self._step_began = self._progress_at = now

    def start_ended(self) -> None:
        """The first pass has ended: the End and the start are known, its requests made."""
        now = time.monotonic()
        with self._lock:
            self._take_requests(now)
            downloads = self._downloads
            if downloads is not None and not downloads.failed and self._nations:
                by_host: dict[str, float] = {}
                for _nation, key, seconds in downloads.requests:
                    host = host_of(key)
                    by_host[host] = by_host.get(host, 0.0) + seconds
                own = now - self._step_began - max(by_host.values(), default=0.0)
                self._measured_start = max(own, 0.0) / len(self._nations)
            if self._side_by_side:
                self._expected = {}  # what was not asked for is not needed now
            self._in_start = False
            self._progress_at = now

    def chart_begun(self, nation: str) -> None:
        """One nation's chart is begun; its requests are named as its own (``http.asking_for``), on the worker's thread."""
        asking_for(nation)
        now = time.monotonic()
        with self._lock:
            self._take_requests(now)
            self._in_chart = True
            self._step_began = self._progress_at = now
            self._step_requests_seen = len(self._downloads.requests) if self._downloads is not None else 0
            self._step_quotes = self._downloads.quote_seconds if self._downloads is not None else 0.0

    def chart_ended(self, drawn: bool) -> None:
        """The chart under way has ended. ``drawn`` False: its source failed, and its time teaches nothing."""
        asking_for(None)
        now = time.monotonic()
        with self._lock:
            self._take_requests(now)
            downloads = self._downloads
            if drawn and downloads is not None:
                requests = sum(seconds for _nation, _key, seconds in downloads.requests[self._step_requests_seen:])
                quotes = downloads.quote_seconds - self._step_quotes
                own = max(now - self._step_began - requests - quotes, 0.0)
                self._measured_charts.append(own / _size_factor(self._pixels))
                if self._quotes:
                    # A request of its own a chart makes because no first pass made it counts under the downloads, as expected.
                    self._measured_lates.append((requests if self._side_by_side else 0.0) + quotes)
            self._charts_left = max(self._charts_left - 1, 0)
            self._in_chart = False
            self._progress_at = now

    def finished(self) -> None:
        """The drawing has ended and was not stopped: the figures move towards what it measured."""
        downloads = self._downloads
        if downloads is None:
            return
        self._figures.learn(
            downloads.requests,
            downloads.asked,
            self._measured_start,
            self._measured_charts,
            self._measured_lates,
            nations=self._nations,
            live=self._live,
        )

    # -- what the front ends ask ---------------------------------------------

    def _take_requests(self, now: float) -> None:
        """Take the requests that have ended off what is expected; the caller holds the lock."""
        downloads = self._downloads
        if downloads is None:
            return
        ended = downloads.requests[self._seen:]
        for _nation, key, _seconds in ended:
            waiting = self._expected.get(host_of(key))
            if not waiting:
                continue
            at = next((index for index, (each, _time) in enumerate(waiting) if each == key), None)
            if at is None:
                at = next((index for index, (each, _time) in enumerate(waiting) if each is None), None)
            if at is not None:
                del waiting[at]
        if ended:
            self._seen += len(ended)
            self._progress_at = now

    def _downloads_left(self) -> float:
        """The longest host's expected requests still to end: hosts are asked side by side, each host's in turn."""
        return max((sum(seconds for _key, seconds in waiting) for waiting in self._expected.values()), default=0.0)

    def whole(self) -> float:
        """This drawing's whole estimate, as it stands, with nothing yet done: for a drawing queued behind another."""
        with self._lock:
            return self._start_own + self._downloads_left() + self._charts_left * self._chart_time

    def remaining(self, now: float | None = None) -> float:
        """The seconds still expected before this wait is over, never below 0: the drawings ahead, its own, one queued behind."""
        now = time.monotonic() if now is None else now
        ahead = self._ahead if self._downloads is None else None
        before = ahead() if ahead is not None else 0.0
        return before + self.own_remaining(now) + (self.then() if self.then is not None else 0.0)

    def own_remaining(self, now: float | None = None) -> float:
        """This drawing's own part of the wait; each step's time counted down while it runs. What a drawing behind this one counts of it, so none is counted twice."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._take_requests(now)
            in_step = now - self._progress_at
            downloads = self._downloads_left()
            if self._downloads is None:  # its turn has not come
                left = self._start_own + downloads + self._charts_left * self._chart_time
            elif self._in_start:
                left = max(self._start_own + downloads - in_step, 0.0) + self._charts_left * self._chart_time
            elif self._in_chart:
                others = max(self._charts_left - 1, 0) * self._chart_time
                left = max(downloads + self._chart_time - in_step, 0.0) + others
            else:
                left = downloads + self._charts_left * self._chart_time
        return left

    def line(self, now: float | None = None) -> str:
        """The line to show now: the figure counts down steadily, drops at once, and rises only on a real jump."""
        now = time.monotonic() if now is None else now
        worked_out = self.remaining(now)
        if self._shown is None:
            shown = worked_out
        else:
            counted = max(self._shown - (now - self._shown_at), 0.0)
            rise_needed = max(_JUMP_SECONDS, _JUMP_SHARE * counted)
            shown = worked_out if worked_out < counted or worked_out > counted + rise_needed else counted
        self._shown, self._shown_at = shown, now
        return wait_text(shown, now - self.began)
