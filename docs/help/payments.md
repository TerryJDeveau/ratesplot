# Balance of payments

The money coming into a nation against the money going out, as two lines on the right axis in the nation's currency, each the sum over the trailing twelve months, as [GDP](?help=gdp) and [interest](?help=interest) are. The gap between them is shaded light green where more comes in than goes out, light pink where more goes out. Ticking Balance of payments adds the two lines and hides nothing; one pair is drawn at a time, chosen by the boxes under it:

- **current account**, the default: the current account's credits (exports of goods and services, income received from abroad, transfers received) in purple, against its debits (imports, income paid abroad, transfers paid) in gold. Their gap is the current account balance, the headline figure: a deficit is what the nation borrows from, or sells to, the rest of the world over the year.
- **trade**: exports of goods and services in purple against imports in gold. Their gap is the trade balance.

Every nation reports these under the IMF's sixth balance of payments manual (BPM6), so the two pairs mean the same on every chart. Money in and money out over the whole statement, financing included, are not drawn: the statement is double entry, so those two totals are equal apart from errors and omissions, and their lines would lie on top of each other. The financial account, the financing itself, changes sign from quarter to quarter and so cannot take a log axis; it waits.

[As % of GDP](?help=percent-of-gdp) divides both lines by GDP, the usual way the current account is compared across nations and years; [per capita](?help=per-capita) and [inflation adjusted](?help=constant-prices) measure them as the other amounts are, and the [master currency](?help=master-currency) converts them. The [regression segments](?help=regression) fit each line; the shading is not fitted. With the [projections](?help=projections) on, each line is carried on to today at the past year's pace, faint, and the shading stops at the last figures.

## Where the figures come from

- **The United States, from 1960.** The Bureau of Economic Analysis' international transactions, quarterly and seasonally adjusted, through FRED: under BPM6 from 1999 (`IEAX`, `IEAM`; `IEAXGS`, `IEAMGS`), and before it the older manual's figures (`BOPX`, `BOPM`; `BOPXGS`, `BOPMGS`). The older credits and debits leave out the transfers, which are put in from the older current account balance (`BOPBCA`) by their net, on the side its sign puts it, so that the gap is the current account balance in both. The two join end to end in 1999, nothing scaled: there the older credits are 3.4 % under the newer (the older manual has no transfers received), the debits 1.6 %, exports 0.6 % and imports 0.8 % over.
- **Canada, from 1946.** Statistics Canada's balance of international payments, quarterly and seasonally adjusted: under BPM6 from 1981 (table 36-10-0018: the receipts and payments of the whole current account, and of goods and services), and before it the same lines under the older manual (table 36-10-0047, archived). The two join end to end in 1981, nothing scaled: there the older receipts are 1.4 % under the newer, the payments 1.9 %, exports 1.0 % and imports 1.2 %.
- **The United Kingdom, from 1955.** The Office for National Statistics' balance of payments (dataset PNBP), quarterly and seasonally adjusted, under BPM6 throughout: the current account's credits and debits (`HBON`, `HBOO`), and exports and imports of goods and services (`IKBH`, `IKBI`). One series each, with no join.
- **Germany** is not drawn yet; its chart says so in the message log.

## On the command line

`--payments`, at least `--pay` (`--bop` would be ambiguous with `--b:`, Bottom); `--no-payments` takes it off. `--payments:trade` draws exports and imports, `--payments:current` the current account; one at a time, so `--payments:current,trade` is refused. A pair given turns the lines on. As a series, `--payments` alone draws the balance of payments alone: [Command line](?help=command-line).
