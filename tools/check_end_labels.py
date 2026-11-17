#!/usr/bin/env python3
"""Count the -l end labels that lie across another curve, chart by chart, to measure a change to their placement.

Batch 47.2 (Terry, 2026-11-17: "Some of the “last value” label still overwrite
other series plot lines when a leader line could easily avoid it"). Each case of
the regression set with -l is drawn as ``regress_charts.py`` draws it
(``--e:2026-09-01`` first, the regression download cache), through each chart's
``build_figure`` (the comparison chart's too, where the tree drawn has it). Then
each end label is found among the drawn texts (an annotation on a white
background, not a regression segment's "%/yr") and its background tested
against every line of the figure not of its colour (its own curve's pieces),
sampled along each stroke as it is drawn: stepped as its drawstyle steps,
broken at its gaps. A line within 1.5 px of the background counts.

The test is this tool's own copy of ``endlabels._Ink``'s, so that any version
of the placement is measured the same way (``--commit`` and ``--root`` as in
``regress_charts.py``): a label the program moves off a curve should count
here as clear, and one it leaves should count as covering.

Usage (from the project root)::

    python tools/check_end_labels.py --commit main --json out/end_labels_before.json
    python tools/check_end_labels.py --json out/end_labels_after.json --compare out/end_labels_before.json
    python tools/check_end_labels.py --only us_pol_inf_l
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
from matplotlib.cbook import STEP_LOOKUP_MAP  # noqa: E402
from matplotlib.colors import same_color, to_rgba  # noqa: E402
from matplotlib.text import Annotation  # noqa: E402

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import regress_charts  # noqa: E402  (this tool's own copy: the cases and the cache, whatever tree is drawn)

RATE_TEXT = re.compile(r"%/yr$")
LABEL_TOKENS = ("-l", "--L", "--label", "--labels")
SPACING_PX = 2.0
CLEARANCE_PX = 1.5


def stroke_samples(line, axis) -> np.ndarray:
    """Points along a line's stroke as drawn, SPACING_PX apart, in display pixels (endlabels._stroke_samples's way)."""
    xy = np.asarray(line.get_xydata(), dtype=float)
    if not len(xy):
        return np.empty((0, 2))
    try:
        display = axis.transData.transform(xy)
    except Exception:  # noqa: BLE001
        return np.empty((0, 2))
    finite = np.isfinite(display).all(axis=1)
    if line.get_linestyle() in ("None", "", " ", "none"):
        return display[finite]
    step = STEP_LOOKUP_MAP.get(line.get_drawstyle(), STEP_LOOKUP_MAP["default"])
    parts = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], finite.astype(int), [0]])))
    for start, stop in zip(edges[::2], edges[1::2]):
        run = display[start:stop]
        if len(run) < 2:
            parts.append(run)
            continue
        xs, ys = step(run[:, 0], run[:, 1])
        stroke = np.column_stack([xs, ys])
        deltas = np.diff(stroke, axis=0)
        counts = np.maximum(1, (np.hypot(deltas[:, 0], deltas[:, 1]) / SPACING_PX).astype(int))
        segment = np.repeat(np.arange(len(counts)), counts)
        k = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
        parts.append(stroke[:-1][segment] + (k / counts[segment])[:, None] * deltas[segment])
        parts.append(stroke[-1:])
    return np.concatenate(parts) if parts else np.empty((0, 2))


def measure(figure) -> list[dict]:
    """Each end label of ``figure``: its text, and whether it covers a line not of its colour (and which colours)."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    lines = []
    for axis in figure.axes:
        if not axis.get_visible():
            continue
        for line in axis.get_lines():
            if line.get_visible() and line.get_alpha() != 0:
                samples = stroke_samples(line, axis)
                if len(samples):
                    lines.append((line.get_color(), line.get_label(), samples))
    found = []
    for axis in figure.axes:
        for text in axis.texts:
            patch = text.get_bbox_patch() if isinstance(text, Annotation) else None
            if patch is None or RATE_TEXT.search(text.get_text()) or to_rgba(patch.get_facecolor())[:3] != (1.0, 1.0, 1.0):
                continue
            box = patch.get_window_extent(renderer)
            colour = text.get_color()
            covered = []
            for line_colour, name, samples in lines:
                if same_color(line_colour, colour):
                    continue
                x, y = samples[:, 0], samples[:, 1]
                if ((x >= box.x0 - CLEARANCE_PX) & (x <= box.x1 + CLEARANCE_PX)
                        & (y >= box.y0 - CLEARANCE_PX) & (y <= box.y1 + CLEARANCE_PX)).any():
                    covered.append(name)
            found.append({"text": text.get_text(), "covers": sorted(set(covered)),
                          "leader": text.arrow_patch is not None})
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--commit", help="draw from this git revision (exported, working tree untouched)")
    source.add_argument("--root", type=Path, help="draw from this project tree")
    parser.add_argument("--only", help="comma-separated case names (default: every case with -l)")
    parser.add_argument("--cache", type=Path, help="download cache folder (default out/download_cache)")
    parser.add_argument("--json", type=Path, help="write the findings here")
    parser.add_argument("--compare", type=Path, help="an earlier --json file to set beside these")
    args = parser.parse_args(argv)

    cases = (
        {name: regress_charts.CASES[name] for name in args.only.split(",")}
        if args.only
        else {name: case for name, case in regress_charts.CASES.items() if any(token in LABEL_TOKENS for token in case)}
    )
    tree = regress_charts.export_commit(args.commit) if args.commit else (args.root.resolve() if args.root else ROOT)
    sys.path.insert(0, str(tree))
    http = importlib.import_module("ratesplot.http")
    plotting = importlib.import_module("ratesplot.plotting")
    cli = importlib.import_module("ratesplot.cli")
    try:  # the comparison chart (batch 26), where the tree drawn has it
        compare = importlib.import_module("ratesplot.compare")
        charts, build = compare.CHARTS, compare.build_chart
    except ImportError:
        charts, build = plotting.COUNTRIES, plotting.build_figure
    regress_charts.install_disk_cache(http, args.cache or ROOT / "out" / "download_cache")
    earlier = json.loads(args.compare.read_text(encoding="utf-8")) if args.compare else {}

    results: dict[str, list[dict]] = {}
    labels = covering = leaders = 0
    print(f"[end labels] {len(cases)} case(s) from {tree}")
    for name, case in cases.items():
        with contextlib.redirect_stdout(io.StringIO()):
            config = plotting.resolve_start(cli.parse_args([regress_charts.PINNED_END, *case, "--no-gui"]))
            figures = [(chart.key, build(chart, config)) for chart in charts if getattr(config, chart.show_field)]
        for key, figure in figures:
            chart = f"{name}/{key}"
            found = measure(figure)
            results[chart] = found
            labels += len(found)
            covering += sum(1 for item in found if item["covers"])
            leaders += sum(1 for item in found if item["leader"])
            before = [item["text"] for item in earlier.get(chart, []) if item["covers"]]
            now = [f"{item['text']} over {', '.join(item['covers'])}" for item in found if item["covers"]]
            if now or before:
                print(f"{chart:26} covering now: {now or 'none'}" + (f"   before: {before}" if earlier else ""))
    if earlier:
        before_labels = sum(len(found) for found in earlier.values())
        before_covering = sum(1 for found in earlier.values() for item in found if item["covers"])
        before_charts = sum(1 for found in earlier.values() if any(item["covers"] for item in found))
        print(f"[end labels] before: {before_labels} labels, {before_covering} covering another curve on {before_charts} charts")
    now_charts = sum(1 for found in results.values() if any(item["covers"] for item in found))
    print(f"[end labels] now: {labels} labels on {len(results)} charts, {covering} covering another curve on {now_charts} charts, "
          f"{leaders} with a leader")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
