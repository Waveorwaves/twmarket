"""MOPS monthly revenue: bulk-file parsing and point-in-time queries."""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from . import _client, _store
from ._dates import estimate_announce_date, gregorian_year_to_roc, parse_period

BACKFILL_START = "2015-01"

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


def ensure_period(period: str) -> None:
    """Fetch, parse, and store one bulk month if not already cached."""
    if _store.has_revenue_period(period):
        return
    year, month = parse_period(period)
    content = _client.fetch_mops_revenue(gregorian_year_to_roc(year), month)
    df = parse_bulk_file(content, period)
    df["announce_date"] = estimate_announce_date(period)
    df["announce_date_estimated"] = True
    df["is_restated"] = False
    df["observed_date"] = dt.date.today()
    _store.append_revenue_observations(period, df)


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
        ensure_period(period)
        df = _store.load_revenue_period(period)
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
