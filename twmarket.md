# twmarket — Tech Spec & Build Plan (v0.1)

> Open-source Python package: clean, English-documented, **point-in-time** API for Taiwan market data.
> Target user: quant researchers who can't read Chinese and can't navigate MOPS/TWSE sites.
> Ship = pip-installable from GitHub + README + revenue/prices/calendar working with point-in-time semantics.

---

## 1. Scope

**v0.1 IN:**
- Monthly revenue (MOPS 每月營收) — all TWSE-listed companies, bulk monthly files
- Daily prices/volume — TWSE official JSON API, **unadjusted raw exchange data**
- Trading calendar — derived from price history
- Point-in-time announce dates for revenue: estimated for backfill, observed going forward via snapshot job
- Restatement tracking (both original and revised rows preserved)

**v0.1 OUT (do not build):** TPEx/OTC anything, quarterly financials, adjusted prices,
shareholding, institutional flows (三大法人), margin data, news, English company-name
mapping beyond ticker, real-time quotes, async client, hosted/published dataset,
PyPI publishing, docs site, dashboard. Extras go to a v0.2 ideas list — the OUT list is law.

## 2. Architecture

```
twmarket/
├── pyproject.toml            # hatchling, Python 3.10+, deps: requests, pandas, pyarrow
├── src/twmarket/
│   ├── __init__.py           # public API: revenue(), prices(), calendar(), sync()
│   ├── _client.py            # HTTP layer: retry/backoff, rate limit, realistic UA
│   ├── revenue.py            # MOPS monthly revenue + point-in-time query logic
│   ├── sync.py               # snapshot job: fetch, diff, record observed announce dates
│   ├── prices.py             # TWSE daily OHLCV
│   ├── calendar.py           # trading days derived from price history
│   ├── _store.py             # local parquet store (~/.twmarket/), month-granular keys
│   └── _dates.py             # ROC↔ISO conversion, Asia/Taipei, announce-date estimation
└── tests/                    # pytest + recorded HTTP fixtures (never hit live sources in CI)
```

**Design rules:**
- Returns **pandas DataFrames** (what quant users expect at the boundary)
- All dates ISO; all sources use ROC/Minguo years (year 114 = 2025; convert = +1911).
  Centralize in `_dates.py`; this is the #1 parsing bug source — test it directly.
- Store is append-only observations: grain = `(ticker, period, observed_date)`. Queries
  derive "latest" or "as-of" views from observations — never overwrite.
- Cache-first: fetch once, store parquet, refresh on demand
- Rate-limit politely (MOPS blocks aggressive scrapers): ≥1s between requests,
  exponential backoff, realistic User-Agent

## 3. Data sources

| Domain | Endpoint | Format | Notes |
|---|---|---|---|
| Monthly revenue | `https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{ROC_year}_{month}_0.html` | HTML, **Big5** | One file = all listed companies for one month. Legacy host: MOPS redesign moved old site to `mopsov` in Feb 2025 — tutorials citing `mops.twse.com.tw/nas/...` are stale. ROC year ≤ 98: filename drops `_0`. Filter out `合計` (total) rows. |
| TWSE prices | `www.twse.com.tw/exchangeReport/STOCK_DAY` (JSON) | JSON | One stock × one month per request (~12 req/ticker/year) — design cache around month-granular fetches |
| Calendar | derived from TWSE price history (e.g., 0050 daily data) | — | Handles typhoon closures and make-up Saturdays automatically; cannot predict future days — document |

## 4. Point-in-time rules (the core value — get this right)

The bulk MOPS files preserve **no historical filing timestamps** (their 出表日期 is a
fetch-time report-generation date, not a filing date). Confirmed, not a maybe. Therefore:

- **Backfill:** `announce_date` = statutory deadline (10th of following month, rolled
  forward to next trading day), with `announce_date_estimated=True`. Most companies file
  days earlier, so estimates are conservative — safe against lookahead bias, but backtest
  signals lag slightly. Say this in the README.
- **Forward capture:** `tw.sync()` re-fetches current + prior month's files, diffs against
  the store, records first-seen date as true `announce_date` (`estimated=False`). Users
  who want real dates run it daily (cron); twmarket stays a library, not a service.
- **Restatements:** a changed figure between snapshots = new observation row with its own
  observed date and `is_restated=True`. **Never discard the original row** — that
  reintroduces the lookahead bias this package exists to prevent. Default query returns
  latest; `as_of` returns what was knowable then. Detection only works from the date
  snapshotting begins — document.
- **yoy/mom:** MOPS publishes these, but compute from stored revenue for internal
  consistency; note possible divergence around mergers/restatements.

## 5. Public API (v0.1)

```python
import twmarket as tw

tw.revenue("2330")                       # all history, one ticker (latest figures)
tw.revenue("2330", "2024-01", "2025-12") # period range
tw.revenue("2330", as_of="2025-06-05")   # point-in-time: only what was knowable then
tw.prices("2330", "2025-01-01", "2025-06-30")
tw.calendar("2025-01-01", "2025-12-31")  # trading days
tw.sync()                                # snapshot job: capture announce dates/restatements
```

Revenue columns: `ticker, period (YYYY-MM), revenue_twd, yoy_pct, mom_pct, announce_date,
announce_date_estimated, is_restated`. Prices: `date, open, high, low, close, volume, turnover`.

**Error semantics:** invalid ticker → `ValueError`; valid ticker with no data in range →
empty DataFrame with correct dtypes.

## 6. Build steps (each = one sitting, commit after each)

**Step 0 — Scaffold (½ day)**
- [ ] pyproject (hatchling), src layout, pytest, ruff, GitHub Actions (lint/test/build)
- [ ] Public GitHub repo under Waveorwaves, MIT license, README stub with the pitch
- [ ] First commit

**Step 1 — Source recon + fixtures (½ day)**
- [ ] Fetch one real t21sc03 file and one STOCK_DAY response (rate-limited, one-time)
- [ ] Commit them as test fixtures — real Big5 bytes, real ROC dates, real 合計 rows.
      Do NOT hand-write fake fixtures; parser bugs hide in real quirks.
- [ ] Document endpoints/params/encoding in `docs/sources.md`

**Step 2 — _client.py + _dates.py (½ day)**
- [ ] requests session: retry w/ backoff, ≥1s spacing, UA header
- [ ] ROC↔ISO conversion + announce-date estimation; dedicated tests (114/01 → 2025-01)

**Step 3 — revenue.py core (1–2 days)**
- [ ] Parse one bulk month file → DataFrame (Big5, 合計 filtering, thousand-NT$ units)
- [ ] Fixture tests before wiring live fetch

**Step 4 — Store + backfill (1 day)**
- [ ] Observation store in parquet; backfill 2015–present (~130 requests, cache-first)
- [ ] `tw.revenue(...)` reads store, fetches missing months
- [ ] Estimated announce dates applied per §4

**Step 5 — Point-in-time + sync (1–2 days)** ← the differentiator
- [ ] `as_of=` filter on announce_date over observations
- [ ] `tw.sync()`: fetch → diff → append observations (true announce dates, restatements)
- [ ] Tests: as_of before estimated announce returns nothing; sync twice with changed
      fixture yields original + restated row pair

**Step 6 — prices.py (1 day)**
- [ ] STOCK_DAY monthly loop → OHLCV DataFrame, same store pattern
- [ ] Fixture tests; spot-check 5 closes vs TWSE site manually

**Step 7 — calendar.py (½ day)**
- [ ] Trading days derived from price history; `is_trading_day()`, `next_trading_day()`
- [ ] Test: 2025 LNY (Jan 27–31) not trading days; ≥1 historical make-up Saturday is

**Step 8 — Polish & ship (1 day)**
- [ ] README: quickstart (≤3 code blocks), Taiwan monthly-revenue disclosure explainer,
      explicit estimated-vs-observed announce-date + restatement section
- [ ] Docstrings with examples on public API
- [ ] CI green; `pip install -e .` clean

## 7. Definition of done (v0.1)

- [ ] `pip install -e .` works, imports clean
- [ ] `tw.revenue("2330", "2024-01", "2025-12")` matches MOPS website (spot-check 3 months,
      verified by a human or separate session — not the agent that wrote the parser)
- [ ] `tw.prices("2330", "2025-01-01", "2025-06-30")` matches TWSE closes (spot-check 5 days)
- [ ] `as_of` correctness: period 2025-05 with `as_of="2025-06-05"` → nothing;
      `as_of="2025-06-10"` → returned (estimated policy)
- [ ] Sync/restatement test passes (original + revised rows, correct observed dates)
- [ ] Calendar: 2025 LNY closed; a make-up Saturday trades
- [ ] ROC-year conversion tested
- [ ] CI green; README quickstart runs top to bottom
- [ ] Public repo under Waveorwaves

## 8. Risks

| Risk | Mitigation |
|---|---|
| MOPS blocks scraping | bulk files (1 req/month of data), slow rate, cache-first |
| No historical announce_date | estimated + flagged; true dates via sync going forward — documented as the honest tradeoff |
| Legacy `mopsov` host disappears | endpoints isolated in `_client.py`; recorded fixtures keep tests green while migrating |
| Encoding hell (Big5) | handle in one place, real recorded fixtures |
| ROC date bugs | centralized `_dates.py` + dedicated tests |
| Scope creep | v0.1 OUT list is law; extras → v0.2 list |
