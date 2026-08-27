import datetime as dt

import pytest

import twmarket as tw


def test_single_month_query(use_mops_fixture):
    df = tw.revenue("2330", "2025-06", "2025-06")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["revenue_twd"] == 263_708_978_000
    assert row["announce_date"] == dt.date(2025, 7, 10)
    assert row["announce_date_estimated"] is True or row["announce_date_estimated"] == True  # noqa: E712
    assert not row["is_restated"]


def test_range_fetches_each_month_once(use_mops_fixture):
    tw.revenue("2330", "2025-04", "2025-06")
    assert sorted(use_mops_fixture) == [(114, 4), (114, 5), (114, 6)]
    # Second query hits the cache — no new fetches
    tw.revenue("1101", "2025-04", "2025-06")
    assert len(use_mops_fixture) == 3


def test_invalid_ticker_raises(use_mops_fixture):
    with pytest.raises(ValueError):
        tw.revenue("not-a-ticker")


def test_unknown_ticker_raises(use_mops_fixture):
    with pytest.raises(ValueError):
        tw.revenue("9999", "2025-06", "2025-06")


def test_as_of_before_announce_returns_empty(use_mops_fixture):
    # June 2025 revenue estimated announce = 2025-07-10
    df = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-09")
    assert df.empty
    assert list(df.columns) == [
        "ticker", "period", "revenue_twd", "yoy_pct", "mom_pct",
        "announce_date", "announce_date_estimated", "is_restated",
    ]  # fmt: skip


def test_as_of_on_announce_returns_row(use_mops_fixture):
    df = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-10")
    assert len(df) == 1


def test_open_filing_window_is_not_cached(use_mops_fixture):
    """A month is only frozen into the store once its filing window has closed.

    Companies file throughout the window. Caching a snapshot taken on the 5th
    would hide every filing that lands between then and the deadline — the store
    is append-only and the month would read as complete forever.
    """
    from twmarket import _store
    from twmarket.revenue import ensure_period

    early = ensure_period("2025-06", today=dt.date(2025, 7, 5))
    assert not early.empty  # still served to the caller
    assert not _store.has_revenue_period("2025-06")

    ensure_period("2025-06", today=dt.date(2025, 7, 11))
    assert _store.has_revenue_period("2025-06")


def test_open_window_refetches_until_settled(use_mops_fixture):
    """Each query inside the open window goes back to MOPS for late filers."""
    from twmarket.revenue import ensure_period

    ensure_period("2025-06", today=dt.date(2025, 7, 5))
    ensure_period("2025-06", today=dt.date(2025, 7, 8))
    assert len(use_mops_fixture) == 2  # no stale cache served
    ensure_period("2025-06", today=dt.date(2025, 7, 11))
    ensure_period("2025-06", today=dt.date(2025, 7, 12))
    assert len(use_mops_fixture) == 3  # settled, then served from the store
