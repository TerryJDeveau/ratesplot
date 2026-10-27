"""HTTP and source-format helpers for FRED, Bank of Canada, Statistics Canada, the UK's and Germany's sources and the latest-value sources; the message log's download lines."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import html
import http.client as http_client
import io
import json
import os
import pickle
import re
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence, TypeVar
from urllib.parse import urlsplit

import pandas as pd
import requests
from urllib3.exceptions import MaxRetryError, ProtocolError

from .config import (
    CANADIAN_SESSION,
    DE_SESSION,
    DATE_COLUMN,
    FRED_CSV_URL,
    HTTP_TIMEOUT_SECONDS,
    LATEST_SESSION,
    RETRY_WAIT_SECONDS,
    SOURCE_NAMES,
    UK_SESSION,
)
from .console import current_writer, this_thread_output_to

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Session download cache
# ---------------------------------------------------------------------------
# Off by default: a command-line run downloads everything fresh, as it always
# has. The GUI turns it on so that redrawing after a change re-processes what
# was already downloaded instead of fetching it again; its Refresh button drops
# what is older than an hour (``forget_downloads_older_than``).
# The command line turns it on for a run without --start, whose trial pass
# (plotting.resolve_start) and drawing then share each download; it is still
# fresh for every run.
# The web page (ratesplot.web) serves every visitor from one process and keeps
# running for days, so there each download is kept for a limited time only
# (``max_age_seconds``): visitors share the downloads, and still see new data
# within that time. Entries are stored with the time they were fetched (by
# the monotonic clock for their age, and by the wall clock for the message
# log's "the oldest from …").
# Keyed by URL (and query parameters, or a POST's JSON). The download helpers
# below use it; the Statistics Canada WDS fallback (a POST) too, since 2026-10-21:
# with Statistics Canada down it is asked in every drawing (``canadian_post``).

_download_cache: dict[tuple, tuple[float, float, object]] | None = None
_download_cache_max_age: float | None = None  # seconds; None keeps each download for the session
_download_cache_lock = threading.Lock()

# ---------------------------------------------------------------------------
# The last good copy of every download (batch 20)
# ---------------------------------------------------------------------------
# Terry, 2026-10-21, after FRED and Statistics Canada had answered for hours
# with their outage pages: "It is nuts to discard data in hand one day and
# then be unable to display it the next day because some site was down for
# maintenance" (decision 48). So every download that succeeds through the
# cache below is also kept on disk, one file per request, replaced at each
# success; when a later request for it fails (an outage page, a bot check, a
# timeout, an error status after the retries), the copy is used and the
# drawing names the source and the copy's date (``drawing_downloads``). The
# live request is always made first, so a copy never stands in for an answer
# and revisions still arrive. Off by default; the window, the web page and
# the command line turn it on (``enable_last_good_copies``); the harnesses,
# which replace ``_cached``, and tools/check_sources.py, which must see a
# source fail, do not. Intraday quotes are never cached, so never kept: a
# quote of another moment is not the day's. On the web page's server the disk
# lasts only while the app runs (a Reboot or a sleep starts it empty); the
# baked history of batch 19.2 is what lasts there.

_copies_folder: Path | None = None


def last_good_folder() -> Path:
    """``%LOCALAPPDATA%\\ratesplot\\last_good`` on Windows (``~/.cache/ratesplot/last_good`` elsewhere)."""
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".cache") / "ratesplot" / "last_good"


def enable_last_good_copies(folder: Path | None = None) -> None:
    """Keep the last good copy of every cached download in ``folder`` (``last_good_folder``), and use it when its source fails.

    A folder that cannot be made leaves the copies off, with a note.
    """
    global _copies_folder
    folder = folder or last_good_folder()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"  Note: no copies of the downloads can be kept in {folder} ({exc}); a source that fails is not drawn.")
        return
    _copies_folder = folder


def _copy_label(key: tuple) -> str:
    """Name a download for the message log: its group's label (``downloads_of``), else its series or host."""
    groups = _groups()
    if groups:
        return groups[-1].label
    return f"FRED {key[1]}" if key[0] == "fred" else urlsplit(key[1]).netloc


def _copy_path(key: tuple) -> Path:
    assert _copies_folder is not None
    return _copies_folder / (hashlib.sha256(repr(key).encode()).hexdigest() + ".pickle")


def _keep_copy(key: tuple, result: object) -> None:
    """Write ``result`` as ``key``'s last good copy, replacing the one before (atomically)."""
    path = _copy_path(key)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_bytes(pickle.dumps((key, time.time(), result)))
        os.replace(temporary, path)
    except OSError as exc:  # another window reading it on Windows, a full disk: the older copy stays
        print(f"  Note: {_copy_label(key)}: no new copy kept ({exc}).")
        with contextlib.suppress(OSError):
            temporary.unlink()


def _last_good_copy(key: tuple) -> tuple[float, object] | None:
    """Return ``(when it was downloaded, the copy)`` kept for ``key``; None if there is none."""
    path = _copy_path(key)
    try:
        stored_key, fetched_wall, result = pickle.loads(path.read_bytes())
    except FileNotFoundError:
        return None
    except Exception as exc:  # a damaged copy is no copy; said, not swallowed
        print(f"  Note: {_copy_label(key)}: its kept copy could not be read ({exc}).")
        return None
    return (fetched_wall, result) if stored_key == key else None


def _copy_used(key: tuple, fetched_wall: float, failure: Exception) -> None:
    """Record that ``key``'s source failed and its copy was used: in the drawing's log at its end (its source's warning), else at once."""
    label = _copy_label(key)
    why = _why(failure)
    drawing = getattr(_log_state, "drawing", None)
    if drawing is None:
        print(f"  Warning: {label}: {why}; drawn from its last good copy, downloaded {_utc_text(fetched_wall)}.")
        return
    with drawing.lock:
        earlier = drawing.copies.get(label)
        if earlier is None or fetched_wall < earlier[0]:  # a group's oldest copy is the one named
            drawing.copies[label] = (fetched_wall, why)
        copies = drawing.fallback(source_name(_host_of(key)), why).copies
        copies[label] = min(fetched_wall, copies.get(label, fetched_wall))


def baked_alone(label: str, failure: Exception, last: pd.Timestamp) -> None:
    """Record that series ``label``'s recent part failed and its bake alone is drawn, to ``last``: in its source's warning at the drawing's end, else at once.

    Called by ``baked.with_recent_part`` and ``frame_with_recent_part``.
    ``label`` begins with its source's name (``config.SOURCE_NAMES``).
    """
    why = _why(failure)
    drawing = getattr(_log_state, "drawing", None)
    if drawing is None:
        print(f"  Warning: {label}: its recent values unavailable ({why}); drawn from its baked history, to {last:%Y-%m-%d}.")
        return
    with drawing.lock:
        drawing.fallback(_source_named(label), why).baked.setdefault(label, last)


def _why(failure: BaseException) -> str:
    return str(failure) or type(failure).__name__


def source_name(host: str) -> str:
    """A source's name in the message log (``config.SOURCE_NAMES``), the host itself for one not named there."""
    return SOURCE_NAMES.get(host, host)


def _source_named(label: str) -> str:
    """The source whose name ``label`` begins with (the longest that fits), else the label itself."""
    names = sorted(set(SOURCE_NAMES.values()), key=len, reverse=True)
    return next((name for name in names if label.startswith(f"{name} ")), label)


def _within(name: str, label: str) -> str:
    """``label`` without its source's name in front: "FRED DGS10" -> "DGS10"."""
    return label[len(name) + 1 :] if label.startswith(f"{name} ") else label


def _utc_text(wall: float) -> str:
    """``2026-10-21 18:30 UTC``."""
    return f"{datetime.fromtimestamp(wall, timezone.utc):%Y-%m-%d %H:%M} UTC"


# ---------------------------------------------------------------------------
# The message log's download lines
# ---------------------------------------------------------------------------
# Terry, 2026-10-12: a time stamp in UTC only for a real download from a
# source. So each real download is logged with the time it began,
# "2026-10-13 14:32:05 -> Bank of Canada benchmark yields", once for each
# group of downloads named by ``downloads_of``, however many requests the
# group makes. A download served again from the session's cache is not
# logged by itself; a drawing ends with one line counting them ("Reused 14
# earlier downloads, the oldest from 2026-10-13 16:32:05 UTC"), since how old
# the data are still matters. The built-in history (the baked and transcribed data)
# is never logged: it is the same on every run.
#
# A drawing (``drawing_downloads``) writes its lines where its thread's
# output went when it began. The trial pass of ``plotting.resolve_start``
# discards everything it prints, but its downloads are real ones, and the
# real pass then finds them in the cache: they are logged once, by the
# trial pass, and are not counted as reused (they were fetched during
# this drawing).


@dataclass
class _Group:
    """A group of downloads named by ``downloads_of``; its line is written at its first real download."""

    label: str
    logged: bool = False


@dataclass
class _Fallback:
    """What a drawing drew in place of one source's answers, for one cause: its warning at the drawing's end (batch 19.4)."""

    # A group of downloads (its label) -> when its oldest copy used was downloaded (time.time()).
    copies: dict[str, float] = field(default_factory=dict)
    # A series drawn from its bake alone (its label) -> the bake's last date.
    baked: dict[str, pd.Timestamp] = field(default_factory=dict)

    def warning(self, name: str, why: str) -> str:
        """``  Warning: FRED: WHY. 13 series drawn from their baked history: DGS2, DGS10 to 2026-10-21; GDP to 2026-04-01. ...``

        The cause once; the series grouped by how far their bake reaches,
        the latest first (Terry, 2026-10-22, decision 53), each named
        without its source's name; the copies by when they were downloaded,
        each by its group's whole label ("FRED Treasury yields", "Canadian
        policy rate"): a group may draw on two sources ("ECB and Eurostat
        government debt"), and is then listed in each one's warning.
        """
        parts = [f"  Warning: {name}: {why}."]
        if self.baked:
            reach: dict[pd.Timestamp, list[str]] = {}
            for label, last in self.baked.items():
                reach.setdefault(last, []).append(_within(name, label))
            count = len(self.baked)
            groups = "; ".join(f"{', '.join(series)} to {last:%Y-%m-%d}" for last, series in sorted(reach.items(), reverse=True))
            parts.append(f"{count} series drawn from {'its' if count == 1 else 'their'} baked history: {groups}.")
        downloaded: dict[str, list[str]] = {}
        for label, when in sorted(self.copies.items(), key=lambda item: item[1]):
            downloaded.setdefault(_utc_text(when), []).append(label)
        for when, labels in downloaded.items():
            parts.append(f"Drawn from {'its last good copy' if len(labels) == 1 else 'their last good copies'}, "
                         f"downloaded {when}: {'; '.join(labels)}.")
        return " ".join(parts) + "\n"


@dataclass
class _Drawing:
    """One drawing's download log (``drawing_downloads``)."""

    write: Callable[[str], object]
    began: float  # time.monotonic() when the drawing began
    reused: dict[tuple, float] = field(default_factory=dict)  # cache key -> when it was fetched (time.time())
    # A group of downloads (its label) whose source failed and whose last good
    # copy was drawn -> (when the oldest copy used was downloaded, time.time();
    # why the source failed). Batch 20.
    copies: dict[str, tuple[float, str]] = field(default_factory=dict)
    # A source that failed, and why -> what was drawn in place of its answers:
    # one warning each at the drawing's end (batch 19.4).
    fallbacks: dict[tuple[str, str], _Fallback] = field(default_factory=dict)
    # A request (cache key) that failed in this drawing -> its failure: not asked
    # again before the drawing ends (``_cached``).
    failed: dict[tuple, Exception] = field(default_factory=dict)
    # A host that failed as unavailable in this drawing (``_unavailable``) -> its
    # failure: asked nothing more before the drawing ends (batch 19.3, ``host_turn``).
    unavailable: dict[str, Exception] = field(default_factory=dict)
    # Its tasks may run side by side (``in_parallel``): ``copies`` is read and then written.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def copies_used(self) -> list[str]:
        """The sources drawn from their last good copies, each with the copy's date: "FRED Treasury yields (2026-10-21 18:30 UTC)"."""
        return [f"{label} ({_utc_text(when)})" for label, (when, _why) in self.copies.items()]

    def fallback(self, name: str, why: str) -> _Fallback:
        """Source ``name``'s record for failure ``why`` (made at its first use); the caller holds ``lock``."""
        return self.fallbacks.setdefault((name, why), _Fallback())


_log_state = threading.local()  # .groups: list[_Group]; .drawing: _Drawing | None


def _groups() -> list[_Group]:
    """The calling thread's open groups, innermost last."""
    groups = getattr(_log_state, "groups", None)
    if groups is None:
        groups = _log_state.groups = []
    return groups


@contextlib.contextmanager
def downloads_of(label: str) -> Iterator[None]:
    """Name the downloads the calling thread makes meanwhile, for the message log: one line for the group.

    The innermost group names a download. Usable as a decorator too.
    """
    groups = _groups()
    groups.append(_Group(label))
    try:
        yield
    finally:
        groups.pop()


def log_download(fallback: str) -> None:
    """Log a real download about to begin, under its group's name, once per group.

    ``fallback`` names a download made outside any group (a source a later
    change forgot to name), so none goes unlogged.
    """
    groups = _groups()
    if groups:
        group = groups[-1]
        if group.logged:
            return
        group.logged = True
        label = group.label
    else:
        label = fallback
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} -> {label}\n"
    drawing = getattr(_log_state, "drawing", None)
    if drawing is not None:
        drawing.write(line)
    else:
        print(line, end="")


def _note_reused(key: tuple, fetched_at: float, fetched_wall: float) -> None:
    """Count a cached download served again, if it was fetched before the calling thread's drawing began."""
    drawing = getattr(_log_state, "drawing", None)
    if drawing is not None and fetched_at < drawing.began:
        drawing.reused[key] = fetched_wall


@contextlib.contextmanager
def drawing_downloads() -> Iterator[_Drawing]:
    """Log the downloads of one drawing (see above), and end with how many earlier ones it reused.

    The window's worker, a web visitor's drawing and the command line's
    run each wrap their whole drawing in this, the trial pass included;
    the bake's run too (tools/bake_archives.py, tools/rebake.py), so that a
    host that fails as unavailable is asked nothing more in it (batch 19.3,
    ``host_turn``).
    It also ends with one warning for each source that failed (Terry,
    2026-10-22, decision 53: "one warning per source per drawing, the cause
    once, its series grouped by how far their bake reaches"): what was
    drawn from its last good copies (batch 20) and what from its bake alone
    (19.2), once however many times the drawing asked for it. Written at
    the end, the trial pass's silence cannot swallow it. Before, each copy
    and each series had a line of its own, each repeating the cause: 22 for
    the four nations' rates with every source failing. The drawing is
    yielded, so the window and the page can name the copies too
    (``_Drawing.copies_used``).
    """
    drawing = _Drawing(write=current_writer(), began=time.monotonic())
    previous = getattr(_log_state, "drawing", None)
    _log_state.drawing = drawing
    try:
        yield drawing
    finally:
        _log_state.drawing = previous
        for (name, why), fallback in drawing.fallbacks.items():
            drawing.write(fallback.warning(name, why))
        if drawing.reused:
            oldest = datetime.fromtimestamp(min(drawing.reused.values()), timezone.utc)
            # Always with its date, as the download lines are (Terry, 2026-10-24,
            # batch 24.3): with the time alone on the day it was, a saved log
            # read wrong where the date changed partway down, since the date was
            # judged against today, not against the lines above it.
            count = len(drawing.reused)
            drawing.write(
                f"Reused {count} earlier download{'' if count == 1 else 's'}, the oldest from {oldest:%Y-%m-%d %H:%M:%S} UTC\n"
            )


def in_parallel(tasks: Sequence[Callable[[], T]]) -> list[T | Exception]:
    """Run ``tasks`` at the same time, a thread each, in the calling thread's drawing; return each one's result or exception, in order.

    For work that mostly waits on downloads (batch 19.1: the trial pass of
    ``plotting.resolve_start`` prepares the nations side by side). Each host
    still gets one request at a time (``host_turn``). Each task belongs to
    the calling thread's drawing (``drawing_downloads``): its real downloads
    are logged as they happen, each line with its time, and its copies and
    reused downloads are counted there. What a task prints is held, and
    written where the calling thread's output goes once every task has
    ended, task by task in the order given, so the log reads as if they had
    run one after another. A task's exception is returned, not raised: the
    caller decides what it means.
    """
    drawing = getattr(_log_state, "drawing", None)
    printed: list[list[str]] = [[] for _ in tasks]
    outcomes: list[T | Exception | None] = [None] * len(tasks)

    def run(index: int) -> None:
        _log_state.drawing = drawing
        try:
            with this_thread_output_to(printed[index].append):
                outcomes[index] = tasks[index]()
        except Exception as exc:
            outcomes[index] = exc
        finally:
            _log_state.drawing = None

    threads = [threading.Thread(target=run, args=(index,), name=f"ratesplot task {index}") for index in range(len(tasks))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for text in printed:
        print("".join(text), end="")
    return outcomes  # type: ignore[return-value]  (every task has ended: no None is left)


def enable_download_cache(max_age_seconds: float | None = None) -> None:
    """Keep every download for the rest of the session, or for ``max_age_seconds`` each (see above)."""
    global _download_cache, _download_cache_max_age
    with _download_cache_lock:
        if _download_cache is None:
            _download_cache = {}
        _download_cache_max_age = max_age_seconds


def download_cache_on() -> bool:
    """Whether downloads are being kept (``enable_download_cache``): the window, the web page, a command line without -s."""
    return _download_cache is not None


def forget_downloads_older_than(seconds: float) -> int:
    """Forget the cached downloads fetched more than ``seconds`` ago; return how many (the window's Refresh)."""
    with _download_cache_lock:
        if _download_cache is None:
            return 0
        now = time.monotonic()
        old = [key for key, (fetched_at, _wall, _result) in _download_cache.items() if now - fetched_at > seconds]
        for key in old:
            del _download_cache[key]
        return len(old)


def _cached(key: tuple, download: Callable[[], T]) -> T:
    """Return the cached result for ``key``, downloading it first if needed (or if caching is off).

    A result older than the cache's age limit is downloaded again. Two threads
    asking for the same missing key at once both download it; the later one's
    result is kept. That costs a duplicate download, never a wrong result.
    A result served again is counted for the message log (``_note_reused``);
    ``download`` logs a real one itself (``log_download``), so the harnesses'
    stand-ins for this function log what they really download, and nothing else.
    With the last good copies on (batch 20, above), each real download that
    succeeds is kept on disk, and one that fails returns its kept copy, if
    there is one, and is named in the drawing's log; a copy is not put in
    the memory cache, so the next drawing asks the source again.

    A request that failed is not made again in the same drawing (Terry,
    2026-10-21: the program must not become a nuisance to the servers it
    asks): its failure is raised again, or its copy returned, at once. The
    trial pass of ``plotting.resolve_start`` and the real pass after it are
    one drawing, so a source down was asked twice in a drawing before, each
    time with its retries. Nor is a request to a host that has failed as
    unavailable in the drawing (batch 19.3, ``host_turn``): its failure is
    raised at once, before the download is logged, and the request's copy
    returned if it has one, as if the request itself had failed.
    """
    with _download_cache_lock:
        if _download_cache is not None and key in _download_cache:
            fetched_at, fetched_wall, result = _download_cache[key]
            if _download_cache_max_age is None or time.monotonic() - fetched_at <= _download_cache_max_age:
                _note_reused(key, fetched_at, fetched_wall)
                return result  # type: ignore[return-value]
    drawing = getattr(_log_state, "drawing", None)
    earlier = drawing.failed.get(key) if drawing is not None else None
    if earlier is None and drawing is not None:
        earlier = drawing.unavailable.get(_host_of(key))
    try:
        if earlier is not None:
            # With this call's traceback only: the object is the one raised before, whose
            # traceback (the first pass's, perhaps another thread's) each raise would extend.
            raise earlier.with_traceback(None)
        result = download()
    except Exception as failure:
        if drawing is not None:
            drawing.failed[key] = failure
        kept = _last_good_copy(key) if _copies_folder is not None else None
        if kept is None:
            raise
        fetched_wall, copy = kept
        _copy_used(key, fetched_wall, failure)
        return copy  # type: ignore[return-value]
    if _copies_folder is not None and result is not None:  # None: a 404 asked for with missing_ok
        _keep_copy(key, result)
    with _download_cache_lock:
        if _download_cache is not None:
            _download_cache[key] = (time.monotonic(), time.time(), result)
    return result


def _host_of(key: tuple) -> str:
    """The host a download's cache key asks (as ``host_turn`` names it): FRED's for ``("fred", ...)``, else its address's."""
    return urlsplit(FRED_CSV_URL if key[0] == "fred" else key[1]).netloc


class BotCheck(RuntimeError):
    """A source answered with a bot check (a "challenge" page) instead of data. Never retried.

    The Bundesbank's API sent one to every request from Buddug, which goes
    out through a VPN (2026-10-08 and 2026-10-13): a 303 to
    ``/.enodia/challenge?redirect=...``, then a page of its own or a 400.
    Asking again does not get past it, and the fix is on the machine's
    side (the VPN's split tunnelling), never in the request's headers.
    """

    def __init__(self, host: str) -> None:
        super().__init__(f"{host} sent a bot check instead of data; a VPN can cause this")
        self.host = host


# Where a bot check sends a request (the Bundesbank's, measured 2026-10-08).
_BOT_CHECK_PATHS = ("/.enodia/challenge",)


class SourcePage(RuntimeError):
    """A source answered a request for data with a web page (its outage or maintenance page). Never retried.

    Measured 2026-10-21, for hours: FRED answered every CSV request with its
    "Site Maintenance | St. Louis Fed" page, and Statistics Canada every
    table download (and its WDS service) with its "We're sorry! The website
    is currently unavailable" page, all with status 200. Read as data they
    gave a pandas ParserError and "File is not a zip file", each FRED series
    was asked for three times, and the web page's drawing failed with a
    traceback. The page's own title says what happened, so it is named.
    """

    def __init__(self, host: str, title: str) -> None:
        super().__init__(f"{host} sent a web page instead of data (“{title}”); the site may be down for maintenance")
        self.host = host
        self.title = title


# The start of a web page: an HTML document, after any blank lines and
# comments (Statistics Canada's outage page opens with "<!--Last modified
# ... -->"). No source the program reads sends HTML as its data: CSV, JSON,
# XML ("<?xml") and ZIP never begin so.
_WEB_PAGE_START = re.compile(rb"\A\s*(?:<!--.*?-->\s*)*<(?:!doctype\s+html|html)[\s>]", re.IGNORECASE | re.DOTALL)
_WEB_PAGE_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def raise_if_web_page(url: str, body: bytes) -> None:
    """Raise ``SourcePage`` if ``body``, the answer to a request for data at ``url``, is a web page, naming its title."""
    if not _WEB_PAGE_START.match(body[:8192]):
        return
    found = _WEB_PAGE_TITLE.search(body[:65536])
    # FRED's title ends in a stray "<" ("Site Maintenance | St. Louis Fed<").
    title = " ".join(html.unescape(found.group(1).decode("utf-8", errors="replace")).split()).strip(" <") if found else ""
    raise SourcePage(urlsplit(url).netloc, title or "untitled")


# ---------------------------------------------------------------------------
# One request at a time to each host (batch 19.1)
# ---------------------------------------------------------------------------
# The nations' sources may be fetched side by side, but each host still gets
# one request at a time from the program, as when everything was fetched in
# turn: decision 42, "each host's own requests still in turn", so that the
# sources see one client asking, not several at once (Terry, 2026-10-21: the
# program must not become a nuisance to them). A host is the address's
# network location; a redirect to another host is not held apart.
#
# A host that fails as unavailable (a timeout, a refused connection, an
# outage page, a bot check: ``_unavailable``) is asked nothing more in that
# drawing (batch 19.3, Terry's decision 52, 2026-10-22): each of its later
# requests fails at once with the same failure, and is drawn from its last
# good copy or its bake, as if it had been asked. A failure of one request
# (not found, an answer that cannot be read) does not stop the others. The
# next drawing asks again. Before it, a drawing remembered a failed request,
# not a failed host, so each series of a host that was down was still asked:
# with FRED hanging, a U.S. chart with --policy made 42 requests, each ended
# by the 90 s timeout (about an hour; measured 2026-10-22 with a 5 s timeout).
_host_locks: dict[str, threading.Lock] = {}
_host_locks_lock = threading.Lock()


@contextlib.contextmanager
def host_turn(url: str) -> Iterator[None]:
    """Hold ``url``'s host for one request: another thread's request to the same host waits until it ends.

    In a drawing (``drawing_downloads``), a host that has failed as
    unavailable raises its failure again at once, before the request is
    made; a failure that makes it so is recorded here, before the host is
    let go, so the request of another thread waiting its turn is not made
    either. The request's checks of the answer (an outage page, a bot check)
    belong inside the turn for that reason.
    """
    host = urlsplit(url).netloc
    with _host_locks_lock:
        lock = _host_locks.setdefault(host, threading.Lock())
    drawing = getattr(_log_state, "drawing", None)
    with lock:
        down = drawing.unavailable.get(host) if drawing is not None else None
        if down is not None:
            # With this call's traceback only, as ``_cached`` raises a request's earlier failure.
            raise down.with_traceback(None)
        try:
            yield
        except Exception as failure:
            if not hasattr(failure, _HOST_ATTRIBUTE):
                # Which source failed, for a chart not drawn (``source_failure``); urllib's errors do not say.
                with contextlib.suppress(AttributeError):
                    setattr(failure, _HOST_ATTRIBUTE, host)
            if drawing is not None and _unavailable(failure):
                drawing.unavailable.setdefault(host, failure)
            raise


# The attribute ``host_turn`` gives a failure: the host it was asking.
_HOST_ATTRIBUTE = "ratesplot_host"


# ---------------------------------------------------------------------------
# A request asked once more (batch 19.3)
# ---------------------------------------------------------------------------
# Terry, 2026-10-22 (decision 52): "Retries: yes, one retry after 2 s, only
# for a dropped or reset connection or a 5xx; none for a 404 or other 4xx, an
# outage page, a bot check or a timeout". How each library reports each kind
# was measured against a server on this machine (2026-10-22): a connection
# reset, or closed without an answer, is requests' ConnectionError holding
# urllib3's ProtocolError (urllib's ConnectionResetError, RemoteDisconnected);
# an answer broken off, ChunkedEncodingError (urllib's IncompleteRead); a
# server that never answers, ReadTimeout (urllib's TimeoutError); a refused
# connection, ConnectionError holding a MaxRetryError whose reason is the
# connection never made (on Windows a refusal by this machine itself came as a
# ConnectTimeout, after its own retries); a 503, HTTPError.


def _dropped_part_way(failure: BaseException) -> bool:
    """Whether ``failure`` is a connection dropped or reset after it was made: an answer broken off, or none sent before it closed.

    Not a connection refused or never made, and not a timeout.
    """
    if isinstance(failure, requests.Timeout):
        return False
    if isinstance(failure, requests.exceptions.ChunkedEncodingError):
        return True
    if isinstance(failure, requests.ConnectionError):
        cause = failure.args[0] if failure.args else None
        if isinstance(cause, MaxRetryError):
            cause = cause.reason
        return isinstance(cause, ProtocolError)
    # urllib (FRED's requests): its own errors, or a URLError holding one.
    if isinstance(failure, urllib.error.URLError) and not isinstance(failure, urllib.error.HTTPError):
        failure = failure.reason  # type: ignore[assignment]  (an exception, or a string, which is no drop)
    return isinstance(failure, (http_client.IncompleteRead, ConnectionResetError, ConnectionAbortedError))


def _server_error(failure: BaseException) -> bool:
    """Whether ``failure`` is the server's own error status (5xx): requests' ``raise_for_status`` or urllib's."""
    if isinstance(failure, requests.HTTPError):
        return failure.response is not None and failure.response.status_code >= 500
    return isinstance(failure, urllib.error.HTTPError) and failure.code >= 500


def _unavailable(failure: BaseException) -> bool:
    """Whether ``failure`` says its host is not answering now: a timeout, a connection refused or never made, an outage page, a bot check.

    Terry, 2026-10-22 (decision 52): "once a host fails as unavailable
    (timeout after retries, refused connection, outage page, bot check), ask
    it nothing more in that drawing". A failure of one request (a 404 or
    other error status, a 5xx after its retry, a connection dropped twice,
    an answer that cannot be read) is not the host's.
    """
    if isinstance(failure, (BotCheck, SourcePage, requests.Timeout)):
        return True
    if _dropped_part_way(failure) or _server_error(failure):
        return False
    if isinstance(failure, requests.ConnectionError):  # refused, the name not found: the connection never made
        return True
    if isinstance(failure, urllib.error.HTTPError):  # urllib's error status (FRED's)
        return False
    # urllib: a URLError holding why the connection was never made, or a timeout while reading.
    return isinstance(failure, (urllib.error.URLError, TimeoutError))


def _with_retries(describe: str, attempt_once: Callable[[], T]) -> T:
    """Call ``attempt_once``, and once more after ``RETRY_WAIT_SECONDS`` if it failed part way or with a server error (see above).

    Every other failure is raised at once, and the second attempt's failure
    as it is, so callers see the real exception: a 404 or other 4xx, an
    outage page or a bot check, a refused connection, a timeout: a source
    that does not answer is not asked again seconds later, and in a drawing
    is asked nothing more (``host_turn``).
    """
    try:
        return attempt_once()
    except Exception as failure:
        if not (_dropped_part_way(failure) or _server_error(failure)):
            raise
        print(f"  {describe} failed ({failure}); asked once more in {RETRY_WAIT_SECONDS} s …")
    time.sleep(RETRY_WAIT_SECONDS)
    return attempt_once()


# ---------------------------------------------------------------------------
# A chart not drawn (batch 19.4)
# ---------------------------------------------------------------------------
# Terry, 2026-10-22, on follow-up 27 (decision 53), after the window wrote a
# whole traceback for the U.S. chart FRED's outage had left out, which read
# as a crash: "One line, but can it be bolded or in red, or something to make
# it more visible in a log of messages usually not inspected closely?" So a
# chart not drawn gets one line, "NOT DRAWN: the United States chart: FRED:
# ...", which the window shows red and bold; on the page, whose log is plain
# text, and in a saved log file, its first words stand out. The traceback is
# kept for an unexpected error, which it is needed to fix, before the line.
NOT_DRAWN = "NOT DRAWN"


def source_failure(failure: BaseException) -> tuple[str, str] | None:
    """``(the source's name, why)`` if ``failure``, or one it was raised from or while handling, is a source not answering (``_unavailable``); else None."""
    seen: set[int] = set()
    current: BaseException | None = failure
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _unavailable(current):
            host = getattr(current, _HOST_ATTRIBUTE, None) or getattr(current, "host", None)
            return (source_name(host) if host else "a source", _why(current))
        current = current.__cause__ or current.__context__
    return None


def not_drawn(failure: BaseException) -> tuple[str, str | None]:
    """Why a chart was not drawn, and the traceback to log before its line (``not_drawn_line``): none for a source not answering."""
    found = source_failure(failure)
    if found is not None:
        return f"{found[0]}: {found[1]}", None
    return f"{type(failure).__name__}: {failure}", "".join(traceback.format_exception(failure))


def not_drawn_line(what: str, why: str) -> str:
    """``NOT DRAWN: the United States chart: FRED: timed out`` (``what``, "the United States chart" or "the charts"), with its newline."""
    return f"{NOT_DRAWN}: {what}: {why}\n"


def _session_get(
    session: requests.Session,
    tag: str,
    url: str,
    params: dict | None,
    *,
    timeout: int,
    cached: bool = True,
    missing_ok: bool = False,
) -> requests.Response | None:
    """GET ``url`` through ``session``, asked once more for a dropped connection or a server error (``_with_retries``); cached under ``(tag, url, params)`` unless ``cached`` is False.

    With ``missing_ok`` a 404 returns None at once: the thing does not exist
    (yet), and asking again will not change that.
    """

    def attempt() -> requests.Response | None:
        # The answer checked in the host's turn, so an outage page or a bot check marks it unavailable (host_turn).
        with host_turn(url):
            response = session.get(url, params=params, timeout=timeout)
            # Before the status: the check's own page may be a 400, which would be read as the request's own failure.
            if any(path in response.url for path in _BOT_CHECK_PATHS):
                raise BotCheck(urlsplit(url).netloc)
            if missing_ok and response.status_code == 404:
                return None
            response.raise_for_status()
            # Not after a redirect: that is the source's own answer, which its
            # caller reads (the Bank of England's error page, uk_data.iadb_series).
            if not response.history:
                raise_if_web_page(url, response.content)
        return response

    def download() -> requests.Response | None:
        log_download(url)
        return _with_retries(f"{tag.capitalize()} request", attempt)

    if not cached:
        return download()
    # A Response keeps its body, so a cached one can be read again by later callers.
    return _cached((tag, url, tuple(sorted((params or {}).items()))), download)


def canadian_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bank of Canada or Statistics Canada URL, asked once more for a dropped connection or a server error (``_with_retries``).

    Args:
        url: Complete endpoint URL.
        params: Optional query parameters, such as ``start_date``.
        timeout: Per-request timeout in seconds.
    """
    response = _session_get(CANADIAN_SESSION, "canadian", url, params, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def canadian_post(url: str, payload: object, *, timeout: int) -> requests.Response:
    """POST ``payload`` as JSON to a Statistics Canada service (its WDS), once; cached and kept as the GETs are.

    One attempt, not retried: it is the fallback for a table that has just
    failed. Through the cache, a drawing does not ask it twice (the trial or
    side-by-side pass, then the chart), and its last good copy is kept.
    """

    def download() -> requests.Response:
        log_download(url)
        with host_turn(url):
            response = CANADIAN_SESSION.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            # Its outage page arrives with status 200 too (2026-10-21; SourcePage).
            raise_if_web_page(url, response.content)
        return response

    return _cached(("canadian-post", url, json.dumps(payload, sort_keys=True)), download)


def uk_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bank of England or Office for National Statistics URL (``uk_data``), asked once more and cached as the others are."""
    response = _session_get(UK_SESSION, "uk", url, params, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def de_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bundesbank, ECB or Eurostat URL (``de_data``), asked once more and cached as the others are.

    The Bundesbank's whole-series download once broke off part way from the
    laptop and answered on the next try (2026-10-06): the retry covers that.
    """
    response = _session_get(DE_SESSION, "de", url, params, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def latest_get(
    url: str,
    params: dict | None = None,
    *,
    cached: bool = True,
    missing_ok: bool = False,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response | None:
    """GET a source of the latest values (--cur, see ``ratesplot.latest``), asked once more as the others are.

    ``cached=False`` is for intraday quotes: every drawing should show the
    quotes of the moment, not those of the window's first drawing.
    ``missing_ok`` returns None for a 404 (a year the source does not have).
    """
    return _session_get(LATEST_SESSION, "latest", url, params, timeout=timeout, cached=cached, missing_ok=missing_ok)


def get_if_published(url: str, *, timeout: int = HTTP_TIMEOUT_SECONDS) -> requests.Response | None:
    """GET a file that may not exist, such as a Census year not yet published; None on 404.

    Asked once more for a dropped connection or a server error, as in
    ``canadian_get``; a missing file is not (it will not appear on retry),
    and any other HTTP error is raised. Used by the bake, so not cached.
    """

    def attempt() -> requests.Response | None:
        with host_turn(url):
            response = CANADIAN_SESSION.get(url, timeout=timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response

    return _with_retries("Request", attempt)


def fetch_fred_csv(series_id: str, *, since: pd.Timestamp | None = None) -> pd.DataFrame:
    """Download one FRED series as a two-column ``DATE`` / ``series_id`` frame: every row, or those from ``since`` on.

    FRED is intentionally read as ``pandas.read_csv`` reads a URL (urllib's
    ``urlopen``) rather than through a ``requests.Session``. Routing FRED
    through the shared session caused connection resets and long retry
    delays in practice, so do not "tidy" this into the Canadian download
    path. The answer is read first and then parsed, so that a web page in
    its place (FRED's maintenance page, 2026-10-21) is named and not
    retried (``SourcePage``); until then the URL itself was handed to
    ``pandas.read_csv``, which made the same request without a time limit.
    Asked once more for a dropped connection or a server error, as every
    request is (``_with_retries``); an answer that cannot be read as a
    series is not (it was, until batch 19.3).

    Args:
        series_id: FRED series identifier, such as ``"DGS10"`` or ``"GDP"``.
        since: The first date asked for (FRED's ``cosd``): FRED answers from
            the period holding it (a quarterly series from that quarter's
            first day), every row after. The recent part of a baked series
            (batch 19.2, ``us_data.fred_series``); None, the whole series
            (the bake, and the checks against FRED itself).
    """
    url = f"{FRED_CSV_URL}?id={series_id}" + (f"&cosd={since:%Y-%m-%d}" if since is not None else "")

    def attempt() -> pd.DataFrame:
        # The answer checked in FRED's turn, so its outage page marks it unavailable (host_turn).
        with host_turn(url):
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
                body = response.read()
                # As pandas does for a URL: a gzip-encoded answer is unpacked.
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            raise_if_web_page(url, body)
        data = pd.read_csv(io.BytesIO(body))
        if len(data.columns) < 2:
            raise ValueError(f"FRED series {series_id} returned no value column")
        # FRED's header is ``observation_date,<SERIES>``; normalise positionally
        # so a header rename upstream cannot break the pipeline.
        data = data.iloc[:, :2].set_axis([DATE_COLUMN, series_id], axis=1)
        data[DATE_COLUMN] = pd.to_datetime(data[DATE_COLUMN])
        data[series_id] = pd.to_numeric(data[series_id], errors="coerce")
        return data

    def download() -> pd.DataFrame:
        log_download(f"FRED {series_id}")
        return _with_retries(f"FRED {series_id} request", attempt)

    # Callers modify the frame they get, so each receives its own copy of the cached one.
    key = ("fred", series_id) if since is None else ("fred", series_id, f"{since:%Y-%m-%d}")
    return _cached(key, download).copy()


def parse_boc_csv(response_text: str, key: str = "date") -> pd.DataFrame:
    """Parse a Bank of Canada Valet CSV, skipping the metadata block above the header.

    Valet responses begin with several ``"key","value"`` metadata lines; the
    observation table starts at the first line whose first field is ``key``:
    ``date`` for time series, another name for a table keyed by something
    else (``dom_dbt_id``, the "as of" date of the debt outstanding). The
    result is indexed by that field, read as dates.
    """
    lines = response_text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith((f'"{key}"', key))
        ),
        None,
    )
    if header_index is None:
        raise ValueError(f"Bank of Canada response contains no {key!r} header line")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_index:])))
    df.columns = [column.strip().strip('"') for column in df.columns]
    df[key] = pd.to_datetime(df[key])
    return df.set_index(key).sort_index()
