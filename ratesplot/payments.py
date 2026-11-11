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
last day of its last quarter, as GDP and interest are (``frames.at_quarter_end``).
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
"""

from __future__ import annotations

import pandas as pd

from .config import (
    BILLION,
    DATE_COLUMN,
    MILLION,
    PAYMENTS_CREDITS_COLUMN,
    PAYMENTS_DEBITS_COLUMN,
    nation_by_key,
)
from .frames import at_quarter_end
from .http import downloads_of
from .joins import ttm_sum
from .us_data import fred_series

# The nations whose balance of payments is drawn so far (batch 23's stages):
# a chart of another prints a note and draws none.
PAYMENTS_NATIONS = ("us",)

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


def _ttm_frame(credits: pd.Series, debits: pd.Series) -> pd.DataFrame:
    """The pair's quarterly flows as trailing-twelve-month sums, ``[DATE, credits, debits]``, dated by each last quarter's end."""
    frame = pd.DataFrame({PAYMENTS_CREDITS_COLUMN: ttm_sum(credits), PAYMENTS_DEBITS_COLUMN: ttm_sum(debits)}).dropna()
    frame.index = at_quarter_end(frame.index)
    return frame.rename_axis(DATE_COLUMN).reset_index()


def payments_earliest(key: str) -> pd.Timestamp | None:
    """The first quarter of nation ``key``'s balance of payments, for the coverage warning; None where none is drawn yet."""
    return {"us": US_PAYMENTS_EARLIEST}.get(key)


@downloads_of("the balance of payments")
def fetch_payments(key: str, item: str) -> pd.DataFrame | None:
    """Nation ``key``'s pair ``item`` (``PAYMENTS_ITEMS``) as TTM sums, ``[DATE, credits, debits]``; None, with a note, where it is not drawn yet.

    A source that fails raises: the caller (``plotting``) warns and draws the
    chart without the pair, as it does a curve whose source fails.
    """
    if key not in PAYMENTS_NATIONS:
        print(f"  Note: the balance of payments is not drawn yet for {nation_by_key(key).name} (batch 23's later stages).")
        return None
    credits, debits = _us_quarters(item)
    return _ttm_frame(credits, debits)
