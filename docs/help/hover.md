# Hover read-out

On by default. The pointer resting on a line for half a second shows a small box beside it: the line's name, as the legend gives it, and its value and date. The box follows the pointer along the lines, and goes 2 seconds after the pointer has left them, or at once when a button is pressed.

## What it reads

- **Every line within 3 screen pixels** of the pointer, the nearest first, each once, with a ring on the point read; the box's border is in the nearest line's colour. Where lines cross, all of them are read in the one box.
- **A line drawn through observations** (the yields, the right axis's curves): the nearer observation, never a value between two.
- **A line drawn as steps** (policy rates, mortgage rates, a quarterly figure held until the next): the value in force on the day under the pointer, with "(observed DATE)" where that value was observed earlier.
- **A projection** ([Projections to today](?help=projections)): its value on the day under the pointer, with "≈".
- **A quote of the day** ([Latest values](?help=latest-values)): its time, as the subtitle gives it. A policy rate drawn from its bank's announcement adds "(announced)".

Each value is written as the [latest value](?help=end-labels) at a line's end writes it: a yield to three decimals, a spread in points, an amount as the axis's ticks.

## Where it shows

In the window, on the page and in the plain matplotlib windows of `--no-gui`. On the page a touch shows nothing, so a phone has no read-out. It draws nothing on the chart: a chart saved or exported is the same with the box ticked or not, and ticking or unticking it doesn't draw the chart again.

In the window, unticking it also hides the tips that appear over the controls with an ⓘ beside them, since the ⓘ shows the same text with a click; the tips over the buttons stay.

## On the command line

On unless `--no-ho` (or `--no-hover`) is given; `--ho` or `--hover` turns it on.
