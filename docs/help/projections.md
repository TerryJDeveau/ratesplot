# Projections to today

On by default. GDP, debt and interest are published weeks or months after the period they describe, so their curves end well before today. With this box ticked, each curve on the right axis is carried on from its last figure to the chart's End in a straight line, at its own pace over the year before that figure, as a debt clock does. The projections are not data: each is drawn faint, at 40 % strength, in its curve's own colour and dashes; the legend's grey entry reads "Projected at the past year's pace"; and the [latest value](?help=end-labels) at a line's end and the [hover read-out](?help=hover) write a projected value with "≈" (≈C$4.22T).

## How a curve is carried on

- **From** the date its last figure describes: a quarter's figure is dated by the quarter's last day.
- **At** the curve's change over the 365 days before that figure, as so much a day: the line is the last figure plus that much for each day since. The pace is measured on the curve's whole history, so a chart whose Start is later than that year still gets it.
- **Not projected:** a curve whose last figure is more than 400 days before the End, such as the dotted line of Canada's federal debt before 1933.
- **Population** is held at its last estimate, not projected. Under [Per capita](?help=per-capita) and [As % of GDP](?help=percent-of-gdp) the projected figures are divided as the published ones are; GDP is projected too.

## Canada's debt follows market debt

The Bank of Canada publishes the Government of Canada's marketable debt, its treasury bills and marketable bonds outstanding, every business day, about four days behind. It counts less than the federal debt the chart draws, and its quarterly changes follow that debt only loosely (pensions, payables and market valuation move the rest), so it isn't joined as data; but it does steer the projection of Canada's aggregate debt and of its federal level. Each is drawn as market debt plus the rest: market debt as published to its last day, then at its own pace over the year before; the rest from the quarter's end at its pace over the year to it. Tested from the start of each quarter since 2010, this cut the root-mean-square error in the next quarter's level from 48 billion dollars to 37 for the aggregate, and from 45 to 33 for the federal level. Each day is read as the middle value of it and the two days before, since new bills settle a day before the old ones mature and lift the total by about 2 % for a day. Where a curve is steered, the legend's entry reads "Projected; debt follows market debt". If market debt can't be had, the log warns and the plain pace is used; the other levels of government always keep it.

## When it adds nothing

The projections are drawn only on a chart whose End is no more than four days before today, the rule for the day's quotes ([Latest values](?help=latest-values)). The box is greyed when the End is earlier, and while none of debt, GDP and interest is ticked.

It has been a box of its own since 2026-10-27; until then "Intraday quotes on end date" turned both on and off. The quotes draw values published since the regular sources' last figures; this box draws an estimate.

## On the command line

On unless `--no-pro` (or `--no-projections`) is given; `--pro` or `--projections` turns them on.
