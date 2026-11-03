# Price index (CPI)

Each nation's consumer price index itself, in index points on a log axis of its own, drawn as a solid deep-pink line, each month's index a step across that month. Price index (CPI) draws it not seasonally adjusted; Price index, seasonally adjusted draws the adjusted index instead, where one is published. One or the other: in the window and on the page ticking one box unticks the other. Either adds the index to the chart and hides nothing.

When GDP, debt or interest is drawn, the index has an axis of its own outside the right axis, so it keeps its own scale; without them it is on the right axis. It is drawn the same either way, and the same [per capita](?help=per-capita), [as % of GDP](?help=percent-of-gdp) and [inflation adjusted](?help=constant-prices): the index is never divided. The axis names each index's base, as its statistics office states it: "Consumer Price Index (2002 = 100, Log Scale)". Top and Bottom are the right axis's limits, not the index's.

On a log axis a straight stretch of the index is a steady rise in prices, and its slope is that rate. The [regression segments](?help=regression) fit the index on its own axis, by that axis's height, so each piece's %/yr is the average [inflation](?help=inflation) over it. The unadjusted index's seasonal swings can take more pieces on a short window than the adjusted one's. An end label and the read-out give the index to one decimal, as the statistics offices publish it.

## Seasonally adjusted

Seasonal adjustment takes out the swings that come back each year at the same time (clothing sales, fuel in winter, the summer's travel), so a month's change reads as the trend. Over a year the two indexes agree: each year's average of the adjusted index is within 0.1 % of the unadjusted one's (measured 2026-11-03), and their 12-month rises differ by less than a point (0.7 at most, Germany's at the VAT cut of 2020-07). The adjusted figures are revised as the seasonal factors are re-estimated, each year for the U.S. and Canada, and the unadjusted ones never are. The headline rates are taken from the unadjusted index, which also goes back further.

## Where each index comes from

- **Canada, unadjusted, from 1914-01.** Statistics Canada's consumer price index, all items, 2002 = 100 (table 18-10-0004, vector v41690973, [Consumer Price Index, monthly, not seasonally adjusted](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401)).
- **Canada, seasonally adjusted, from 1992-01.** The same index seasonally adjusted, 2002 = 100 (table 18-10-0006, vector v41690914, [Consumer Price Index, monthly, seasonally adjusted](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000601)).
- **The United States, unadjusted, from 1913-01.** The CPI for all urban consumers, all items in U.S. city average, 1982–84 = 100, from the Bureau of Labor Statistics through FRED ([CPIAUCNS](https://fred.stlouisfed.org/series/CPIAUCNS)). The Bureau collected no prices in October 2025, during the federal shutdown, so the index has no value for that month, and the line holds September's across it.
- **The United States, seasonally adjusted, from 1947-01.** The same index seasonally adjusted ([CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL)), with no value for October 2025 either. The Bureau recomputes five years of seasonal factors with each January's figures.
- **The United Kingdom, unadjusted, 1914-07 to 1987.** The monthly consumer price index in the Bank of England's millennium dataset ([Research datasets](https://www.bankofengland.co.uk/statistics/research-datasets)), 2015 = 100: the ONS's estimates of the CPI from 1949, the cost-of-living index before them.
- **The United Kingdom, unadjusted, from 1988-01.** The ONS's CPI index, all items, 2015 = 100 ([D7BT](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23)), laid end to end with the Bank's index, neither scaled (they differ by 0.04 % in 1988-01).
- **The United Kingdom, seasonally adjusted:** the ONS publishes none, so with the seasonally adjusted box ticked the UK's chart draws no index, with a note.
- **Germany, unadjusted, from 1991-01.** The Federal Statistical Office's consumer price index, all items, 2020 = 100, through the Bundesbank ([BBDP1.M.DE.N.VPI.C.A00000.I20.A](https://www.bundesbank.de/dynamic/action/en/statistics/time-series-databases/time-series-databases/759784/759784?tsId=BBDP1.M.DE.N.VPI.C.A00000.I20.A)). West Germany's index before it is not read.
- **Germany, seasonally adjusted, from 1991-01.** The same index, calendar and seasonally adjusted, 2020 = 100 ([BBDP1.M.DE.Y.VPI.C.A00000.I20.A](https://www.bundesbank.de/dynamic/action/en/statistics/time-series-databases/time-series-databases/759784/759784?tsId=BBDP1.M.DE.Y.VPI.C.A00000.I20.A)).

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.

## On the command line

`--cpi`, at least `--cp`, the index not seasonally adjusted; `--seasonally-adjusted`, at least `--sea`, the adjusted one. `--no-cpi` and `--no-sea` take them off. The two can't be given together.
