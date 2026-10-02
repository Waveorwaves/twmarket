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


def test_month_is_rechecked_until_its_window_closes(use_mops_fixture):
    """A month is only final once it has been checked after its re-check window.

    Before the deadline it is not cached at all. After the deadline it is cached,
    but late filers keep arriving, so each query still compares it with MOPS until
    the window closes at the end of the following month. One check after that
    makes it final.
    """
    from twmarket import _store
    from twmarket.revenue import ensure_period

    ensure_period("2025-06", today=dt.date(2025, 7, 5))
    ensure_period("2025-06", today=dt.date(2025, 7, 8))
    assert len(use_mops_fixture) == 2  # filing window open: no stale cache served
    assert not _store.has_revenue_period("2025-06")

    ensure_period("2025-06", today=dt.date(2025, 7, 11))  # past the 07-10 deadline
    ensure_period("2025-06", today=dt.date(2025, 7, 12))
    assert len(use_mops_fixture) == 4  # stored now, but still looking for late filers
    assert _store.has_revenue_period("2025-06")

    ensure_period("2025-06", today=dt.date(2025, 8, 2))  # window closed on 08-01
    ensure_period("2025-06", today=dt.date(2025, 8, 3))
    ensure_period("2025-06", today=dt.date(2026, 1, 1))
    assert len(use_mops_fixture) == 5  # one last check, then served from the store


def test_unpublished_month_is_never_cached(monkeypatch, mops_unpublished_bytes):
    """A 查無資料 page means "ask again later", even after the deadline."""
    from twmarket import _store
    from twmarket.revenue import ensure_period

    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: mops_unpublished_bytes)
    df = ensure_period("2026-08", today=dt.date(2026, 9, 28))  # deadline long passed
    assert df.empty
    assert not _store.has_revenue_period("2026-08")


def test_unpublished_month_in_range_leaves_the_rest(
    monkeypatch, mops_fixture_bytes, mops_unpublished_bytes
):
    pages = {(114, 6): mops_fixture_bytes, (114, 7): mops_unpublished_bytes}
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: pages[(y, m)])
    df = tw.revenue("2330", "2025-06", "2025-07")
    assert list(df["period"]) == ["2025-06"]


def test_unknown_ticker_costs_one_fetch_even_early_in_the_month(set_taipei_date, use_mops_fixture):
    """Before the 10th the last completed month is still being filed.

    The lookup has to skip it and use the latest *settled* month, or a typo
    would cost two fetches and a real company that has not filed yet would be
    called unknown.
    """
    set_taipei_date(2026, 10, 5)  # September's window is open; August is settled
    with pytest.raises(ValueError, match="unknown ticker.*2026-08"):
        tw.revenue("9999")
    assert use_mops_fixture == [(115, 8)]


def test_missing_from_an_open_window_month_is_not_an_error(
    set_taipei_date, monkeypatch, first_rows
):
    """While a month is being filed, a company not in it yet has simply not filed."""
    set_taipei_date(2025, 7, 3)  # June's deadline is 07-10
    thin = first_rows(40)
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: thin)
    assert tw.revenue("2330", "2025-06", "2025-06").empty  # not among the first 40 filers
    assert len(tw.revenue("1101", "2025-06", "2025-06")) == 1  # one that has filed


def test_range_of_unpublished_months_is_empty_not_an_error(monkeypatch, mops_unpublished_bytes):
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: mops_unpublished_bytes)
    df = tw.revenue("2330", "2099-01", "2099-02")
    assert df.empty
    assert list(df.columns) == [
        "ticker", "period", "revenue_twd", "yoy_pct", "mom_pct",
        "announce_date", "announce_date_estimated", "is_restated",
    ]  # fmt: skip


def test_delisted_company_needs_an_end_within_its_history(
    monkeypatch, mops_fixture_bytes, without_ticker
):
    """The one-month lookup trades this away: gone from the latest month = unknown.

    The error has to say how to get the data, and following it has to work.
    """
    pages = {(114, 5): mops_fixture_bytes, (114, 6): without_ticker("1101")}
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: pages[(y, m)])
    with pytest.raises(ValueError, match="delisted.*`end`"):
        tw.revenue("1101", "2025-05", "2025-06")
    assert list(tw.revenue("1101", "2025-05", "2025-05")["period"]) == ["2025-05"]


def test_synced_month_gets_one_last_check_and_no_more(use_mops_fixture):
    """Everyone filed early and later syncs found nothing new.

    The store then holds no row dated after the deadline, which must not leave
    the month open forever. Once its re-check window has closed, one final
    comparison settles it and later queries stay off MOPS.
    """
    from twmarket.sync import sync_period

    sync_period("2025-06", today=dt.date(2025, 7, 9))
    sync_period("2025-06", today=dt.date(2025, 7, 11))  # past the 07-10 deadline, nothing new
    use_mops_fixture.clear()
    for _ in range(3):
        tw.revenue("2330", "2025-06", "2025-06")  # long after the window closed
    assert use_mops_fixture == [(114, 6)]


def test_revenue_before_2013_is_rejected_up_front(use_mops_fixture):
    """MOPS switched to IFRS consolidated revenue, and a new page layout, in 2013-01."""
    with pytest.raises(ValueError, match="2013-01"):
        tw.revenue("2330", "2012-12", "2013-03")
    assert use_mops_fixture == []


def test_as_of_can_be_a_date_object(use_mops_fixture):
    by_string = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-10")
    by_date = tw.revenue("2330", "2025-06", "2025-06", as_of=dt.date(2025, 7, 10))
    assert len(by_date) == 1 and by_string.equals(by_date)
    with pytest.raises(ValueError, match="as_of must be a date like"):
        tw.revenue("2330", "2025-06", "2025-06", as_of="July 10")


def test_asking_for_an_etf_explains_why_it_is_not_there(use_mops_fixture):
    with pytest.raises(ValueError, match="ETFs and funds"):
        tw.revenue("0050", "2025-06", "2025-06")


def test_ticker_loop_downloads_a_month_still_being_filed_only_once(
    set_taipei_date, use_mops_fixture
):
    """Research loops over tickers. The month that is still open must not be
    fetched again for each one: that is slow, and it hammers MOPS."""
    set_taipei_date(2025, 7, 5)  # June's filing window is open: never cached on disk
    for ticker in ("2330", "1101", "2317"):
        assert len(tw.revenue(ticker, "2025-06", "2025-06")) == 1
    assert use_mops_fixture == [(114, 6)]


def test_ticker_loop_rechecks_a_stored_month_only_once(set_taipei_date, use_mops_fixture):
    set_taipei_date(2025, 7, 15)  # past the deadline, inside the re-check window
    for ticker in ("2330", "1101", "2317"):
        assert len(tw.revenue(ticker, "2025-06", "2025-06")) == 1
    assert use_mops_fixture == [(114, 6)]


def test_an_open_month_is_looked_at_again_once_the_interval_has_passed(
    set_taipei_date, use_mops_fixture, monkeypatch
):
    import sys

    # `twmarket.revenue` is the public function; the module is reached through sys.modules.
    monkeypatch.setattr(sys.modules["twmarket.revenue"], "RECHECK_INTERVAL_SECONDS", 0)
    set_taipei_date(2025, 7, 5)
    tw.revenue("2330", "2025-06", "2025-06")
    tw.revenue("2330", "2025-06", "2025-06")
    assert use_mops_fixture == [(114, 6), (114, 6)]
