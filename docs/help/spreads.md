# Yield spreads

The difference between two of a nation's bond yields, the first less the second, in percentage points, drawn as thick lines on the left axis. Where a spread is below zero, the shorter term yielding more than the longer (an inverted curve), the stretch between it and zero is shaded. Yield spreads draws them; Spreads chooses the pairs: by default 10y–2y, 10y–3m and 30y–10y, and for the UK and Germany their own (10y–5y and 20y–10y; 10y–2y and 30y–10y). Each nation's panel has a box for each of these and for 2y–3m, 5y–2y, 30y–2y and 20y–5y that its terms allow, and the command line takes any pair of the terms in [Bond yields](?help=yields), as `--spreads:7-1m`. The colours go to the spreads drawn, in the order given.

Each spread is taken from the yields as the chart has them: the same sources and dates, a value wherever both terms have one. So a spread is a monthly step where either of its yields is monthly, and with [the latest values](?help=latest-values) it runs on to the day's quotes. A pair with a term a nation doesn't have is named in the log and left off its chart. An end label gives a spread in basis points, hundredths of a percentage point: "+47 pts" is 0.47 points.

## Canada

The Bank of Canada's yields: 10y–2y, 10y–3m and 30y–10y from 1951 as monthly steps, from 2001 daily. Before 2001 the 2-year is the 1 to 3 year average until 1982-05, the 10-year the 5 to 10 year average and the 30-year the over-10-year average, so the spreads of those years are between those averages; from 2001 the 30-year is the long-term benchmark.

## The United States

The Treasury's constant-maturity yields, daily: 10y–2y from 1976-06, 30y–10y from 1977-02, 10y–3m from 1981-09. The program's 10y–2y and 10y–3m agree with FRED's own spread series ([T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y), [T10Y3M](https://fred.stlouisfed.org/series/T10Y3M)) on every day but five, all in the 1990s, on which FRED's spread is not the difference of the yields it publishes; the program's source checks compare them again.

## The United Kingdom

The Bank of England's yields: 20y–10y from 1963 as monthly steps until 1999, daily from 2000; 10y–5y daily from 1993-12.

## Germany

The Bundesbank's yields: 10y–2y from 1972-09 as month-end steps, daily from 1997-08; 30y–10y from 2000-01, daily from 2000-08.

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.
