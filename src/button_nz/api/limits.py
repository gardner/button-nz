"""A cap on how many design runs a public server starts a day.

Each design run is a series of Meta Model API calls and a sandboxed Blender
run on the GPU, so a server anyone can reach starts at most ``designs`` of
them, originals and revisions alike, in any 24 hours. One past the cap is
refused (429) with when the next frees up, and is never queued.
"""

import math
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

WINDOW = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(UTC)


class DailyCap:
    """At most ``limit`` of something (``noun``) in any 24 hours, counted by
    ``started``: when each began since a time, oldest first."""

    def __init__(
        self,
        started: Callable[[datetime], Sequence[datetime]],
        limit: int,
        noun: str = "design runs",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if limit < 1:
            raise ValueError(f"a daily cap of {limit} {noun} allows none")
        self.started, self.limit, self.noun, self.clock = started, limit, noun, clock
        self._lock = threading.Lock()

    @contextmanager
    def admit(self) -> Generator[None]:
        """Hold the cap while one more is created, or refuse it (429)."""
        with self._lock:
            now = self.clock()
            started = self.started(now - WINDOW)
            if len(started) >= self.limit:
                frees = started[len(started) - self.limit] + WINDOW
                wait = max(1, math.ceil((frees - now).total_seconds()))
                raise HTTPException(
                    429,
                    f"This server starts {self.limit} {self.noun} a day, and they are "
                    f"used. The next frees up at {frees:%H:%M} UTC.",
                    headers={"Retry-After": str(wait)},
                )
            yield
