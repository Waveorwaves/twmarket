"""The local store has to survive an interrupted run.

A cold backfill takes minutes, so someone will press Ctrl-C during it. Whatever
that leaves behind must not break every later query.
"""

import datetime as dt

import pandas as pd
import pytest

import twmarket as tw
from twmarket import _store
from twmarket.revenue import ensure_period


def _halve(path):
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def test_an_interrupted_write_leaves_the_previous_file_intact(use_mops_fixture, monkeypatch):
    ensure_period("2025-06", today=dt.date(2025, 8, 1))
    path = _store.data_dir() / "revenue" / "2025-06.parquet"
    before = path.read_bytes()

    def dies_half_way(self, target, **kwargs):
        with open(target, "wb") as handle:
            handle.write(b"PAR1 half a file")
        raise KeyboardInterrupt

    monkeypatch.setattr(pd.DataFrame, "to_parquet", dies_half_way)
    with pytest.raises(KeyboardInterrupt):
        _store.append_revenue_observations("2025-06", _store.load_revenue_period("2025-06"))
    assert path.read_bytes() == before


def test_unreadable_revenue_month_says_which_file_and_what_to_do(use_mops_fixture):
    tw.revenue("2330", "2025-06", "2025-06")
    path = _store.data_dir() / "revenue" / "2025-06.parquet"
    _halve(path)
    with pytest.raises(RuntimeError, match=r"2025-06\.parquet cannot be read.*Delete that file"):
        tw.revenue("2330", "2025-06", "2025-06")

    path.unlink()  # following the message has to work
    assert len(tw.revenue("2330", "2025-06", "2025-06")) == 1


def test_unreadable_price_month_is_downloaded_again(caplog):
    first = tw.prices("2330", "2025-06-01", "2025-06-30")
    _halve(_store.data_dir() / "prices" / "2330_2025-06.parquet")
    with caplog.at_level("WARNING", logger="twmarket"):
        again = tw.prices("2330", "2025-06-01", "2025-06-30")
    assert again.equals(first)
    assert "cannot be read" in caplog.text
    assert tw.prices("2330", "2025-06-01", "2025-06-30").equals(first)  # and repaired


def test_stray_scratch_files_are_not_mistaken_for_months(use_mops_fixture):
    tw.revenue("2330", "2025-06", "2025-06")
    stray = _store.data_dir() / "revenue" / "2025-05.parquet.tmp"
    stray.write_bytes(b"left by an interrupted run")
    assert _store.list_revenue_periods() == ["2025-06"]
    assert not _store.has_revenue_period("2025-05")
