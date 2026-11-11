# Daily values

On by default. Debt, GDP, interest, the balance of payments, inflation, the consumer price index and the population change steadily, but each is published only now and then: a quarter's debt, a month's index, a year's population estimate. With this box ticked, each of them is filled in between its figures: drawn as a straight line from one figure to the next, and read day by day by the [hover read-out](?help=hover). Unticked, each figure is held until the next, drawn in steps, as before 2026-11-11.

## Where each figure is pinned

- **A level on a date** (debt at a quarter's end, a population estimate): on that date.
- **A sum over twelve months** (TTM GDP, interest, the balance of payments; a year's figure in the older history): on the last day of its twelve months. The line between two such sums is the sum over the twelve months to each day, with each quarter's flow spread evenly across its quarter: the quarter that leaves the window is counted as the new one comes in.
- **A month's figure** (the price index, and the inflation rate taken from it): at the middle of its month, held flat over the first half of the first month and the second half of the last, so the line begins and ends where its steps did. A month missing breaks the line (the U.S. has no index for 2025-10).

Each line is cut at the chart's Start and End where it crosses them, its value there on the line. After a series' last figure its value is held, as before, unless [Projections to today](?help=projections) carry it on.

## Which series it leaves alone

Yields, spreads and the market's rates are prices quoted each day, not filled in; policy rates and the rates that follow them (the prime rates, the UK tracker) hold until they are changed; mortgage rates are surveys of a week or a month. They are drawn as they always were, ticked or not.

## With the measures

[Per capita](?help=per-capita), [As % of GDP](?help=percent-of-gdp) and [Constant prices](?help=constant-prices) divide the figures filled in: debt filled in over GDP filled in, an amount over the population on that day, an amount over the price index filled in between its months' middles. So a curve divided is as smooth as the curves it is divided by.

## When it adds nothing

The box is greyed while none of the series it acts on is ticked.

## On the command line

On unless `--no-da` (or `--no-daily`) is given; `--da` or `--daily` turns it on. At least "da": `--d:` is [debt by level](?help=levels).
