import datetime as dt

import pytest

import twmarket as tw
from twmarket import _store
from twmarket.revenue import ensure_period
from twmarket.sync import sync_period

TSMC_ORIGINAL = b"            263,708,978"
TSMC_REVISED = b"            999,999,999"


@pytest.fixture
def fetch_returns(monkeypatch, mops_fixture_bytes):
    """Control what fetch_mops_revenue returns per test (mutable holder)."""
    holder = {"content": mops_fixture_bytes}
    monkeypatch.setattr(
        "twmarket._client.fetch_mops_revenue", lambda roc_year, month: holder["content"]
    )
    return holder


def test_first_sync_records_observed_announce_dates(fetch_returns):
    today = dt.date(2025, 7, 8)
    appended = sync_period("2025-06", today=today)
    row = appended[appended["ticker"] == "2330"].iloc[0]
    assert row["announce_date"] == today
    assert not row["announce_date_estimated"]
    assert not row["is_restated"]


def test_second_sync_no_changes_appends_nothing(fetch_returns):
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    appended = sync_period("2025-06", today=dt.date(2025, 7, 9))
    assert appended.empty


def test_restatement_preserves_original_row(fetch_returns, mops_fixture_bytes):
    assert TSMC_ORIGINAL in mops_fixture_bytes
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    fetch_returns["content"] = mops_fixture_bytes.replace(TSMC_ORIGINAL, TSMC_REVISED)
    appended = sync_period("2025-06", today=dt.date(2025, 7, 20))

    revised = appended[appended["ticker"] == "2330"].iloc[0]
    assert revised["is_restated"]
    assert revised["revenue_twd"] == 999_999_999_000
    assert revised["observed_date"] == dt.date(2025, 7, 20)

    stored = _store.load_revenue_period("2025-06")
    tsmc = stored[stored["ticker"] == "2330"]
    assert len(tsmc) == 2  # original + restated, original never discarded
    assert set(tsmc["revenue_twd"]) == {263_708_978_000, 999_999_999_000}


def test_as_of_respects_restatement_timeline(fetch_returns, mops_fixture_bytes):
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    fetch_returns["content"] = mops_fixture_bytes.replace(TSMC_ORIGINAL, TSMC_REVISED)
    sync_period("2025-06", today=dt.date(2025, 7, 20))

    before = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-10")
    assert before.iloc[0]["revenue_twd"] == 263_708_978_000
    after = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-21")
    assert after.iloc[0]["revenue_twd"] == 999_999_999_000
    assert after.iloc[0]["is_restated"]
    too_early = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-07")
    assert too_early.empty


def test_sync_after_backfill_marks_observed(fetch_returns):
    # Backfilled period has estimated dates; sync appends nothing if figures match
    ensure_period("2025-06")
    appended = sync_period("2025-06", today=dt.date(2025, 8, 1))
    assert appended.empty
    df = tw.revenue("2330", "2025-06", "2025-06")
    assert df.iloc[0]["announce_date_estimated"]
