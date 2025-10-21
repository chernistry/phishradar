import asyncio
import time
import types
import sys

import pytest

from app.domain import canonical_domain
from app.http import async_http_client
from app.resilience import CircuitBreaker


def test_canonical_domain_variants():
    assert canonical_domain("http://WWW.Example.com:8080/path") == "example.com"
    assert canonical_domain("not a url") == ""


@pytest.mark.asyncio
async def test_async_http_client_context():
    async with async_http_client(timeout=0.1, max_connections=1, max_keepalive=1) as client:
        assert client is not None


@pytest.mark.asyncio
async def test_circuit_breaker_open_and_recover():
    cb = CircuitBreaker(failure_threshold=2, recovery_time=0.05)

    async def failing():
        raise RuntimeError("boom")

    # Two failures -> OPEN
    with pytest.raises(RuntimeError):
        await cb.run(failing)
    with pytest.raises(RuntimeError):
        await cb.run(failing)
    # While OPEN, allow() should be False and run() should raise circuit_open
    assert not (await cb.allow())
    with pytest.raises(RuntimeError):
        await cb.run(failing)
    # After recovery time, HALF_OPEN – success closes circuit
    await asyncio.sleep(0.06)

    async def ok():
        return 1

    assert await cb.run(ok) == 1

