# twmarket — v0.1.1 Fix Plan

Written 2026-08-19. **Updated 2026-09-28** with status and decisions (see below).
Execution target: Claude Code, working in the `twmarket` repo.

Findings come from a review of the shipped v0.1.0 tree: 37 tests pass, `ruff check`
clean, 86% line coverage. The structure is sound. The defects below are correctness
and robustness issues, not architecture problems. **Do not restructure the package.**

Work P0 → P3. Each item lists the change, the test that proves it, and how to verify.
Every fix lands with a test that fails before it and passes after.

---

## Status — 2026-09-28

| Item | Status |
| --- | --- |
| P0 — `sync()` false announce dates | ✅ Done, `e71a6f5` |
| P1 — silent failure in `sync_period` | ✅ Done 2026-09-28 (not yet committed) |
| P1 — unknown ticker costs ~140 fetches | **Open — do next** |
| P2 — coverage gaps | Open (figures below are stale; re-measure first) |
| P2 — `parse_bulk_file` fails open | Half done: zero-row parses raise. Row floor and 合計 cleanup open |
| P2 — spec conflicts with `twmarket.md` | 1–2 decided, spec amended; 3–4 open (code fixes) |
| P3 — repository hygiene | Partial; history decision made (leave as is) |

Current tree: 58 tests pass, `ruff check` clean.

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

## P1 — Silent failure in the snapshot job — ✅ DONE (2026-09-28, uncommitted)

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

## P1 — `revenue()` fetches ~140 months before it can reject a bad ticker

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

---

## P2 — Coverage gaps sit exactly where risk is highest

Measured on v0.1.0: `_client.py` 43%, `sync.py` 77%, overall 86%. **Stale** — re-measure
on the current tree before starting.

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

## P2 — `parse_bulk_file` fails open on MOPS layout changes

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

**Test:** ✅ a truncated fixture raises rather than silently storing zero rows (done).
Still to add with the row floor: a pre-deadline fetch with few rows is served without
raising.

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
3. **Empty `revenue()` frames have all-`object` dtypes.** §5 requires correct dtypes.
   No decision needed: build the empty frame from `_store.REVENUE_COLUMNS`, as
   `prices._empty()` does. Test: dtypes of an `as_of`-before-announce result.
4. **Calendar helpers are unreachable as attributes.** `tw.calendar` is the function,
   so `tw.calendar.is_trading_day` raises `AttributeError`; only
   `from twmarket.calendar import is_trading_day` works. Build Step 7 promised both
   helpers. Fix by exporting `is_trading_day` and `next_trading_day` at package level —
   an addition to the public API, not a rename.

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
- [ ] Unknown ticker raises after one period fetch, not ~140
- [x] `parse_bulk_file` raises on a zero-row parse that is not the `查無資料` page
      (2026-09-28)
- [ ] Row-count floor applied when caching a settled period
- [ ] Coverage ≥90%, CI enforces it
- [x] Spec conflicts 1–2 decided and `twmarket.md` amended to match (2026-09-28)
- [ ] Spec conflicts 3–4 fixed in code (empty-frame dtypes; calendar helpers exported)
- [x] History decision made: leave as is (2026-09-28)
- [ ] `v0.1.0` and `v0.1.1` tagged
- [ ] `v0.1.1` published to PyPI by trusted publishing from the tag; README install line
      updated
