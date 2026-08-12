"""Date handling: ROC (Minguo) <-> ISO conversion and announce-date estimation.

All Taiwan sources use ROC years (Gregorian - 1911; year 114 = 2025). This is the
package's #1 parsing bug source, so every conversion goes through this module.
All dates are naive dates in Asia/Taipei terms — sources publish local dates only.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable

ROC_OFFSET = 1911

_ROC_DATE_RE = re.compile(r"^\s*(\d{2,3})/(\d{1,2})/(\d{1,2})\s*$")


def roc_year_to_gregorian(roc_year: int) -> int:
    """114 -> 2025."""
    if roc_year < 1:
        raise ValueError(f"invalid ROC year: {roc_year}")
    return roc_year + ROC_OFFSET


def gregorian_year_to_roc(year: int) -> int:
    """2025 -> 114."""
    roc = year - ROC_OFFSET
    if roc < 1:
        raise ValueError(f"year {year} predates the ROC calendar")
    return roc


def parse_roc_date(text: str) -> dt.date:
    """'114/06/02' -> date(2025, 6, 2)."""
    m = _ROC_DATE_RE.match(text)
    if not m:
        raise ValueError(f"not a ROC date: {text!r}")
    roc_year, month, day = (int(g) for g in m.groups())
    return dt.date(roc_year_to_gregorian(roc_year), month, day)


def parse_period(period: str) -> tuple[int, int]:
    """'2025-01' -> (2025, 1). Validates month range."""
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if not m:
        raise ValueError(f"period must be 'YYYY-MM', got {period!r}")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month in period {period!r}")
    return year, month


def estimate_announce_date(
    period: str,
    is_trading_day: Callable[[dt.date], bool] | None = None,
) -> dt.date:
    """Statutory-deadline estimate for a revenue period's announce date.

    Taiwan listed companies must report monthly revenue by the 10th of the
    following month. We use that deadline, rolled forward to the next trading
    day (weekends only if no calendar is provided). Conservative by design:
    most companies file earlier, so estimates never introduce lookahead bias.
    """
    year, month = parse_period(period)
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    date = dt.date(year, month, 10)

    def _trades(d: dt.date) -> bool:
        return is_trading_day(d) if is_trading_day is not None else d.weekday() < 5

    while not _trades(date):
        date += dt.timedelta(days=1)
    return date
