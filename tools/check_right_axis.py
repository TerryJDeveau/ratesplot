"""Batch 40: a right axis in its one series' colour, its title in the currency, the inflation curve's name, the note.

Each chart is drawn through ``plotting.build_figure`` from the regression set's downloads, and the axes read as drawn:

* 40.1: which right axis is coloured, on the title, tick labels, tick marks and spine alike, and which stays black: one
  series with others on the chart, the only series on it, two on the axis, a level, the index on the right axis and
  outside it, the population, --reg's pieces not counted; the left axis where it mirrors the right, and otherwise as it was;
* 40.5: the right axis's title under each measure, its currency named once and first, the axes not in a currency as they
  were;
* 40.4: the inflation curve's name in the legend, and a character the output's encoding lacks not stopping the program;
* 40.3: the note on a month with no index, on the charts that show one and no others.

    python tools/check_right_axis.py [--cache out/cache_b24s2]
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from matplotlib.colors import to_hex
from matplotlib.legend import Legend

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from regress_charts import PINNED_END, install_disk_cache  # noqa: E402

from ratesplot import cli, http  # noqa: E402
from ratesplot.config import MACRO_PLOT_STYLES  # noqa: E402
from ratesplot.console import this_thread_output_to, tolerant_output  # noqa: E402
from ratesplot.plotting import COUNTRIES, build_figure, resolve_start  # noqa: E402

BLACK = "#000000"
GDP, INTEREST, NET = (to_hex(MACRO_PLOT_STYLES[key]["color"]) for key in ("gdp", "interest", "net_debt"))
FEDERAL = to_hex(MACRO_PLOT_STYLES["debt_f"]["color"])
INDEX, POPULATION = to_hex("deeppink"), to_hex("darkgoldenrod")

# The command line, then the colours expected of the right axis and of the axis outside it (None: there is none).
COLOURS: dict[str, tuple[list[str], str, str | None]] = {
    "GDP and a yield": (["-u", "--gdp", "--yields:10"], GDP, None),
    "interest and a yield": (["-u", "--interest", "--yields:10"], INTEREST, None),
    "debt and a yield: black is its colour": (["-u", "--debt", "--yields:10"], BLACK, None),
    "GDP and the policy rate": (["-u", "--gdp", "--policy"], GDP, None),
    "GDP and inflation": (["-u", "--gdp", "--inflation"], GDP, None),
    "GDP alone on the chart": (["-u", "--gdp"], BLACK, None),
    "two on the axis": (["-u", "--gdp", "--debt"], BLACK, None),
    "three on the axis and a yield": (["-u", "--gdp", "--debt", "--interest", "--yields:10"], BLACK, None),
    "one level and a yield": (["-u", "--debt:f", "--yields:10"], FEDERAL, None),
    "two levels and a yield": (["-u", "--debt:fs", "--yields:10"], BLACK, None),
    "the UK's net debt and a yield": (["--nations:gb", "--aggregate:net", "--yields:10"], NET, None),
    "the UK's gross and net debt and a yield": (["--nations:gb", "--aggregate:gross,net", "--yields:10"], BLACK, None),
    "as % of GDP, interest and a yield": (["-u", "-r", "--interest", "--yields:10"], INTEREST, None),
    "--reg's pieces are not series": (["-u", "--gdp", "--yields:10", "--reg"], GDP, None),
    "the index on the right axis and a yield": (["-u", "--cpi", "--yields:10"], INDEX, None),
    "the index alone on the chart": (["-u", "--cpi"], BLACK, None),
    "GDP, and the index outside": (["-u", "--gdp", "--cpi"], GDP, INDEX),
    "two on the axis, and the index outside": (["-u", "--gdp", "--debt", "--cpi"], BLACK, INDEX),
    "debt, and the population outside": (["-u", "--debt", "--population"], BLACK, POPULATION),
}

# The charts whose left axis repeats a coloured right axis, having nothing of its own, and that colour.
MIRRORS = {"GDP, and the index outside": GDP}

# The command line, then the right axis's title.
TITLES: dict[str, tuple[list[str], str]] = {
    "U.S.": (["-u", "--debt"], "Nominal USD (Log Scale)"),
    "Canada": (["-c", "--debt"], "Nominal CAD (Log Scale)"),
    "the UK": (["--nations:gb", "--debt"], "Nominal GBP (Log Scale)"),
    "Germany": (["--nations:de", "--debt", "-s:2010"], "Nominal EUR (Log Scale)"),
    "per capita": (["-u", "--debt", "-p"], "Nominal USD per Capita (Log Scale)"),
    "inflation adjusted": (["-c", "--debt", "--constant"], "Inf. Adj. CAD at 2026-09 Prices (Log Scale)"),
    "inflation adjusted per capita": (["-c", "--debt", "--constant", "-p"], "Inf. Adj. CAD per Capita at 2026-09 Prices (Log Scale)"),
    "as % of GDP: no currency": (["-u", "--debt", "-r"], "Percent of TTM GDP (Log Scale)"),
}
MASTER_TITLES: dict[str, tuple[list[str], str, str]] = {
    "in a master currency": (["-c", "-u", "--debt", "--master:USD"], "Nominal USD (at ", " per CAD, 2026-09-01 – Log Scale)"),
    "per capita in a master currency": (["-c", "-u", "--debt", "-p", "--master:USD"], "Nominal USD per Capita (at ", " per CAD, 2026-09-01 – Log Scale)"),
    "inflation adjusted in a master currency": (["-c", "-u", "--debt", "--constant", "--master:USD"], "Inf. Adj. USD at 2026-09 Prices (at ", " per CAD, 2026-09-01 – Log Scale)"),
}

RISE_NOTE = ("  Note: no U.S. consumer price index for 2025-10: the Bureau of Labor Statistics collected no prices in the 2025 "
             "shutdown, so no 12-month rise for 2025-10 or 2026-10")
HOLD = "; the index's line holds 2025-09's across the month"
# The command line, then the note expected in full (None: no note).
NOTES: dict[str, tuple[list[str], str | None]] = {
    "the inflation curve over the month": (["-u", "--inflation", "-s:2025-01-01"], RISE_NOTE + "."),
    "the index over the month": (["-u", "--cpi", "-s:2025-01-01"], "  Note: no U.S. consumer price index for 2025-10: the Bureau of Labor Statistics collected no prices in the 2025 shutdown" + HOLD + "."),
    "both over the month": (["-u", "--inflation", "--cpi", "-s:2025-01-01"], RISE_NOTE + HOLD + "."),
    "the window inside the month": (["-u", "--inflation", "-s:2025-10-05", "--e:2025-10-20"], RISE_NOTE + "."),
    "the inflation curve before the month": (["-u", "--inflation", "-s:2024-01-01", "--e:2025-09-30"], None),
    "the inflation curve between the two": (["-u", "--inflation", "-s:2025-11-01", "--e:2026-09-30"], None),
    "the index a year on": (["-u", "--cpi", "-s:2026-10-01", "--e:2026-11-30"], None),
    "Canada's curve over the month": (["-c", "--inflation", "-s:2025-01-01"], None),
    "debt over the month": (["-u", "--debt", "-s:2025-01-01"], None),
}


def drawn(tokens: list[str]) -> tuple[dict, list[str]]:
    """The figures of a command line, with what its drawing printed."""
    printed: list[str] = []
    with this_thread_output_to(printed.append):
        config = resolve_start(cli.parse_args(["--no-gui", PINNED_END, *tokens]))
        figures = {country.key: build_figure(country, config) for country in COUNTRIES if getattr(config, country.show_field)}
    return figures, "".join(printed).splitlines()


def axis_colours(axes) -> set[str]:
    """Every colour the right axis ``axes`` is drawn in: its title, tick labels, tick marks and spine."""
    ticks = [*axes.yaxis.get_major_ticks(), *axes.yaxis.get_minor_ticks()]
    return {
        to_hex(axes.yaxis.label.get_color()),
        to_hex(axes.spines["right"].get_edgecolor()),
        *(to_hex(tick.label2.get_color()) for tick in ticks),
        *(to_hex(tick.tick2line.get_color()) for tick in ticks),
    }


def left_colours(figure) -> set[str]:
    """Every colour the left axis is drawn in: its title, tick labels, tick marks and the spine each twin draws there."""
    axes = figure.axes[0]
    ticks = [*axes.yaxis.get_major_ticks(), *axes.yaxis.get_minor_ticks()]
    return {
        to_hex(axes.yaxis.label.get_color()),
        *(to_hex(twin.spines["left"].get_edgecolor()) for twin in figure.axes),
        *(to_hex(tick.label1.get_color()) for tick in ticks),
        *(to_hex(tick.tick1line.get_color()) for tick in ticks),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, help="download cache folder (default out/download_cache)")
    args = parser.parse_args(argv)
    install_disk_cache(http, (args.cache or ROOT / "out" / "download_cache").resolve())
    failed: list[str] = []
    total = 0

    def check(name: str, ok: bool, detail: object = "") -> None:
        nonlocal total
        total += 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f": {detail}"))
        if not ok:
            failed.append(name)

    print("40.1: the axis's colour")
    for name, (tokens, right, outer) in COLOURS.items():
        figure = next(iter(drawn(tokens)[0].values()))
        check(f"{name}: the right axis", axis_colours(figure.axes[1]) == {right}, axis_colours(figure.axes[1]))
        if outer is None:
            check(f"{name}: no axis outside it", len(figure.axes) == 2, len(figure.axes))
        else:
            check(f"{name}: the axis outside it", len(figure.axes) == 3 and axis_colours(figure.axes[2]) == {outer}, axis_colours(figure.axes[-1]))
        left = MIRRORS.get(name, BLACK)
        check(f"{name}: the left axis {'mirrors it' if name in MIRRORS else 'as it was'}", left_colours(figure) == {left}, left_colours(figure))

    print("40.5: the right axis's title")
    for name, (tokens, title) in TITLES.items():
        label = next(iter(drawn(tokens)[0].values())).axes[1].get_ylabel()
        check(name, label == title, label)
    for name, (tokens, before, after) in MASTER_TITLES.items():
        label = drawn(tokens)[0]["cdn"].axes[1].get_ylabel()
        check(name, label.startswith(before) and label.endswith(after) and label.count("USD") == 1, label)
    index_label = drawn(["-u", "--cpi", "--yields:10"])[0]["us"].axes[1].get_ylabel()
    check("the price index's axis as it was", index_label == "Consumer Price Index (1982-84 = 100, Log Scale)", index_label)

    print("40.4: the inflation curve's name")
    legends = next(iter(drawn(["-u", "--inflation"])[0].values())).findobj(Legend)
    names = [text.get_text() for one in legends for text in one.get_texts()]
    check("in the legend", "Inflation (CPI, 12-month Δ%)" in names, names)
    raw = io.BytesIO()
    stand_in = io.TextIOWrapper(raw, encoding="cp1252")
    kept = sys.stdout
    sys.stdout = stand_in
    try:
        tolerant_output()
        print("Δ")
        stand_in.flush()
    except UnicodeEncodeError as exc:
        check("a pipe in cp1252 takes it", False, exc)
    else:
        check("a pipe in cp1252 takes it", raw.getvalue().startswith(b"?"), raw.getvalue())
    finally:
        sys.stdout = kept

    print("40.3: the note")
    for name, (tokens, note) in NOTES.items():
        lines = [line for line in drawn(tokens)[1] if "consumer price index for" in line]
        check(name, lines == ([] if note is None else [note]), lines)

    print(f"[right axis] {total - len(failed)} of {total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
