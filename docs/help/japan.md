# Japan

Japan's chart is drawn only when it is asked for: while its box is ticked, or when the command line names it, `--nations:jp` (or `jpn`) alone or with others, as in `--nations:ca,us,jp`. Its amounts are in yen (¥), its rates in percent a year. This page says what the chart holds for Japan; the page of each curve, linked below, gives its sources in full.

## What the chart draws

At the start it draws GDP and debt on the right axis, and the 1-, 3-, 10- and 30-year bond yields with the 10-year less 2-year spread on the left; the policy rate, inflation, the price index or the population when they are ticked. No interest is drawn: Japan publishes no quarterly figures of it.

- [TTM nominal GDP](?help=gdp), from 1994-Q4: the mean of four quarters' annual rates of the Cabinet Office's nominal GDP, seasonally adjusted, as FRED carries it ([JPNNGDP](https://fred.stlouisfed.org/series/JPNNGDP), from 1994-Q1; equal to the Cabinet Office's own table in all 131 quarters to 2026-Q3).
- [Aggregate public debt](?help=debt), from 1980: general government's loans and debt securities in the Bank of Japan's flow of funds, at the end of each fiscal year (March) from 1980 to 1997, then at each quarter's end from 1997-Q4. In 2026-Q2 they were ¥1,273.8 trillion, 185 % of GDP. The flow of funds does not consolidate the levels of government: a loan from one to another is in both the lender's assets and the borrower's debt.
- [TTM interest outlays](?help=interest): not drawn. Japan's interest paid is published yearly, by fiscal year, in the Cabinet Office's national accounts; there are no quarterly figures (the IMF's quarterly government finance statistics hold none for Japan).
- [Balance of payments](?help=payments), from 1996-01: the Bank of Japan's balance of payments (the IMF's sixth manual), monthly, not seasonally adjusted: the current account's credits (goods exports, services, primary and secondary income received) and debits, or exports and imports of goods and services; the twelve-month sums begin in 1996-12. Credits less debits equal the Bank's current account balance in every month.
- [By level](?help=levels): the debt of central or local government instead of the total, from the same flow of funds, at the same dates. Japan has no state level; its social security funds are no level of the chart. In 2026-Q2 central government owed ¥1,113.9 trillion and local governments ¥156.8 trillion; with the social security funds' ¥3.1 trillion they add up to the total exactly. No interest by level.
- [Bond yields](?help=yields): the Ministry of Finance's yields of Japanese government bonds at constant maturities, daily: the 1-, 2-, 3-, 5- and 7-year from 1974-09-24, the 10-year from 1986-07-05, the 20-year from 1986-12-01 and the 30-year from 1999-09-02. Its 15-, 25- and 40-year terms are not drawn: the program has no such term. No real yields.
- [Policy rates](?help=policy-rates): the Bank of Japan's uncollateralized overnight call rate, its operating target most years since 1995 and since 2024: daily from 1998-01-05, its monthly averages from 1985-07 before, and the collateralized call rate's monthly averages from 1960-01 before that. The Bank publishes no series of its target itself. The call rate is also Japan's overnight market rate, so "market" alone draws the same rate, and with "target" ticked it is drawn once.
- [Inflation](?help=inflation), from 1956-01: the 12-month rise of Japan's consumer price index, all items, as the IMF publishes it. The consumption tax's rise of 2014-04 shows as a step a year long.
- [Mortgage rates](?help=mortgages): none for Japan. Its source, the Japan Housing Finance Agency, is not a host the program asks.
- [Per capita](?help=per-capita): divided by the population the Population box draws.
- [Inflation adjusted](?help=constant-prices): at the consumer prices of one month, by the same index, from 1955-01.
- [Price index (CPI)](?help=price-index): the IMF's consumer price index for Japan, all items, 2020 = 100, monthly from 1955-01; unadjusted; no seasonally adjusted index is offered.
- [Population](?help=population): the World Bank's midyear estimates on FRED ([POPTOTJPA647NWDB](https://fred.stlouisfed.org/series/POPTOTJPA647NWDB)), yearly from 1960, each year's drawn at its middle.
- [Latest values](?help=latest-values): no quotes during the day for Japan; its yields end at the Ministry's last day, the day before.

## Its own controls

Under Japan's chart in the window, and under "Japan only" on the page, are the controls that set its chart alone: the policy rates it draws, its levels of government, and the [limits of its axes](?help=limits): Min and Max on the left, Top and Bottom on the right, in ¥ unless another currency is named by its code (USD20t). On the command line each is written after Japan's prefix, `--jp:` or `--jpn:`, as in `--jp:max:8`.

## The other nations

[Canada](?help=canada), [the United States](?help=united-states), [the United Kingdom](?help=united-kingdom), [Germany](?help=germany), [France](?help=france), [Portugal](?help=portugal), [Italy](?help=italy), [Spain](?help=spain), [the Netherlands](?help=netherlands).
