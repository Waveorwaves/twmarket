"""Local parquet store (~/.twmarket/), month-granular, append-only observations.

Grain: (ticker, period, observed_date). Rows are never overwritten or deleted;
queries derive "latest" or "as-of" views from the observation history.
Set TWMARKET_DATA_DIR to relocate the store (used by tests).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

REVENUE_COLUMNS = {
    "ticker": "string",
    "name": "string",
    "period": "string",
    "revenue_twd": "Int64",
    "mom_pct": "float64",
    "yoy_pct": "float64",
    "announce_date": "object",  # datetime.date
    "announce_date_estimated": "bool",
    "is_restated": "bool",
    "observed_date": "object",  # datetime.date
}


def data_dir() -> Path:
    return Path(os.environ.get("TWMARKET_DATA_DIR", "~/.twmarket")).expanduser()


def _revenue_path(period: str) -> Path:
    return data_dir() / "revenue" / f"{period}.parquet"


def has_revenue_period(period: str) -> bool:
    return _revenue_path(period).exists()


def load_revenue_period(period: str) -> pd.DataFrame | None:
    path = _revenue_path(period)
    return pd.read_parquet(path) if path.exists() else None


def list_revenue_periods() -> list[str]:
    folder = data_dir() / "revenue"
    if not folder.exists():
        return []
    return sorted(
        p.stem for p in folder.glob("*.parquet") if re.fullmatch(r"\d{4}-\d{2}", p.stem)
    )


def _prices_path(key: str) -> Path:
    return data_dir() / "prices" / f"{key}.parquet"


def load_prices_month(key: str) -> pd.DataFrame | None:
    """key = '{ticker}_{YYYY-MM}'. Returns None if not cached."""
    path = _prices_path(key)
    return pd.read_parquet(path) if path.exists() else None


def save_prices_month(key: str, df: pd.DataFrame) -> None:
    path = _prices_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def append_revenue_observations(period: str, df: pd.DataFrame) -> None:
    """Append observation rows for one period (never overwrites existing rows)."""
    df = df.astype(REVENUE_COLUMNS)[list(REVENUE_COLUMNS)]
    path = _revenue_path(period)
    existing = pd.read_parquet(path) if path.exists() else None
    if existing is not None:
        df = pd.concat([existing, df], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
