"""Trading calendar derived from actual price history.

Deriving from real trading records automatically handles typhoon closures and
make-up Saturdays (e.g. 2013-02-23 traded). Limitations, by construction:
- cannot predict FUTURE trading days (no data yet)
- TWSE STOCK_DAY history begins 2010-01-04

A single instrument is not enough: a stock can be suspended while the market is
open, which would read as a market holiday. 0050 had no trades from 2025-06-11
to 2025-06-17 around its 1:4 split, while 2330 traded every one of those days.
So the calendar is the UNION over several continuously-listed references — a day
counts as a trading day if any of them traded, since a stock can only trade when
the market is open. Suspensions can therefore only ever remove a day from one
series, never invent one.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .prices import get_prices

#: Reference instruments, most liquid first. 0050 (Yuan Ta Taiwan 50 ETF) and
#: 2330 (TSMC) are both continuously listed well before the 2010 history floor.
REFERENCE_TICKERS = ("0050", "2330")


def get_calendar(start: str, end: str) -> pd.DataFrame:
    """Trading days between two ISO dates (inclusive), one `date` column."""
    days = sorted(trading_days(start, end))
    return pd.DataFrame({"date": pd.Series(days, dtype="object")})


def trading_days(
    start: str,
    end: str,
    tickers: tuple[str, ...] = REFERENCE_TICKERS,
) -> set[dt.date]:
    """Union of days on which any reference instrument traded.

    Pass a single-element `tickers` to answer a cheap "did the market trade on
    this day?" question: a day present in one reference is proof the market was
    open, so no second fetch is needed to confirm it.
    """
    days: set[dt.date] = set()
    for ticker in tickers:
        days |= set(get_prices(ticker, start, end)["date"])
    return days


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
