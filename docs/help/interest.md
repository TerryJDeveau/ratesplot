# TTM interest outlays

The interest each nation's governments pay on their debt over the trailing twelve months (TTM): at each quarter's end, the interest of the four quarters to that date. It is drawn on the right axis in the nation's own currency, as a step held until the next quarter, as a share of GDP under [As % of GDP](?help=percent-of-gdp) and per person under [Per capita](?help=per-capita). With levels of government ticked, each level is drawn instead of the total: [By level](?help=levels).

Each source's quarters are added up as [GDP's](?help=gdp) are: Canada's oldest and the U.S.' are at annual rates, so the TTM figure is the mean of four; Canada's since 1990, the UK's and Germany's are each one quarter's interest, so it is the sum of four. Canada's total since 1990 and the UK's leave out interest one government pays another; the U.S. total is the national accounts' interest payments of all its governments together.

## Canada

- **1926 to 1960: the 1968 national accounts.** Statistics Canada's historical tables of government revenue and expenditure in the 1968 System of National Accounts: interest on the public debt of all governments for each calendar year from 1926 ([36-10-0177](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610017701)), then quarterly at annual rates from 1951 ([36-10-0142](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610014201), which has no figures for 1947 to 1949). Archived.
- **1961 to 1990: the sector accounts.** Statistics Canada's table [36-10-0245](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610024501), sector accounts of all levels of government, quarterly at annual rates, 1961 to 2012. Archived.
- **1990 on: government finance statistics.** Statistics Canada's table [10-10-0015](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1010001501), the statement of government operations, consolidated government, its expense "Interest", quarterly from 1990, millions of dollars, not annualised. Published about three months after each quarter: the release of 2026-09-25 brought the second quarter of 2026. The first twelve months from it end with 1990.

Each older source is scaled to meet the newer one by the median ratio of the two over the years both cover (to 1994), reached year by year over the older one's last five years, so that the line has no jump at the join: the 1968 accounts by as much as 1.3 % over 1957 to 1961, the sector accounts by as much as 1.0 % over 1986 to 1990. The chart's label is "TTM Interest Payable".

## The United States

- **1947 on.** The Bureau of Economic Analysis' government current expenditures on interest payments, all levels of government, [A180RC1Q027SBEA on FRED](https://fred.stlouisfed.org/series/A180RC1Q027SBEA), seasonally adjusted at annual rates, quarterly from 1947, billions of dollars (national accounts table 3.1). It equals the federal government's interest payments ([A091RC1Q027SBEA](https://fred.stlouisfed.org/series/A091RC1Q027SBEA)) plus state and local governments' ([B111RC1Q027SBEA](https://fred.stlouisfed.org/series/B111RC1Q027SBEA)) in every quarter. These are interest payments as paid; the interest the governments receive is a separate line of the accounts, not subtracted. FRED had the second quarter of 2026 on 2026-09-30; the next release is on 2026-10-29.

## The United Kingdom

- **1946 on.** General government interest and dividends paid to the private sector and the rest of the world, [NMYX at the ONS](https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/nmyx/pusf), quarterly from 1946, millions of pounds, not seasonally adjusted, from the public sector finances. Paid outside general government, so consolidated; the chart's label is "TTM Interest Paid (consolidated)". The release of 2026-10-21 brought the third quarter of 2026; the next is on 2026-11-20.

## Germany

- **1995 to 2001: years.** General government interest payable (D.41), annual, Eurostat's dataset [gov_10dd_edpt1](https://ec.europa.eu/eurostat/databrowser/view/gov_10dd_edpt1/default/table?lang=en) (government deficit, debt and associated data).
- **2002 on: quarters.** General government interest payable (D.41), not seasonally adjusted, Eurostat's dataset [gov_10q_ggnfa](https://ec.europa.eu/eurostat/databrowser/view/gov_10q_ggnfa/default/table?lang=en), quarterly from 2002, millions of euros. Eurostat releases each quarter about 112 days after it ends ([Eurostat's notes](https://ec.europa.eu/eurostat/cache/metadata/en/gov_10q_ggnfa_esms.htm)); the second quarter of 2026 is the latest.

The years agree with the sums of their quarters where both exist, so no scaling is needed. Figures before 1999 are Deutsche Marks converted to euros at 1.95583, as Eurostat publishes them.

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program asks the source for its figures from 24 months before the last one it holds, since revisions reach that far back, and draws the older ones from what it holds. If the source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of England's dataset) are kept as they were last published.
