# Start and End (-s, -e)

Start and End set the span of dates the charts cover, the same for every chart shown. A date is written `YYYY-MM-DD`, or `YYYY-MM` or `YYYY` for the first day of the month or the year (`--start:2001`), with a slash allowed in place of each dash. The earliest date a chart can show is 1600-01-01, and End must be at least seven days after Start.

The subtitle under the title names the first and last dates of the data actually drawn, which can be narrower than Start and End: a curve that begins later, or ends earlier, is drawn where its data are.

## A blank Start

Left blank, Start is 2000-01-01, or the first date on which every curve chosen has data, if that is later, so that no curve is cut short at the left. The program finds that date from the data at each drawing, so it follows the curves ticked, and the message log names it. A chart that ends before 2000 starts at the first date on which every curve has data.

The floor of 2000 was chosen on 2026-10-06, since Start was being set by hand each time; before then a blank Start was always the first date on which every curve had data.

A curve that begins within seven days of the End, or after it, can't be whole in any span: it is left out of the choice of Start, the log says so, and it is drawn from where it begins, if at all.

## A blank End

Left blank, End is today. When a chart shown draws a policy rate whose change has been announced for a day after today (Canada's target for the overnight rate or the UK's Bank Rate, or Canada's prime rate or the UK tracker, which follow them), a blank End is that day instead, for every chart shown, so the change is drawn ([Policy rates](?help=policy-rates)). The log says so: "End 2026-10-29, the last day a rate drawn holds (a change announced)".

An End later than today can also be typed. The yields and the other published series end by today; the rates that hold until they are changed (the central banks' official rates, the prime rates, the UK tracker) are drawn on to the End; and the [projections](?help=projections) of GDP, debt and interest are carried to it.

The day's quotes are added only when the End is no more than four days before today ([Latest values](?help=latest-values)), and the projections drawn only then.

## Moving the dates

In the window and on the page alike:

- **A box dragged over a chart** zooms to it: its width sets Start and End, its height the [axis limits](?help=limits) of that chart.
- **The wheel over a chart** zooms the dates about the pointer.
- **In the window**, dragging with the right or middle button moves the dates.
- **On the page**, "◀ Earlier" and "Later ▶" move the dates by half their span, and "Zoom out" doubles the span about its middle, kept between 1600 and today.
- **Back** undoes one zoom, move, Unzoom or Reset; **Unzoom** returns to the dates before the first zoom or move since the last Reset. Each is greyed while it would do nothing.

The dates are shared by every chart, so a zoom on one moves them all; the axis limits are each nation's own.

## On the command line

`--start:DATE` or `-s:DATE`, and `--end:DATE` or `-e:DATE`, as in `-s:2015 -e:2026-09-01`.
