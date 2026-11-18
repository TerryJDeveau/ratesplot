# Population

Each nation's population itself, in persons on a log axis of its own, drawn as a solid dark-goldenrod line. Ticking Population adds it to the chart and hides nothing.

When GDP, debt, interest or the [balance of payments](?help=payments) is drawn, the population has an axis of its own outside the right axis, so it keeps its own scale; with the [price index](?help=price-index) and none of them, it has an axis of its own outside the index's; alone, it is on the right axis. The right side holds two kinds of unit at most: beside an amount the population and the price index are drawn one at a time, so ticking one unticks the other, and ticking an amount while both are drawn unticks the population; on the command line the three kinds together are refused. Being a count, the population is drawn the same [per capita](?help=per-capita), [as % of GDP](?help=percent-of-gdp) and [inflation adjusted](?help=constant-prices). Top and Bottom are the right axis's limits, not the population's.

The line runs straight from one estimate to the next rather than in steps, since an estimate is a count on one date, not a figure held until the next. With [Projections to today](?help=projections), on a chart reaching today, it is carried on from the last estimate to the End, faint, at its pace over the year before; without them it is held at the last estimate. On a log axis a straight stretch is steady growth, and it is the same line Per capita divides by. The [regression segments](?help=regression) fit the population on its own axis, by that axis's height, so each piece's %/yr is the average growth over it. An end label and the read-out give it to three figures, as the amounts are written: 41.6M.

Three jumps in the line are changes of territory, not of the number of people: the United Kingdom's in 1801 (all of Ireland counted) and 1922 (Irish independence), and Germany's between 1990 and 1991 (unification). A regression piece over one of them gives a rate that says nothing about growth.

## Where each population comes from

These are the figures Per capita divides by; [its page](?help=per-capita) gives each source and its dates in full.

- **Canada, from 1867.** Statistics Canada's estimates, yearly to 1945, quarterly from 1946.
- **The United States, from 1947.** The Bureau of Economic Analysis' population, quarterly, through FRED. Nothing earlier is read.
- **The United Kingdom, from 1707.** The Bank of England's yearly figures to 1954 (Great Britain to 1800, with all of Ireland from 1801 to 1921, with Northern Ireland alone from 1922), then the ONS's quarterly figures.
- **Germany, from 1950.** The Bundesbank's yearly averages to 1959, then Eurostat's counts on 1 January to 1990, both for West Germany with the Saarland and West Berlin, then Eurostat's quarterly figures for all of Germany from 1991, a step of 17 million at unification.

## On the command line

`--population`, at least `--pop` (`--po` is the policy rate). `--no-population` takes it off. As a series, `--population` alone draws the population alone: [Command line](?help=command-line).
