#!/usr/bin/env python3
"""Check the help beside each control (batch 29.1, decision 76) where no window is needed.

* every control the window and the page show (``Option.in_gui``) has a
  short text, the option's own ``help``, which its ⓘ panel and its "?" tip
  show;
* every topic an option names (``Option.topic``) has its file,
  ``docs/help/TOPIC.md``, and every file there is named by an option;
* each topic reads as the window renders it (``frontend.help_blocks``): a
  heading first, every link to an http(s) address; a name no option gives is
  refused (``frontend.help_text``), as the page's address may hold anything;
* ``frontend.greyed_reason`` gives a reason exactly where the window greys a
  control (the rule of ``gui._update_dependent_controls`` and
  ``gui._update_auto_refresh``, which the page follows), for every control of
  every nation, over every combination of the switches that grey things and
  a few fields that do; and ``frontend.all_tick_reason`` exactly where an
  "All" box is greyed (``all_tick_offered``).

The reasons are given by the same rules that grey (``options.idle_option_reasons``
and the rest), so the last check guards the one place they could part: a
control greyed by a rule that gives no reason, or the other way round.

No network, no window. The ⓘ panels and More are checked in the window by
``tools/verify_gui.py`` (group ``batch291``), the tips and the help view on
the page by ``tools/verify_web.py``.

Usage (from the project root)::

    python tools/check_help.py

Exit code 1 on any FAIL.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ratesplot.config import NATIONS, PlotConfig  # noqa: E402
from ratesplot.frontend import (  # noqa: E402
    ALL_TICKS,
    GREYABLE_OPTIONS,
    HELP_DIR,
    all_tick_offered,
    all_tick_reason,
    greyed_line,
    greyed_reason,
    greyed_reasons,
    help_blocks,
    help_text,
    help_topics,
    idle_choices,
    idle_nation_keys,
    option_of,
)
from ratesplot.options import OPTIONS, Kind, by_name, choices_from_config, nation_choice  # noqa: E402

results: list[bool] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    results.append(bool(condition))
    shown = f"  [{detail}]" if not condition or detail else ""
    print(f"{'ok  ' if condition else 'FAIL'} {label}{shown}", flush=True)


def greyed_in_window(key: str, payloads: dict[str, str], flags: dict[str, bool], idle: frozenset[str], nations: frozenset[str]) -> bool:
    """Whether the window greys control ``key``: its rule (``gui._update_dependent_controls``, ``gui._update_auto_refresh``), written out again."""
    option = option_of(key)
    if option.kind is not Kind.VALUE:
        return option.name in GREYABLE_OPTIONS and option.name in idle
    if option.turns_on not in flags and option.name not in GREYABLE_OPTIONS:
        return False
    off = option.turns_on in flags and not flags[option.turns_on]
    return off or option.name in idle or key in nations


def check_texts() -> None:
    """Every control has a short text."""
    print("-- the short texts")
    shown = [option for option in OPTIONS if option.in_gui]
    without = [option.name for option in shown if not " ".join(option.help.split())]
    check(f"each of the {len(shown)} controls has a short text", not without, without)


def check_topics() -> None:
    """Each topic named has its file, each file is named, each reads as the window renders it."""
    print("-- the topics")
    topics = help_topics()
    check("at least one topic named", bool(topics), sorted(topics))
    files = {path.stem for path in HELP_DIR.glob("*.md")}
    check("every topic named has its file in docs/help", set(topics) <= files, sorted(set(topics) - files))
    check("every file in docs/help is named by an option", files <= set(topics), sorted(files - set(topics)))
    for topic, named in topics.items():
        blocks = help_blocks(help_text(topic))
        check(f"{topic} (named by {', '.join(option.name for option in named)}): opens with a heading",
              bool(blocks) and blocks[0].kind == "heading" and blocks[0].level == 1, blocks[0] if blocks else None)
        links = [span.url for block in blocks for span in block.spans if span.style == "link"]
        bad = [url for url in links if not url.startswith(("https://", "http://"))]
        check(f"{topic}: its {len(links)} links all to http(s) addresses", not bad, bad)
    for name in ("../README", "nonsense", ""):
        try:
            help_text(name)
            refused = False
        except KeyError:
            refused = True
        check(f"a topic no option names is refused: {name!r}", refused)


def check_reasons() -> None:
    """A reason exactly where the window greys, over the switches and fields that grey things."""
    print("-- the reasons against the greying")
    base_payloads, base_flags = choices_from_config(PlotConfig())
    switches = ("debt", "gdp", "interest", "relative", "yield", "mortgages", "spreads", "policy", "regression", "current", "auto-refresh")
    first_level = {nation.key: nation.level_boxes[0][0] for nation in NATIONS if nation.level_boxes}
    variants = {
        "the defaults": {},
        "End before today": {"end": "2020-01-01"},
        "levels for every nation, Canada's terms without prime": {
            **{nation_choice(nation, by_name("debt-parts")): letter for nation in NATIONS for key, letter in first_level.items() if key == nation.key},
            nation_choice(next(nation for nation in NATIONS if nation.key == "cdn"), by_name("mortgage-terms")): "5",
        },
    }
    keys = [key for key in (*base_payloads, *base_flags) if key not in ALL_TICKS]
    combinations = disagreements = greyed_seen = 0
    first_disagreement = None
    for (name, fields), states in itertools.product(variants.items(), itertools.product((False, True), repeat=len(switches))):
        flags = {**base_flags, **dict(zip(switches, states))}
        if flags["relative"] and flags.get("per-capita"):
            continue
        payloads = {**base_payloads, **fields}
        idle, nations = idle_choices(payloads, flags), idle_nation_keys(payloads, flags)
        reasons = greyed_reasons(keys, payloads, flags)
        combinations += 1
        for key in keys:
            greyed = greyed_in_window(key, payloads, flags, idle, nations)
            greyed_seen += greyed
            if greyed != bool(reasons.get(key)):
                disagreements += 1
                first_disagreement = first_disagreement or (name, key, greyed, reasons.get(key), {s: flags[s] for s in switches})
    check(f"{combinations} combinations, {len(keys)} controls each ({greyed_seen} greyed): a reason exactly where greyed",
          disagreements == 0, first_disagreement)
    check("greyed_reason agrees with greyed_reasons", greyed_reason("relative", base_payloads, {**base_flags, "debt": False, "interest": False})
          == "it acts on debt and interest, and neither is ticked")
    check("the line a greyed control's help gains", greyed_line("“Bond yields” is unticked") == "Greyed because “Bond yields” is unticked.")


def check_all_ticks() -> None:
    """The "All" boxes: a reason exactly where one is greyed."""
    print("-- the \"All\" boxes")
    us = next(nation for nation in NATIONS if nation.key == "us")
    two = {"cdn": True, "us": True}
    cases = {
        "a value, two nations": ({nation_choice(us, by_name("max")): "8"}, two, ""),
        "a blank box": ({}, two, "the Max box is blank"),
        "a text the box refuses": ({nation_choice(us, by_name("max")): "eight"}, two, "the Max box's text is not a value it takes"),
        "one nation": ({nation_choice(us, by_name("max")): "8"}, {"us": True}, "only one nation is ticked"),
        "Top with no right-axis curve": ({nation_choice(us, by_name("top")): "20t"}, {**two, "debt": False, "gdp": False, "interest": False},
                                         "it acts on the right axis's curves, and none of debt, GDP and interest is ticked"),
    }
    for label, (payloads, flags, expected) in cases.items():
        key = next(iter(payloads), nation_choice(us, by_name("max")))
        reason = all_tick_reason(payloads, flags, key)
        check(f"{label}: {expected or 'offered'}", reason == expected and all_tick_offered(payloads, flags, key) == (not expected), reason)


def main() -> int:
    check_texts()
    check_topics()
    check_reasons()
    check_all_ticks()
    failed = results.count(False)
    print(f"\n{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
