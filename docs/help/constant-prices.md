# Inflation adjusted (--constant)

GDP, debt, interest and the [balance of payments](?help=payments) at constant prices: each amount divided by its nation's consumer price index for the month it is dated in, and multiplied by the index for one month, the last the index has on or before the chart's End. The amounts are then in that month's prices. The right axis reads "Inf. Adj. CAD at 2026-09 Prices (Log Scale)", the title ends "at 2026-09 Prices", and GDP's name in the legend drops "Nominal". Each curve ends where it does in current prices, and its history is raised by the rise in prices since, so a curve's slope is its growth beyond inflation, and the [regression segments](?help=regression) give that real growth in %/yr.

## How the division is made

Each figure is divided when it is observed, by the index of its month, and held until the next figure, as [per capita](?help=per-capita) divides by the population, so the lines keep their steps. A figure dated after the index's last month (a debt clock's days, or a month not yet published) is divided by the last index published, which is also the month the chart is in, so the newest amounts are as they are in current prices.

Debt, counted on a date, is divided by the index of that date's month. GDP and interest, each a total over twelve months, are divided by the index of their last month too. This keeps the distance between debt and GDP on the log axis what it is in current prices, as it should be, since a share of GDP is free of inflation. Dividing each total by the average of its twelve months' index instead would raise GDP and interest by about half a year's inflation.

Before an index begins there is no price to divide by, and nothing is drawn: before 1914 in Canada, 1914-07 in the UK and 1948-06 in Germany (the U.S. index, from 1913, is older than any U.S. curve). On a chart ending before its index begins, the amounts are drawn in current prices, with a warning.

Inflation adjusted combines with per capita, for real amounts per person ("Inf. Adj. CAD per Capita at 2026-09 Prices"). It can't be combined with [As % of GDP](?help=percent-of-gdp): a share of GDP is free of inflation already, and in the window and on the page ticking that box unticks this one. In the [master currency](?help=master-currency) each chart's amounts are put at its own nation's prices first, then converted at the rate of its End date. Without [GDP](?help=gdp), [debt](?help=debt) or [interest](?help=interest) ticked it has no effect, and its box is greyed.

## Where each index comes from

Each is the all-items consumer price index, not seasonally adjusted, the one the [inflation](?help=inflation) curve is taken from. Its base year doesn't matter, since the program divides by one month's index and multiplies by another's.

- **Canada, from 1914-01.** Statistics Canada's consumer price index, 2002 = 100 (table 18-10-0004, vector v41690973, [Consumer Price Index, monthly, not seasonally adjusted](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401)).
- **The United States, from 1913-01.** The CPI for all urban consumers, 1982–84 = 100, from the Bureau of Labor Statistics through FRED ([CPIAUCNS](https://fred.stlouisfed.org/series/CPIAUCNS)). The Bureau collected no prices in October 2025, so figures dated in that month are divided by September's index.
- **The United Kingdom, 1914-07 to 1987.** The monthly consumer price index in the Bank of England's millennium dataset ([Research datasets](https://www.bankofengland.co.uk/statistics/research-datasets)), 2015 = 100: the ONS's estimates of the CPI from 1949, the cost-of-living index before them.
- **The United Kingdom, from 1988-01.** The ONS's CPI index, all items, 2015 = 100, to one decimal ([D7BT](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23)). It and the Bank's index differ by 0.04 % in 1988-01 and by at most 0.17 points in the 351 months both have (to 2017-03, measured 2026-11-03), so they are laid end to end, neither scaled.
- **Germany, from 1991-01.** The Federal Statistical Office's consumer price index, 2020 = 100, through the Bundesbank ([BBDP1.M.DE.N.VPI.C.A00000.I20.A](https://www.bundesbank.de/dynamic/action/en/statistics/time-series-databases/time-series-databases/759784/759784?tsId=BBDP1.M.DE.N.VPI.C.A00000.I20.A)).
- **Germany, 1948-06 to 1990.** West Germany's cost-of-living indexes, as the [price index](?help=price-index) page says, scaled to the index above. Germany's GDP, debt and interest reach back to 1950 (the interest of each level of government to 1970).

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.

## On the command line

`--constant`, at least `--con`; `--no-constant` takes it off.
