#!/usr/bin/env python3
"""Batch 20: a source that fails is drawn from its last good copy, and the drawing says so.

Made-up data in each source's own format (``tools/synthetic_sources.py``) answers every
request through the program's real download path: requests' ``Session.get`` and urllib's
``urlopen`` are replaced, and the program's own cache (``http._cached``) is left as it is, so
the copies are written and read as on a user's machine, into a temporary folder. The same
charts are drawn three times:

1. every source answers: the charts drawn, and a copy kept of every download;
2. every source fails as sources were seen to fail (FRED and Statistics Canada with their
   outage pages of 2026-10-21, the Bundesbank with its bot check, the rest refusing the
   connection): each chart must come out byte for byte as in pass 1, and the drawing must
   name each source it drew from a copy; the web page's drawing (``web._draw``) too;
3. the same failures without the copies: the program as it was before batch 20, which
   cannot draw them all (the difference the copies make).

Usage (from the project root)::

    python tools/check_last_good.py

The exit code is 1 if any check fails. No network is used.
"""

from __future__ import annotations

import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import requests  # noqa: E402

import synthetic_sources  # noqa: E402
from ratesplot import cli, http  # noqa: E402
from ratesplot import web  # noqa: E402  (imported first: it turns on the page's caches, undone below)
from ratesplot.console import this_thread_output_to  # noqa: E402
from ratesplot.frontend import png_bytes  # noqa: E402
from ratesplot.plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402

# The charts: the defaults (automatic start); every nation with the rates on the yield axis;
# levels of government per capita. The end pinned before the synthetic series end.
CASES = {
    "default": ["--e:2026-09-01"],
    "rates": ["--na:ca,us,gb,de", "--e:2026-09-01", "-s:2000", "--policy", "--mo", "--sp"],
    "levels": ["-c", "-u", "--e:2026-09-01", "-s:1990", "--debt:fp", "-p"],
}

# The pages measured on 2026-10-21 (their heads; the program reads only the start and title).
FRED_PAGE = (
    b"<!doctype html>\n<html lang=\"en\">\n<head>\n    <title>Site Maintenance | St. Louis Fed<</title>\n"
    b"</head><body>Site maintenance</body></html>"
)
STATCAN_PAGE = (
    b"<!--Last modified Dec 16, 2021-->\r\n\r\n\r\n<!DOCTYPE html>\r\n<html>\r\n<head>\r\n"
    b"    <title>Statistics Canada - We're sorry! The website is currently unavailable</title>\r\n"
    b"</head><body></body></html>"
)

failures = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global failures
    failures += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail != "" else ""))


class _Answer:
    """What ``urllib.request.urlopen`` returns, for ``http.fetch_fred_csv``."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.headers: dict[str, str] = {}

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _page(url: str, body: bytes, *, at: str | None = None) -> requests.Response:
    response = requests.Response()
    response._content = body
    response.status_code = 200
    response.encoding = "utf-8"
    response.url = at or url
    return response


def answering_get(_session, url, params=None, **_kwargs) -> requests.Response:
    """Every source answers, from the synthetic data (a source with none refuses, as offline)."""
    try:
        response = synthetic_sources.synth(("get", url, tuple(sorted((params or {}).items()))))
    except KeyError as exc:
        raise requests.ConnectionError(f"no synthetic answer: {exc}") from None
    response.url = url
    return response


def answering_urlopen(url, timeout=None) -> _Answer:
    return _Answer(synthetic_sources.fred(url.split("?id=", 1)[1]).to_csv(index=False).encode())


def failing_get(_session, url, params=None, **_kwargs) -> requests.Response:
    """Every source fails, each as such sources were seen to."""
    host = urlsplit(url).netloc
    if host == "www150.statcan.gc.ca":
        return _page(url, STATCAN_PAGE)
    if host == "api.statistiken.bundesbank.de":
        return _page(url, b"<html>challenge</html>", at=f"https://{host}/.enodia/challenge?redirect=x")
    raise requests.ConnectionError(f"{host}: cut off by check_last_good")


def failing_urlopen(url, timeout=None) -> _Answer:
    return _Answer(FRED_PAGE)


def refused_post(*_args, **_kwargs):
    raise requests.ConnectionError("StatCan WDS: cut off by check_last_good")


def draw(tokens: list[str]) -> tuple[dict[str, bytes], dict[str, str], list[str], str]:
    """Draw a case's charts as the window does; return (PNGs, charts not drawn, copies used, log)."""
    config = cli.parse_args(["--no-gui", *tokens])
    lines: list[str] = []
    pngs: dict[str, bytes] = {}
    not_drawn: dict[str, str] = {}
    with this_thread_output_to(lines.append), http.drawing_downloads() as downloads:
        drawn = resolve_start(config)
        for country in COUNTRIES:
            if getattr(drawn, country.show_field):
                try:
                    pngs[country.key] = png_bytes(build_figure(country, drawn))
                except Exception as exc:  # pass 3 expects some
                    not_drawn[country.key] = f"{type(exc).__name__}: {exc}"
    return pngs, not_drawn, downloads.copies_used(), "".join(lines)


def main() -> int:
    # web's import turned on the page's memory cache, which would answer pass 2 from pass 1.
    http._download_cache = None
    http.RETRY_BACKOFF_BASE_SECONDS = 0  # the retries of a refused connection, without the waits
    requests.Session.post = refused_post  # type: ignore[assignment]
    folder = Path(tempfile.mkdtemp(prefix="ratesplot_last_good_"))
    http.enable_last_good_copies(folder)
    print(f"[last good] copies in {folder}")

    print("[last good] pass 1: every source answers")
    requests.Session.get = answering_get  # type: ignore[assignment]
    urllib.request.urlopen = answering_urlopen  # type: ignore[assignment]
    first = {}
    for name, tokens in CASES.items():
        pngs, not_drawn, copies, _log = draw(tokens)
        first[name] = pngs
        check(f"{name}: every chart drawn, no copy used", not not_drawn and not copies, (sorted(pngs), not_drawn, copies))
    kept = sorted(folder.glob("*.pickle"))
    check("a copy kept of every download", len(kept) >= 20, f"{len(kept)} copies")

    print("[last good] pass 2: every source fails; the copies drawn")
    requests.Session.get = failing_get  # type: ignore[assignment]
    urllib.request.urlopen = failing_urlopen  # type: ignore[assignment]
    for name, tokens in CASES.items():
        pngs, not_drawn, copies, log = draw(tokens)
        same = sorted(key for key in pngs if pngs[key] == first[name].get(key))
        check(f"{name}: every chart drawn as in pass 1, byte for byte", not not_drawn and same == sorted(first[name]),
              (same, sorted(first[name]), not_drawn))
        check(f"{name}: the copies named, each with its date", bool(copies) and all(" UTC)" in copy for copy in copies),
              "; ".join(copies))
        warnings = [line for line in log.splitlines() if "drawn from its last good copy" in line]
        check(f"{name}: one warning per source in the log", len(warnings) == len(copies), f"{len(warnings)} warnings")
        if name == "default":
            print("\n".join(f"      {line.strip()}" for line in warnings))
        if name == "rates":
            check("rates: FRED's page named", any("Site Maintenance | St. Louis Fed" in line for line in warnings))
            check("rates: StatCan's page named", any("We're sorry!" in line for line in warnings))
            check("rates: the Bundesbank's bot check named", any("bot check" in line for line in warnings))
    config = cli.parse_args(["--no-gui", *CASES["default"]])
    drawing = web._draw(config, tuple(CASES["default"]))
    check("the web page: drawn as in pass 1, its notice listing the copies",
          drawing.error is None and not drawing.failed and drawing.pngs == first["default"] and bool(drawing.copies),
          (drawing.error, drawing.failed, drawing.copies))

    print("[last good] pass 3: the same failures without the copies (as before batch 20)")
    http._copies_folder = None
    for name, tokens in CASES.items():
        pngs, not_drawn, copies, _log = draw(tokens)
        differs = sorted(key for key in first[name] if pngs.get(key) != first[name][key])
        check(f"{name}: not drawn, or drawn otherwise, without them", bool(differs), f"differ or missing: {differs}")

    print(f"[last good] {'all checks passed' if not failures else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
