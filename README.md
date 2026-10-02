# twmarket

[![CI](https://github.com/Waveorwaves/twmarket/actions/workflows/ci.yml/badge.svg)](https://github.com/Waveorwaves/twmarket/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/twmarket)](https://pypi.org/project/twmarket/)
[![Python](https://img.shields.io/pypi/pyversions/twmarket)](https://pypi.org/project/twmarket/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Waveorwaves/twmarket/blob/main/LICENSE)

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
Requests are politely rate-limited (≥1 s spacing), so **the first call for a range is
slow: about 6 seconds per month of revenue history**. Six months takes about half a
minute; the full history from 2015 takes about 15 minutes. A progress line shows it is
working. After that, a full-history query for any ticker takes about a quarter of a
second, so looping over hundreds of tickers is practical. Set `TWMARKET_PROGRESS=0` to silence
the progress line.

## Install

```bash
pip install twmarket
```

Requires Python 3.10 or newer (tested on 3.10 to 3.14, with pandas 2.0 through 3.x, on
Linux and macOS). Windows should work but has not been tested.

## Quickstart

```python
import twmarket as tw

# Monthly revenue. The first call downloads from MOPS (about 30 s for these six
# months, with a progress line); after that it is served from the local cache.
rev = tw.revenue("2330", "2025-01", "2025-06")
#   ticker, period, revenue_twd, yoy_pct, mom_pct,
#   announce_date, announce_date_estimated, is_restated

# Point-in-time: only figures that were knowable on that date
# (dates can be strings like this, or date / datetime / pandas Timestamp objects)
rev_pit = tw.revenue("2330", "2025-01", "2025-06", as_of="2025-06-05")
```

```python
# Daily prices (unadjusted) and trading calendar
px = tw.prices("2330", "2025-01-01", "2025-06-30")
#   date, open, high, low, close, volume, turnover
cal = tw.calendar("2025-01-01", "2025-06-30")  # one `date` column
tw.is_trading_day("2025-01-28")                # False: Lunar New Year closure
tw.next_trading_day("2025-01-22")              # datetime.date(2025, 2, 3)
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
generated at fetch time. So **every announce date for history is an estimate**, and is
flagged as one. Real, observed dates exist only for months that pass while you run
`tw.sync()` daily. In detail:

- **Backfilled history** gets `announce_date` = statutory deadline (10th of the following
  month, rolled forward to the next **trading day**), flagged
  `announce_date_estimated=True`. The roll uses the real trading calendar, not just
  weekends: the 10th lands inside the Lunar New Year closure often enough to matter
  (January 2013 revenue was due 2013-02-10, but the market did not reopen until
  2013-02-18). For a company that files on time this is conservative: it filed on or
  before the deadline, so the estimate is never early, only a few days late.
  **For a company that files late, the estimate is early** — it names a deadline the
  company missed — and that is lookahead. This is not rare enough to ignore: for July
  2026, 13 of the 31 financial-sector companies (Fubon, Cathay, CTBC and others) were
  still missing from MOPS two days after the deadline. That is one observed month, not a
  measured pattern. If it matters to your backtest, treat rows with
  `announce_date_estimated=True` as "deadline, possibly a few days more", or lag them.
- **Going forward**, run `tw.sync()` daily (e.g. cron). It re-fetches the current and
  prior month's files and diffs against the local store. If a figure appears **on or
  before** its deadline, that sighting is a real announce date
  (`announce_date_estimated=False`) — this is what running `sync()` buys you. If it first
  appears **after** the deadline (a cold start, or a cron that was down), it was filed at
  a time MOPS does not record, so `twmarket` falls back to the deadline estimate and says
  so rather than dating the figure late and calling it authoritative.
- **Late filers are dated when they actually appear.** Each `sync()` records that it
  looked, even on days nothing changed. So if a check after the deadline did not have a
  company and a later one does, that company filed late, and its `announce_date` is the
  day it showed up — not the deadline it missed. An observed date is as precise as your
  checks are frequent: daily `sync()` gives the day, a month-long gap gives the month.
  One case still falls back to the estimate: if no check ran between the deadline and the
  late filing (the cron was down across it), nothing shows the company was absent.
- **Restatements**: a changed figure between snapshots is appended as a *new* observation
  with `is_restated=True` and its own date. The original row is **never discarded** —
  `tw.revenue(..., as_of=...)` returns exactly what was knowable at that date.
  Restatement detection only works from the date you start running `sync()`.
- **A month is not final until the end of the month after it.** Before its deadline it
  is not cached at all. After the deadline it is stored, but every query still compares
  it with MOPS (one request), because late filers keep arriving. Once the following month
  has ended — when `sync()` stops re-checking it too — one last comparison makes it
  final, and it is served from disk from then on.
- **`as_of` means "known by the end of that day".** `announce_date` is a calendar date
  and companies can file after the 13:30 close, so a figure with `announce_date` D may
  not have been tradable on D. Act on it from the next trading day
  (`tw.next_trading_day(D)`).
- **Every date is a Taiwan date**, whatever timezone your machine is in. A cron job in
  Chicago or London still stamps observations with the date in Taipei, so a filing never
  looks like it was knowable the day before it happened.
- `yoy_pct` / `mom_pct` come from MOPS as published; they may diverge from values you
  compute from stored revenue around mergers and restatements.

## Running `sync()` every day

Any scheduler works. With cron, once a day late in the Taiwan evening (23:00 in Taipei is
15:00 UTC), so that day's filings are stamped with that day:

```bash
0 15 * * * /full/path/to/python -c "import twmarket as tw; tw.sync()" >> ~/twmarket-sync.log 2>&1
```

Adjust the hour to your machine's timezone. `sync()` raises if MOPS cannot be reached, so
a failed run shows up in the log instead of passing silently — a missed day cannot be
recovered later.

## Error semantics

- Malformed ticker → `ValueError` (all functions). Tickers are strings: `"0050"`, not
  `50` — a number can't carry the leading zero.
- `revenue()` looks the ticker up in one month first — the latest *final* month of your
  range — so a typo fails after a single request instead of after the whole backfill.
  Not in that month → `ValueError`. For a **delisted** company, pass an `end` no later
  than its last month. A recent month that can still gain late filers is never used as
  evidence that a ticker doesn't exist.
- `revenue()`: ticker found, but nothing knowable yet (e.g. `as_of` before the announce
  date, or a month it hasn't filed for yet) → empty DataFrame with the correct columns
  and dtypes.
- `revenue()`: start after end → `ValueError`.
- `prices()`: no data in range → empty DataFrame with the correct columns. TWSE answers
  an unknown ticker exactly like a month with no trading, so the two can't be told apart.

## Scope (v0.1.x)

TWSE-listed only. Not included: TPEx/OTC, quarterly financials, adjusted prices,
institutional flows, real-time quotes. The calendar is historical — it cannot predict
future trading days (price history starts 2010-01-04, the TWSE API floor).

Known limits:

- **Revenue starts at 2013-01.** MOPS moved to IFRS consolidated revenue that month;
  earlier files use a different layout and their figures are not comparable. An earlier
  `start` raises `ValueError`.
- **Restatements are only caught for the current and previous month**, because those are
  the two files `sync()` re-checks. A figure revised later than that goes unnoticed.
- **`prices()` takes all-digit tickers only** (`"2330"`, `"0050"`). Codes with a letter,
  such as the leveraged ETF `00631L` or preferred shares, are rejected.
- **One process at a time.** The local store has no locking, so don't run `sync()` and a
  query against the same store at the same moment.
- **Interrupting a download is safe.** Months already downloaded stay cached and the next
  call carries on from there. If a stored revenue file ever becomes unreadable, the error
  names the file; delete it and that month is downloaded again.

See [docs/sources.md](https://github.com/Waveorwaves/twmarket/blob/main/docs/sources.md) for endpoint details, the
[changelog](https://github.com/Waveorwaves/twmarket/blob/main/CHANGELOG.md) for what changed in each version, and
[docs/dev/](https://github.com/Waveorwaves/twmarket/tree/main/docs/dev) for the specification and development records.

## Development

```bash
pip install -e ".[dev]"
ruff check . && pytest
```

Tests run entirely against recorded fixtures — they never hit live TWSE/MOPS endpoints.

## License

MIT
