"""Snapshot job: capture true announce dates and restatements going forward.

Run daily (e.g. cron). Re-fetches the current and prior month's bulk files,
diffs against the store, and appends new observations. `observed_date` is always
the date of the snapshot that saw the row; `announce_date` is when the figure
became knowable, which is only the same thing when we were watching in time:

- First sighting on or before the statutory deadline -> a genuine catch:
  announce_date = today, estimated=False. This is the point of sync().
- First sighting after the deadline -> the filing already happened at an unknown
  earlier date and MOPS preserves no timestamp, so fall back to the deadline
  estimate: announce_date = estimated deadline, estimated=True. Claiming today
  here would date the figure *later* than reality and call it authoritative.
- Changed revenue vs the latest stored observation -> restatement: a NEW row with
  is_restated=True, announce_date = today (we watched the value change, so that
  is the date it became knowable). The original row is never discarded.
- Unchanged rows -> nothing appended.

Detection only works from the date snapshotting begins.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import _client, _store
from ._dates import gregorian_year_to_roc, parse_period
from .revenue import announce_date_for, parse_bulk_file


def _current_and_prior_periods(today: dt.date) -> list[str]:
    y, m = today.year, today.month
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return [f"{py:04d}-{pm:02d}", f"{y:04d}-{m:02d}"]


def _latest_view(stored: pd.DataFrame) -> pd.DataFrame:
    """Latest observation per ticker within one period file (append order)."""
    return stored.groupby("ticker", as_index=False).tail(1)


def sync_period(period: str, today: dt.date | None = None) -> pd.DataFrame:
    """Snapshot one period; returns the newly appended observations."""
    today = today or dt.date.today()
    year, month = parse_period(period)
    try:
        content = _client.fetch_mops_revenue(gregorian_year_to_roc(year), month)
    except Exception:
        # Current month's file may not exist yet (nobody has filed) — skip quietly.
        return pd.DataFrame()
    fresh = parse_bulk_file(content, period)
    if fresh.empty:
        return pd.DataFrame()

    stored = _store.load_revenue_period(period)
    if stored is None or stored.empty:
        latest = pd.DataFrame(columns=["ticker", "revenue_twd"])
    else:
        latest = _latest_view(stored)[["ticker", "revenue_twd"]]

    merged = fresh.merge(latest, on="ticker", how="left", suffixes=("", "_stored"))
    is_new = merged["revenue_twd_stored"].isna() & merged["revenue_twd"].notna()
    # Carry the restatement flag as a column so it survives filtering without
    # relying on index alignment between `merged` and the filtered frame.
    merged["is_restated"] = (
        merged["revenue_twd_stored"].notna()
        & merged["revenue_twd"].notna()
        & (merged["revenue_twd"] != merged["revenue_twd_stored"])
    )
    new_obs = merged[is_new | merged["is_restated"]].drop(columns=["revenue_twd_stored"]).copy()
    if new_obs.empty:
        return pd.DataFrame()

    # A first sighting after the deadline cannot be dated; only a restatement is
    # observed as it happens regardless of when the period's deadline was.
    deadline = announce_date_for(period)
    undatable = (today > deadline) & ~new_obs["is_restated"]
    new_obs["announce_date"] = [deadline if late else today for late in undatable]
    new_obs["announce_date_estimated"] = undatable.to_numpy()
    new_obs["observed_date"] = today
    _store.append_revenue_observations(period, new_obs)
    return new_obs.reset_index(drop=True)


def run_sync(today: dt.date | None = None) -> pd.DataFrame:
    """Snapshot current + prior month. Returns all newly appended observations."""
    today = today or dt.date.today()
    frames = [sync_period(p, today) for p in _current_and_prior_periods(today)]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
