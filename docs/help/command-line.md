# Command line

The line under the charts is the command that draws the same charts with the program on your own computer: `python ratesplot.py` followed by the chart's options, each written out in full (`--C --relative --regression`). It follows every change of the controls.

## Running it

The program is at [github.com/TerryJDeveau/ratesplot](https://github.com/TerryJDeveau/ratesplot). It needs Python 3.12 or later and the packages its folder lists, installed once with `python -m pip install -r requirements.txt`. Run in the program's folder, the line opens the program's window on these charts; with `--no-gui` added they open in plain chart windows instead, and with `--save:FILE` the chart is written to a file without a window.

## Copying it

In the window, Copy beside the line puts it on the clipboard; on the web page, the copy button at the right of its box does the same. A copied line can be run, kept in a script to draw the same charts again, or sent to someone who has the program. Its link on the web page, the line under it, draws the same charts in a browser for anyone: [Web page](?help=web-page).

## What it draws

The same charts, from the same sources, at the size the Size boxes give. On a narrow screen the web page draws a smaller chart with larger text, but the line is the controls', so it draws the full-size chart ([Size and layout](?help=layout)). With End left blank it draws up to the day it is run, so the same line run later draws the latest data ([Start and End](?help=dates)).

Every option, as the line spells it, is listed by `python ratesplot.py --help`, and on the web page under "Every option, as the command line spells it" at the page's foot.

## What a line starts from

A line that names a series draws only the series it names: `--gdp`, `--policy`, `--mo:5`, `--yields:2,10`, `--debt:fp`, `--cpi`; `--gdp --policy` draws the two. A curve it doesn't name isn't drawn, so the four curves with the policy rate are `--gdp --debt --interest --yield --policy`, as the line under the charts writes them. A `--no-` form hides what it says and names nothing: `--no-gdp` and `--no-yields:30` leave the rest as they are.

Naming a series also starts the window from the values Reset gives rather than the settings it remembers: Canada and the U.S. unless the line names other nations, every other control at Reset's value unless the line names it, and "Remember my settings" unticked, so that a one-off view leaves the settings remembered as they were. A line that names no series starts from the settings remembered, with the options it names laid over them.

`--rem` (at least that: `--re` is `-r`) and `--no-rem` tick and untick that box at the start, whatever the line names, and aren't written in the line or its link. `--save:FILE` and `--no-gui` leave the settings remembered alone, unless `--rem` is given: then the run's choices become the settings the next window from that command window starts from.

## The version in the data saved

The data Export chart and `--save:FILE` write (XLSX, CSV, TSV) end their subtitle, the second row, with the version that wrote them: `; v7.9, build: 1a2b3c4`. `--no-ver` leaves it out. It has no control: a window or a web page started with it keeps it until it closes, in the line and the link it writes, so a copy keeps it too, and it is not remembered for the next start. The images are the same either way. `-v` or `--version` alone prints the version and draws nothing.
