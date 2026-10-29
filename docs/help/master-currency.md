# The master currency

Each chart draws its amounts (debt, GDP and interest, their levels, per person, and their projections to today) in its own nation's currency. With a master currency, every chart drawn with it draws them in that one currency instead, so that the nations' curves read in one unit.

## The box

In each nation's panel, "Use CAD as the master currency" (with that nation's own currency). One box at most is ticked: ticking one unticks the others. On the command line it is `--master:CODE`, at least `--mas` (`--ma` is shared with `--max`): `--master:USD`, with `CAD`, `GBP`, `EUR`, or `US$`, `C$`, `£`, `€`, in either case. There is no nation's own form (`--us:master` is refused): the master is every chart's.

The box is greyed, keeping its tick, while fewer than two nations are ticked, while [% of GDP](?help=percent-of-gdp) is in effect (a share of GDP is in no currency), and while no chart draws debt, GDP or interest. A nation unticked keeps its box's tick, and its currency is not applied while it isn't drawn. The command line leaves out a master that changes nothing, and a command line that gives one says so in the log.

## The conversion

The master's own chart is drawn as it always is. Every other chart converts its amounts at one rate, the master's against its nation's currency on its End date, the latest on or before it, the same rates as for [a limit in another currency](?help=limits) (FRED's daily rates from 1971, the older ones before). One rate for the whole chart multiplies every amount by the same number, so on the log axis each curve keeps its shape and its place: only the axis's ticks and label, the [end labels](?help=end-labels), the [hover read-out](?help=hover) and Export chart's data change. The [regression segments](?help=regression) keep their rates of growth, which no currency changes.

The right axis names the master and the rate: "Nominal Units (USD at 0.71932 per CAD, 2026-09-01 – Log Scale)", and the log gives the rate's source. A chart converted to U.S. dollars writes them US$, since $ alone on the Canadian chart would read as Canadian dollars; the U.S. chart keeps its $. A chart that ends today converts at FRED's latest rate, which can be a week or more old.

Where there is no rate by the End date (the pound before 1791, the Canadian dollar before 1858, the euro before 1948-06-21), that chart is drawn in its own currency, with a warning in the log.

## Top and Bottom

The master changes only the units a chart is drawn and read out in, not what is set: each Top and Bottom box keeps its value as it was set, in the nation's own currency or in the one it was typed in (`USD20t`), and the chart converts it for drawing as it converts every amount. With one of the two set, the other end's fixed default is converted too, so the lines stay where they were. A box dragged over a chart drawn in the master currency writes its Top and Bottom with the master's code (`USD2.2t`), so they mean the same with the master off. "All" copies an amount with its currency, as it always has.
