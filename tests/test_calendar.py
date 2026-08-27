import datetime as dt
import json
from pathlib import Path

import pytest

import twmarket as tw
from twmarket.calendar import is_trading_day, next_trading_day

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def use_0050_fixtures(monkeypatch):
    """Serve recorded 0050 months; anything unrecorded is an error."""

    def _fake(ticker, year, month):
        path = FIXTURES / f"stock_day_{ticker}_{year:04d}{month:02d}.json"
        if not path.exists():
            raise AssertionError(f"no fixture for {ticker} {year}-{month:02d}")
        return json.loads(path.read_text())

    monkeypatch.setattr("twmarket._client.fetch_stock_day", _fake)


def test_2025_lunar_new_year_closed(use_0050_fixtures):
    df = tw.calendar("2025-01-01", "2025-02-28")
    days = set(df["date"])
    for day in range(27, 32):  # Jan 27-31, 2025: LNY closure
        assert dt.date(2025, 1, day) not in days
    assert dt.date(2025, 1, 22) in days  # last day before the break
    assert dt.date(2025, 2, 3) in days  # first day after


def test_makeup_saturday_trades(use_0050_fixtures):
    # 2013-02-23 was a make-up Saturday and the market traded
    assert is_trading_day(dt.date(2013, 2, 23))
    assert dt.date(2013, 2, 23).weekday() == 5


def test_regular_weekend_not_trading(use_0050_fixtures):
    assert not is_trading_day("2025-01-04")  # ordinary Saturday


def test_next_trading_day_over_holiday(use_0050_fixtures):
    assert next_trading_day("2025-01-22") == dt.date(2025, 2, 3)


def test_calendar_returns_sorted_dates(use_0050_fixtures):
    df = tw.calendar("2025-01-01", "2025-01-31")
    assert list(df.columns) == ["date"]
    assert list(df["date"]) == sorted(df["date"])
    assert len(df) == 15  # trading days in Jan 2025


def test_reference_suspension_is_not_a_market_holiday(use_0050_fixtures):
    """0050 was suspended around its 2025-06 split; the market stayed open.

    A calendar built on one instrument would report five phantom holidays here,
    which would push every announce-date estimate in that window a week late.
    """
    import json as _json

    days = set(tw.calendar("2025-06-01", "2025-06-30")["date"])
    suspended = [dt.date(2025, 6, d) for d in (11, 12, 13, 16, 17)]
    assert all(d in days for d in suspended)

    only_0050 = _json.loads((FIXTURES / "stock_day_0050_202506.json").read_text())
    dates_0050 = {r[0] for r in only_0050["data"]}
    assert not any(f"114/06/{d.day:02d}" in dates_0050 for d in suspended)
