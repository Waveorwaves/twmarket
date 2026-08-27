"""MOPS monthly revenue: bulk-file parsing and point-in-time queries."""

from __future__ import annotations

import datetime as dt
import logging
import re

import pandas as pd

from . import _client, _store
from ._dates import (
    estimate_announce_date,
    gregorian_year_to_roc,
    parse_period,
    statutory_deadline,
)
from .calendar import REFERENCE_TICKERS, trading_days

logger = logging.getLogger("twmarket")

BACKFILL_START = "2015-01"

#: How far past the statutory deadline to look for the next trading day. The
#: longest TWSE closure is the Lunar New Year break (~9 calendar days), and
#: 10 + 14 stays inside the same month, so this costs one cached price-month.
ANNOUNCE_ROLL_WINDOW_DAYS = 14

_TICKER_RE = re.compile(r"^\d{4,6}$")

# Data rows are <tr align=right> with 11 <td> cells; industry-total (合計) rows use
# <th> cells inside the same <tr> pattern and are skipped by requiring an all-<td> row.
_ROW_RE = re.compile(r"<tr align=right>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", " ").strip()


def _num(text: str) -> float | None:
    text = text.replace(",", "").strip()
    if text in ("", "-"):
        return None
    return float(text)


def parse_bulk_file(content: bytes, period: str) -> pd.DataFrame:
    """Parse one MOPS t21sc03 bulk file (raw Big5 bytes) into a DataFrame.

    Columns: ticker, name, period, revenue_twd (source is thousand NTD; converted
    to NTD here), yoy_pct, mom_pct. Industry 合計 (total) rows are excluded.
    """
    text = content.decode("big5", errors="replace")
    records = []
    for row in _ROW_RE.findall(text):
        if "合計" in row:
            continue
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) != 11 or not re.fullmatch(r"\d{4,6}", cells[0]):
            continue
        revenue = _num(cells[2])
        records.append(
            {
                "ticker": cells[0],
                "name": cells[1],
                "period": period,
                "revenue_twd": None if revenue is None else int(revenue * 1000),
                "mom_pct": _num(cells[5]),
                "yoy_pct": _num(cells[6]),
            }
        )
    df = pd.DataFrame.from_records(
        records, columns=["ticker", "name", "period", "revenue_twd", "mom_pct", "yoy_pct"]
    )
    df["revenue_twd"] = df["revenue_twd"].astype("Int64")
    return df


def _month_range(start: str, end: str) -> list[str]:
    (y0, m0), (y1, m1) = parse_period(start), parse_period(end)
    months = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def _last_completed_period(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{y:04d}-{m:02d}"


def announce_date_for(period: str) -> dt.date:
    """Estimated announce date: the deadline rolled to the next *trading* day.

    Rolling over weekends alone is not conservative enough. The 10th lands
    inside the Lunar New Year closure often enough to matter: January 2013
    revenue was due Sunday 2013-02-10, the weekday roll lands on Monday
    2013-02-11, and TWSE did not trade again until 2013-02-18.
    An announce date on a closed market is a week earlier than the market could
    possibly have reacted — exactly the lookahead bias this package exists to
    prevent — so the real trading calendar decides.

    One cached price-month per call, and usually one request: a deadline that
    already appears in the primary reference's history is proof the market was
    open, so no second reference is consulted.

    Beyond available price history (a deadline still in the future, or before
    the 2010 floor) no calendar exists; that falls back to the weekday-only
    roll, which can name a market holiday. `ensure_period` avoids storing such
    a date by refusing to cache a period whose deadline has not passed.
    """
    deadline = statutory_deadline(period)
    horizon = (deadline + dt.timedelta(days=ANNOUNCE_ROLL_WINDOW_DAYS)).isoformat()
    days = trading_days(deadline.isoformat(), horizon, tickers=REFERENCE_TICKERS[:1])
    if deadline not in days:
        # Absence in one instrument is ambiguous (holiday or suspension), so pay
        # for the full union before concluding the market was closed.
        days = trading_days(deadline.isoformat(), horizon)
    later = sorted(d for d in days if d >= deadline)
    if later:
        return later[0]
    logger.info(
        "no trading calendar covering the %s deadline (%s) — falling back to the "
        "weekday-only estimate",
        period,
        deadline,
    )
    return estimate_announce_date(period)


def _is_settled(stored: pd.DataFrame, period: str) -> bool:
    """True if some stored observation postdates the period's filing deadline.

    Rows written while the filing window was still open — by an early query, or
    by a `sync()` that ran before the 10th — can be missing every company that
    filed later, so the file cannot be taken as complete.
    """
    last_seen = max(stored["observed_date"])
    # Cheap bound first: past the widest possible roll no calendar is needed,
    # which keeps the fully-cached query path free of price lookups.
    if last_seen > statutory_deadline(period) + dt.timedelta(days=ANNOUNCE_ROLL_WINDOW_DAYS):
        return True
    return last_seen > announce_date_for(period)


def ensure_period(period: str, today: dt.date | None = None) -> pd.DataFrame:
    """All stored observations for one period, fetching the bulk file if needed.

    A period whose filing deadline has not passed is fetched but **not cached**.
    Companies file throughout the window, so freezing an early snapshot would
    hide every filing that lands after it: the store is append-only and the
    month would read as complete forever. A period already holding rows that
    were all observed while the window was open is topped up through the differ,
    which appends late filers without duplicating what is already held.
    """
    today = today or dt.date.today()
    stored = _store.load_revenue_period(period)
    if stored is not None and not stored.empty:
        if _is_settled(stored, period):
            return stored
        from .sync import sync_period  # deferred: sync builds on this module

        sync_period(period, today=today)
        return _store.load_revenue_period(period)

    year, month = parse_period(period)
    logger.info("fetching MOPS bulk file for %s", period)
    content = _client.fetch_mops_revenue(gregorian_year_to_roc(year), month)
    df = parse_bulk_file(content, period)
    announce = announce_date_for(period)
    df["announce_date"] = announce
    df["announce_date_estimated"] = True
    df["is_restated"] = False
    df["observed_date"] = today
    df = _store.normalize_revenue(df)

    if today > announce:
        _store.append_revenue_observations(period, df)
    else:
        logger.info(
            "%s filing window is still open (deadline %s) — serving fresh, not caching",
            period,
            announce,
        )
    return df


def get_revenue(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Monthly revenue for one ticker, latest view or point-in-time (`as_of`).

    Reads the local store and fetches any missing months in the range
    (rate-limited). Default range is BACKFILL_START through the last
    completed month.
    """
    if not _TICKER_RE.fullmatch(str(ticker)):
        raise ValueError(f"invalid ticker: {ticker!r}")
    start, end = start or BACKFILL_START, end or _last_completed_period()
    as_of_date = dt.date.fromisoformat(as_of) if as_of else None

    frames, seen_anywhere = [], False
    for period in _month_range(start, end):
        df = ensure_period(period)
        if df is None or df.empty:
            continue
        seen_anywhere = seen_anywhere or (df["ticker"] == ticker).any()
        frames.append(df[df["ticker"] == ticker])

    columns = [
        "ticker", "period", "revenue_twd", "yoy_pct", "mom_pct",
        "announce_date", "announce_date_estimated", "is_restated",
    ]  # fmt: skip
    if not seen_anywhere:
        raise ValueError(f"unknown ticker: {ticker!r} (not found in any fetched month)")
    obs = pd.concat(frames, ignore_index=True)
    if as_of_date is not None:
        obs = obs[obs["announce_date"] <= as_of_date]
    if obs.empty:
        return pd.DataFrame(columns=columns)
    # Latest observation per period (append order = observation order within a period)
    obs = obs.groupby("period", as_index=False).tail(1)
    return obs.sort_values("period")[columns].reset_index(drop=True)
