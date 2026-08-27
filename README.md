# twmarket

**Point-in-time Taiwan market data for quant research — in English.**

Taiwan is one of the few markets where every listed company must disclose **monthly revenue**
(by the 10th of the following month, per securities regulations). That's a high-frequency
fundamental signal you can't get in most markets — but the data lives on MOPS/TWSE sites
that are Chinese-only and hard to navigate programmatically.

`twmarket` gives you:

- **Monthly revenue** for all TWSE-listed companies, with **point-in-time semantics**
  (announce dates + restatement tracking, so your backtests don't cheat)
- **Daily prices** (unadjusted raw exchange data) from the official TWSE API
- **Trading calendar** derived from actual price history (typhoon closures and
  make-up Saturdays handled automatically), taken as the union of several reference
  instruments so a single stock's suspension can't masquerade as a market holiday

All data is cached locally in `~/.twmarket/` (parquet) — fetch once, query forever.
Requests are politely rate-limited (≥1 s spacing).

## Install

```bash
pip install git+https://github.com/Waveorwaves/twmarket.git
```

Requires Python 3.10+.

## Quickstart

```python
import twmarket as tw

# Monthly revenue (first call backfills from MOPS; ~1 request per month of data)
rev = tw.revenue("2330", "2024-01", "2025-06")
#   ticker, period, revenue_twd, yoy_pct, mom_pct,
#   announce_date, announce_date_estimated, is_restated

# Point-in-time: only figures that were knowable on that date
rev_pit = tw.revenue("2330", "2025-01", "2025-06", as_of="2025-06-05")
```

```python
# Daily prices (unadjusted) and trading calendar
px = tw.prices("2330", "2025-01-01", "2025-06-30")
#   date, open, high, low, close, volume, turnover
cal = tw.calendar("2025-01-01", "2025-06-30")  # one `date` column
```

```python
# Run daily (cron) to capture true announce dates and restatements going forward
tw.sync()
```

## Taiwan's monthly revenue disclosure, in 30 seconds

Every TWSE-listed company must file its prior month's revenue with MOPS by the **10th of
the following month**. Most file a few days early; a handful file at the deadline. Figures
are occasionally **restated** later. This makes monthly revenue the fastest broad
fundamental signal in the Taiwan market — if you handle announce timing honestly.

## Point-in-time honesty (read this before backtesting)

The MOPS bulk files preserve **no historical filing timestamps** — their report date is
generated at fetch time. So:

- **Backfilled history** gets `announce_date` = statutory deadline (10th of the following
  month, rolled forward to the next **trading day**), flagged
  `announce_date_estimated=True`. The roll uses the real trading calendar, not just
  weekends: the 10th lands inside the Lunar New Year closure often enough to matter
  (January 2013 revenue was due 2013-02-10, but the market did not reopen until
  2013-02-18). Conservative by design: most companies file earlier, so using the deadline
  can never introduce lookahead bias — but backtest signals will lag reality by a few days.
- **Going forward**, run `tw.sync()` daily (e.g. cron). It re-fetches the current and
  prior month's files and diffs against the local store. If a figure appears **on or
  before** its deadline, that sighting is a real announce date
  (`announce_date_estimated=False`) — this is what running `sync()` buys you. If it first
  appears **after** the deadline (a cold start, or a cron that was down), it was filed at
  a time MOPS does not record, so `twmarket` falls back to the deadline estimate and says
  so rather than dating the figure late and calling it authoritative.
- **Restatements**: a changed figure between snapshots is appended as a *new* observation
  with `is_restated=True` and its own date. The original row is **never discarded** —
  `tw.revenue(..., as_of=...)` returns exactly what was knowable at that date.
  Restatement detection only works from the date you start running `sync()`.
- **Months still being filed are never cached.** A period whose deadline hasn't passed is
  re-fetched on every query, so companies that file late in the window still show up.
  Once the deadline passes, the month is frozen into the store and served from disk.
- `yoy_pct` / `mom_pct` come from MOPS as published; they may diverge from values you
  compute from stored revenue around mergers and restatements.

## Error semantics

- Invalid ticker → `ValueError`
- Valid ticker with no data in range → empty DataFrame with correct columns

## Scope (v0.1)

TWSE-listed only. Not included: TPEx/OTC, quarterly financials, adjusted prices,
institutional flows, real-time quotes. The calendar is historical — it cannot predict
future trading days (price history starts 2010-01-04, the TWSE API floor).

See [docs/sources.md](docs/sources.md) for endpoint details and
[twmarket.md](twmarket.md) for the full spec.

## Development

```bash
pip install -e ".[dev]"
ruff check . && pytest
```

Tests run entirely against recorded fixtures — they never hit live TWSE/MOPS endpoints.

## License

MIT
