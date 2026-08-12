"""HTTP layer: shared session with retry/backoff, polite rate limiting, realistic UA.

All endpoint URLs live here so a host migration (e.g. mopsov going away) touches one file.
"""

from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

MOPS_REVENUE_URL = "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{month}{suffix}.html"
TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"

MIN_REQUEST_SPACING = 1.0  # seconds between any two live requests

_session: requests.Session | None = None
_last_request_time = 0.0


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
        retry = Retry(
            total=4,
            backoff_factor=2.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def _throttle() -> None:
    global _last_request_time
    wait = MIN_REQUEST_SPACING - (time.monotonic() - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.monotonic()


def get(url: str, params: dict | None = None, timeout: float = 30.0) -> requests.Response:
    """Rate-limited GET with retry/backoff. Raises for HTTP errors."""
    _throttle()
    resp = _get_session().get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp


def fetch_mops_revenue(roc_year: int, month: int) -> bytes:
    """Fetch one bulk monthly revenue file (raw Big5 bytes).

    ROC year <= 98 files drop the trailing `_0` in the filename.
    """
    suffix = "" if roc_year <= 98 else "_0"
    url = MOPS_REVENUE_URL.format(roc_year=roc_year, month=month, suffix=suffix)
    return get(url).content


def fetch_stock_day(ticker: str, year: int, month: int) -> dict:
    """Fetch one stock x one month of daily OHLCV from TWSE (JSON)."""
    params = {"response": "json", "date": f"{year:04d}{month:02d}01", "stockNo": ticker}
    return get(TWSE_STOCK_DAY_URL, params=params).json()
