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
   cannot draw them all (the difference the copies make). What it draws from the baked
   history alone must stop: no curve on the right axis keeps its last value for more than
   ``joins.MACRO_CARRY_LIMIT`` (Canada's debt, left with its history to 1994, ran on flat
   to the day before 2026-10-21). The Bank of England's series, the Bank of Canada's,
   FRED's, the ECB's, Eurostat's, the ONS's and Statistics Canada's tables, baked (batch
   19.2; a synthetic bake here), are drawn to the bake's last date, each named with that
   date in its source's one warning (19.4: one per source per drawing, the cause once, its
   series grouped by how far their bake reaches; in pass 2 the copies are listed in it the
   same way); Statistics Canada is asked only for its tables' recent parts
   (WDS), never the CMHC mortgage rate, which is drawn from its bake unasked. The
   Bundesbank's too, but its bot check is named once, after its first request, the only
   one it is sent in the drawing (its other series drawn from their bake unasked). The
   UK's chart is drawn once more without the ONS's bake (as before 19.2's ONS stage):
   its national debt, drawn to 2016 without the gross debt, must stop and is named
   without "(pre-1975)".

In passes 2 and 3 every request is counted: within one drawing each failing source is
asked once (Terry, 2026-10-21: the program must not become a nuisance to the servers; the
trial pass of an automatic start and the real pass asked each failing source again
before). Since batch 19.3 a source answering with an outage page or a bot check, or
refusing the connection, is asked nothing more in the drawing after its first request,
which is not retried (only a connection dropped part way or a server error is asked once
more): every series of it is then drawn from its copy or its bake, as if it had been asked.

Usage (from the project root)::

    python tools/check_last_good.py

The exit code is 1 if any check fails. No network is used.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from collections import Counter
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import synthetic_sources  # noqa: E402
from ratesplot import baked, cdn_data, cli, http  # noqa: E402
from ratesplot import web  # noqa: E402  (imported first: it turns on the page's caches, undone below)
from ratesplot.console import this_thread_output_to  # noqa: E402
from ratesplot.frontend import png_bytes  # noqa: E402
from ratesplot.joins import MACRO_CARRY_LIMIT  # noqa: E402
from ratesplot.plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402

# The charts: the defaults (automatic start); every nation with the rates on the yield axis;
# levels of government per capita. The end pinned before the synthetic series end.
CASES = {
    "default": ["--e:2026-09-01"],
    "rates": ["--na:ca,us,gb,de", "--e:2026-09-01", "-s:2000", "--policy", "--mo", "--sp"],
    "levels": ["-c", "-u", "--e:2026-09-01", "-s:1990", "--debt:fp", "-p"],
}

# The FRED series the "rates" case draws (batch 19.2): in pass 3 each from its bake, named. Not
# Canada's GDP (NGDPSAXDCCAQ) since 19.2's Statistics Canada stage: Statistics Canada's GDP is drawn
# from its own bake when it fails, so FRED's copy, the fallback for a table that cannot be had, is not asked.
FRED_DRAWN_IN_RATES = (
    "DGS3MO", "DGS2", "DGS5", "DGS10", "DGS30", "FEDFUNDS", "DFEDTARL", "DFEDTARU",
    "MORTGAGE30US", "GFDEBTN", "SLGSDODNS", "GDP", "A180RC1Q027SBEA",
)
# The ECB series the "rates" case draws (batch 19.2): Germany's policy rate (fixed, then the minimum
# bid), its three mortgage bands and its year-end debt before 2000; not EONIA or €STR (the market rate).
ECB_DRAWN_IN_RATES = (
    "FM.B.U2.EUR.4F.KR.MRR_FR.LEV", "MIR.M.DE.B.A2C.I.R.A.2250.EUR.N",
    "MIR.M.DE.B.A2C.O.R.A.2250.EUR.N", "MIR.M.DE.B.A2C.P.R.A.2250.EUR.N", "GFS.A.N.DE.W0.S13.S1.C.L.LE.GD.T._Z.XDC._T.F.V.N._T",
)
# The series the "rates" case draws whose source has stopped (19.3, declared in ``rates``): FRED's fed funds
# target to 2008 and the ECB's minimum bid rate; each drawn from its bake alone, never asked, never named.
STOPPED_IN_RATES = {"FRED": "DFEDTAR", "ECB": "FM.B.U2.EUR.4F.KR.MRR_MBR.LEV"}
# The Eurostat series the "rates" case draws (batch 19.2): Germany's quarterly debt, its interest (the
# annual figures, then the quarters) and its GDP, each of general government; not the levels or population.
EUROSTAT_DRAWN_IN_RATES = ("gov_10q_ggdebt.S13", "gov_10q_ggnfa.S13", "gov_10dd_edpt1.D41PAY.S13", "namq_10_gdp")
# Statistics Canada's tables the "rates" case draws: interest, GDP, debt (not population, nor the CMHC rate).
STATCAN_DRAWN_IN_RATES = ("10100015", "36100104", "36100467")
# The ONS series the "rates" case draws (batch 19.2): the UK's gross and net debt, its interest and its GDP;
# not the levels or population.
ONS_DRAWN_IN_RATES = ("BKPX", "HF6W", "NMYX", "YBHA")
# The UK's chart of the "rates" case, drawn again in pass 3 without the ONS's bake.
UK_RATES = ["--na:gb", *CASES["rates"][1:]]
# The cases every source of which is baked (batch 19.2): in pass 3 drawn from the bake alone, byte for byte
# as in pass 1 (the synthetic bake reaches past what they draw). "levels" since Statistics Canada's stage:
# Canada's levels and population from its tables, the U.S.' from FRED's series.
DRAWN_FROM_THE_BAKE_ALONE = ("levels",)

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
    # The series' whole synthetic answer, whatever date it is asked from (``&cosd=``, batch 19.2).
    return _Answer(synthetic_sources.fred(url.split("?id=", 1)[1].split("&", 1)[0]).to_csv(index=False).encode())


# Requests made to failing sources, by (how it failed, address, parameters); reset per drawing.
asked: Counter = Counter()


def failing_get(_session, url, params=None, **_kwargs) -> requests.Response:
    """Every source fails, each as such sources were seen to."""
    host = urlsplit(url).netloc
    request = (url, tuple(sorted((params or {}).items())))
    if host == "www150.statcan.gc.ca":
        asked[("page", *request)] += 1
        return _page(url, STATCAN_PAGE)
    if host == "api.statistiken.bundesbank.de":
        asked[("page", *request)] += 1
        return _page(url, b"<html>challenge</html>", at=f"https://{host}/.enodia/challenge?redirect=x")
    asked[("refused", *request)] += 1
    raise requests.ConnectionError(f"{host}: cut off by check_last_good")


def failing_urlopen(url, timeout=None) -> _Answer:
    asked[("page", url, ())] += 1
    return _Answer(FRED_PAGE)


def check_asked_once(name: str) -> None:
    """A drawing's requests to failing sources: each host asked once, as each fails as unavailable (19.3), and not again."""
    by_host = Counter()
    for request, count in asked.items():
        by_host[urlsplit(request[1]).netloc] += count
    again = {host: count for host, count in by_host.items() if count > 1}
    check(f"{name}: each failing source asked once in the drawing (19.3)", bool(asked) and not again,
          again or f"{len(by_host)} hosts, {sum(by_host.values())} attempts")


# A source's warning at a drawing's end (19.4), one per source and cause:
#   "  Warning: FRED: WHY. 13 series drawn from their baked history: DGS2, DGS10 to 2026-10-21; GDP to 2026-04-01.
#    Drawn from their last good copies, downloaded 2026-10-21 18:30 UTC: Treasury yields; debt, GDP, and interest."
_BAKED_PART = re.compile(r"\d+ series drawn from (?:its|their) baked history: (.*?\d{4}-\d{2}-\d{2})\.(?= |$)")
_COPIES_PART = re.compile(
    r"Drawn from (?:its last good copy|their last good copies), downloaded \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC: (.*?)\.(?= Drawn from |$)"
)


def source_warnings(log: str) -> dict[str, list[str]]:
    """Each source's warning lines in a drawing's log (19.4), by the source's name."""
    found: dict[str, list[str]] = {}
    for line in log.splitlines():
        if line.startswith("  Warning: ") and (_BAKED_PART.search(line) or _COPIES_PART.search(line)):
            found.setdefault(line[len("  Warning: "):].split(": ", 1)[0], []).append(line)
    return found


def baked_reach(lines: list[str]) -> dict[str, str]:
    """The series a source's warnings list as drawn from their bake, each with its bake's last date: {"DGS10": "2026-10-21"}."""
    reach: dict[str, str] = {}
    for line in lines:
        for match in _BAKED_PART.finditer(line):
            for group in match.group(1).split("; "):
                series, last = group.rsplit(" to ", 1)
                reach.update((one, last) for one in series.split(", "))
    return reach


def copies_listed(lines: list[str]) -> list[str]:
    """The downloads a source's warnings list as drawn from their last good copies."""
    return [one for line in lines for match in _COPIES_PART.finditer(line) for one in match.group(1).split("; ")]


def check_reach(what: str, warned: dict[str, list[str]], source: str, ends: dict[str, object]) -> None:
    """``what``, the series of ``source`` the case draws (``ends``: each its bake's last date), all and only them in its one warning (19.2, 19.4)."""
    reach = baked_reach(warned.get(source, []))
    named = sorted(code for code, end in ends.items() if reach.get(code) == f"{end:%Y-%m-%d}")
    others = sorted(set(reach) - set(ends))
    check(f"rates: {what} drawn from their bake, each in {source}'s one warning with its last date (19.2, 19.4)",
          named == sorted(ends) and not others and len(warned.get(source, [])) == 1, (named, others))


def refused_post(_session, url, json=None, **_kwargs):
    asked[("post", url, repr(json))] += 1
    raise requests.ConnectionError("StatCan WDS: cut off by check_last_good")


def final_flat_days(figure: Figure) -> dict[str, float]:
    """For each curve on the right axis, how many days its last value is drawn unchanged."""
    days: dict[str, float] = {}
    for ax in figure.axes:
        if ax.yaxis.get_label_position() != "right":
            continue
        for line in ax.get_lines():
            x = np.asarray(mdates.date2num(line.get_xdata()), dtype=float)
            y = np.asarray(line.get_ydata(), dtype=float)
            drawn = np.isfinite(y)
            x, y = x[drawn], y[drawn]
            if y.size:
                changed = np.flatnonzero(y != y[-1])
                days[line.get_label()] = x[-1] - x[changed[-1] + 1 if changed.size else 0]
    return days


def draw(tokens: list[str]) -> tuple[dict[str, bytes], dict[str, str], list[str], str, dict[str, float]]:
    """Draw a case's charts as the window does.

    Returns (PNGs, charts not drawn, copies used, log, the right axis's final flat days
    by "nation: curve").
    """
    config = cli.parse_args(["--no-gui", *tokens])
    lines: list[str] = []
    pngs: dict[str, bytes] = {}
    not_drawn: dict[str, str] = {}
    flat: dict[str, float] = {}
    with this_thread_output_to(lines.append), http.drawing_downloads() as downloads:
        drawn = resolve_start(config)
        for country in COUNTRIES:
            if getattr(drawn, country.show_field):
                try:
                    figure = build_figure(country, drawn)
                except Exception as exc:  # pass 3 expects some
                    not_drawn[country.key] = f"{type(exc).__name__}: {exc}"
                    continue
                flat.update((f"{country.key}: {label}", days) for label, days in final_flat_days(figure).items())
                pngs[country.key] = png_bytes(figure)
    return pngs, not_drawn, downloads.copies_used(), "".join(lines), flat


def main() -> int:
    # web's import turned on the page's memory cache, which would answer pass 2 from pass 1.
    http._download_cache = None
    requests.Session.post = refused_post  # type: ignore[assignment]
    folder = Path(tempfile.mkdtemp(prefix="ratesplot_last_good_"))
    http.enable_last_good_copies(folder)
    print(f"[last good] copies in {folder}")
    synthetic_sources.install_synthetic_bake(Path(tempfile.mkdtemp(prefix="ratesplot_baked_")))

    print("[last good] pass 1: every source answers")
    requests.Session.get = answering_get  # type: ignore[assignment]
    urllib.request.urlopen = answering_urlopen  # type: ignore[assignment]
    first = {}
    for name, tokens in CASES.items():
        pngs, not_drawn, copies, _log, _flat = draw(tokens)
        first[name] = pngs
        check(f"{name}: every chart drawn, no copy used", not not_drawn and not copies, (sorted(pngs), not_drawn, copies))
    kept = sorted(folder.glob("*.pickle"))
    check("a copy kept of every download", len(kept) >= 20, f"{len(kept)} copies")

    print("[last good] pass 2: every source fails; the copies drawn")
    requests.Session.get = failing_get  # type: ignore[assignment]
    urllib.request.urlopen = failing_urlopen  # type: ignore[assignment]
    for name, tokens in CASES.items():
        asked.clear()
        pngs, not_drawn, copies, log, _flat = draw(tokens)
        check_asked_once(name)
        same = sorted(key for key in pngs if pngs[key] == first[name].get(key))
        check(f"{name}: every chart drawn as in pass 1, byte for byte", not not_drawn and same == sorted(first[name]),
              (same, sorted(first[name]), not_drawn))
        check(f"{name}: the copies named, each with its date", bool(copies) and all(" UTC)" in copy for copy in copies),
              "; ".join(copies))
        warned = source_warnings(log)
        warnings = [line for lines in warned.values() for line in lines]
        # A group drawing on two sources ("ECB and Eurostat government debt") is listed in each one's warning.
        listed = {item for lines in warned.values() for item in copies_listed(lines)}
        labels = {copy.rsplit(" (", 1)[0] for copy in copies}
        check(f"{name}: one warning per source in the log, the cause once, every copy listed in it (19.4)",
              bool(warned) and all(len(lines) == 1 for lines in warned.values()) and listed == labels
              and "drawn from its last good copy" not in log,
              f"{len(warned)} sources ({', '.join(warned)}), {len(labels)} copies"
              + ("" if listed == labels else f": listed {sorted(listed)}; copies {sorted(labels)}"))
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
    flat: dict[str, float] = {}
    for name, tokens in CASES.items():
        asked.clear()
        pngs, not_drawn, copies, log, case_flat = draw(tokens)
        check_asked_once(name)
        warned = source_warnings(log)
        check(f"{name}: one warning per source, none per series (19.4)",
              all(len(lines) == 1 for lines in warned.values()) and "its recent values unavailable" not in log,
              ", ".join(warned))
        if name == "rates":
            # Every Bank of England series the case draws (not SONIA, the market rate), each with its bake's last date.
            ends = {code: baked.read_series("boe", code).index[-1]
                    for code in ("IUDSNPY", "IUDMNPY", "IUDLNPY", "IUDBEDR", "IUMBV34", "IUMBV37", "IUMBV42", "IUMTLMV")}
            check_reach("the Bank of England's series", warned, "Bank of England", ends)
            # The Bank of Canada's the case draws: the benchmark group (named once), the 3-month, the policy rate's
            # three parts and the 5-year mortgage rate (not CORRA, nor the bills it does not choose).
            group = cdn_data.BOC_GROUP_CODES[cdn_data.BOC_BENCHMARK_GROUP]
            ends = {cdn_data.BOC_BENCHMARK_GROUP: max(baked.read_series("boc", code).index[-1] for code in group)}
            ends |= {code: baked.read_series("boc", code).index[-1]
                     for code in ("TB.CDN.90D.MID", "V80691303", "V122530", "V80691310", "CBC20210", "V80691335")}
            check_reach("the Bank of Canada's series", warned, "Bank of Canada", ends)
            # FRED's the case draws: the five yields, the policy rate's parts, the 30-year mortgage rate,
            # debt (federal, state and local), GDP and interest (not DFF, the market rate).
            ends = {code: baked.read_series("fred", code).last_valid_index() for code in FRED_DRAWN_IN_RATES}
            check_reach("FRED's series", warned, "FRED", ends)
            ends = {code: baked.read_series("ecb", code).index[-1] for code in ECB_DRAWN_IN_RATES}
            check_reach("the ECB's series", warned, "ECB", ends)
            # The stopped series: not asked (FRED's address names its series, "?id=DFEDTAR&"; the ECB's its key),
            # not named in a warning.
            stopped_asked = sorted(request[1] for request in asked
                                   if f"id={STOPPED_IN_RATES['FRED']}&" in request[1] or STOPPED_IN_RATES["ECB"].split(".", 1)[1] in request[1])
            stopped_named = [code for source, code in STOPPED_IN_RATES.items() if code in baked_reach(warned.get(source, []))]
            check("rates: the series declared stopped drawn from their bake alone, not asked, not named (19.3)",
                  not stopped_asked and not stopped_named, (stopped_asked, stopped_named))
            ends = {code: baked.read_series("eurostat", code).index[-1] for code in EUROSTAT_DRAWN_IN_RATES}
            check_reach("Eurostat's series", warned, "Eurostat", ends)
            ends = {code: baked.read_series("ons", code).index[-1] for code in ONS_DRAWN_IN_RATES}
            check_reach("the ONS's series", warned, "ONS", ends)
            # Statistics Canada: asked once, for a table's recent part (WDS), never a ZIP; its outage page then
            # stands for every table (19.3); each table the case draws from its bake, named with its last date;
            # the CMHC mortgage rate (the 5-year before 1975) read from its bake alone, not asked.
            statcan = [request for request in asked if urlsplit(request[1]).netloc == "www150.statcan.gc.ca"]
            by_vectors = {",".join(f'"{vector.lstrip("v")}"' for vector in read.vectors): table
                          for table, read in cdn_data.STATCAN_SERIES_READ.items()}
            tables = sorted(by_vectors.get(dict(request[2]).get("vectorIds"), request[1]) for request in statcan)
            check("rates: Statistics Canada asked once, for a table's recent part (19.2, 19.3)",
                  len(tables) == 1 and tables[0] in STATCAN_DRAWN_IN_RATES
                  and all(request[1] == cdn_data.STATCAN_WDS_RANGE_URL for request in statcan), tables)
            ends = {f"table {table}": max(baked.read_series("statcan", vector).index[-1] for vector in read.vectors)
                    for table, read in cdn_data.STATCAN_SERIES_READ.items() if table in STATCAN_DRAWN_IN_RATES}
            check_reach("Statistics Canada's tables", warned, "Statistics Canada", ends)
            # The Bundesbank's yields: its bot check answers the first request, the only one it is sent; every
            # term then drawn from its bake, the check named once, with the bakes' last date.
            end = max(baked.read_series("bbk", path.stem).index[-1] for path in (baked.DATA_FOLDER / "bbk").glob("*.csv"))
            to_bundesbank = sum(count for request, count in asked.items() if urlsplit(request[1]).netloc == "api.statistiken.bundesbank.de")
            said = [line for line in log.splitlines() if "sent a bot check instead of data" in line]
            per_series = [line for line in log.splitlines() if "Warning: Bundesbank " in line]
            check("rates: the Bundesbank asked once, its bot check named once, the yields drawn from their bake to its last date (19.2)",
                  to_bundesbank == 1 and len(said) == 1 and not per_series
                  and f"The German yields drawn from their baked history, to {end:%Y-%m-%d}." in said[0],
                  (to_bundesbank, said, per_series))
        differs = sorted(key for key in first[name] if pngs.get(key) != first[name][key])
        if name in DRAWN_FROM_THE_BAKE_ALONE:
            check(f"{name}: drawn without them as in pass 1, byte for byte, from the bake alone (19.2)", not differs, f"differ or missing: {differs}")
        else:
            check(f"{name}: not drawn, or drawn otherwise, without them", bool(differs), f"differ or missing: {differs}")
        flat.update((f"{name}, {curve}", days) for curve, days in case_flat.items())
    # The UK's chart without the ONS's bake too, as before 19.2's ONS stage: its gross debt is not drawn, so the
    # national debt runs on alone to 2016, past 1975.
    without_ons = Path(tempfile.mkdtemp(prefix="ratesplot_baked_no_ons_"))
    shutil.copytree(baked.DATA_FOLDER, without_ons, dirs_exist_ok=True)
    shutil.rmtree(without_ons / "ons")
    with_ons, baked.DATA_FOLDER = baked.DATA_FOLDER, without_ons
    baked.forget_read_files()
    try:
        asked.clear()
        _pngs, not_drawn, _copies, log, uk_flat = draw(UK_RATES)
        check_asked_once("uk without the ONS's bake")
        check("uk without the ONS's bake: the gross debt not drawn, with its warning",
              "uk" not in not_drawn and "Warning: ONS BKPX (UK debt) unavailable" in log, not_drawn)
        flat.update((f"uk without the ONS's bake, {curve}", days) for curve, days in uk_flat.items())
    finally:
        baked.DATA_FOLDER = with_ons
        baked.forget_read_files()
    held_on = {curve: round(days) for curve, days in flat.items() if days > MACRO_CARRY_LIMIT.days}
    check(f"the baked history alone: no right-axis curve keeps its last value more than {MACRO_CARRY_LIMIT.days} days",
          bool(flat) and not held_on,
          held_on or "; ".join(f"{curve} {round(days)}" for curve, days in flat.items()))
    national = [curve for curve in flat if "National Debt" in curve]
    check("the baked history alone: the UK's national debt, past 1975 without the gross debt, named without (pre-1975)",
          national == ["uk without the ONS's bake, uk: UK National Debt"], national)

    print(f"[last good] {'all checks passed' if not failures else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
