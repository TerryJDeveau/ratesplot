"""The balance of payments (batch 23, --payments[:LIST]): money coming into a nation against money going out.

Two pairs, one drawn at a time (decision 61, 2026-10-24):

* ``current``: the current account's credits (exports of goods and services,
  primary income received, secondary income received) against its debits
  (imports, primary income paid, secondary income paid). Their gap is the
  current account balance, the headline figure, and by the balance of
  payments' identity also the nation's net borrowing from abroad.
* ``trade``: exports against imports of goods and services. Their gap is the
  trade balance.

Not gross inflows against gross outflows over the whole statement: the balance
of payments is double entry (current account + capital account - financial
account + errors and omissions = 0), so those two totals would lie on top of
each other. The financial account waits (plan 23).

Each nation's reader returns one frame, ``[DATE, PAYMENTS_CREDITS_COLUMN,
PAYMENTS_DEBITS_COLUMN]``, in the nation's currency (units, not millions),
each value the sum over the trailing twelve months to its date, dated by the
last day of its last quarter, as GDP and interest are (``frames.at_quarter_end``);
Germany's, whose figures are monthly, one each month, by the month's last day.
``plotting`` merges it into the macro frame, so that it is measured (-r, -p,
--constant, --master), fitted (--reg, decision 62), projected (--projections)
and exported as the other amounts are.

The sources, measured 2026-11-11 from Buddug (the batch's measurement note):

* U.S.: the BEA's international transactions through FRED, under the IMF's
  sixth manual (BPM6) from 1999-Q1, quarterly, seasonally adjusted, millions
  of dollars a quarter (not annualised): IEAX and IEAM (table 1.1, lines 1 and
  31) and IEAXGS and IEAMGS (lines 2 and 32). Before 1999 the fifth manual's
  (BPM5) figures from 1960-Q1, stopped at 2014-Q1, billions, debits negative:
  BOPX and BOPM (goods, services and income, without transfers) and BOPXGS and
  BOPMGS; their current account balance BOPBCA gives the net unilateral
  transfers (BOPBCA - BOPX - BOPM), put on the side its sign puts it, so that
  the gap is the current account balance in both. Joined end to end at
  1999-Q1, nothing scaled, as every join of the program's is drawn: at the
  join the older is 3.4 % under the newer for the credits (BPM5 has no
  transfers received), 1.6 % for the debits, 0.6 % for exports, 0.8 % over
  for imports.
* Canada: Statistics Canada's international accounts, quarterly, seasonally
  adjusted, millions of dollars a quarter: 36-10-0018 (BPM6) from 1981-Q1,
  receipts and payments of the total current account and of goods and
  services; before 1981 the same lines of 36-10-0047 (BPM5, 1946-Q1 to
  2012-Q2, archived, no longer updated), baked once into ``cdn_archive_data``
  and never asked for again (Terry, 2026-11-11). Joined end to end at
  1981-Q1, nothing scaled: there
  the older is 1.4 % under the newer for the receipts, 1.9 % for the
  payments, 1.0 % for exports, 1.2 % for imports.
* The UK: the ONS's balance of payments (dataset PNBP), quarterly from 1955
  Q1, seasonally adjusted, £m a quarter, under BPM6 throughout: HBON and
  HBOO, the current account's credits and debits (HBON less HBOO is the
  balance, HBOP, exactly), and IKBH and IKBI, exports and imports of goods
  and services. One series each, no join.
* Germany: the Bundesbank's balance of payments (``de_data.DE_PAYMENTS_SERIES``),
  monthly from 1971-01, unadjusted (its only whole monthly figures), millions
  of euros a month, the Deutsche Mark years in euros at 1.95583: West
  Germany's to 1990-06 and all of Germany's from 1990-07, in one series, no
  join. The credits and debits are each the sum of goods, services, primary
  income and secondary income (credits less debits is the Bundesbank's
  current account balance within 0.002 million a month); trade, of goods and
  services alone. Each month's twelve-month sum, dated by the month's last
  day, not a sum of quarters (decision 128's call; alternative: quarterly,
  as the other three). So the sums ending 1990-07 to 1991-05 hold months of
  both territories: per person, each is over its months' mean population
  (``de_data.payments_population``). -r divides them by the GDP drawn,
  West Germany's until 1991-09-30, so the sums holding all of Germany's
  months read high until 1991-12-31, by up to 14.4 % (all of Germany's GDP
  to 1991-12-31 over West Germany's to 1991-09-30), where Germany's debt
  and interest, each a year's figure until 1991, meet GDP's territory; and
  each month's sum is over GDP's latest quarter, so the ratio runs up within
  a quarter by up to its growth (about 2 % a quarter in the 1970s, 1 %
  since 2010), which batch 42.3's filled-in sums would smooth.
"""

from __future__ import annotations

import pandas as pd

from .cdn_archive_data import EMBEDDED_CDN_PAYMENTS_HISTORY
from .cdn_data import statcan_table
from .config import (
    ARCHIVED_CDN_PAYMENTS_VECTORS,
    BILLION,
    DATE_COLUMN,
    MILLION,
    PAYMENTS_CREDITS_COLUMN,
    PAYMENTS_DEBITS_COLUMN,
    STATCAN_CDN_PAYMENTS_TABLE,
    STATCAN_CDN_PAYMENTS_VECTORS,
    nation_by_key,
)
from .de_data import DE_PAYMENTS_SERIES, DE_PAYMENTS_SIDES, bundesbank_series
from .frames import at_quarter_end, rows_to_frame
from .http import downloads_of
from .joins import ttm_sum
from .uk_data import ons_series
from .us_data import fred_series

# The nations whose balance of payments is drawn (batch 23's stages): a chart
# of another prints a note and draws none.
PAYMENTS_NATIONS = ("us", "cdn", "uk", "de")

# FRED's BEA series, BPM6, from 1999-Q1, millions of dollars a quarter,
# seasonally adjusted: (credits, debits) of each pair.
US_PAYMENTS_SERIES = {"current": ("IEAX", "IEAM"), "trade": ("IEAXGS", "IEAMGS")}
# The same before 1999, BPM5, billions a quarter, debits negative; stopped
# with 2014-Q1 (FRED, measured 2026-11-11).
US_OLD_PAYMENTS_SERIES = {"current": ("BOPX", "BOPM"), "trade": ("BOPXGS", "BOPMGS")}
US_OLD_BALANCE_SERIES = "BOPBCA"
US_OLD_PAYMENTS_STOPPED = pd.Timestamp("2014-01-01")
# Where the BPM6 figures take over (FRED dates a quarter by its first day).
US_PAYMENTS_JOIN = pd.Timestamp("1999-01-01")
US_PAYMENTS_EARLIEST = pd.Timestamp("1960-01-01")

# Canada (Statistics Canada dates a quarter by its first day): the vectors of
# each table are in ``config``. 36-10-0018 is read by ``cdn_data``; the
# archived 36-10-0047 from ``cdn_archive_data``, where it is baked whole.
CDN_PAYMENTS_JOIN = pd.Timestamp("1981-01-01")
CDN_PAYMENTS_EARLIEST = pd.Timestamp("1946-01-01")

# The UK's ONS series (``uk_data.ONS_SERIES``), £m a quarter, dated by each
# quarter's last day: (credits, debits) of each pair.
UK_PAYMENTS_SERIES = {"current": ("HBON", "HBOO"), "trade": ("IKBH", "IKBI")}
UK_PAYMENTS_EARLIEST = pd.Timestamp("1955-01-01")

# Germany: the Bundesbank's items (``de_data.DE_PAYMENTS_ITEMS``) added up into
# each pair's credits and debits, millions of euros a month.
DE_PAYMENTS_PARTS = {"current": ("G", "S", "IN1", "IN2"), "trade": ("G", "S")}
DE_PAYMENTS_EARLIEST = pd.Timestamp("1971-01-01")
# A year of months, for Germany's twelve-month sums.
_MONTHS_IN_A_YEAR = 12


def _fred_quarters(series_id: str, *, stopped: pd.Timestamp | None = None) -> pd.Series:
    """One quarterly FRED series as FRED gives it, indexed by its quarters' first days (revised: the BEA revises its accounts)."""
    frame = fred_series(series_id, revised=True, stopped=stopped)
    return pd.Series(frame[series_id].to_numpy(dtype=float), index=pd.DatetimeIndex(frame[DATE_COLUMN]), name=series_id).dropna()


def _us_quarters(item: str) -> tuple[pd.Series, pd.Series]:
    """The U.S. credits and debits of pair ``item``, each a quarter's flow in dollars, BPM5 to 1998 then BPM6 (the module's docstring)."""
    credits_id, debits_id = US_PAYMENTS_SERIES[item]
    old_credits_id, old_debits_id = US_OLD_PAYMENTS_SERIES[item]
    credits = _fred_quarters(credits_id) * MILLION
    debits = _fred_quarters(debits_id) * MILLION
    old_credits = _fred_quarters(old_credits_id, stopped=US_OLD_PAYMENTS_STOPPED) * BILLION
    old_debits = -_fred_quarters(old_debits_id, stopped=US_OLD_PAYMENTS_STOPPED) * BILLION
    if item == "current":
        # BPM5's goods, services and income leave out the unilateral transfers,
        # which its balance includes: their net goes on the side its sign puts it.
        transfers = _fred_quarters(US_OLD_BALANCE_SERIES, stopped=US_OLD_PAYMENTS_STOPPED) * BILLION - old_credits + old_debits
        old_credits = old_credits + transfers.clip(lower=0.0)
        old_debits = old_debits - transfers.clip(upper=0.0)
    joined = []
    for old, new in ((old_credits, credits), (old_debits, debits)):
        joined.append(pd.concat([old.loc[old.index < US_PAYMENTS_JOIN], new.loc[new.index >= US_PAYMENTS_JOIN]]))
    return joined[0], joined[1]


def _cdn_quarters(item: str) -> tuple[pd.Series, pd.Series]:
    """Canada's receipts and payments of pair ``item``, each a quarter's flow in dollars, 36-10-0047 to 1980 then 36-10-0018 (the module's docstring)."""
    new = statcan_table(STATCAN_CDN_PAYMENTS_TABLE)
    joined = []
    for old_vector, new_vector in zip(ARCHIVED_CDN_PAYMENTS_VECTORS[item], STATCAN_CDN_PAYMENTS_VECTORS[item]):
        before = rows_to_frame(EMBEDDED_CDN_PAYMENTS_HISTORY[old_vector], old_vector)[old_vector]
        after = new[new_vector].dropna()
        joined.append(pd.concat([before.loc[before.index < CDN_PAYMENTS_JOIN], after.loc[after.index >= CDN_PAYMENTS_JOIN]]) * MILLION)
    return joined[0], joined[1]


def _uk_quarters(item: str) -> tuple[pd.Series, pd.Series]:
    """The UK's credits and debits of pair ``item``, each a quarter's flow in pounds (``uk_data.ons_series``)."""
    credits_id, debits_id = UK_PAYMENTS_SERIES[item]
    return ons_series(credits_id), ons_series(debits_id)


def _de_months(item: str) -> tuple[pd.Series, pd.Series]:
    """Germany's credits and debits of pair ``item``, each a month's flow in euros: the Bundesbank's items added up (the module's docstring).

    A month lacking any item is left out, so no sum of twelve holds it.
    """
    sides = []
    for side in DE_PAYMENTS_SIDES:
        parts = [bundesbank_series(*DE_PAYMENTS_SERIES[(side, part)], revised=True) for part in DE_PAYMENTS_PARTS[item]]
        sides.append(pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).dropna() * MILLION)
    return sides[0], sides[1]


# Each drawn nation's reader: (credits, debits) of a pair, a quarter's flows,
# or for Germany a month's.
_QUARTERS = {"us": _us_quarters, "cdn": _cdn_quarters, "uk": _uk_quarters}
_MONTHS = {"de": _de_months}


def _ttm_frame(credits: pd.Series, debits: pd.Series) -> pd.DataFrame:
    """The pair's quarterly flows as trailing-twelve-month sums, ``[DATE, credits, debits]``, dated by each last quarter's end."""
    frame = pd.DataFrame({PAYMENTS_CREDITS_COLUMN: ttm_sum(credits), PAYMENTS_DEBITS_COLUMN: ttm_sum(debits)}).dropna()
    frame.index = at_quarter_end(frame.index)
    return frame.rename_axis(DATE_COLUMN).reset_index()


def _twelve_month_sum(monthly: pd.Series) -> pd.Series:
    """The sum of each twelve consecutive months, dated by the last one's last day; a month missing inside leaves the sums that hold it missing (as ``joins.ttm_sum`` for quarters)."""
    regular = monthly.resample("ME").sum(min_count=1)
    return regular.rolling(_MONTHS_IN_A_YEAR, min_periods=_MONTHS_IN_A_YEAR).sum().dropna()


def _monthly_ttm_frame(credits: pd.Series, debits: pd.Series) -> pd.DataFrame:
    """The pair's monthly flows as trailing-twelve-month sums, ``[DATE, credits, debits]``, one each month, dated by its last day."""
    frame = pd.DataFrame({PAYMENTS_CREDITS_COLUMN: _twelve_month_sum(credits), PAYMENTS_DEBITS_COLUMN: _twelve_month_sum(debits)}).dropna()
    return frame.rename_axis(DATE_COLUMN).reset_index()


def payments_earliest(key: str) -> pd.Timestamp | None:
    """The first quarter (Germany's: month) of nation ``key``'s balance of payments, for the coverage warning; None where none is drawn yet."""
    return {"us": US_PAYMENTS_EARLIEST, "cdn": CDN_PAYMENTS_EARLIEST, "uk": UK_PAYMENTS_EARLIEST, "de": DE_PAYMENTS_EARLIEST}.get(key)


@downloads_of("the balance of payments")
def fetch_payments(key: str, item: str) -> pd.DataFrame | None:
    """Nation ``key``'s pair ``item`` (``PAYMENTS_ITEMS``) as TTM sums, ``[DATE, credits, debits]``; None, with a note, where it is not drawn yet.

    A source that fails raises: the caller (``plotting``) warns and draws the
    chart without the pair, as it does a curve whose source fails.
    """
    if key not in PAYMENTS_NATIONS:
        print(f"  Note: the balance of payments is not drawn yet for {nation_by_key(key).name}.")
        return None
    if key in _MONTHS:
        return _monthly_ttm_frame(*_MONTHS[key](item))
    credits, debits = _QUARTERS[key](item)
    return _ttm_frame(credits, debits)
