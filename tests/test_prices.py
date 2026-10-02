import datetime as dt
import json
from pathlib import Path

import pytest

import twmarket as tw
from twmarket.prices import parse_stock_day

FIXTURE = Path(__file__).parent / "fixtures" / "stock_day_2330_202506.json"


@pytest.fixture
def stock_day_payload():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def use_stock_day_fixture(monkeypatch, stock_day_payload):
    calls = []

    def _fake(ticker, year, month):
        calls.append((ticker, year, month))
        return stock_day_payload

    monkeypatch.setattr("twmarket._client.fetch_stock_day", _fake)
    return calls


def test_parse_fixture(stock_day_payload):
    df = parse_stock_day(stock_day_payload, "2330")
    assert len(df) == 21
    first = df.iloc[0]
    assert first["date"] == dt.date(2025, 6, 2)
    assert first["open"] == 958.0
    assert first["close"] == 946.0
    assert first["volume"] == 40_608_468
    assert first["turnover"] == 38_643_155_297
    last = df.iloc[-1]
    assert last["date"] == dt.date(2025, 6, 30)
    assert last["close"] == 1060.0


def test_parse_error_stat_returns_empty():
    df = parse_stock_day({"stat": "很抱歉，沒有符合條件的資料!"}, "0000")
    assert df.empty
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "turnover"]


def test_prices_date_filter(use_stock_day_fixture):
    df = tw.prices("2330", "2025-06-05", "2025-06-10")
    assert df["date"].min() >= dt.date(2025, 6, 5)
    assert df["date"].max() <= dt.date(2025, 6, 10)
    assert len(df) == 4  # 6/5, 6/6, 6/9, 6/10 (weekend skipped)


def test_prices_cached_after_first_fetch(use_stock_day_fixture):
    tw.prices("2330", "2025-06-01", "2025-06-30")
    tw.prices("2330", "2025-06-01", "2025-06-30")
    assert use_stock_day_fixture == [("2330", 2025, 6)]


def test_prices_invalid_ticker():
    with pytest.raises(ValueError):
        tw.prices("abc", "2025-06-01", "2025-06-30")


def test_prices_start_after_end():
    with pytest.raises(ValueError):
        tw.prices("2330", "2025-07-01", "2025-06-01")


def test_prices_rejects_a_non_string_ticker():
    with pytest.raises(ValueError, match="invalid ticker"):
        tw.prices(2330, "2025-06-01", "2025-06-30")


def test_month_in_progress_is_not_cached(set_taipei_date, use_stock_day_fixture):
    set_taipei_date(2025, 6, 15)  # June is still trading
    tw.prices("2330", "2025-06-01", "2025-06-30")
    tw.prices("2330", "2025-06-01", "2025-06-30")
    assert use_stock_day_fixture == [("2330", 2025, 6), ("2330", 2025, 6)]


def test_dates_can_be_date_objects(use_stock_day_fixture):
    import pandas as pd

    by_string = tw.prices("2330", "2025-06-05", "2025-06-10")
    by_date = tw.prices("2330", dt.date(2025, 6, 5), dt.date(2025, 6, 10))
    by_timestamp = tw.prices("2330", pd.Timestamp("2025-06-05"), pd.Timestamp("2025-06-10"))
    assert by_string.equals(by_date) and by_string.equals(by_timestamp)


def test_bad_date_says_which_argument():
    with pytest.raises(ValueError, match="end must be a date like"):
        tw.prices("2330", "2025-06-01", "2025/06/30")


def test_calendar_helpers_accept_dates_and_datetimes():
    assert len(tw.calendar(dt.date(2025, 1, 20), dt.date(2025, 1, 22))) == 3
    assert tw.is_trading_day(dt.datetime(2025, 1, 22, 9, 30))
    assert tw.next_trading_day(dt.date(2025, 1, 22)) == dt.date(2025, 2, 3)
