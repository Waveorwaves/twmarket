# twmarket

[![CI](https://github.com/Waveorwaves/twmarket/actions/workflows/ci.yml/badge.svg)](https://github.com/Waveorwaves/twmarket/actions/workflows/ci.yml)
[![Python 3.10–3.14](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg)](https://github.com/Waveorwaves/twmarket/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Waveorwaves/twmarket/blob/main/LICENSE)

Point-in-time Taiwan stock market data for Python: monthly revenue with the date each
figure became public, daily prices, and the trading calendar. Data comes straight from
the official sources (MOPS and TWSE) and is cached on your machine.

```python
import twmarket as tw

tw.revenue("2330", "2025-04", "2025-06")
```

```text
  ticker   period   revenue_twd  yoy_pct  mom_pct announce_date  announce_date_estimated  is_restated
0   2330  2025-04  349566940000    48.10    22.24    2025-05-12                     True        False
1   2330  2025-05  320515951000    39.58    -8.31    2025-06-10                     True        False
2   2330  2025-06  263708978000    26.86   -17.72    2025-07-10                     True        False
```

## Why

Every company listed in Taiwan reports its revenue each month, by the 10th of the
following month. That makes it one of the fastest fundamental signals in any market. A
backtest has to know *when* each figure became public, and the official files do not
record that. `twmarket` puts an announce date on every figure, says whether that date
was observed or estimated, and lets you ask what was known on any given day.

## Install

```bash
pip install twmarket
```

Python 3.10 or newer. Tested on Linux and macOS.

## Usage

| Function | Returns |
| --- | --- |
| `tw.revenue(ticker, start, end, as_of=None)` | Monthly revenue from 2013-01, one row per month, with its announce date |
| `tw.prices(ticker, start, end)` | Daily open, high, low, close, volume and turnover (unadjusted), from 2010 |
| `tw.calendar(start, end)` | The days the market actually traded |
| `tw.is_trading_day(date)` | Whether the market traded on a date |
| `tw.next_trading_day(date)` | The first trading day after a date |
| `tw.sync()` | Records real announce dates and restatements; run it once a day |

```python
# Only what was public on 5 June 2025: May's figure (announced 10 June) is left out
tw.revenue("2330", "2025-01", "2025-06", as_of="2025-06-05")

tw.prices("2330", "2025-01-01", "2025-06-30")
tw.calendar("2025-01-01", "2025-06-30")
tw.is_trading_day("2025-01-28")      # False: Lunar New Year
tw.next_trading_day("2025-01-22")    # datetime.date(2025, 2, 3)
```

Tickers are strings (`"0050"`, not `50`). Dates can be strings, `date`, `datetime` or
pandas `Timestamp` objects.

## How announce dates work

- **History is estimated.** MOPS keeps no record of when each company filed, so past
  figures get the filing deadline, moved to the next trading day, and are flagged
  `announce_date_estimated=True`.
- **Run `tw.sync()` daily for real dates.** From then on it records the day each figure
  actually appears, catches companies that file late, and keeps every restatement as a
  separate row without discarding the original.
- **`as_of` never shows the future.** It returns only figures whose announce date is on
  or before the day you ask about.

An estimate is safe for a company that filed on time, and early for one that filed
late. [How announce dates are decided](https://github.com/Waveorwaves/twmarket/blob/main/docs/point-in-time.md) explains
the rules and their limits; read it before trusting a backtest.

## Good to know

- **The first download is slow, then it is fast.** Requests are rate-limited to be polite
  to the source: about 6 seconds per month of revenue history, with a progress line.
  After that a full-history query takes about a quarter of a second.
- **Coverage.** Companies listed on TWSE. Revenue from 2013-01, prices from 2010-01. No
  OTC market, financial statements, adjusted prices or real-time quotes.
- **Storage.** Parquet files in `~/.twmarket/`; set `TWMARKET_DATA_DIR` to move them.

## Documentation

- [How announce dates are decided](https://github.com/Waveorwaves/twmarket/blob/main/docs/point-in-time.md)
- [Usage notes](https://github.com/Waveorwaves/twmarket/blob/main/docs/usage.md): errors, limits, scheduling `sync()`
- [Data sources](https://github.com/Waveorwaves/twmarket/blob/main/docs/sources.md): the MOPS and TWSE endpoints and their quirks
- [Changelog](https://github.com/Waveorwaves/twmarket/blob/main/CHANGELOG.md)

## Development

```bash
pip install -e ".[dev]"
ruff check . && pytest
```

The tests run against recorded responses and never touch the network.

## License

MIT
