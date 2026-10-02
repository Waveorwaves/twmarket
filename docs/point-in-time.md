# How announce dates are decided

A backtest may only use a figure from the day it became public. This page explains how
`twmarket` decides that day for monthly revenue, and where the answer is uncertain.

## The problem

Every TWSE-listed company files its revenue for a month by the **10th of the following
month**. Most file a few days early, some on the deadline, a few after it. Figures are
occasionally revised later.

The official bulk files do not record when each company filed. Their "report date" is
the day the file was generated for you. So a real filing date exists only if someone
was watching when the figure appeared.

## Two kinds of date

Every row carries `announce_date` and `announce_date_estimated`.

| | `announce_date_estimated=True` | `announce_date_estimated=False` |
| --- | --- | --- |
| Meaning | The filing deadline | The day `sync()` first saw the figure |
| Applies to | All history, and anything first seen after its deadline | Figures that appeared while you were running `sync()` |
| Accuracy | Up to about nine days late for an early filer; **early** for a late filer | As precise as your checks are frequent |

Until you run `sync()`, every row is an estimate.

## Estimated dates

The estimate is the 10th of the following month, moved forward to the next **trading
day**. The real trading calendar is used, not just weekends: January 2013 revenue was
due on Sunday 10 February, but the market was closed for Lunar New Year until 18
February, so that is the estimate.

For a company that filed on time, the estimate can only be late, never early. **For a
company that filed after the deadline, the estimate is early**, and a backtest using it
would see the figure before it existed. This does happen: for July 2026, 13 of the 31
companies in the financial sector were still missing from MOPS two days after the
deadline. That is one observed month, not a measured pattern. If it matters to you,
treat estimated dates as "the deadline, possibly a few days more", or lag them.

## Observed dates

`tw.sync()` downloads the files for the current and previous month and compares them
with what is stored.

- **A figure that appears on or before its deadline** is dated the day it appeared.
- **A figure first seen after its deadline, with no earlier check since the deadline**
  (a first run, or a scheduler that was down) was filed at a time nobody recorded. It
  gets the deadline estimate, flagged as estimated.
- **A figure that was absent on a check after the deadline and is present later** was
  filed late. It is dated the day it appeared. `sync()` records every check, including
  days nothing changed, which is what makes this possible.
- **A changed figure** is a restatement: a new row with `is_restated=True`, dated the
  day the change was seen. The original row is never removed.

One gap remains. If no check ran between the deadline and a late filing, nothing shows
the company was absent, and it gets the deadline estimate.

## Asking what was known

```python
tw.revenue("2330", "2025-01", "2025-06", as_of="2025-06-05")
```

`as_of` returns the figures whose `announce_date` is on or before that day, using the
version of each figure that was current then.

**`as_of` means "known by the end of that day".** Companies can file after the 13:30
market close, so a figure dated D may not have been tradable on D. Act on it from the
next trading day: `tw.next_trading_day(D)`.

## Other rules

- **Every date is a Taiwan date**, whatever timezone your machine is in.
- **A month is not final until the end of the following month.** Until then each query
  compares it with MOPS again, because late filers keep arriving.
- **Restatements are caught only for the current and previous month**, the two files
  `sync()` re-checks, and only from the day you start running it.
- **`yoy_pct` and `mom_pct` are the values MOPS publishes.** They can differ from what
  you compute from stored revenue, because MOPS uses its latest prior-period figures.
