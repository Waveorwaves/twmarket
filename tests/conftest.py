import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Every test gets a fresh, throwaway ~/.twmarket equivalent."""
    monkeypatch.setenv("TWMARKET_DATA_DIR", str(tmp_path / "twmarket-data"))


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch):
    """Tests must never hit live endpoints — fail loudly if they try."""

    def _blocked(*args, **kwargs):
        raise AssertionError("live HTTP request attempted in tests")

    monkeypatch.setattr("twmarket._client.get", _blocked)


@pytest.fixture(autouse=True)
def stock_day_from_fixtures(monkeypatch):
    """Serve recorded STOCK_DAY months to anything that needs a trading calendar.

    Announce-date estimation consults the calendar, so revenue and sync tests
    reach this too. A month with no recorded fixture answers with the recorded
    out-of-history response, which is what TWSE really returns for a window the
    calendar cannot cover — the production fallback path.
    """
    out_of_history = json.loads((FIXTURES / "stock_day_0050_200912.json").read_text())

    def _fake(ticker, year, month):
        path = FIXTURES / f"stock_day_{ticker}_{year:04d}{month:02d}.json"
        return json.loads(path.read_text()) if path.exists() else out_of_history

    monkeypatch.setattr("twmarket._client.fetch_stock_day", _fake)


@pytest.fixture
def mops_fixture_bytes():
    return (FIXTURES / "t21sc03_114_6_0.html").read_bytes()


@pytest.fixture
def use_mops_fixture(monkeypatch, mops_fixture_bytes):
    """Route fetch_mops_revenue to the recorded June-2025 file for any month."""
    calls = []

    def _fake(roc_year, month):
        calls.append((roc_year, month))
        return mops_fixture_bytes

    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", _fake)
    return calls
