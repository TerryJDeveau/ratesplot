# The United Kingdom

The UK's chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:gb` (or `uk`) alone or with others, as in `--nations:ca,us,gb`. Its amounts are in pounds sterling (£), its rates in percent a year. This page says what the chart holds for the UK; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, gross debt and interest on the right axis, and the 5-, 10- and 20-year gilt yields on the left; the policy rate, mortgage rates and yield spreads when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1700: the Bank of England's dataset "A millennium of macroeconomic data", yearly, to 1954; the ONS's quarterly GDP from 1955.
- [Aggregate public debt](?help=debt), from 1691: central government's national debt at each financial year's end, from the Bank of England's dataset, drawn as a dotted curve of its own until general government gross debt, the Maastricht measure, begins in March 1975 (the ONS, monthly). Public sector net debt excluding the public sector banks, also from March 1975, is drawn when it is ticked under Aggregate debts: only the UK has two measures to choose from.
- [TTM interest outlays](?help=interest), from 1946: the ONS's general government interest and dividends paid to the private sector and the rest of the world.
- [By level](?help=levels): the debt and interest of central or local government instead of the total. The devolved governments of Scotland, Wales and Northern Ireland are inside central government in the UK's accounts.
- [Bond yields](?help=yields), from 1935: the 5-, 10- and 20-year only, all three ticked at the start. The 10-year from 1935 and the 20-year from 1963, monthly, from the Bank of England's dataset; then the Bank's daily par yields, the 10-year from 1993-11, the 5-year from 1993-12 and the 20-year from 2000-01.
- [Yield spreads](?help=spreads): 20y–10y from 1963 and 10y–5y from 1993-12, both ticked at the start.
- [Policy rates](?help=policy-rates): Bank Rate from 1833, on each day it changed, and SONIA, the overnight market's rate, from 1997-01-02.
- [Mortgage rates](?help=mortgages): the Bank of England's quoted 2-, 3- and 5-year fixed rates and standard variable rate from 1995-01, the standard variable rate carried back to 1939 by the Bank's dataset; and a tracker rate from 1997-01-01, Bank Rate plus the margin in Tracker margin. All five are ticked at the start.
- [Per capita](?help=per-capita): divided by the population in the Bank of England's dataset from 1707, the ONS's mid-year estimates from 1955.
- [Latest values](?help=latest-values): the day's 5-, 10- and 20-year yields quoted by CNBC's feed, their time given in London time.

## Its own controls

Under the UK's chart in the window, and under "United Kingdom only" on the page, are the controls that set its chart alone: the yield terms, spreads, policy rates and mortgage terms it draws (only those it has are offered), the tracker's margin, gross or net debt or both under Aggregate debts, its levels of government, and the limits of its axes: Min and Max on the left, Top and Bottom on the right, in £ unless another currency is named by its code (USD20t). On the command line each is written after the UK's prefix, `--uk:` or `--gb:`, as in `--uk:max:8` or `--uk:aggregate:gross,net`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [Germany](?help=germany).
