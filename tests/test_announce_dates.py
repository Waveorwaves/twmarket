"""Announce-date estimation against the real trading calendar.

The package's central promise is that an estimated announce date can only ever
be *late*, never early. Rolling the statutory deadline over weekends alone
breaks that promise whenever the 10th falls inside a market holiday.
"""

import datetime as dt

from twmarket._dates import estimate_announce_date, statutory_deadline
from twmarket.revenue import announce_date_for


def test_deadline_is_the_tenth():
    assert statutory_deadline("2025-06") == dt.date(2025, 7, 10)
    assert statutory_deadline("2024-12") == dt.date(2025, 1, 10)


def test_trading_deadline_needs_no_roll():
    # 2025-07-10 was an ordinary trading Thursday
    assert announce_date_for("2025-06") == dt.date(2025, 7, 10)


def test_rolls_past_lunar_new_year_closure():
    # January 2013 revenue was due Sunday 2013-02-10. The weekday-only roll
    # lands on Monday 2013-02-11 — but TWSE was shut for the Lunar New Year and
    # did not trade again until 2013-02-18, a week later (both reference
    # instruments confirm the gap in tests/fixtures/stock_day_*_201302.json).
    assert statutory_deadline("2013-01") == dt.date(2013, 2, 10)
    assert estimate_announce_date("2013-01") == dt.date(2013, 2, 11)  # weekday-only: too early
    assert announce_date_for("2013-01") == dt.date(2013, 2, 18)


def test_falls_back_to_weekday_roll_beyond_price_history():
    # No calendar can exist for a deadline still in the future.
    assert announce_date_for("2030-01") == estimate_announce_date("2030-01")
