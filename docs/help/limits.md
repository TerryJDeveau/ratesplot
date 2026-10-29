# Axis limits: Min, Max, Top and Bottom

Each chart has two vertical axes: on the left the yields, spreads and rates, in percent; on the right GDP, debt and interest, on a log scale. Min and Max set the bottom and top of the left axis, Bottom and Top those of the right. Left blank, each axis fits the curves drawn on it.

## Min and Max: the left axis

In percent, as plain numbers: `--max:8`, `--min:-0.5`. A negative Min is allowed, since spreads go below zero when the yield curve inverts and some yields have. With one of the two set, the other end still fits the curves. The axis leaves a small margin beyond each end (1.5 % of its height below and 4 % above, at least 0.02 and 0.08 points), so a line at a limit isn't hidden by the frame. Both boxes are greyed while nothing is drawn on the left axis.

## Top and Bottom: the right axis

- **An amount** in the chart's own currency (C$ for Canada, $ for the U.S., £ for the UK, € for Germany), with k, m, b or t for thousands, millions, billions or trillions; a number alone is billions: `--top:20t`, `--bottom:500` (500 billion). Under [Per capita](?help=per-capita) the amounts are per person (`--top:100k`).
- **A percentage** under [As % of GDP](?help=percent-of-gdp): `--top:150%`. An amount is refused there, a percentage elsewhere, and the boxes are cleared when the measure changes. The unit beside each box shows the currency, and is blank under % of GDP.

With one of the two set, the other end is not fitted to the curves but set at a fixed default, so that this axis never mixes a limit chosen with one taken from the data: 10 billion or 100 trillion, 0.1 % or 1,000 % under % of GDP, 1 or 1 million per person. For a close view, set both. Both boxes are greyed while no curve is drawn on the right axis.

## A limit in another currency

Top and Bottom can be given in another nation's currency by its code first: `USD20t`, `CAD5t`, `GBP2t`, `EUR3t`; `US$`, `C$`, `£` and `€` are accepted too, and written back as the code. A `$` alone is refused, since it doesn't say whose dollars (and on a command line `$20t` is read as a variable). The chart converts the amount at the exchange rate of its End date, the latest on or before it, and the log gives the rate: a chart with a fixed End draws the same each time, one ending today follows the rate.

Every rate goes through the U.S. dollar:

- **From 1971:** the Federal Reserve Board's daily rates (H.10), on FRED: [Canadian dollars](https://fred.stlouisfed.org/series/DEXCAUS) and [pounds](https://fred.stlouisfed.org/series/DEXUSUK) from 1971-01-04, [euros](https://fred.stlouisfed.org/series/DEXUSEU) from 1999-01-04; before the euro, the [Deutsche mark](https://fred.stlouisfed.org/series/EXGEUS) (monthly averages) at its fixed 1.95583 marks to the euro. FRED adds the H.10 rates once a week, on Mondays, so the latest rate can be a week or more old.
- **The pound before 1971:** U.S. dollars per pound, monthly from 1791, from the Bank of England's dataset "A millennium of macroeconomic data" ([research datasets](https://www.bankofengland.co.uk/statistics/research-datasets)).
- **The Canadian dollar before 1971:** from 1858 at the gold par of $4.86⅔ to the pound; 1913 to 1962 each year's average from Historical Statistics of Canada (table J562); 1963 to 1970 the millennium dataset's monthly rate against the pound.
- **The euro before 1971:** the mark's official parities with the U.S. dollar from 1948-06-21 (3⅓ marks to the dollar, then 4.20 from 1949-09-19 and 4.00 from 1961-03-06), and 1963 to 1970 the millennium dataset's rate against the pound, each at 1.95583 marks to the euro.

Where there is no rate (the pound before 1791, the Canadian dollar before 1858, the euro before 1948-06-21), or Bottom is no longer below Top once converted, the log warns and the limit is left to the axis.

With a [master currency](?help=master-currency), a chart converted to it draws in the master's currency, and its Top and Bottom are converted to that one: a limit with no code is in the nation's own currency still, at the chart's rate. A box dragged over such a chart writes its limits with the master's code.

## “All”

Beside each limit, "All" copies its value into every other nation's box, so one limit is set for every chart, and the command line writes it once (`--max:8`). A value typed into any box while it is ticked goes into the others; a blank is never copied. An amount is copied with its currency (20t from the U.S. box as USD20t), so each chart converts it at its own End date; a percentage is copied as it is. "All" is greyed while its box is blank, while fewer than two nations are ticked, and while the box itself is greyed.

## Zooming

A box dragged over a chart sets that chart's limits from its height, and Start and End from its width; the other charts' limits are left as they are, unless the limit's "All" is ticked. Back undoes it.

## Each nation's own

The limits are each nation's own, under its chart in the window and in its section on the page ([Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany)). On the command line a limit with no prefix is for every chart (`--max:8`); a nation's prefix sets its chart alone (`--us:max:8`, `--cdn:top:5t`).
