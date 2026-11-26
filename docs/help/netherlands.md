# Netherlands

The Netherlands' chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:nl` (or `nld`) alone or with others, as in `--nations:ca,us,nl`. Its amounts are in euros (€), its rates in percent a year. Figures before 1999 are Dutch guilders converted to euros at 2.20371, as the ECB and Eurostat publish them in national currency. This page says what the chart holds for the Netherlands; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, debt and interest on the right axis, and the 10-year bond yield on the left; the policy rate, inflation, mortgage rates, the price index or the population when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1995: four-quarter sums of Eurostat's quarterly national accounts at current prices.
- [Aggregate public debt](?help=debt), from 1995: general government consolidated gross debt, the ECB's year ends 1995 to 1999, then Eurostat's quarters from 2000-Q1.
- [TTM interest outlays](?help=interest), from 1999: four-quarter sums of general government interest payable, Eurostat's quarters from 1999-Q1.
- [Balance of payments](?help=payments), from 2003-Q2: Eurostat's quarterly balance of payments, not seasonally adjusted: the current account's credits and debits, or exports and imports of goods and services; the four-quarter sums begin in 2004. Eurostat's monthly figures hold neither for the Netherlands, so both end at their last quarter.
- [Debt and interest by level](?help=levels): the debt and interest of central or local government instead of the total, from Eurostat's figures by subsector: the debt quarterly from 2000, the interest yearly from 1995 (each year's at its last day). The Netherlands has no state level; its social security funds are no level of the chart. In 2026-Q2 central government owed €582 billion and local government €53 billion, of a total of €524 billion: each subsector's debt is consolidated within it but not with the others, so central government's alone runs above the total. Local government's interest is small and fell to €114 million in 2021, Eurostat's yearly figure, before rising to over €1 billion from 2023.
- [Bond yields](?help=yields), from 1959-01: the 10-year alone, the OECD's long-term interest rate on FRED ([IRLTLT01NLM156N](https://fred.stlouisfed.org/series/IRLTLT01NLM156N)), a monthly average drawn across its month. The chart's End is then the first day of the last month published, where its last average is drawn as a point. No other terms, no real yields, and so no yield spreads.
- [Policy rates](?help=policy-rates): the euro area's, the ECB's main refinancing rate from 1999-01-01; the overnight market's rate, EONIA from 1999-01-04, €STR from 2019-10-01. None before 1999.
- [Inflation](?help=inflation), from 1961-04: the 12-month rise of the Netherlands' consumer prices, Eurostat's harmonised index from 1996 and the national index before it, scaled to it where it begins; the rises from 1997 are the harmonised index's alone. In the early 1960s the national index often stays the same for months and then moves in a step (it rises 4.4 % in 1964-04 alone), so the rises of those years jump about: the source's, not the chart's.
- [Mortgage rates](?help=mortgages), monthly: the ECB's rates on new loans to households in the Netherlands for house purchase. The rates fixed for over 1 to 5 and over 5 to 10 years, from 2000-01, and over 10 years, from 2003-01, are ticked at the start, as Germany's, France's and Italy's are; none misses a month or moves a point from one month to the next. The variable rate (a variable rate or one fixed for up to a year), from 2000-01, can be ticked beside them. The ECB flags the figures before 2003 as estimates.
- [Per capita](?help=per-capita): divided by the population the Population box draws.
- [Inflation adjusted](?help=constant-prices): at the consumer prices of one month, by the same index, from 1960-04.
- [Price index (CPI)](?help=price-index): Eurostat's harmonised index of consumer prices for the Netherlands from 1996-01, 2025 = 100, and before it, from 1960-04, the national index as the OECD published it, scaled to it; unadjusted; no seasonally adjusted index is offered.
- [Population](?help=population): Eurostat's quarterly figures from 1995.
- [Latest values](?help=latest-values): no quotes during the day for the Netherlands; its yield is a monthly average, so the chart ends at the last month published.

## Its own controls

Under the Netherlands' chart in the window, and under "Netherlands only" on the page, are the controls that set its chart alone: the policy rates and mortgage terms it draws, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in € unless another currency is named by its code (USD20t). On the command line each is written after the Netherlands' prefix, `--nl:` or `--nld:`, as in `--nl:max:8`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany), [France](?help=france), [Portugal](?help=portugal), [Italy](?help=italy), [Spain](?help=spain), [Japan](?help=japan).
