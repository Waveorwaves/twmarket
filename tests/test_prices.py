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
