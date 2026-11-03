# Command line

The line under the charts is the command that draws the same charts with the program on your own computer: `python ratesplot.py` followed by the chart's options, each written out in full (`--C --relative --regression`). It follows every change of the controls.

## Running it

The program is at [github.com/TerryJDeveau/ratesplot](https://github.com/TerryJDeveau/ratesplot). It needs Python 3.12 or later and the packages its folder lists, installed once with `python -m pip install -r requirements.txt`. Run in the program's folder, the line opens the program's window on these charts; with `--no-gui` added they open in plain chart windows instead, and with `--save:FILE` the chart is written to a file without a window.

## Copying it

In the window, Copy beside the line puts it on the clipboard; on the web page, the copy button at the right of its box does the same. A copied line can be run, kept in a script to draw the same charts again, or sent to someone who has the program. Its link on the web page, the line under it, draws the same charts in a browser for anyone: [Web page](?help=web-page).

## What it draws

The same charts, from the same sources, at the size the Size boxes give. On a narrow screen the web page draws a smaller chart with larger text, but the line is the controls', so it draws the full-size chart ([Size and layout](?help=layout)). With End left blank it draws up to the day it is run, so the same line run later draws the latest data ([Start and End](?help=dates)).

Every option, as the line spells it, is listed by `python ratesplot.py --help`, and on the web page under "Every option, as the command line spells it" at the page's foot.
