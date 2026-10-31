"""A cap on how many design runs a public server starts a day.

Each design run is a series of Meta Model API calls and a sandboxed Blender
run on the GPU, so a server anyone can reach starts at most ``designs`` of
them, originals and revisions alike, in any 24 hours. One past the cap is
refused (429) with when the next frees up, and is never queued.
"""

import math
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from button_nz.api.store import Store

WINDOW = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(UTC)


class DailyCap:
    def __init__(self, store: Store, designs: int, clock: Callable[[], datetime] = utc_now) -> None:
        if designs < 1:
            raise ValueError(f"a daily cap of {designs} design runs allows none")
        self.store, self.designs, self.clock = store, designs, clock
        self._lock = threading.Lock()

    @contextmanager
    def admit(self) -> Generator[None]:
        """Hold the cap while one design run is created, or refuse it (429)."""
        with self._lock:
            now = self.clock()
            started = self.store.created_since(now - WINDOW)
            if len(started) >= self.designs:
                frees = started[len(started) - self.designs] + WINDOW
                wait = max(1, math.ceil((frees - now).total_seconds()))
                raise HTTPException(
                    429,
                    f"This server starts {self.designs} design runs a day, and they are "
                    f"used. The next frees up at {frees:%H:%M} UTC.",
                    headers={"Retry-After": str(wait)},
                )
            yield
