# The central banks' announcement feeds, saved 2026-10-28 (batch 32)

`tools/check_announced.py` reads these through the program's own readers (`ratesplot/announced.py`).
Both were fetched on Buddug at 19:18 UTC on 2026-10-28, the day the Bank of Canada raised its target
for the overnight rate to 2.5 %, with the program's own request headers; each answered 200 in under
half a second, and each address is allowed by its host's robots.txt.

- `boc_press_releases.xml`: https://www.bankofcanada.ca/content_type/press-releases/feed/ (11,919
  bytes; RSS 1.0 with the RSS-CB extension; the last ten press releases of every kind; four of them
  rate announcements, 2026-06-10 to 2026-10-28; Last-Modified 17:49:45 GMT).
- `boe_news.xml`: https://www.bankofengland.co.uk/rss/news (25,899 bytes; RSS 2.0; about fifty news
  items back to 2026-07-06; two MPC decisions, the holds of 2026-07-30 and 2026-09-17 at 3.75 %).

What was measured from them and from the releases of 2020 to 2026 is in the module's docstring.
