# Yield spreads

The difference between two of a nation's bond yields, the first less the second, in percentage points, drawn as thick lines on the left axis. Where a spread is below zero, the shorter term yielding more than the longer (an inverted curve), the stretch between it and zero is shaded. Yield spreads draws them; Spreads chooses the pairs: by default 10y–2y wherever a nation has both terms, the UK 10y–5y (it has no 2-year), Italy, Spain and the Netherlands none (one term each). 10y–3m, which forecasts recessions better in the research (the New York Fed's model uses it), is a box away. For the euro area's nations the spread most watched is the 10-year over Germany's, which [the comparison chart](?help=compare) draws with Germany as the base nation. Each nation's panel has a box for each of these and for 30y–10y, 2y–3m, 5y–2y, 30y–2y, 20y–10y and 20y–5y that its terms allow, and the command line takes any pair of the terms in [Bond yields](?help=yields), as `--spreads:7-1m`, the real ones too: `--spreads:10y-r10` is a nominal yield less the real one. The colours go to the spreads drawn, in the order given.

Each spread is taken from the yields as the chart has them: the same sources and dates, a value wherever both terms have one. So a spread is a monthly step where either of its yields is monthly, and with [the latest values](?help=latest-values) it runs on to the day's quotes. A pair with a term a nation doesn't have is named in the log and left off its chart. An end label gives a spread in basis points, hundredths of a percentage point: "+47 pts" is 0.47 points.

## Canada

10y–2y ticked at the start; 10y–3m, 30y–10y, 2y–3m, 5y–2y, 30y–2y and 10y–5y offered, Canada having no 20-year. The Bank of Canada's yields: monthly steps from 1951 (2y–3m and 30y–2y from 1949), daily from 2001.

Before 2001 the 2-year is the 1 to 3 year average until 1982-05, the 5-year the 3 to 5 year average until 1980-10, the 10-year the 5 to 10 year average and the 30-year the over-10-year average, so the spreads of those years are between those averages; from 2001 the 30-year is the long-term benchmark.

## The United States

10y–2y ticked at the start; 10y–3m, 30y–10y, 2y–3m, 5y–2y, 30y–2y, 10y–5y, 20y–10y and 20y–5y offered. The Treasury's constant-maturity yields, daily: 10y–2y from 1976-06, 30y–10y from 1977-02, 10y–3m from 1981-09.

The program's 10y–2y and 10y–3m agree with FRED's own spread series ([T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y), [T10Y3M](https://fred.stlouisfed.org/series/T10Y3M)) on every day but five, all in the 1990s, on which FRED's spread is not the difference of the yields it publishes; the program's source checks compare them again.

## The United Kingdom

10y–5y ticked at the start, the UK having no 2-year; 20y–10y and 20y–5y offered. The Bank of England's yields: 10y–5y daily from 1993-12; 20y–10y from 1963 as monthly steps until 1999, daily from 2000; 20y–5y from 1993-12, a monthly step until 1999.

## Germany

10y–2y ticked at the start; 30y–10y, 5y–2y, 30y–2y, 10y–5y, 20y–10y and 20y–5y offered (no 3-month, so no 10y–3m or 2y–3m). The Bundesbank's yields: month-end steps from 1972-09, daily from 1997-08; the pairs with the 20-year from 1986-06, those with the 30-year from 2000-01, daily from 2000-08.

## France

10y–2y ticked at the start; 30y–10y, 5y–2y, 30y–2y, 10y–5y, 20y–10y and 20y–5y offered (no 3-month). The Banque de France's yields, daily: any two of its terms from 2004-11, the pairs with the 30-year from 2006-10. Before 2004-11 the 10-year is a monthly average and no other term exists, so no spread is drawn there.

## Portugal

10y–2y ticked at the start; 5y–2y and 10y–5y offered. The Banco de Portugal's yields, daily, from 1993-07 (the 5-year's pairs from 1994-02), broken where the 2-year has gaps: several months a year before 1998, and 2002-07 to 2003-02. In 2011 and early 2012 the 2-year yielded up to 8 points more than the 10-year.

## Italy, Spain and the Netherlands

None of their own: each has the 10-year alone, so there is no pair. The spread watched for them is the 10-year over Germany's, which [the comparison chart](?help=compare) draws with Germany as the base nation.

## Japan

10y–2y ticked at the start; 30y–10y, 5y–2y, 30y–2y, 10y–5y, 20y–10y and 20y–5y offered (no 3-month). The Ministry of Finance's yields, daily: 5y–2y from 1974-09-24, 10y–2y and 10y–5y from 1986-07-05, 20y–10y and 20y–5y from 1986-12-01, 30y–10y and 30y–2y from 1999-09-02.

So 5y–2y is the one pair drawn before 1986. There are no quotes during the day for Japan: each spread ends at the Ministry's last day, the day before.

## How the program keeps these figures

Each source's figures are kept in the program as the source published them. A job on GitHub asks every live source each day and adds the new figures; a revision of older ones waits for review before it is taken. When a chart is drawn, the program takes only the newest figures from each source and draws the older ones from what it holds: those from 24 months before the last figure it holds where the source revises its figures (GDP, debt, interest, population and the mortgage rates from surveys), from two months before where it doesn't (the yields, and the rates that are set or traded). If a source doesn't answer, the chart is drawn from what the program holds, with a warning naming the source and its last date. Statistics Canada is checked once a day: on a day it doesn't answer, it is asked nothing more until the next day in Ottawa, and where another source publishes the same figures (the consumer price index at the Bank of Canada, GDP in the IMF's copy at FRED, interest, consolidated and federal, at the IMF itself), that source's newer figures follow Statistics Canada's last, and the warning names them. The sources that have stopped (Statistics Canada's old tables, Historical Statistics of Canada, the Bank of Canada's historical tables, the Bank of England's dataset, and the series the Federal Reserve, the Bundesbank and the ECB no longer update) are kept as they were last published, and asked nothing.
