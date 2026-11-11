#!/usr/bin/env python3
"""Check the wait line (``ratesplot/wait.py``, batch 35.1) and the page's line of drawings (``web._turn``, 35.2), with no network.

* the words: "Please wait about 12 s (5 s so far)", seconds to about 90 s
  (rounded to 5 above 20), minutes from there, "nearly done";
* the figures (``wait.Figures``): the starting ones; read back from the settings
  file, anything else in it left out; each moved towards what was measured, the
  newest weighing a third; a nation's requests replaced by its last drawing's;
* the sum (``wait.Wait``): the longest host's requests, not all of them; a kept
  download not counted; a chart scaled by its size; the quotes where they reach
  the chart; the drawings ahead and a drawing queued behind;
* the figure shown: it counts down steadily, rises only on a real jump, drops
  at once, and leaves "nearly done" when a step overruns, never 0 or less;
* what ``http._cached`` notes for it: a real download's time less its wait for
  the host's turn, the nation asking, nothing for a failed request;
* the page's drawings: one at a time in the order asked, a stopped one leaving
  the line, the message log naming a wait, what is left of those ahead counted,
  a drawing stopped between charts teaching nothing.

    python tools/check_wait.py

Exit status 0 only if every check passes. The last good copies its made-up requests
leave are kept in a folder of its own in Temp, removed at its end (batch 41.2).
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import temp_folders  # noqa: E402  (tools/, the script's own folder)
from ratesplot import http, web, wait  # noqa: E402
from ratesplot.cli import parse_args  # noqa: E402
from ratesplot.config import DEFAULT_CANVAS_PX  # noqa: E402

HOST_A = "https://a.example/data"
HOST_B = "https://b.example/data"


def key(url: str, name: str = "x") -> tuple:
    """A request's cache key as ``http`` makes one: its tag, its address, its parameters."""
    return ("get", url, (("series", name),))


def check_words(check) -> None:
    """The words."""
    cases = [
        (0.6, "1 s"), (1.4, "1 s"), (12.4, "12 s"), (20.0, "20 s"), (21.0, "20 s"), (23.0, "25 s"), (47.0, "45 s"),
        (89.0, "90 s"), (90.0, "2 min"), (120.0, "2 min"), (400.0, "7 min"),
    ]
    for seconds, text in cases:
        check(f"expected {seconds} s: {text}", wait.expected_text(seconds) == text, wait.expected_text(seconds))
    for seconds, text in [(0.0, "0 s"), (5.9, "5 s"), (89.9, "89 s"), (90.0, "1 min 30 s"), (125.0, "2 min 5 s")]:
        check(f"taken {seconds} s: {text}", wait.taken_text(seconds) == text, wait.taken_text(seconds))
    check("the line, Terry's words", wait.wait_text(12.0, 5.0) == "Please wait about 12 s (5 s so far)", wait.wait_text(12.0, 5.0))
    check("the line in minutes", wait.wait_text(120.0, 95.0) == "Please wait about 2 min (1 min 35 s so far)", wait.wait_text(120.0, 95.0))
    check("nearly done, never 0 s", wait.wait_text(0.4, 9.0) == "Please wait, nearly done (9 s so far)", wait.wait_text(0.4, 9.0))
    check("nothing says another visitor", not any("visitor" in wait.wait_text(left, 1.0) for left in (0.0, 5.0, 500.0)))


def check_figures(check) -> None:
    """The figures."""
    figures = wait.Figures()
    check("starting: a chart at the default size", figures.chart_seconds(DEFAULT_CANVAS_PX[0] * DEFAULT_CANVAS_PX[1]) == wait.STARTING_CHART_SECONDS)
    check("a larger chart takes longer, a smaller less, not in proportion",
          figures.chart_seconds(800 * 600) < figures.chart == 1.0 < figures.chart_seconds(4096 * 3072) < 4 * figures.chart)
    check("every nation has its starting requests", set(figures.asked) == {"cdn", "us", "uk", "de"}, sorted(figures.asked))
    expected = figures.expected_requests(["uk"])
    check("a nation not yet drawn: its starting count, at its host's figure",
          sorted((host, len(each)) for host, each in expected.items()) == [("www.bankofengland.co.uk", 3), ("www.ons.gov.uk", 3)]
          and expected["www.bankofengland.co.uk"][0] == (None, 15.0), expected)
    saved = figures.to_saved()
    again = wait.Figures(saved)
    check("written and read back: the same", again.to_saved() == saved)
    edited = {"chart": "fast", "start": -1, "late": 1e9, "hosts": {"a.example": 2.0, "b.example": "x", 5: 1.0}, "asked": {"de": {"a.example": 2, "b.example": -1}, "uk": 3}, "other": 1}
    read = wait.Figures(edited)
    check("a settings file's nonsense left out", read.chart == wait.STARTING_CHART_SECONDS and read.start == wait.STARTING_START_SECONDS
          and read.late == wait.STARTING_LATE_SECONDS and read.hosts["a.example"] == 2.0 and "b.example" not in read.hosts
          and read.asked["de"] == {"a.example": 2} and read.asked["uk"] == wait._STARTING_ASKED["uk"], read.to_saved())
    check("no settings at all: the starting figures", wait.Figures(["a list"]).to_saved() == saved)
    figures = wait.Figures()
    a, b = key(HOST_A, "1"), key(HOST_B, "2")
    figures.learn([("uk", a, 4.0)], {"uk": {a, b}}, 0.4, [3.0], [1.1])
    check("each figure moved a third of the way", abs(figures.chart - (1.0 + 2.0 / 3)) < 1e-9 and abs(figures.start - 0.2) < 1e-9 and abs(figures.late - 0.5) < 1e-9
          and abs(figures.hosts["a.example"] - 2.0) < 1e-9, figures.to_saved())
    check("a nation's requests are its last drawing's", figures.asked["uk"] == {"a.example": 1, "b.example": 1}, figures.asked["uk"])
    expected = figures.expected_requests(["uk"])
    check("a request measured: its own last time, not its host's", expected["a.example"] == [(a, 4.0)], expected)
    check("a request not measured (it was kept): its host's", expected["b.example"] == [(b, wait._UNKNOWN_HOST_SECONDS)], expected)
    figures.learn([], {"us": {a}}, None, [], [])
    check("a request two nations share counted once", sum(len(each) for each in figures.expected_requests(["uk", "us"]).values()) == 2)
    past = wait.Figures()
    check("a chart ending in the past, not yet drawn: no requests expected", past.expected_requests(["uk"], live=False) == {}, past.expected_requests(["uk"], live=False))
    past.learn([], {}, None, [], [], nations=["uk"], live=False)
    check("… one that asked for nothing: nothing expected of it, its live row as it was",
          past.expected_requests(["uk"], live=False) == {} and past.asked["uk"] == wait._STARTING_ASKED["uk"]
          and len(past.expected_requests(["uk"])["www.bankofengland.co.uk"]) == 3)
    past.learn([], {"uk": {a}}, None, [], [], live=False)
    check("… one that asked: its own request, the saved counts as they were",
          list(past.expected_requests(["uk"], live=False)) == ["a.example"] and past.asked["uk"] == wait._STARTING_ASKED["uk"], past.expected_requests(["uk"], live=False))
    past.learn([], {}, None, [], [], nations=["uk"])
    check("a chart reaching today that asked for nothing: nothing expected, the saved counts kept for a new run",
          past.expected_requests(["uk"]) == {} and past.asked["uk"] == wait._STARTING_ASKED["uk"])
    check("no measurement, no change", abs(figures.start - 0.2) < 1e-9)
    http.enable_download_cache(max_age_seconds=3600)
    try:
        with http._download_cache_lock:
            http._download_cache[a] = (time.monotonic(), time.time(), "body")
        check("a download still kept is not expected", list(figures.expected_requests(["uk"])) == ["b.example"], figures.expected_requests(["uk"]))
        with http._download_cache_lock:
            http._download_cache[a] = (time.monotonic() - 3601, time.time(), "body")
        check("… one older than the limit is", set(figures.expected_requests(["uk"])) == {"a.example", "b.example"})
    finally:
        with http._download_cache_lock:
            http._download_cache.clear()


def check_sum(check) -> None:
    """The sum."""
    figures = wait.Figures()
    pixels = DEFAULT_CANVAS_PX[0] * DEFAULT_CANVAS_PX[1]
    whole = wait.Wait(figures, ["cdn"], pixels).remaining()
    # Canada: the Bank's 6 at 1 s and Statistics Canada's 3 at 1 s, side by side: 6 s; its start 0.1 s; its chart 1 s.
    check("the longest host's requests, the start's work and the chart", abs(whole - 7.1) < 1e-6, whole)
    two = wait.Wait(figures, ["cdn", "us"], pixels).remaining()
    check("two nations: their hosts side by side, each chart in turn", abs(two - (9.0 + 0.2 + 2.0)) < 1e-6, two)
    quoted = wait.Wait(figures, ["cdn"], pixels, quotes=True).remaining()
    check("the quotes where they reach the chart", abs(quoted - (whole + wait.STARTING_LATE_SECONDS)) < 1e-6, quoted)
    large = wait.Wait(figures, ["cdn"], 4 * pixels).remaining()
    check("a larger chart, a longer wait", large > whole, large)
    config = parse_args(["--na:ca,us", "-s:2001", "--e:2019"])
    check("a chart ending in the past: no quotes", wait.Wait.of_config(figures, config, ["cdn", "us"])._quotes is False)
    check("… and of the kind that asks for little", wait.Wait.of_config(figures, config, ["cdn", "us"])._live is False)
    check("a chart reaching today: of the kind that asks", wait.Wait.of_config(figures, parse_args(["-c"]), ["cdn"])._live is True)
    check("a start given with one nation: the chart makes the requests", wait.Wait.of_config(figures, parse_args(["-c", "-s:2001"]), ["cdn"])._side_by_side is False)
    check("a blank start with one nation: a first pass makes them", wait.Wait.of_config(figures, parse_args(["-c"]), ["cdn"])._side_by_side is True)
    ahead = wait.Wait(figures, ["cdn"], pixels, ahead=lambda: 30.0).remaining()
    check("the drawings ahead added", abs(ahead - (whole + 30.0)) < 1e-6, ahead)
    behind = wait.Wait(figures, ["cdn"], pixels)
    behind.then = wait.Wait(figures, ["us"], pixels).whole
    check("a drawing queued behind added", abs(behind.remaining() - (whole + 9.0 + 0.1 + 1.0)) < 1e-6, behind.remaining())
    # A drawing's steps, the clock given.
    downloads = SimpleNamespace(requests=[], asked={}, quote_seconds=0.0, failed={})
    fixed = wait.Wait(figures, ["cdn"], pixels)
    fixed.began_work(downloads)
    began = fixed._step_began
    check("its turn come: nothing ahead", abs(fixed.remaining(began) - whole) < 1e-3, fixed.remaining(began))
    fixed._ahead = lambda: 99.0
    check("… what was ahead no longer counted", abs(fixed.remaining(began) - whole) < 1e-3, fixed.remaining(began))
    check("it counts down while a step runs", abs(fixed.remaining(began + 2.0) - (whole - 2.0)) < 1e-3, fixed.remaining(began + 2.0))
    check("a step that overruns counts down no further than the steps after it", abs(fixed.remaining(began + 50.0) - 1.0) < 1e-3, fixed.remaining(began + 50.0))
    fixed.start_ended()
    now = fixed._progress_at
    check("the first pass over: the charts left", abs(fixed.remaining(now) - 1.0) < 1e-3, fixed.remaining(now))
    fixed.chart_begun("cdn")
    now = fixed._step_began
    check("in the last chart, overrun: never below 0", fixed.remaining(now + 60.0) == 0.0, fixed.remaining(now + 60.0))
    check("… its line says nearly done", "nearly done" in fixed.line(now + 60.0), fixed.line(now + 60.0))
    fixed.chart_ended(True)
    check("its figure for the chart measured", len(fixed._measured_charts) == 1)
    # Requests ending: taken off what is expected, by key where known.
    figures = wait.Figures()
    a1, a2, b1 = key(HOST_A, "1"), key(HOST_A, "2"), key(HOST_B, "1")
    figures.learn([("uk", a1, 5.0), ("uk", a2, 6.0), ("uk", b1, 2.0)], {"uk": {a1, a2, b1}}, None, [], [])
    downloads = SimpleNamespace(requests=[], asked={}, quote_seconds=0.0, failed={})
    fixed = wait.Wait(figures, ["uk"], pixels)
    fixed.began_work(downloads)
    check("the longest host's sum", abs(fixed._downloads_left() - 11.0) < 1e-9, fixed._downloads_left())
    downloads.requests.append(("uk", a2, 6.0))
    fixed.remaining()
    check("… a request ended: taken off", abs(fixed._downloads_left() - 5.0) < 1e-9, fixed._downloads_left())
    downloads.requests.append(("uk", a1, 5.0))
    fixed.remaining()
    check("… that host done: the other's", abs(fixed._downloads_left() - 2.0) < 1e-9, fixed._downloads_left())
    # With only counts known (a nation not yet drawn).
    figures = wait.Figures({"hosts": {"a.example": 2.0}, "asked": {"de": {"a.example": 3}}})
    downloads = SimpleNamespace(requests=[], asked={}, quote_seconds=0.0, failed={})
    fixed = wait.Wait(figures, ["de"], pixels)
    fixed.began_work(downloads)
    downloads.requests.append(("de", a1, 1.0))
    fixed.remaining()
    check("… a count known: one taken off", abs(fixed._downloads_left() - 4.0) < 1e-9, fixed._downloads_left())
    # What a whole drawing teaches.
    figures = wait.Figures()
    downloads = SimpleNamespace(requests=[("uk", a1, 5.0)], asked={"uk": {a1}}, quote_seconds=0.0, failed={})
    fixed = wait.Wait(figures, ["uk"], pixels, quotes=True)
    fixed.began_work(downloads)
    fixed._step_began -= 5.5  # the first pass: its 5 s request and 0.5 s of its own
    fixed.start_ended()
    fixed.chart_begun("uk")
    fixed._step_began -= 2.0  # the chart: 2 s, 0.5 of them its quotes
    downloads.quote_seconds = 0.5
    fixed.chart_ended(True)
    fixed.finished()
    check("the first pass's own work", abs(figures.start - (0.1 + (0.5 - 0.1) / 3)) < 0.02, figures.start)
    check("the chart's own time, its quotes aside", abs(figures.chart - (1.0 + 0.5 / 3)) < 0.02, figures.chart)
    check("the quotes", abs(figures.late - (0.2 + 0.3 / 3)) < 1e-6, figures.late)
    check("the host's", abs(figures.hosts["a.example"] - (1.0 + 4.0 / 3)) < 1e-6, figures.hosts["a.example"])
    failed = wait.Figures()
    downloads = SimpleNamespace(requests=[], asked={}, quote_seconds=0.0, failed={a1: OSError("down")})
    fixed = wait.Wait(failed, ["uk"], pixels)
    fixed.began_work(downloads)
    fixed._step_began -= 90.0
    fixed.start_ended()
    fixed.chart_begun("uk")
    fixed._step_began -= 90.0
    fixed.chart_ended(False)
    fixed.finished()
    check("a source failing teaches nothing of the start or the chart", failed.start == wait.STARTING_START_SECONDS and failed.chart == wait.STARTING_CHART_SECONDS, failed.to_saved())


def check_steady(check) -> None:
    """The figure shown."""
    figures = wait.Figures()
    worked_out = {"value": 30.0}
    steady = wait.Wait(figures, [], 1000, began=100.0)
    steady.remaining = lambda now=None: worked_out["value"]
    check("the first look: as worked out", steady.line(100.0) == "Please wait about 30 s (0 s so far)", steady.line(100.0))
    worked_out["value"] = 30.0
    check("a sum that stays put: counted down all the same", steady.line(105.0) == "Please wait about 25 s (5 s so far)", steady.line(105.0))
    worked_out["value"] = 31.0
    check("a small rise: not shown", steady.line(106.0) == "Please wait about 25 s (6 s so far)", steady.line(106.0))
    worked_out["value"] = 60.0
    check("a real jump: shown", steady.line(107.0) == "Please wait about 60 s (7 s so far)", steady.line(107.0))
    worked_out["value"] = 10.0
    check("a drop: shown at once", steady.line(108.0) == "Please wait about 10 s (8 s so far)", steady.line(108.0))
    worked_out["value"] = 2.0
    check("a step overrunning: the small rise not shown once it has run out", "nearly done" in steady.line(130.0), steady.line(130.0))
    worked_out["value"] = 0.0
    check("nearly done, and never 0 or less", steady.line(140.0) == "Please wait, nearly done (40 s so far)", steady.line(140.0))


def check_noted(check) -> None:
    """What ``http._cached`` notes."""
    http.enable_download_cache(max_age_seconds=3600)
    with http._download_cache_lock:
        http._download_cache.clear()
    try:
        with http.drawing_downloads() as downloads:
            http.asking_for("uk")
            http._cached(key(HOST_A), lambda: (time.sleep(0.05), "body")[1])
            http._cached(key(HOST_A), lambda: "not asked: kept")
            http.asking_for(None)
            http._cached(key(HOST_B), lambda: "asked with no nation")
            try:
                http._cached(key(HOST_B, "bad"), lambda: (_ for _ in ()).throw(ValueError("no")))
            except ValueError:
                pass
        check("a real download noted once, with the nation and its time", len([r for r in downloads.requests if r[1] == key(HOST_A)]) == 1
              and downloads.requests[0][0] == "uk" and downloads.requests[0][2] >= 0.05, downloads.requests)
        check("the nation's requests, kept or not", downloads.asked == {"uk": {key(HOST_A)}}, downloads.asked)
        check("a request with no nation noted without one", any(r[0] is None and r[1] == key(HOST_B) for r in downloads.requests))
        check("a failed request not noted", not any(r[1] == key(HOST_B, "bad") for r in downloads.requests))
        check("the kept request is answered as kept", http.download_is_kept(key(HOST_A)) and not http.download_is_kept(key(HOST_B, "bad")))

        # A request's wait for its host's turn is another's time.
        slow = threading.Event()
        held = threading.Event()

        def first() -> None:
            with http.host_turn(HOST_A):
                held.set()
                slow.wait(5)

        with http.drawing_downloads() as downloads:
            thread = threading.Thread(target=first)
            thread.start()
            held.wait(5)
            threading.Timer(0.2, slow.set).start()

            def second() -> str:
                with http.host_turn(HOST_A):
                    return "body"

            http._cached(key(HOST_A, "after"), second)
            thread.join()
        noted = downloads.requests[0][2]
        check("the wait for a host's turn taken out of a request's time", noted < 0.1, noted)
        with http.drawing_downloads() as downloads:
            http.note_quote_seconds(0.25)
            http.note_quote_seconds(0.25)
        check("the quotes' seconds added up", downloads.quote_seconds == 0.5, downloads.quote_seconds)
    finally:
        with http._download_cache_lock:
            http._download_cache.clear()


class _Stand:
    """``web``'s drawing with its work stood in for: a chart takes ``seconds``, ``began`` lists the order they began in."""

    def __init__(self, seconds: float = 0.2) -> None:
        self.seconds = seconds
        self.began: list[str] = []
        self.gate: threading.Event | None = None
        self.saved = {name: getattr(web, name) for name in ("resolve_start", "build_figure", "png_bytes", "ChartGeometry")}
        self.chart_lines = web.hover.chart_lines

    def __enter__(self) -> _Stand:
        web.resolve_start = lambda config: config
        web.png_bytes = lambda figure: b"png"
        web.ChartGeometry = SimpleNamespace(from_figure=lambda figure, drawn: None)
        web.hover.chart_lines = lambda figure: None

        def build(country, drawn):
            self.began.append(f"{drawn.width_px}:{country.key}")
            if self.gate is not None:
                self.gate.wait(10)
            time.sleep(self.seconds)
            return object()

        web.build_figure = build
        return self

    def __exit__(self, *_exc: object) -> None:
        for name, value in self.saved.items():
            setattr(web, name, value)
        web.hover.chart_lines = self.chart_lines


def _config(width: int, *more: str):
    return parse_args(["--na:ca,us", "-s:2001", "--e:2019", f"--dim:{width}x900", *more])


def _until(condition, seconds: float = 10.0) -> bool:
    began = time.monotonic()
    while time.monotonic() - began < seconds:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _started(config) -> web._Job:
    """A job begun on its worker, as ``web._start_job`` does, without a page's session state."""
    job = web._new_job(config, ())
    with web._DRAWINGS_LOCK:
        web._DRAWINGS.append(job)
    threading.Thread(target=web._run_job, args=(job,), daemon=True).start()
    return job


def check_line_of_drawings(check) -> None:
    """The page's drawings."""
    with _Stand(0.05) as stand:
        stand.gate = threading.Event()
        first = _started(_config(1000))
        check("the first begins", _until(lambda: stand.began == ["1000:cdn"]), stand.began)
        second = _started(_config(1100))
        third = _started(_config(1200))
        check("three in the line, in the order asked", web._DRAWINGS == [first, second, third])
        time.sleep(0.15)
        check("the second and third wait", stand.began == ["1000:cdn"], stand.began)
        own = [each.wait.own_remaining() for each in (first, second, third)]
        check("what is ahead counted, each drawing once", abs(third.wait.remaining() - sum(own)) < 0.1 and abs(second.wait.remaining() - sum(own[:2])) < 0.1, (third.wait.remaining(), own))
        third.stopped.set()
        check("a stopped one leaves the line before its turn", _until(lambda: third.done.is_set()) and third not in web._DRAWINGS, web._DRAWINGS)
        stand.gate.set()
        check("the others end", _until(lambda: first.done.is_set() and second.done.is_set()))
        check("each drawn in turn, whole", stand.began == ["1000:cdn", "1000:us", "1100:cdn", "1100:us"], stand.began)
        check("the stopped one drew nothing", not third.drawing.pngs and third.drawing.drawn is None and third.drawing.error is None, third.drawing)
        check("the line is empty, the lock free", not web._DRAWINGS and not web._DRAWING_LOCK.locked())
        check("the first drawing's charts", sorted(first.drawing.pngs) == ["cdn", "us"], sorted(first.drawing.pngs))
        check("no wait of a second: no line in the first's log", "Waited" not in first.drawing.log, first.drawing.log)

    with _Stand(0.6) as stand:
        first = _started(_config(1000, "-c"))
        second = _started(_config(1100, "-c"))
        check("both end", _until(lambda: first.done.is_set() and second.done.is_set()))
        check("the message log names a wait of a second or more", first.drawing.seconds < 1.5 and "Waited" not in first.drawing.log, first.drawing.log)
    with _Stand(1.2) as stand:
        first = _started(_config(1000, "-c"))
        second = _started(_config(1100, "-c"))
        check("both end", _until(lambda: first.done.is_set() and second.done.is_set()))
        check("… “Waited 2 s for an earlier drawing.”", re.search(r"^Waited [12] s for an earlier drawing\.$", second.drawing.log, re.M), second.drawing.log)

    with _Stand(0.05) as stand:
        figures_before = web._FIGURES.to_saved()
        stand.gate = threading.Event()
        job = _started(_config(1000))
        check("a drawing under way", _until(lambda: stand.began == ["1000:cdn"]), stand.began)
        job.stopped.set()
        stand.gate.set()
        check("stopped: it ends", _until(lambda: job.done.is_set()))
        check("… between charts: the second not begun", stand.began == ["1000:cdn"], stand.began)
        check("… and it teaches nothing", web._FIGURES.to_saved() == figures_before)

    with _Stand(0.0):
        web.build_figure = lambda country, drawn: (_ for _ in ()).throw(ValueError("a chart that cannot be drawn"))
        job = _started(_config(1000, "-c"))
        check("a chart failing: named, the drawing ended", _until(lambda: job.done.is_set()) and "cdn" in job.drawing.failed, job.drawing)
        check("… and the line empty", not web._DRAWINGS and not web._DRAWING_LOCK.locked())


def main() -> int:
    results: list[bool] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        results.append(bool(condition))
        shown = f"  [{detail}]" if not condition and detail != "" else ""
        print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)

    # web's import turned the last good copies on in the person's own folder, where the made-up
    # requests of check_noted (a.example, b.example) were kept until batch 41.2: a folder of its own.
    temp_folders.begin(temp_folders.keep_asked())
    http.enable_last_good_copies(temp_folders.make("check_wait_copies"))
    for group in (check_words, check_figures, check_sum, check_steady, check_noted, check_line_of_drawings):
        print(f"-- {group.__doc__.splitlines()[0]}")
        try:
            group(check)
        except Exception as exc:  # the group stops; its failure is counted and shown
            check(f"{group.__name__} ran to its end", False, f"{type(exc).__name__}: {exc}")
    print(f"[wait] {sum(results)} of {len(results)} checks passed")
    temp_folders.end(failed=not all(results))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
