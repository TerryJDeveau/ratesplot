# Portugal

Portugal's chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:pt` (or `prt`) alone or with others, as in `--nations:ca,us,pt`. Its amounts are in euros (€), its rates in percent a year. Figures before 1999 are Portuguese escudos converted to euros at 200.482, as the ECB and Eurostat publish them in national currency. This page says what the chart holds for Portugal; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, debt and interest on the right axis, and the 10-year bond yield on the left; the policy rate, inflation, mortgage rates, the price index or the population when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1995: four-quarter sums of Eurostat's quarterly national accounts at current prices.
- [Aggregate public debt](?help=debt), from 1995: general government consolidated gross debt, the ECB's year ends to 1999, Eurostat's quarters from 2000.
- [TTM interest outlays](?help=interest), from 1999: four-quarter sums of general government interest payable, Eurostat's quarters.
- [Balance of payments](?help=payments), from 1996: Eurostat's quarterly balance of payments, not seasonally adjusted: the current account's credits and debits, or exports and imports of goods and services; the quarters after its last from its monthly figures.
- [By level](?help=levels): the debt and interest of central government or of local government instead of the total, from Eurostat's figures by subsector: the debt quarterly from 2000, the interest yearly from 1995 (each year's at its last day), as France's. Eurostat has no state level for Portugal; its social security funds are no level of the chart. Each subsector's debt is consolidated within it but not with the others, so central government's runs above general government's (€316 billion against €294 billion in 2026-Q2): what it owes the other subsectors counts in its own figure and is netted out of the total.
- [Bond yields](?help=yields), from 1993-07: the 10-year alone, the OECD's long-term interest rate on FRED, a monthly average drawn across its month. The chart's End is then the first day of the last month published, where its last average is drawn as a point. No other terms, no real yields, and so no yield spreads.
- [Policy rates](?help=policy-rates): the euro area's, the ECB's main refinancing rate from 1999-01-01; the overnight market's rate, EONIA from 1999-01-04, €STR from 2019-10-01. None before 1999.
- [Inflation](?help=inflation), from 1956-01: the 12-month rise of Portugal's consumer prices, Eurostat's harmonised index from 1996 and the national index before it, scaled to it where it begins; the rises from 1997 are the harmonised index's alone.
- [Mortgage rates](?help=mortgages), monthly: the ECB's rates on new loans to households in Portugal for house purchase. The variable rate (a variable rate or one fixed for up to a year), from 2000-01 with no month missing, is ticked at the start. The rates fixed for over 1 to 5 and over 5 to 10 years, from 2003-01, and over 10 years, from 2003-07, can be ticked beside it; each misses 57 or 58 months, mostly before 2013, and jumps by several points from one month to the next, the over-10-year rate until 2015.
- [Per capita](?help=per-capita): divided by the population the Population box draws.
- [Inflation adjusted](?help=constant-prices): at the consumer prices of one month, by the same index, from 1955.
- [Price index (CPI)](?help=price-index): Eurostat's harmonised index of consumer prices for Portugal from 1996-01, 2025 = 100, and before it, from 1955-01, the national index as the OECD published it, scaled to it; unadjusted; no seasonally adjusted index is offered.
- [Population](?help=population): Eurostat's quarterly figures from 1995.
- [Latest values](?help=latest-values): no quotes during the day for Portugal; its yield is a monthly average, so the chart ends at the last month published.

## Its own controls

Under Portugal's chart in the window, and under "Portugal only" on the page, are the controls that set its chart alone: the policy rates and mortgage terms it draws, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in € unless another currency is named by its code (USD20t). On the command line each is written after Portugal's prefix, `--pt:` or `--prt:`, as in `--pt:max:8`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany), [France](?help=france), [Italy](?help=italy).
