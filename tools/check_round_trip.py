#!/usr/bin/env python3
"""Check that the window's and the page's command line, and the web address the window writes, draw what the line they came from draws; offline, in seconds.

The window and the web page read a command line into their controls
(``frontend.starting_choices``) and write their controls back as a command
line (``options.command_line_tokens``): the one they show, and the page's
address. For each combination of nations and lists below, the written line
must draw the same charts (``options.drawn_config`` for each nation drawn)
as the line it came from. No data is fetched and nothing is drawn.

Found wanting on 2026-10-07: 91 of 192 combinations did not hold. A list of
which a nation could draw nothing (Canada's view of ``--yields:7,20``) was
read back as that nation's default; such a list was then written after a
nation's code, which the parser refuses; and a nation with its own default
(Germany's 2 5 10 30) had its list shortened to a removal counted from the
default for every chart. The last two were fixed first. The first was
Terry's to decide (2026-10-07: "plot no yields in that case, but issue a
warning message"): that nation's field now reads "none", as its chart draws
(``options.NONE_ITEM``), and every combination must hold.

Usage (from the project root)::

    python tools/check_round_trip.py

Exit code 1 if any combination does not hold.
"""

from __future__ import annotations

import itertools
import sys
import urllib.parse
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot.cli import sort_tokens  # noqa: E402
from ratesplot.config import NATIONS, WEB_PAGE_ADDRESS  # noqa: E402
from ratesplot.frontend import (  # noqa: E402
    ADDRESS_KEY, NATION_OPTIONS, chart_link, choice_values, choices_text, drawn_payloads, level_letters, level_text,
    starting_choices,
)
from ratesplot.options import command_line_tokens, config_from_choices, drawn_config, nation_choice  # noqa: E402

# The lists a nation may be left none of, and the flag that draws each.
_LISTS = {"yield_terms": "include_yield", "mortgage_terms": "mortgages", "spread_pairs": "spreads", "policy_terms": "policy_rates"}

# The nations drawn, and the lists and values given: for every chart, for
# one nation, both; lists some nation has none of; removals; limits.
NATION_SETS = ("-c", "-u", "-c -u", "--na:gb", "--na:de", "--na:ca,gb", "--na:us,de", "--na:ca,us,gb,de")
VALUES = (
    "", "--mo", "--sp", "--y:7,20", "--y:20", "--y:3m", "--y:1m,7", "--y:2,10", "--no-y:30", "--yields:3m,2,5,10,30",
    "--mo:30", "--mo:5", "--mo:svr", "--mo:1-5", "--mo:30,svr", "--mo:30,5",
    "--sp:10-3m", "--sp:20-5", "--sp:7-1m", "--sp:30-2", "--sp:7-1m,10-2", "--sp:10-2,10-3m,30-10",
    "--us:y:7 --y:20", "--cdn:y:2 --y:7", "--y:7,20 --uk:y:10", "--y:1,7 --cdn:y:3m --uk:y:5",
    "--us:no-y:30 --y:2,30", "--uk:no-y:20", "--ger:no-y:2 --us:y:1m",
    "--uk:mo:2f --mo:30", "--mo:15 --cdn:mo:prime --ger:mo:over10", "--y:20,30 --mo:svr,5-10",
    "--ger:sp:30-2 --sp:10-3m", "--sp:20-10 --cdn:sp:10-3m", "--sp:30-10 --us:sp:7-1m", "--y:7 --mo:15 --sp:7-1m",
    "--max:6 --us:max:8", "--uk:top:5t --ger:top:4t", "-r --uk:top:150%", "--d:fpm --y:7",
    # A nation's own list of none (2026-10-07), alone, with every nation's, and with a list for every chart.
    "--cdn:y:none", "--cdn:y:none --us:y:none", "--uk:y:none --y:7", "--ger:mo:none --mo", "--us:mo:none --mo:30,5",
    "--cdn:sp:none --sp:10-2", "--cdn:mo:none --us:mo:none --uk:mo:none --ger:mo:none --mo",
    # The prime margin (batch 9.4): for every chart, for one nation, with a list that leaves prime out.
    "--prime:0.5", "--cdn:prime:-0.25", "--us:prime:1 --mo:30,prime", "--mo:5 --prime:0.5", "--prime:0.5 --cdn:mo:5v",
    # A margin for every chart names its term on the charts that have it only: the UK keeps its own default (2026-10-21).
    "--nations:ca,gb --prime:0.5",
    # The UK tracker's margin (batch 9.5): for every chart, for the UK, with a list that leaves it out, beside --prime.
    "--nations:gb --tracker:1.25", "--nations:gb --uk:mo:svr,tracker --uk:tracker:0.5", "--nations:gb --mo:svr --tracker:1",
    "--nations:ca,gb --prime:0.5 --uk:tracker:2",
    # The policy terms (batch 9.1): for every chart, for one nation, a nation's own none.
    "--po", "--po:market", "--po:target,market", "--us:po:market", "--po:market --cdn:po:target,market",
    "--uk:po:none --po", "--po:target --ger:po:market --mo",
    # The aggregate debts (batch 10.4): for every chart, for the UK, both; with the levels and
    # without debt, where they draw nothing; with a measure.
    "--agg:gross,net", "--agg:net", "--uk:agg:net", "--uk:agg:gross,net --agg:net", "--agg:net --d:f",
    "--agg:net --no-debt", "--uk:agg:net -r",
    # The levels for one nation (batch 10.5): alone, beside those for every chart, by --interest, the UK's
    # "n" and its missing "p", with a curve given.
    "--cdn:d:fp", "--d:fp --uk:d:f", "--d:fn", "--us:i:f --d:fpm", "--ger:d:pm --uk:d:fn", "--d:p",
    "--cdn:d:fp --gdp", "--d:fp --cdn:i:f",
    # Top and Bottom in a currency (batch 18.3): for every chart, for one nation, a nation's own currency, two
    # currencies, per capita, a symbol typed.
    "--top:USD20t", "--top:EUR2t --bottom:EUR50b", "--cdn:top:USD20t", "--us:top:USD20t", "--top:USD5t --bottom:CAD1t",
    "-p --top:GBP100k", "--uk:top:C$3t --ger:bottom:£40b",
    # The automatic refresh (batch 11.3): on, with its minutes, and greyed (its minutes then left off).
    "--au", "--au:10", "--au:10 --no-cur", "--au:10 -e:2026-09-01", "--au:15 --no-y --sp", "--au:20 --cdn:y:none",
)


def round_trip(line: list[str]) -> tuple[list[str], list[str]] | None:
    """Return (the written line, the nations it draws otherwise), or None for a line the parser refuses.

    Written twice: from the fields as the window keeps them, and from the
    fields as the page rebuilds each list from its ticked boxes
    (``through_boxes``); both must draw what the line drew. Each is also
    written as the chart's web address, as the window writes it under its
    command line (batch 31.3, ``frontend.chart_link`` on
    ``config.WEB_PAGE_ADDRESS``), and read back as the page reads its
    address (``page_reads``), which must draw the same. The written line
    returned is the page's where they differ.
    """
    payloads, flags, unmatched, misspelled = sort_tokens(line)
    if unmatched or misspelled:
        return None
    try:
        config = config_from_choices(payloads, flags)
    except ValueError:
        return None
    (choice_payloads, choice_flags), _notes = starting_choices(config, payloads, flags, {})
    differ: list[str] = []
    for fields in (choice_payloads, through_boxes(choice_payloads)):
        written = command_line_tokens(fields, choice_flags)
        try:
            again = config_from_choices(*sort_tokens(written)[:2])
        except ValueError as exc:
            return written, [f"refused: {exc}"]
        linked, problems = page_reads(chart_link(WEB_PAGE_ADDRESS, written))
        if linked is None:
            return written, [f"its web address refused: {'; '.join(problems)}"]
        for read in (again, linked):
            differ += [
                nation.key for nation in NATIONS
                if (getattr(config, nation.show_field) != getattr(read, nation.show_field)
                    or (getattr(config, nation.show_field) and _drawn(config, nation.key) != _drawn(read, nation.key)))
                and nation.key not in differ
            ]
    return written, differ


def page_reads(link: str):
    """The PlotConfig the page draws for ``link``: its ``?chart=`` read as Streamlit gives the page its query, then as the page reads it.

    ``web._choices_from_line`` gives the controls, from which the page draws
    with its greyed fields set aside (``frontend.drawn_payloads``), as
    ``web._config_for`` does. (None, problems) where the page refuses it.
    """
    from ratesplot import web  # here: it brings Streamlit, which the rest of this check does without

    text = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query, keep_blank_values=True)[ADDRESS_KEY][0]
    choices, problems = web._choices_from_line(text)
    if choices is None:
        return None, problems
    return config_from_choices(drawn_payloads(*choices), choices[1]), []


def through_boxes(payloads: dict[str, str]) -> dict[str, str]:
    """Return ``payloads`` with each nation's list as the page's boxes give it back: the items ticked, "none" for none.

    The levels too (batch 10.5): the letters of the nation's boxes ticked, a
    synonym as the box it ticks (the UK's "n" as "m").
    """
    boxed = dict(payloads)
    for option in NATION_OPTIONS:
        for nation in NATIONS:
            key = nation_choice(nation, option)
            if option.editor == "choices":
                boxed[key] = choices_text(option, choice_values(option, payloads[key], nation))
            elif option.editor == "levels":
                letters = level_letters(payloads[key], nation)
                boxed[key] = level_text([letter for letter, _caption in nation.level_boxes if letter in letters])
    return boxed


def _drawn(config, key: str):
    """``drawn_config`` for one nation, with each list whose curves are off set aside (it draws nothing either way)."""
    drawn = drawn_config(config, key)
    hidden = {field: None for field, flag in _LISTS.items() if not getattr(drawn, flag)}
    if drawn.refresh_brings_nothing is not None:
        hidden["auto_refresh_minutes"] = None  # greyed, its minutes left off the written line (batch 11.3)
    return replace(drawn, **hidden) if hidden else drawn


def main() -> int:
    checked, failed = 0, 0
    for nations, values in itertools.product(NATION_SETS, VALUES):
        line = f"{nations} {values}".split()
        result = round_trip(line)
        if result is None:
            continue
        checked += 1
        written, differ = result
        if differ:
            failed += 1
            print(f"FAIL {' '.join(line)}  ->  {' '.join(written)}  [{', '.join(differ)}]")
    print(f"[round trip] {checked - failed} of {checked} command lines come back drawing the same charts; {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
