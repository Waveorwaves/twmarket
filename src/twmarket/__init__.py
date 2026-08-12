"""twmarket — point-in-time Taiwan market data for quant research.

Public API:
    revenue()   Monthly revenue (MOPS) with point-in-time announce dates
    prices()    Daily OHLCV from TWSE (unadjusted raw exchange data)
    calendar()  Trading days derived from price history
    sync()      Snapshot job: capture observed announce dates and restatements
"""

__version__ = "0.1.0"

__all__ = ["revenue", "prices", "calendar", "sync"]

# Import submodules first so the public functions defined below shadow the
# module objects on the package (import twmarket.revenue would otherwise
# rebind twmarket.revenue to the module).
from . import revenue as _revenue_mod  # noqa: E402, F401


def revenue(ticker, start=None, end=None, as_of=None):
    """Monthly revenue for a TWSE-listed ticker.

    Args:
        ticker: e.g. "2330". Invalid tickers raise ValueError.
        start, end: period range as "YYYY-MM" (inclusive). Defaults to full
            history (2015-01 through last completed month).
        as_of: ISO date; return only figures knowable on that date
            (point-in-time view based on announce_date).

    Returns a DataFrame with columns: ticker, period, revenue_twd, yoy_pct,
    mom_pct, announce_date, announce_date_estimated, is_restated.
    """
    return _revenue_mod.get_revenue(ticker, start, end, as_of)


def prices(ticker, start, end):
    """Daily OHLCV for a TWSE-listed ticker. Not yet implemented."""
    raise NotImplementedError("Coming in v0.1 — see build plan")


def calendar(start, end):
    """Trading days between start and end. Not yet implemented."""
    raise NotImplementedError("Coming in v0.1 — see build plan")


def sync():
    """Snapshot job: record observed announce dates and restatements. Not yet implemented."""
    raise NotImplementedError("Coming in v0.1 — see build plan")
