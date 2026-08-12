"""Trading calendar derived from actual price history (0050 daily data).

Deriving from real trading records automatically handles typhoon closures and
make-up Saturdays (e.g. 2013-02-23 traded). Limitations, by construction:
- cannot predict FUTURE trading days (no data yet)
- TWSE STOCK_DAY history begins 2010-01-04

The reference instrument is 0050 (Yuan Ta Taiwan 50 ETF), listed since 2003 and
continuously traded.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .prices import get_prices

REFERENCE_TICKER = "0050"


def get_calendar(start: str, end: str) -> pd.DataFrame:
    """Trading days between two ISO dates (inclusive), one `date` column."""
    px = get_prices(REFERENCE_TICKER, start, end)
    return px[["date"]].reset_index(drop=True)


def trading_days(start: str, end: str) -> set[dt.date]:
    return set(get_calendar(start, end)["date"])


def is_trading_day(date: str | dt.date) -> bool:
    """True if the market traded on this (historical) date."""
    d = dt.date.fromisoformat(date) if isinstance(date, str) else date
    return d in trading_days(d.isoformat(), d.isoformat())


def next_trading_day(date: str | dt.date, max_lookahead_days: int = 30) -> dt.date:
    """First trading day strictly after `date` (historical data only)."""
    d = dt.date.fromisoformat(date) if isinstance(date, str) else date
    horizon = d + dt.timedelta(days=max_lookahead_days)
    days = sorted(trading_days(d.isoformat(), horizon.isoformat()))
    for day in days:
        if day > d:
            return day
    raise ValueError(
        f"no trading day within {max_lookahead_days} days after {d} "
        "(future dates cannot be predicted from price history)"
    )
