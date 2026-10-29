# Size and layout of the chart

## Size

The chart's width and height in pixels, at least 800 each way; 2048 by 1536 when blank. In the window and on the page the two are typed in their own boxes, and "Preserve aspect ratio" keeps their ratio as one is changed. Export chart writes a PNG of exactly this size.

The text and the lines are scaled with the size: every font by the smaller of width ÷ 2048 and height ÷ 1536, never below half its size, with the spacing tied to the text (the legend's margins, the gaps around the titles); the lines never thinner than on the default chart. On a narrow screen (under 700 pixels wide) the page draws 800 by 800 unless a size is typed, and its text is never below 80 % of its size: at half size, with the chart shown as a phone shows it, the legend and the ticks could not be read.

## The title and the subtitle

The title is made from what the chart draws, its phrases joined by commas and a last "&": "Canadian Benchmark Yields, Aggregate Public Debt, TTM GDP & Interest Outlays". The nation is named once, near the beginning: by its adjective (Canadian, German; US and UK), or by its short form (CDN, DEU) only where that lets a long title be drawn in larger type. A title that doesn't name the nation in its first phrase begins with its name ("Canada: Policy Rate"); a title too wide for the chart is drawn smaller until it fits.

The subtitle names the first and last dates of the data drawn, which can be narrower than Start and End ([Start and End](?help=dates)), and the time of the day's quotes where they are drawn, "intraday, provisional" ([Latest values](?help=latest-values)).

## The axes

- **Left:** the yields, spreads and rates, in percent, on a linear scale, with ticks at steps of 1, 2 or 5 times a power of ten, so that they fall on round values.
- **Right:** GDP, debt and interest, on a log scale, where equal distances are equal ratios, so steady growth draws a straight line and a doubling is the same height at any level. Ticks at the powers of ten and at round values between, written with T, B, M and K for trillions, billions, millions and thousands. Under [As % of GDP](?help=percent-of-gdp) the right axis is in percent, also on a log scale.

The limits of both: [Axis limits](?help=limits).

## The legend

The legend is placed last, once everything else is laid out, where it covers no line: in two columns, then three, then one, then the same with smaller type; at least 40 pixels from the frame and, where it can be, 200 pixels clear of every line, as near a corner as that allows, otherwise centred in the largest open space (both distances on the default chart, scaled with the text). Where no shape fits anywhere without covering a line, it goes where the lines under it are least busy: the fewest of the labels of [Latest value](?help=end-labels) and [Regression segments](?help=regression) under it, then the fewest reversals of direction, then the fewest changes, then the least ink. It is drawn above every curve.

The yields are listed from the longest term down, then the policy rate, the mortgage rates and the spreads, to echo the order of the curves on the chart; the right axis's curves are a group of their own.

## On the command line

`--dimensions:WxH` or `--dim:WxH` (`--dim:1600x1200`); one number is the width, with the height at three quarters of it (`--dim:1600`), and `x` and a number the height, with the width at four thirds (`--dim:x1200`).
