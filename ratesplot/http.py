"""HTTP and source-format helpers for FRED, Bank of Canada, Statistics Canada, the UK's and Germany's sources and the latest-value sources; the message log's download lines."""

from __future__ import annotations

import contextlib
import io
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterator, TypeVar
from urllib.parse import urlsplit

import pandas as pd
import requests

from .config import (
    CANADIAN_SESSION,
    DE_SESSION,
    DATE_COLUMN,
    DEFAULT_FRED_RETRIES,
    DEFAULT_GET_RETRIES,
    FRED_CSV_URL,
    HTTP_TIMEOUT_SECONDS,
    LATEST_SESSION,
    RETRY_BACKOFF_BASE_SECONDS,
    UK_SESSION,
)
from .console import current_writer

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
# Keyed by URL (and query parameters). Only the two download helpers below use
# it; the StatCan WDS fallback is rare and stays uncached.

_download_cache: dict[tuple, tuple[float, float, object]] | None = None
_download_cache_max_age: float | None = None  # seconds; None keeps each download for the session
_download_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# The message log's download lines
# ---------------------------------------------------------------------------
# Terry, 2026-10-12: a time stamp in UTC only for a real download from a
# source. So each real download is logged with the time it began,
# "2026-10-13 14:32:05 -> Bank of Canada benchmark yields", once for each
# group of downloads named by ``downloads_of``, however many requests the
# group makes. A download served again from the session's cache is not
# logged by itself; a drawing ends with one line counting them ("Reused 14
# earlier downloads, the oldest from 16:32:05 UTC"), since how old the data
# are still matters. The built-in history (the baked and transcribed data)
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
class _Drawing:
    """One drawing's download log (``drawing_downloads``)."""

    write: Callable[[str], object]
    began: float  # time.monotonic() when the drawing began
    reused: dict[tuple, float] = field(default_factory=dict)  # cache key -> when it was fetched (time.time())


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
def drawing_downloads() -> Iterator[None]:
    """Log the downloads of one drawing (see above), and end with how many earlier ones it reused.

    The window's worker, a web visitor's drawing and the command line's
    run each wrap their whole drawing in this, the trial pass included.
    """
    drawing = _Drawing(write=current_writer(), began=time.monotonic())
    previous = getattr(_log_state, "drawing", None)
    _log_state.drawing = drawing
    try:
        yield
    finally:
        _log_state.drawing = previous
        if drawing.reused:
            oldest = datetime.fromtimestamp(min(drawing.reused.values()), timezone.utc)
            # The time alone on the day it is; a window left open overnight gets the date too.
            when = f"{oldest:%H:%M:%S}" if oldest.date() == datetime.now(timezone.utc).date() else f"{oldest:%Y-%m-%d %H:%M:%S}"
            count = len(drawing.reused)
            drawing.write(f"Reused {count} earlier download{'' if count == 1 else 's'}, the oldest from {when} UTC\n")


def enable_download_cache(max_age_seconds: float | None = None) -> None:
    """Keep every download for the rest of the session, or for ``max_age_seconds`` each (see above)."""
    global _download_cache, _download_cache_max_age
    with _download_cache_lock:
        if _download_cache is None:
            _download_cache = {}
        _download_cache_max_age = max_age_seconds


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
    """
    with _download_cache_lock:
        if _download_cache is not None and key in _download_cache:
            fetched_at, fetched_wall, result = _download_cache[key]
            if _download_cache_max_age is None or time.monotonic() - fetched_at <= _download_cache_max_age:
                _note_reused(key, fetched_at, fetched_wall)
                return result  # type: ignore[return-value]
    result = download()
    with _download_cache_lock:
        if _download_cache is not None:
            _download_cache[key] = (time.monotonic(), time.time(), result)
    return result


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


def _with_retries(
    describe: str,
    attempt_once: Callable[[], T],
    *,
    max_retries: int,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call ``attempt_once`` up to ``max_retries`` times with exponential backoff.

    The wait after attempt *n* is ``RETRY_BACKOFF_BASE_SECONDS ** n`` seconds.
    The last failure is re-raised unchanged so callers see the real exception.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return attempt_once()
        except retry_on as exc:
            if attempt == max_retries:
                raise
            wait_seconds = RETRY_BACKOFF_BASE_SECONDS**attempt
            print(
                f"  {describe} attempt {attempt}/{max_retries} failed ({exc}). "
                f"Retrying in {wait_seconds}s …"
            )
            time.sleep(wait_seconds)
    raise AssertionError("unreachable: max_retries must be >= 1")


def _session_get(
    session: requests.Session,
    tag: str,
    url: str,
    params: dict | None,
    *,
    max_retries: int,
    timeout: int,
    cached: bool = True,
    missing_ok: bool = False,
) -> requests.Response | None:
    """GET ``url`` through ``session`` with retries; cached under ``(tag, url, params)`` unless ``cached`` is False.

    With ``missing_ok`` a 404 returns None at once: the thing does not exist
    (yet), and asking again will not change that.
    """

    def attempt() -> requests.Response | None:
        response = session.get(url, params=params, timeout=timeout)
        # Before the status: the check's own page may be a 400, which would be retried.
        if any(path in response.url for path in _BOT_CHECK_PATHS):
            raise BotCheck(urlsplit(url).netloc)
        if missing_ok and response.status_code == 404:
            return None
        response.raise_for_status()
        return response

    def download() -> requests.Response | None:
        log_download(url)
        return _with_retries(f"{tag.capitalize()} request", attempt, max_retries=max_retries, retry_on=(requests.RequestException,))

    if not cached:
        return download()
    # A Response keeps its body, so a cached one can be read again by later callers.
    return _cached((tag, url, tuple(sorted((params or {}).items()))), download)


def canadian_get(
    url: str,
    params: dict | None = None,
    *,
    max_retries: int = DEFAULT_GET_RETRIES,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bank of Canada or Statistics Canada URL with retries.

    Args:
        url: Complete endpoint URL.
        params: Optional query parameters, such as ``start_date``.
        max_retries: Total attempts before the last ``RequestException`` is raised.
        timeout: Per-request timeout in seconds.
    """
    response = _session_get(CANADIAN_SESSION, "canadian", url, params, max_retries=max_retries, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def uk_get(
    url: str,
    params: dict | None = None,
    *,
    max_retries: int = DEFAULT_GET_RETRIES,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bank of England or Office for National Statistics URL with retries (``uk_data``), cached as the others are."""
    response = _session_get(UK_SESSION, "uk", url, params, max_retries=max_retries, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def de_get(
    url: str,
    params: dict | None = None,
    *,
    max_retries: int = DEFAULT_GET_RETRIES,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response:
    """GET a Bundesbank, ECB or Eurostat URL with retries (``de_data``), cached as the others are.

    The Bundesbank's whole-series download once broke off part way from the
    laptop and answered on the next try (2026-10-06): the retries cover that.
    """
    response = _session_get(DE_SESSION, "de", url, params, max_retries=max_retries, timeout=timeout)
    assert response is not None  # only missing_ok returns None
    return response


def latest_get(
    url: str,
    params: dict | None = None,
    *,
    cached: bool = True,
    missing_ok: bool = False,
    max_retries: int = DEFAULT_GET_RETRIES,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> requests.Response | None:
    """GET a source of the latest values (--cur, see ``ratesplot.latest``) with retries.

    ``cached=False`` is for intraday quotes: every drawing should show the
    quotes of the moment, not those of the window's first drawing.
    ``missing_ok`` returns None for a 404 (a year the source does not have).
    """
    return _session_get(
        LATEST_SESSION, "latest", url, params, max_retries=max_retries, timeout=timeout, cached=cached, missing_ok=missing_ok
    )


def get_if_published(
    url: str, *, max_retries: int = DEFAULT_GET_RETRIES, timeout: int = HTTP_TIMEOUT_SECONDS
) -> requests.Response | None:
    """GET a file that may not exist, such as a Census year not yet published; None on 404.

    Connection failures and timeouts are retried as in ``canadian_get``; a
    missing file is not (it will not appear on retry), and any other HTTP
    error is raised. Used by the bake, so not cached.
    """

    def attempt() -> requests.Response | None:
        response = CANADIAN_SESSION.get(url, timeout=timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response

    return _with_retries(
        "Request", attempt, max_retries=max_retries, retry_on=(requests.ConnectionError, requests.Timeout)
    )


def fetch_fred_csv(series_id: str, *, max_retries: int = DEFAULT_FRED_RETRIES) -> pd.DataFrame:
    """Download one FRED series as a two-column ``DATE`` / ``series_id`` frame.

    FRED is intentionally read by handing the URL straight to ``pandas.read_csv``
    rather than through a ``requests.Session``. Routing FRED through the shared
    session caused connection resets and long retry delays in practice, so do
    not "tidy" this into the Canadian download path.

    Args:
        series_id: FRED series identifier, such as ``"DGS10"`` or ``"GDP"``.
        max_retries: Complete read attempts before the last exception is raised.
    """
    url = f"{FRED_CSV_URL}?id={series_id}"

    def attempt() -> pd.DataFrame:
        data = pd.read_csv(url)
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
        return _with_retries(series_id, attempt, max_retries=max_retries)

    # Callers modify the frame they get, so each receives its own copy of the cached one.
    return _cached(("fred", series_id), download).copy()


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
