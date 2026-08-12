# Data sources

Verified against live endpoints on 2026-08-12. Recorded responses live in `tests/fixtures/`.

## Monthly revenue — MOPS bulk file (t21sc03)

- **URL:** `https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{month}_0.html`
  - `roc_year` = Gregorian year − 1911 (2025 → 114); `month` = 1–12, **no zero-padding**
  - ROC year ≤ 98: filename drops the trailing `_0`
  - Legacy host: MOPS redesign (Feb 2025) moved the old site to `mopsov.twse.com.tw`;
    tutorials citing `mops.twse.com.tw/nas/...` are stale.
- **Encoding:** **Big5** (decode with `errors` handling; a few chars may not map)
- **Format:** one HTML file = all TWSE-listed companies for one month, grouped by
  industry into multiple `<table>` blocks.
  - Data row: `<tr align=right>` with cells:
    `ticker, company_name, revenue_this_month, revenue_prior_month, revenue_same_month_last_year, mom_pct, yoy_pct, cum_revenue_this_year, cum_revenue_last_year, cum_yoy_pct, remarks`
  - Revenue units: **thousand NTD**
  - Beware mixed-case tags in the wild (`<Td nowrap>` observed) — parse case-insensitively.
  - **Filter out `合計` (total) rows** — one per industry group (35 in the 114/6 file).
- **`出表日期` (report date) is fetch-time**, not a filing date. Fixture fetched
  2026-08-12 shows `出表日期：115/08/10` on a June-2025 data file. This confirms the
  point-in-time design in the spec: bulk files preserve no historical announce dates.
- **Fixture:** `tests/fixtures/t21sc03_114_6_0.html` (June 2025, ~449 KB, raw Big5 bytes)

## Daily prices — TWSE STOCK_DAY

- **URL:** `https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={YYYYMMDD}&stockNo={ticker}`
  - Returns **one stock × one month**; `date` can be any day in the target month.
- **Response:** JSON with `stat` (`"OK"` on success), `fields`, `data`.
  - Fields (zh): `日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數, 註記`
    → date, share volume, turnover (NTD), open, high, low, close, change, transactions, remark
  - Dates are **ROC format** (`114/06/02` = 2025-06-02); numbers are comma-separated strings.
  - Invalid ticker / no data: `stat` is an error message instead of `"OK"`.
- **Fixture:** `tests/fixtures/stock_day_2330_202506.json` (2330, June 2025, 21 rows)

## Rate limiting

- ≥1 s between requests, exponential backoff on failure, realistic browser User-Agent.
- MOPS blocks aggressive scrapers; bulk files mean backfill 2015–present ≈ 130 requests total.
- Tests must **never** hit live endpoints — use the recorded fixtures.
