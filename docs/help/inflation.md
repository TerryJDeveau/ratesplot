# Inflation

Each nation's 12-month rise in consumer prices: each month's consumer price index against the same month's a year before, in percent, drawn on the left axis as a dotted deep-pink line, each month's rise a step across that month. Inflation draws it. Beside the bond yields it shows what a yield is worth once prices have risen: 5 % a year with prices rising 10 % a year is a loss. An end label and the read-out give the rise to one decimal, as the statistics offices publish it.

The index is the all-items consumer price index, not seasonally adjusted, the one each nation's headline rate is taken from. A month's figure comes some weeks after it ends: Statistics Canada's and the ONS's for September 2026 on October 19 and 21, and the Bundesbank had Germany's first estimate for October 2026 by November 3.

## Canada

- **From 1915-01: Statistics Canada's consumer price index.** All items, monthly from 1914-01, 2002 = 100 (table 18-10-0004, vector v41690973, [Consumer Price Index, monthly, not seasonally adjusted](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401)). Statistics Canada computes its rate from the index as published, so the line is its rate before rounding.

## The United States

- **From 1914-01: the CPI for all urban consumers.** All items in U.S. city average, monthly from 1913-01, 1982–84 = 100, from the Bureau of Labor Statistics through FRED ([CPIAUCNS](https://fred.stlouisfed.org/series/CPIAUCNS)). The Bureau collected no prices in October 2025, during the federal shutdown, so the index has no value for that month, and the line has no rise for 2025-10 or for 2026-10, a year later.

## The United Kingdom

- **1915-07 to 1988: the Bank of England's spliced index.** The monthly consumer price index in the Bank's millennium dataset ([Research datasets](https://www.bankofengland.co.uk/statistics/research-datasets)), 2015 = 100: the ONS's estimates of the CPI from 1949, the cost-of-living index before them, from 1914-07. Its 12-month rise is within 0.28 points of the ONS's own rate in every month both have (1989 to 2017, measured 2026-11-03).
- **From 1989-01: the ONS's 12-month rate.** The CPI's annual rate as the ONS publishes it, to one decimal ([D7G7](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23)). The ONS computes it from the index before rounding, so it is taken as published: the rise of the published index, rounded, differs from it in 190 of 453 months, by up to 0.19 points.

## Germany

- **From 1992-01: the Federal Statistical Office's consumer price index.** All items, monthly from 1991-01, 2020 = 100, through the Bundesbank ([BBDP1.M.DE.N.VPI.C.A00000.I20.A](https://www.bundesbank.de/dynamic/action/en/statistics/time-series-databases/time-series-databases/759784/759784?tsId=BBDP1.M.DE.N.VPI.C.A00000.I20.A)). The index for the whole of Germany begins in 1991, so the line begins a year later; West Germany's index before it is not drawn.

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.
