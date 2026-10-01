# twmarket — v0.1.1 Fix Plan

Written 2026-08-19. **Updated 2026-10-01** with status and decisions (see below).
Execution target: Claude Code, working in the `twmarket` repo.

Findings come from a review of the shipped v0.1.0 tree: 37 tests pass, `ruff check`
clean, 86% line coverage. The structure is sound. The defects below are correctness
and robustness issues, not architecture problems. **Do not restructure the package.**

Work P0 → P3. Each item lists the change, the test that proves it, and how to verify.
Every fix lands with a test that fails before it and passes after.

---

## Status — 2026-10-01

**All code work for v0.1.1 is done.** What remains is release hygiene (P3): changelog,
version bump, tags, and the PyPI publish.

| Item | Status |
| --- | --- |
| P0 — `sync()` false announce dates | ✅ Done, `e71a6f5` |
| P1 — silent failure in `sync_period` | ✅ Done, `eda3719` |
| P1 — unknown ticker costs ~140 fetches | ✅ Done 2026-10-01 |
| P2 — coverage gaps | ✅ Done: 98%, CI gate at 90% |
| P2 — `parse_bulk_file` fails open | ✅ Done: zero-row raise, row floor, 合計 check removed |
| P2 — spec conflicts with `twmarket.md` | ✅ All four resolved |
| Review 2026-09-29 — four further defects | ✅ Done, `d954ea6` (see "Independent review") |
| Found 2026-10-01 — late filers, re-downloads, pre-2013 | ✅ Done, `9babe53` (see "Found after the review") |
| Review 2026-10-01 — months frozen too early; README overclaim | ✅ Done 2026-10-01 (see "Second review") |
| Open question — do financials file late every month? | **Unknown.** Needs daily `sync()` across a 10th–20th |
| P3 — repository hygiene | **Open — next.** History decision made (leave as is) |

Current tree: 169 tests pass on Python 3.12 / pandas 3 and Python 3.10 / pandas 2.3 (the
CI matrix), `ruff check` clean, 98% coverage.

## Decisions

- **2026-09-28 — PyPI in v0.1.1, docs site deferred to v0.2.** `twmarket.md` §1 puts
  both PyPI publishing and a docs site on the v0.1 OUT list; this plan originally pulled
  both into v0.1.1. Resolved: PyPI ships in v0.1.1, **gated on P1 and P2 landing first**
  — PyPI releases are immutable, so the first public release must not carry the
  silent-failure bug. The docs site goes to the v0.2 parking lot. `twmarket.md` stays
  unchanged as the record of v0.1 scope; this is a deliberate amendment for v0.1.1.
- **2026-09-28 — `revenue()` raises on a ticker absent from the whole range.** Kept the
  current behaviour; `twmarket.md` §5 amended to match (spec-conflict item 1).
- **2026-09-28 — `yoy_pct` / `mom_pct` are MOPS's published values.** Kept the current
  behaviour; `twmarket.md` §4 amended to match (spec-conflict item 2).
- **2026-09-28 — commit history left as is.** The `Generated with Devin` lines stay in
  the Step 0–8 commit messages. They are plain text, not `Co-authored-by:` trailers, so
  GitHub does not list Devin as a contributor; removing them would need a force-push to
  published `main` for no functional gain (P3.1).
- **2026-10-01 — debug and ship, no new features.** v0.1.1 fixes every known defect,
  goes to PyPI with the README as its documentation, and development stops there. The
  only additions to the public surface are the two calendar helpers that Step 7 already
  promised (`is_trading_day`, `next_trading_day`), now reachable from the package.

---

## P0 — `sync()` records false announce dates — ✅ DONE (`e71a6f5`, 2026-08-27)

Fixed as specified. `observed_date` is always the snapshot date; `announce_date` follows
the three-case table:

| Row type | Condition | `announce_date` | `announce_date_estimated` |
| --- | --- | --- | --- |
| `is_new` | `today <= estimated deadline` | `today` | `False` |
| `is_new` | `today > estimated deadline` | estimated deadline | `True` |
| `is_changed` (restatement) | always | `today` | `False` |

The restatement flag is now an explicit column on `merged` rather than relying on index
alignment. Regression test `test_sync_after_deadline_falls_back_to_estimate` was
verified failing against the previous `sync.py` (announce date 2025-08-01) and passing
after the fix (2025-07-10).

The same commit fixed four defects this plan did not anticipate, found while
implementing P0:

- **Estimates landed on market holidays.** `estimate_announce_date` rolled past
  weekends only, so the "conservative" estimate could be *early*: January 2013 revenue
  was due Sun 2013-02-10, rolled to Mon 2013-02-11, but TWSE was shut for Lunar New Year
  until 2013-02-18. `revenue.announce_date_for()` now rolls to the next real trading day,
  falling back to the weekday roll only where no price history exists (future deadlines,
  pre-2010).
- **The calendar reported phantom holidays.** 0050 has no trades 2025-06-11..17 (1:4
  split suspension) while the market was open. `calendar()` is now the union over
  `REFERENCE_TICKERS = ("0050", "2330")`; June 2025 went from 16 trading days to the
  correct 21.
- **Partially-filed months were cached forever.** `ensure_period` no longer caches a
  period before its deadline, and tops up a stored period whose observations all predate
  the deadline (written by an early query or an early `sync()`) via `sync_period`.
- **`get_prices` raised on an all-empty range** (`pd.concat([])`) instead of returning
  the empty frame §5 requires.

Not done from P0's docs list: `docs/api.md` belonged to the docs site, now deferred —
`README.md` carries the three-case semantics instead. `CHANGELOG.md` moved to P3.2.

---

## P1 — Silent failure in the snapshot job — ✅ DONE (`eda3719`, 2026-09-28)

**The problem.** `sync_period` wrapped its fetch in `except Exception: return
pd.DataFrame()`, commented as "current month's file may not exist yet". Since `e71a6f5`
`revenue()` also ran through it, via `ensure_period`'s top-up of unsettled months. With
the network down, `revenue()` quietly served the stale partial month — confirmed by a
test that failed before the fix with `DID NOT RAISE ConnectionError`.

**The premise was wrong.** This plan said to "catch only the 404 for unpublished months
— likely 404, confirm before hardcoding". Checked live on 2026-09-28: MOPS answers an
unpublished month (current 115/9, future 115/12) with **HTTP 200** and a ~900-byte
`查無資料` ("no data found") page, which the parser already turned into zero rows. The
handler never saw unpublished months at all; it only ever caught real failures —
network, timeouts, 5xx after retries, blocks — and hid them.

**What landed:**

- The catch-all is gone. Network and HTTP errors propagate from `sync()` and from
  `revenue()`. No 404 special case: from MOPS, a 404 would mean the URL scheme changed.
- "Not published yet" is recognised explicitly by the `查無資料` marker.
  `parse_bulk_file` returns an empty frame for that page only; `sync()` skips the month
  with an INFO log, and `ensure_period` never caches it.
- Any other page that parses to zero rows raises `ValueError` (layout change). That is
  the first half of the P2 parser item, done here because it is the same few lines.
- Real `查無資料` page recorded as `tests/fixtures/t21sc03_115_9_0_unpublished.html`.
- 10 new tests: 7 failed against the pre-fix code, 3 guard behaviour that was already
  correct. Live check: `tw.sync()` on 2026-09-28 skipped 2026-09, appended 993 rows for
  2026-08 (first seen after the deadline, so dated at the estimated 2026-09-10), and a
  failing host raised `ConnectionError` after four retries.

**Deliberately not done:** the plan's "WARNING when a sync appends zero rows for a
period that already has stored data". The daily cron re-checks the prior month every
day and most days nothing changes, so that warning would fire almost daily and train
the user to ignore warnings. Propagating real errors is the protection that matters.

---

## P1 — `revenue()` fetches ~140 months before it can reject a bad ticker — ✅ DONE (2026-10-01)

`get_revenue` defaults to `BACKFILL_START` (2015-01) through last completed month and
loops `ensure_period` over every month. At the client's ≥1s spacing that is roughly
three minutes of silence on a cold cache, with no output. Worse, a well-formed but
nonexistent ticker (`"9999"`) triggers the full ~140 fetches and *then* raises
`unknown ticker`.

**Fix:**

1. Before the main loop, `ensure_period` the **most recent settled** period in the
   range and check whether the ticker appears. If it does not, raise `ValueError`
   immediately with a message noting the ticker may be delisted or may have listed
   later, and suggesting an explicit `start`. Only run the full loop after that check
   passes.

   *Amended 2026-09-28:* "settled" matters. Before the 10th, the default `end` (last
   completed month) is still being filed, so a real ticker that hasn't filed yet would
   look absent and raise a false "unknown ticker". Probe the latest period whose
   deadline has passed.
2. Log at INFO per period fetched (not cached), so a long backfill is visible with
   logging enabled. (`ensure_period` now does this.)
3. Document the cold-cache cost in the `revenue()` docstring: roughly one request per
   month of history, ≥1s apart, plus one cached price-month per period for the
   announce-date calendar.

Keep the `BACKFILL_START` default as-is. Do not add a progress bar dependency.

**Tests:** an unknown ticker raises after a single period fetch (assert the client was
called once); a known ticker still returns the full range; a ticker absent only from an
unsettled month does not raise.

**What landed (2026-10-01).** `get_revenue` looks the ticker up in the latest settled
month of the range and raises there. Months that cannot answer the question are skipped
rather than trusted: an unpublished month, and a month still being filed, are never
evidence of absence. Live check against MOPS: cold-cache `tw.revenue("9999")` made one
request and raised in 3.5s.

Known cost, documented in the README and the error message: a company absent from the
latest settled month raises even if it appears earlier in the range, so a **delisted**
company must be queried with an `end` inside its history. A range holding only
unpublished months returns an empty frame instead of raising.

---

## P2 — Coverage gaps sit exactly where risk is highest — ✅ DONE (2026-10-01)

Measured on v0.1.0: `_client.py` 43%, `sync.py` 77%, overall 86%.

**Now:** 98% overall; `_client.py`, `revenue.py` and `sync.py` at 100%. The reviewer's
`tests/test_client.py` covers retry, backoff and throttle against a local HTTP server.
`pytest-cov` is in the `dev` extra and CI runs `pytest --cov=twmarket
--cov-fail-under=90`. The workflow's actions were also moved to `checkout@v7` and
`setup-python@v7`; GitHub had flagged the old ones as deprecated.

`_client.py` holds the retry, backoff, and throttle logic — the layer most likely to
misbehave against a rate-limiting government site — and is almost entirely untested.
`sync.py` generates the point-in-time moat.

**Fix:**

- `_client.py`: test that `_throttle()` enforces ≥1s spacing (monkeypatch the clock, do
  not `sleep`); that a 5xx retries with backoff and eventually raises; that a 404 raises
  `HTTPError` without retrying; that the User-Agent header is set.
- `sync.py`: the P1 tests above should carry this past 90%.
- Add `pytest-cov` to the `dev` extra and `--cov=twmarket --cov-fail-under=90` to the CI
  test step.

---

## P2 — `parse_bulk_file` fails open on MOPS layout changes — ✅ DONE (2026-10-01)

Two brittle points, both silent:

- Rows are matched with `<tr align=right>` and required to have exactly 11 `<td>`
  cells. A MOPS layout change yields **zero rows** rather than an error.
- `if "合計" in row: continue` skips any row containing that substring anywhere,
  including a hypothetical company name.

`ensure_period` then stores the empty result, and the period reads as cached forever.
The gap is permanent and invisible.

**Fix:**

- ✅ *Done 2026-09-28 with P1.* Raise `ValueError` from `parse_bulk_file` when a
  document yields zero data rows and is not MOPS's `查無資料` page — name MOPS layout
  change as the likely cause.
- In `ensure_period`, sanity-check the row count against a floor (TWSE has ~1,000
  listed companies; the 114/6 fixture parses 990). Raise rather than store a partial
  month.

  *Amended 2026-09-28:* apply the floor **only when caching a settled period**. Before
  the deadline a low count is normal — most companies haven't filed — and those
  fetches are no longer cached anyway, so raising there would only break legitimate
  early-month queries.
- Restrict the 合計 filter to the ticker cell being non-numeric, which the
  `re.fullmatch(r"\d{4,6}", cells[0])` guard already handles — the substring check is
  redundant and strictly more dangerous. Remove it.

  *Verified 2026-08-26:* the 114/6 fixture parses to the same 990 rows with and without
  the substring check (it contains 34 合計 rows, all already rejected by the ticker
  guard). Safe to remove.

**Test:** ✅ a truncated fixture raises rather than silently storing zero rows; a
pre-deadline fetch with few rows is served without raising.

**What landed (2026-10-01).** `MIN_SETTLED_ROWS = 500`, enforced by
`check_settled_row_count` in both places a settled month can be written:
`ensure_period`, and `sync_period` (a cold sync after the deadline would otherwise freeze
a truncated month). The `"合計" in row` substring check is gone; the ticker-cell guard
alone excludes totals, and a company named 合計實業 now parses.

---

## P2 — Spec conflicts with `twmarket.md` (added 2026-09-28)

From reviewing the v0.1.0 tree against the spec. Each is resolved by changing the code
**or** amending the spec, never neither. Items 1–2 were decided 2026-09-28 by amending
the spec; items 3–4 are code fixes.

1. **Unknown-but-valid ticker: raise or empty frame? — ✅ decided: raise.** §5 said a
   valid ticker with no data in range returns an empty DataFrame. The code raises
   `ValueError("unknown ticker")` whenever the ticker appears in no month of the range
   — including a real ticker that listed after `end`. Without a listings registry (out
   of scope) the code cannot tell "never existed" from "not listed yet".
   *Resolved 2026-09-28:* keep raising, so a typo that lands on a nonexistent code
   (`23300` for `2330`) fails loudly instead of looking like an empty history. It cannot
   catch a typo that lands on a real ticker (`2303` is UMC). §5 amended, scoped per
   function: `prices()` still returns empty, since TWSE answers an unknown ticker exactly
   like an empty month. README "Error semantics" updated to match. Remaining code work:
   the reworded message, which is P1's unknown-ticker fix.
2. **`yoy_pct` / `mom_pct`: published or computed? — ✅ decided: published.** §4 said compute
   from stored revenue for internal consistency. The code stores MOPS's published
   values, and the README documents that. *Resolved 2026-09-28:* §4 amended to
   "published". Computing yoy needs the same month a year earlier in the store, which a
   2015-01 backfill start doesn't have for 2015, and restatement-consistent
   recomputation is v0.2 material. No code change.
3. **Empty `revenue()` frames have all-`object` dtypes — ✅ fixed 2026-10-01** (an empty
   result now goes through the same steps as a full one, so the dtypes match on both
   pandas 2 and 3). §5 requires correct dtypes.
   No decision needed: build the empty frame from `_store.REVENUE_COLUMNS`, as
   `prices._empty()` does. Test: dtypes of an `as_of`-before-announce result.
4. **Calendar helpers are unreachable as attributes — ✅ fixed 2026-10-01**
   (`tw.is_trading_day`, `tw.next_trading_day`). `tw.calendar` is the function,
   so `tw.calendar.is_trading_day` raises `AttributeError`; only
   `from twmarket.calendar import is_trading_day` works. Build Step 7 promised both
   helpers. Fix by exporting `is_trading_day` and `next_trading_day` at package level —
   an addition to the public API, not a rename.

---

## Independent review — 2026-09-29 (all fixed 2026-10-01)

A separate session reviewed `e71a6f5` plus the P1 fix and wrote `tests/test_client.py`,
`tests/test_contract.py` and `tests/test_open_issues.py`. It confirmed the point-in-time
core by sweeps and mutation testing, and did the spec §7 spot-checks independently of the
parser's author: revenue for 2330 (2024-03, 2025-01, 2025-12) matches the raw MOPS pages,
and five closes match TWSE's `MI_INDEX`, a different endpoint from the one the package
uses. It also found four defects that were not in this plan:

1. **`sync()` used the machine's date, not Taiwan's.** A cron in a timezone west of
   Taiwan stamps a filing with the previous day — one day of lookahead. Fixed with
   `_dates.taipei_today()` (a fixed UTC+8 offset; Taiwan has no DST), used at every
   former `date.today()`.
2. **Future price months were cached as empty**, which would leave that month with no
   trading calendar once it arrived. `ensure_month` now caches only months that are over.
3. **An inverted `revenue()` range** was reported as "unknown ticker". It now raises
   "start … is after end …" without fetching.
4. **`revenue(2330)` (an int)** passed validation, never matched, and blamed the ticker
   after a full backfill. `revenue()` and `prices()` now accept strings only.

Each had a strict-xfail test; the markers were deleted with the fixes. Remaining manual
items from the review, all for the repo owner: configure PyPI trusted publishing, set the
GitHub repo description and topics, and read the README once as a first-time user.

---

## Found after the review — 2026-10-01 (all fixed the same day)

Three defects that neither the builder nor the reviewer had tested for. Each was
reproduced before it was fixed.

1. **Late filers were dated before they filed — lookahead.** P0's rule sends every first
   sighting after the deadline to the deadline estimate. That is right for a cold start,
   and wrong when `sync()` was already watching: a check on 07-14 without company X,
   then X appearing on 07-15, was recorded as announced 07-10. The store could not tell
   the two cases apart, because a sync that finds nothing new left no trace.

   *Fix:* `revenue/checked.json` records the date of every successful comparison with
   MOPS, including the days nothing changed. P0's table gains a fourth row:

   | Row type | Condition | `announce_date` | `announce_date_estimated` |
   | --- | --- | --- | --- |
   | `is_new` | `today > deadline`, and an earlier check on or after the deadline exists | `today` | `False` |

   The estimate still applies when no such earlier check exists (a cold start, or a cron
   that was down across the deadline).
2. **A fully synced month could be re-downloaded on every query, forever.** "Settled"
   meant "some stored row is dated after the deadline". If everyone filed early and later
   syncs found nothing, no such row ever existed. "Settled" now means "compared with MOPS
   after the deadline", from the same check dates.
3. **Revenue before 2013-02 did not work.** 2013-01 crashed on `不適用` ("not
   applicable") cells; 2012 and earlier use a 10-cell layout and predate IFRS
   consolidated revenue. `不適用` now parses as missing, and `revenue()` rejects a
   `start` before `2013-01` without fetching. The default range (2015-01 on) was never
   affected.

Known limits, documented in the README and left as designed: restatements are caught
only for the current and previous month; `prices()` takes all-digit tickers only; the
store has no locking.

---

## Second review — 2026-10-01 (fixed the same day)

The reviewer property-tested `9babe53` (`tests/test_checked_dates.py`: 40 random
schedules of syncs and backfills against a known truth) and found no case where a late
check proved absence and the row was still dated early. It did find:

1. **The README promised estimates "can never introduce lookahead bias".** False for any
   company that files after the deadline. Reworded: conservative for on-time filers,
   early for late ones, with the observation below.
2. **Late filers may be a whole group, not stragglers.** The owner's real store had
   `2026-07` backfilled on 2026-08-12, two days after its deadline, with 980 rows; MOPS
   now has 993. The 14 missing: ten financial holding companies (富邦金 2881, 國泰金 2882,
   中信金 2891, 元大金 2885 …), three insurers, one new listing — 13 of the 31 companies in
   金融保險業. **One month only; not known to be systematic.** See "Open question".
3. **A month was frozen one check after its deadline**, so those 14 were missing for good
   and `revenue("2881", "2026-07", "2026-07")` raised "unknown ticker" for 富邦金.

   *Fix:* a stored month is final only once it has been compared with MOPS on or after
   `recheck_window_end(period)` — the 1st of the second month after it, when `sync()`
   stops covering it. Until then each query tops it up through the differ (one request).
   The unknown-ticker lookup uses the same rule: a month that can still gain filers is
   never evidence that a ticker does not exist. Verified on a copy of the real store:
   2881 is returned after one request, then served from disk.
4. **Smaller:** `as_of=D` includes figures filed after D's 13:30 close — README now says
   to act from the next trading day. An unreadable `checked.json` is now ignored with a
   warning instead of failing every call.

**Still true, by design, and documented:** if no check runs between the deadline and a
late filing (a cron down across the deadline), the late filer is dated at the deadline,
flagged `estimated=True`. The flag is honest; the date is early.

### Open question — is late filing by financials systematic?

If financial holding companies file after the 10th every month, every *backfilled* month
dates them a few days early, and the fix would be a later estimate for that industry
(v0.2 material: it needs the industry column). One month is not evidence of that. To
find out, run `tw.sync()` daily from the 5th to the 20th of any month and look at which
tickers get `announce_date` after the deadline.

---

## P3 — Repository hygiene

Independent of the code. Can be done in any order, except that **5 waits for P1 and
P2**.

1. ~~**Rewrite history.**~~ **✅ Decided 2026-09-28: leave as is.** Authorship is
   already fixed — all 11 commits are `Waveorwaves <jason890427@ymail.com>`. The
   `Generated with [Devin](https://devin.ai)` line remains in the nine Step 0–8 commit
   messages; it is plain text, not a `Co-authored-by:` trailer, so GitHub shows no
   co-author. Not worth a force-push to published `main`.
2. **Tag and release.** v0.1.0 was never tagged: tag Step 8 (`5aed57f`) as `v0.1.0`, then tag `v0.1.1` at release. Cut GitHub
   Releases. Add `CHANGELOG.md` (moved here from P0), with `e71a6f5`'s fixes under
   `[0.1.1] → Fixed`.
3. **Repo metadata.** Set the GitHub description and topics (`taiwan`, `twse`, `mops`,
   `quant`, `point-in-time`, `market-data`). The repo currently has neither, so it
   surfaces below competitors in search.
4. ~~**Docs site.**~~ **Deferred to v0.2** (decision 2026-09-28). The
   `git mv twmarket.md docs/spec.md` move goes with it; the README links `twmarket.md`
   by its current path.
5. **PyPI — in v0.1.1, gated on P1 and P2.** Add a `pypa/gh-action-pypi-publish` job
   triggered on tag push, using trusted publishing (no stored API token). Bump the
   version in **both** `pyproject.toml` and `src/twmarket/__init__.py`. Then the README
   install line becomes `pip install twmarket`.
   *Checked 2026-09-28:* the name `twmarket` is unclaimed on PyPI. It is claimed by the
   first upload, not before.
6. **README badges.** CI status, supported Python versions, licence; PyPI version once
   published.
7. **Reposition the README opening.** It currently leads with English documentation.
   TW Market Data (twmarketdata.com) is a funded commercial API with SDKs, an MCP
   server, `llms.txt`, and real SEO — they will own "Taiwan stock data in English."
   Lead with the defensible claim instead: honest announce timing. Their monthly-revenue
   schema is `symbol / revenue_month / revenue / revenue_yoy / revenue_mom` — no
   announce date, no `as_of`, no restatement history — and their own pricing page
   disclaims a backtest-grade baseline and lists delisted coverage as pending.
8. **Comparison table.** Add to `docs/` a single-axis comparison — twmarket vs FinMind
   vs TW Market Data — on one question: does it expose an announce date you can filter
   on? Naming competitors honestly and comparing on one stated axis reads as expertise.
   Do not claim to beat them on breadth; they win that decisively. (A plain Markdown
   file; no docs site needed.)
9. **Track this plan and the lockfile** (added 2026-09-28). Commit `Fixplan.md`. Decide
   on `uv.lock` (untracked since 2026-09-22): commit it if uv is now the workflow. CI
   installs with pip either way.

---

## Out of scope

Do not do these as part of v0.1.1, regardless of how small they look:

- TPEx/OTC, quarterly financials, adjusted prices, institutional flows, derivatives
- Async client, MCP server, `llms.txt`
- Docs site (mkdocs / GitHub Pages) — v0.2, per the 2026-09-28 decision
- Any restructuring of the package layout, or renaming public functions
- Rewriting working modules "while we're in there"

The v0.2 parking lot exists. Use it.

## Definition of done for v0.1.1

- [x] P0 regression test fails on pre-fix `main`, passes after the fix (`e71a6f5`)
- [x] `sync()` never reports `announce_date_estimated=False` for a first sighting after
      the statutory deadline
- [x] `README.md` describes the corrected three-case PIT semantics
- [x] Network and HTTP errors propagate from `sync()` and `revenue()` instead of
      returning empty; only MOPS's `查無資料` page reads as "not published" (2026-09-28)
- [x] Unknown ticker raises after one period fetch, not ~140 (2026-10-01)
- [x] `parse_bulk_file` raises on a zero-row parse that is not the `查無資料` page
      (2026-09-28)
- [x] Row-count floor applied when caching a settled period (2026-10-01)
- [x] Coverage ≥90%, CI enforces it (98% on 2026-10-01)
- [x] Spec conflicts 1–2 decided and `twmarket.md` amended to match (2026-09-28)
- [x] Spec conflicts 3–4 fixed in code (empty-frame dtypes; calendar helpers exported)
- [x] The four defects from the 2026-09-29 review fixed (2026-10-01)
- [x] Late filers dated when they appear; settled months not re-downloaded; revenue
      served from 2013-01 with earlier ranges rejected (2026-10-01)
- [x] Months re-checked until their window closes; README no longer claims estimates
      are never early (2026-10-01)
- [x] History decision made: leave as is (2026-09-28)
- [ ] `v0.1.0` and `v0.1.1` tagged
- [ ] `v0.1.1` published to PyPI by trusted publishing from the tag; README install line
      updated
