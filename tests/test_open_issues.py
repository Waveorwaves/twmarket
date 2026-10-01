"""Executable form of the open v0.1.1 work: each test states the wanted behaviour.

`xfail(strict=True)` means "known defect, fix pending". The suite stays green today, and
the moment a fix lands the test XPASSes, which strict mode turns into a failure —
so the marker has to be deleted in the same commit as the fix and the test becomes a
permanent regression guard. Never loosen a test here to make a fix pass; fix the code.

Sections are labelled with their Fixplan.md item, or "REVIEW" where the defect was found
while reviewing and is not (yet) in the plan.
"""

from __future__ import annotations

import datetime as dt
import os
import time

import pytest

import twmarket as tw
from twmarket import _store
from twmarket.revenue import ensure_period, parse_bulk_file

ROW_TAG = b"<tr align=right>"


def _keep_first_rows(content: bytes, n: int) -> bytes:
    """Cut a real bulk file after its first `n` data rows (byte-level: Big5 stays intact)."""
    pos = -1
    for _ in range(n + 1):
        pos = content.find(ROW_TAG, pos + 1)
    assert pos > 0, "fixture has fewer rows than requested"
    return content[:pos]


# --- Fixplan P1: unknown ticker costs ~140 fetches ---------------------------


@pytest.mark.xfail(
    strict=True,
    reason="Fixplan P1: get_revenue loops every month before it can reject a bad ticker",
)
def test_unknown_ticker_fails_after_one_period_fetch(use_mops_fixture):
    with pytest.raises(ValueError, match="unknown ticker"):
        tw.revenue("9999")  # default range: 2015-01 .. last completed month
    assert len(use_mops_fixture) == 1


def test_known_ticker_still_gets_the_whole_range(use_mops_fixture):
    """Guard for the P1 fix: the early probe must not truncate a valid query."""
    df = tw.revenue("2330", "2024-01", "2025-06")
    assert len(df) == 18
    assert len(set(use_mops_fixture)) == 18


# --- Fixplan P2: parse_bulk_file fails open ----------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="Fixplan P2: ensure_period stores a settled month even if the file is truncated",
)
def test_settled_period_with_implausibly_few_rows_is_rejected(monkeypatch, mops_fixture_bytes):
    partial = _keep_first_rows(mops_fixture_bytes, 40)
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: partial)
    with pytest.raises(ValueError):
        ensure_period("2025-06", today=dt.date(2025, 8, 1))  # deadline long passed
    assert not _store.has_revenue_period("2025-06")


def test_open_window_with_few_rows_is_served_not_raised(monkeypatch, mops_fixture_bytes):
    """Guard for the P2 floor: early in the month a thin file is normal."""
    partial = _keep_first_rows(mops_fixture_bytes, 40)
    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: partial)
    df = ensure_period("2025-06", today=dt.date(2025, 7, 3))  # before the 07-10 deadline
    assert len(df) == len(parse_bulk_file(partial, "2025-06")) > 0
    assert not _store.has_revenue_period("2025-06")


@pytest.mark.xfail(
    strict=True,
    reason="Fixplan P2: the substring check drops any row containing 合計, incl. a company name",
)
def test_company_name_containing_total_marker_is_not_dropped(mops_fixture_bytes):
    baseline = parse_bulk_file(mops_fixture_bytes, "2025-06")
    renamed = mops_fixture_bytes.replace("台泥".encode("big5"), "合計實業".encode("big5"), 1)
    df = parse_bulk_file(renamed, "2025-06")
    assert len(df) == len(baseline)
    assert df[df["ticker"] == "1101"].iloc[0]["name"] == "合計實業"


def test_real_total_rows_are_still_excluded(mops_fixture_bytes):
    """Guard for removing the substring check: the ticker guard must carry the load."""
    df = parse_bulk_file(mops_fixture_bytes, "2025-06")
    assert len(df) == 990
    assert (df["name"] != "合計").all()


# --- Fixplan P2 spec conflicts 3 and 4 ---------------------------------------


@pytest.mark.xfail(
    strict=True, reason="Fixplan spec-conflict 3: empty revenue() frame has all-object dtypes"
)
def test_empty_revenue_frame_has_the_same_dtypes_as_a_full_one(use_mops_fixture):
    full = tw.revenue("2330", "2025-06", "2025-06")
    empty = tw.revenue("2330", "2025-06", "2025-06", as_of="2025-07-09")
    assert empty.empty
    assert list(empty.columns) == list(full.columns)
    assert dict(empty.dtypes) == dict(full.dtypes)


@pytest.mark.xfail(
    strict=True, reason="Fixplan spec-conflict 4: is_trading_day/next_trading_day not exported"
)
def test_calendar_helpers_are_reachable_from_the_package(monkeypatch):
    assert callable(tw.is_trading_day)
    assert callable(tw.next_trading_day)
    assert tw.is_trading_day("2025-01-22")
    assert tw.next_trading_day("2025-01-22") == dt.date(2025, 2, 3)


def test_calendar_function_is_not_shadowed_by_its_module():
    """Guard: exporting the helpers must not turn tw.calendar back into a module."""
    assert callable(tw.calendar)
    assert list(tw.calendar("2025-01-20", "2025-01-22").columns) == ["date"]


# --- REVIEW: found while reading the code, not in Fixplan.md -----------------


@pytest.mark.xfail(
    strict=True,
    reason="REVIEW: ensure_month caches any month != the current one, including future months",
)
def test_future_price_months_are_not_frozen_as_empty():
    """An empty answer for a month that has not happened is not data.

    Caching it makes that ticker-month permanently empty once the month arrives, and
    every announce-date estimate or calendar lookup that touches it silently loses its
    trading calendar (falling back to the weekday-only roll).
    """
    assert tw.prices("2330", "2099-01-01", "2099-01-31").empty
    assert _store.load_prices_month("2330_2099-01") is None


@pytest.mark.xfail(
    strict=True,
    reason="REVIEW: an inverted revenue range is reported as 'unknown ticker'",
)
def test_inverted_revenue_range_is_reported_as_such(use_mops_fixture):
    with pytest.raises(ValueError, match=r"(?i)start|after|before|order|range"):
        tw.revenue("2330", "2025-06", "2025-01")
    assert use_mops_fixture == []  # and nothing should be fetched to find that out


@pytest.mark.xfail(
    strict=True,
    reason="REVIEW: revenue() accepts an int ticker, then never matches it and blames the ticker",
)
def test_integer_ticker_is_handled_deliberately(use_mops_fixture):
    try:
        df = tw.revenue(2330, "2025-06", "2025-06")
    except ValueError as exc:
        assert "invalid ticker" in str(exc)  # rejecting it up front is fine
    else:
        assert len(df) == 1  # so is accepting it


@pytest.fixture
def utc_machine_at_1730_on_deadline_day(monkeypatch):
    """Machine clock in UTC, frozen at 2025-07-10 17:30 UTC (= 07-11 01:30 in Taipei)."""
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    instant = dt.datetime(2025, 7, 10, 17, 30, tzinfo=dt.timezone.utc).timestamp()  # noqa: UP017
    monkeypatch.setattr(time, "time", lambda: instant)
    yield
    monkeypatch.undo()
    if old_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old_tz
    time.tzset()


@pytest.mark.xfail(
    strict=True,
    reason="REVIEW: sync() dates rows with the machine's local date, not Asia/Taipei",
)
def test_sync_uses_the_taipei_date_not_the_machine_date(
    utc_machine_at_1730_on_deadline_day, monkeypatch, mops_fixture_bytes
):
    """A UTC cron at 17:30 on the deadline is already the day *after* in Taipei.

    The June deadline is 07-10. In Taipei this sighting is past it, so it must fall
    back to the estimate. Dated with the UTC date it looks like an on-time catch and is
    flagged authoritative: the false-announce-date bug (Fixplan P0) coming back in
    through the clock.
    """
    from twmarket.sync import sync_period

    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: mops_fixture_bytes)
    appended = sync_period("2025-06")  # no injected `today`: the real default path
    row = appended[appended["ticker"] == "2330"].iloc[0]
    assert row["observed_date"] == dt.date(2025, 7, 11)
    assert row["announce_date_estimated"]
