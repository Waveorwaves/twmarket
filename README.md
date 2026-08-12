# twmarket

**Point-in-time Taiwan market data for quant research — in English.**

Taiwan is one of the few markets where every listed company must disclose **monthly revenue**
(by the 10th of the following month). That's a high-frequency fundamental signal you can't get
in most markets — but the data lives on MOPS/TWSE sites that are Chinese-only and hard to
navigate programmatically.

`twmarket` gives you:

- **Monthly revenue** for all TWSE-listed companies, with **point-in-time semantics**
  (announce dates + restatement tracking, so your backtests don't cheat)
- **Daily prices** (unadjusted raw exchange data) from the official TWSE API
- **Trading calendar** derived from actual price history (typhoon closures and
  make-up Saturdays handled automatically)

## Install

```bash
pip install git+https://github.com/Waveorwaves/twmarket.git
```

## Quickstart

```python
import twmarket as tw

tw.revenue("2330")                        # all revenue history for TSMC (latest figures)
tw.revenue("2330", as_of="2025-06-05")    # point-in-time: only what was knowable then
tw.prices("2330", "2025-01-01", "2025-06-30")
tw.calendar("2025-01-01", "2025-12-31")   # trading days
tw.sync()                                 # daily snapshot: capture real announce dates
```

> **Status: pre-alpha.** API is stubbed; implementation in progress. See
> [twmarket.md](twmarket.md) for the spec and build plan.

## Point-in-time honesty

MOPS bulk files preserve no historical filing timestamps, so:

- **Backfilled data** gets `announce_date` = statutory deadline (10th of following month,
  rolled to next trading day), flagged `announce_date_estimated=True`. Conservative —
  safe against lookahead bias, but signals lag slightly.
- **Going forward**, run `tw.sync()` daily (cron) to record true first-seen announce dates
  and restatements. Originals are never discarded.

## License

MIT
