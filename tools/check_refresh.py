#!/usr/bin/env python3
"""Check the automatic refresh (``ratesplot/refresh.py``, batch 11.3) where no window is needed.

* the rule for when a refresh can bring nothing new
  (``PlotConfig.refresh_brings_nothing``): the quotes off, an End before
  today, no quoted yield on any chart shown (the spreads count);
* the markets' hours (``refresh.in_market_hours``), each chart's in its own
  zone, a chart without quoted yields not counted;
* the quotes a refresh compares (``latest.quote_state``): those a drawing
  takes, the next day's session and a day after the chart's end left out;
* whether each tick draws again (``refresh.Ticker``): always within market
  hours; outside them at the first tick, then only when a quote has changed;
  never when the feed does not answer;
* the --save files (``export.SavedFiles``): written through a temporary file
  swapped in; a file another program holds gets "_n" (n from 1), kept until
  that one is held too; a name with a number that is already there skipped;
  the name given replaced as a save replaces it; nothing left open;
* the command line (``cli.main``, ``cli.keep_saving``): a refresh that can
  bring nothing new says so and draws once; otherwise the console line about
  Ctrl-C, a file written at each tick that is due, none at one that is not,
  and the end on Ctrl-C or when an End given as today has passed;
* a plain window's refresh (``plotting._refresher``, ``refresh.attach``): what
  Refresh does at a tick that is due, nothing at one that is not, the end when
  nothing new can come; the hover read-out taken off and given again
  (``hover.detach``).

No network: the feed, the drawing and the clock are stood in for. The
window's and the page's timers are checked by ``tools/verify_gui.py`` (group
``auto_refresh``) and ``tools/verify_web.py``.

Usage (from the project root)::

    python tools/check_refresh.py

Exit code 1 on any FAIL.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import verify_charts  # noqa: E402,F401  (unused but first: it sets the Agg backend before pyplot is imported)

del verify_charts
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from ratesplot import cli, export, hover, latest, plotting, refresh  # noqa: E402
from ratesplot.config import PlotConfig  # noqa: E402

TODAY = pd.Timestamp.today().normalize()


def config(*tokens: str) -> PlotConfig:
    return cli.parse_args(["--no-gui", *tokens])


def at(text: str) -> pd.Timestamp:
    """A moment, written in Toronto's time."""
    return pd.Timestamp(text, tz="America/Toronto").tz_convert("UTC")


def quote(last: str, when: str, change: str = "+0.010") -> dict:
    return {"last": last, "last_time": when, "change": change}


def check_rule(check) -> None:
    """When a refresh can bring nothing new."""
    check("the defaults: a refresh can bring something", config("--au").refresh_brings_nothing is None)
    check("the quotes off: nothing", "--no-cur" in (config("--au", "--no-cur").refresh_brings_nothing or ""))
    yesterday = f"-e:{TODAY - pd.Timedelta(days=1):%Y-%m-%d}"
    check("an End before today: nothing", "before today" in (config("--au", yesterday).refresh_brings_nothing or ""))
    check("an End of today: something", config("--au", f"-e:{TODAY:%Y-%m-%d}").refresh_brings_nothing is None)
    check("an End after today: something", config("--au", f"-e:{TODAY + pd.Timedelta(days=30):%Y-%m-%d}").refresh_brings_nothing is None)
    check("no yield: nothing", "no chart" in (config("--au", "--no-yield").refresh_brings_nothing or ""))
    check("no yield, a spread: something", config("--au", "--no-yield", "--sp").refresh_brings_nothing is None)
    check("Canada's 7-year alone, which has no quote: nothing", config("--au", "-c", "--yields:7").refresh_brings_nothing is not None)
    check("the U.S.'s none, Canada's own: something", config("--au", "--us:yields:none").refresh_brings_nothing is None)
    check("both nations' none: nothing", config("--au", "--us:yields:none", "--cdn:yields:none").refresh_brings_nothing is not None)
    check("the UK alone: its three quoted", config("--au", "--na:gb").quoted_columns("uk") == ("5-Year", "10-Year", "20-Year"),
          config("--au", "--na:gb").quoted_columns("uk"))


def check_hours(check) -> None:
    """The markets' hours, each chart's in its own zone."""
    both = config()
    check("Tuesday 10:00 Toronto: within", refresh.in_market_hours(both, at("2026-10-27 10:00")))
    check("Tuesday 16:59 Toronto: within", refresh.in_market_hours(both, at("2026-10-27 16:59")))
    check("Tuesday 17:00 Toronto: outside", not refresh.in_market_hours(both, at("2026-10-27 17:00")))
    check("Tuesday 07:59 Toronto: outside", not refresh.in_market_hours(both, at("2026-10-27 07:59")))
    check("Saturday noon: outside", not refresh.in_market_hours(both, at("2026-10-31 12:00")))
    uk = config("--na:gb")
    check("the UK at 04:00 Toronto, 08:00 London: within", refresh.in_market_hours(uk, at("2026-10-27 04:00")))
    # Europe's clocks went back on 2026-10-25, North America's on 2026-11-01: London is 4 hours ahead this week.
    check("the UK at 13:30 Toronto, 17:30 London: outside", not refresh.in_market_hours(uk, at("2026-10-27 13:30")))
    check("the UK with Canada at 13:30 Toronto: within, Canada's", refresh.in_market_hours(config("--na:gb,ca"), at("2026-10-27 13:30")))
    check("Canada shown without yields, the UK with: the UK's hours alone",
          not refresh.in_market_hours(config("--na:gb,ca", "--cdn:yields:none"), at("2026-10-27 13:30")))


def check_quote_state(check) -> None:
    """The quotes a refresh compares: those a drawing takes."""
    answers: dict[str, dict] = {}
    original = latest.fetch_quotes
    asked: list[str] = []

    def fetch(country, columns=None):
        asked.append(country)
        return {column: answers.get(country, {}).get(column) for column in columns}

    latest.fetch_quotes = fetch
    try:
        today = f"{TODAY:%Y-%m-%d}"
        answers["us"] = {
            "3-Month": quote("3.900%", f"{today}T10:00:00.000-0400"),
            "2-Year": quote("3.500%", f"{today}T17:05:00.000-0400"),  # the next day's session
            "10-Year": None,
            "30-Year": {"last": "4.6%"},  # no time: unusable
        }
        state = latest.quote_state(config("-u"))
        check("the U.S.: one request", asked == ["us"], asked)
        check("the usable quote kept, the next session's and the unusable left out",
              [item[0] for item in state] == ["US3M"], state)
        asked.clear()
        state = latest.quote_state(config("-u", f"-e:{TODAY - pd.Timedelta(days=1):%Y-%m-%d}"))
        check("a quote after the chart's end left out", state == (), state)
        asked.clear()
        latest.quote_state(config("--na:ca,us,gb", "--cdn:yields:none"))
        check("only the nations shown with quoted yields asked", asked == ["us", "uk"], asked)
    finally:
        latest.fetch_quotes = original


def check_ticker(check) -> None:
    """Whether each tick draws again."""
    states = iter([("A",), ("A",), ("B",), ("B",)])
    original = refresh.quote_state
    refresh.quote_state = lambda _config: next(states)
    shown = config("-u")
    ticker = refresh.Ticker()

    def due(when: str) -> bool:
        with contextlib.redirect_stdout(io.StringIO()):
            return ticker.due(shown, at(when))

    try:
        check("within market hours: due, the feed not asked", due("2026-10-27 10:00"))
        check("the first tick outside: due", due("2026-10-27 18:00"))
        check("outside, the same quotes: not due", not due("2026-10-27 18:05"))
        check("outside, a quote changed: due", due("2026-10-27 18:10"))
        check("within again: due", due("2026-10-28 09:00"))
        check("outside after it: due again at first", due("2026-10-28 17:30"))

        def down(_config):
            raise ConnectionError("no answer")

        refresh.quote_state = down
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            due = refresh.Ticker().due(shown, at("2026-10-27 18:00"))
        check("the feed down: not due, with a warning", not due and "Warning: intraday quotes unavailable" in printed.getvalue(),
              printed.getvalue())
    finally:
        refresh.quote_state = original


def check_saved_files(check) -> None:
    """The --save files: a temporary file swapped in; "_n" for a file another program holds."""
    folder = Path(tempfile.mkdtemp(prefix="ratesplot_check_refresh_"))
    try:
        files = export.SavedFiles()
        target = str(folder / "rates_ca.png")

        def write(saving: export.SavedFiles, data: bytes, name: str = target) -> tuple[str, str]:
            """The name written, and what was said."""
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                return saving.write(name, data), printed.getvalue()

        check("a new file: under its name", write(files, b"one")[0] == target and Path(target).read_bytes() == b"one")
        Path(folder / "other.png").write_bytes(b"theirs")
        check("the name given replaced as a save replaces it",
              write(export.SavedFiles(), b"mine", str(folder / "other.png"))[0] == str(folder / "other.png"))
        check("written again: replaced", write(files, b"two")[0] == target and Path(target).read_bytes() == b"two")
        held = open(target, "rb")  # Python opens without sharing deletion: Windows refuses to replace it
        try:
            first, said = write(files, b"three")
            check("held by another program: written as _1, and said", first == str(folder / "rates_ca_1.png")
                  and "Held by another program" in said, (first, said))
            check("the held file left as it was", Path(target).read_bytes() == b"two")
        finally:
            held.close()
        check("the next refresh keeps _1, though the first is free again", write(files, b"four")[0] == first
              and Path(first).read_bytes() == b"four")
        (folder / "rates_ca_2.png").write_bytes(b"someone else's")
        held = open(first, "rb")
        try:
            second = write(files, b"five")[0]
        finally:
            held.close()
        check("_1 held too: _2 is there already, so _3", second == str(folder / "rates_ca_3.png")
              and (folder / "rates_ca_2.png").read_bytes() == b"someone else's", second)
        check("and _3 kept", write(files, b"six")[0] == second)
        check("no temporary file left", not list(folder.glob("*.tmp")), sorted(path.name for path in folder.iterdir()))
        check("no file held open: each can be removed", all(_removable(path) for path in folder.iterdir()))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _removable(path: Path) -> bool:
    try:
        path.rename(path.with_suffix(path.suffix + ".moved"))
    except OSError:
        return False
    return True


def check_command_line(check) -> None:
    """The command line: drawn once where nothing new can come; otherwise written again until Ctrl-C."""
    saved: list[str] = []
    originals = (cli.save_charts, cli.resolve_start, cli.time.sleep, cli.Ticker, cli.forget_old_downloads)
    sleeps: list[float] = []
    plan: list[object] = []

    def save_charts(drawn, files=None):
        saved.append(drawn.save)
        return []

    def sleep(seconds):
        sleeps.append(seconds)
        step = plan.pop(0)
        if isinstance(step, BaseException):
            raise step

    class Ticker:
        def due(self, _config, now=None):
            return bool(plan.pop(0))

    cli.save_charts, cli.resolve_start, cli.time.sleep, cli.Ticker = save_charts, lambda drawn: drawn, sleep, Ticker
    cli.forget_old_downloads = lambda: 0
    try:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            cli.main(["--au", "--no-cur", "--save:r.png", "-s:2020"])
        check("nothing new can come: said, drawn once", saved == ["r.png"] and "nothing new can come" in printed.getvalue()
              and "Ctrl-C" not in printed.getvalue(), printed.getvalue())

        saved.clear()
        plan[:] = [None, True, None, False, KeyboardInterrupt()]  # sleep, due, sleep, not due, Ctrl-C
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            cli.main(["--au:10", "--save:r.png", "-s:2020"])
        out = printed.getvalue()
        check("the console line: every 10 minutes, Ctrl-C ends it", "Automatic refresh every 10 minutes: press Ctrl-C to end it." in out, out)
        check("10 minutes between ticks", sleeps and all(seconds == 600 for seconds in sleeps), sleeps)
        check("written at the start and at the tick due, not at the other", saved == ["r.png", "r.png"], saved)
        check("ended by Ctrl-C, and said", "Automatic refresh ended (Ctrl-C)." in out, out)

        saved.clear()
        today = f"-e:{TODAY:%Y-%m-%d}"
        plan[:] = [None]
        reads = iter([config("--au", today, "--save:r.png"), config("--au", "-e:2020-01-02", "--save:r.png")])
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            cli.keep_saving(lambda: next(reads), export.SavedFiles(), [])
        check("an End given as today, now past: ended by itself, and said", "Automatic refresh ended: the End date" in printed.getvalue()
              and saved == [], printed.getvalue())
    finally:
        cli.save_charts, cli.resolve_start, cli.time.sleep, cli.Ticker, cli.forget_old_downloads = originals


def check_plain_window(check) -> None:
    """A plain window's refresh: what Refresh does at a tick that is due; the hover read-out given again."""
    prepared: list[PlotConfig] = []
    dropped: list[int] = []
    original = plotting.forget_old_downloads
    plotting.forget_old_downloads = lambda: dropped.append(1) or 3

    def prepare(own):
        prepared.append(own)
        return "yields", "macro", "rates"

    class Due:
        def __init__(self, answer):
            self.answer = answer

        def due(self, _config, now=None):
            return self.answer

    try:
        shown = config("-u", "--au")
        check("no refresh asked for: none", plotting._refresher("us", prepare, None) is None)
        refreshed = plotting._refresher("us", prepare, lambda: shown)
        with contextlib.redirect_stdout(io.StringIO()):
            result = refreshed(Due(True))
        check("a tick due: the old downloads dropped, the chart prepared again, its own config last",
              dropped == [1] and result[:3] == ("yields", "macro", "rates") and result[3] == prepared[-1]
              and prepared[-1] == shown.for_nation("us"), result)
        check("a tick not due: nothing", refreshed(Due(False)) is None and len(prepared) == 1)
        past = plotting._refresher("us", prepare, lambda: replace(shown, end=pd.Timestamp("2020-01-02")))
        try:
            past(Due(True))
            ended = False
        except refresh.Ended:
            ended = True
        check("nothing new can come any more: ended", ended)

        # The window's side, on an Agg canvas (its timers never fire there): a tick's result drawn on its thread.
        figure = Figure()
        FigureCanvasAgg(figure)
        drawn: list[object] = []
        refresh.attach(figure, 5, lambda ticker: "the inputs", drawn.append)
        window = figure._ratesplot_refresh_window
        check("its timer every 5 minutes", window.timers[0].interval == 5 * 60_000, window.timers[0].interval)
        window.working = True
        with contextlib.redirect_stdout(io.StringIO()):
            window._work()
        window._poll()
        check("a result drawn on the window's thread", drawn == ["the inputs"] and not window.working)
        window.refreshed = lambda ticker: (_ for _ in ()).throw(refresh.Ended("the End date is past"))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            window._work()
        window._poll()
        check("ended: said, nothing drawn", "Automatic refresh ended: the End date is past." in printed.getvalue() and drawn == ["the inputs"])

        figure = Figure()
        FigureCanvasAgg(figure)
        hover.attach(figure)
        callbacks = sum(len(handlers) for handlers in figure.canvas.callbacks.callbacks.values())
        hover.detach(figure)
        left = sum(len(handlers) for handlers in figure.canvas.callbacks.callbacks.values())
        check("the read-out taken off: its three callbacks gone", callbacks - left == 3 and not hasattr(figure, "_ratesplot_hover_window"),
              (callbacks, left))
    finally:
        plotting.forget_old_downloads = original


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    os.chdir(tempfile.mkdtemp(prefix="ratesplot_check_refresh_cwd_"))  # cli.main's stand-in writes nothing, but just in case
    for group in (check_rule, check_hours, check_quote_state, check_ticker, check_saved_files, check_command_line, check_plain_window):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group(check)
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[refresh] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
