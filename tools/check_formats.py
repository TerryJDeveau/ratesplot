#!/usr/bin/env python3
"""Check the amounts' and percentages' formatters (``axes.format_currency``, ``format_population``, ``format_percent``), 8.18.

Never in exponent form: ``.3g`` alone wrote "+C$1e+03K" in the read-out for a change that rounds to 1,000 of its unit,
and "−C$1.04e-06" for a day's change of a debt per person in 1867. So, with no network:

* the examples in their docstrings and the boundaries: a figure that rounds to 1,000 of its unit is 1 of the next
  ("$1M"), from 1,000T whole trillions comma-grouped, below 0.0001 plain decimals to three figures, 1,000% and up whole;
* a sweep from 1e-9 to 1e16, either side of each unit's boundary: no exponent, and the text read back within half of
  its third figure of the value (whole trillions from 1,000T, whole percent from 1,000%);
* the same sweep against 8.17's formatters, kept here: the same text wherever 8.17's had no exponent;
* a figure below zero: its size's text with a hyphen first.

    python tools/check_formats.py

Exit status 0 only if every check passes.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ratesplot.axes import format_currency, format_percent, format_population  # noqa: E402

_EXPONENT = re.compile(r"\de[+-]?\d")
_UNITS = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3, "": 1.0}


def _currency_817(value: float, prefix: str = "$") -> str:
    """8.17's ``format_currency``, word for word: the texts 8.18 must keep."""
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= scale:
            return f"{prefix}{value / scale:.3g}{suffix}"
    return f"{prefix}{value:.3g}"


def _percent_817(value: float) -> str:
    """8.17's ``format_percent``, word for word."""
    return f"{value:,.0f}%" if value >= 1000 else f"{value:.3g}%"


def _read_currency(text: str, prefix: str) -> float:
    """A text of ``format_currency`` read back as a figure: "C$1.5T" to 1.5e12."""
    assert text.startswith(prefix), text
    body = text[len(prefix):]
    unit = body[-1] if body[-1:] in "TBMK" else ""
    return float(body[: len(body) - len(unit)].replace(",", "")) * _UNITS[unit]


def _allowed(value: float, whole_from: float, step: float) -> float:
    """How far a three-figure text may be from ``value``: half of its third figure; from ``whole_from``, half of ``step``."""
    if value >= whole_from:
        return step / 2.0 * (1.0 + 1e-9)
    return 0.5 * 10.0 ** (math.floor(math.log10(value)) - 2) * (1.0 + 1e-9)


def _sweep() -> list[float]:
    """Figures from 1e-9 to 1e16, either side of each power of ten (each unit's boundary among them)."""
    mantissas = (1.0, 1.04, 1.234, 2.5, 4.999, 5.0, 9.99, 9.994, 9.995, 9.996, 9.9994, 9.9996, 9.99999)
    return [mantissa * 10.0 ** exponent for exponent in range(-9, 17) for mantissa in mantissas]


def main() -> int:
    results: list[bool] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        results.append(bool(ok))
        if not ok:
            print(f"  FAIL {name}: {detail}")

    # The examples and the boundaries.
    for value, prefix, expected in (
        (2e9, "$", "$2B"), (1.5e12, "$", "$1.5T"), (1.6e10, "$", "$16B"), (0.0, "$", "$0"), (999.4, "$", "$999"),
        (999.5, "$", "$1K"), (999.6, "C$", "C$1K"), (999_499.0, "C$", "C$999K"), (999_500.0, "C$", "C$1M"),
        (999_600.0, "C$", "C$1M"), (999.6e6, "€", "€1B"), (999.6e9, "£", "£1T"), (999.4e12, "$", "$999T"),
        (999.6e12, "$", "$1,000T"), (1.25e15, "$", "$1,250T"), (1.04e-6, "C$", "C$0.00000104"), (1e-6, "C$", "C$0.000001"),
        (9.996e-5, "$", "$0.0001"), (1.234e-4, "$", "$0.000123"), (0.5, "$", "$0.5"), (3.2e-5, "", "0.000032"),
        (-5e9, "$", "-$5B"), (-2.5, "C$", "-C$2.5"),
    ):
        text = format_currency(value, prefix)
        check(f"format_currency({value!r}, {prefix!r})", text == expected, f"{text!r}, not {expected!r}")
    for value, expected in ((41.6e6, "41.6M"), (343e6, "343M"), (900e3, "900K"), (999.7, "1K"), (3.23e-5, "0.0000323")):
        text = format_population(value)
        check(f"format_population({value!r})", text == expected, f"{text!r}, not {expected!r}")
    for value, expected in (
        (0.25, "0.25%"), (1.5, "1.5%"), (120.0, "120%"), (999.4, "999%"), (999.6, "1,000%"), (1000.0, "1,000%"),
        (1234.5, "1,234%"), (1.23e-5, "0.0000123%"), (-1.23e-5, "-0.0000123%"), (-0.4, "-0.4%"), (-1500.0, "-1,500%"),
        (0.0001, "0.0001%"), (0.0, "0%"),
    ):
        text = format_percent(value)
        check(f"format_percent({value!r})", text == expected, f"{text!r}, not {expected!r}")

    # The sweep: no exponent, the figure kept to three figures, 8.17's text kept where it had none.
    swept = _sweep()
    kept = 0
    for value in swept:
        for prefix in ("$", "C$", ""):
            text = format_currency(value, prefix)
            check(f"format_currency({value!r}) without an exponent", not _EXPONENT.search(text), text)
            error = abs(_read_currency(text, prefix) - value)
            check(f"format_currency({value!r}) to three figures", error <= _allowed(value, 1e15, 1e12), (text, error))
            old = _currency_817(value, prefix)
            if not _EXPONENT.search(old):
                kept += 1
                check(f"format_currency({value!r}) as 8.17 wrote it", text == old, (text, old))
            check(f"format_currency({-value!r}) a hyphen first", format_currency(-value, prefix) == "-" + text,
                  format_currency(-value, prefix))
        text = format_percent(value)
        check(f"format_percent({value!r}) without an exponent", not _EXPONENT.search(text), text)
        error = abs(float(text[:-1].replace(",", "")) - value)
        check(f"format_percent({value!r}) to three figures", error <= _allowed(value, 999.5, 1.0), (text, error))
        old = _percent_817(value)
        if not _EXPONENT.search(old):
            kept += 1
            check(f"format_percent({value!r}) as 8.17 wrote it", text == old, (text, old))
        check(f"format_percent({-value!r}) a hyphen first", format_percent(-value) == "-" + text, format_percent(-value))
    print(f"[formats] {len(swept)} figures swept, {kept} texts as 8.17 wrote them")
    print(f"[formats] {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
