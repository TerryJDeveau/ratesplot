# Hover read-out

On by default. The pointer resting on a line for half a second shows a small box beside it: the line's name, as the legend gives it, its value and date, and its change. The box follows the pointer along the lines, and goes 2 seconds after the pointer has left them, or at once when a button is pressed.

## What it reads

- **Every line within 3 screen pixels** of the pointer, the nearest first, each once, with a ring on the point read; the box's border is in the nearest line's colour. Where lines cross, all of them are read in the one box.
- **A line drawn through observations** (the yields, the spreads): the last observation on or before the day under the pointer, never a value between two or from a later day. On the sparse monthly yields of earlier years the ring stays on a month's point until the pointer passes the next.
- **A line filled in between its figures** ([Daily values](?help=daily): debt, GDP, interest, the balance of payments, inflation, the price index, the population): its value on the line on the day under the pointer.
- **A line drawn as steps** (policy rates, mortgage rates; with Daily values unticked, a quarterly figure held until the next): the value in force on the day under the pointer, with "(observed DATE)" where that value was observed earlier.
- **A projection** ([Projections to today](?help=projections)): its value on the day under the pointer, with "≈".
- **A quote of the day** ([Latest values](?help=latest-values)): its time, as the subtitle gives it. A policy rate drawn from its bank's announcement adds "(announced)".

Each value is written as the [latest value](?help=end-labels) at a line's end writes it: a yield to three decimals, a spread in points, an amount as the axis's ticks.

## Its change

Under the value, each line gives its change: a plain subtraction in the line's own unit, and where that unit isn't percent (an amount, a population, the price index) the percentage change of the same pair after it, where the earlier value is above zero.

- **A line filled in between its figures, or a projection**: its change from the day before, then that change's rate over a year: "+$4.97B, +1.4 bp a day (≈ +5.11%/yr)", or for a line in percent "+0.4 bp a day (≈ +1.46 pp/yr)". Where the value is held after its last figure: "no change from the day before".
- **A rate set by announcement** (a policy rate, a prime rate, the UK's tracker): its last change and that change's date, "−25 bp on 2025-10-29", whether the chart's Daily values are ticked or not. On a stretch from the chart's start, the change before the chart.
- **Any other line** (the yields, the spreads, the mortgage rates; with Daily values unticked, a quarterly or monthly figure): its change from the observation before it, with that one's date, "−3.0 bp from 2026-08-28".

A change in a rate is written in bp (hundredths of a point) below 1 point and in pp from 1; a percentage change in bp below 1 % and in % from 1. pp and % are written to three places, two where the third is 0 ("+1.25 pp", "+1.375 pp"); bp to a tenth below 10 and whole from 10 ("+3.5 bp", "−25 bp"). Each has its sign, and a figure that rounds to nothing has none.

Every figure in the box, its values too, is rounded on its decimal digits, half away from zero: 1.235 to two places is 1.24, and −1.235 is −1.24. The latest value at a line's end is written as before, so where a source has more decimals than the box shows, the two can differ in the last digit at an exact half.

## Where it shows

In the window, on the page and in the plain matplotlib windows of `--no-gui`. On the page a touch shows nothing, so a phone has no read-out. It draws nothing on the chart: a chart saved or exported is the same with the box ticked or not, and ticking or unticking it doesn't draw the chart again.

In the window, unticking it also hides the tips that appear over the controls with an ⓘ beside them, since the ⓘ shows the same text with a click; the tips over the buttons stay.

## On the command line

On unless `--no-ho` (or `--no-hover`) is given; `--ho` or `--hover` turns it on.
