# Automatic refresh (--au)

Off by default. Ticked, the charts are drawn again every 5 minutes, or every so many minutes as the box beside it says, as Refresh draws them: figures downloaded more than an hour before are asked for again, and the day's quotes always afresh. It is for following the day's yields while the markets are open.

## When it draws again

- **In market hours,** 08:00 to 17:00 Monday to Friday in the time zone of each chart's market (Toronto, New York, London, Frankfurt), at every interval. Holidays aren't known, so they count as working days.
- **Outside them,** the quotes are asked for at every interval, one request for each nation shown, and the charts are drawn again only when a quote has changed. The first interval after the markets close always draws, since a quote may have come after the last drawing.

The interval is at least 5 minutes, on the page and everywhere else, so that the program asks the sources' servers no more often than that. The largest is 1,440, a day.

## When it adds nothing

Only the yields have intraday quotes (and the spreads taken from them), so a refresh can bring nothing new, and the box and its minutes are greyed, when "Intraday quotes on end date" is unticked, when the End is before today, or when no chart shown draws a yield the quotes reach ([Latest values](?help=latest-values)). A series given intraday quotes later will count too.

## Where it runs

In the window and on the page the charts are drawn again in place. On the command line with `--save:FILE` the files are written again at every interval until Ctrl-C, each through a temporary file swapped in once whole; a file another program holds open gets "_1" (and so on) after its name, kept until that one is held too. In the plain matplotlib windows of `--no-gui` each window draws itself again.

## On the command line

`--au` or `--auto-refresh` turns it on, `--no-au` off; `--au:MIN` sets the minutes and turns it on (`--au:10`).
