from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Simple async RPS limiter using sleep spacing.

    Example: rps=1.0 allows ~1 call per second across await acquire() calls.
    """

    def __init__(self, rps: float) -> None:
        self.period = 1.0 / max(0.001, rps)
        self._last: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._last + self.period - now)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

