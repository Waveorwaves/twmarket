# Changelog

All notable changes to twmarket. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-10-02

The first release on PyPI. It adds no data sets; it corrects v0.1.0, mostly in how
announce dates are decided. If you used v0.1.0, delete `~/.twmarket/` once so history is
rebuilt under the corrected rules.

### Fixed — announce dates

- **Estimates no longer land on market holidays.** The filing deadline is rolled to the
  next real trading day, not just past weekends. January 2013 revenue was due Sunday
  2013-02-10; the old rule said Monday 02-11, but the market was shut for Lunar New Year
  until 02-18.
- **`sync()` no longer invents announce dates.** A figure first seen after its deadline
  was dated "today" and marked as observed. It now falls back to the deadline estimate
  and is marked as estimated.
- **Late filers are dated when they appear.** `sync()` records each check, including days
  nothing changed, so a company absent on a check after the deadline and present later
  is dated the day it appeared instead of the deadline it missed.
- **Every date is a Taiwan date.** `sync()` used the machine's local date; west of Taiwan
  that stamped filings a day early.
- **The trading calendar no longer reports phantom holidays.** It is now the union of
  two reference instruments. 0050 was suspended 2025-06-11 to 06-17 around its split
  while the market stayed open.

### Fixed — completeness

- **A month is not frozen while companies are still filing.** It is not cached before its
  deadline, and it keeps being compared with MOPS until the end of the following month.
  For July 2026, 13 of the 31 financial-sector companies appeared after the deadline.
- **`sync()` and `revenue()` no longer hide failures.** A blanket `except` turned network
  errors, server errors and unparseable pages into "nothing new today".
- **A changed or truncated MOPS page is an error, not an empty month.** Zero rows raise
  unless the page is MOPS's own "no data" page; a month past its deadline with fewer
  than 500 rows is rejected.
- **Future and unfinished price months are not cached as empty.**
- **`prices()` returns an empty frame for a range with no data** instead of raising.

### Fixed — usability

- **A mistyped ticker fails after one request**, not after the whole backfill.
- **Tickers must be strings.** `revenue(2330)` used to fetch everything and then report
  an unknown ticker.
- **A start after the end** is reported as such, and **a start before 2013-01** is
  rejected: MOPS moved to IFRS consolidated revenue that month and earlier files are not
  comparable.
- **Looping over tickers no longer re-downloads the month that is still being filed.**
  It is compared with MOPS at most once every ten minutes per process; twelve tickers of
  full history went from one download each to one in total.
- **Empty `revenue()` results keep the right column types.**
- **Dates can be `date`, `datetime` or pandas `Timestamp` objects**, not only strings,
  for `as_of`, `prices()`, `calendar()` and the two calendar helpers. A wrong date now
  names the argument and shows the expected form.
- **An interrupted run cannot corrupt the store.** Files are written beside the target
  and renamed into place. An unreadable price month is downloaded again; an unreadable
  revenue month raises an error naming the file.
- **A company whose name contains 合計 is no longer dropped** by the parser.

### Added

- **A progress line during long downloads**, on stderr. A cold cache used to sit silent
  for minutes. Set `TWMARKET_PROGRESS=0` to turn it off.
- `tw.is_trading_day()` and `tw.next_trading_day()` are reachable from the package. They
  existed in v0.1.0 but could only be imported from `twmarket.calendar`.

### Changed

- `revenue()` raises `ValueError` for a ticker that is not in the latest final month of
  the requested range. A **delisted** company therefore needs an `end` no later than its
  last month.
- The README no longer says an estimated announce date can never be early. It is
  conservative for companies that file on time and early for those that file late.

## [0.1.0] — 2026-08-12

Initial version, installable from GitHub only: monthly revenue with estimated announce
dates and `as_of` queries, daily prices, a trading calendar, and `sync()`.

[0.1.1]: https://github.com/Waveorwaves/twmarket/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Waveorwaves/twmarket/releases/tag/v0.1.0
