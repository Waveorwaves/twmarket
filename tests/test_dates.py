import datetime as dt

import pytest

from twmarket._dates import (
    estimate_announce_date,
    gregorian_year_to_roc,
    parse_period,
    parse_roc_date,
    roc_year_to_gregorian,
)


def test_roc_year_conversion():
    assert roc_year_to_gregorian(114) == 2025
    assert roc_year_to_gregorian(98) == 2009
    assert gregorian_year_to_roc(2025) == 114
    assert gregorian_year_to_roc(1912) == 1


def test_roc_year_invalid():
    with pytest.raises(ValueError):
        roc_year_to_gregorian(0)
    with pytest.raises(ValueError):
        gregorian_year_to_roc(1900)


def test_parse_roc_date():
    assert parse_roc_date("114/06/02") == dt.date(2025, 6, 2)
    assert parse_roc_date("98/1/5") == dt.date(2009, 1, 5)
    assert parse_roc_date(" 114/12/31 ") == dt.date(2025, 12, 31)


def test_parse_roc_date_invalid():
    for bad in ("2025-06-02", "114/13/01", "", "abc"):
        with pytest.raises(ValueError):
            parse_roc_date(bad)


def test_parse_period():
    assert parse_period("2025-01") == (2025, 1)
    assert parse_period("2024-12") == (2024, 12)
    for bad in ("2025-13", "2025-1", "202501", "2025/01"):
        with pytest.raises(ValueError):
            parse_period(bad)


def test_estimate_announce_date_plain_weekday():
    # June 2025 revenue: deadline 2025-07-10 (Thursday) — no roll needed
    assert estimate_announce_date("2025-06") == dt.date(2025, 7, 10)


def test_estimate_announce_date_weekend_roll():
    # April 2025 revenue: 2025-05-10 is a Saturday -> roll to Monday 05-12
    assert estimate_announce_date("2025-04") == dt.date(2025, 5, 12)


def test_estimate_announce_date_december_wraps_year():
    # December 2024 revenue: deadline 2025-01-10 (Friday)
    assert estimate_announce_date("2024-12") == dt.date(2025, 1, 10)


def test_estimate_announce_date_with_calendar():
    # Custom calendar that says the 10th and 11th are holidays
    holidays = {dt.date(2025, 7, 10), dt.date(2025, 7, 11)}

    def is_trading_day(d):
        return d.weekday() < 5 and d not in holidays

    assert estimate_announce_date("2025-06", is_trading_day) == dt.date(2025, 7, 14)
