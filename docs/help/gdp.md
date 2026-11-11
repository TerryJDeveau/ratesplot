# TTM nominal GDP

Each nation's gross domestic product at current prices, over the trailing twelve months (TTM): at each quarter's end, the GDP of the four quarters to that date. It is drawn on the right axis in the nation's own currency, as a step held until the next quarter, and it is the divisor of [As % of GDP](?help=percent-of-gdp). Under that measure GDP itself isn't drawn; under [Per capita](?help=per-capita) it is drawn per person.

How the twelve months are added up depends on how each source gives its quarters. Canada's and the U.S.' quarters are seasonally adjusted at annual rates: each is already a year's worth, so the TTM figure is the mean of four. The UK's quarters are seasonally adjusted but not annualised, and Germany's are neither: each is one quarter's GDP, so the TTM figure is the sum of four, over which the seasons cancel.

## Canada

- **1926 to 1960: the 1968 national accounts.** Statistics Canada's historical tables of the 1968 System of National Accounts: GDP at market prices for each calendar year from 1926 ([36-10-0150](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610015001)), then quarterly at annual rates from 1947 ([36-10-0137](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610013701)), once four quarters are in hand. No longer updated.
- **1961 on.** Statistics Canada's table [36-10-0104](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610010401), GDP at market prices, expenditure-based, current prices, seasonally adjusted at annual rates, quarterly from 1961, millions of dollars. Published about two months after each quarter: the release of 2026-08-28 brought the second quarter of 2026. Each release can revise earlier quarters.

The older accounts are scaled up by as much as 4.1 % over 1957 to 1961 to meet the newer: the median ratio of the two over the years both cover (to 1994), reached year by year over the older one's last five years, so that the line has no jump at the join.

## The United States

- **1947 on.** The Bureau of Economic Analysis' GDP, [GDP on FRED](https://fred.stlouisfed.org/series/GDP), seasonally adjusted at annual rates, quarterly from 1947, billions of dollars. FRED had the second quarter of 2026 on 2026-09-30; the next release is on 2026-10-29. Later releases revise the earlier estimates.

## The United Kingdom

- **1700 to 1954: the Bank of England's dataset.** Its annual estimate of nominal GDP, from 1700, in "A millennium of macroeconomic data", version 3.1 ([research datasets](https://www.bankofengland.co.uk/statistics/research-datasets)), at each year's end. No longer updated (to 2016).
- **1955 on.** GDP at market prices, current prices, seasonally adjusted, [YBHA at the ONS](https://www.ons.gov.uk/economy/grossdomesticproductgdp/timeseries/ybha/ukea), quarterly from 1955, millions of pounds, from the quarterly national accounts. The release of 2026-09-30 brought the second quarter of 2026; the next is on 2026-12-22.

The two are joined as Canada's are; they differ by less than 0.1 % where they meet, so the scaling is slight.

## Germany

- **1950 to 1959: West Germany without the Saarland and West Berlin.** GDP at current prices for each calendar year, at each year's end, billions of euros: the Federal Statistical Office's table 81000-117, in its [Statistischer Bericht on the national accounts](https://www.destatis.de/DE/Themen/Wirtschaft/Volkswirtschaftliche-Gesamtrechnungen-Inlandsprodukt/Publikationen/Downloads-Inlandsprodukt/statistischer-bericht-2180120.xlsx?__blob=publicationFile) (Excel, 50 MB).
- **1960 to 1969: West Germany whole, on the older basis.** The same table's figures with the Saarland and West Berlin, at each year's end.
- **1970 to 1991-09: West Germany whole, after the revision of 2005.** The Office's [revised quarterly results](https://www.destatis.de/DE/Themen/Wirtschaft/Volkswirtschaftliche-Gesamtrechnungen-Inlandsprodukt/Publikationen/Downloads-Inlandsprodukt/inlandsprodukt-revidiert-vierteljahr-2189027919005.xlsx?__blob=publicationFile), not seasonally adjusted, billions of euros, summed over four quarters, the first sum at the end of 1970. They add up to the table's revised years. West Germany's figures have stopped, and are kept as published.
- **1991-12 on: all of Germany.** GDP at market prices, current prices, not seasonally adjusted, Eurostat's dataset [namq_10_gdp](https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table?lang=en), quarterly from 1991, millions in national currency (euros, Deutsche Marks at 1.95583 before 1999), summed over four quarters, the first sum at the end of 1991; the second quarter of 2026 is the latest. Eurostat takes each nation's revisions as the nation publishes them ([Eurostat's notes](https://ec.europa.eu/eurostat/cache/metadata/en/namq_10_esms.htm)).

The Office says its three spans are not fully comparable. Two jumps in the line are changes of territory, not of GDP, and are left as they are: at the end of 1960, from 130.31 to 154.77 billion euros, 6.0 % of it the Saarland and West Berlin (1960 without them is 146.04), and at the end of 1991, unification, from West Germany's 1,391 billion to all of Germany's 1,592 billion. A regression piece over one of them gives a rate that says nothing about growth. The revision at 1970 is no change of territory: it raises 1970 from 345.28 to 360.60 billion, so the older figures are scaled up by as much as 4.4 % over 1965 to 1969 to meet it, reached year by year as Canada's are, so that the line has no jump there and 1970's growth is the older figures' own. Per person, the line's figures to 1959 are the Office's own ([Per capita](?help=per-capita)).

Figures before 1999 are Deutsche Marks converted to euros at 1.95583, as the Office publishes them and Eurostat does in national currency. Eurostat's figures in euros for those years are at each quarter's ECU rate instead (4.6 % lower in 1991, 4.4 % higher in 1995), and are not used.

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.
