# Latest values

"Intraday quotes on end date", on by default, carries each chart past the end of its regular sources, to the moment, from faster ones. The regular sources publish with a lag: FRED has the Treasury's yields a business day or more after the Treasury, the other nations' official yields come after the day (Germany's during it), and the U.S. federal debt in FRED is quarterly and a quarter or more behind.

It adds nothing to GDP, interest, population or the other nations' debts, which have no faster free source. Carrying those curves on to today is the work of [Projections to today](?help=projections), a box of its own.

## The United States

- **Yields: the Treasury's daily par yield curve.** For the days FRED doesn't have yet, the yields of the Treasury's own daily par yield curve ([Daily Treasury Par Yield Curve Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve)), the figures FRED's series carry a day or more later, for every term the chart draws. The Treasury posts each day's curve the same afternoon (seen 2026-09-28).
- **Federal debt: Debt to the Penny.** The Treasury's total public debt outstanding, each business day, one day behind ([Debt to the Penny](https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/)), from the day after the quarter FRED's last figure closes, so the [debt](?help=debt) runs on day by day. Where it has that quarter's last day, it must agree there with FRED's figure to within 0.1 %, or it isn't joined and the debt ends with the quarter, with a warning.

## The day's quotes, every nation

- **CNBC's quote feed.** The day's government bond yields from the feed CNBC's own pages read ([CNBC bonds](https://www.cnbc.com/markets/bonds/)), a few minutes old, for a day after the last official one: the U.S.' ten terms, Canada's nine (not the 7-year, which the feed doesn't quote), the UK's three and Germany's seven. They are quotes of the moment, so provisional. The feed is unofficial and undocumented: if it fails, each line ends at its last official value, with a warning.
- **Joined at the day's move.** The feed quotes the bonds being traded, not the official curves, so its yields differ from the official ones by a few basis points (by up to 6 on 2026-09-25, the U.S. 3-month). Where the official series ends on the business day before, the program adds the feed's change on the day to the official close; only otherwise does it draw the quote as it is. Quotes from 17:00 Eastern time on are the next day's session and are left out. A quote is dated by its day in Toronto, as the chart's end is.
- **The subtitle** gives the quote's time in the chart's own market's time zone (Toronto, New York, London, Frankfurt), "intraday, provisional".
- **Germany:** the Bundesbank publishes the day's yields during the day, so once they are out the chart ends at them and adds no quote.

The quotes reach the [yields](?help=yields) and so the [spreads](?help=spreads) taken from them.

## When it adds nothing

The quotes are asked for only when the End date is no more than four days before today; the Treasury's daily figures whenever the U.S. chart's End is later than FRED's last figures. So the box is greyed when the End is too early for the day's quotes and no U.S. chart is shown. [Automatic refresh](?help=auto-refresh) draws the chart again after a set number of minutes, with the quotes of that moment; it is greyed while this box is unticked.

## How the program asks for these figures

None of them is kept in the program, and the daily job doesn't add them: the Treasury's figures are asked for when a chart needs them, the quotes afresh at every drawing, never taken from an earlier one. Once the regular sources publish the same days, the chart draws theirs instead.
