"""Contract tests: twmarket.md definition-of-done items and point-in-time invariants.

These do not re-test single behaviours (the module test files do that). They check
properties that must hold across whole sequences of operations — the ones a
refactor could break without any single-function test noticing.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd
import pytest

import twmarket as tw
from twmarket import _store
from twmarket.revenue import ensure_period
from twmarket.sync import _current_and_prior_periods, run_sync, sync_period

ROOT = Path(__file__).parent.parent
TSMC_ORIGINAL = b"            263,708,978"
REVISED_A = b"            300,000,000"
REVISED_B = b"            400,000,000"


@pytest.fixture
def feed(monkeypatch, mops_fixture_bytes):
    """Mutable MOPS response: feed['content'] is served for every month."""
    holder = {"content": mops_fixture_bytes}
    monkeypatch.setattr(
        "twmarket._client.fetch_mops_revenue", lambda roc_year, month: holder["content"]
    )
    return holder


def _with_tsmc(fixture_bytes: bytes, revenue: bytes) -> bytes:
    assert TSMC_ORIGINAL in fixture_bytes
    return fixture_bytes.replace(TSMC_ORIGINAL, revenue)


# --- twmarket.md §7 definition of done ---------------------------------------


def test_dod_as_of_2025_05_before_and_after_the_deadline(use_mops_fixture):
    """§7: period 2025-05, as_of 06-05 -> nothing; as_of 06-10 -> returned."""
    assert tw.revenue("2330", "2025-05", "2025-05", as_of="2025-06-05").empty
    got = tw.revenue("2330", "2025-05", "2025-05", as_of="2025-06-10")
    assert list(got["period"]) == ["2025-05"]
    assert got.iloc[0]["announce_date"] == dt.date(2025, 6, 10)
    assert got.iloc[0]["announce_date_estimated"]


def test_dod_versions_agree():
    """Release bumps must touch pyproject.toml and __init__ together (Fixplan P3.5)."""
    pyproject = (ROOT / "pyproject.toml").read_text()
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    assert tw.__version__ == declared


def test_readme_quickstart_calls_run(use_mops_fixture, feed):
    """The three README code blocks must at least execute against fixtures."""
    rev = tw.revenue("2330", "2025-04", "2025-06")
    assert list(rev.columns) == [
        "ticker", "period", "revenue_twd", "yoy_pct", "mom_pct",
        "announce_date", "announce_date_estimated", "is_restated",
    ]  # fmt: skip
    tw.revenue("2330", "2025-04", "2025-06", as_of="2025-06-05")
    px = tw.prices("2330", "2025-01-01", "2025-02-28")
    assert list(px.columns) == ["date", "open", "high", "low", "close", "volume", "turnover"]
    assert not px.empty
    assert list(tw.calendar("2025-01-01", "2025-02-28").columns) == ["date"]
    assert not run_sync(today=dt.date(2025, 7, 8)).empty  # tw.sync() minus the wall clock


# --- point-in-time invariants ------------------------------------------------


def test_as_of_never_returns_a_figure_announced_later(feed, mops_fixture_bytes):
    """Sweep as_of across a restatement timeline; nothing may leak from the future."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    sync_period("2025-06", today=dt.date(2025, 7, 20))

    day = dt.date(2025, 7, 1)
    while day <= dt.date(2025, 7, 31):
        got = tw.revenue("2330", "2025-06", "2025-06", as_of=day.isoformat())
        assert (got["announce_date"] <= day).all(), f"lookahead on as_of={day}"
        day += dt.timedelta(days=1)


def test_as_of_result_is_monotone_as_knowledge_accumulates(feed, mops_fixture_bytes):
    """Once a period is visible it stays visible for every later as_of."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    visible = []
    day = dt.date(2025, 7, 1)
    while day <= dt.date(2025, 7, 31):
        visible.append(not tw.revenue("2330", "2025-06", "2025-06", as_of=day.isoformat()).empty)
        day += dt.timedelta(days=1)
    assert visible == sorted(visible)  # False... then True..., never back
    assert visible[0] is False and visible[-1] is True


def test_two_restatements_each_visible_only_from_its_own_date(feed, mops_fixture_bytes):
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    sync_period("2025-06", today=dt.date(2025, 7, 15))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_B)
    sync_period("2025-06", today=dt.date(2025, 7, 22))

    def at(day):
        return tw.revenue("2330", "2025-06", "2025-06", as_of=day).iloc[0]

    assert at("2025-07-09")["revenue_twd"] == 263_708_978_000
    assert not at("2025-07-09")["is_restated"]
    assert at("2025-07-16")["revenue_twd"] == 300_000_000_000
    assert at("2025-07-23")["revenue_twd"] == 400_000_000_000
    assert at("2025-07-23")["is_restated"]
    # Latest view (no as_of) is the last restatement
    assert tw.revenue("2330", "2025-06", "2025-06").iloc[0]["revenue_twd"] == 400_000_000_000


def test_restating_back_to_the_original_value_is_still_a_new_observation(feed, mops_fixture_bytes):
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    sync_period("2025-06", today=dt.date(2025, 7, 15))
    feed["content"] = mops_fixture_bytes  # MOPS reverts the figure
    appended = sync_period("2025-06", today=dt.date(2025, 7, 22))

    row = appended[appended["ticker"] == "2330"].iloc[0]
    assert row["is_restated"] and row["revenue_twd"] == 263_708_978_000
    stored = _store.load_revenue_period("2025-06")
    assert len(stored[stored["ticker"] == "2330"]) == 3


def test_store_is_append_only_across_syncs(feed, mops_fixture_bytes):
    """Earlier rows must survive byte-for-byte; row count never shrinks."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    before = _store.load_revenue_period("2025-06")

    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    sync_period("2025-06", today=dt.date(2025, 7, 15))
    sync_period("2025-06", today=dt.date(2025, 7, 16))  # no-op day
    after = _store.load_revenue_period("2025-06")

    assert len(after) == len(before) + 1
    pd.testing.assert_frame_equal(after.iloc[: len(before)].reset_index(drop=True), before)


def test_same_day_double_sync_appends_nothing_the_second_time(feed):
    first = sync_period("2025-06", today=dt.date(2025, 7, 8))
    second = sync_period("2025-06", today=dt.date(2025, 7, 8))
    assert not first.empty and second.empty


def test_one_row_per_period_even_with_restatements(feed, mops_fixture_bytes):
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    sync_period("2025-06", today=dt.date(2025, 7, 15))
    df = tw.revenue("2330", "2025-05", "2025-06")
    assert not df["period"].duplicated().any()
    assert list(df["period"]) == sorted(df["period"])


def test_restatement_flag_only_on_changed_rows(feed, mops_fixture_bytes):
    """One company changing must not mark the other ~990 as restated."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    feed["content"] = _with_tsmc(mops_fixture_bytes, REVISED_A)
    appended = sync_period("2025-06", today=dt.date(2025, 7, 15))
    assert list(appended["ticker"]) == ["2330"]
    stored = _store.load_revenue_period("2025-06")
    assert stored["is_restated"].sum() == 1


def test_first_sync_marks_every_row_observed_not_estimated(feed):
    appended = sync_period("2025-06", today=dt.date(2025, 7, 8))
    assert len(appended) > 900
    assert not appended["announce_date_estimated"].any()
    assert (appended["announce_date"] == dt.date(2025, 7, 8)).all()


def test_observed_then_backfill_never_downgrades_observed_rows(feed):
    """An observed row must stay observed when a later query walks the same month."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    ensure_period("2025-06", today=dt.date(2025, 7, 15))
    got = tw.revenue("2330", "2025-06", "2025-06")
    assert not got.iloc[0]["announce_date_estimated"]
    assert got.iloc[0]["announce_date"] == dt.date(2025, 7, 8)


def test_estimated_dates_are_never_before_the_statutory_deadline(use_mops_fixture):
    """The conservative-estimate guarantee, across a stretch of real periods."""
    from twmarket._dates import statutory_deadline

    for period in ("2024-12", "2025-01", "2025-02", "2025-05", "2025-06"):
        df = ensure_period(period, today=dt.date(2025, 8, 1))
        assert not df.empty
        deadline = statutory_deadline(period)
        assert (df["announce_date"] >= deadline).all(), period
        assert (df["announce_date"] - deadline).map(lambda d: d.days).max() <= 14


def test_lunar_new_year_estimate_end_to_end(use_mops_fixture):
    """Jan-2013 revenue is due Sun 02-10; the market reopened Mon 02-18."""
    got = tw.revenue("2330", "2013-01", "2013-01", as_of="2013-02-17")
    assert got.empty
    got = tw.revenue("2330", "2013-01", "2013-01", as_of="2013-02-18")
    assert got.iloc[0]["announce_date"] == dt.date(2013, 2, 18)


# --- year boundaries and period arithmetic -----------------------------------


def test_sync_periods_wrap_the_year():
    assert _current_and_prior_periods(dt.date(2026, 1, 15)) == ["2025-12", "2026-01"]
    assert _current_and_prior_periods(dt.date(2025, 12, 31)) == ["2025-11", "2025-12"]


def test_run_sync_snapshots_both_months_and_is_idempotent(feed):
    first = run_sync(today=dt.date(2025, 7, 8))
    assert set(first["period"]) == {"2025-06", "2025-07"}
    assert run_sync(today=dt.date(2025, 7, 8)).empty


def test_range_spanning_a_year_boundary(use_mops_fixture):
    got = tw.revenue("2330", "2024-11", "2025-02")
    assert list(got["period"]) == ["2024-11", "2024-12", "2025-01", "2025-02"]
    dec = got[got["period"] == "2024-12"].iloc[0]
    assert dec["announce_date"] == dt.date(2025, 1, 10)  # deadline crosses into next year


# --- output contract ---------------------------------------------------------


def test_revenue_output_dtypes(use_mops_fixture):
    df = tw.revenue("2330", "2025-05", "2025-06")
    assert str(df["revenue_twd"].dtype) == "Int64"
    assert df["yoy_pct"].dtype == "float64"
    assert df["mom_pct"].dtype == "float64"
    assert df["announce_date_estimated"].dtype == "bool"
    assert df["is_restated"].dtype == "bool"
    assert all(isinstance(d, dt.date) for d in df["announce_date"])


def test_revenue_hides_internal_columns(use_mops_fixture):
    df = tw.revenue("2330", "2025-06", "2025-06")
    assert "observed_date" not in df.columns and "name" not in df.columns


@pytest.mark.parametrize("bad", ["", "abc", "23", "2330a", " 2330", "2330 ", "12345678", None])
def test_malformed_ticker_raises_valueerror_everywhere(bad):
    with pytest.raises(ValueError):
        tw.revenue(bad, "2025-06", "2025-06")
    with pytest.raises(ValueError):
        tw.prices(bad, "2025-06-01", "2025-06-30")


def test_prices_matches_recorded_closes():
    """Spot-check parsed closes against the raw recorded TWSE payload."""
    import json

    raw = json.loads((ROOT / "tests/fixtures/stock_day_2330_202501.json").read_text())
    px = tw.prices("2330", "2025-01-01", "2025-01-31")
    assert len(px) == len(raw["data"])
    for parsed, row in zip(px.itertuples(), raw["data"], strict=True):
        assert parsed.close == float(row[6].replace(",", ""))
        assert parsed.volume == int(row[1].replace(",", ""))
    assert px["date"].is_monotonic_increasing
