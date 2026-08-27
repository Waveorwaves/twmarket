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


def test_sync_after_deadline_falls_back_to_estimate(fetch_returns):
    """A cold start long after the deadline must not invent an announce date.

    June 2025 revenue was filed by 2025-07-10. A snapshot first seeing it on
    2025-08-01 knows only that it was filed some time before then, so it has to
    fall back to the estimate — dating it 2025-08-01 would be three weeks late
    *and* flagged authoritative.
    """
    appended = sync_period("2025-06", today=dt.date(2025, 8, 1))
    row = appended[appended["ticker"] == "2330"].iloc[0]
    assert row["announce_date"] == dt.date(2025, 7, 10)
    assert row["announce_date_estimated"]
    assert row["observed_date"] == dt.date(2025, 8, 1)


def test_restatement_is_observed_even_after_the_deadline(fetch_returns, mops_fixture_bytes):
    """A value seen changing is genuinely observed, whenever that happens."""
    sync_period("2025-06", today=dt.date(2025, 7, 8))
    fetch_returns["content"] = mops_fixture_bytes.replace(TSMC_ORIGINAL, TSMC_REVISED)
    appended = sync_period("2025-06", today=dt.date(2025, 7, 20))  # past the 07-10 deadline

    row = appended[appended["ticker"] == "2330"].iloc[0]
    assert row["is_restated"]
    assert row["announce_date"] == dt.date(2025, 7, 20)
    assert not row["announce_date_estimated"]


def test_as_of_excludes_late_first_sighting_before_deadline(fetch_returns):
    """The fallback date must hold up end-to-end through the as_of filter."""
    sync_period("2025-06", today=dt.date(2025, 8, 1))
    assert tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-09").empty
    visible = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-10")
    assert len(visible) == 1
    assert visible.iloc[0]["announce_date_estimated"]


def test_partial_month_from_an_early_sync_is_topped_up(fetch_returns, mops_fixture_bytes):
    """A snapshot taken before the deadline must not freeze the month.

    sync() writes a period file whenever it runs, including on the 5th when most
    companies have not filed. Later queries have to notice that every row in
    that file predates the deadline and go back for the ones that came after.
    """
    not_yet_filed = mops_fixture_bytes.replace(TSMC_ORIGINAL, b"                      -")
    fetch_returns["content"] = not_yet_filed
    sync_period("2025-06", today=dt.date(2025, 7, 5))
    stored = _store.load_revenue_period("2025-06")
    assert stored[stored["ticker"] == "2330"].empty  # nothing filed for 2330 yet

    fetch_returns["content"] = mops_fixture_bytes  # 2330 files before the deadline
    df = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-31")
    assert df.iloc[0]["revenue_twd"] == 263_708_978_000
