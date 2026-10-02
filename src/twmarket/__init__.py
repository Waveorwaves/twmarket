"""twmarket — point-in-time Taiwan market data for quant research.

Public API:
    revenue()   Monthly revenue (MOPS) with point-in-time announce dates
    prices()    Daily OHLCV from TWSE (unadjusted raw exchange data)
    calendar()  Trading days derived from price history
    sync()      Snapshot job: capture observed announce dates and restatements

    is_trading_day(), next_trading_day()   Single-date lookups on that calendar
"""

__version__ = "0.1.1"

__all__ = ["revenue", "prices", "calendar", "sync", "is_trading_day", "next_trading_day"]

# Import submodules first so the public functions defined below shadow the
# module objects on the package (import twmarket.revenue would otherwise
# rebind twmarket.revenue to the module).
from . import calendar as _calendar_mod  # noqa: E402
from . import prices as _prices_mod  # noqa: E402
from . import revenue as _revenue_mod  # noqa: E402
from . import sync as _sync_mod  # noqa: E402

# `twmarket.calendar` is the function below, so these cannot be reached through it.
from .calendar import is_trading_day, next_trading_day  # noqa: E402


def revenue(ticker, start=None, end=None, as_of=None):
    """Monthly revenue for a TWSE-listed ticker.

    Args:
        ticker: a string such as "2330". A malformed ticker raises ValueError,
            and so does one that is not in the latest settled month of the range
            (a typo, or a delisted company queried past its last month).
        start, end: period range as "YYYY-MM" (inclusive). Defaults to full
            history (2015-01 through last completed month). The earliest
            month available is 2013-01. A cold cache downloads about six
            seconds' worth per month of history, with a progress line on stderr.
        as_of: ISO date; return only figures knowable on that date
            (point-in-time view based on announce_date).

    Returns a DataFrame with columns: ticker, period, revenue_twd, yoy_pct,
    mom_pct, announce_date, announce_date_estimated, is_restated.

    Example:
        >>> import twmarket as tw
        >>> tw.revenue("2330", "2025-05", "2025-06")[["period", "revenue_twd", "announce_date"]]
            period   revenue_twd announce_date
        0  2025-05  320515951000    2025-06-10
        1  2025-06  263708978000    2025-07-10
        >>> len(tw.revenue("2330", "2025-05", "2025-06", as_of="2025-06-30"))  # June not out yet
        1
    """
    return _revenue_mod.get_revenue(ticker, start, end, as_of)


def prices(ticker, start, end):
    """Daily OHLCV for a TWSE-listed ticker (unadjusted raw exchange data).

    Args:
        ticker: a string such as "2330". A malformed ticker raises ValueError.
        start, end: ISO dates (inclusive), e.g. "2025-01-01".

    Returns a DataFrame with columns: date, open, high, low, close,
    volume (shares), turnover (NTD). Cached month-by-month in ~/.twmarket.

    Example:
        >>> import twmarket as tw
        >>> tw.prices("2330", "2025-06-02", "2025-06-03")[["date", "open", "close", "volume"]]
                 date   open  close    volume
        0  2025-06-02  958.0  946.0  40608468
        1  2025-06-03  960.0  950.0  27482916
    """
    return _prices_mod.get_prices(ticker, start, end)


def calendar(start, end):
    """Trading days between two ISO dates (inclusive).

    Derived from real price history (the union of 0050 and 2330), so typhoon
    closures and make-up Saturdays are handled automatically and one
    instrument's suspension is not mistaken for a holiday. Cannot predict
    future trading days; history begins 2010-01-04 (TWSE API limit).

    Returns a DataFrame with a single `date` column.

    Example:
        >>> import twmarket as tw
        >>> list(tw.calendar("2025-01-20", "2025-02-04")["date"].astype(str))
        ['2025-01-20', '2025-01-21', '2025-01-22', '2025-02-03', '2025-02-04']
    """
    return _calendar_mod.get_calendar(start, end)


def sync():
    """Snapshot job: record observed announce dates and restatements.

    Re-fetches the current and prior month's MOPS bulk files, diffs against the
    local store, and appends new observations. A row first seen on or before its
    statutory deadline gets that sighting as a true announce_date
    (announce_date_estimated=False). A row first seen after the deadline, with
    no earlier check on or after the deadline, was filed at an unknowable earlier
    time and falls back to the deadline estimate; if an earlier check did not
    have it, it filed late and is dated the day it appeared. Restatements append
    a new row with is_restated=True, dated the day the change was observed. Run
    daily via cron for real announce dates going forward.

    Returns a DataFrame of newly appended observations (empty if none).

    Example (run once a day, e.g. from cron):
        >>> import twmarket as tw
        >>> new = tw.sync()
        >>> len(new)  # companies that filed, or restated, since the last run
        8
    """
    return _sync_mod.run_sync()
