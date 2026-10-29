# Canada

Canada's chart is drawn while its box is ticked, as it is at the start, beside the United States'. On the command line `--cdn` (or `--canada`) draws Canada's chart alone, `--cdn --us` both, and `--nations:ca,gb` names it with others. Its amounts are in Canadian dollars (C$), its rates in percent a year. This page says what the chart holds for Canada; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP, aggregate public debt and interest on the right axis, and the 3-month, 2-, 5-, 10- and 30-year bond yields on the left; the policy rate, mortgage rates and yield spreads when they are ticked.

- [TTM nominal GDP](?help=gdp), from 1926: Statistics Canada's 1968 national accounts to 1960, its table 36-10-0104 from 1961.
- [Aggregate public debt](?help=debt), from 1867: the federal government's debt alone to 1932, drawn as a dotted curve of its own; all governments' from 1933, from Historical Statistics of Canada, then the national balance sheets from 1961 and Statistics Canada's general government gross debt from 1990.
- [TTM interest outlays](?help=interest), from 1926: the 1968 national accounts, then the sector accounts from 1961 and government finance statistics from 1990.
- [By level](?help=levels): the debt and interest of the federal, provincial or municipal governments, or of the provincial and municipal together (Non-federal), instead of the total.
- [Bond yields](?help=yields), from 1919: the Bank of Canada's, monthly to 2000 (the 30-year from 1919, the 3-month from 1934, the 2-year from 1949, the 5- and 10-year from 1951), every business day from 2001. Every term but the 20-year: the 1-, 3- and 6-month, and the 1-, 2-, 3-, 5-, 7-, 10- and 30-year.
- [Yield spreads](?help=spreads): 10y–2y, 10y–3m and 30y–10y, from 1951.
- [Policy rates](?help=policy-rates): the Bank of Canada's Bank Rate from 1935, its target for the overnight rate from 1996-02-22, and CORRA, the overnight market's rate, from 1997-08-12.
- [Mortgage rates](?help=mortgages): the 5-year from 1951 (CMHC's rate until the banks' posted rate begins in 1975), the posted 3- and 1-year from 1980, the Bank of Canada's estimated 5-year variable rate from 2011-01-06, and the banks' prime rate from 1975, drawn plus a margin with Prime margin. The 5-year is ticked at the start.
- [Per capita](?help=per-capita): divided by Statistics Canada's population, yearly from 1867, quarterly from 1946.
- [Latest values](?help=latest-values): the day's yields quoted by CNBC's feed (all but the 7-year), their time given in Toronto time.

## Its own controls

Under Canada's chart in the window, and under "Canada only" on the page, are the controls that set its chart alone: the yield terms, spreads, policy rates and mortgage terms it draws (only those it has are offered), the prime rate's margin, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in C$ unless another currency is named by its code (USD20t). On the command line each is written after Canada's prefix, `--cdn:` or `--ca:`, as in `--cdn:max:8` or `--cdn:yields:2y,10y`.

## The other nations

[The United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany).
