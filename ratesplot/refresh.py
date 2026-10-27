"""The automatic refresh (--auto-refresh:MIN, batch 11.3): when a refresh draws again, and the plain windows' timer.

Terry's items of 2026-10-08 and 2026-10-12 (plan 11.3, decision 23): every
MIN minutes, 5 when none is given and never more often, what Refresh does
(the quotes of the moment, and anything downloaded over an hour ago fetched
again), in the window, on the web page and in the plain matplotlib windows;
with --save the files are written again until Ctrl-C (``cli``).

Outside market hours (``config.MARKET_HOURS``) a refresh draws again only
when a quote has changed: the feed is asked first (``latest.quote_state``,
one request per nation shown), and the charts are left as they are when its
quotes are those of the refresh before (``Ticker``). Where a refresh can
bring nothing new (``PlotConfig.refresh_brings_nothing``: the quotes off, an
End before today, no quoted yield shown) there is none: the window and the
page grey the box out, and the command line draws once.

No GUI toolkit here: the window and the page keep their own timers (Tk's
``after``, a Streamlit fragment's ``run_every``) and ask a ``Ticker`` at
each; a plain window's timer is matplotlib's own (``attach``).
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

import pandas as pd
from matplotlib.figure import Figure

from . import http
from .config import DOWNLOAD_MAX_AGE_SECONDS, MARKET_HOURS, NATIONS, PlotConfig
from .latest import quote_state

# How often a plain window looks for a refresh's result, in milliseconds: the
# downloads run on a thread of their own, the drawing on the window's.
_POLL_MS = 250


class Ended(Exception):
    """A refresh can bring nothing new any more (an End date that was today is past): the refresh ends, with this reason."""


def in_market_hours(config: PlotConfig, now: pd.Timestamp | None = None) -> bool:
    """Whether the market of a chart shown with quoted yields is within its hours (``MARKET_HOURS``, Monday to Friday, in its own zone)."""
    now = pd.Timestamp.now(tz="UTC") if now is None else now
    first, last = MARKET_HOURS
    for nation in NATIONS:
        if getattr(config, nation.show_field) and config.quoted_columns(nation.key):
            local = now.tz_convert(nation.market_timezone)
            if local.weekday() < 5 and first <= local.hour < last:
                return True
    return False


def forget_old_downloads() -> int:
    """Refresh's first step: drop the downloads kept over an hour (``DOWNLOAD_MAX_AGE_SECONDS``), so the drawing fetches them again; return how many."""
    return http.forget_downloads_older_than(DOWNLOAD_MAX_AGE_SECONDS)


class Ticker:
    """Whether each tick of an automatic refresh draws again (``due``): one for each window, page visitor or command line.

    Within market hours, always. Outside them the quotes are asked for
    (``latest.quote_state``), and the charts drawn again only when those
    differ from the tick before's. The first tick outside them (the first of
    all, or after one within them) draws again: which quotes the last drawing
    had is not known here, and a quote that came after it would otherwise be
    missed until the next market day.
    """

    def __init__(self) -> None:
        self._quotes: tuple | None = None

    def due(self, config: PlotConfig, now: pd.Timestamp | None = None) -> bool:
        """Whether this tick draws ``config`` again; says why not. Called in a drawing (``http.drawing_downloads``), so the request is logged."""
        if in_market_hours(config, now):
            self._quotes = None
            return True
        try:
            quotes = quote_state(config)
        except Exception as exc:  # the feed not answering: nothing new could come from it
            print(f"  Warning: intraday quotes unavailable ({exc}); not drawn again.")
            return False
        changed = self._quotes is None or quotes != self._quotes
        self._quotes = quotes
        if not changed:
            print("Outside market hours, and no quote has changed since the last refresh: not drawn again.")
        return changed


def attach(
    figure: Figure,
    minutes: int,
    refreshed: Callable[[Ticker], object | None],
    draw: Callable[[object], None],
) -> None:
    """Refresh a plain matplotlib window's chart every ``minutes`` (--no-gui --au): matplotlib's own timers.

    At each tick ``refreshed`` runs on a thread of its own, in a drawing of
    its own (the downloads), and returns what to draw, or None for nothing;
    ``draw`` then draws it on the window's thread. It raises ``Ended`` when no
    refresh can bring anything new any more, which stops the timer. A tick
    while the one before is still at work is skipped. Stopped when the window
    is closed.
    """
    figure._ratesplot_refresh_window = _RefreshedWindow(figure, minutes, refreshed, draw)  # kept with the figure


class _RefreshedWindow:
    """One plain window's automatic refresh (``attach``)."""

    def __init__(self, figure: Figure, minutes: int, refreshed: Callable[[Ticker], object | None], draw: Callable[[object], None]) -> None:
        self.refreshed = refreshed
        self.draw = draw
        self.ticker = Ticker()
        self.results: queue.Queue = queue.Queue()
        self.working = False
        canvas = figure.canvas
        self.timers = [canvas.new_timer(interval=minutes * 60_000), canvas.new_timer(interval=_POLL_MS)]
        self.timers[0].add_callback(self._tick)
        self.timers[1].add_callback(self._poll)
        for timer in self.timers:
            timer.start()
        canvas.mpl_connect("close_event", lambda _event: self._stop())

    def _stop(self) -> None:
        for timer in self.timers:
            timer.stop()

    def _tick(self) -> None:
        if self.working:
            return
        self.working = True
        threading.Thread(target=self._work, name="ratesplot refresh", daemon=True).start()

    def _work(self) -> None:
        """Worker thread: what to draw, or None; never touches the window."""
        result: object | None = None
        try:
            with http.drawing_downloads():
                result = self.refreshed(self.ticker)
        except Ended as ended:
            print(f"Automatic refresh ended: {ended}.")
            result = ended
        except Exception as exc:  # the chart is left as it was; named, never swallowed
            why, trace = http.not_drawn(exc)
            print(trace or "", end="")
            print(f"  Warning: the automatic refresh drew nothing ({why}); the chart is left as it was.")
        self.results.put(result)

    def _poll(self) -> None:
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            return
        self.working = False
        if isinstance(result, Ended):
            self._stop()
        elif result is not None:
            self.draw(result)
