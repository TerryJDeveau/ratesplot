# The United States

The U.S. chart is drawn while its box is ticked, as it is at the start, beside Canada's. On the command line `--us` (or `--usa`) draws the U.S. chart alone, `--cdn --us` both, and `--nations:us,gb` names it with others. Its amounts are in U.S. dollars ($), its rates in percent a year. This page says what the chart holds for the United States; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, aggregate public debt and interest on the right axis, and the 3-month, 2-, 5-, 10- and 30-year bond yields on the left; the policy rate, mortgage rates and yield spreads when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1947: the Bureau of Economic Analysis' GDP, read from FRED.
- [Aggregate public debt](?help=debt), from 1966: the federal government's total public debt, from the Treasury, plus the state and local governments' debt securities and loans, from the Federal Reserve's Financial Accounts. What one government owes another isn't netted out, as it is in the other three nations' totals.
- [TTM interest outlays](?help=interest), from 1947: the national accounts' interest payments of all levels of government.
- [By level](?help=levels): the debt and interest of the federal, state or local governments, or of the state and local together, instead of the total; the split between state and local comes from yearly figures.
- [Bond yields](?help=yields), from 1962: the Treasury's constant-maturity yields, daily, read from FRED; from 1962 the 1-, 5-, 10- and 20-year, the others later. Every term but the 3-year: the 1-, 3- and 6-month, and the 1-, 2-, 5-, 7-, 10-, 20- and 30-year.
- [Yield spreads](?help=spreads): 10y–2y from 1976-06, 30y–10y from 1977-02 and 10y–3m from 1981-09, daily.
- [Policy rates](?help=policy-rates): the effective federal funds rate's monthly average from 1954-07, the Federal Reserve's target from 1982-09-27 and its target range from 2008-12-16, drawn as a band; and the effective federal funds rate, the overnight market's rate, from 1954-07-01.
- [Mortgage rates](?help=mortgages): Freddie Mac's survey, the 30-year fixed rate from 1971-04-02 and the 15-year from 1991-08-30; and the bank prime loan rate from 1955-08-04, drawn plus a margin with Prime margin. The 30-year is ticked at the start.
- [Per capita](?help=per-capita): divided by the Bureau of Economic Analysis' population, quarterly from 1947.
- [Latest values](?help=latest-values): for the days FRED doesn't have yet, the Treasury's own daily yields, and its daily Debt to the Penny for federal debt; then the day's yields quoted by CNBC's feed, their time given in New York time.

## Its own controls

Under the U.S. chart in the window, and under "United States only" on the page, are the controls that set its chart alone: the yield terms, spreads, policy rates and mortgage terms it draws (only those it has are offered), the prime rate's margin, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in $ unless another currency is named by its code (CAD20t). On the command line each is written after the U.S. prefix, `--us:`, as in `--us:max:8` or `--us:yields:2y,10y`.

## The other nations

[Canada](?help=canada), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany).
