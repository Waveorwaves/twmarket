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
