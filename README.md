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
  the charts in the panel on the left. Drag a box on a chart to zoom to it, or turn the mouse
  wheel over it to zoom the dates about the pointer; buttons move the dates and undo a zoom;
  each date has a calendar; the size keeps its shape when you change one side. Unzoom goes
  back to the charts before the first zoom or move since the last Reset. The page's
  address holds the chart's settings, so a chart can be bookmarked or
  sent; under the command line its link is in a box with a copy button (the default charts' link
  ends `?chart=`). The page remembers your last chart for your next visit, in a cookie in your
  browser, while "Remember my settings" is ticked, and the panel's width once you drag it; a link
  with a chart in it opens on that chart.
  On a narrow screen (under 700 px, a phone) the page draws the chart 800 x 800 px with larger
  text, unless another size is given; its link and command line still draw the full-size chart.
  To run it on your own machine: `streamlit run streamlit_app.py`.
- **The desktop window** (`ratesplot/gui.py`): `python ratesplot.py`. It adds a
  right-drag pan, and remembers your last settings: each command window
  its own, so several windows can be open at once; a window whose monitor has gone comes back
  at its size on another. Untick "Remember my settings" (on the page too) to draw other charts
  without replacing the settings kept; it is ticked again at every start. Under its command line
  is the same chart's address on the web page, each with its own Copy, and Go opens it in the
  browser. As it opens, the window gives the keyboard back to the window it was started from; a
  click or a turn of the wheel over it takes it (Ctrl+S, with or without Shift or Caps Lock, and F5
  then work). More's windows open over the window, on its monitor. The handle between the controls and the charts sets the controls'
  width, remembered with the settings, and each row of controls takes as many as fit it. "Save log file" saves the
  message log as text (on the page, a button under the log). Its dialog and Export chart's open in
  the folder last saved to, remembered with the settings, and the first time in Documents; never in
  the program's own folder, so nothing saved lands among the repository's files.
- **The command line**: `python ratesplot.py --no-gui [options]`, or any options with the
  window. `python ratesplot.py --help` lists them all; the web page shows the same list.

All three draw the same charts from the same code (`plotting.build_figure`).

The version is shown small at the top left of the window's controls and of the page's sidebar,
with the commit the program was started from (`v6.5, build: 8c3e41b`); `--version` prints it. It is
major.minor: the major goes up when a batch of the plan adds a new type of series, the minor at
each push of a build (`ratesplot.__version__`).

Each chart can be kept as a picture or as the data it shows: in the window "Export chart…"
(Ctrl+S), the type chosen in its dialog; on the page a menu of types beside "Export chart" under
each chart; on the command line `--save:FILE`. PNG is the chart as drawn; JPG, PDF and SVG the same
chart in those formats (PDF and SVG stay sharp at any size). XLSX, CSV and TSV hold the data: the
title and the dates, then a column for each curve as its legend names it, with its unit, and a row
for each date in the window on which any curve has a point, holding the value each line shows on
that date (a rate in force, or the straight line between two points, as drawn; blank where the
chart has no line). The regression segments are fits, not data, and are not written. "XLSX-global"
is one workbook with a sheet for each chart. `--save:rates.png` writes a file for each chart,
named with its country's code (`rates_ca.png`, `rates_us.png`), and opens no window;
`--save:rates.xlsx` writes one workbook, a sheet for each chart.

Resting the pointer on a line for half a second shows, beside it, the line's name and its value
and date, as its end label would write them: in the window, on the page and in the plain
matplotlib windows (`--no-gui`). The pointer is caught within 3 pixels of a line in any direction,
and every line that near is read in the one box, the nearest first: each line's name in its own
colour with its value and date under it, a ring on each line's point, the box bordered in the
nearest line's colour. The read-out follows the pointer along the lines, and goes 2 seconds after
it has left them. A line's value is that of its observation nearer the pointer, never one between two;
a curve drawn as steps (a quarterly figure, a rate held until changed) gives the value in force
on the date under the pointer and the date it was observed ("$26.5T  2020-05-15 (observed
2020-03-31)"); a projection to today, its value on that day, marked "≈" and "(projected)"; an
intraday quote, its time. "Hover read-out" turns it off, as `--no-hover` does; it changes no chart.
In the window it also hides the tips that pop up over the controls with an ⓘ beside them, whose
text a click on the ⓘ shows; the buttons keep theirs.

"Automatic refresh" (`--auto-refresh`, at least `--au`; off by default) does what Refresh does every
5 minutes, or every so many minutes as given (`--au:10`; never fewer than 5): the intraday quotes
of the moment, and anything downloaded over an hour ago fetched again. Outside market hours
(8:00 to 17:00 on weekdays, in each chart's own market's time) it asks for the quotes first and
draws again only when one has changed. It is greyed, its tick kept, where nothing new can come: the
intraday quotes off, an End before today, or no chart showing a yield (or a spread) that the quotes
carry on. In the window and on the page its box and minutes sit with the quotes' box, and the page
says under the charts how often it refreshes. On the command line it draws the plain windows again
while they are open, or with `--save` writes the files again until Ctrl-C. Every file `--save`
writes goes first to a temporary file beside it, swapped in once closed, so a viewer never reads a
half-written file and none is held open between refreshes; a file another program holds (a
workbook open in Excel) is written as `rates_1.xlsx` instead, and that name kept from then on, a
numbered name already there skipped.

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

A control that would change nothing is greyed, its tick or text kept for when it applies again:
% of GDP, Per capita, the levels and the regression segments with no right-axis curve; Max and Min
with nothing on the yield axis, and the yield terms with Bond yields off; the intraday quotes when
the End is more than four days before today and no U.S. chart is shown (the U.S. chart takes the
Treasury's daily yields and debt at any End), and the projections to today when the End is more
than four days back; Blank in a calendar whose field is blank; an "All" box beside a value its box
refuses; and Reset when everything is at its defaults. On the page a country's own section shows
only while its box is ticked, as the window shows a tab only for a ticked country, and keeps its
values for when it is ticked again.

Beside each control is an ⓘ, never greyed. In the window a click on it opens a small panel: what
the control does, its command-line spelling, why it is greyed if it is ("Greyed because “Bond
yields” is unticked."), and, where there is more to say, More, which opens a window of its own
with the whole of it. On the page the ⓘ is Streamlit's tip, which says the same and ends with a
More link that opens the longer text alone in a new tab (`?help=percent-of-gdp`). The longer texts
are in `docs/help/`, one file per topic: % of GDP, and the sources' pages for debt, GDP, interest,
the levels of government, per capita, bond yields, policy rates, mortgage rates, yield spreads and
the latest values, which say where each nation's figures come from, how they are joined and how
soon they are published, with a link to each source. A topic's link to
another opens that topic: in the window in its own window, on the page in a new tab.

Right of each country's axis limit is its unit (% for Max and Min, the country's currency for Top
and Bottom, none for a percentage of GDP) and an "All" box. Ticked, the limit goes into every
country's box, and a value typed into any of them goes into the others; the command line writes it
once, for every chart (`--max:8`). Unticked, each box keeps its value. A box emptied unticks its
"All" once Enter is pressed or the box is left. "All" needs two countries ticked and a value the
box takes. Top and Bottom go to the other countries with their currency: 20t in the U.S. box becomes
`USD20t` in the others.

Top and Bottom may be given in any of the four currencies, its code first: `--top:USD20t`,
`--bottom:EUR50b` (`CAD`, `USD`, `GBP`, `EUR`; `C$`, `US$`, `£` and `€` are accepted too, but a
`$` on a PowerShell or bash command line needs quotes). Each chart converts such a limit into its
own currency at the exchange rate of its end date, the latest on or before it, and the message
log says which rate it used: a chart with a fixed end draws the same every time, one ending today
follows the rate. The rates are FRED's from 1971: the Canadian dollar and the pound daily, the
euro from 1999, and before it the Deutsche mark at its fixed 1.95583 per euro. Before 1971 they
are older rates built into the program: the pound against the U.S. dollar monthly from 1791 (the
Bank of England's millennium dataset); the Canadian dollar from 1858, at its gold par with the
pound to 1912, then each year's average to 1962 (*Historical Statistics of Canada*), then monthly
through the pound; the mark from June 1948, at its official parities to 1962, then monthly
through the pound. A limit whose currency has no rate yet at its chart's end date is left to the
axis, with a warning.

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
| `--policy:target,market` | the policy rate: `target`, each central bank's official rate (the default: the fed funds target, its range from 2008 drawn as a band, in the legend too, the monthly average before September 1982; Canada's Bank Rate, then its overnight target from 1996; the UK's Bank Rate; Germany's: the Bundesbank's discount rate from 1948, on the days it changed, then the ECB's main refinancing rate from 1999), and `market`, the overnight market's rate around it (the effective fed funds rate, CORRA, SONIA, EONIA then €STR), named "Overnight Rate (CORRA)" and the like in the legend and "market (CORRA)" on its box; the legend names the parts of a joined line that the chart shows |
| `--prime:0.5`, `--cdn:prime:-0.25` | the prime rate drawn plus a margin in points (negative allowed), as a variable mortgage priced from it; shown in the legend ("Prime Rate + 0.50") |
| `--tracker:2`, `--uk:tracker:1.25` | the UK's tracker mortgage (the term `tracker`, among the UK's mortgage terms by default): Bank Rate plus a margin in points, 1.75 unless given, from 1997, when the Bank of England first quoted a tracker rate; shown in the legend ("Tracker Mortgage (Bank Rate + 1.75)") |
| `--top:20t`, `--bottom:USD500b` | the right axis's limits (k, m, b, t; billions unsuffixed), in each chart's own currency or in the one named, converted at the rate of the chart's end date; with `-r` a percentage of GDP (`--top:150%`) |
| `--us:max:8`, `--cdn:yields:2,10` | a value for one country's chart only (its code in front: `ca` or `cdn`, `us`, `gb` or `uk`, `ger` or `deu`; Germany's `de` names it only in `--nations`, since `--de` is `--debt`); a country's own list may be `none` (`--cdn:yields:none`); in the window and on the page each country's terms, levels of government and axis limits (and the UK's aggregate debts) have their own panel, as many to a row as fit |
| `-l` | each line's last value at its end (to three decimals where the third is not 0, as quotes and gilt yields are; a spread to a tenth of a point) |
| `--reg`, `--reg:1` | each right-axis curve fitted by straight pieces, labelled with its growth in %/yr; each piece within 0.3 % of the axis height of the curve (or the percentage given), loosened where monthly figures would otherwise cut a curve into pieces of a few months (the message log says where) |
| `-s:1990`, `-e:2020` | the date window (without `-s` it starts in 2000, or where the chosen curves all have data if later; the year is `DEFAULT_START_FLOOR` in `ratesplot/config.py`); no date before 1600-01-01, the earliest a chart shows |
| `--no-cur` | without the latest daily and intraday values |
| `--no-projections` | without the projection of each right-axis curve to today; it has its own switch (`--pro`), and `--no-cur` leaves it on |
| `--save:rates.png` | the charts written to files and no window opened, the format by the extension: `.png`, `.jpg`, `.pdf` or `.svg`, or the data as `.csv` or `.tsv`, a file for each chart (`rates_ca.png` …); `.xlsx`, one workbook with a sheet for each chart (at least `--sa`, since `--s:` is the start) |
| `--no-hover` | without the read-out by the pointer resting on a line (at least `--no-ho`, since `--h` is `--help`) |
| `--version` | the version and the commit, printed (at least `--ver`) |
| `--au`, `--au:10` | the charts drawn again every 5 minutes (or 10, at least 5) as Refresh draws them, outside market hours only when a quote has changed; with `--save`, the files written again until Ctrl-C |

Each rate on the yield axis is drawn across what it applies to: a central bank's rate or a prime
rate holds until it changes, so it runs on to the chart's end; an average, a survey or a market's
overnight rate covers only its own day, week or month, so a missing stretch is a gap and the
line stops where its last period does. Intraday yield quotes (from CNBC's quote feed) and the
projection of each curve to today are provisional, and drawn as such. The subtitle gives the quotes' time in each market's own zone
(Toronto's, New York's, London's, Frankfurt's).

## Layout

`ratesplot/` is the program (its `__init__.py` has the module map); `tools/` holds the checks
used when it is changed (`regress_charts.py`, `verify_cli.py`, `verify_web.py`, `verify_gui.py`, the
window driven from a script, its charts against the command line's and its controls' behaviour, `check_sources.py`,
`check_drawn_values.py`, every curve on the yield axis against its sources, `check_reg_labels.py`,
what the regression segments' labels cover, `check_export.py`, the data Export chart writes
against the lines drawn, `check_refresh.py`, the automatic refresh's rules and the files `--save`
writes again, `check_last_good.py`, the charts drawn from the
last good copies with every source cut off, `check_requests.py`, which failed requests are
asked again and when a source is asked nothing more, against a server on the same machine,
`check_help.py`, the help beside each control: its texts, its topics' files, and a reason given
exactly where a control is greyed, and
`check_baked.py`, the built-in history's files and how a drawing joins them to what it asks for)
and the bake of the historical data (`bake_archives.py`), which also writes `ratesplot/data/`:
the live sources' history, one file per series (`bake_archives.py --only boe`, `--only boc`,
`--only fred`, `--only ecb`, `--only eurostat`, `--only ons`, `--only bbk`, `--only statcan`), re-baked by running it again or by the daily job
(`rebake.py`); nothing else writes there. `docs/help/` holds the longer help texts, one Markdown
file per topic an option names.
