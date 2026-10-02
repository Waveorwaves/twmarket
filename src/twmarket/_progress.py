"""One-line download progress on stderr.

A cold cache means minutes of rate-limited requests, and silence for that long
looks like a hang. Queries served from the store never show anything.
Set TWMARKET_PROGRESS=0 to switch it off.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from typing import TextIO

#: Fewer downloads than this take a few seconds and are not worth announcing.
MIN_ITEMS = 3



def _duration(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m {seconds % 60:02d}s"


class Progress:
    """Counts downloads as they start: `with Progress(...) as p: p.step("2025-06")`.

    On a terminal the line is rewritten in place with a time estimate. Anywhere
    else (a log file, a notebook) it is a start line and an end line, so nothing
    fills up with carriage returns.
    """

    def __init__(
        self,
        what: str,
        total: int,
        stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._what, self._total = what, total
        self._stream = stream if stream is not None else sys.stderr
        self._clock = clock
        switched_off = os.environ.get("TWMARKET_PROGRESS", "1").lower() in ("0", "false", "off")
        self._enabled = total >= MIN_ITEMS and not switched_off
        self._live = self._enabled and self._stream.isatty()
        self._started = clock() if self._enabled else 0.0
        self._count = 0
        self._width = 0  # length of the line currently on screen

    def __enter__(self) -> Progress:
        return self

    def _write(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()

    def _rewrite(self, line: str, end: str = "") -> None:
        """Replace the line on screen. Padding with spaces overwrites a longer
        previous line without terminal escape codes, which older Windows consoles
        print literally."""
        self._write("\r" + line.ljust(self._width) + end)
        self._width = len(line)

    def step(self, detail: str) -> None:
        """Announce the download that is about to start."""
        if not self._enabled:
            return
        finished, now = self._count, self._clock()
        self._count += 1
        if not self._live:
            if finished == 0:
                self._write(
                    f"twmarket: downloading {self._total} months of {self._what} "
                    "(rate-limited; cached afterwards)\n"
                )
            return
        line = f"twmarket: downloading {self._what}  {self._count}/{self._total}  ({detail})"
        if finished:
            left = (now - self._started) / finished * (self._total - finished)
            line += f"  about {_duration(left)} left"
        self._rewrite(line)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self._enabled or self._count == 0:
            return
        if exc_type is not None:
            if self._live:
                self._write("\n")  # leave the half-finished line; the error follows
            return
        took = _duration(self._clock() - self._started)
        summary = (
            f"twmarket: downloaded {self._count} months of {self._what} in {took} "
            "(cached from now on)"
        )
        if self._live:
            self._rewrite(summary, end="\n")
        else:
            self._write(summary + "\n")
