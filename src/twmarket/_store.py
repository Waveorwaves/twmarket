"""Local parquet store (~/.twmarket/), month-granular, append-only observations.

Grain: (ticker, period, observed_date). Rows are never overwritten or deleted;
queries derive "latest" or "as-of" views from the observation history.
Set TWMARKET_DATA_DIR to relocate the store (used by tests).

Observations only record what changed. `revenue/checked.json` records when each
period was last compared with MOPS, including the days nothing had changed —
without it "this company was not there yesterday" leaves no trace.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("twmarket")

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


def _checked_path() -> Path:
    return data_dir() / "revenue" / "checked.json"


def _load_checks() -> dict[str, str]:
    path = _checked_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        # Losing the check dates is safe: callers fall back to the newest stored
        # observation, which can only make a date an estimate, never earlier.
        logger.warning("%s is unreadable; ignoring it and starting a new one", path)
        return {}


def revenue_last_checked(period: str) -> dt.date | None:
    """Date the store was last brought level with MOPS for this period, if recorded."""
    value = _load_checks().get(period)
    return dt.date.fromisoformat(value) if value else None


def mark_revenue_checked(period: str, date: dt.date) -> None:
    """Record that the store matched MOPS for this period on `date`."""
    path = _checked_path()
    checks = _load_checks()
    if checks.get(period, "") < date.isoformat():
        checks[period] = date.isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename, so an interrupted run cannot leave half a file behind.
        scratch = path.with_suffix(".json.tmp")
        scratch.write_text(json.dumps(checks, indent=0, sort_keys=True))
        os.replace(scratch, path)


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


def normalize_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce observation rows to the stored column set and dtypes.

    Applied on the way into the store, and to rows served without being stored,
    so callers see identical frames either way.
    """
    return df.astype(REVENUE_COLUMNS)[list(REVENUE_COLUMNS)]


def append_revenue_observations(period: str, df: pd.DataFrame) -> None:
    """Append observation rows for one period (never overwrites existing rows)."""
    df = normalize_revenue(df)
    path = _revenue_path(period)
    existing = pd.read_parquet(path) if path.exists() else None
    if existing is not None:
        df = pd.concat([existing, df], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
