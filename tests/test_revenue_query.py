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
