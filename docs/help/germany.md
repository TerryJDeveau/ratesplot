# Germany

Germany's chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:de` (or `ger`, `deu`) alone or with others, as in `--nations:ca,us,de`. Its amounts are in euros (€), its rates in percent a year. Figures before 1999 are Deutsche Marks converted to euros at 1.95583, as the ECB and Eurostat publish them. Germany's GDP, debt and interest begin with unification; West Germany's, from 1950, are planned. This page says what the chart holds for Germany; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, debt and interest on the right axis, and the 2-, 5-, 10- and 30-year bond yields on the left; the policy rate, mortgage rates and yield spreads when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1991: Eurostat's quarterly national accounts.
- [Aggregate public debt](?help=debt), from 1991: general government consolidated gross debt, the ECB's year ends to 1999, Eurostat's quarters from 2000.
- [TTM interest outlays](?help=interest), from 1995: general government interest payable, Eurostat's years to 2001, its quarters from 2002.
- [By level](?help=levels): the debt and interest of the federal government, the Länder or local government, or of the Länder and local government together, instead of the total, from Eurostat's figures by subsector.
- [Bond yields](?help=yields), from 1956: the Bundesbank's. The yield of public debt securities outstanding, drawn as the 10-year, from 1956-05; then the yields of Federal securities from its term structure, the 1-, 2-, 5-, 7- and 10-year from 1972-09, the 20-year from 1986-06 and the 30-year from 2000-01, at month ends until they are daily from 1997-08-07 (the 30-year from 2000-08-01). No 1-, 3- or 6-month or 3-year.
- [Yield spreads](?help=spreads): 10y–2y from 1972-09 and 30y–10y from 2000-01, both ticked at the start.
- [Policy rates](?help=policy-rates): the Bundesbank's discount rate from 1948-07 (the Bank deutscher Länder's until 1957), then the ECB's main refinancing rate from 1999-01-01; the overnight market's rate, EONIA from 1999-01-04, €STR from 2019-10-01. From 1999 the rates are the euro area's.
- [Mortgage rates](?help=mortgages): the ECB's rates on new loans to households in Germany for house purchase, fixed for over 1 to 5, over 5 to 10 and over 10 years, monthly from 2000-01. All three are ticked at the start.
- [Per capita](?help=per-capita): divided by Eurostat's population, quarterly from 1991.
- [Latest values](?help=latest-values): the Bundesbank publishes the day's yields during the day, so once they are out the chart ends at them; before then, the day's yields quoted by CNBC's feed, their time given in Frankfurt time.

## Its own controls

Under Germany's chart in the window, and under "Germany only" on the page, are the controls that set its chart alone: the yield terms, spreads, policy rates and mortgage terms it draws (only those it has are offered), its levels of government, and the limits of its axes: Min and Max on the left, Top and Bottom on the right, in € unless another currency is named by its code (USD20t). On the command line each is written after Germany's prefix, `--ger:` or `--deu:`, as in `--ger:max:8` or `--ger:yields:2y,10y`; never `--de:`, which the command line reads as `--debt:`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom).
