# Latest value for each line (-l)

Each curve's last value written at its end, in the curve's colour, on a white ground, so the chart can be read at its most recent date without the axes.

## How each value is written

- **Yields and rates** in percent to three decimals, a third decimal of 0 dropped: `3.70%`, `3.263%`. Three, since eighths of a point are still common.
- **Spreads** in points to a tenth, the tenth dropped when it is 0: `+36 pts`, `+48.1 pts`.
- **The right axis's curves** as its ticks write them: `C$4.15T`, `135%` under [As % of GDP](?help=percent-of-gdp), `C$99.5K` under [Per capita](?help=per-capita).
- **A projected value** with "≈" before it: `≈C$4.22T` ([Projections to today](?help=projections)).

## Where each goes

A curve that stops before the chart's end is labelled where it stops; one whose last value lies beyond Top or Bottom has no label ([Axis limits](?help=limits)). The date axis is widened on the right only as far as the labels need, and not at all where they fit beside the curves' ends.

Labels that would overlap are moved up or down as little as will separate them. Where moving them leaves a group of touching labels with one more than half its height from its curve's end, that group alone is made smaller, a point at a time from 16 points down to 12; if it is still crowded at 12, it stands a little off, and each of its labels gets a thin line to its curve's end. The other labels keep their full size. The legend is then placed so as to cover none of them ([Size and layout](?help=layout)).

## On the command line

`-l`, `--L` or `--label`.
