from __future__ import annotations

import asyncio
import time
from typing import Callable, Awaitable, TypeVar


T = TypeVar("T")


class CircuitBreaker:
    """Minimal async circuit breaker.

    States: CLOSED -> OPEN (on failure threshold) -> HALF_OPEN (after cooldown) -> CLOSED (on success).
    """

    def __init__(self, failure_threshold: int = 5, recovery_time: float = 10.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.state = "CLOSED"
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        async with self._lock:
            if self.state == "OPEN":
                if time.monotonic() - self._opened_at >= self.recovery_time:
                    self.state = "HALF_OPEN"
                else:
                    return False
            return True

    async def on_success(self) -> None:
        async with self._lock:
            self.failures = 0
            self.state = "CLOSED"

    async def on_failure(self) -> None:
        async with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self._opened_at = time.monotonic()

    async def run(self, fn: Callable[[], Awaitable[T]]) -> T:
        if not await self.allow():
            raise RuntimeError("circuit_open")
        try:
            result = await fn()
            await self.on_success()
            return result
        except Exception:
            await self.on_failure()
            raise

