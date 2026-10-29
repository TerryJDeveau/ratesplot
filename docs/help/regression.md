# Regression segments (--reg)

Each curve on the right axis fitted by the fewest straight pieces that stay close to it, each labelled with the curve's growth over it, in % a year. On the log axis a straight line is steady growth, so each piece marks a stretch of roughly steady growth, and its label says how fast. The pieces are drawn as pale bands in the curve's colour, under the curves, and the legend adds one grey entry, "Regression segments, growth in %/yr".

## The fit

Each piece is a weighted least-squares regression of the logarithm of the curve's values on time in years.

- **The label.** A piece whose first and last observations are a year or more apart gets the compound annual rate: what the curve grew by, on average, in each year of it (`+6.8%/yr`). A shorter piece gets the slope of the logarithm, the continuous rate, since compounding a few months into a year's rate would be extrapolation. One decimal, and a sign.
- **The points.** The curve's observations within the dates shown, that is, the dates on which its value changes. The [projection to today](?help=projections) is left out, so the last piece ends at the last observation. Each point is weighted by half the gap to each of its neighbours, so a run of daily figures counts for no more in a year than the quarterly figures before it.
- **Under** [As % of GDP](?help=percent-of-gdp) the label is the ratio's own growth; under [Per capita](?help=per-capita), the growth per person.

## How close a piece stays

Every observation of a piece lies within the tolerance of its line: 0.3 % of the right axis's height, about 4 pixels on the default chart of 2048 by 1536, but never less than 1 % of the value. The tolerance is measured on the picture, so it changes with the axis: another curve drawn, or Top and Bottom set ([Axis limits](?help=limits)), can change the pieces. The floor of 1 % keeps a close zoom from being cut up by quarter-to-quarter noise. A larger tolerance gives fewer and longer pieces: it was 1 until 2026-10-12, when it was set at 0.3 after some testing.

Of all the ways to cover a curve within the tolerance, the program takes the one with the fewest pieces, and of those the one with the least total squared error. The pieces are separate regressions and don't join, so a jump (2020's, for instance) falls between two.

Where the tolerance cuts a stretch into short pieces, three or more in a row each spanning less than a year (on a span of dates under eight years, less than an eighth of it), that stretch is fitted again alone with the least tolerance that makes its pieces that long, up to three times the tolerance. The message log names each stretch so loosened. The reason is seasons: monthly debt figures rise and fall within the year (the UK's net debt stood about 1.8 % above its trend each December and 1.7 % below it each February in 1997 to 2009), which cut the curve into pieces of a few months at −39 or +51 %/yr. Loosened, its 44 pieces became 18.

## The labels

Each label is written along its piece, in the curve's colour, above or below it, placed where it covers the fewest other labels, bands and curves; where it is crowded, it is drawn smaller, or set further off with a thin line to its piece. A piece wholly outside the axes has no label.

## On the command line

`--reg` or `--regression` turns them on, `--no-reg` off; `--reg:TOL` sets the tolerance in % of the axis's height and turns them on (`--reg:1`). In the window and on the page the tolerance has its box beside "Regression segments" (0.3 when blank). Both are greyed while none of debt, GDP and interest is ticked, and the tolerance's box while "Regression segments" is unticked.
