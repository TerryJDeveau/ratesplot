#!/usr/bin/env python3
"""Count what the --reg rate labels cover, chart by chart, to measure a change to their placement.

Each case is drawn as ``regress_charts.py`` draws it (``--e:2026-09-01`` first,
the regression download cache), through ``plotting.build_figure``. Then each
rate label ("+5.3%/yr") is found among the drawn texts and its area rebuilt
from the text itself: the rectangle beside its anchor, turned to lie along its
piece, halo included, as ``regression.add_rate_labels`` scores it. In the
occupancy raster's 4 px cells it counts, for every label:

    lines    cells of a curve under the label (the curves only, not the bands)
    bands    cells of another curve's regression band under the label (the band's whole width)
    labels   cells it shares with another label: a rate label, or an -l value label

and for every chart the pairs of labels that touch. Because the areas are
rebuilt from the drawn texts, any version of the placement is measured the
same way (``--commit`` and ``--root`` as in ``regress_charts.py``).

Usage (from the project root)::

    python tools/check_reg_labels.py                       # the --reg cases of the regression set
    python tools/check_reg_labels.py --commit main --json out/labels_before.json
    python tools/check_reg_labels.py --json out/labels_after.json --compare out/labels_before.json
    python tools/check_reg_labels.py --only u_reg_lv1950
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import regress_charts  # noqa: E402  (this tool's own copy: the cases and the cache, whatever tree is drawn)

RATE_TEXT = re.compile(r"^(?:[+\N{MINUS SIGN}]\d+(?:\.\d)?|0\.0)%/yr$")
BAND_LABEL = "_regression"
# The label's area is sampled this finely (display pixels), as add_rate_labels samples it.
SAMPLE_PX = 2.0


def label_area(text, renderer) -> np.ndarray:
    """Points filling a rate label's rectangle, halo included, in display coordinates."""
    angle = math.radians(text.get_rotation())
    along = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-along[1], along[0]])
    # The text's own width and height, measured unturned (as add_rate_labels measures it).
    rotation = text.get_rotation()
    text.set_rotation(0)
    size = text.get_window_extent(renderer)
    text.set_rotation(rotation)
    halo = 0.0
    for effect in text.get_path_effects():
        halo = max(halo, getattr(effect, "_gc", {}).get("linewidth", 0.0) * text.figure.dpi / 72.0 / 2)
    width, height = size.width + 2 * halo, size.height + 2 * halo
    anchor = text.axes.transData.transform(text.xy) + np.asarray(text.xyann) * text.figure.dpi / 72.0
    up = normal if text.get_va() == "bottom" else -normal
    s = np.linspace(-width / 2, width / 2, max(2, math.ceil(width / SAMPLE_PX) + 1))
    t = np.linspace(0.0, height, max(2, math.ceil(height / SAMPLE_PX) + 1))
    return (anchor + s[:, None, None] * along + t[None, :, None] * up).reshape(-1, 2)


def band_area(line, ax) -> np.ndarray:
    """Points filling a regression band (a thick straight line) in display coordinates."""
    start, end = ax.transData.transform(np.asarray(line.get_xydata(), dtype=float))
    length = float(np.hypot(*(end - start)))
    if length == 0:
        return start[None, :]
    along = (end - start) / length
    normal = np.array([-along[1], along[0]])
    half = line.get_linewidth() * ax.figure.dpi / 72.0 / 2
    s = np.linspace(0, length, max(2, math.ceil(length / SAMPLE_PX) + 1))
    t = np.linspace(-half, half, max(2, math.ceil(2 * half / SAMPLE_PX) + 1))
    return (start + s[:, None, None] * along + t[None, :, None] * normal).reshape(-1, 2)


def cell_set(raster, points: np.ndarray) -> set[tuple[int, int]]:
    cells, inside = raster.cells_at(points)
    return {(int(r), int(c)) for r, c in cells[inside]}


def measure(figure, occupancy) -> dict:
    """The counts for one drawn chart."""
    renderer = figure.canvas.get_renderer()
    ax = figure.axes[0]
    bands = [(line, axis) for axis in figure.axes for line in axis.get_lines() if line.get_label() == BAND_LABEL]
    curves = occupancy.collect_display_samples(ax, exclude=[line for line, _axis in bands])
    raster = occupancy.Raster.from_axes(ax, curves)
    curve_cells = {(int(r), int(c)) for r, c in zip(*np.nonzero(raster.cells))}
    band_cells = [cell_set(raster, band_area(line, axis)) for line, axis in bands]
    band_ends = [axis.transData.transform(np.asarray(line.get_xydata(), dtype=float)) for line, axis in bands]

    rates, others = [], []
    for axis in figure.axes:
        for text in axis.texts:
            if not text.get_visible() or not text.get_text():
                continue
            if RATE_TEXT.match(text.get_text()):
                rates.append(text)
            else:
                others.append(cell_set(raster, _box_points(text.get_window_extent(renderer))))
    labels = []
    for text in rates:
        cells = cell_set(raster, label_area(text, renderer))
        point = text.axes.transData.transform(text.xy)
        own = _own_band(point, band_ends)
        covered = set().union(*(c for i, c in enumerate(band_cells) if i != own)) if band_cells else set()
        labels.append({"text": text.get_text(), "cells": cells, "lines": len(cells & curve_cells), "bands": len(cells & covered)})
    pairs = 0
    shared = 0
    for i, first in enumerate(labels):
        overlap = sum(len(first["cells"] & other) for other in others)
        for second in labels[i + 1 :]:
            common = len(first["cells"] & second["cells"])
            if common:
                pairs += 1
                overlap += common
        first["labels"] = overlap
        shared += overlap
    return {
        "labels": len(labels),
        "lines": sum(item["lines"] for item in labels),
        "bands": sum(item["bands"] for item in labels),
        "label_cells": shared,
        "touching_pairs": pairs,
        "on_band": sum(1 for item in labels if item["bands"] > 0),
        "on_label": sum(1 for item in labels if item["labels"] > 0),
    }


def _box_points(box) -> np.ndarray:
    xs = np.arange(box.x0, box.x1 + SAMPLE_PX, SAMPLE_PX)
    ys = np.arange(box.y0, box.y1 + SAMPLE_PX, SAMPLE_PX)
    return np.stack(np.meshgrid(xs, ys), axis=-1).reshape(-1, 2)


def _own_band(point: np.ndarray, band_ends: list[np.ndarray]) -> int:
    """The band whose centre line passes nearest ``point`` (a label's anchor lies on its own piece)."""
    best, best_distance = -1, math.inf
    for index, (start, end) in enumerate(band_ends):
        segment = end - start
        span = float(segment @ segment)
        fraction = 0.0 if span == 0 else min(1.0, max(0.0, float((point - start) @ segment) / span))
        distance = float(np.hypot(*(start + fraction * segment - point)))
        if distance < best_distance:
            best, best_distance = index, distance
    return best


KEYS = ("labels", "lines", "bands", "label_cells", "touching_pairs", "on_band", "on_label")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--commit", help="draw from this git revision (exported, working tree untouched)")
    source.add_argument("--root", type=Path, help="draw from this project tree")
    parser.add_argument("--only", help="comma-separated case names (default: every case with --reg)")
    parser.add_argument("--json", type=Path, help="write the counts here")
    parser.add_argument("--compare", type=Path, help="an earlier --json file to set beside these counts")
    args = parser.parse_args(argv)

    cases = (
        {name: regress_charts.CASES[name] for name in args.only.split(",")}
        if args.only
        else {name: case for name, case in regress_charts.CASES.items() if any(token.startswith("--reg") for token in case)}
    )
    tree = regress_charts.export_commit(args.commit) if args.commit else (args.root.resolve() if args.root else ROOT)
    sys.path.insert(0, str(tree))
    http = importlib.import_module("ratesplot.http")
    plotting = importlib.import_module("ratesplot.plotting")
    occupancy = importlib.import_module("ratesplot.occupancy")
    cli = importlib.import_module("ratesplot.cli")
    regress_charts.install_disk_cache(http, ROOT / "out" / "download_cache")
    earlier = json.loads(args.compare.read_text()) if args.compare else {}

    results: dict[str, dict] = {}
    totals = dict.fromkeys(KEYS, 0)
    before_totals = dict.fromkeys(KEYS, 0)
    print(f"[labels] {len(cases)} case(s) from {tree}")
    print(f"{'chart':22} " + " ".join(f"{key:>14}" for key in KEYS))
    for name, case in cases.items():
        with contextlib.redirect_stdout(io.StringIO()):
            config = plotting.resolve_start(cli.parse_args([regress_charts.PINNED_END, *case, "--no-gui"]))
            figures = [
                (country.key, plotting.build_figure(country, config))
                for country in plotting.COUNTRIES
                if getattr(config, country.show_field)
            ]
        for key, figure in figures:
            chart = f"{name}/{key}"
            counts = measure(figure, occupancy)
            results[chart] = counts
            row = []
            for item in KEYS:
                totals[item] += counts[item]
                cell = f"{counts[item]}"
                if chart in earlier:
                    before_totals[item] += earlier[chart][item]
                    cell = f"{earlier[chart][item]}->{counts[item]}"
                row.append(f"{cell:>14}")
            print(f"{chart:22} " + " ".join(row))
    if earlier:
        print(f"{'TOTAL':22} " + " ".join(f"{before_totals[key]}->{totals[key]}".rjust(14) for key in KEYS))
    else:
        print(f"{'TOTAL':22} " + " ".join(f"{totals[key]:>14}" for key in KEYS))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
