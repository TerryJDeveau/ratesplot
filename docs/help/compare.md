# Compare the nations

A chart of its own after the nations' charts, under a tab named Compare: one measure, with a curve for each nation ticked, each in its own colour (Canada red, the United States blue, the United Kingdom purple, Germany near-black). Ticking Compare the nations, under Country selection, adds the chart and brings its tab to the front; the nations' charts are left as they are. It is a prototype (2026-11-11): what it draws and how it is laid out are open to change once it has been tried.

The measure is chosen by the boxes of the block Comparison chart, one at a time, under three headings: Bond yields, Real bond yields (inflation-linked) and Other measures. The block is shown while the Compare tab is in front, and there the curves' boxes and the rates on the yield axis are left out, since they do not change this chart; back on a nation's tab they return as they were, and the comparison's block is left out.

- **a yield term**, the 10-year by default: each nation's yield of that term, as its own chart draws it (Canada's monthly history before 2001 in steps, the daily yields after, the day's quotes with the [latest values](?help=latest-values)). A nation without the term is left off, with a note in the message log: the UK has no 2-year yield, Canada no 20-year. The [real yields](?help=yields) are terms too.
- **Policy rate**: each central bank's [policy rate](?help=policy-rates), its target, held in steps from each change; the U.S. target range as a band.
- **Inflation**: each nation's [inflation](?help=inflation), the consumer price index's rise over twelve months.
- **Public debt**, **TTM GDP**, **TTM interest paid on public debt**: each nation's aggregate (general government) [debt](?help=debt), [GDP](?help=gdp) or [interest](?help=interest), in total, not by level of government. [As % of GDP](?help=percent-of-gdp) gives debt and interest as a share of GDP, which needs no currency; GDP, -r's divisor, is then compared as an amount. Otherwise the amounts are in one currency: the [master currency](?help=master-currency) when one is ticked, else the U.S. dollar, each nation's converted at the rate of the End date, which the message log gives. [Per capita](?help=per-capita) and [inflation adjusted](?help=constant-prices) measure them as on the nations' charts, each nation's at its own consumer prices. The [projections](?help=projections) carry each on to today, faint.
- **Population**: each nation's [population](?help=population), in persons, the same under every measure.

The dates, the [line labels](?help=end-labels), the [regression segments](?help=regression) (for the amounts and the population), the [daily values](?help=daily) and the [hover read-out](?help=hover) are the ones every chart shares. What a nation's chart chooses for itself under its tab (its terms, its levels, its Min, Max, Top and Bottom) does not reach this chart, so its axes are fitted to its curves; dragging a box on it, or panning it, moves the dates alone. Export chart writes its curves named for their nations ("Canada: 10-Year Yield").

The chart reads what the nations' charts have already downloaded, so it asks no source for anything new.

## Against a base nation

Ticking **Base nation**, in the block under the measure, draws the chart against one nation, chosen by the boxes under it, one at a time: the United States unless another is ticked. Its curve is drawn flat at 0, whether or not it is ticked under Country selection, and each other nation's curve becomes its difference from it, at each date from the base nation's value then in force:

- a measure in percent (a yield, the policy rate, inflation, debt or interest as a share of GDP under [As % of GDP](?help=percent-of-gdp)): the difference in percentage points, "+0.85%" where the nation's is 0.85 point above the base's;
- an amount in a currency, GDP, or the population: the percentage above or below the base's, "+12.3%".

Everything is then drawn on the left axis, its label naming the base, and the title ends with it ("(base: United States)"). The U.S. target range as the base is its midpoint; as another nation's curve, both its limits are made differences. Before the base nation's first value, a curve has nothing to be measured from, and is not drawn there. The [regression segments](?help=regression) are not drawn against a base. The read-out, Export chart and the line labels give the differences.

## On the command line

`--compare`, at least `--com`, draws the 10-year yields compared; `--no-compare` takes the chart off. `--compare:MEASURE` chooses the measure and turns the chart on: a yield term as `--yields` writes it (`--compare:2y`, `--compare:r10`; `--compare:10` is the 10-year), or `policy`, `inflation`, `debt`, `gdp`, `interest` or `population`, each spelled by a leading part (`--com:pol`, `--com:pop`). One measure at a time: `--compare:10y,2y` is refused. `--base` draws it against the United States, `--base:NATION` against another by its code as `--nations` takes it (`--base:gb`, at least `--bas:`), one at a time; `--no-base` draws it without one. The nations compared are those ticked (`--nations:ca,us,gb,de`). With `--save` the chart has a file of its own, `_compare` added to the name, or a sheet named Compare in a workbook: [Command line](?help=command-line).
