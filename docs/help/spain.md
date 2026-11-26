# Spain

Spain's chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:es` (or `esp`) alone or with others, as in `--nations:ca,us,es`. Its amounts are in euros (€), its rates in percent a year. Figures before 1999 are Spanish pesetas converted to euros at 166.386, as the ECB and Eurostat publish them in national currency. This page says what the chart holds for Spain; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, debt and interest on the right axis, and the 10-year bond yield on the left; the policy rate, inflation, mortgage rates, the price index or the population when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1995: four-quarter sums of Eurostat's quarterly national accounts at current prices.
- [Aggregate public debt](?help=debt), from 1995: general government consolidated gross debt, Eurostat's quarters from 1995-Q1 (the ECB's year ends, from 1995, stand in only if Eurostat does not answer).
- [TTM interest outlays](?help=interest), from 1995: four-quarter sums of general government interest payable, Eurostat's quarters from 1995-Q1.
- [Balance of payments](?help=payments), from 1993: Eurostat's quarterly balance of payments, not seasonally adjusted: the current account's credits and debits, or exports and imports of goods and services. The current account's quarters after its last come from its monthly figures; Eurostat's monthly figures hold no goods and services for Spain, so exports and imports end at their last quarter.
- [Debt and interest by level](?help=levels): the debt and interest of central, regional or local government, or of regional and local together, instead of the total, from Eurostat's figures by subsector: the debt quarterly from 1995, the interest yearly from 1995 (each year's at its last day). The regional level is the autonomous communities, Eurostat's state government, as Germany's Länder are; its social security funds are no level of the chart. In 2026-Q2 central government owed €1,613 billion, the autonomous communities €355 billion and local government €21 billion, of a total of €1,763 billion: each subsector's debt is consolidated within it but not with the others, so the levels add up to more than the total.
- [Bond yields](?help=yields), from 1980-01: the 10-year alone, the OECD's long-term interest rate on FRED ([IRLTLT01ESM156N](https://fred.stlouisfed.org/series/IRLTLT01ESM156N)), a monthly average drawn across its month. The chart's End is then the first day of the last month published, where its last average is drawn as a point. No other terms, no real yields, and so no yield spreads.
- [Policy rates](?help=policy-rates): the euro area's, the ECB's main refinancing rate from 1999-01-01; the overnight market's rate, EONIA from 1999-01-04, €STR from 2019-10-01. None before 1999.
- [Inflation](?help=inflation), from 1955-03: the 12-month rise of Spain's consumer prices, Eurostat's harmonised index from 1996 and the national index before it, scaled to it where it begins; the rises from 1997 are the harmonised index's alone.
- [Mortgage rates](?help=mortgages), monthly: the ECB's rates on new loans to households in Spain for house purchase. The variable rate (a variable rate or one fixed for up to a year), from 2000-01, is ticked at the start, as Portugal's is: it misses no month and moves by under 1 point from one month to the next, where the rate fixed for over 5 to 10 years jumps by up to 2 points. The ECB flags the figures before 2003 as estimates. The rates fixed for over 1 to 5 and over 5 to 10 years, from 2000-01, and over 10 years, from 2003-01, can be ticked beside it.
- [Per capita](?help=per-capita): divided by the population the Population box draws.
- [Inflation adjusted](?help=constant-prices): at the consumer prices of one month, by the same index, from 1954-03.
- [Price index (CPI)](?help=price-index): Eurostat's harmonised index of consumer prices for Spain from 1996-01, 2025 = 100, and before it, from 1954-03, the national index as the OECD published it, scaled to it; unadjusted; no seasonally adjusted index is offered.
- [Population](?help=population): Eurostat's quarterly figures from 1995.
- [Latest values](?help=latest-values): no quotes during the day for Spain; its yield is a monthly average, so the chart ends at the last month published.

## Its own controls

Under Spain's chart in the window, and under "Spain only" on the page, are the controls that set its chart alone: the policy rates and mortgage terms it draws, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in € unless another currency is named by its code (USD20t). On the command line each is written after Spain's prefix, `--es:` or `--esp:`, as in `--es:max:8`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany), [France](?help=france), [Portugal](?help=portugal), [Italy](?help=italy), [the Netherlands](?help=netherlands), [Japan](?help=japan).
