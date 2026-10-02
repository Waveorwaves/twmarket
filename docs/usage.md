# Usage notes

## First download and caching

Requests are spaced at least one second apart to be polite to the source. Downloading
revenue takes about 6 seconds per month of history: six months is about half a minute,
the full history from 2015 about 15 minutes. A progress line on stderr shows it is
working; set `TWMARKET_PROGRESS=0` to silence it.

Everything downloaded is stored as parquet in `~/.twmarket/` (set `TWMARKET_DATA_DIR` to
move it). After that, a full-history query for any ticker takes about a quarter of a
second, so looping over hundreds of tickers is practical.

Interrupting a download is safe: months already stored stay stored, and the next call
carries on from there.

## Running `sync()` every day

Any scheduler works. With cron, once a day late in the Taiwan evening (23:00 in Taipei
is 15:00 UTC), so that day's filings are stamped with that day:

```bash
0 15 * * * /full/path/to/python -c "import twmarket as tw; tw.sync()" >> ~/twmarket-sync.log 2>&1
```

Adjust the hour to your machine's timezone. `sync()` raises if the source cannot be
reached, so a failed run shows up in the log. A missed day cannot be recovered later.

## Errors

| Call | Situation | Result |
| --- | --- | --- |
| any | Ticker is not a string of 4 to 6 digits | `ValueError` |
| any | A date is not `YYYY-MM-DD` or a date object | `ValueError` naming the argument |
| `revenue()` | Ticker is not in the latest final month of the range | `ValueError` |
| `revenue()` | `start` is after `end`, or before `2013-01` | `ValueError` |
| `revenue()` | Ticker is known but nothing was public yet | Empty DataFrame |
| `prices()` | No data in the range | Empty DataFrame |
| any | The source cannot be reached, or its page layout changed | The error is raised, never hidden |

`revenue()` looks a ticker up in one month before downloading a range, so a typo fails
after a single request. That month is the latest one in your range that can no longer
gain late filers. Two consequences:

- For a **delisted** company, pass an `end` no later than its last month.
- **ETFs and funds** (`0050`, `00878`) report no revenue and raise the same error.

`prices()` cannot tell an unknown ticker from a month without trading, because the
exchange answers both the same way. It returns an empty DataFrame for either.

## Limits

- **TWSE-listed companies only.** No OTC market, quarterly financial statements,
  adjusted prices, institutional flows or real-time quotes.
- **Revenue starts at 2013-01.** MOPS moved to IFRS consolidated revenue that month;
  earlier files use a different layout and are not comparable.
- **Prices start at 2010-01-04**, the earliest the exchange serves. The calendar is
  historical and cannot predict future trading days.
- **`prices()` takes all-digit tickers only.** Codes with a letter, such as the
  leveraged ETF `00631L` or preferred shares, are rejected.
- **One process at a time.** The store has no locking, so do not run `sync()` and a
  query against the same store at the same moment.
- **Windows is untested.** It should work.

If a stored revenue file ever becomes unreadable, the error names the file. Delete it
and that month is downloaded again; observed dates recorded in it are lost.
