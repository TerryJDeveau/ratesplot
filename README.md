# ratesplot: bond yields and public debt

Government bond yields against public debt, TTM GDP, and interest outlays, for Canada and the
United States, and when asked for the United Kingdom and Germany, on one two-axis chart per
country. The data come from their sources each time: Statistics Canada, the Bank of Canada, FRED,
the U.S. Treasury and the U.S. Census Bureau; the Bank of England and the Office for National
Statistics for the UK; the Deutsche Bundesbank, the ECB and Eurostat for Germany. The history
before the sources' own series (back to 1867 for Canadian federal debt, to about 1700 for the UK's
national debt and GDP, to 1956 for Germany's 10-year yield) is built into the code. So is the
history of the series the program reads from the Bank of England's database, the Bank of
Canada's Valet, FRED, the ECB's Data Portal, Eurostat, the ONS, the Bundesbank and Statistics
Canada (`ratesplot/data/boe/`, `ratesplot/data/boc/`, `ratesplot/data/fred/`, `ratesplot/data/ecb/`,
`ratesplot/data/eurostat/`, `ratesplot/data/ons/`, `ratesplot/data/bbk/`, `ratesplot/data/statcan/`,
one file per series): of each, a drawing asks the source only for the last
two months, or the last 24 for a series that may be revised (the Bank of England's quoted mortgage
rates, the Bank of Canada's brokers' variable rate, FRED's GDP, debt, interest, population and
mortgage rates, the ECB's German debt and mortgage rates, and every Eurostat, ONS and Statistics
Canada series: Germany's, the UK's and Canada's debt, interest, GDP and population). The ONS cannot
be asked for part of a series, so it is asked for the whole, as before, and only its last 24 months
are taken. The Bundesbank's download is whole too, so the last two months of its yields are asked
of its web service, which can be asked from a date; so are Statistics Canada's tables, whose last
24 months are asked of its Web Data Service, one request per table. The CMHC mortgage rate, drawn
only before Canada's posted 5-year rate begins in 1975, is not asked for at all. Nor is a series
whose last two (or 24) months begin more than a year after the chart ends: every value such a
chart draws is built in (a chart may draw a figure dated up to one of its periods after its end,
such as a month's average mortgage rate dated by the month's last day).
A job on GitHub (`.github/workflows/rebake.yml`, run each day at 06:37 UTC) bakes that history
again: a series whose only change is new values is committed straight to `main`; one whose
history changed (a value revised, a date added within it, dates the source no longer gives) goes
to a pull request from the branch `rebake-review`, and merging it accepts the change.

## Three ways to run it

- **The web page** (`ratesplot/web.py`): open <https://ratesplot.streamlit.app> and choose
  the charts in the panel on the left. Drag a box on a chart to zoom to it; buttons move the
  dates and undo a zoom; each date has a calendar; the size keeps its shape when you change
  one side. The page's address holds the chart's settings, so a chart can be bookmarked or
  sent.
  To run it on your own machine: `streamlit run streamlit_app.py`.
- **The desktop window** (`ratesplot/gui.py`): `python ratesplot.py`. It adds the
  mouse wheel and a right-drag pan, and remembers your last settings: each command window
  its own, so several windows can be open at once; a window whose monitor has gone comes back
  at its size on another. The handle between the controls and the charts sets the controls'
  width, and each row of controls takes as many as fit it. "Save log file" saves the
  message log as text (on the page, a button under the log).
- **The command line**: `python ratesplot.py --no-gui [options]`, or any options with the
  window. `python ratesplot.py --help` lists them all; the web page shows the same list.

All three draw the same charts from the same code (`plotting.build_figure`).

When a source does not answer (it is down, or sends a web page such as its maintenance notice
in place of its data), the chart is drawn from the last good copy of that download, which is
kept on disk each time the download succeeds (`%LOCALAPPDATA%\ratesplot\last_good` on Windows,
`~/.cache/ratesplot/last_good` elsewhere); the web page says so above the charts, and the window
in its status line. A Bank of England, Bank of Canada, FRED, ECB, Eurostat, ONS, Bundesbank or
Statistics Canada series with no copy kept is drawn from its history built into the code, to its
last date. A source that does not answer (it times out, refuses the connection, or sends an outage
page or a bot check, as the Bundesbank may behind a VPN) is asked nothing more in that drawing:
each of its series is drawn from its copy or its history built in, and the next drawing asks it
again. The message log gives one warning for each source that failed, with the cause once, the
copies drawn and their dates, and the series drawn from their history built in, grouped by how far
it reaches. A chart that cannot be drawn is left out and named in one line beginning "NOT DRAWN"
(in the window in red and bold, with the status line in red), and the other charts are drawn.
The web page's server keeps its copies only until it restarts. A
curve on the right axis whose source has stopped (or is left with only its baked history) ends a
year after its last figure instead of running on flat to the end of the chart.

The nations' sources are fetched side by side, but each source's server gets one request at
a time from the program, and a request that fails is not made again until the next drawing. A
failed request is asked once more, 2 seconds later, only when its connection drops part way or
the server reports an error of its own. A series whose source has stopped (the fed funds target
before its range, the ECB's minimum bid rate, EONIA) is drawn from its history built in, without
asking. The daily job asks its sources by the same rules.

In the window and on the page a blank field shows in grey the value it stands for (the
automatic start, today's end, each chart's axis limits as drawn); a value typed in is black,
and a number typed without the 0 before its point (`.3`) gets it (`0.3`). A country ticked
becomes the current tab once its chart is drawn; Reset leaves the country boxes as they are.

Right of each country's axis limit is its unit (% for Max and Min, the country's currency for Top
and Bottom, none for a percentage of GDP) and an "All" box. Ticked, the limit goes into every
country's box, and a value typed into any of them goes into the others; the command line writes it
once, for every chart (`--max:8`). Unticked, each box keeps its value. A box emptied unticks its
"All" once Enter is pressed or the box is left. "All" needs two countries ticked and a value in the
box; Top and Bottom take it only as percentages of GDP (`-r`), being each country's own currency
otherwise.

## Setting up

Python 3.12 or later, then:

```
python -m pip install -r requirements.txt
```

## A few options

| | |
|---|---|
| `-c`, `-u`, `--nations:gb,de` | Canada or the United States only (Canada and the U.S. by default); the United Kingdom and Germany are named only by their codes, `--nations:gb`, `--nations:de` or with others `--nations:ca,us,gb,de` (`-c` and `-u` may join them) |
| `-r`, `-p` | debt and interest as % of GDP, or GDP, debt and interest per person |
| `--debt:fnpm`, `--cdn:debt:fp` | debt and interest by level of government, for every chart or for one country's (`f` federal, `p` provincial or state, `m` municipal or local, `n` all but federal; the UK's `f` central, `m` local); in the window and on the page each country's levels are in its own panel, named for its governments |
| `--aggregate:gross,net` | the UK's aggregate debt: `gross`, its general government gross debt (the default, as on the other charts), `net`, its public sector net debt excluding the public sector banks, or both; the other countries have gross debt only |
| `--yields:2,10`, `--no-yields:30` | the yield terms drawn (Canada also 1m, 6m, 1, 3 and 7 years, from 2001; the U.S. also 1m, 6m, 1, 7 and 20 years; the UK 5, 10 and 20; Germany 1, 2, 5, 7, 10, 20 and 30), or those dropped; a chart that has none of the terms named draws no yield, with a warning (`-c --yields:20`) |
| `--policy`, `--mortgages`, `--spreads` | policy rates, mortgage rates (`--mo:30,15`; `prime`, each country's banks' prime rate, Canada's and the U.S.'; the UK's `2f`, `3f`, `5f`, `svr`, the standard variable rate, quoted from 1995 and before that the Bank of England's millennium dataset from 1939, and `tracker`; Germany's fixation bands `1-5`, `5-10`, `over10`), yield spreads (`--sp:10-2`), on the yield axis |
| `--policy:target,market` | the policy rate: `target`, each central bank's official rate (the default: the fed funds target, its range from 2008 drawn as a band, the monthly average before September 1982; Canada's Bank Rate, then its overnight target from 1996; the UK's Bank Rate; Germany's: the Bundesbank's discount rate from 1948, on the days it changed, then the ECB's main refinancing rate from 1999), and `market`, the overnight market's rate around it (the effective fed funds rate, CORRA, SONIA, EONIA then €STR); the legend names the parts of a joined line that the chart shows |
| `--prime:0.5`, `--cdn:prime:-0.25` | the prime rate drawn plus a margin in points (negative allowed), as a variable mortgage priced from it; shown in the legend ("Prime Rate + 0.50") |
| `--tracker:2`, `--uk:tracker:1.25` | the UK's tracker mortgage (the term `tracker`, among the UK's mortgage terms by default): Bank Rate plus a margin in points, 1.75 unless given, from 1997, when the Bank of England first quoted a tracker rate; shown in the legend ("Tracker Mortgage (Bank Rate + 1.75)") |
| `--us:max:8`, `--cdn:yields:2,10` | a value for one country's chart only (its code in front: `ca` or `cdn`, `us`, `gb` or `uk`, `ger` or `deu`; Germany's `de` names it only in `--nations`, since `--de` is `--debt`); a country's own list may be `none` (`--cdn:yields:none`); in the window and on the page each country's terms, levels of government and axis limits (and the UK's aggregate debts) have their own panel, as many to a row as fit |
| `-l` | each line's last value at its end (to three decimals where the third is not 0, as quotes and gilt yields are; a spread to a tenth of a point) |
| `--reg`, `--reg:1` | each right-axis curve fitted by straight pieces, labelled with its growth in %/yr; each piece within 0.3 % of the axis height of the curve (or the percentage given), loosened where monthly figures would otherwise cut a curve into pieces of a few months (the message log says where) |
| `-s:1990`, `-e:2020` | the date window (without `-s` it starts in 2000, or where the chosen curves all have data if later; the year is `DEFAULT_START_FLOOR` in `ratesplot/config.py`) |
| `--no-cur` | without the latest daily and intraday values |

Each rate on the yield axis is drawn across what it applies to: a central bank's rate or a prime
rate holds until it changes, so it runs on to the chart's end; an average, a survey or a market's
overnight rate covers only its own day, week or month, so a missing stretch is a gap and the
line stops where its last period does. Intraday yield quotes (from CNBC's quote feed) and the
projection of each curve to today are provisional, and drawn as such. The subtitle gives the quotes' time in each market's own zone
(Toronto's, New York's, London's, Frankfurt's).

## Layout

`ratesplot/` is the program (its `__init__.py` has the module map); `tools/` holds the checks
used when it is changed (`regress_charts.py`, `verify_cli.py`, `verify_web.py`, `check_sources.py`,
`check_drawn_values.py`, every curve on the yield axis against its sources, `check_reg_labels.py`,
what the regression segments' labels cover, `check_last_good.py`, the charts drawn from the
last good copies with every source cut off, `check_requests.py`, which failed requests are
asked again and when a source is asked nothing more, against a server on the same machine, and
`check_baked.py`, the built-in history's files and how a drawing joins them to what it asks for)
and the bake of the historical data (`bake_archives.py`), which also writes `ratesplot/data/`:
the live sources' history, one file per series (`bake_archives.py --only boe`, `--only boc`,
`--only fred`, `--only ecb`, `--only eurostat`, `--only ons`, `--only bbk`, `--only statcan`), re-baked by running it again or by the daily job
(`rebake.py`); nothing else writes there.
