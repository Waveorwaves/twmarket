"""Property tests for how sync() dates a first sighting after the deadline.

The rule under test (`revenue/checked.json`): a row first seen after the deadline gets
`today` when an earlier check on or after the deadline did not have it, and the deadline
estimate otherwise. The safety property is that no announce date comes out *earlier* than
the figure was knowable.

Each scenario fixes the ground truth — the day every company really appeared on MOPS —
then replays a random schedule of syncs and backfills against it and checks the store.
"""

from __future__ import annotations

import datetime as dt
import json
import random

import pytest

from twmarket import _store
from twmarket.revenue import ensure_period, parse_bulk_file
from twmarket.sync import sync_period

PERIOD = "2025-06"
DEADLINE = dt.date(2025, 7, 10)
DAYS = [dt.date(2025, 7, 1) + dt.timedelta(days=i) for i in range(35)]  # 07-01 .. 08-04


def _drop_rows(content: bytes, tickers) -> bytes:
    for ticker in tickers:
        at = content.find(f">{ticker}<".encode())
        start = content.rfind(b"<tr align=right>", 0, at)
        end = content.find(b"</tr>", at) + len(b"</tr>")
        content = content[:start] + content[end:]
    return content


@pytest.fixture
def world(monkeypatch, mops_fixture_bytes):
    """MOPS as a function of the day: companies in `arrival` are absent until their day."""
    state = {"today": None, "arrival": {}}

    def served():
        absent = [t for t, day in state["arrival"].items() if day > state["today"]]
        return _drop_rows(mops_fixture_bytes, absent)

    monkeypatch.setattr("twmarket._client.fetch_mops_revenue", lambda y, m: served())
    state["tickers"] = list(parse_bulk_file(mops_fixture_bytes, PERIOD)["ticker"][:6])
    return state


def _run(world, rng, *, lose_checks=False):
    """Replay one random schedule. Returns (arrival, proofs, store rows by ticker)."""
    world["arrival"] = {
        t: rng.choice(DAYS[:28]) for t in world["tickers"]  # arrive anywhere 07-01 .. 07-28
    }
    proofs = []  # days a persisted check ran on/after the deadline
    for day in DAYS:
        if rng.random() > 0.55:
            continue  # cron down / nobody looked today
        world["today"] = day
        had_rows = _store.has_revenue_period(PERIOD)
        if rng.random() < 0.3:
            ensure_period(PERIOD, today=day)  # a revenue() query: backfill or top-up
            persisted = had_rows or (_store.has_revenue_period(PERIOD))
        else:
            sync_period(PERIOD, today=day)
            persisted = True
        if persisted and day >= DEADLINE:
            proofs.append(day)
        if lose_checks and rng.random() < 0.15:
            (_store.data_dir() / "revenue" / "checked.json").unlink(missing_ok=True)
    stored = _store.load_revenue_period(PERIOD)
    return world["arrival"], proofs, stored


@pytest.mark.parametrize("seed", range(40))
def test_no_announce_date_precedes_the_appearance_when_a_late_check_proves_absence(world, seed):
    rng = random.Random(seed)
    arrival, proofs, stored = _run(world, rng)
    if stored is None:
        pytest.skip("this schedule never ran")

    first = stored.groupby("ticker").head(1).set_index("ticker")
    for ticker, day in arrival.items():
        if ticker not in first.index:
            continue
        row = first.loc[ticker]
        # Non-estimated dates are observations: never earlier than the sighting.
        if not row["announce_date_estimated"]:
            assert row["announce_date"] == row["observed_date"], (seed, ticker)
            assert row["announce_date"] >= day, (seed, ticker)
        # The commit's claim: proof of absence on/after the deadline defeats the estimate.
        proven_absent = [c for c in proofs if c < day and c < row["observed_date"]]
        if proven_absent and day > DEADLINE:
            assert row["announce_date"] >= day, (
                f"seed {seed}: {ticker} appeared {day}, was absent in a stored check on "
                f"{max(proven_absent)}, yet is dated {row['announce_date']} "
                f"(estimated={row['announce_date_estimated']})"
            )


def test_every_non_estimated_row_is_dated_the_day_it_was_observed(world):
    """The honesty invariant, over many schedules, including restatement-free late filers."""
    for seed in range(100, 130):
        _store_reset()
        _, _, stored = _run(world, random.Random(seed))
        if stored is None:
            continue
        live = stored[~stored["announce_date_estimated"]]
        assert (live["announce_date"] == live["observed_date"]).all(), seed


def _store_reset():
    import shutil

    shutil.rmtree(_store.data_dir(), ignore_errors=True)


# --- the check record itself --------------------------------------------------


def test_losing_checked_json_can_only_cost_precision_never_safety_in_the_estimate_direction(
    world, mops_fixture_bytes, without_ticker
):
    """If the record of no-change checks is lost, a late filer falls back to the estimate.

    That date is earlier than the filing — the exposure the record exists to remove — so a
    wiped file has to be visible in the flag (estimated=True), never silent.
    """
    world["arrival"] = {"1101": dt.date(2025, 7, 15)}
    world["today"] = dt.date(2025, 7, 9)
    sync_period(PERIOD, today=world["today"])
    for day in (dt.date(2025, 7, 12), dt.date(2025, 7, 13), dt.date(2025, 7, 14)):
        world["today"] = day
        sync_period(PERIOD, today=day)  # nothing new; recorded only in checked.json
    (_store.data_dir() / "revenue" / "checked.json").unlink()

    world["today"] = dt.date(2025, 7, 15)
    appended = sync_period(PERIOD, today=world["today"])
    row = appended[appended["ticker"] == "1101"].iloc[0]
    assert row["announce_date_estimated"]  # honest about the fallback
    assert row["announce_date"] == DEADLINE


def test_checked_json_is_not_mistaken_for_a_period_file():
    _store.mark_revenue_checked(PERIOD, dt.date(2025, 7, 11))
    assert _store.list_revenue_periods() == []
    assert json.loads((_store.data_dir() / "revenue" / "checked.json").read_text()) == {
        PERIOD: "2025-07-11"
    }


# --- known exposure: pinned so a change to it is deliberate -------------------


def test_gap_across_the_deadline_still_falls_back_to_an_earlier_estimate(world):
    """Watched before the deadline, then blind across it: the estimate can precede the filing.

    1101 was absent on 07-09 and appeared on 07-12; the cron was down 07-10..07-14. When
    sync() next runs, the only earlier check predates the deadline, so there is no proof
    the company was still missing *after* it. The row is dated at the deadline (07-10) —
    two days before it existed — and flagged estimated. This is the cold-start trade-off
    applied to a gap; the README must not promise that estimates are never early.
    """
    world["arrival"] = {"1101": dt.date(2025, 7, 12)}
    world["today"] = dt.date(2025, 7, 9)
    sync_period(PERIOD, today=world["today"])

    world["today"] = dt.date(2025, 7, 15)
    appended = sync_period(PERIOD, today=world["today"])
    row = appended[appended["ticker"] == "1101"].iloc[0]
    assert row["announce_date"] == DEADLINE < world["arrival"]["1101"]
    assert row["announce_date_estimated"]  # at least honest about it


# --- open: a month is frozen one check after its deadline ----------------------


def test_a_backfill_just_after_the_deadline_does_not_freeze_out_late_filers(world):
    world["arrival"] = {"1101": dt.date(2025, 7, 15)}
    world["today"] = dt.date(2025, 7, 12)
    ensure_period(PERIOD, today=world["today"])  # a first revenue() query, two days late
    stored = _store.load_revenue_period(PERIOD)
    assert stored[stored["ticker"] == "1101"].empty  # not filed yet: correct so far

    world["today"] = dt.date(2025, 7, 16)  # 1101 has filed since
    df = ensure_period(PERIOD, today=world["today"])
    late = df[df["ticker"] == "1101"]
    assert len(late) == 1
    assert late.iloc[0]["announce_date"] == dt.date(2025, 7, 16)  # dated when it appeared
    assert not late.iloc[0]["announce_date_estimated"]
