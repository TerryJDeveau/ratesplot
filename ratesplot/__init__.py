"""ratesplot: Canadian/U.S./UK/German bond yields vs public debt, GDP and interest charts.

Package layout
--------------
config            constants, per-country metadata, HTTP session, PlotConfig; the
                  nations (Nation, NATIONS) and the choices each may have its own of
frames            small DataFrame helpers shared by the layers below
http              GET helpers (a failed request asked once more only if dropped or 5xx; a
                  source that does not answer asked nothing more in the drawing), FRED CSV
                  reader, BoC CSV parser, session download cache, the message log's line for
                  each real download and one warning per source that fails, "NOT DRAWN",
                  one request at a time per host
console           printed output routed by thread (the message log; the trial pass discarded)
axes              y-axis configuration, limit padding, currency and percent formatters
legend            legend auto-placement, title/subtitle/layout finishing
occupancy         every drawn line sampled into a grid of the axes, for finding free room
endlabels         -l: each line's last value at its end; widens the date axis to fit
regression        --reg: the right-axis curves fitted by straight pieces on their log
                  axis, each labelled with its growth in %/yr
joins             a nation's sources joined into one series (baked history to live
                  tables), and the series laid on the chart's dates
cdn_data          Bank of Canada / Statistics Canada fetch, splice and align; both
                  sources' series read through their bake and recent part
                  (boc_valet_series, also for rates; statcan_table)
cdn_archive_data  baked historical CDN rows: debt, GDP, interest, population, yield
                  stand-ins (rewritten by tools/bake_archives.py)
cdn_hist_yields   transcribed Bank of Canada historical yield tables (1919-2000)
bake              the bake of the historical data (run by tools/bake_archives.py), and of
                  the live sources' history into data/
baked             the live sources' history as data files (data/SOURCE/CODE.csv, batch
                  19.2): their form, their reading, and each joined to the recent part a
                  drawing asks for (the Bank of England's database, the Bank of
                  Canada's Valet, FRED, the ECB's Data Portal, Eurostat, the ONS, the
                  Bundesbank, Statistics Canada); nothing asked for a chart that
                  ends more than a year before the recent part
us_data           FRED fetch for U.S. yields and macro series; every FRED series read
                  through its bake and recent part (fred_series, also for rates and cdn_data)
latest            --cur: newer values than the regular series (Treasury daily yields and
                  debt, intraday quotes)
us_archive_data   baked Census counts of U.S. state and local debt apart
                  (rewritten by tools/bake_archives.py)
uk_data           Bank of England database / ONS fetch for the UK's yields and macro
                  series (batch 3); both sources' series read through their bake and
                  recent part (iadb_series, also for rates; ons_series)
de_data           Bundesbank / ECB / Eurostat fetch for Germany's yields and macro
                  series (batch 4); the Bundesbank's, the ECB's and Eurostat's series
                  read through their bake and recent part (bundesbank_series;
                  ecb_series, also for rates; eurostat_series)
de_archive_data   baked German history: the Bundesbank's yield on public debt
                  securities before 1972 (rewritten by tools/bake_archives.py)
uk_archive_data   baked UK history from the Bank of England's "A millennium of
                  macroeconomic data" (rewritten by tools/bake_archives.py)
rates             the yield axis's other curves, each only when chosen: policy rates,
                  mortgage rates, yield spreads
fx                exchange rates, for Top and Bottom given in another currency
                  (batch 18.3): FRED's from 1971, older ones baked (18.4)
measures          the right-axis measure: dollars, % of GDP (-r) or per person (-p)
export            Export chart (batch 11.1): a chart as an image, or the data it shows
                  (XLSX, CSV, TSV), the format by the file's extension; each curve
                  marked as plotting draws it
hover             the hover read-out (batch 11.2): where each line runs on the picture
                  and what it says by the pointer, the nearest line within 3 px; its
                  timing; the plain matplotlib windows' (the window and the page read it)
refresh           the automatic refresh (batch 11.3): whether each tick draws again
                  (within market hours always, outside them when a quote has
                  changed); the plain matplotlib windows' timer
plotting         line drawing, draw_country, build_figure (no pyplot), COUNTRIES, run_cdn / run_us / run_uk / run_de
options           the option table, value parsers/formatters, choices <-> PlotConfig, --help text
frontend          what the window and the web page share without a GUI toolkit: starting
                  choices, remembered settings, each nation's own controls, option
                  help, PNG bytes and file names
gui               the interactive window (default; --no-gui for plain matplotlib windows)
web               the web page (Streamlit; streamlit_app.py): the same charts in a browser
cli               argument parsing (driven by the options table) and main()

Dependency direction is strictly downward: cli -> gui -> {frontend, options,
plotting, http}; web -> {cli (its token matching), frontend, options,
plotting, http}; cli -> {options, plotting, http}; frontend -> {options,
config}; plotting -> {axes, legend, endlabels, regression, measures, rates,
cdn_data, us_data, uk_data, de_data, joins, latest, baked} -> {frames, http} -> config;
{cdn_data, uk_data, de_data} -> joins; {cdn_data, uk_data, us_data, de_data} -> baked -> {http, config};
rates -> {cdn_data, uk_data, us_data, de_data, baked, http}; cdn_data -> us_data (FRED's
Canadian GDP); plotting -> fx -> {us_data, cdn_archive_data, uk_archive_data};
plotting, gui, web, http -> console;
us_data -> latest; legend -> {axes, endlabels, regression, occupancy};
regression -> occupancy; options -> config; {plotting, legend, options, cli,
gui, web} -> export -> config; {plotting, gui, web} -> hover -> {export, legend};
{plotting, cli, gui, web} -> refresh -> {latest, http, config}. Data modules never import
plotting. Nothing imports web or gui, and cli imports gui only when the
window is opened, so --no-gui and the web page never load tkinter.
"""

# The version (batch 11.7; Terry, 2026-10-27): major.minor. The major goes up when a batch of the plan adds a new
# type of series (CPI, population and the like), batch 11 being 6; the minor goes up by one at each push of a
# build, in a commit of its own made before the push (the daily data job's commits leave it). It counts from 0 at
# the first work on batch 11: its four pushes of 2026-10-27 made 6.4. Shown with the commit the program was
# started from (frontend.version_text).
__version__ = "6.10"
