# As % of GDP (-r)

Debt and interest drawn as a percentage of the nation's GDP over the same twelve months, rather than in its currency. A share of GDP has no currency, so the nations' charts can be read against each other without exchange rates.

## What is divided by what

- **Debt**, the aggregate and, when levels of government are ticked, each level (the UK's net debt too), over the trailing-twelve-month (TTM) nominal GDP: the nation's GDP over the twelve months to each date.
- **Interest**, the TTM interest outlays, over the same TTM GDP.
- **GDP** is the divisor, so it is not drawn, and its box is greyed.

## When the ratio is taken

Each ratio is taken when its debt or interest is observed, and held until the next observation. A debt reported once a year is divided by the GDP of the twelve months to that year's end, and its line stays level until the next year's figure. Dividing on every date instead would set one year's debt over each newer quarter's GDP in turn: the line would fall through the year and jump at its end, a sawtooth that is not in the data.

Where GDP is missing the ratio is missing too. Canada's federal debt runs from 1867, but its GDP only from 1926, so the debt shows as a share of GDP from 1926.

## The axis

The right axis reads "Percent of TTM GDP (Log Scale)". On a log axis a ratio growing at a steady rate is a straight line, and with [Regression segments](?help=regression) ticked each segment's label gives the ratio's own growth, in % a year.

[Top and Bottom](?help=limits) are percentages under -r (`--top:150%`); an amount in a currency is refused there, and the boxes are cleared when the measure changes. **All** beside them copies a percentage as it is.

## On the command line

`-r`, `--R` or `--relative`. It can't be combined with per capita (`-p`): a curve is either a share of GDP or an amount per person, and in the window and on the page ticking one unticks the other. Without debt or interest ticked it has no effect, and its box is greyed.
