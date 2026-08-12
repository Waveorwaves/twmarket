"""TWSE daily OHLCV — unadjusted raw exchange data, cached month-by-month."""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from . import _client, _store
from ._dates import parse_roc_date

_TICKER_RE = re.compile(r"^\d{4,6}$")

COLUMNS = ["date", "open", "high", "low", "close", "volume", "turnover"]


def _num(text: str) -> float | None:
    text = text.replace(",", "").strip()
    if text in ("", "--", "-", "X"):
        return None
    return float(text)


def parse_stock_day(payload: dict, ticker: str) -> pd.DataFrame:
    """Parse one STOCK_DAY JSON response into a daily OHLCV DataFrame.

    Rows: date, open, high, low, close, volume (shares), turnover (NTD).
    A non-"OK" stat (unknown ticker / no data) returns an empty DataFrame.
    """
    if payload.get("stat") != "OK" or not payload.get("data"):
        return _empty()
    records = []
    for row in payload["data"]:
        # 日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數[, 註記]
        records.append(
            {
                "date": parse_roc_date(row[0]),
                "open": _num(row[3]),
                "high": _num(row[4]),
                "low": _num(row[5]),
                "close": _num(row[6]),
                "volume": int(_num(row[1]) or 0),
                "turnover": int(_num(row[2]) or 0),
            }
        )
    return pd.DataFrame.from_records(records, columns=COLUMNS)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS).astype(
        {
            "date": "object",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "int64",
            "turnover": "int64",
        }
    )


def _months_between(start: dt.date, end: dt.date) -> list[tuple[int, int]]:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def ensure_month(ticker: str, year: int, month: int) -> pd.DataFrame:
    """Load one ticker-month from the store, fetching and caching if missing."""
    key = f"{ticker}_{year:04d}-{month:02d}"
    cached = _store.load_prices_month(key)
    if cached is not None:
        return cached
    payload = _client.fetch_stock_day(ticker, year, month)
    # Non-"OK" stat covers both unknown tickers and months with no data; TWSE
    # doesn't distinguish, so both yield an empty month (format validation of
    # tickers happens in get_prices).
    df = parse_stock_day(payload, ticker)
    today = dt.date.today()
    if (year, month) != (today.year, today.month):  # don't freeze a partial month
        _store.save_prices_month(key, df)
    return df


def get_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV for one ticker between two ISO dates (inclusive)."""
    if not _TICKER_RE.fullmatch(str(ticker)):
        raise ValueError(f"invalid ticker: {ticker!r}")
    start_d, end_d = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if start_d > end_d:
        raise ValueError(f"start {start} is after end {end}")
    frames = [ensure_month(ticker, y, m) for y, m in _months_between(start_d, end_d)]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else _empty()
    if df.empty:
        return _empty()
    df = df[(df["date"] >= start_d) & (df["date"] <= end_d)]
    return df.sort_values("date").reset_index(drop=True)
