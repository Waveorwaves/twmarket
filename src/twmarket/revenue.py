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
    taipei_today,
)
from .calendar import REFERENCE_TICKERS, trading_days

logger = logging.getLogger("twmarket")

BACKFILL_START = "2015-01"

#: First month this package can serve. MOPS moved to IFRS consolidated revenue in
#: January 2013; earlier bulk files use a different page layout and their figures
#: are not on that basis, so they are not comparable with what follows.
EARLIEST_PERIOD = "2013-01"

#: How far past the statutory deadline to look for the next trading day. The
#: longest TWSE closure is the Lunar New Year break (~9 calendar days), and
#: 10 + 14 stays inside the same month, so this costs one cached price-month.
ANNOUNCE_ROLL_WINDOW_DAYS = 14

#: Fewest rows a month may have once its filing window has closed. TWSE lists
#: roughly a thousand companies (990 in the 2025-06 file), so a settled file with
#: fewer than half that is a truncated or re-laid-out page, not a quiet month.
MIN_SETTLED_ROWS = 500

OUTPUT_COLUMNS = [
    "ticker", "period", "revenue_twd", "yoy_pct", "mom_pct",
    "announce_date", "announce_date_estimated", "is_restated",
]  # fmt: skip

_TICKER_RE = re.compile(r"^\d{4,6}$")

# Data rows are <tr align=right> with 11 <td> cells whose first cell is a ticker.
# Industry-total (合計) rows share the <tr> pattern but have no ticker cell, which is
# what excludes them — matching on the text 合計 would also drop a company whose
# name happens to contain it.
_ROW_RE = re.compile(r"<tr align=right>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# MOPS answers a month nobody has filed yet with HTTP 200 and a short page whose
# only content is this "no data found" message — never with a 404.
_UNPUBLISHED_MARKER = "查無資料"


def _clean(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", " ").strip()


def _num(text: str) -> float | None:
    text = text.replace(",", "").strip()
    # 不適用 = "not applicable": e.g. no prior month to compare with in 2013-01,
    # the first month of IFRS reporting.
    if text in ("", "-", "不適用"):
        return None
    return float(text)


def parse_bulk_file(content: bytes, period: str) -> pd.DataFrame:
    """Parse one MOPS t21sc03 bulk file (raw Big5 bytes) into a DataFrame.

    Columns: ticker, name, period, revenue_twd (source is thousand NTD; converted
    to NTD here), yoy_pct, mom_pct. Industry 合計 (total) rows are excluded.

    Returns an empty frame only for MOPS's "no data found" page, i.e. a month
    that is not published yet. Any other page that yields no rows raises
    ValueError: it almost certainly means MOPS changed its layout, and an empty
    result would otherwise pass for a month in which nobody filed.
    """
    text = content.decode("big5", errors="replace")
    records = []
    for row in _ROW_RE.findall(text):
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
    if not records and _UNPUBLISHED_MARKER not in text:
        raise ValueError(
            f"MOPS bulk file for {period} parsed to zero rows ({len(content):,} bytes) "
            "and is not the 'no data found' page — the page layout may have changed"
        )
    df = pd.DataFrame.from_records(
        records, columns=["ticker", "name", "period", "revenue_twd", "mom_pct", "yoy_pct"]
    )
    df["revenue_twd"] = df["revenue_twd"].astype("Int64")
    return df


def check_settled_row_count(df: pd.DataFrame, period: str) -> None:
    """Refuse a month that is past its deadline yet implausibly thin.

    Only for settled periods: while the filing window is open a short file is
    normal, because most companies have not filed yet.
    """
    if len(df) < MIN_SETTLED_ROWS:
        raise ValueError(
            f"MOPS bulk file for {period} has only {len(df)} rows after its filing "
            f"deadline (expected at least {MIN_SETTLED_ROWS}) — the page is truncated or "
            "its layout changed; nothing was stored"
        )


def _month_range(start: str, end: str) -> list[str]:
    (y0, m0), (y1, m1) = parse_period(start), parse_period(end)
    months = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def _last_completed_period(today: dt.date | None = None) -> str:
    today = today or taipei_today()
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


def last_checked(period: str, stored: pd.DataFrame | None) -> dt.date | None:
    """Latest date on which the store is known to have matched MOPS for a period.

    The recorded check date where there is one, otherwise the newest observation
    (stores written before check dates were recorded have only that).
    """
    dates = [_store.revenue_last_checked(period)]
    if stored is not None and not stored.empty:
        dates.append(max(stored["observed_date"]))
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def _is_settled(stored: pd.DataFrame, period: str) -> bool:
    """True if the store was compared with MOPS after the period's filing deadline.

    Rows written while the filing window was still open — by an early query, or
    by a `sync()` that ran before the 10th — can be missing every company that
    filed later, so the file cannot be taken as complete until something has
    looked again after the deadline.
    """
    checked = last_checked(period, stored)
    # Cheap bound first: past the widest possible roll no calendar is needed,
    # which keeps the fully-cached query path free of price lookups.
    if checked > statutory_deadline(period) + dt.timedelta(days=ANNOUNCE_ROLL_WINDOW_DAYS):
        return True
    return checked > announce_date_for(period)


def ensure_period(period: str, today: dt.date | None = None) -> pd.DataFrame:
    """All stored observations for one period, fetching the bulk file if needed.

    A period whose filing deadline has not passed is fetched but **not cached**.
    Companies file throughout the window, so freezing an early snapshot would
    hide every filing that lands after it: the store is append-only and the
    month would read as complete forever. A period already holding rows that
    were all observed while the window was open is topped up through the differ,
    which appends late filers without duplicating what is already held.
    """
    today = today or taipei_today()
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
    if df.empty:
        # Not published yet. Never cache it: the next query should ask again.
        logger.info("%s is not published on MOPS yet", period)
        return _store.normalize_revenue(pd.DataFrame(columns=list(_store.REVENUE_COLUMNS)))
    announce = announce_date_for(period)
    df["announce_date"] = announce
    df["announce_date_estimated"] = True
    df["is_restated"] = False
    df["observed_date"] = today
    df = _store.normalize_revenue(df)

    if today > announce:
        check_settled_row_count(df, period)
        _store.append_revenue_observations(period, df)
        _store.mark_revenue_checked(period, today)
    else:
        logger.info(
            "%s filing window is still open (deadline %s) — serving fresh, not caching",
            period,
            announce,
        )
    return df


def _probe_order(periods: list[str], today: dt.date) -> list[tuple[str, bool]]:
    """Months to look a ticker up in, as (period, settled), most conclusive first.

    A settled month — its filing window has closed — is complete, so a listed
    company is certain to be in it. Those come first, latest first. Months still
    being filed follow: finding the ticker there proves it exists, but not
    finding it proves nothing.
    """
    open_window = []
    last = len(periods) - 1
    while last >= 0:
        period = periods[last]
        # The deadline itself is a cheap lower bound; only ask the calendar for
        # the rolled date once that has passed.
        if today > statutory_deadline(period) and today > announce_date_for(period):
            break
        open_window.append((period, False))
        last -= 1
    return [(p, True) for p in reversed(periods[: last + 1])] + open_window


def get_revenue(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Monthly revenue for one ticker, latest view or point-in-time (`as_of`).

    Reads the local store and fetches any missing months in the range
    (rate-limited: about one request per uncached month, at least 1s apart).
    Default range is BACKFILL_START through the last completed month.

    The ticker is looked up in one month first — the latest settled month of the
    range — so a mistyped ticker fails after a single fetch instead of after the
    whole backfill. A company that is not in that month raises ValueError even
    if it appears earlier in the range; for a delisted company pass an `end` no
    later than its last month.
    """
    # Strings only: an int cannot carry a leading zero (0050 would arrive as 50).
    if not isinstance(ticker, str) or not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"invalid ticker: {ticker!r} (pass a string of 4-6 digits, e.g. '2330')")
    start, end = start or BACKFILL_START, end or _last_completed_period()
    as_of_date = dt.date.fromisoformat(as_of) if as_of else None
    periods = _month_range(start, end)
    if not periods:
        raise ValueError(f"start {start} is after end {end}")
    if start < EARLIEST_PERIOD:
        raise ValueError(
            f"revenue history starts at {EARLIEST_PERIOD} (got start={start}): MOPS moved to "
            "IFRS consolidated revenue that month, and earlier files are not comparable"
        )

    today = taipei_today()
    loaded: dict[str, pd.DataFrame] = {}
    for period, settled in _probe_order(periods, today):
        df = loaded[period] = ensure_period(period, today)
        if (df["ticker"] == ticker).any():
            break
        if settled and not df.empty:
            raise ValueError(
                f"unknown ticker: {ticker!r} is not in MOPS's {period} file, the latest "
                "settled month of the requested range. Check for a typo. For a delisted "
                "company pass an `end` no later than its last month; for a newly listed "
                "one pass a range that starts at its first month."
            )
        # Unpublished, or still being filed: absence here proves nothing.

    frames = []
    for period in periods:
        df = loaded[period] if period in loaded else ensure_period(period, today)
        frames.append(df[df["ticker"] == ticker])

    obs = pd.concat(frames, ignore_index=True)
    if as_of_date is not None:
        obs = obs[obs["announce_date"] <= as_of_date]
    # Latest observation per period (append order = observation order within a period).
    # An empty result goes through the same steps, so it keeps the stored dtypes.
    obs = obs.groupby("period", as_index=False).tail(1)
    return obs.sort_values("period")[OUTPUT_COLUMNS].reset_index(drop=True)
