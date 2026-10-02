"""The download progress line: a sign of life during a cold-cache backfill."""

import io

import twmarket as tw
from twmarket._progress import Progress


class _Terminal(io.StringIO):
    def isatty(self):
        return True


def _clock(*ticks):
    it = iter(ticks)
    return lambda: next(it)


def test_live_terminal_gets_one_line_that_updates_in_place():
    out = _Terminal()
    # start, after month 1, after month 2, finish
    with Progress("monthly revenue", 3, stream=out, clock=_clock(0, 0, 6, 12, 18)) as progress:
        progress.step("2025-04")
        progress.step("2025-05")
        progress.step("2025-06")
    text = out.getvalue()
    assert text.count("\n") == 1  # everything on one line until the summary ends it
    assert "\r" in text
    assert "1/3  (2025-04)" in text
    assert "3/3  (2025-06)  about 6s left" in text
    summary = "downloaded 3 months of monthly revenue in 18s (cached from now on)"
    assert text.rstrip().endswith(summary)


def test_log_file_or_notebook_gets_a_start_line_and_an_end_line():
    out = io.StringIO()  # not a terminal: no carriage returns, no per-month spam
    with Progress("monthly revenue", 3, stream=out, clock=_clock(0, 0, 6, 12, 18)) as progress:
        for period in ("2025-04", "2025-05", "2025-06"):
            progress.step(period)
    lines = out.getvalue().splitlines()
    assert "\r" not in out.getvalue()
    assert lines == [
        "twmarket: downloading 3 months of monthly revenue (rate-limited; cached afterwards)",
        "twmarket: downloaded 3 months of monthly revenue in 18s (cached from now on)",
    ]


def test_short_downloads_stay_silent():
    out = _Terminal()
    with Progress("monthly revenue", 2, stream=out) as progress:  # a few seconds: not a hang
        progress.step("2025-05")
        progress.step("2025-06")
    assert out.getvalue() == ""


def test_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("TWMARKET_PROGRESS", "0")
    out = _Terminal()
    with Progress("monthly revenue", 10, stream=out) as progress:
        progress.step("2025-06")
    assert out.getvalue() == ""


def test_failure_ends_the_line_without_claiming_success():
    out = _Terminal()
    try:
        with Progress("monthly revenue", 3, stream=out) as progress:
            progress.step("2025-04")
            raise RuntimeError("network down")
    except RuntimeError:
        pass
    assert "downloaded" not in out.getvalue()
    assert out.getvalue().endswith("\n")  # the traceback starts on its own line


def test_long_durations_read_as_minutes():
    out = io.StringIO()
    with Progress("monthly revenue", 3, stream=out, clock=_clock(0, 0, 40, 80, 112)) as progress:
        for period in ("a", "b", "c"):
            progress.step(period)
    assert "in 1m 52s" in out.getvalue()


def test_revenue_backfill_reports_progress_and_cached_queries_do_not(use_mops_fixture, capsys):
    tw.revenue("2330", "2025-01", "2025-06")
    err = capsys.readouterr().err
    assert "downloading 5 months of monthly revenue" in err  # the 6th was the ticker lookup
    assert "downloaded 5 months of monthly revenue" in err

    tw.revenue("2330", "2025-01", "2025-06")
    assert capsys.readouterr().err == ""


def test_prices_backfill_reports_progress(capsys):
    tw.prices("2330", "2025-01-01", "2025-06-30")
    assert "months of daily prices for 2330" in capsys.readouterr().err
    tw.prices("2330", "2025-01-01", "2025-06-30")
    assert capsys.readouterr().err == ""
